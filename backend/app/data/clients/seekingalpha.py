from typing import Any

import httpx

from app.data.clients._http import make_client


class SeekingAlphaClient:
    """Seeking Alpha API via RapidAPI——美股 realtime quote + 代码补全。

    RapidAPI 走两个头：`x-rapidapi-host` + `x-rapidapi-key`。
    端点 URL 是完整 URL（不是相对路径），因为 RapidAPI 的 SA 路由不共享前缀。
    """

    def __init__(
        self,
        *,
        api_key: str,
        host: str,
        autocomplete_url: str,
        quote_url: str,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self._autocomplete_url = autocomplete_url
        self._quote_url = quote_url
        self._client = client or make_client(
            headers={"x-rapidapi-host": host, "x-rapidapi-key": api_key},
        )

    async def aclose(self) -> None:
        await self._client.aclose()

    async def autocomplete(self, query: str, size: int = 10) -> dict[str, Any]:
        resp = await self._client.get(
            self._autocomplete_url,
            params={"query": query, "type": "people,symbols", "size": size},
        )
        resp.raise_for_status()
        return resp.json()

    async def get_realtime_quotes(self, symbols: list[str]) -> dict[str, Any]:
        resp = await self._client.get(self._quote_url, params={"symbols": ",".join(symbols)})
        resp.raise_for_status()
        return resp.json()
