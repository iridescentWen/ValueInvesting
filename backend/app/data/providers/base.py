from abc import ABC, abstractmethod
from datetime import date
from decimal import Decimal
from typing import ClassVar, Literal

from pydantic import BaseModel

from app.models.enums import Market

PeriodType = Literal["annual", "quarterly"]


class Stock(BaseModel):
    symbol: str
    name: str
    market: Market
    exchange: str | None = None


class DailyBar(BaseModel):
    symbol: str
    date: date
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: int


class Fundamentals(BaseModel):
    symbol: str
    as_of: date
    pe: Decimal | None = None
    pb: Decimal | None = None
    roe: Decimal | None = None
    dividend_yield: Decimal | None = None
    market_cap: Decimal | None = None


class RealtimeQuote(BaseModel):
    symbol: str
    price: Decimal
    change_pct: Decimal
    volume: int


class FinancialSnapshot(BaseModel):
    """单期财报关键字段（合并 income / balance / cashflow 的核心行）。

    不求全——只够 screener 和 agent 做基础价值分析（revenue/net_income/equity/
    owner earnings proxy）。需要更细颗粒再扩。
    """

    symbol: str
    period: date
    period_type: PeriodType
    # income
    revenue: Decimal | None = None
    net_income: Decimal | None = None
    # balance
    total_assets: Decimal | None = None
    total_equity: Decimal | None = None
    # cashflow
    operating_cashflow: Decimal | None = None
    capex: Decimal | None = None


class MarketDataProvider(ABC):
    market: ClassVar[Market]

    @abstractmethod
    async def list_stocks(self) -> list[Stock]: ...

    @abstractmethod
    async def get_daily_bars(self, symbol: str, start: date, end: date) -> list[DailyBar]: ...

    @abstractmethod
    async def get_fundamentals(self, symbol: str) -> Fundamentals | None: ...

    @abstractmethod
    async def get_realtime_quote(self, symbol: str) -> RealtimeQuote | None: ...

    @abstractmethod
    async def get_financial_snapshots(
        self,
        symbol: str,
        period_type: PeriodType = "annual",
        limit: int = 5,
    ) -> list[FinancialSnapshot]: ...
