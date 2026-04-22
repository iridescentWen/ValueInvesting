"""Screener API 编排测试——专注 `_cn_candidates` 新路径(全 A 股 universe + Mairui)。

不打网络、不调真实 Mairui——stub provider 的 `_mr` 属性、`list_stocks` 和
`enrich_fundamentals`。
"""

from datetime import date
from decimal import Decimal
from typing import Any

import pytest

from app.api import screener as screener_mod
from app.api.screener import _cn_candidates, _compute_screener
from app.data.providers.base import Fundamentals, Stock
from app.data.providers.cn import CnProvider


class _StubMairui:
    """只实现 _cn_candidates 要用的 get_realtime。"""

    def __init__(self, data: dict[str, dict[str, Any]]) -> None:
        self._data = data

    async def get_realtime(self, symbol: str) -> dict[str, Any]:
        return self._data.get(symbol, {})

    async def aclose(self) -> None:
        pass


def _make_provider(
    universe: list[Stock],
    mairui_data: dict[str, dict[str, Any]],
) -> CnProvider:
    """做一个 CnProvider,注入 stub Mairui + 固定 universe,enrich 直接返回原 base。"""
    provider = CnProvider(mairui_client=_StubMairui(mairui_data))  # type: ignore[arg-type]

    async def _stub_list_stocks() -> list[Stock]:
        return universe

    async def _passthrough_enrich(base: Fundamentals) -> Fundamentals:
        return base

    provider.list_stocks = _stub_list_stocks  # type: ignore[method-assign]
    provider.enrich_fundamentals = _passthrough_enrich  # type: ignore[method-assign]
    return provider


def _stock(code: str, name: str, exchange: str | None = None) -> Stock:
    return Stock(symbol=code, name=name, market="cn", exchange=exchange)


@pytest.mark.asyncio
async def test_cn_candidates_maps_mairui_fields() -> None:
    """Mairui pe / sjl / sz 分别映射到 Fundamentals.pe / pb / market_cap。"""
    provider = _make_provider(
        [_stock("600519", "贵州茅台", "SH"), _stock("600036", "招商银行", "SH")],
        {
            "600519": {"pe": 21.47, "sjl": 7.23, "sz": 1.77e12},
            "600036": {"pe": 6.5, "sjl": 1.0, "sz": 9e11},
        },
    )
    candidates = await _cn_candidates(provider)

    # 茅台 PE*PB=155 超粗筛阈值 (GRAHAM_NUMBER_MAX+20=50),被剔除;
    # 招行 PE*PB=6.5 通过
    assert {c.symbol for c in candidates} == {"600036"}
    cmb = next(c for c in candidates if c.symbol == "600036")
    assert cmb.pe == Decimal("6.5")
    assert cmb.pb == Decimal("1.0")
    assert cmb.market_cap == Decimal(str(9e11))
    assert cmb.market == "cn"
    assert cmb.exchange == "SH"
    assert cmb.name == "招商银行"


@pytest.mark.asyncio
async def test_cn_candidates_infers_exchange_when_universe_has_none() -> None:
    """universe 里 exchange 为 None 时,代码前缀推断 (600 → SH)。"""
    provider = _make_provider(
        [_stock("600036", "招商银行", exchange=None)],
        {"600036": {"pe": 6.5, "sjl": 1.0, "sz": 9e11}},
    )
    candidates = await _cn_candidates(provider)
    assert len(candidates) == 1
    assert candidates[0].exchange == "SH"


@pytest.mark.asyncio
async def test_cn_candidates_drops_missing_fields() -> None:
    """Mairui realtime 返回缺字段(老股 / 停牌)直接剔除,不抛。"""
    provider = _make_provider(
        [_stock("600519", "贵州茅台", "SH"), _stock("000001", "平安银行", "SZ")],
        {
            "600519": {"pe": 20, "sjl": 2, "sz": 1e12},
            "000001": {},  # 完全空
        },
    )
    candidates = await _cn_candidates(provider)
    assert {c.symbol for c in candidates} == {"600519"}


@pytest.mark.asyncio
async def test_cn_candidates_drops_negative_pe() -> None:
    """亏损股 PE<0 一律剔除,防止排序时排到前面。"""
    provider = _make_provider(
        [_stock("600519", "贵州茅台", "SH"), _stock("000725", "京东方A", "SZ")],
        {
            "600519": {"pe": 20, "sjl": 2, "sz": 1e12},
            "000725": {"pe": -5.0, "sjl": 1.5, "sz": 2e11},
        },
    )
    candidates = await _cn_candidates(provider)
    assert {c.symbol for c in candidates} == {"600519"}


@pytest.mark.asyncio
async def test_cn_candidates_drops_under_market_cap() -> None:
    """市值 < MARKET_CAP_MIN(50 亿)被剔除。"""
    provider = _make_provider(
        [_stock("600519", "贵州茅台", "SH"), _stock("002007", "华兰生物", "SZ")],
        {
            "600519": {"pe": 20, "sjl": 2, "sz": 1e12},
            "002007": {"pe": 10, "sjl": 1.5, "sz": 1e9},
        },
    )
    candidates = await _cn_candidates(provider)
    assert {c.symbol for c in candidates} == {"600519"}


@pytest.mark.asyncio
async def test_cn_candidates_tolerates_mairui_exception() -> None:
    """单支股票 Mairui 抛错不影响其他候选。"""

    class _ErrorMairui:
        async def get_realtime(self, symbol: str) -> dict[str, Any]:
            if symbol == "BROKEN":
                raise RuntimeError("mairui rate limit")
            return {"pe": 20, "sjl": 2, "sz": 1e12}

        async def aclose(self) -> None:
            pass

    provider = CnProvider(mairui_client=_ErrorMairui())  # type: ignore[arg-type]

    async def _stub_list_stocks() -> list[Stock]:
        return [_stock("600519", "贵州茅台", "SH"), _stock("BROKEN", "坏数据", "SH")]

    async def _passthrough_enrich(base: Fundamentals) -> Fundamentals:
        return base

    provider.list_stocks = _stub_list_stocks  # type: ignore[method-assign]
    provider.enrich_fundamentals = _passthrough_enrich  # type: ignore[method-assign]

    candidates = await _cn_candidates(provider)
    assert {c.symbol for c in candidates} == {"600519"}


@pytest.mark.asyncio
async def test_cn_candidates_returns_empty_without_mairui(monkeypatch) -> None:
    """无 Mairui client 配置时返回空 list,不抛。"""
    from app.data.providers import cn as cn_mod

    monkeypatch.setattr(cn_mod.settings, "mairui_api_key", None)
    provider = CnProvider(mairui_client=None)
    candidates = await _cn_candidates(provider)
    assert candidates == []


@pytest.mark.asyncio
async def test_compute_screener_raises_on_empty_passed(monkeypatch) -> None:
    """零候选被视作上游故障——抛异常阻止 AsyncTTLCache 存"假空"1h。

    实测:yfinance 批量 401 会让 HK coarse_passed=0,老实存空结果的话用户
    就被卡在空界面上一整个 TTL;抛异常让下次请求重新试。
    """
    async def _empty_cn_candidates(_provider: Any) -> list[Any]:
        return []

    monkeypatch.setattr(screener_mod, "_cn_candidates", _empty_cn_candidates)
    # 不走真实 get_provider——一个裸 CnProvider 够骗过 cast
    monkeypatch.setattr(
        screener_mod,
        "get_provider",
        lambda _market: CnProvider(mairui_client=None),
    )

    with pytest.raises(RuntimeError, match="0 passed rows"):
        await _compute_screener("cn")


@pytest.mark.asyncio
async def test_compute_screener_empty_does_not_poison_cache(monkeypatch) -> None:
    """抛异常后缓存是空的——下次正常返回的 compute 能顺利存进去。"""
    from decimal import Decimal

    from app.screening.value import ScreenerCandidate

    call_count = {"n": 0}

    async def _flaky_cn_candidates(_provider: Any) -> list[Any]:
        call_count["n"] += 1
        if call_count["n"] == 1:
            return []  # 上游第一次"挂"
        return [
            ScreenerCandidate(
                symbol="600036",
                name="招商银行",
                market="cn",
                exchange="SH",
                pe=Decimal("6.5"),
                pb=Decimal("1.0"),
                roe=Decimal("0.15"),
                dividend_yield=Decimal("0.04"),
                market_cap=Decimal("9e11"),
            )
        ]

    monkeypatch.setattr(screener_mod, "_cn_candidates", _flaky_cn_candidates)
    monkeypatch.setattr(
        screener_mod,
        "get_provider",
        lambda _market: CnProvider(mairui_client=None),
    )
    # 用全新 cache,避免被其他测试污染
    from app.data.cache import AsyncTTLCache
    from app.api.screener import ScreenerResult
    fresh_cache: AsyncTTLCache[list[ScreenerResult]] = AsyncTTLCache(3600)
    monkeypatch.setattr(screener_mod, "_screener_cache", fresh_cache)

    # 第一次:空 → 抛异常 → cache 里没东西
    with pytest.raises(RuntimeError):
        await fresh_cache.get_or_load("cn", lambda: _compute_screener("cn"))
    assert fresh_cache.get("cn") is None

    # 第二次:非空 → 正常存进 cache
    result = await fresh_cache.get_or_load("cn", lambda: _compute_screener("cn"))
    assert len(result) == 1
    assert fresh_cache.get("cn") is not None


@pytest.mark.asyncio
async def test_cn_candidates_enriches_all_coarse_survivors() -> None:
    """粗筛幸存者全部进 enrich——不按 Graham # 截断 top-N。

    之前版本按 PE×PB 升序只保留前 N 支,导致 Mairui realtime 对上交所
    部分股字段缺失时,板块分布严重偏 000xxx 深主板(一支上交所银行股都
    没有)。apply_filter 的最终闸门必须对所有粗筛幸存者平等生效。
    """
    provider = _make_provider(
        [
            _stock("600519", "贵州茅台", "SH"),
            _stock("600036", "招商银行", "SH"),
            _stock("601318", "中国平安", "SH"),
        ],
        {
            "600519": {"pe": 20, "sjl": 2, "sz": 1e12},    # GN=40, 粗筛 GN 上限 50,通过
            "600036": {"pe": 6.5, "sjl": 1.0, "sz": 9e11}, # GN=6.5,通过
            "601318": {"pe": 10, "sjl": 1.5, "sz": 8e11},  # GN=15,通过
        },
    )

    enrich_calls: list[str] = []
    orig_enrich = provider.enrich_fundamentals

    async def _spy_enrich(base: Fundamentals) -> Fundamentals:
        enrich_calls.append(base.symbol)
        return await orig_enrich(base)

    provider.enrich_fundamentals = _spy_enrich  # type: ignore[method-assign]

    candidates = await _cn_candidates(provider)
    # 3 支全部粗筛通过 → 3 支全部 enrich,不再有 top-N 截断
    assert set(enrich_calls) == {"600519", "600036", "601318"}
    assert len(candidates) == 3
    assert {c.symbol for c in candidates} == {"600519", "600036", "601318"}
    assert all(isinstance(date.today(), date) for _ in candidates)
