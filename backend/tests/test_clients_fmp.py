import httpx
import pytest

from app.data.clients.fmp import FmpClient


def _make_client(handler) -> FmpClient:
    """构造一个把所有 HTTP 请求路由到 handler 的 FmpClient。"""
    transport = httpx.MockTransport(handler)
    http = httpx.AsyncClient(base_url="https://fmp.test/api", transport=transport, timeout=5.0)
    return FmpClient(api_key="KEY", base_url="https://fmp.test/api", client=http)


@pytest.mark.asyncio
async def test_list_us_stocks_returns_json_and_sends_apikey() -> None:
    seen: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["path"] = request.url.path
        seen["apikey"] = request.url.params.get("apikey", "")
        return httpx.Response(200, json=[{"symbol": "AAPL", "exchangeShortName": "NASDAQ"}])

    client = _make_client(handler)
    try:
        data = await client.list_us_stocks()
    finally:
        await client.aclose()

    assert seen["path"] == "/api/v3/stock/list"
    assert seen["apikey"] == "KEY"
    assert data == [{"symbol": "AAPL", "exchangeShortName": "NASDAQ"}]


@pytest.mark.asyncio
async def test_get_historical_prices_passes_from_and_to() -> None:
    seen: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["path"] = request.url.path
        seen["from"] = request.url.params.get("from", "")
        seen["to"] = request.url.params.get("to", "")
        return httpx.Response(200, json={"symbol": "AAPL", "historical": [{"date": "2024-01-02"}]})

    client = _make_client(handler)
    try:
        data = await client.get_historical_prices("AAPL", "2024-01-01", "2024-01-31")
    finally:
        await client.aclose()

    assert seen["path"] == "/api/v3/historical-price-full/AAPL"
    assert seen["from"] == "2024-01-01"
    assert seen["to"] == "2024-01-31"
    assert data["historical"][0]["date"] == "2024-01-02"


@pytest.mark.asyncio
async def test_get_ratios_ttm_and_profile_hit_expected_paths() -> None:
    paths: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        paths.append(request.url.path)
        return httpx.Response(200, json=[{"peRatioTTM": 20.0}])

    client = _make_client(handler)
    try:
        await client.get_ratios_ttm("AAPL")
        await client.get_profile("AAPL")
    finally:
        await client.aclose()

    assert paths == ["/api/v3/ratios-ttm/AAPL", "/api/v3/profile/AAPL"]


@pytest.mark.asyncio
async def test_financial_statements_send_period_and_limit() -> None:
    captures: list[tuple[str, str, str]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        captures.append(
            (
                request.url.path,
                request.url.params.get("period", ""),
                request.url.params.get("limit", ""),
            )
        )
        return httpx.Response(200, json=[])

    client = _make_client(handler)
    try:
        await client.get_income_statements("AAPL", period="annual", limit=3)
        await client.get_balance_sheets("AAPL", period="quarter", limit=7)
        await client.get_cashflow_statements("AAPL")
    finally:
        await client.aclose()

    assert captures[0] == ("/api/v3/income-statement/AAPL", "annual", "3")
    assert captures[1] == ("/api/v3/balance-sheet-statement/AAPL", "quarter", "7")
    # 默认值
    assert captures[2] == ("/api/v3/cash-flow-statement/AAPL", "annual", "5")


@pytest.mark.asyncio
async def test_http_error_raises() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, json={"error": "not found"})

    client = _make_client(handler)
    try:
        with pytest.raises(httpx.HTTPStatusError):
            await client.get_profile("NOPE")
    finally:
        await client.aclose()
