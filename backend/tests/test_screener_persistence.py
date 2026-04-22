"""Screener cache 持久化 + lifespan 集成:重启不重算。

冷启动 22 分钟是 Mairui 限速硬算出来的,开发期 uvicorn --reload 每次重算无法接受。
测试:
- `_screener_cache` 是 PersistPath-配置过的,set 时落盘
- 进程重启后 load_from_disk() 能恢复数据
- lifespan 里 disk-hit 的市场直接标 ready、不 spawn prewarm
"""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

from app.api import screener as screener_mod
from app.api.screener import ScreenerResult
from app.data.cache import AsyncTTLCache


def _reset_state() -> None:
    for m in ("cn", "us", "hk"):
        screener_mod._prewarm_state[m] = screener_mod.PrewarmStatus(status="idle")


def _sample_row() -> ScreenerResult:
    return ScreenerResult(
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


def test_screener_cache_has_persist_path_wired() -> None:
    """生产 `_screener_cache` 实例应该配置了 persist_path + serialize/deserialize。

    不测具体路径——只保证持久化路径被接上了,否则重启还是重算。
    """
    cache = screener_mod._screener_cache
    assert cache._persist_path is not None
    assert cache._serialize is not None
    assert cache._deserialize is not None


@pytest.mark.asyncio
async def test_screener_result_roundtrips_through_persist(tmp_path: Path) -> None:
    """用生产 serialize/deserialize 把 ScreenerResult list 落盘 + 读回,
    Decimal 字段不丢精度。
    """
    from app.api.screener import ScreenerResult

    cache: AsyncTTLCache[list[ScreenerResult]] = AsyncTTLCache(
        ttl_seconds=3600,
        persist_path=tmp_path / "cache.json",
        serialize=lambda rows: [r.model_dump(mode="json") for r in rows],
        deserialize=lambda raw: [ScreenerResult.model_validate(d) for d in raw],
    )

    await cache.get_or_load("cn", lambda: _async_return([_sample_row()]))

    cache2: AsyncTTLCache[list[ScreenerResult]] = AsyncTTLCache(
        ttl_seconds=3600,
        persist_path=tmp_path / "cache.json",
        serialize=lambda rows: [r.model_dump(mode="json") for r in rows],
        deserialize=lambda raw: [ScreenerResult.model_validate(d) for d in raw],
    )
    cache2.load_from_disk()
    hit = cache2.get("cn")
    assert hit is not None
    assert len(hit) == 1
    assert hit[0].symbol == "600036"
    assert hit[0].pe == Decimal("6.5")
    assert hit[0].graham_number == Decimal("50")


@pytest.mark.asyncio
async def test_lifespan_skips_prewarm_for_hot_markets(monkeypatch, tmp_path: Path) -> None:
    """lifespan 启动时:disk-hit 的市场直接标 ready、不 spawn prewarm;miss 的走 prewarm。

    让 CN 在 disk 里是 hot,HK/US miss。期望:prewarm 只被调用 2 次(hk、us),
    state.cn 直接为 ready。
    """
    _reset_state()

    # 用临时路径装 cache
    fresh: AsyncTTLCache[list[ScreenerResult]] = AsyncTTLCache(
        ttl_seconds=3600,
        persist_path=tmp_path / "cache.json",
        serialize=lambda rows: [r.model_dump(mode="json") for r in rows],
        deserialize=lambda raw: [ScreenerResult.model_validate(d) for d in raw],
    )
    # 预先写入 cn 数据到磁盘
    fresh.set("cn", [_sample_row()])
    fresh._write_to_disk()  # 直接调内部方法让磁盘有数据(set 本身不写盘)
    monkeypatch.setattr(screener_mod, "_screener_cache", fresh)

    prewarm_calls: list[str] = []

    async def _fake_prewarm(market: str) -> None:
        prewarm_calls.append(market)

    monkeypatch.setattr(screener_mod, "prewarm", _fake_prewarm)

    # lifespan 应暴露一个"启动时做的初始化"入口,让测试能单独跑
    from app.api.screener import boot_screener_cache

    await boot_screener_cache()
    # boot 里的 create_task 是 fire-and-forget,需要让事件循环跑一拍才会执行
    import asyncio
    await asyncio.sleep(0)

    # CN 已 hot:不 spawn,状态 ready
    assert "cn" not in prewarm_calls
    assert screener_mod._prewarm_state["cn"].status == "ready"
    # HK/US miss:spawn
    assert set(prewarm_calls) == {"hk", "us"}


async def _async_return(value: Any) -> Any:
    return value
