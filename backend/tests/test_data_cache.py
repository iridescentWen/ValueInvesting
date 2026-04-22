"""AsyncTTLCache 磁盘持久化测试。

为什么要持久化：screener 冷启动 ~22min(CN 限速),uvicorn --reload 每次都清空
in-memory cache,开发期几乎永远拿不到数据。给 cache 加 `persist_path` +
`serialize/deserialize` 回调,set 时落盘、启动时 `load_from_disk()`。
"""

from __future__ import annotations

import json
import time
from pathlib import Path

import pytest

from app.data.cache import AsyncTTLCache


def _make_persistent_cache(
    tmp_path: Path, ttl: float = 3600
) -> AsyncTTLCache[dict]:
    return AsyncTTLCache[dict](
        ttl_seconds=ttl,
        persist_path=tmp_path / "cache.json",
        serialize=lambda v: v,
        deserialize=lambda v: v,
    )


@pytest.mark.asyncio
async def test_persist_roundtrip_across_instances(tmp_path: Path) -> None:
    """cache1 set → 自动落盘;cache2 load_from_disk 后能读出相同值。"""
    cache1 = _make_persistent_cache(tmp_path)
    await cache1.get_or_load("k", lambda: _loader({"a": 1}))
    assert (tmp_path / "cache.json").exists()

    cache2 = _make_persistent_cache(tmp_path)
    cache2.load_from_disk()
    assert cache2.get("k") == {"a": 1}


@pytest.mark.asyncio
async def test_persist_skips_expired_on_load(tmp_path: Path) -> None:
    """磁盘上过期的 entry(ts 太旧)load 时不恢复。"""
    persist_path = tmp_path / "cache.json"
    stale_payload = {
        "k": {"value": {"a": 1}, "ts": time.time() - 10_000},  # 远超 3600 TTL
    }
    persist_path.write_text(json.dumps(stale_payload))

    cache = _make_persistent_cache(tmp_path, ttl=3600)
    cache.load_from_disk()
    assert cache.get("k") is None


def test_load_from_disk_missing_file_is_noop(tmp_path: Path) -> None:
    """首次启动没有文件 → load_from_disk() 不抛不打印。"""
    cache = _make_persistent_cache(tmp_path)
    cache.load_from_disk()  # 不应抛
    assert cache.get("k") is None


def test_load_from_disk_corrupt_json_is_noop(tmp_path: Path) -> None:
    """磁盘文件损坏 → 不抛,当空处理。下次 set 会覆盖。"""
    (tmp_path / "cache.json").write_text("{not json")
    cache = _make_persistent_cache(tmp_path)
    cache.load_from_disk()
    assert cache.get("k") is None


@pytest.mark.asyncio
async def test_no_persist_path_still_works(tmp_path: Path) -> None:
    """没传 persist_path 的 cache 行为不变,不碰磁盘。"""
    cache: AsyncTTLCache[dict] = AsyncTTLCache(ttl_seconds=3600)
    await cache.get_or_load("k", lambda: _loader({"a": 1}))
    assert cache.get("k") == {"a": 1}
    # tmp_path 不应被碰过
    assert not list(tmp_path.iterdir())


@pytest.mark.asyncio
async def test_serialize_deserialize_applied(tmp_path: Path) -> None:
    """自定义 serialize / deserialize 被正确调用——例如 Pydantic 对象。"""

    class _Box:
        def __init__(self, n: int) -> None:
            self.n = n

    cache: AsyncTTLCache[_Box] = AsyncTTLCache(
        ttl_seconds=3600,
        persist_path=tmp_path / "cache.json",
        serialize=lambda b: {"n": b.n},
        deserialize=lambda d: _Box(d["n"]),
    )
    await cache.get_or_load("k", lambda: _loader(_Box(42)))

    cache2: AsyncTTLCache[_Box] = AsyncTTLCache(
        ttl_seconds=3600,
        persist_path=tmp_path / "cache.json",
        serialize=lambda b: {"n": b.n},
        deserialize=lambda d: _Box(d["n"]),
    )
    cache2.load_from_disk()
    hit = cache2.get("k")
    assert hit is not None
    assert hit.n == 42


async def _loader[T](value: T) -> T:
    return value
