"""价值筛选纯函数测试——只测 `screening.value` 里的 gate + rank 逻辑。

端点级别的编排（并发 enrich / 各市场 source）走集成测试,这里不覆盖。
"""

from decimal import Decimal

from app.screening.value import (
    GRAHAM_NUMBER_MAX,
    MARKET_CAP_MIN,
    PB_MAX,
    PE_MAX,
    ROE_MIN,
    ScreenerCandidate,
    apply_filter,
    rank,
)


def _mk(
    symbol: str,
    *,
    pe: Decimal | None = Decimal("10"),
    pb: Decimal | None = Decimal("1.5"),
    roe: Decimal | None = Decimal("0.15"),
    dv: Decimal | None = Decimal("0.02"),
    mc: Decimal | None = MARKET_CAP_MIN * 2,
) -> ScreenerCandidate:
    return ScreenerCandidate(
        symbol=symbol,
        name=f"Stock {symbol}",
        market="us",
        exchange="NYSE",
        pe=pe,
        pb=pb,
        roe=roe,
        dividend_yield=dv,
        market_cap=mc,
    )


def test_passes_all_gates_when_within_thresholds() -> None:
    rows = apply_filter([_mk("A")])
    assert len(rows) == 1
    assert rows[0].graham_number == Decimal("15")  # 10 * 1.5
    assert rows[0].roe_missing is False


def test_rejects_when_pe_exceeds_max() -> None:
    rows = apply_filter([_mk("A", pe=PE_MAX + Decimal(1))])
    assert rows == []


def test_rejects_when_pb_exceeds_max() -> None:
    rows = apply_filter([_mk("A", pb=PB_MAX + Decimal(1))])
    assert rows == []


def test_rejects_when_graham_number_exceeds_max() -> None:
    # PE=15, PB=2.5 → GN=37.5 > 30
    rows = apply_filter([_mk("A", pe=Decimal("15"), pb=Decimal("2.5"))])
    assert rows == []


def test_rejects_when_market_cap_below_min() -> None:
    rows = apply_filter([_mk("A", mc=MARKET_CAP_MIN - Decimal(1))])
    assert rows == []


def test_rejects_when_roe_below_min_if_provided() -> None:
    rows = apply_filter([_mk("A", roe=ROE_MIN - Decimal("0.01"))])
    assert rows == []


def test_accepts_with_roe_missing_flag_when_roe_is_none() -> None:
    rows = apply_filter([_mk("A", roe=None)])
    assert len(rows) == 1
    assert rows[0].roe_missing is True


def test_rejects_non_positive_pe_or_pb() -> None:
    # 亏损 / 资不抵债
    assert apply_filter([_mk("A", pe=Decimal(0))]) == []
    assert apply_filter([_mk("A", pe=Decimal(-1))]) == []
    assert apply_filter([_mk("A", pb=Decimal(0))]) == []


def test_rejects_when_required_field_is_none() -> None:
    assert apply_filter([_mk("A", pe=None)]) == []
    assert apply_filter([_mk("A", pb=None)]) == []
    assert apply_filter([_mk("A", mc=None)]) == []


def test_rank_sorts_by_graham_number_ascending() -> None:
    a = _mk("A", pe=Decimal("10"), pb=Decimal("2"))  # GN=20
    b = _mk("B", pe=Decimal("5"), pb=Decimal("1"))  # GN=5
    c = _mk("C", pe=Decimal("15"), pb=Decimal("1.5"))  # GN=22.5
    rows = rank(apply_filter([a, b, c]))
    assert [r.candidate.symbol for r in rows] == ["B", "A", "C"]
    # GN 严格升序
    assert rows[0].graham_number < rows[1].graham_number < rows[2].graham_number


def test_graham_number_bound_exactly_at_max_passes() -> None:
    # PE × PB == GRAHAM_NUMBER_MAX 应该通过(≤)
    rows = apply_filter([_mk("A", pe=Decimal("10"), pb=Decimal("3"))])  # GN=30
    assert len(rows) == 1
    assert rows[0].graham_number == GRAHAM_NUMBER_MAX
