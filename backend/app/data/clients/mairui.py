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

    async def get_realtime(self, symbol: str) -> dict[str, Any]:
        """实时交易快照:`/hsrl/ssjy/{code}/{key}`。

        返回原始 dict,关键字段:
        - `p` 最新价, `pc` 涨跌额, `ud` 涨跌幅
        - `pe` 市盈率, `sjl` 市净率, `sz` 总市值, `lt` 流通市值
        - `v` 成交量, `cje` 成交额, `t` 时间戳

        用于 screener 粗筛:PE / 市净率 / 总市值 直接从这里拿,跳过 AkShare
        被 geo-block 的 `stock_zh_a_spot_em` 全市场端点。
        """
        resp = await self._client.get(f"/hsrl/ssjy/{symbol}/{self._api_key}")
        resp.raise_for_status()
        data = resp.json()
        return data if isinstance(data, dict) else {}

    async def list_all_stocks(self) -> list[dict[str, Any]]:
        """`/hslt/list/{key}`:全 A 股基础名单(~5200 支,一次请求 0.3s)。

        每条字段:
        - `dm` 代码(含后缀,如 `000001.SZ`)
        - `mc` 中文名
        - `jys` 交易所(`SZ`/`SH`/`BJ`)

        是 screener 的种子名单来源——比硬编码 CSI300 的 ~200 支覆盖面大 25 倍。
        这个端点不走 East Money,境外能通(探测通过)。
        """
        resp = await self._client.get(f"/hslt/list/{self._api_key}")
        resp.raise_for_status()
        data = resp.json()
        return data if isinstance(data, list) else []
