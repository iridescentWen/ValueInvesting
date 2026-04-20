from typing import Any

import httpx

from app.data.clients._http import make_client


class MairuiClient:
    """麦蕊 (Mairui) A 股财报 API。

    URL 格式：`{base_url}/hscp/{endpoint}/{code}/{license_key}`——license_key
    走路径，不是 query 参数。基础 license（本项目用的）只开放 `cwzb`（财务指标）
    和 `gsjj`（公司简介），三张报表独立端点需要升级套餐，实际请求会 404。

    `cwzb` 返回一个混合数组：按期（season / year）排序，每条里同时有
      - 营业收入 `zyyw`、扣非净利润 `kflr`、总资产 `zzc`
      - 大量比率 / 同比 / 每股指标（见上游文档）
    provider 层从这里面挑需要的字段组 `FinancialSnapshot`。
    """

    _METRICS = "cwzb"

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

    async def _get(self, endpoint: str, symbol: str) -> list[dict[str, Any]]:
        resp = await self._client.get(f"/hscp/{endpoint}/{symbol}/{self._api_key}")
        resp.raise_for_status()
        data = resp.json()
        return data if isinstance(data, list) else []

    async def get_financial_metrics(self, symbol: str) -> list[dict[str, Any]]:
        """返回按报告期倒序的财务指标列表。"""
        return await self._get(self._METRICS, symbol)
