"""UsProvider 的组合逻辑测试——注入 stub client。"""

from datetime import date
from decimal import Decimal
from typing import Any

import pytest

from app.data.providers.us import UsProvider


class _StubFmp:
    def __init__(
        self,
        *,
        list_items: list[dict[str, Any]] | None = None,
        historical: dict[str, Any] | None = None,
        ratios: list[dict[str, Any]] | None = None,
        profile: list[dict[str, Any]] | None = None,
        income: list[dict[str, Any]] | None = None,
        balance: list[dict[str, Any]] | None = None,
        cashflow: list[dict[str, Any]] | None = None,
    ) -> None:
        self._list = list_items or []
        self._historical = historical or {"historical": []}
        self._ratios = ratios or []
        self._profile = profile or []
        self._income = income or []
        self._balance = balance or []
        self._cashflow = cashflow or []

    async def list_us_stocks(self) -> list[dict[str, Any]]:
        return self._list

    async def get_historical_prices(self, symbol: str, start: str, end: str) -> dict[str, Any]:
        return self._historical

    async def get_ratios_ttm(self, symbol: str) -> list[dict[str, Any]]:
        return self._ratios

    async def get_profile(self, symbol: str) -> list[dict[str, Any]]:
        return self._profile

    async def get_income_statements(
        self, symbol: str, period: str = "annual", limit: int = 5
    ) -> list[dict[str, Any]]:
        return self._income

    async def get_balance_sheets(
        self, symbol: str, period: str = "annual", limit: int = 5
    ) -> list[dict[str, Any]]:
        return self._balance

    async def get_cashflow_statements(
        self, symbol: str, period: str = "annual", limit: int = 5
    ) -> list[dict[str, Any]]:
        return self._cashflow

    async def aclose(self) -> None:
        pass


class _StubSeekingAlpha:
    def __init__(self, *, response: dict[str, Any] | None = None) -> None:
        self._response = response or {}

    async def get_realtime_quotes(self, symbols: list[str]) -> dict[str, Any]:
        return self._response

    async def aclose(self) -> None:
        pass


@pytest.mark.asyncio
async def test_list_stocks_filters_by_exchange() -> None:
    fmp = _StubFmp(
        list_items=[
            {"symbol": "AAPL", "name": "Apple", "exchangeShortName": "NASDAQ"},
            {"symbol": "BRK-A", "name": "Berkshire", "exchangeShortName": "NYSE"},
            {"symbol": "ABCD.L", "name": "London co", "exchangeShortName": "LSE"},
            {"symbol": "XYZ", "name": "Amex co", "exchangeShortName": "AMEX"},
            {"symbol": None, "name": "broken", "exchangeShortName": "NYSE"},
        ]
    )
    provider = UsProvider(fmp_client=fmp, sa_client=_StubSeekingAlpha())
    stocks = await provider.list_stocks()

    symbols = [s.symbol for s in stocks]
    assert symbols == ["AAPL", "BRK-A", "XYZ"]
    assert all(s.market == "us" for s in stocks)


@pytest.mark.asyncio
async def test_get_daily_bars_sorts_ascending_and_skips_bad_rows() -> None:
    fmp = _StubFmp(
        historical={
            "historical": [
                # FMP 倒序返回
                {
                    "date": "2024-01-03",
                    "open": 11.0,
                    "high": 12.0,
                    "low": 10.5,
                    "close": 11.5,
                    "volume": 200000,
                },
                {
                    "date": "2024-01-02",
                    "open": 10.0,
                    "high": 11.0,
                    "low": 9.5,
                    "close": 10.5,
                    "volume": 100000,
                },
                # 缺字段应被跳过
                {
                    "date": "2024-01-04",
                    "open": None,
                    "high": 12.0,
                    "low": 10.0,
                    "close": 11.0,
                    "volume": 300000,
                },
                # 无法解析的日期应被跳过
                {"date": "not-a-date", "open": 1, "high": 1, "low": 1, "close": 1, "volume": 1},
            ]
        }
    )
    provider = UsProvider(fmp_client=fmp, sa_client=_StubSeekingAlpha())
    bars = await provider.get_daily_bars("AAPL", date(2024, 1, 1), date(2024, 1, 31))

    assert [b.date for b in bars] == [date(2024, 1, 2), date(2024, 1, 3)]
    assert bars[0].close == Decimal("10.5")
    assert bars[1].volume == 200000


@pytest.mark.asyncio
async def test_get_fundamentals_merges_ratios_and_profile() -> None:
    fmp = _StubFmp(
        ratios=[
            {
                "peRatioTTM": 30.0,
                "priceToBookRatioTTM": 40.0,
                "returnOnEquityTTM": 0.45,
                "dividendYieldTTM": 0.005,
            }
        ],
        profile=[{"mktCap": 3.1e12}],
    )
    provider = UsProvider(fmp_client=fmp, sa_client=_StubSeekingAlpha())
    f = await provider.get_fundamentals("AAPL")

    assert f is not None
    assert f.pe == Decimal("30.0")
    assert f.pb == Decimal("40.0")
    assert f.roe == Decimal("0.45")
    assert f.dividend_yield == Decimal("0.005")
    assert f.market_cap == Decimal(str(3.1e12))


@pytest.mark.asyncio
async def test_get_fundamentals_falls_back_to_misspelled_dividend_yield() -> None:
    # FMP 历史上两种拼写都出现过
    fmp = _StubFmp(
        ratios=[{"peRatioTTM": 10.0, "dividendYielTTM": 0.02}],
        profile=[],
    )
    provider = UsProvider(fmp_client=fmp, sa_client=_StubSeekingAlpha())
    f = await provider.get_fundamentals("AAPL")
    assert f is not None
    assert f.dividend_yield == Decimal("0.02")


@pytest.mark.asyncio
async def test_get_fundamentals_returns_none_when_all_empty() -> None:
    fmp = _StubFmp(ratios=[], profile=[])
    provider = UsProvider(fmp_client=fmp, sa_client=_StubSeekingAlpha())
    assert await provider.get_fundamentals("AAPL") is None


@pytest.mark.asyncio
async def test_get_realtime_quote_parses_seeking_alpha_shape() -> None:
    sa = _StubSeekingAlpha(
        response={
            "data": {
                "quotes": {
                    "AAPL": {
                        "attributes": {
                            "last": 200.5,
                            "percent_change": 1.23,
                            "volume": 5000000,
                        }
                    }
                }
            }
        }
    )
    provider = UsProvider(fmp_client=_StubFmp(), sa_client=sa)

    q = await provider.get_realtime_quote("AAPL")
    assert q is not None
    assert q.price == Decimal("200.5")
    assert q.change_pct == Decimal("1.23")
    assert q.volume == 5000000


@pytest.mark.asyncio
async def test_get_realtime_quote_returns_none_when_missing() -> None:
    sa = _StubSeekingAlpha(response={"data": {"quotes": {}}})
    provider = UsProvider(fmp_client=_StubFmp(), sa_client=sa)
    assert await provider.get_realtime_quote("AAPL") is None


@pytest.mark.asyncio
async def test_get_financial_snapshots_joins_three_statements() -> None:
    fmp = _StubFmp(
        income=[
            {"date": "2024-12-31", "revenue": 400e9, "netIncome": 100e9},
            {"date": "2023-12-31", "revenue": 380e9, "netIncome": 95e9},
        ],
        balance=[
            {"date": "2024-12-31", "totalAssets": 350e9, "totalStockholdersEquity": 60e9},
            {"date": "2023-12-31", "totalAssets": 340e9, "totalStockholdersEquity": 55e9},
        ],
        cashflow=[
            {"date": "2024-12-31", "operatingCashFlow": 120e9, "capitalExpenditure": -10e9},
            {"date": "2023-12-31", "operatingCashFlow": 115e9, "capitalExpenditure": -9e9},
        ],
    )
    provider = UsProvider(fmp_client=fmp, sa_client=_StubSeekingAlpha())
    snaps = await provider.get_financial_snapshots("AAPL", limit=2)

    assert [s.period for s in snaps] == [date(2024, 12, 31), date(2023, 12, 31)]
    assert snaps[0].revenue == Decimal(str(400e9))
    assert snaps[0].total_equity == Decimal(str(60e9))
    assert snaps[0].operating_cashflow == Decimal(str(120e9))
    assert snaps[0].capex == Decimal(str(-10e9))


@pytest.mark.asyncio
async def test_get_financial_snapshots_empty_when_no_fmp(monkeypatch) -> None:
    from app.data.providers import us as us_mod

    monkeypatch.setattr(us_mod.settings, "fmp_api_key", None)
    provider = UsProvider(fmp_client=None, sa_client=_StubSeekingAlpha())
    assert await provider.get_financial_snapshots("AAPL") == []
