"""港股 provider：AkShare Sina 管全市场名单,yfinance 管 per-stock 基本面。

yfinance 是同步库,所有调用用 `asyncio.to_thread` 包一层转 async,并用
Semaphore 限并发避免被上游限流。

全港股名单(~2700 支)来自 AkShare `stock_hk_spot`(Sina 端点,境外能通);
East Money 的 `stock_hk_spot_em` 境外 geo-block,不用。AkShare 失败时降级到
硬编码的 `HK_SEED_UNIVERSE`(70+ 支 HSI 蓝筹)。
"""

import asyncio
import logging
from datetime import date
from decimal import Decimal
from typing import Any, ClassVar

from app.data.cache import AsyncTTLCache
from app.data.providers.base import (
    DailyBar,
    FinancialSnapshot,
    Fundamentals,
    MarketDataProvider,
    PeriodType,
    RealtimeQuote,
    Stock,
)
from app.data.providers.hk_universe import HK_SEED_UNIVERSE
from app.models.enums import Market

log = logging.getLogger(__name__)

_UNIVERSE_TTL_SECONDS = 24 * 3600
_FUND_TTL_SECONDS = 3600  # 1h:2700 支 yfinance 重拉一次太贵,缓存命中省掉整轮冷启


def _hk_code_to_yf(code: str) -> str:
    """AkShare Sina 返回 5 位代码(`00700`);yfinance 要 4 位 + `.HK`(`0700.HK`)。

    5 位一般是 `0` + 4 位常规 ticker;偶尔有 5 位真 ticker(少见)。
    统一:去首位 0(如果总长 5 且首位是 0),再拼 `.HK`。
    """
    code = code.strip()
    if len(code) == 5 and code.startswith("0"):
        code = code[1:]
    return f"{code.zfill(4)}.HK"


def _dec(v: Any) -> Decimal | None:
    """DataFrame cell / dict value → Decimal；NaN / Infinity / 空值都归 None。

    yfinance 对亏损股 / 无财报股会返回 `inf`,pydantic Fundamentals 里 Decimal 字段
    禁止非有限值,不过滤会炸。
    """
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


def _pct_to_decimal(v: Any) -> Decimal | None:
    """yfinance 0.2.x 起把 dividendYield 返回成百分数(3.49 表示 3.49%),
    与我们 Fundamentals 里"十进制小数"的约定相反。归一:>1 就认为是百分数。
    """
    d = _dec(v)
    if d is None:
        return None
    if d > 1:
        return d / Decimal(100)
    return d


class HkProvider(MarketDataProvider):
    market: ClassVar[Market] = "hk"

    def __init__(self, concurrency: int = 6) -> None:
        # yfinance 对 2700 支批量查询并发 > 8 就频繁 401 Invalid Crumb
        # (Yahoo 反爬 session cookie),降到 6 换稳定性——冷启动慢一点,
        # 命中缓存后无感
        self._sem = asyncio.Semaphore(concurrency)
        # lazy-import,`hk` extras 装过才能用
        self._yf: Any | None = None
        self._ak: Any | None = None
        self._universe_cache: AsyncTTLCache[list[Stock]] = AsyncTTLCache(_UNIVERSE_TTL_SECONDS)
        self._fund_cache: AsyncTTLCache[Fundamentals] = AsyncTTLCache(_FUND_TTL_SECONDS)

    def _ensure_yf(self) -> Any:
        if self._yf is None:
            import yfinance as yf

            self._yf = yf
        return self._yf

    def _ensure_ak(self) -> Any:
        if self._ak is None:
            import akshare as ak

            self._ak = ak
        return self._ak

    async def aclose(self) -> None:
        # yfinance / akshare 无需显式关闭
        return None

    async def _get_info(self, symbol: str) -> dict[str, Any]:
        yf = self._ensure_yf()

        def _fetch() -> dict[str, Any]:
            return yf.Ticker(symbol).info or {}

        async with self._sem:
            return await asyncio.to_thread(_fetch)

    async def list_stocks(self) -> list[Stock]:
        """全港股名单(~2700 支)。AkShare Sina `stock_hk_spot` 为主,seed 兜底。

        24h TTL in-memory 缓存。
        """
        return await self._universe_cache.get_or_load("hk", self._load_universe)

    async def _load_universe(self) -> list[Stock]:
        try:
            ak = self._ensure_ak()
            df = await asyncio.to_thread(ak.stock_hk_spot)
            stocks: list[Stock] = []
            for _, row in df.iterrows():
                raw = str(row.get("代码") or "").strip()
                if not raw:
                    continue
                name = str(row.get("中文名称") or row.get("英文名称") or raw).strip()
                stocks.append(
                    Stock(
                        symbol=_hk_code_to_yf(raw),
                        name=name,
                        market="hk",
                        exchange="HKEX",
                    )
                )
            if stocks:
                log.info("hk universe: loaded %d from AkShare Sina", len(stocks))
                return stocks
        except Exception as e:  # noqa: BLE001
            log.warning("hk universe: AkShare Sina failed (%s), fallback to seed", e)

        log.warning("hk universe: using hardcoded HK_SEED_UNIVERSE (%d)", len(HK_SEED_UNIVERSE))
        return [
            Stock(symbol=sym, name=name, market="hk", exchange="HKEX")
            for sym, name in HK_SEED_UNIVERSE
        ]

    async def get_fundamentals(self, symbol: str) -> Fundamentals | None:
        cached = self._fund_cache.get(symbol)
        if cached is not None:
            return cached
        try:
            info = await self._get_info(symbol)
        except Exception as e:  # noqa: BLE001 — yfinance 抛的异常类型不固定
            log.debug("yfinance info failed for %s: %s", symbol, e)
            return None
        if not info:
            return None
        result = Fundamentals(
            symbol=symbol,
            as_of=date.today(),
            pe=_dec(info.get("trailingPE")),
            pb=_dec(info.get("priceToBook")),
            # ROE 在 yfinance 所有版本里都是小数(0.18 = 18%);dividendYield
            # 在 0.2.x 改成百分数,统一走 _pct_to_decimal 做兜底
            roe=_pct_to_decimal(info.get("returnOnEquity")),
            dividend_yield=_pct_to_decimal(info.get("dividendYield")),
            market_cap=_dec(info.get("marketCap")),
        )
        self._fund_cache.set(symbol, result)
        return result

    async def get_daily_bars(
        self, symbol: str, start: date, end: date
    ) -> list[DailyBar]:
        # screener 不依赖这个;本轮留空实现,未来再接 yf.Ticker.history
        return []

    async def get_realtime_quote(self, symbol: str) -> RealtimeQuote | None:
        return None

    async def get_financial_snapshots(
        self,
        symbol: str,
        period_type: PeriodType = "annual",
        limit: int = 5,
    ) -> list[FinancialSnapshot]:
        """yfinance 三表映射到 FinancialSnapshot。

        yfinance 行标签没有强约定(同一字段可能叫 `Total Revenue` / `Operating
        Revenue` / `Revenue`),用多 label fallback 找第一个命中的行。
        """
        yf = self._ensure_yf()

        def _fetch() -> tuple[Any, Any, Any]:
            t = yf.Ticker(symbol)
            if period_type == "quarterly":
                return t.quarterly_income_stmt, t.quarterly_balance_sheet, t.quarterly_cashflow
            return t.income_stmt, t.balance_sheet, t.cashflow

        try:
            async with self._sem:
                income, balance, cashflow = await asyncio.to_thread(_fetch)
        except Exception as e:  # noqa: BLE001 — yfinance 抛的异常类型不固定
            log.debug("yfinance financials failed for %s: %s", symbol, e)
            return []

        def _row(df: Any, *labels: str) -> Any:
            if df is None or df.empty:
                return None
            for label in labels:
                if label in df.index:
                    return df.loc[label]
            return None

        rev = _row(income, "Total Revenue", "Operating Revenue", "Revenue")
        ni = _row(
            income,
            "Net Income",
            "Net Income Common Stockholders",
            "Net Income From Continuing Operation Net Minority Interest",
        )
        ta = _row(balance, "Total Assets")
        eq = _row(
            balance,
            "Stockholders Equity",
            "Common Stock Equity",
            "Total Equity Gross Minority Interest",
        )
        ocf = _row(
            cashflow,
            "Operating Cash Flow",
            "Cash Flow From Continuing Operating Activities",
        )
        capex = _row(cashflow, "Capital Expenditure")

        def _periods(*frames: Any) -> list[Any]:
            cols: set[Any] = set()
            for f in frames:
                if f is not None and not f.empty:
                    cols.update(f.columns)
            return sorted(cols, reverse=True)[:limit]

        snapshots: list[FinancialSnapshot] = []
        for col in _periods(income, balance, cashflow):
            period_date = col.date() if hasattr(col, "date") else col
            snapshots.append(
                FinancialSnapshot(
                    symbol=symbol,
                    period=period_date,
                    period_type=period_type,
                    revenue=_dec(rev.get(col)) if rev is not None else None,
                    net_income=_dec(ni.get(col)) if ni is not None else None,
                    total_assets=_dec(ta.get(col)) if ta is not None else None,
                    total_equity=_dec(eq.get(col)) if eq is not None else None,
                    operating_cashflow=_dec(ocf.get(col)) if ocf is not None else None,
                    capex=_dec(capex.get(col)) if capex is not None else None,
                )
            )
        return snapshots
