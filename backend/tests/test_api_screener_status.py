"""`/api/screener/status` 端点 + `/api/screener` 冷启动期 202 行为。

设计:cache miss 时不再阻塞 loader,而是立即回 202 + 进度 JSON,前端轮询 /status
直到 ready 再拉 /screener。warming 中的重复请求也走 202(不 double-fire,由
AsyncTTLCache 的 per-key 锁兜底)。
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from app.api import screener as screener_mod
from app.api.screener import ScreenerResult
from app.data.cache import AsyncTTLCache
from app.main import app


def _reset_state() -> None:
    for m in ("cn", "us", "hk"):
        screener_mod._prewarm_state[m] = screener_mod.PrewarmStatus(status="idle")


@pytest.fixture(autouse=True)
def _isolate_state(monkeypatch):
    """每个测试用独立 cache,state 清回 idle,避免串扰。"""
    _reset_state()
    fresh: AsyncTTLCache[list[ScreenerResult]] = AsyncTTLCache(3600)
    monkeypatch.setattr(screener_mod, "_screener_cache", fresh)
    yield


# ---------- GET /api/screener/status ----------


def test_status_endpoint_returns_all_three_markets() -> None:
    client = TestClient(app)
    r = client.get("/api/screener/status")
    assert r.status_code == 200
    body = r.json()
    assert set(body.keys()) == {"cn", "us", "hk"}
    for market in ("cn", "us", "hk"):
        assert body[market]["status"] == "idle"
        assert body[market]["done"] == 0
        assert body[market]["total"] == 0


def test_status_endpoint_reflects_in_memory_state() -> None:
    screener_mod._prewarm_state["cn"].status = "warming"
    screener_mod._prewarm_state["cn"].done = 1247
    screener_mod._prewarm_state["cn"].total = 5200

    client = TestClient(app)
    r = client.get("/api/screener/status")
    assert r.status_code == 200
    body = r.json()
    assert body["cn"]["status"] == "warming"
    assert body["cn"]["done"] == 1247
    assert body["cn"]["total"] == 5200


# ---------- GET /api/screener 202 行为 ----------


def test_screener_returns_rows_when_cache_hot(monkeypatch) -> None:
    """cache 有 ready 数据 → 200 + rows,行为不变。"""
    row = ScreenerResult(
        symbol="600036",
        name="招商银行",
        market="cn",
        exchange="SH",
        pe=Decimal("6.5"),
        pb=Decimal("1.0"),
        roe=Decimal("0.15"),
        dividend_yield=Decimal("0.04"),
        market_cap=Decimal("9e11"),
        graham_number=Decimal("50"),
        roe_missing=False,
    )
    # 直接塞进 fixture 注入的 cache
    screener_mod._screener_cache.set("cn", [row])
    screener_mod._prewarm_state["cn"].status = "ready"

    client = TestClient(app)
    r = client.get("/api/screener?market=cn&limit=10")
    assert r.status_code == 200
    body = r.json()
    assert len(body) == 1
    assert body[0]["symbol"] == "600036"


def test_screener_returns_202_when_warming(monkeypatch) -> None:
    """state=warming + cache miss → 202 + 进度 JSON,绝不阻塞 loader。"""
    screener_mod._prewarm_state["cn"].status = "warming"
    screener_mod._prewarm_state["cn"].done = 1247
    screener_mod._prewarm_state["cn"].total = 5200

    client = TestClient(app)
    r = client.get("/api/screener?market=cn&limit=10")
    assert r.status_code == 202
    body = r.json()
    assert body["status"] == "warming"
    assert body["done"] == 1247
    assert body["total"] == 5200


def test_screener_returns_202_and_kicks_off_when_idle(monkeypatch) -> None:
    """state=idle + cache miss → 202。核心契约是端点立刻回 202,不阻塞用户。

    create_task spawn 的后台 prewarm 在 TestClient 同步路径下不保证被调度,
    所以这里不断言 spawn 本身,只断言响应形状。
    """
    async def _noop_prewarm(market: str) -> None:
        return None
    monkeypatch.setattr(screener_mod, "prewarm", _noop_prewarm)

    client = TestClient(app)
    r = client.get("/api/screener?market=cn&limit=10")
    assert r.status_code == 202
    assert r.json()["status"] in ("idle", "warming")


def test_refresh_during_warming_is_noop(monkeypatch) -> None:
    """warming 中的 refresh 不能重置 state —— 在跑的 prewarm 的 tracker 还
    绑着这个 state 对象,重置会造成 done 继续涨而 total=0 的分裂态。

    实测 bug:用户点刷新后前端进度条卡在"预热上游清单"不动,因为 total=0。
    """
    screener_mod._prewarm_state["cn"].status = "warming"
    screener_mod._prewarm_state["cn"].done = 1247
    screener_mod._prewarm_state["cn"].total = 5200

    async def _noop_prewarm(market: str) -> None:
        return None
    monkeypatch.setattr(screener_mod, "prewarm", _noop_prewarm)

    client = TestClient(app)
    r = client.get("/api/screener?market=cn&limit=10&refresh=true")
    assert r.status_code == 202
    body = r.json()
    # state 不被重置:total 保持 5200,done 保持 1247
    assert body["status"] == "warming"
    assert body["done"] == 1247
    assert body["total"] == 5200


def test_refresh_invalidates_cache_and_returns_202(monkeypatch) -> None:
    """refresh=true 清 cache + 重置进度到 0,然后走 202 路径。

    不阻塞:CN 冷启动 22 分钟,阻塞一个 HTTP 请求不现实。前端轮询 /status
    跟进,ready 后再拉一次 /screener。
    """
    # 先塞一份老数据进 cache + ready 态
    row = ScreenerResult(
        symbol="600036",
        name="招商银行",
        market="cn",
        exchange="SH",
        pe=Decimal("6.5"),
        pb=Decimal("1.0"),
        roe=Decimal("0.15"),
        dividend_yield=Decimal("0.04"),
        market_cap=Decimal("9e11"),
        graham_number=Decimal("50"),
        roe_missing=False,
    )
    screener_mod._screener_cache.set("cn", [row])
    screener_mod._prewarm_state["cn"].status = "ready"
    screener_mod._prewarm_state["cn"].done = 5200
    screener_mod._prewarm_state["cn"].total = 5200

    # 让 fake prewarm 不抢事件循环时间片
    async def _noop_prewarm(market: str) -> None:
        return None
    monkeypatch.setattr(screener_mod, "prewarm", _noop_prewarm)

    client = TestClient(app)
    r = client.get("/api/screener?market=cn&limit=10&refresh=true")
    assert r.status_code == 202
    body = r.json()
    assert body["status"] == "idle"
    assert body["done"] == 0
    assert body["total"] == 0
    # 老缓存应被清
    assert screener_mod._screener_cache.get("cn") is None
