import asyncio
from typing import Any

import akshare as ak
import pandas as pd


class AkshareClient:
    """同步的 akshare 库用 `asyncio.to_thread` 包成 async，和其他 HTTP 客户端同构。

    `concurrency` 限并发调用数（AkShare 底层大多直接打爬虫接口，堆太多
    并发容易被限流）。
    """

    def __init__(self, concurrency: int = 10) -> None:
        self._sem = asyncio.Semaphore(concurrency)

    async def _call(self, fn: Any, /, *args: Any, **kwargs: Any) -> pd.DataFrame:
        async with self._sem:
            return await asyncio.to_thread(fn, *args, **kwargs)

    async def list_a_stocks(self) -> pd.DataFrame:
        """全 A 股基础列表，列：code / name。"""
        return await self._call(ak.stock_info_a_code_name)

    async def get_daily_bars(
        self, symbol: str, start: str, end: str, adjust: str = "qfq"
    ) -> pd.DataFrame:
        """前复权日线。`start`/`end` 格式 YYYYMMDD。"""
        return await self._call(
            ak.stock_zh_a_hist,
            symbol=symbol,
            period="daily",
            start_date=start,
            end_date=end,
            adjust=adjust,
        )

    async def get_indicator(self, symbol: str) -> pd.DataFrame:
        """估值分析：PE(TTM) / PB / 总市值 等。取最新一行就是当前快照。

        东财数据源没有股息率，provider 把 dividend_yield 留空。
        """
        return await self._call(ak.stock_value_em, symbol=symbol)

    async def get_spot(self) -> pd.DataFrame:
        """全市场实时快照——一次拉全，内存按 symbol 过滤。

        同时是 screener 的粗筛来源——字段包括 代码 / 名称 / 最新价 /
        市盈率-动态 / 市净率 / 总市值，一次 HTTP 覆盖全 A 股。
        """
        return await self._call(ak.stock_zh_a_spot_em)

    async def get_indicator_lg(self, symbol: str) -> pd.DataFrame:
        """乐咕乐股每日估值：pe / pe_ttm / pb / dv_ratio / dv_ttm / total_mv。

        用来给 screener 候选补股息率。取最新一行作为当前值。
        """
        return await self._call(ak.stock_a_indicator_lg, symbol=symbol)

    async def get_financial_abstract(self, symbol: str) -> pd.DataFrame:
        """同花顺财务摘要——供 screener 候选补 ROE（"净资产收益率"行）。

        比 stock_financial_analysis_indicator 快且稳定。返回的是
        "指标名 x 期次" 的长表，行里含"净资产收益率"。
        """
        return await self._call(ak.stock_financial_abstract, symbol=symbol)

    async def list_hk_stocks(self) -> pd.DataFrame:
        """港股全量名单——走 Sina `stock_hk_spot`（~2700 支,~8s）。

        列：`日期时间` / `代码`（如 `00001`,5 位补零）/ `中文名称` /
        `英文名称` / `交易类型` / `最新价`。

        East Money 的 `stock_hk_spot_em` 境外 geo-block；Sina 这个端点稳定。
        """
        return await self._call(ak.stock_hk_spot)

    async def get_financial_report_sina(self, stock: str, kind: str) -> pd.DataFrame:
        """A 股财报三表——Sina 端点境外能通。

        `stock` 是 sina 格式(`sh600519` / `sz000001`),`kind` 是
        `利润表` / `资产负债表` / `现金流量表`。

        返回宽表(每行一期),首列 `报告日` 是 `YYYYMMDD` 字符串,其余列是
        具体科目(利润表 ~83 列、资产负债表 ~147 列、现金流量表 ~71 列)。
        包含 20+ 年季度数据,年度靠 `报告日` 末尾 `1231` 过滤。
        """
        return await self._call(ak.stock_financial_report_sina, stock=stock, symbol=kind)
