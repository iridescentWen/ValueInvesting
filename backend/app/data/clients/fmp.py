from typing import Any

import httpx

from app.data.clients._http import make_client


class FmpClient:
    """Financial Modeling Prep HTTP 客户端。

    所有端点都要 `apikey={key}` 查询参数。v3 / v4 路径在调用处拼。
    """

    def __init__(
        self,
        *,
        api_key: str,
        base_url: str,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self._api_key = api_key
        self._client = client or make_client(base_url=base_url)

    async def aclose(self) -> None:
        await self._client.aclose()

    async def _get(self, path: str, **params: Any) -> Any:
        resp = await self._client.get(path, params={"apikey": self._api_key, **params})
        resp.raise_for_status()
        return resp.json()

    async def list_us_stocks(self) -> list[dict[str, Any]]:
        return await self._get("/v3/stock/list")

    async def get_historical_prices(self, symbol: str, start: str, end: str) -> dict[str, Any]:
        """返回 `{"symbol": "AAPL", "historical": [{"date": ..., ...}]}`。"""
        # `from` 是 Python 关键字，只能用 **kwargs 方式
        return await self._get(f"/v3/historical-price-full/{symbol}", **{"from": start, "to": end})

    async def get_ratios_ttm(self, symbol: str) -> list[dict[str, Any]]:
        return await self._get(f"/v3/ratios-ttm/{symbol}")

    async def get_profile(self, symbol: str) -> list[dict[str, Any]]:
        return await self._get(f"/v3/profile/{symbol}")

    async def get_income_statements(
        self, symbol: str, period: str = "annual", limit: int = 5
    ) -> list[dict[str, Any]]:
        return await self._get(f"/v3/income-statement/{symbol}", period=period, limit=limit)

    async def get_balance_sheets(
        self, symbol: str, period: str = "annual", limit: int = 5
    ) -> list[dict[str, Any]]:
        return await self._get(f"/v3/balance-sheet-statement/{symbol}", period=period, limit=limit)

    async def get_cashflow_statements(
        self, symbol: str, period: str = "annual", limit: int = 5
    ) -> list[dict[str, Any]]:
        return await self._get(f"/v3/cash-flow-statement/{symbol}", period=period, limit=limit)
