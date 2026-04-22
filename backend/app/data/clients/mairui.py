import asyncio
import logging
from typing import Any

import httpx
from aiolimiter import AsyncLimiter

from app.data.clients._http import make_client

log = logging.getLogger(__name__)

_DEFAULT_RATE_PER_MIN = 240
_MAX_RETRIES = 3
# 429 退避秒数。Mairui 限速以 per-minute 滑动窗口算,所以最后一轮必须能跨
# 一整个 60s 窗口才能真正恢复。总等待 ≈ 5+20+60 = 85s。
_RETRY_BACKOFF_SECONDS = (5, 20, 60)


class MairuiClient:
    """麦蕊 (Mairui) A 股财报 API。

    URL 格式：`{base_url}/hscp/{endpoint}/{code}/{license_key}`——license_key
    走路径，不是 query 参数。基础 license（本项目用的）只开放 `cwzb`（财务指标）
    和 `gsjj`（公司简介），三张报表独立端点需要升级套餐，实际请求会 404。

    `cwzb` 返回一个混合数组：按期（season / year）排序，每条里同时有
      - 营业收入 `zyyw`、扣非净利润 `kflr`、总资产 `zzc`
      - 大量比率 / 同比 / 每股指标（见上游文档）
    provider 层从这里面挑需要的字段组 `FinancialSnapshot`。

    **限速**：Mairui 按套餐分级 rate limit（免费 50/天、月/年/黄金 300/min、
    铂金 3000/min、钻石 6000/min）。client 持一个共享 `AsyncLimiter` token
    bucket，`rate_per_min` 由调用方按套餐的 80% 安全阈配置。所有 HTTP 方法
    都经限速器。即便如此上游偶有抖动，`_request_with_retry` 对 429 做指数退避
    重试(1s/2s/4s)。
    """

    _METRICS = "cwzb"

    def __init__(
        self,
        *,
        api_key: str,
        base_url: str,
        rate_per_min: int = _DEFAULT_RATE_PER_MIN,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self._api_key = api_key
        self._client = client or make_client(base_url=base_url)
        # aiolimiter 漏桶:稳态 rate = capacity/time_period 每秒,peak(60s window)
        # = capacity + 60*leak_rate。Mairui 是硬 per-minute 限速,想要稳态
        # rate_per_min/min 且 peak ≤ rate_per_min,用"小桶 + 匹配漏速":
        #   AsyncLimiter(rate_per_min/60, 1) → 稳态 rate_per_min/60 每秒,
        #   peak over 60s = rate_per_min/60 + 60*(rate_per_min/60) ≈ rate_per_min。
        # 对 rate_per_min=240: AsyncLimiter(4, 1) → 稳态 4/s、60s 峰值 244。✓
        _per_sec = max(rate_per_min // 60, 1)
        self._limiter = AsyncLimiter(max_rate=_per_sec, time_period=1)

    async def aclose(self) -> None:
        await self._client.aclose()

    async def _rate_limited_get(self, url: str) -> httpx.Response:
        """单次 HTTP 请求,前置通过限速器——重要:每次调用(含重试)都要走这里,
        让限速器对重试也生效,避免重试变相放大请求速率打爆上游。"""
        async with self._limiter:
            return await self._client.get(url)

    async def _request_with_retry(self, url: str) -> httpx.Response:
        """带 429 指数退避的 GET。每次 attempt 都走 `_rate_limited_get`。

        只对 429 重试——其他 4xx/5xx 直接返回让调用方 raise_for_status。
        网络异常 (ConnectError / ReadTimeout 等 httpx.HTTPError 子类) 也重试。
        """
        last_exc: Exception | None = None
        resp: httpx.Response | None = None
        for attempt in range(_MAX_RETRIES):
            try:
                resp = await self._rate_limited_get(url)
                last_exc = None
                if resp.status_code != 429:
                    return resp
            except httpx.HTTPError as e:
                last_exc = e
                resp = None
            if attempt < _MAX_RETRIES - 1:
                backoff = _RETRY_BACKOFF_SECONDS[attempt]
                log.warning(
                    "mairui retry %d/%d after %s (url=%s) in %ds",
                    attempt + 1, _MAX_RETRIES,
                    "429" if last_exc is None else type(last_exc).__name__,
                    url, backoff,
                )
                await asyncio.sleep(backoff)
        # 重试用完:如果有异常抛异常,否则返最后一次响应(必是 429,
        # 调用方的 raise_for_status 会抛 HTTPStatusError)
        if last_exc is not None:
            raise last_exc
        assert resp is not None
        return resp

    async def _get(self, endpoint: str, symbol: str) -> list[dict[str, Any]]:
        resp = await self._request_with_retry(
            f"/hscp/{endpoint}/{symbol}/{self._api_key}"
        )
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
        """
        resp = await self._request_with_retry(
            f"/hsrl/ssjy/{symbol}/{self._api_key}"
        )
        resp.raise_for_status()
        data = resp.json()
        return data if isinstance(data, dict) else {}

    async def list_all_stocks(self) -> list[dict[str, Any]]:
        """`/hslt/list/{key}`:全 A 股基础名单(~5200 支,一次请求 0.3s)。

        每条字段:
        - `dm` 代码(含后缀,如 `000001.SZ`)
        - `mc` 中文名
        - `jys` 交易所(`SZ`/`SH`/`BJ`)
        """
        resp = await self._request_with_retry(
            f"/hslt/list/{self._api_key}"
        )
        resp.raise_for_status()
        data = resp.json()
        return data if isinstance(data, list) else []
