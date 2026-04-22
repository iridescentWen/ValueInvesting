"""Stocks API endpoint 测试——用 FastAPI TestClient,provider 层打桩。"""

from datetime import date
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from app.data.providers.base import (
    DailyBar,
    FinancialSnapshot,
    Fundamentals,
    MarketDataProvider,
    PeriodType,
    RealtimeQuote,
    Stock,
)
from app.main import app


class _StubProvider(MarketDataProvider):
    """最小 provider stub,只把 get_financial_snapshots 做活。"""

    market = "cn"  # type: ignore[assignment]

    def __init__(self, snapshots: list[FinancialSnapshot]) -> None:
        self._snapshots = snapshots
        self.calls: list[tuple[str, PeriodType, int]] = []

    async def list_stocks(self) -> list[Stock]:
        return []

    async def get_daily_bars(self, symbol: str, start: date, end: date) -> list[DailyBar]:
        return []

    async def get_fundamentals(self, symbol: str) -> Fundamentals | None:
        return None

    async def get_realtime_quote(self, symbol: str) -> RealtimeQuote | None:
        return None

    async def get_financial_snapshots(
        self,
        symbol: str,
        period_type: PeriodType = "annual",
        limit: int = 5,
    ) -> list[FinancialSnapshot]:
        self.calls.append((symbol, period_type, limit))
        return self._snapshots


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


def test_get_financials_returns_snapshots(client, monkeypatch) -> None:
    snaps = [
        FinancialSnapshot(
            symbol="600519",
            period=date(2024, 12, 31),
            period_type="annual",
            revenue=Decimal("170000000000"),
            net_income=Decimal("85000000000"),
            total_assets=Decimal("300000000000"),
            total_equity=Decimal("200000000000"),
            operating_cashflow=Decimal("90000000000"),
            capex=Decimal("-3000000000"),
        ),
    ]
    stub = _StubProvider(snaps)
    from app.api import stocks as stocks_mod

    monkeypatch.setattr(stocks_mod, "get_provider", lambda market: stub)

    resp = client.get("/api/stocks/600519/financials?market=cn&years=3")
    assert resp.status_code == 200
    payload = resp.json()
    assert len(payload) == 1
    row = payload[0]
    assert row["symbol"] == "600519"
    assert row["period"] == "2024-12-31"
    assert row["period_type"] == "annual"
    # Decimal 序列化成 string
    assert row["revenue"] == "170000000000"
    assert row["capex"] == "-3000000000"
    # 参数传到了 provider
    assert stub.calls == [("600519", "annual", 3)]


def test_get_financials_defaults_to_annual_5_years(client, monkeypatch) -> None:
    stub = _StubProvider([])
    from app.api import stocks as stocks_mod

    monkeypatch.setattr(stocks_mod, "get_provider", lambda market: stub)

    resp = client.get("/api/stocks/AAPL/financials?market=us")
    assert resp.status_code == 200
    assert resp.json() == []
    assert stub.calls == [("AAPL", "annual", 5)]


def test_get_financials_passes_quarterly(client, monkeypatch) -> None:
    stub = _StubProvider([])
    from app.api import stocks as stocks_mod

    monkeypatch.setattr(stocks_mod, "get_provider", lambda market: stub)

    resp = client.get("/api/stocks/0700.HK/financials?market=hk&period=quarterly&years=8")
    assert resp.status_code == 200
    assert stub.calls == [("0700.HK", "quarterly", 8)]


def test_get_financials_rejects_invalid_period(client, monkeypatch) -> None:
    stub = _StubProvider([])
    from app.api import stocks as stocks_mod

    monkeypatch.setattr(stocks_mod, "get_provider", lambda market: stub)

    resp = client.get("/api/stocks/600519/financials?market=cn&period=yearly")
    assert resp.status_code == 422


def test_get_financials_rejects_out_of_range_years(client, monkeypatch) -> None:
    stub = _StubProvider([])
    from app.api import stocks as stocks_mod

    monkeypatch.setattr(stocks_mod, "get_provider", lambda market: stub)

    # years > 20 越界
    resp = client.get("/api/stocks/600519/financials?market=cn&years=25")
    assert resp.status_code == 422
    # years < 1 越界
    resp = client.get("/api/stocks/600519/financials?market=cn&years=0")
    assert resp.status_code == 422
