import httpx
import pytest

from app.data.clients import mairui as mairui_mod
from app.data.clients.mairui import MairuiClient


def _make_client(handler) -> MairuiClient:
    transport = httpx.MockTransport(handler)
    http = httpx.AsyncClient(base_url="http://mairui.test", transport=transport, timeout=5.0)
    return MairuiClient(api_key="LICENSE", base_url="http://mairui.test", client=http)


@pytest.mark.asyncio
async def test_financial_metrics_hits_cwzb_with_license_key_in_path() -> None:
    seen: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["path"] = request.url.path
        return httpx.Response(200, json=[{"date": "2024-12-31", "zzc": 1000}])

    client = _make_client(handler)
    try:
        data = await client.get_financial_metrics("600519")
    finally:
        await client.aclose()

    # license_key 走路径不走 query
    assert seen["path"] == "/hscp/cwzb/600519/LICENSE"
    assert data == [{"date": "2024-12-31", "zzc": 1000}]


@pytest.mark.asyncio
async def test_non_list_response_coerced_to_empty_list() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        # Mairui 偶尔返回 error dict 而不是 list
        return httpx.Response(200, json={"error": "invalid code"})

    client = _make_client(handler)
    try:
        data = await client.get_financial_metrics("000000")
    finally:
        await client.aclose()

    assert data == []


@pytest.mark.asyncio
async def test_http_error_raises() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(403, json={"error": "bad license"})

    client = _make_client(handler)
    try:
        with pytest.raises(httpx.HTTPStatusError):
            await client.get_financial_metrics("600519")
    finally:
        await client.aclose()


@pytest.mark.asyncio
async def test_get_realtime_hits_ssjy_path_and_returns_dict() -> None:
    seen: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["path"] = request.url.path
        return httpx.Response(
            200,
            json={
                "t": "2026-04-21 15:00:00",
                "p": 1411.63,
                "pe": 21.47,
                "sjl": 7.23,
                "sz": 1767742203600.0,
                "lt": 1767742203600.0,
            },
        )

    client = _make_client(handler)
    try:
        data = await client.get_realtime("600519")
    finally:
        await client.aclose()

    assert seen["path"] == "/hsrl/ssjy/600519/LICENSE"
    assert data["pe"] == 21.47
    assert data["sjl"] == 7.23
    assert data["sz"] == 1767742203600.0


@pytest.mark.asyncio
async def test_get_realtime_non_dict_coerced_to_empty() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=[])  # 错误时 Mairui 偶尔给数组

    client = _make_client(handler)
    try:
        data = await client.get_realtime("000000")
    finally:
        await client.aclose()

    assert data == {}


@pytest.mark.asyncio
async def test_429_retries_with_backoff_then_succeeds(monkeypatch) -> None:
    """上游 429 → 指数退避重试 → 最终成功拿到 200。"""
    # 别让测试真的 sleep 1s/2s
    sleeps: list[float] = []

    async def _fake_sleep(s: float) -> None:
        sleeps.append(s)

    monkeypatch.setattr(mairui_mod.asyncio, "sleep", _fake_sleep)

    attempts = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        attempts["n"] += 1
        if attempts["n"] < 3:
            return httpx.Response(429, json={"error": "rate limit"})
        return httpx.Response(200, json={"pe": 7.28, "sjl": 0.7, "sz": 2.68e12})

    client = _make_client(handler)
    try:
        data = await client.get_realtime("601398")
    finally:
        await client.aclose()

    assert attempts["n"] == 3  # 两次 429 + 一次 200
    assert sleeps == [5, 20]  # 退避:5s、20s——必须足够跨 Mairui 的 60s 速率窗口
    assert data["pe"] == 7.28


@pytest.mark.asyncio
async def test_429_exhausted_raises(monkeypatch) -> None:
    """3 次重试仍 429 → raise_for_status 抛 HTTPStatusError。"""

    async def _fake_sleep(s: float) -> None:
        pass

    monkeypatch.setattr(mairui_mod.asyncio, "sleep", _fake_sleep)

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(429, json={"error": "rate limit"})

    client = _make_client(handler)
    try:
        with pytest.raises(httpx.HTTPStatusError):
            await client.get_realtime("601398")
    finally:
        await client.aclose()


@pytest.mark.asyncio
async def test_rate_limiter_blocks_bursts_above_threshold(monkeypatch) -> None:
    """AsyncLimiter 拒绝超过 rate_per_min 的突发——稳态下 token bucket 会节流。

    不真实等待秒级,靠 aiolimiter 内部记账来验证 has_capacity / acquire 的语义:
    bucket 满格时前 N 次立即通过,第 N+1 次会等待。
    """
    from aiolimiter import AsyncLimiter

    # 2 tokens per 60s,测试瞬时性
    limiter = AsyncLimiter(max_rate=2, time_period=60)

    # 前 2 个 acquire 立即成功
    assert limiter.has_capacity()
    await limiter.acquire()
    assert limiter.has_capacity()
    await limiter.acquire()
    # 第 3 个时 bucket 已空
    assert not limiter.has_capacity()
