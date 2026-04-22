"""Screener prewarm 进度追踪测试。

为什么:`/api/screener` 冷启动最长 ~22 分钟,前端需要显示 "1247/5200 (24%)" 而
不是干转圈。以模块级 `_prewarm_state` 记录三市场的 status/done/total,每个
per-stock 任务完成时 tick。`_compute_screener` 负责标 warming → ready / failed。
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

import pytest

from app.api import screener as screener_mod
from app.api.screener import (
    ProgressTracker,
    _cn_candidates,
    _compute_screener,
    get_prewarm_state,
)
from app.data.providers.base import Fundamentals, Stock
from app.data.providers.cn import CnProvider

# ---------- ProgressTracker 单元测试 ----------


def test_progress_tracker_starts_at_zero() -> None:
    t = ProgressTracker()
    assert t.done == 0
    assert t.total == 0


def test_progress_tracker_tick_increments_done() -> None:
    t = ProgressTracker()
    t.set_total(100)
    for _ in range(5):
        t.tick()
    assert t.done == 5
    assert t.total == 100


# ---------- prewarm_state 转换测试 ----------


def _reset_prewarm_state() -> None:
    """每个测试前把 _prewarm_state 三市场都清回 idle,避免串扰。"""
    for m in ("cn", "us", "hk"):
        screener_mod._prewarm_state[m] = screener_mod.PrewarmStatus(status="idle")


def test_prewarm_state_defaults_to_idle() -> None:
    _reset_prewarm_state()
    for market in ("cn", "us", "hk"):
        state = get_prewarm_state(market)  # type: ignore[arg-type]
        assert state.status == "idle"
        assert state.done == 0
        assert state.total == 0
        assert state.error is None


@pytest.mark.asyncio
async def test_compute_screener_marks_ready_on_success(monkeypatch) -> None:
    """成功路径:idle → warming → ready。"""
    _reset_prewarm_state()

    from app.screening.value import ScreenerCandidate

    async def _stub_cn_candidates(
        _provider: Any, tracker: ProgressTracker | None = None
    ) -> list[ScreenerCandidate]:
        return [
            ScreenerCandidate(
                symbol="600036",
                name="招商银行",
                market="cn",
                exchange="SH",
                pe=Decimal("6.5"),
                pb=Decimal("1.0"),
                roe=Decimal("0.15"),
                dividend_yield=Decimal("0.04"),
                market_cap=Decimal("9e11"),
            )
        ]

    monkeypatch.setattr(screener_mod, "_cn_candidates", _stub_cn_candidates)
    monkeypatch.setattr(
        screener_mod, "get_provider", lambda _m: CnProvider(mairui_client=None)
    )

    await _compute_screener("cn")
    state = get_prewarm_state("cn")
    assert state.status == "ready"
    assert state.error is None


@pytest.mark.asyncio
async def test_compute_screener_marks_failed_on_exception(monkeypatch) -> None:
    """异常路径:status=failed,error 记录异常字符串。"""
    _reset_prewarm_state()

    async def _broken_candidates(
        _provider: Any, tracker: ProgressTracker | None = None
    ) -> list[Any]:
        raise RuntimeError("upstream on fire")

    monkeypatch.setattr(screener_mod, "_cn_candidates", _broken_candidates)
    monkeypatch.setattr(
        screener_mod, "get_provider", lambda _m: CnProvider(mairui_client=None)
    )

    with pytest.raises(RuntimeError, match="upstream on fire"):
        await _compute_screener("cn")
    state = get_prewarm_state("cn")
    assert state.status == "failed"
    assert state.error is not None
    assert "upstream on fire" in state.error


@pytest.mark.asyncio
async def test_compute_screener_marks_failed_on_empty_passed(monkeypatch) -> None:
    """零行也算 failed——用户应该看到上游挂了,不是空白静默。"""
    _reset_prewarm_state()

    async def _empty_candidates(
        _provider: Any, tracker: ProgressTracker | None = None
    ) -> list[Any]:
        return []

    monkeypatch.setattr(screener_mod, "_cn_candidates", _empty_candidates)
    monkeypatch.setattr(
        screener_mod, "get_provider", lambda _m: CnProvider(mairui_client=None)
    )

    with pytest.raises(RuntimeError, match="0 passed rows"):
        await _compute_screener("cn")
    state = get_prewarm_state("cn")
    assert state.status == "failed"


# ---------- 进度 tick 穿透到 candidate helper ----------


@pytest.mark.asyncio
async def test_cn_candidates_ticks_progress_per_stock() -> None:
    """_cn_candidates 把 tracker 穿透到 per-stock 循环,每支完成后 tick。

    end state: tracker.total == universe size, tracker.done == universe size
    (不管这支有没有过粗筛,tick 都应该发生——否则进度条会卡)。
    """

    class _StubMairui:
        async def get_realtime(self, symbol: str) -> dict[str, Any]:
            return {"pe": 20, "sjl": 2, "sz": 1e12}

        async def aclose(self) -> None:
            pass

    provider = CnProvider(mairui_client=_StubMairui())  # type: ignore[arg-type]

    async def _universe() -> list[Stock]:
        return [
            Stock(symbol="600519", name="A", market="cn", exchange="SH"),
            Stock(symbol="600036", name="B", market="cn", exchange="SH"),
            Stock(symbol="000001", name="C", market="cn", exchange="SZ"),
        ]

    async def _passthrough(base: Fundamentals) -> Fundamentals:
        return base

    provider.list_stocks = _universe  # type: ignore[method-assign]
    provider.enrich_fundamentals = _passthrough  # type: ignore[method-assign]

    tracker = ProgressTracker()
    await _cn_candidates(provider, tracker=tracker)
    assert tracker.total == 3
    assert tracker.done == 3
