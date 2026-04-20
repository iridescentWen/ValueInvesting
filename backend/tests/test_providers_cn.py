"""CnProvider 的组合逻辑测试——注入 stub client，不打网络、不碰 akshare。"""

from datetime import date
from decimal import Decimal
from typing import Any

import pandas as pd
import pytest

from app.data.providers.cn import CnProvider


class _StubAkshare:
    """只实现 CnProvider 要用的 4 个方法。"""

    def __init__(
        self,
        *,
        list_df: pd.DataFrame | None = None,
        daily_df: pd.DataFrame | None = None,
        indicator_df: pd.DataFrame | None = None,
        spot_df: pd.DataFrame | None = None,
    ) -> None:
        self._list = list_df
        self._daily = daily_df
        self._indicator = indicator_df
        self._spot = spot_df

    async def list_a_stocks(self) -> pd.DataFrame:
        return self._list if self._list is not None else pd.DataFrame()

    async def get_daily_bars(self, **_: Any) -> pd.DataFrame:
        return self._daily if self._daily is not None else pd.DataFrame()

    async def get_indicator(self, symbol: str) -> pd.DataFrame:
        return self._indicator if self._indicator is not None else pd.DataFrame()

    async def get_spot(self) -> pd.DataFrame:
        return self._spot if self._spot is not None else pd.DataFrame()


class _StubMairui:
    def __init__(self, *, metrics: list[dict[str, Any]] | None = None) -> None:
        self._metrics = metrics or []

    async def get_financial_metrics(self, symbol: str) -> list[dict[str, Any]]:
        return self._metrics

    async def aclose(self) -> None:
        pass


@pytest.mark.asyncio
async def test_list_stocks_infers_exchange_from_code() -> None:
    ak = _StubAkshare(
        list_df=pd.DataFrame(
            {
                "code": ["600519", "000001", "300750", "900001"],
                "name": ["贵州茅台", "平安银行", "宁德时代", "外高桥B"],
            }
        )
    )
    provider = CnProvider(akshare_client=ak, mairui_client=_StubMairui())
    stocks = await provider.list_stocks()

    by_symbol = {s.symbol: s for s in stocks}
    assert by_symbol["600519"].exchange == "SH"
    assert by_symbol["000001"].exchange == "SZ"
    assert by_symbol["300750"].exchange == "SZ"
    assert by_symbol["900001"].exchange == "SH"
    assert all(s.market == "cn" for s in stocks)


@pytest.mark.asyncio
async def test_get_daily_bars_maps_chinese_columns() -> None:
    ak = _StubAkshare(
        daily_df=pd.DataFrame(
            [
                {
                    "日期": "2024-01-02",
                    "开盘": 10.0,
                    "最高": 11.0,
                    "最低": 9.5,
                    "收盘": 10.5,
                    "成交量": 100000,
                },
                {
                    "日期": "2024-01-03",
                    "开盘": 10.5,
                    "最高": 12.0,
                    "最低": 10.0,
                    "收盘": 11.5,
                    "成交量": 150000,
                },
            ]
        )
    )
    provider = CnProvider(akshare_client=ak, mairui_client=_StubMairui())
    bars = await provider.get_daily_bars("600519", date(2024, 1, 1), date(2024, 1, 31))

    assert len(bars) == 2
    assert bars[0].date == date(2024, 1, 2)
    assert bars[0].open == Decimal("10.0")
    assert bars[0].close == Decimal("10.5")
    assert bars[0].volume == 100000
    assert bars[1].high == Decimal("12.0")


@pytest.mark.asyncio
async def test_get_daily_bars_skips_rows_with_missing_fields() -> None:
    ak = _StubAkshare(
        daily_df=pd.DataFrame(
            [
                {
                    "日期": "2024-01-02",
                    "开盘": 10.0,
                    "最高": 11.0,
                    "最低": 9.5,
                    "收盘": 10.5,
                    "成交量": 100000,
                },
                {
                    "日期": "2024-01-03",
                    "开盘": None,
                    "最高": 12.0,
                    "最低": 10.0,
                    "收盘": 11.5,
                    "成交量": 150000,
                },
            ]
        )
    )
    provider = CnProvider(akshare_client=ak, mairui_client=_StubMairui())
    bars = await provider.get_daily_bars("600519", date(2024, 1, 1), date(2024, 1, 31))

    assert len(bars) == 1
    assert bars[0].date == date(2024, 1, 2)


@pytest.mark.asyncio
async def test_get_fundamentals_takes_last_row() -> None:
    ak = _StubAkshare(
        indicator_df=pd.DataFrame(
            [
                {"数据日期": "2024-12-30", "PE(TTM)": 30.0, "市净率": 10.0, "总市值": 1e12},
                {"数据日期": "2024-12-31", "PE(TTM)": 31.5, "市净率": 10.5, "总市值": 1.05e12},
            ]
        )
    )
    provider = CnProvider(akshare_client=ak, mairui_client=_StubMairui())
    f = await provider.get_fundamentals("600519")

    assert f is not None
    assert f.pe == Decimal("31.5")
    assert f.pb == Decimal("10.5")
    assert f.market_cap == Decimal(str(1.05e12))
    # 目前数据源没给 ROE / 股息率
    assert f.roe is None
    assert f.dividend_yield is None
    assert f.as_of == date(2024, 12, 31)


@pytest.mark.asyncio
async def test_get_fundamentals_returns_none_when_empty() -> None:
    ak = _StubAkshare(indicator_df=pd.DataFrame())
    provider = CnProvider(akshare_client=ak, mairui_client=_StubMairui())
    assert await provider.get_fundamentals("600519") is None


@pytest.mark.asyncio
async def test_get_realtime_quote_filters_by_symbol() -> None:
    ak = _StubAkshare(
        spot_df=pd.DataFrame(
            [
                {"代码": "600519", "最新价": 1600.0, "涨跌幅": 1.5, "成交量": 1000},
                {"代码": "000001", "最新价": 12.0, "涨跌幅": -0.5, "成交量": 5000},
            ]
        )
    )
    provider = CnProvider(akshare_client=ak, mairui_client=_StubMairui())

    q = await provider.get_realtime_quote("600519")
    assert q is not None
    assert q.price == Decimal("1600.0")
    assert q.change_pct == Decimal("1.5")

    assert await provider.get_realtime_quote("NOPE") is None


@pytest.mark.asyncio
async def test_get_financial_snapshots_maps_cwzb_and_filters_annual() -> None:
    mr = _StubMairui(
        metrics=[
            {"date": "2024-12-31", "zyyw": 1000, "kflr": 200, "zzc": 5000},
            {"date": "2024-09-30", "zyyw": 700, "kflr": 150, "zzc": 4700},
            {"date": "2023-12-31", "zyyw": 900, "kflr": 180, "zzc": 4500},
        ]
    )
    provider = CnProvider(akshare_client=_StubAkshare(), mairui_client=mr)

    snaps = await provider.get_financial_snapshots("600519", limit=3)

    # annual 过滤后只剩 2024-12-31 / 2023-12-31
    assert [s.period for s in snaps] == [date(2024, 12, 31), date(2023, 12, 31)]
    assert snaps[0].revenue == Decimal("1000")
    assert snaps[0].net_income == Decimal("200")
    assert snaps[0].total_assets == Decimal("5000")
    # cwzb 没给 equity / cashflow / capex
    assert snaps[0].total_equity is None
    assert snaps[0].operating_cashflow is None
    assert snaps[0].capex is None
    assert snaps[0].period_type == "annual"


@pytest.mark.asyncio
async def test_get_financial_snapshots_returns_empty_without_mairui(monkeypatch) -> None:
    # 显式清掉 settings 里的 key，确保 CnProvider 不会从 settings 构造真实 client
    from app.data.providers import cn as cn_mod

    monkeypatch.setattr(cn_mod.settings, "mairui_api_key", None)
    provider = CnProvider(akshare_client=_StubAkshare(), mairui_client=None)
    assert await provider.get_financial_snapshots("600519") == []
