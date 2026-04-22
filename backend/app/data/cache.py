"""Async-aware TTL cache, optionally persisted to disk.

全市场股票清单冷拉代价高（CN Mairui list 0.3s 但 HK AkShare Sina 要 8s、US FMP
screener 10s+），后续每股补 PE/PB/ROE 还会放大一个数量级——冷拉完必须缓存。

screener 冷启动按 Mairui 240 req/min 限速能跑到 ~22 分钟(~5200 支 A 股);开发期
uvicorn --reload 频繁重启就会反复冷启。所以 cache 支持可选磁盘持久化:set 时
落盘、启动时 `load_from_disk()` 读回。时间戳用 wall-clock(`time.time()`)而非
`time.monotonic()`,因为 monotonic 是 process-local 的,跨进程落盘没意义。

用法：
    cache = AsyncTTLCache[list[Stock]](ttl_seconds=86400)
    result = await cache.get_or_load("cn_universe", loader)

    # 或带磁盘持久化:
    cache = AsyncTTLCache[list[Stock]](
        ttl_seconds=3600,
        persist_path=Path("data/cache.json"),
        serialize=lambda v: [s.model_dump() for s in v],
        deserialize=lambda v: [Stock.model_validate(s) for s in v],
    )
    cache.load_from_disk()  # 启动时调一次

语义：
- 命中且未过期 → 直接返回
- 未命中或已过期 → 走 loader；同 key 并发请求只跑一次 loader（内部 per-key 锁）
- loader 抛异常 → 不缓存，异常向上透传
- 有 persist_path 时,get_or_load 在写 cache 后同步把整份 store 覆盖写入磁盘
  (只有 3 个 key,写全量比 diff 简单稳)。文件原子替换(tmp → rename)。
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)


class AsyncTTLCache[T]:
    def __init__(
        self,
        ttl_seconds: float,
        *,
        persist_path: Path | None = None,
        serialize: Callable[[T], Any] | None = None,
        deserialize: Callable[[Any], T] | None = None,
    ) -> None:
        self._ttl = ttl_seconds
        self._store: dict[str, tuple[T, float]] = {}
        self._locks: dict[str, asyncio.Lock] = {}
        self._persist_path = persist_path
        self._serialize = serialize
        self._deserialize = deserialize
        if persist_path is not None and (serialize is None or deserialize is None):
            raise ValueError("persist_path requires both serialize and deserialize")

    def get(self, key: str) -> T | None:
        hit = self._store.get(key)
        if hit is None:
            return None
        value, ts = hit
        if time.time() - ts > self._ttl:
            self._store.pop(key, None)
            return None
        return value

    def set(self, key: str, value: T) -> None:
        self._store[key] = (value, time.time())

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
            self._write_to_disk()
            return value

    def invalidate(self, key: str) -> None:
        self._store.pop(key, None)
        self._write_to_disk()

    def clear(self) -> None:
        self._store.clear()
        self._write_to_disk()

    # ---- 磁盘持久化 ----

    def load_from_disk(self) -> None:
        """启动时从磁盘恢复未过期条目。文件不存在 / 损坏都当空处理。"""
        if self._persist_path is None or self._deserialize is None:
            return
        if not self._persist_path.exists():
            return
        try:
            payload = json.loads(self._persist_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as e:
            log.warning("cache load_from_disk failed path=%s: %s", self._persist_path, e)
            return
        if not isinstance(payload, dict):
            return
        now = time.time()
        for key, entry in payload.items():
            try:
                ts = float(entry["ts"])
                raw = entry["value"]
            except (TypeError, KeyError, ValueError):
                continue
            if now - ts > self._ttl:
                continue
            try:
                value = self._deserialize(raw)
            except Exception as e:  # noqa: BLE001 — 反序列化失败当作丢失条目
                log.warning("cache deserialize failed key=%s: %s", key, e)
                continue
            self._store[key] = (value, ts)

    def _write_to_disk(self) -> None:
        """把当前 store 同步落盘。3 个 key,写全量不做增量。"""
        if self._persist_path is None or self._serialize is None:
            return
        payload = {
            k: {"value": self._serialize(v), "ts": ts}
            for k, (v, ts) in self._store.items()
        }
        try:
            self._persist_path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self._persist_path.with_suffix(self._persist_path.suffix + ".tmp")
            tmp.write_text(
                json.dumps(payload, ensure_ascii=False, default=str),
                encoding="utf-8",
            )
            tmp.replace(self._persist_path)
        except OSError as e:
            log.warning("cache write_to_disk failed path=%s: %s", self._persist_path, e)
