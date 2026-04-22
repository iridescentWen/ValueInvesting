"""HkProvider 测试：注入一个假 yfinance 模块,不打网络。"""

from datetime import date
from decimal import Decimal
from typing import Any

import pandas as pd
import pytest

from app.data.providers.hk import HkProvider


class _FakeTicker:
    def __init__(
        self,
        info: dict[str, Any],
        *,
        income_stmt: pd.DataFrame | None = None,
        balance_sheet: pd.DataFrame | None = None,
        cashflow: pd.DataFrame | None = None,
        quarterly_income_stmt: pd.DataFrame | None = None,
        quarterly_balance_sheet: pd.DataFrame | None = None,
        quarterly_cashflow: pd.DataFrame | None = None,
    ) -> None:
        self.info = info
        self.income_stmt = income_stmt if income_stmt is not None else pd.DataFrame()
        self.balance_sheet = balance_sheet if balance_sheet is not None else pd.DataFrame()
        self.cashflow = cashflow if cashflow is not None else pd.DataFrame()
        self.quarterly_income_stmt = (
            quarterly_income_stmt if quarterly_income_stmt is not None else pd.DataFrame()
        )
        self.quarterly_balance_sheet = (
            quarterly_balance_sheet if quarterly_balance_sheet is not None else pd.DataFrame()
        )
        self.quarterly_cashflow = (
            quarterly_cashflow if quarterly_cashflow is not None else pd.DataFrame()
        )


class _FakeYfinance:
    """只实现 HkProvider 要用的 `Ticker(symbol).*`。"""

    def __init__(
        self,
        info_by_symbol: dict[str, dict[str, Any]] | None = None,
        *,
        tickers: dict[str, _FakeTicker] | None = None,
    ) -> None:
        self._by_symbol = info_by_symbol or {}
        self._tickers = tickers or {}

    def Ticker(self, symbol: str) -> _FakeTicker:  # noqa: N802 — match yfinance API
        if symbol in self._tickers:
            return self._tickers[symbol]
        return _FakeTicker(self._by_symbol.get(symbol, {}))


@pytest.mark.asyncio
async def test_list_stocks_returns_seed_universe() -> None:
    provider = HkProvider()
    stocks = await provider.list_stocks()
    # 至少 50 支,全部 hk market,symbol 是 XXXX.HK 格式
    assert len(stocks) >= 50
    assert all(s.market == "hk" for s in stocks)
    assert all(s.symbol.endswith(".HK") for s in stocks)
    assert all(s.exchange == "HKEX" for s in stocks)
    # 腾讯和 HSBC 必在列表中(经典 HSI 蓝筹)
    symbols = {s.symbol for s in stocks}
    assert "0700.HK" in symbols
    assert "0005.HK" in symbols


@pytest.mark.asyncio
async def test_get_fundamentals_maps_yfinance_fields() -> None:
    provider = HkProvider()
    provider._yf = _FakeYfinance(
        {
            "0700.HK": {
                "trailingPE": 22.5,
                "priceToBook": 4.1,
                "returnOnEquity": 0.18,
                "dividendYield": 0.004,
                "marketCap": 3.5e12,
            }
        }
    )
    f = await provider.get_fundamentals("0700.HK")
    assert f is not None
    assert f.symbol == "0700.HK"
    assert f.pe == Decimal("22.5")
    assert f.pb == Decimal("4.1")
    assert f.roe == Decimal("0.18")
    assert f.dividend_yield == Decimal("0.004")
    assert f.market_cap == Decimal(str(3.5e12))


@pytest.mark.asyncio
async def test_get_fundamentals_handles_nan_and_missing_fields() -> None:
    provider = HkProvider()
    provider._yf = _FakeYfinance(
        {
            # 有些港股 yfinance 返回的字段含 NaN 或 None
            "0001.HK": {
                "trailingPE": float("nan"),
                "priceToBook": None,
                "returnOnEquity": 0.12,
                "marketCap": 2.0e11,
            }
        }
    )
    f = await provider.get_fundamentals("0001.HK")
    assert f is not None
    assert f.pe is None
    assert f.pb is None
    assert f.roe == Decimal("0.12")
    assert f.dividend_yield is None
    assert f.market_cap == Decimal(str(2.0e11))


@pytest.mark.asyncio
async def test_get_fundamentals_returns_none_for_unknown_symbol() -> None:
    provider = HkProvider()
    provider._yf = _FakeYfinance({})  # 空字典——任何 symbol 查不到
    f = await provider.get_fundamentals("9999.HK")
    assert f is None  # info 空 dict → 返回 None


@pytest.mark.asyncio
async def test_get_fundamentals_normalizes_percent_dividend_yield() -> None:
    # yfinance 0.2.x 起把 dividendYield 返回成百分数(3.49 表示 3.49%)
    # HkProvider 应归一成小数 0.0349
    provider = HkProvider()
    provider._yf = _FakeYfinance(
        {
            "0005.HK": {
                "trailingPE": 8.2,
                "priceToBook": 0.9,
                "returnOnEquity": 0.11,  # ROE 依然是小数,不动
                "dividendYield": 3.49,  # 百分数 → 归一到 0.0349
                "marketCap": 1.2e12,
            }
        }
    )
    f = await provider.get_fundamentals("0005.HK")
    assert f is not None
    assert f.dividend_yield == Decimal("3.49") / Decimal(100)
    # ROE < 1 原样保留
    assert f.roe == Decimal("0.11")


def _yf_financials_df(
    rows: dict[str, list[Any]], periods: list[pd.Timestamp]
) -> pd.DataFrame:
    """yfinance 三表格式:index=标签, columns=Timestamp。"""
    return pd.DataFrame(rows, index=periods).T


@pytest.mark.asyncio
async def test_get_financial_snapshots_maps_yfinance_three_tables() -> None:
    """yfinance income_stmt / balance_sheet / cashflow 映射到 FinancialSnapshot。"""
    periods = [pd.Timestamp("2024-12-31"), pd.Timestamp("2023-12-31")]
    income = _yf_financials_df(
        {"Total Revenue": [1000, 900], "Net Income": [200, 180]}, periods
    )
    balance = _yf_financials_df(
        {"Total Assets": [5000, 4500], "Stockholders Equity": [2500, 2200]}, periods
    )
    cashflow = _yf_financials_df(
        {"Operating Cash Flow": [300, 280], "Capital Expenditure": [-80, -70]}, periods
    )
    ticker = _FakeTicker(
        info={}, income_stmt=income, balance_sheet=balance, cashflow=cashflow
    )

    provider = HkProvider()
    provider._yf = _FakeYfinance(tickers={"0001.HK": ticker})

    snaps = await provider.get_financial_snapshots("0001.HK", limit=2)
    assert [s.period for s in snaps] == [date(2024, 12, 31), date(2023, 12, 31)]
    s = snaps[0]
    assert s.revenue == Decimal("1000")
    assert s.net_income == Decimal("200")
    assert s.total_assets == Decimal("5000")
    assert s.total_equity == Decimal("2500")
    assert s.operating_cashflow == Decimal("300")
    # yfinance capex 本就是负数,直接透传
    assert s.capex == Decimal("-80")
    assert s.period_type == "annual"


@pytest.mark.asyncio
async def test_get_financial_snapshots_quarterly_uses_quarterly_tables() -> None:
    """period='quarterly' 应该打 `quarterly_*` 属性,不是 annual 表。"""
    periods = [pd.Timestamp("2024-12-31"), pd.Timestamp("2024-09-30")]
    q_income = _yf_financials_df({"Total Revenue": [300, 250]}, periods)
    ticker = _FakeTicker(info={}, quarterly_income_stmt=q_income)

    provider = HkProvider()
    provider._yf = _FakeYfinance(tickers={"0001.HK": ticker})

    snaps = await provider.get_financial_snapshots(
        "0001.HK", period_type="quarterly", limit=2
    )
    assert [s.period for s in snaps] == [date(2024, 12, 31), date(2024, 9, 30)]
    assert snaps[0].revenue == Decimal("300")


@pytest.mark.asyncio
async def test_get_financial_snapshots_uses_fallback_labels() -> None:
    """yfinance 行标签不统一——revenue / net_income 有备用 label。"""
    periods = [pd.Timestamp("2024-12-31")]
    # 用 'Operating Revenue' 代替 'Total Revenue',
    # 'Net Income From Continuing Operation Net Minority Interest' 代替 'Net Income'
    income = _yf_financials_df(
        {
            "Operating Revenue": [888],
            "Net Income From Continuing Operation Net Minority Interest": [111],
        },
        periods,
    )
    # 'Common Stock Equity' 代替 'Stockholders Equity'
    balance = _yf_financials_df({"Common Stock Equity": [500]}, periods)
    ticker = _FakeTicker(info={}, income_stmt=income, balance_sheet=balance)

    provider = HkProvider()
    provider._yf = _FakeYfinance(tickers={"0001.HK": ticker})

    snaps = await provider.get_financial_snapshots("0001.HK", limit=1)
    assert len(snaps) == 1
    assert snaps[0].revenue == Decimal("888")
    assert snaps[0].net_income == Decimal("111")
    assert snaps[0].total_equity == Decimal("500")


@pytest.mark.asyncio
async def test_get_financial_snapshots_returns_empty_when_all_frames_empty() -> None:
    """三表全空(rate limit / 未索引股票)返回空 list。"""
    ticker = _FakeTicker(info={})  # 三表全默认空 DataFrame
    provider = HkProvider()
    provider._yf = _FakeYfinance(tickers={"9999.HK": ticker})

    snaps = await provider.get_financial_snapshots("9999.HK")
    assert snaps == []
