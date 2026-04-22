import asyncio
import logging
from datetime import date, datetime
from decimal import Decimal
from typing import Any, ClassVar

from app.config import settings
from app.data.cache import AsyncTTLCache
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
from app.data.providers.cn_universe import CN_SEED_UNIVERSE
from app.models.enums import Market

log = logging.getLogger(__name__)

# 全市场名单一天刷新一次够了——新股 / 改名都是低频事件
_UNIVERSE_TTL_SECONDS = 24 * 3600


def _infer_exchange(code: str) -> str | None:
    first = code[:1]
    if first in ("6", "9"):
        return "SH"
    if first in ("0", "3"):
        return "SZ"
    return None


def _strip_suffix(dm: str) -> str:
    """Mairui 的 `dm` 是 `000001.SZ` 形式;provider 其他地方用纯 6 位代码。"""
    return dm.split(".", 1)[0] if "." in dm else dm


def _dec(v: Any) -> Decimal | None:
    """DataFrame cell / dict value → Decimal，NaN / Infinity / 空值都归 None。"""
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
        self._universe_cache: AsyncTTLCache[list[Stock]] = AsyncTTLCache(_UNIVERSE_TTL_SECONDS)

    async def aclose(self) -> None:
        if self._mr is not None:
            await self._mr.aclose()

    async def list_stocks(self) -> list[Stock]:
        """全 A 股名单（~5200 支）。优先 Mairui `/hslt/list`（0.3s,境外稳定、
        含 jys 交易所、中文名）；失败降级到 AkShare Sina `stock_info_a_code_name`
        （6s,无交易所）；再失败降级到硬编码 `CN_SEED_UNIVERSE`。

        24h TTL in-memory 缓存——新股 / 改名都是低频事件。
        """
        return await self._universe_cache.get_or_load("cn", self._load_universe)

    async def _load_universe(self) -> list[Stock]:
        # 1) Mairui (最快、有交易所信息)
        if self._mr is not None:
            try:
                rows = await self._mr.list_all_stocks()
                stocks = [
                    Stock(
                        symbol=_strip_suffix(str(r.get("dm", ""))),
                        name=str(r.get("mc", "")).strip(),
                        market="cn",
                        exchange=str(r.get("jys") or "") or None,
                    )
                    for r in rows
                    if r.get("dm")
                ]
                stocks = [s for s in stocks if s.symbol and s.name]
                if stocks:
                    log.info("cn universe: loaded %d from Mairui", len(stocks))
                    return stocks
            except Exception as e:  # noqa: BLE001 — Mairui 网络/限流/套餐问题都吃
                log.warning("cn universe: Mairui list failed (%s), fallback to AkShare", e)

        # 2) AkShare Sina
        try:
            df = await self._ak.list_a_stocks()
            stocks = []
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
            if stocks:
                log.info("cn universe: loaded %d from AkShare Sina", len(stocks))
                return stocks
        except Exception as e:  # noqa: BLE001
            log.warning("cn universe: AkShare Sina failed (%s), fallback to seed", e)

        # 3) 硬编码兜底
        log.warning("cn universe: using hardcoded CN_SEED_UNIVERSE (%d)", len(CN_SEED_UNIVERSE))
        return [
            Stock(symbol=code, name=name, market="cn", exchange=_infer_exchange(code))
            for code, name in CN_SEED_UNIVERSE
        ]

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
        base = Fundamentals(
            symbol=symbol,
            as_of=as_of,
            pe=_dec(row.get("PE(TTM)")),
            pb=_dec(row.get("市净率")),
            # stock_value_em 不给 ROE / 股息率,下面并发补
            roe=None,
            dividend_yield=None,
            market_cap=_dec(row.get("总市值")),
        )
        return await self.enrich_fundamentals(base)

    async def enrich_fundamentals(self, base: Fundamentals) -> Fundamentals:
        """并发拉 ROE(同花顺财务摘要) + 股息率(乐咕乐股每日估值),填回基础字段。

        任一子请求失败不影响另一个;全失败时返回原样。
        """
        roe_task = self._fetch_roe(base.symbol)
        dv_task = self._fetch_dividend_yield(base.symbol)
        roe, dv = await asyncio.gather(roe_task, dv_task)
        return base.model_copy(update={"roe": roe, "dividend_yield": dv})

    async def _fetch_roe(self, symbol: str) -> Decimal | None:
        """从 stock_financial_abstract 提取最新的净资产收益率,返回十进制(0.15 = 15%)。"""
        try:
            df = await self._ak.get_financial_abstract(symbol)
        except Exception as e:  # noqa: BLE001 — akshare 抛的类型不固定
            log.debug("financial_abstract failed for %s: %s", symbol, e)
            return None
        if df.empty:
            return None
        # 列结构:[选项?, 指标, 期1, 期2, ...],指标列里找"净资产收益率"行
        try:
            mask = df["指标"].astype(str).str.contains("净资产收益率", na=False)
        except KeyError:
            return None
        rows = df[mask]
        if rows.empty:
            return None
        # 取第一行(同花顺一般给加权 ROE),期次列按从左到右最新,找第一个非空值
        row = rows.iloc[0]
        for col in df.columns:
            if col in ("选项", "指标"):
                continue
            val = _dec(row.get(col))
            if val is not None:
                # 同花顺返回的是百分数(如 15.2),归一到小数
                return val / Decimal(100)
        return None

    async def _fetch_dividend_yield(self, symbol: str) -> Decimal | None:
        """从 stock_a_indicator_lg 取最新 dv_ratio,返回十进制。"""
        try:
            df = await self._ak.get_indicator_lg(symbol)
        except Exception as e:  # noqa: BLE001
            log.debug("indicator_lg failed for %s: %s", symbol, e)
            return None
        if df.empty or "dv_ratio" not in df.columns:
            return None
        val = _dec(df.iloc[-1].get("dv_ratio"))
        if val is None:
            return None
        # 乐咕乐股的 dv_ratio 是百分数,归一到小数
        return val / Decimal(100)

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
        """走 AkShare Sina 三表端点(覆盖 20+ 年季度数据,境外能通)。

        Mairui 的 cwzb 套餐只给 revenue / net_income / total_assets,没有
        equity / cashflow / capex——这里换成 Sina 拿全。
        """
        exch = _infer_exchange(symbol)
        if exch is None:
            return []
        sina_code = f"{exch.lower()}{symbol}"

        try:
            income, balance, cashflow = await asyncio.gather(
                self._ak.get_financial_report_sina(sina_code, "利润表"),
                self._ak.get_financial_report_sina(sina_code, "资产负债表"),
                self._ak.get_financial_report_sina(sina_code, "现金流量表"),
            )
        except Exception as e:  # noqa: BLE001 — AkShare 爬虫端点异常不固定
            log.debug("financial_report_sina failed for %s: %s", symbol, e)
            return []

        def _by_date(df: Any) -> dict[str, dict[str, Any]]:
            if df is None or df.empty or "报告日" not in df.columns:
                return {}
            out: dict[str, dict[str, Any]] = {}
            for _, row in df.iterrows():
                key = str(row.get("报告日") or "").strip()[:8]
                if key.isdigit() and len(key) == 8:
                    out[key] = row.to_dict()
            return out

        inc_map = _by_date(income)
        bal_map = _by_date(balance)
        cf_map = _by_date(cashflow)

        periods = sorted(set(inc_map) | set(bal_map) | set(cf_map), reverse=True)
        if period_type == "annual":
            periods = [p for p in periods if p.endswith("1231")]
        periods = periods[:limit]

        snapshots: list[FinancialSnapshot] = []
        for p in periods:
            try:
                period_date = datetime.strptime(p, "%Y%m%d").date()
            except ValueError:
                continue
            inc = inc_map.get(p, {})
            bal = bal_map.get(p, {})
            cf = cf_map.get(p, {})

            # capex: Sina 返回正数(购建支出),归一成负号与 FMP / yfinance 一致
            capex_raw = _dec(cf.get("购建固定资产、无形资产和其他长期资产所支付的现金"))
            capex = -capex_raw if capex_raw is not None else None

            snapshots.append(
                FinancialSnapshot(
                    symbol=symbol,
                    period=period_date,
                    period_type=period_type,
                    revenue=_dec(inc.get("营业总收入")) or _dec(inc.get("营业收入")),
                    net_income=(
                        _dec(inc.get("归属于母公司所有者的净利润"))
                        or _dec(inc.get("净利润"))
                    ),
                    total_assets=_dec(bal.get("资产总计")),
                    total_equity=(
                        _dec(bal.get("归属于母公司股东权益合计"))
                        or _dec(bal.get("所有者权益(或股东权益)合计"))
                    ),
                    operating_cashflow=_dec(cf.get("经营活动产生的现金流量净额")),
                    capex=capex,
                )
            )
        return snapshots
