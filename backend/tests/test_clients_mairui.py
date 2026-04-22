import httpx
import pytest

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
