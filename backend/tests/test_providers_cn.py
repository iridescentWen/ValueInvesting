"""CnProvider 的组合逻辑测试——注入 stub client，不打网络、不碰 akshare。"""

from datetime import date
from decimal import Decimal
from typing import Any

import pandas as pd
import pytest

from app.data.providers.cn import CnProvider


class _StubAkshare:
    """只实现 CnProvider 要用的方法。"""

    def __init__(
        self,
        *,
        list_df: pd.DataFrame | None = None,
        daily_df: pd.DataFrame | None = None,
        indicator_df: pd.DataFrame | None = None,
        spot_df: pd.DataFrame | None = None,
        indicator_lg_df: pd.DataFrame | None = None,
        financial_abstract_df: pd.DataFrame | None = None,
        sina_reports: dict[str, pd.DataFrame] | None = None,
    ) -> None:
        self._list = list_df
        self._daily = daily_df
        self._indicator = indicator_df
        self._spot = spot_df
        self._indicator_lg = indicator_lg_df
        self._financial_abstract = financial_abstract_df
        self._sina_reports = sina_reports or {}

    async def list_a_stocks(self) -> pd.DataFrame:
        return self._list if self._list is not None else pd.DataFrame()

    async def get_daily_bars(self, **_: Any) -> pd.DataFrame:
        return self._daily if self._daily is not None else pd.DataFrame()

    async def get_indicator(self, symbol: str) -> pd.DataFrame:
        return self._indicator if self._indicator is not None else pd.DataFrame()

    async def get_spot(self) -> pd.DataFrame:
        return self._spot if self._spot is not None else pd.DataFrame()

    async def get_indicator_lg(self, symbol: str) -> pd.DataFrame:
        return self._indicator_lg if self._indicator_lg is not None else pd.DataFrame()

    async def get_financial_abstract(self, symbol: str) -> pd.DataFrame:
        return self._financial_abstract if self._financial_abstract is not None else pd.DataFrame()

    async def get_financial_report_sina(self, stock: str, kind: str) -> pd.DataFrame:
        return self._sina_reports.get(kind, pd.DataFrame())


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
    # enrich 的两个子源均空,ROE / 股息率仍为 None
    assert f.roe is None
    assert f.dividend_yield is None
    assert f.as_of == date(2024, 12, 31)


@pytest.mark.asyncio
async def test_enrich_fundamentals_fills_roe_and_dv() -> None:
    ak = _StubAkshare(
        indicator_lg_df=pd.DataFrame(
            [
                {"trade_date": "2024-12-30", "dv_ratio": 2.5, "pe": 20, "pb": 3},
                {"trade_date": "2024-12-31", "dv_ratio": 3.0, "pe": 21, "pb": 3.1},
            ]
        ),
        financial_abstract_df=pd.DataFrame(
            [
                {
                    "选项": "盈利能力",
                    "指标": "净资产收益率",
                    "2024-12-31": 15.2,
                    "2023-12-31": 14.0,
                },
                {"选项": "盈利能力", "指标": "毛利率", "2024-12-31": 45.0, "2023-12-31": 44.0},
            ]
        ),
    )
    provider = CnProvider(akshare_client=ak, mairui_client=_StubMairui())

    from app.data.providers.base import Fundamentals

    base = Fundamentals(
        symbol="600519",
        as_of=date(2024, 12, 31),
        pe=Decimal("30"),
        pb=Decimal("10"),
        market_cap=Decimal("1000000000000"),
    )
    enriched = await provider.enrich_fundamentals(base)
    # 两个百分数字段都归一到小数
    assert enriched.roe == Decimal("15.2") / Decimal(100)
    assert enriched.dividend_yield == Decimal("3.0") / Decimal(100)
    # 基础字段原样保留
    assert enriched.pe == Decimal("30")
    assert enriched.symbol == "600519"


@pytest.mark.asyncio
async def test_enrich_fundamentals_handles_missing_sources() -> None:
    # 两个源都空——enrich 不抛异常,ROE / 股息率保持 None
    ak = _StubAkshare()
    provider = CnProvider(akshare_client=ak, mairui_client=_StubMairui())

    from app.data.providers.base import Fundamentals

    base = Fundamentals(
        symbol="600519",
        as_of=date(2024, 12, 31),
        pe=Decimal("30"),
        pb=Decimal("10"),
        market_cap=Decimal("1000000000000"),
    )
    enriched = await provider.enrich_fundamentals(base)
    assert enriched.roe is None
    assert enriched.dividend_yield is None


@pytest.mark.asyncio
async def test_enrich_fundamentals_skips_malformed_financial_abstract() -> None:
    # 没有"指标"列——enrich 退化到 None,不抛
    ak = _StubAkshare(
        financial_abstract_df=pd.DataFrame(
            [{"wrong_column": "净资产收益率", "2024-12-31": 15.2}]
        )
    )
    provider = CnProvider(akshare_client=ak, mairui_client=_StubMairui())

    from app.data.providers.base import Fundamentals

    base = Fundamentals(
        symbol="600519",
        as_of=date(2024, 12, 31),
        pe=Decimal("30"),
        pb=Decimal("10"),
        market_cap=Decimal("1000000000000"),
    )
    enriched = await provider.enrich_fundamentals(base)
    assert enriched.roe is None


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
async def test_get_financial_snapshots_maps_sina_three_statements() -> None:
    """AkShare Sina 三表的字段映射 + annual 过滤 + capex 符号翻转。"""
    income = pd.DataFrame(
        [
            {"报告日": "20241231", "营业总收入": 1000, "归属于母公司所有者的净利润": 200},
            {"报告日": "20240930", "营业总收入": 700, "归属于母公司所有者的净利润": 150},
            {"报告日": "20231231", "营业总收入": 900, "归属于母公司所有者的净利润": 180},
        ]
    )
    balance = pd.DataFrame(
        [
            {"报告日": "20241231", "资产总计": 5000, "归属于母公司股东权益合计": 2500},
            {"报告日": "20240930", "资产总计": 4700, "归属于母公司股东权益合计": 2300},
            {"报告日": "20231231", "资产总计": 4500, "归属于母公司股东权益合计": 2200},
        ]
    )
    cashflow = pd.DataFrame(
        [
            {
                "报告日": "20241231",
                "经营活动产生的现金流量净额": 300,
                "购建固定资产、无形资产和其他长期资产所支付的现金": 80,
            },
            {
                "报告日": "20231231",
                "经营活动产生的现金流量净额": 280,
                "购建固定资产、无形资产和其他长期资产所支付的现金": 70,
            },
        ]
    )
    ak = _StubAkshare(
        sina_reports={"利润表": income, "资产负债表": balance, "现金流量表": cashflow}
    )
    provider = CnProvider(akshare_client=ak, mairui_client=_StubMairui())

    snaps = await provider.get_financial_snapshots("600519", limit=3)

    # annual 过滤后只剩 2024-12-31 / 2023-12-31
    assert [s.period for s in snaps] == [date(2024, 12, 31), date(2023, 12, 31)]
    s = snaps[0]
    assert s.revenue == Decimal("1000")
    assert s.net_income == Decimal("200")
    assert s.total_assets == Decimal("5000")
    assert s.total_equity == Decimal("2500")
    assert s.operating_cashflow == Decimal("300")
    # capex 符号翻转:Sina 返回 80(正),归一到 -80 跟 FMP / yfinance 一致
    assert s.capex == Decimal("-80")
    assert s.period_type == "annual"


@pytest.mark.asyncio
async def test_get_financial_snapshots_quarterly_keeps_all_periods() -> None:
    """period='quarterly' 不过滤 1231,所有报告期都返回。"""
    income = pd.DataFrame(
        [
            {"报告日": "20241231", "营业总收入": 1000, "归属于母公司所有者的净利润": 200},
            {"报告日": "20240930", "营业总收入": 700, "归属于母公司所有者的净利润": 150},
        ]
    )
    ak = _StubAkshare(sina_reports={"利润表": income})
    provider = CnProvider(akshare_client=ak, mairui_client=_StubMairui())

    snaps = await provider.get_financial_snapshots("600519", period_type="quarterly", limit=5)
    assert [s.period for s in snaps] == [date(2024, 12, 31), date(2024, 9, 30)]


@pytest.mark.asyncio
async def test_get_financial_snapshots_returns_empty_when_akshare_raises() -> None:
    """AkShare 抛异常(限流 / 停服)不炸,返回空 list。"""

    class _BoomAkshare(_StubAkshare):
        async def get_financial_report_sina(self, stock: str, kind: str) -> pd.DataFrame:
            raise RuntimeError("akshare rate limit")

    provider = CnProvider(akshare_client=_BoomAkshare(), mairui_client=_StubMairui())
    assert await provider.get_financial_snapshots("600519") == []


@pytest.mark.asyncio
async def test_get_financial_snapshots_returns_empty_for_unknown_exchange() -> None:
    """代码前缀推断不出交易所(非 6/9/0/3 开头)直接返回空。"""
    provider = CnProvider(akshare_client=_StubAkshare(), mairui_client=_StubMairui())
    assert await provider.get_financial_snapshots("999999") == []


@pytest.mark.asyncio
async def test_get_financial_snapshots_falls_back_to_alt_labels() -> None:
    """revenue / net_income / equity 都有备用 label,一个 label 缺了另一个兜底。"""
    income = pd.DataFrame(
        [
            # 只有「营业收入」没有「营业总收入」;只有「净利润」没有「归属于母公司...」
            {"报告日": "20241231", "营业收入": 888, "净利润": 111},
        ]
    )
    balance = pd.DataFrame(
        [
            # 只有「所有者权益(或股东权益)合计」没有「归属于母公司股东权益合计」
            {"报告日": "20241231", "资产总计": 4000, "所有者权益(或股东权益)合计": 2000},
        ]
    )
    ak = _StubAkshare(sina_reports={"利润表": income, "资产负债表": balance})
    provider = CnProvider(akshare_client=ak, mairui_client=_StubMairui())

    snaps = await provider.get_financial_snapshots("600519", limit=1)
    assert len(snaps) == 1
    assert snaps[0].revenue == Decimal("888")
    assert snaps[0].net_income == Decimal("111")
    assert snaps[0].total_equity == Decimal("2000")
