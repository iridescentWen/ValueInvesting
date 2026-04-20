from datetime import date, datetime
from decimal import Decimal
from typing import Any, ClassVar

import httpx

from app.config import settings
from app.data.clients.akshare import AkshareClient
from app.data.clients.mairui import MairuiClient
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


def _infer_exchange(code: str) -> str | None:
    first = code[:1]
    if first in ("6", "9"):
        return "SH"
    if first in ("0", "3"):
        return "SZ"
    return None


def _dec(v: Any) -> Decimal | None:
    """DataFrame cell / dict value → Decimal，遇 NaN / None / "" 返回 None。"""
    if v is None or v == "":
        return None
    # NaN: float('nan') != float('nan')
    if isinstance(v, float) and v != v:
        return None
    try:
        return Decimal(str(v))
    except (ValueError, ArithmeticError):
        return None


def _to_date(v: Any) -> date | None:
    if v is None or v == "":
        return None
    if isinstance(v, date):
        return v
    if hasattr(v, "date"):
        return v.date()
    if isinstance(v, str):
        try:
            return datetime.strptime(v[:10], "%Y-%m-%d").date()
        except ValueError:
            return None
    return None


class CnProvider(MarketDataProvider):
    """A 股 provider：AkShare 管基础（列表 / 日线 / 指标 / 实时），Mairui 管深度财报。"""

    market: ClassVar[Market] = "cn"

    def __init__(
        self,
        akshare_client: AkshareClient | None = None,
        mairui_client: MairuiClient | None = None,
    ) -> None:
        self._ak = akshare_client or AkshareClient(concurrency=settings.akshare_rate_limit)
        if mairui_client is not None:
            self._mr: MairuiClient | None = mairui_client
        elif settings.mairui_api_key:
            self._mr = MairuiClient(
                api_key=settings.mairui_api_key,
                base_url=settings.mairui_base_url,
            )
        else:
            self._mr = None

    async def aclose(self) -> None:
        if self._mr is not None:
            await self._mr.aclose()

    async def list_stocks(self) -> list[Stock]:
        df = await self._ak.list_a_stocks()
        stocks: list[Stock] = []
        for _, row in df.iterrows():
            code = str(row["code"]).strip()
            stocks.append(
                Stock(
                    symbol=code,
                    name=str(row["name"]).strip(),
                    market="cn",
                    exchange=_infer_exchange(code),
                )
            )
        return stocks

    async def get_daily_bars(self, symbol: str, start: date, end: date) -> list[DailyBar]:
        df = await self._ak.get_daily_bars(
            symbol=symbol,
            start=start.strftime("%Y%m%d"),
            end=end.strftime("%Y%m%d"),
        )
        bars: list[DailyBar] = []
        for _, row in df.iterrows():
            d = _to_date(row.get("日期"))
            if d is None:
                continue
            open_, high, low, close = (
                _dec(row.get("开盘")),
                _dec(row.get("最高")),
                _dec(row.get("最低")),
                _dec(row.get("收盘")),
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
                    volume=int(row.get("成交量") or 0),
                )
            )
        return bars

    async def get_fundamentals(self, symbol: str) -> Fundamentals | None:
        df = await self._ak.get_indicator(symbol)
        if df.empty:
            return None
        row = df.iloc[-1]
        as_of = _to_date(row.get("数据日期")) or date.today()
        return Fundamentals(
            symbol=symbol,
            as_of=as_of,
            pe=_dec(row.get("PE(TTM)")),
            pb=_dec(row.get("市净率")),
            # stock_value_em 不给 ROE / 股息率，留空；后续接
            # stock_financial_analysis_indicator 再补
            roe=None,
            dividend_yield=None,
            market_cap=_dec(row.get("总市值")),
        )

    async def get_realtime_quote(self, symbol: str) -> RealtimeQuote | None:
        df = await self._ak.get_spot()
        hit = df[df["代码"] == symbol]
        if hit.empty:
            return None
        row = hit.iloc[0]
        price = _dec(row.get("最新价"))
        if price is None:
            return None
        return RealtimeQuote(
            symbol=symbol,
            price=price,
            change_pct=_dec(row.get("涨跌幅")) or Decimal("0"),
            volume=int(row.get("成交量") or 0),
        )

    async def get_financial_snapshots(
        self,
        symbol: str,
        period_type: PeriodType = "annual",
        limit: int = 5,
    ) -> list[FinancialSnapshot]:
        if self._mr is None:
            return []
        try:
            metrics = await self._mr.get_financial_metrics(symbol)
        except httpx.HTTPStatusError:
            return []

        # Mairui cwzb 是"混合指标"，只能取到 revenue / net_income / total_assets；
        # equity / cashflow / capex 这档套餐拿不到，留 None
        rows: list[tuple[str, dict[str, Any]]] = []
        for item in metrics:
            period = item.get("date") or item.get("rq") or item.get("报告日")
            if period:
                rows.append((str(period)[:10], item))

        if period_type == "annual":
            rows = [r for r in rows if r[0].endswith("-12-31")]
        rows.sort(key=lambda r: r[0], reverse=True)
        rows = rows[:limit]

        snapshots: list[FinancialSnapshot] = []
        for p, item in rows:
            period_date = _to_date(p)
            if period_date is None:
                continue
            snapshots.append(
                FinancialSnapshot(
                    symbol=symbol,
                    period=period_date,
                    period_type=period_type,
                    revenue=_dec(item.get("zyyw")),
                    net_income=_dec(item.get("kflr")),
                    total_assets=_dec(item.get("zzc")),
                    total_equity=None,
                    operating_cashflow=None,
                    capex=None,
                )
            )
        return snapshots
