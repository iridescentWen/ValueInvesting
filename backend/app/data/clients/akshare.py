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
        """全市场实时快照——一次拉全，内存按 symbol 过滤。"""
        return await self._call(ak.stock_zh_a_spot_em)
