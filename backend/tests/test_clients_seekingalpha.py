import httpx
import pytest

from app.data.clients.seekingalpha import SeekingAlphaClient

_AUTOCOMPLETE = "https://sa.test/v2/auto-complete"
_QUOTE = "https://sa.test/market/get-realtime-quotes"


def _make_client(handler) -> SeekingAlphaClient:
    transport = httpx.MockTransport(handler)
    http = httpx.AsyncClient(
        transport=transport,
        timeout=5.0,
        headers={"x-rapidapi-host": "sa.test", "x-rapidapi-key": "SA_KEY"},
    )
    return SeekingAlphaClient(
        api_key="SA_KEY",
        host="sa.test",
        autocomplete_url=_AUTOCOMPLETE,
        quote_url=_QUOTE,
        client=http,
    )


@pytest.mark.asyncio
async def test_autocomplete_sends_query_and_headers() -> None:
    seen: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url.copy_with(query=None))
        seen["query"] = request.url.params.get("query", "")
        seen["type"] = request.url.params.get("type", "")
        seen["size"] = request.url.params.get("size", "")
        seen["host"] = request.headers.get("x-rapidapi-host", "")
        seen["key"] = request.headers.get("x-rapidapi-key", "")
        return httpx.Response(200, json={"symbols": []})

    client = _make_client(handler)
    try:
        data = await client.autocomplete("AAPL", size=5)
    finally:
        await client.aclose()

    assert seen["url"] == _AUTOCOMPLETE
    assert seen["query"] == "AAPL"
    assert seen["type"] == "people,symbols"
    assert seen["size"] == "5"
    assert seen["host"] == "sa.test"
    assert seen["key"] == "SA_KEY"
    assert data == {"symbols": []}


@pytest.mark.asyncio
async def test_realtime_quotes_joins_symbols_with_comma() -> None:
    seen: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url.copy_with(query=None))
        seen["symbols"] = request.url.params.get("symbols", "")
        return httpx.Response(
            200,
            json={
                "data": {
                    "quotes": {
                        "AAPL": {"attributes": {"last": 200.0}},
                        "MSFT": {"attributes": {"last": 420.0}},
                    }
                }
            },
        )

    client = _make_client(handler)
    try:
        data = await client.get_realtime_quotes(["AAPL", "MSFT"])
    finally:
        await client.aclose()

    assert seen["url"] == _QUOTE
    assert seen["symbols"] == "AAPL,MSFT"
    assert data["data"]["quotes"]["AAPL"]["attributes"]["last"] == 200.0


@pytest.mark.asyncio
async def test_http_error_raises() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(429, json={"message": "rate limited"})

    client = _make_client(handler)
    try:
        with pytest.raises(httpx.HTTPStatusError):
            await client.get_realtime_quotes(["AAPL"])
    finally:
        await client.aclose()
