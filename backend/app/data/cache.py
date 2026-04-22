"""Async-aware in-memory TTL cache.

全市场股票清单冷拉代价高（CN Mairui list 0.3s 但 HK AkShare Sina 要 8s、US FMP
screener 10s+），后续每股补 PE/PB/ROE 还会放大一个数量级——冷拉完必须缓存。

用法：
    cache = AsyncTTLCache[list[Stock]](ttl_seconds=86400)
    result = await cache.get_or_load("cn_universe", loader)

语义：
- 命中且未过期 → 直接返回
- 未命中或已过期 → 走 loader；同 key 并发请求只跑一次 loader（内部 per-key 锁）
- loader 抛异常 → 不缓存，异常向上透传
"""

import asyncio
import time
from collections.abc import Awaitable, Callable


class AsyncTTLCache[T]:
    def __init__(self, ttl_seconds: float) -> None:
        self._ttl = ttl_seconds
        self._store: dict[str, tuple[T, float]] = {}
        self._locks: dict[str, asyncio.Lock] = {}

    def get(self, key: str) -> T | None:
        hit = self._store.get(key)
        if hit is None:
            return None
        value, ts = hit
        if time.monotonic() - ts > self._ttl:
            self._store.pop(key, None)
            return None
        return value

    def set(self, key: str, value: T) -> None:
        self._store[key] = (value, time.monotonic())

    async def get_or_load(self, key: str, loader: Callable[[], Awaitable[T]]) -> T:
        cached = self.get(key)
        if cached is not None:
            return cached
        lock = self._locks.setdefault(key, asyncio.Lock())
        async with lock:
            # 二次检查：抢到锁之前可能别人已经填好了
            cached = self.get(key)
            if cached is not None:
                return cached
            value = await loader()
            self.set(key, value)
            return value

    def invalidate(self, key: str) -> None:
        self._store.pop(key, None)

    def clear(self) -> None:
        self._store.clear()
