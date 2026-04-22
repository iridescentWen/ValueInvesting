from datetime import date, datetime
from decimal import Decimal
from typing import Any, ClassVar

import httpx

from app.config import settings
from app.data.cache import AsyncTTLCache
from app.data.clients.fmp import FmpClient
from app.data.clients.seekingalpha import SeekingAlphaClient
from app.data.providers.base import (
    DailyBar,
    FinancialSnapshot,
    Fundamentals,
    MarketDataProvider,
    PeriodType,
    RealtimeQuote,
    Stock,
)
from app.models.enums import Market

_US_EXCHANGES = {"NYSE", "NASDAQ", "AMEX"}
_FUND_TTL_SECONDS = 3600  # 1h: screener reload 期间 FMP quota 友好


def _dec(v: Any) -> Decimal | None:
    if v is None or v == "":
        return None
    if isinstance(v, float):
        if v != v or v in (float("inf"), float("-inf")):
            return None
    try:
        d = Decimal(str(v))
    except (ValueError, ArithmeticError):
        return None
    if not d.is_finite():
        return None
    return d


class UsProvider(MarketDataProvider):
    """美股 provider：FMP 管列表 / 日线 / 基本面 / 财报；Seeking Alpha 管 realtime。"""

    market: ClassVar[Market] = "us"

    def __init__(
        self,
        fmp_client: FmpClient | None = None,
        sa_client: SeekingAlphaClient | None = None,
    ) -> None:
        if fmp_client is not None:
            self._fmp: FmpClient | None = fmp_client
        elif settings.fmp_api_key:
            self._fmp = FmpClient(api_key=settings.fmp_api_key, base_url=settings.fmp_base_url)
        else:
            self._fmp = None

        if sa_client is not None:
            self._sa: SeekingAlphaClient | None = sa_client
        elif settings.rapidapi_key:
            self._sa = SeekingAlphaClient(
                api_key=settings.rapidapi_key,
                host=settings.rapidapi_host,
                autocomplete_url=settings.rapidapi_sa_autocomplete_url,
                quote_url=settings.rapidapi_sa_quote_url,
            )
        else:
            self._sa = None

        self._fund_cache: AsyncTTLCache[Fundamentals] = AsyncTTLCache(_FUND_TTL_SECONDS)

    async def aclose(self) -> None:
        if self._fmp is not None:
            await self._fmp.aclose()
        if self._sa is not None:
            await self._sa.aclose()

    async def list_stocks(self) -> list[Stock]:
        if self._fmp is None:
            return []
        items = await self._fmp.list_us_stocks()
        stocks: list[Stock] = []
        for item in items:
            if item.get("exchangeShortName") not in _US_EXCHANGES:
                continue
            sym = item.get("symbol")
            if not sym:
                continue
            stocks.append(
                Stock(
                    symbol=sym,
                    name=item.get("name") or sym,
                    market="us",
                    exchange=item.get("exchangeShortName"),
                )
            )
        return stocks

    async def get_daily_bars(self, symbol: str, start: date, end: date) -> list[DailyBar]:
        if self._fmp is None:
            return []
        data = await self._fmp.get_historical_prices(
            symbol, start.strftime("%Y-%m-%d"), end.strftime("%Y-%m-%d")
        )
        bars: list[DailyBar] = []
        for item in data.get("historical", []):
            try:
                d = datetime.strptime(item["date"], "%Y-%m-%d").date()
            except (KeyError, ValueError):
                continue
            open_, high, low, close = (
                _dec(item.get("open")),
                _dec(item.get("high")),
                _dec(item.get("low")),
                _dec(item.get("close")),
            )
            if None in (open_, high, low, close):
                continue
            bars.append(
                DailyBar(
                    symbol=symbol,
                    date=d,
                    open=open_,
                    high=high,
                    low=low,
                    close=close,
                    volume=int(item.get("volume") or 0),
                )
            )
        # FMP 返回按日期倒序；统一升序
        bars.sort(key=lambda b: b.date)
        return bars

    async def get_fundamentals(self, symbol: str) -> Fundamentals | None:
        if self._fmp is None:
            return None

        cached = self._fund_cache.get(symbol)
        if cached is not None:
            return cached

        try:
            ratios = await self._fmp.get_ratios_ttm(symbol)
            profile = await self._fmp.get_profile(symbol)
        except httpx.HTTPStatusError:
            return None
        if not ratios and not profile:
            return None
        r = ratios[0] if ratios else {}
        p = profile[0] if profile else {}
        result = Fundamentals(
            symbol=symbol,
            as_of=date.today(),
            pe=_dec(r.get("peRatioTTM")),
            pb=_dec(r.get("priceToBookRatioTTM")),
            roe=_dec(r.get("returnOnEquityTTM")),
            # FMP 有两种拼写，两个都试一下
            dividend_yield=_dec(r.get("dividendYieldTTM") or r.get("dividendYielTTM")),
            market_cap=_dec(p.get("mktCap")),
        )
        self._fund_cache.set(symbol, result)
        return result

    async def get_realtime_quote(self, symbol: str) -> RealtimeQuote | None:
        if self._sa is None:
            return None
        try:
            data = await self._sa.get_realtime_quotes([symbol])
        except httpx.HTTPStatusError:
            return None

        # SA 响应形如 {"data": {"quotes": {"AAPL": {"attributes": {...}}}}}
        quotes = (data.get("data") or {}).get("quotes") or {}
        info = quotes.get(symbol.upper()) or quotes.get(symbol)
        if not info:
            return None
        attrs = info.get("attributes") or info
        price = _dec(attrs.get("last") or attrs.get("price"))
        if price is None:
            return None
        return RealtimeQuote(
            symbol=symbol,
            price=price,
            change_pct=_dec(attrs.get("percent_change")) or Decimal("0"),
            volume=int(attrs.get("volume") or 0),
        )

    async def get_financial_snapshots(
        self,
        symbol: str,
        period_type: PeriodType = "annual",
        limit: int = 5,
    ) -> list[FinancialSnapshot]:
        if self._fmp is None:
            return []
        try:
            income = await self._fmp.get_income_statements(symbol, period_type, limit)
            balance = await self._fmp.get_balance_sheets(symbol, period_type, limit)
            cashflow = await self._fmp.get_cashflow_statements(symbol, period_type, limit)
        except httpx.HTTPStatusError:
            return []

        def by_date(items: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
            return {item["date"]: item for item in items if item.get("date")}

        inc_map = by_date(income)
        bal_map = by_date(balance)
        cf_map = by_date(cashflow)

        periods = sorted(set(inc_map) | set(bal_map) | set(cf_map), reverse=True)[:limit]

        snapshots: list[FinancialSnapshot] = []
        for p in periods:
            try:
                period_date = datetime.strptime(p, "%Y-%m-%d").date()
            except ValueError:
                continue
            inc = inc_map.get(p, {})
            bal = bal_map.get(p, {})
            cf = cf_map.get(p, {})
            snapshots.append(
                FinancialSnapshot(
                    symbol=symbol,
                    period=period_date,
                    period_type=period_type,
                    revenue=_dec(inc.get("revenue")),
                    net_income=_dec(inc.get("netIncome")),
                    total_assets=_dec(bal.get("totalAssets")),
                    total_equity=_dec(bal.get("totalStockholdersEquity")),
                    operating_cashflow=_dec(cf.get("operatingCashFlow")),
                    capex=_dec(cf.get("capitalExpenditure")),
                )
            )
        return snapshots
