"""价值投资筛选：Graham 防御型 + Buffett 质量闸门。

纯函数 + 常量阈值，不碰 HTTP、不碰 DB。端点只做编排，所有判定逻辑走这里。

设计依据：Graham《聪明的投资者》第 14 章防御型投资者标准 + Buffett 对 ROE 的
长期强调。阈值相对 Graham 原版放宽（PE 15→20 / PB 1.5→3 / GN 22.5→30 /
ROE 15%→10%），以适配当代市场和小样本的筛选池。
"""

from dataclasses import dataclass
from decimal import Decimal

from app.data.providers.base import Fundamentals, Stock
from app.models.enums import Market

# ===== 阈值 =====
PE_MAX: Decimal = Decimal("20")
PB_MAX: Decimal = Decimal("3")
GRAHAM_NUMBER_MAX: Decimal = Decimal("30")  # PE × PB
ROE_MIN: Decimal = Decimal("0.10")  # 10% 小数形式
MARKET_CAP_MIN: Decimal = Decimal("5000000000")  # 50 亿本币/美元


@dataclass(frozen=True)
class ScreenerCandidate:
    """截屏时刻的候选股票快照（Stock meta + Fundamentals 合并）。"""

    symbol: str
    name: str
    market: Market
    exchange: str | None
    pe: Decimal | None
    pb: Decimal | None
    roe: Decimal | None
    dividend_yield: Decimal | None
    market_cap: Decimal | None

    @classmethod
    def from_parts(cls, stock: Stock, fund: Fundamentals) -> "ScreenerCandidate":
        return cls(
            symbol=stock.symbol,
            name=stock.name,
            market=stock.market,
            exchange=stock.exchange,
            pe=fund.pe,
            pb=fund.pb,
            roe=fund.roe,
            dividend_yield=fund.dividend_yield,
            market_cap=fund.market_cap,
        )


@dataclass(frozen=True)
class ScreenedRow:
    """通过筛选的行——附加派生字段（Graham Number + ROE 缺失标志）。"""

    candidate: ScreenerCandidate
    graham_number: Decimal
    roe_missing: bool


def passes_cheapness(c: ScreenerCandidate) -> bool:
    """PE / PB / Graham Number 三重便宜闸门。PE<=0 或 PB<=0 直接剔除（亏损 / 资不抵债）。"""
    if c.pe is None or c.pb is None:
        return False
    if c.pe <= 0 or c.pb <= 0:
        return False
    if c.pe > PE_MAX or c.pb > PB_MAX:
        return False
    return c.pe * c.pb <= GRAHAM_NUMBER_MAX


def passes_quality(c: ScreenerCandidate) -> bool:
    """ROE 质量闸门。ROE 缺数据时软放行（返回 True，交给调用方打 roe_missing 标）。"""
    if c.roe is None:
        return True
    return c.roe >= ROE_MIN


def passes_size(c: ScreenerCandidate) -> bool:
    if c.market_cap is None:
        return False
    return c.market_cap >= MARKET_CAP_MIN


def apply_filter(candidates: list[ScreenerCandidate]) -> list[ScreenedRow]:
    """跑完三个闸门，附加 graham_number + roe_missing，返回通过的行。"""
    out: list[ScreenedRow] = []
    for c in candidates:
        if not passes_cheapness(c):
            continue
        if not passes_size(c):
            continue
        if not passes_quality(c):
            continue
        # cheapness 已经验过 pe、pb 非 None 且为正
        assert c.pe is not None and c.pb is not None
        out.append(
            ScreenedRow(
                candidate=c,
                graham_number=c.pe * c.pb,
                roe_missing=c.roe is None,
            )
        )
    return out


def rank(rows: list[ScreenedRow]) -> list[ScreenedRow]:
    """按 Graham Number 升序（越便宜越靠前）。"""
    return sorted(rows, key=lambda r: r.graham_number)
