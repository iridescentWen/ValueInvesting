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
import time
from datetime import date
from decimal import Decimal
from typing import Annotated, Any, Literal, cast

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from app.config import settings
from app.data.cache import AsyncTTLCache
from app.data.providers import get_provider
from app.data.providers.base import Fundamentals, Stock
from app.data.providers.cn import CnProvider
from app.data.providers.hk import HkProvider
from app.data.providers.us import UsProvider
from app.models.enums import MARKETS, Market
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


# ======== prewarm 进度追踪 ========

PrewarmStatusLiteral = Literal["idle", "warming", "ready", "failed"]


class PrewarmStatus(BaseModel):
    """单个市场的 screener 预热状态。

    前端在 cache miss 期间轮询 `/api/screener/status` 拿这个,渲染
    "1247/5200 (24%)" 进度条。mutate-in-place:`_compute_screener` 标转状态、
    `ProgressTracker` 每 per-stock 完成时 tick。
    """

    status: PrewarmStatusLiteral = "idle"
    done: int = 0
    total: int = 0
    started_at: float | None = None
    error: str | None = None


class ProgressTracker:
    """per-stock 进度计数器。可选绑定一个 PrewarmStatus,tick 时同步 mutate。

    独立成类是为了单测,candidate 函数只依赖这个窄接口。
    """

    def __init__(self, state: PrewarmStatus | None = None) -> None:
        self._state = state
        self.done = 0
        self.total = 0

    def set_total(self, n: int) -> None:
        self.total = n
        if self._state is not None:
            self._state.total = n
            self._state.done = 0

    def tick(self) -> None:
        self.done += 1
        if self._state is not None:
            self._state.done = self.done


_prewarm_state: dict[Market, PrewarmStatus] = {
    cast(Market, m): PrewarmStatus() for m in MARKETS
}


def get_prewarm_state(market: Market) -> PrewarmStatus:
    return _prewarm_state[market]

_ENRICH_CONCURRENCY = 16
# FMP screener 服务端预筛已经很准,5000 条足够覆盖全投资级美股
_US_CANDIDATE_LIMIT = 5000
# 粗筛阈值放得比最终阈值宽,给 ROE 闸门留余地(最终 filter 再卡一次)
_US_SCREENER_PE_MAX = float(PE_MAX) + 5
_US_SCREENER_PB_MAX = float(PB_MAX) + 1

# 三市场冷启动 30-90s,缓存整个 passed 列表(不带 limit)1h;用户按刷新 = 传
# `?refresh=true` 清缓存重算。启动时 lifespan 会 fire-and-forget 预热。
#
# 磁盘持久化:开发期 uvicorn --reload 每次重启清空 in-memory cache,CN 冷启动
# 22 分钟。落盘后 `boot_screener_cache()` 启动时读回,跨重启无感。
_SCREENER_TTL_SECONDS = 3600
_screener_cache: AsyncTTLCache[list["ScreenerResult"]] = AsyncTTLCache(
    _SCREENER_TTL_SECONDS,
    persist_path=settings.screener_cache_path,
    serialize=lambda rows: [r.model_dump(mode="json") for r in rows],
    deserialize=lambda raw: [ScreenerResult.model_validate(d) for d in raw],
)


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


async def _cn_candidates(
    provider: CnProvider, tracker: ProgressTracker | None = None
) -> list[ScreenerCandidate]:
    """CN: 全 A 股 universe(~5200 支)→ Mairui realtime 并发粗筛 PE/PB/MC
    → 全部粗筛幸存者进 ROE / 股息率 enrich。

    冷启动:5200 支 × per-stock realtime,Semaphore(16) 下约 60-90s。全量
    名单和 realtime 结果都可以挂 24h TTL,后续请求 ~无感。

    粗筛阈值比最终 apply_filter 宽(PE≤30/PB≤5/GN≤50)——目的是在 ROE 闸门
    生效前先剔除明显不合格股,省 enrich 工作量。最终过滤仍由 apply_filter
    统一执行。这里不再按 Graham # 截断前 N,否则上交所巨头(工商银行等)会在
    Mairui realtime 局部缺字段的情况下被整板块扫掉,结果严重偏 000xxx。

    tracker 可选——传入时 per-stock 粗筛完成(不论成败)都 tick,让 /status
    能渲染 "1247/5200"。
    """
    mairui = provider._mr
    if mairui is None:
        log.warning("cn screener: Mairui client not configured")
        return []

    universe = await provider.list_stocks()
    log.info("cn screener: universe=%d", len(universe))
    if tracker is not None:
        tracker.set_total(len(universe))

    sem = asyncio.Semaphore(_ENRICH_CONCURRENCY)
    # 观测:静默失败要可见,不然下次又是"结果怎么这么少"的谜案
    errors = {"mairui": 0, "missing_fields": 0, "bad_values": 0, "coarse_drop": 0}

    async def fetch_coarse(
        stock: Stock,
    ) -> tuple[Stock, Decimal, Decimal, Decimal] | None:
        """单支股票粗筛:拉 Mairui realtime,过 PE/PB/市值阈值。"""
        try:
            async with sem:
                info = await mairui.get_realtime(stock.symbol)
        except Exception as e:  # noqa: BLE001 — Mairui 限流/网络抖动不固定
            log.debug("cn screener: Mairui get_realtime failed for %s: %s", stock.symbol, e)
            errors["mairui"] += 1
            return None
        finally:
            if tracker is not None:
                tracker.tick()
        pe = _dec(info.get("pe"))
        pb = _dec(info.get("sjl"))
        mc = _dec(info.get("sz"))
        if pe is None or pb is None or mc is None:
            errors["missing_fields"] += 1
            return None
        if pe <= 0 or pb <= 0:
            errors["bad_values"] += 1
            return None
        # 粗筛阈值比最终宽——最终 apply_filter 再卡一次
        if pe > Decimal(30) or pb > Decimal(5):
            errors["coarse_drop"] += 1
            return None
        if mc < MARKET_CAP_MIN:
            errors["coarse_drop"] += 1
            return None
        if pe * pb > GRAHAM_NUMBER_MAX + Decimal(20):
            errors["coarse_drop"] += 1
            return None
        return (stock, pe, pb, mc)

    coarse = await asyncio.gather(*[fetch_coarse(s) for s in universe])
    rows: list[tuple[Stock, Decimal, Decimal, Decimal]] = [r for r in coarse if r is not None]
    log.info(
        "cn screener: universe=%d coarse_passed=%d mairui_err=%d missing=%d bad=%d coarse_drop=%d",
        len(universe), len(rows),
        errors["mairui"], errors["missing_fields"],
        errors["bad_values"], errors["coarse_drop"],
    )

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


async def _us_candidates(
    provider: UsProvider, tracker: ProgressTracker | None = None
) -> list[ScreenerCandidate]:
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

    if tracker is not None:
        tracker.set_total(len(items))

    _US_EXCHANGES = {"NYSE", "NASDAQ", "AMEX"}
    sem = asyncio.Semaphore(_ENRICH_CONCURRENCY)

    async def enrich_one(item: dict[str, Any]) -> ScreenerCandidate | None:
        try:
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
        finally:
            if tracker is not None:
                tracker.tick()

    results = await asyncio.gather(*[enrich_one(i) for i in items])
    return [c for c in results if c is not None]


async def _hk_candidates(
    provider: HkProvider, tracker: ProgressTracker | None = None
) -> list[ScreenerCandidate]:
    """HK: 全港股 universe(~2700 支)→ 并发 yfinance Ticker.info 拿 PE/PB/MC →
    过最宽松粗筛 → top-N enrich ROE / 股息率。

    yfinance 对 HK 股票稳定性一般,失败直接丢弃(None → 过滤)。冷启动
    ~3-5 分钟,后续缓存命中。
    """
    universe = await provider.list_stocks()
    log.info("hk screener: universe=%d", len(universe))
    if tracker is not None:
        tracker.set_total(len(universe))

    sem = asyncio.Semaphore(_ENRICH_CONCURRENCY)

    async def enrich_one(stock: Stock) -> ScreenerCandidate | None:
        try:
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
        finally:
            if tracker is not None:
                tracker.tick()

    results = await asyncio.gather(*[enrich_one(s) for s in universe])
    candidates = [c for c in results if c is not None]
    log.info("hk screener: universe=%d coarse_passed=%d", len(universe), len(candidates))
    # 全部粗筛幸存者进 apply_filter,不按 Graham # 截断 top-N;yfinance 对 HK
    # 不同代号段的稳定性差异会让截断结果严重偏向某板块
    return candidates


# ======== 端点 ========


async def _compute_screener(market: Market) -> list[ScreenerResult]:
    """实算筛选结果(完整 passed 列表,不带 limit)——缓存层和预热层都调这个。

    副作用:同步 mutate `_prewarm_state[market]`:进入标 warming + 重置计数,
    成功 ready,失败 / 空结果 failed。前端通过 `/api/screener/status` 读这个。
    """
    provider = get_provider(market)
    state = _prewarm_state[market]
    state.status = "warming"
    state.done = 0
    state.total = 0
    state.error = None
    state.started_at = time.time()
    tracker = ProgressTracker(state)
    log.info("screener compute start market=%s", market)

    try:
        if market == "cn":
            candidates = await _cn_candidates(cast(CnProvider, provider), tracker=tracker)
        elif market == "us":
            candidates = await _us_candidates(cast(UsProvider, provider), tracker=tracker)
        elif market == "hk":
            candidates = await _hk_candidates(cast(HkProvider, provider), tracker=tracker)
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
    except Exception as e:
        state.status = "failed"
        state.error = str(e)
        raise
    state.status = "ready"
    return [_row_to_result(r) for r in passed]


async def prewarm(market: Market) -> None:
    """启动时 fire-and-forget:把结果跑完丢进缓存。异常吞,不影响 boot。"""
    try:
        await _screener_cache.get_or_load(market, lambda: _compute_screener(market))
        log.info("screener prewarm ok market=%s", market)
    except Exception as e:  # noqa: BLE001 — 上游任一家挂都不能拖死 boot
        log.warning("screener prewarm failed market=%s: %s", market, e)


async def boot_screener_cache() -> None:
    """lifespan 启动钩子:先从磁盘读回未过期的 screener 结果,只对 miss 的市场
    spawn prewarm。disk-hit 的市场直接标 ready,用户无等待。

    `prewarm` 内部用 `get_or_load` 的 per-key 锁去重,所以即便磁盘条目刚好在
    这里被并发的真实请求触发也不会 double-fire。
    """
    _screener_cache.load_from_disk()
    for m in MARKETS:
        market = cast(Market, m)
        if _screener_cache.get(market) is not None:
            _prewarm_state[market].status = "ready"
            log.info("screener cache hit from disk market=%s", market)
        else:
            asyncio.create_task(prewarm(market))


@router.get("/screener/status", response_model=dict[str, PrewarmStatus])
async def screener_status() -> dict[str, PrewarmStatus]:
    """三市场 prewarm 进度,前端在 warming 期间每 2s 轮询这里渲染进度条。"""
    return {m: _prewarm_state[cast(Market, m)] for m in MARKETS}


@router.get("/screener")
async def screen(
    market: Annotated[Market, Query(description="市场代码:cn / us / hk")],
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    refresh: Annotated[bool, Query(description="true 时绕过 1h 缓存强制重算")] = False,
) -> Any:
    """cache hit → 200 + rows;cache miss → 202 + 进度 JSON,后台 spawn prewarm。

    refresh=true 清 cache、重置状态,然后照常走 202 路径——CN 冷启动 22 分钟,
    阻塞一个 http 请求不现实。前端轮询 /status 拿进度,ready 后再拉一次 /screener。
    """
    if market not in ("cn", "us", "hk"):
        raise HTTPException(400, f"Unsupported market: {market}")

    state = _prewarm_state[market]
    # 关键:warming 中的 refresh 必须是 no-op。如果此时重置 state 再 spawn 新
    # prewarm,老 prewarm 的 tracker 还绑着这个 state,继续 tick done;而 total
    # 被重置回 0 → 前端收到 "done=4000, total=0" 的分裂态,进度条卡死在"预热
    # 上游"。正在跑的 prewarm 本身就是拉最新数据,refresh 语义已经被它实现。
    if refresh and state.status != "warming":
        _screener_cache.invalidate(market)
        state.status = "idle"
        state.done = 0
        state.total = 0
        state.error = None
        log.info("screener cache invalidated market=%s (refresh=true)", market)
    elif not refresh:
        cached = _screener_cache.get(market)
        if cached is not None:
            return cached[:limit]

    # cache miss / 主动刷新:立即回 202,后台保证有一个 prewarm 在跑。
    # loader 由 AsyncTTLCache 的 per-key 锁去重,不会 double-fire。
    if state.status != "warming":
        asyncio.create_task(prewarm(market))
    return JSONResponse(status_code=202, content=state.model_dump())
