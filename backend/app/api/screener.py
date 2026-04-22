"""`/api/screener`：按价值投资指标跨市场筛股。

编排三件事：
1. 从每个市场拿候选股——全量名单来自 provider.list_stocks()(三市场都接了
   全量源:CN 走 Mairui `/hslt/list` ~5200 支、HK 走 AkShare Sina
   `stock_hk_spot` ~2700 支、US 走 FMP `/v3/stock-screener` 服务器端预筛
   ~5000 支)
2. 并发 enrich 候选拿完整 Fundamentals(PE/PB/MC → 粗筛 → ROE/股息率)
3. 调 `screening.value` 的纯函数跑 Graham + Buffett 闸门、排序、切前 N

并发上限 = 16(`asyncio.Semaphore`),避免上游限流。全量名单在 provider 层
有 24h TTL in-memory 缓存——冷启动慢但命中后近乎 free。

架构注意:筛选器只是"全量 universe + 具体过滤器"的一个消费者,未来加
其他策略(动量 / 小盘价值 / 质量成长)只需要换过滤器,不需要再造名单源。
"""

import asyncio
import logging
from datetime import date
from decimal import Decimal
from typing import Annotated, Any, cast

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from app.data.cache import AsyncTTLCache
from app.data.providers import get_provider
from app.data.providers.base import Fundamentals, Stock
from app.data.providers.cn import CnProvider
from app.data.providers.hk import HkProvider
from app.data.providers.us import UsProvider
from app.models.enums import Market
from app.screening.value import (
    GRAHAM_NUMBER_MAX,
    MARKET_CAP_MIN,
    PB_MAX,
    PE_MAX,
    ScreenedRow,
    ScreenerCandidate,
    apply_filter,
    rank,
)

log = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["screener"])

_ENRICH_CONCURRENCY = 16
_CN_COARSE_TOP_N = 80
_HK_COARSE_TOP_N = 80
# FMP screener 服务端预筛已经很准,5000 条足够覆盖全投资级美股
_US_CANDIDATE_LIMIT = 5000
# 粗筛阈值放得比最终阈值宽,给 ROE 闸门留余地(最终 filter 再卡一次)
_US_SCREENER_PE_MAX = float(PE_MAX) + 5
_US_SCREENER_PB_MAX = float(PB_MAX) + 1

# 三市场冷启动 30-90s,缓存整个 passed 列表(不带 limit)1h;用户按刷新 = 传
# `?refresh=true` 清缓存重算。启动时 lifespan 会 fire-and-forget 预热。
_SCREENER_TTL_SECONDS = 3600
_screener_cache: AsyncTTLCache[list["ScreenerResult"]] = AsyncTTLCache(_SCREENER_TTL_SECONDS)


class ScreenerResult(BaseModel):
    symbol: str
    name: str
    market: Market
    exchange: str | None
    pe: Decimal | None
    pb: Decimal | None
    roe: Decimal | None
    dividend_yield: Decimal | None
    market_cap: Decimal | None
    graham_number: Decimal
    roe_missing: bool


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


def _row_to_result(row: ScreenedRow) -> ScreenerResult:
    c = row.candidate
    return ScreenerResult(
        symbol=c.symbol,
        name=c.name,
        market=c.market,
        exchange=c.exchange,
        pe=c.pe,
        pb=c.pb,
        roe=c.roe,
        dividend_yield=c.dividend_yield,
        market_cap=c.market_cap,
        graham_number=row.graham_number,
        roe_missing=row.roe_missing,
    )


def _infer_cn_exchange(code: str) -> str | None:
    first = code[:1]
    if first in ("6", "9"):
        return "SH"
    if first in ("0", "3"):
        return "SZ"
    return None


# ======== 各市场的候选获取 ========


async def _cn_candidates(provider: CnProvider) -> list[ScreenerCandidate]:
    """CN: 全 A 股 universe(~5200 支)→ Mairui realtime 并发粗筛 PE/PB/MC
    → 取 Graham # 最小的 top-N → 补 ROE / 股息率。

    冷启动:5200 支 × per-stock realtime,Semaphore(16) 下约 60-90s。全量
    名单和 realtime 结果都可以挂 24h TTL,后续请求 ~无感。
    """
    mairui = provider._mr
    if mairui is None:
        log.warning("cn screener: Mairui client not configured")
        return []

    universe = await provider.list_stocks()
    log.info("cn screener: universe=%d", len(universe))

    sem = asyncio.Semaphore(_ENRICH_CONCURRENCY)

    async def fetch_coarse(
        stock: Stock,
    ) -> tuple[Stock, Decimal, Decimal, Decimal] | None:
        """单支股票粗筛:拉 Mairui realtime,过 PE/PB/市值阈值。"""
        try:
            async with sem:
                info = await mairui.get_realtime(stock.symbol)
        except Exception as e:  # noqa: BLE001 — Mairui 限流/网络抖动不固定
            log.debug("cn screener: Mairui get_realtime failed for %s: %s", stock.symbol, e)
            return None
        pe = _dec(info.get("pe"))
        pb = _dec(info.get("sjl"))
        mc = _dec(info.get("sz"))
        if pe is None or pb is None or mc is None:
            return None
        if pe <= 0 or pb <= 0:
            return None
        # 粗筛阈值比最终宽——最终 apply_filter 再卡一次
        if pe > Decimal(30) or pb > Decimal(5):
            return None
        if mc < MARKET_CAP_MIN:
            return None
        if pe * pb > GRAHAM_NUMBER_MAX + Decimal(20):
            return None
        return (stock, pe, pb, mc)

    coarse = await asyncio.gather(*[fetch_coarse(s) for s in universe])
    rows: list[tuple[Stock, Decimal, Decimal, Decimal]] = [r for r in coarse if r is not None]
    rows.sort(key=lambda x: x[1] * x[2])
    rows = rows[:_CN_COARSE_TOP_N]
    log.info("cn screener: coarse_passed=%d top_n=%d", len(coarse), len(rows))

    async def enrich_one(row: tuple[Stock, Decimal, Decimal, Decimal]) -> ScreenerCandidate:
        stock, pe, pb, mc = row
        # Mairui 返回的 dm 带 `.SZ`/`.SH` 后缀,list_stocks 里已经 _strip_suffix 过
        # 了;这里的 stock.exchange 来自 Mairui 的 jys 字段(SZ/SH/BJ),比靠代码
        # 前缀推断更准
        base = Fundamentals(
            symbol=stock.symbol,
            as_of=date.today(),
            pe=pe,
            pb=pb,
            market_cap=mc,
        )
        async with sem:
            enriched = await provider.enrich_fundamentals(base)
        # 如果 universe 没给 exchange(降级到 AkShare Sina 时)就靠代码前缀推断
        final = (
            stock
            if stock.exchange
            else Stock(
                symbol=stock.symbol, name=stock.name, market="cn",
                exchange=_infer_cn_exchange(stock.symbol),
            )
        )
        return ScreenerCandidate.from_parts(final, enriched)

    return await asyncio.gather(*[enrich_one(r) for r in rows])


async def _us_candidates(provider: UsProvider) -> list[ScreenerCandidate]:
    """US: FMP `/v3/stock-screener` 预筛 → top 200 并发补 ratios-ttm / profile。"""
    fmp = provider._fmp
    if fmp is None:
        log.warning("us screener: FMP client not configured")
        return []

    try:
        items = await fmp.get_screener(
            pe_lower_than=_US_SCREENER_PE_MAX,
            pb_lower_than=_US_SCREENER_PB_MAX,
            market_cap_more_than=float(MARKET_CAP_MIN),
            limit=_US_CANDIDATE_LIMIT,
        )
    except Exception as e:  # noqa: BLE001 — FMP 套餐问题 / 网络问题
        log.warning("us screener fallback (FMP screener failed: %s)", e)
        # 降级到 list_stocks 前 200 个
        stocks = await provider.list_stocks()
        items = [
            {
                "symbol": s.symbol,
                "companyName": s.name,
                "exchangeShortName": s.exchange,
            }
            for s in stocks[:_US_CANDIDATE_LIMIT]
        ]

    _US_EXCHANGES = {"NYSE", "NASDAQ", "AMEX"}
    sem = asyncio.Semaphore(_ENRICH_CONCURRENCY)

    async def enrich_one(item: dict[str, Any]) -> ScreenerCandidate | None:
        sym = item.get("symbol")
        if not sym:
            return None
        exch = item.get("exchangeShortName") or item.get("exchange")
        if exch and exch not in _US_EXCHANGES:
            return None
        async with sem:
            fund = await provider.get_fundamentals(sym)
        if fund is None:
            return None
        stock = Stock(
            symbol=sym,
            name=item.get("companyName") or item.get("name") or sym,
            market="us",
            exchange=exch,
        )
        return ScreenerCandidate.from_parts(stock, fund)

    results = await asyncio.gather(*[enrich_one(i) for i in items])
    return [c for c in results if c is not None]


async def _hk_candidates(provider: HkProvider) -> list[ScreenerCandidate]:
    """HK: 全港股 universe(~2700 支)→ 并发 yfinance Ticker.info 拿 PE/PB/MC →
    过最宽松粗筛 → top-N enrich ROE / 股息率。

    yfinance 对 HK 股票稳定性一般,失败直接丢弃(None → 过滤)。冷启动
    ~3-5 分钟,后续缓存命中。
    """
    universe = await provider.list_stocks()
    log.info("hk screener: universe=%d", len(universe))

    sem = asyncio.Semaphore(_ENRICH_CONCURRENCY)

    async def enrich_one(stock: Stock) -> ScreenerCandidate | None:
        async with sem:
            fund = await provider.get_fundamentals(stock.symbol)
        if fund is None:
            return None
        # 粗筛:过了才回,减轻下游 rank / apply_filter 负担
        if fund.pe is None or fund.pb is None or fund.market_cap is None:
            return None
        if fund.pe <= 0 or fund.pb <= 0:
            return None
        if fund.pe > Decimal(30) or fund.pb > Decimal(5):
            return None
        if fund.market_cap < MARKET_CAP_MIN:
            return None
        if fund.pe * fund.pb > GRAHAM_NUMBER_MAX + Decimal(20):
            return None
        return ScreenerCandidate.from_parts(stock, fund)

    results = await asyncio.gather(*[enrich_one(s) for s in universe])
    candidates = [c for c in results if c is not None]
    log.info("hk screener: coarse_passed=%d", len(candidates))
    # 按 Graham # 排序取 top-N(减少下游不必要的工作)
    candidates.sort(
        key=lambda c: (c.pe or Decimal(999)) * (c.pb or Decimal(999))
    )
    return candidates[:_HK_COARSE_TOP_N]


# ======== 端点 ========


async def _compute_screener(market: Market) -> list[ScreenerResult]:
    """实算筛选结果(完整 passed 列表,不带 limit)——缓存层和预热层都调这个。"""
    provider = get_provider(market)
    log.info("screener compute start market=%s", market)

    if market == "cn":
        candidates = await _cn_candidates(cast(CnProvider, provider))
    elif market == "us":
        candidates = await _us_candidates(cast(UsProvider, provider))
    elif market == "hk":
        candidates = await _hk_candidates(cast(HkProvider, provider))
    else:
        raise ValueError(f"Unsupported market: {market}")

    passed = rank(apply_filter(candidates))
    log.info(
        "screener compute done market=%s candidates=%d passed=%d",
        market,
        len(candidates),
        len(passed),
    )
    # 5000 支 CN / 5000 支 US / 2700 支 HK 里一个都不过闸门 → 上游大概率临时挂了
    # (实测:yfinance 批量 401 Invalid Crumb 会让 HK coarse_passed=0)。
    # 抛异常让 AsyncTTLCache 不缓存,下次请求触发重试,用户不会被卡在"假空"1h
    if not passed:
        raise RuntimeError(
            f"screener returned 0 passed rows for market={market}; "
            "treating as upstream failure, not caching"
        )
    return [_row_to_result(r) for r in passed]


async def prewarm(market: Market) -> None:
    """启动时 fire-and-forget:把结果跑完丢进缓存。异常吞,不影响 boot。"""
    try:
        await _screener_cache.get_or_load(market, lambda: _compute_screener(market))
        log.info("screener prewarm ok market=%s", market)
    except Exception as e:  # noqa: BLE001 — 上游任一家挂都不能拖死 boot
        log.warning("screener prewarm failed market=%s: %s", market, e)


@router.get("/screener", response_model=list[ScreenerResult])
async def screen(
    market: Annotated[Market, Query(description="市场代码:cn / us / hk")],
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    refresh: Annotated[bool, Query(description="true 时绕过 1h 缓存强制重算")] = False,
) -> list[ScreenerResult]:
    if market not in ("cn", "us", "hk"):
        raise HTTPException(400, f"Unsupported market: {market}")
    if refresh:
        _screener_cache.invalidate(market)
        log.info("screener cache invalidated market=%s (refresh=true)", market)
    rows = await _screener_cache.get_or_load(market, lambda: _compute_screener(market))
    return rows[:limit]
