from typing import Annotated

from fastapi import APIRouter, HTTPException, Query

from app.data.providers import get_provider
from app.data.providers.base import FinancialSnapshot, Fundamentals, PeriodType, Stock
from app.models.enums import Market

router = APIRouter(prefix="/api/stocks", tags=["stocks"])


@router.get("", response_model=list[Stock])
async def list_stocks(
    market: Annotated[Market, Query(description="市场代码：cn / us")],
    limit: Annotated[int, Query(ge=1, le=500)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[Stock]:
    """按市场返回股票列表，分页。目前直接打 provider，未来接 DuckDB 缓存。"""
    provider = get_provider(market)
    stocks = await provider.list_stocks()
    return stocks[offset : offset + limit]


@router.get("/{symbol}/fundamentals", response_model=Fundamentals)
async def get_fundamentals(
    symbol: str,
    market: Annotated[Market, Query(description="市场代码：cn / us")],
) -> Fundamentals:
    provider = get_provider(market)
    data = await provider.get_fundamentals(symbol)
    if data is None:
        raise HTTPException(status_code=404, detail=f"No fundamentals for {symbol} in {market}")
    return data


@router.get("/{symbol}/financials", response_model=list[FinancialSnapshot])
async def get_financials(
    symbol: str,
    market: Annotated[Market, Query(description="市场代码：cn / us / hk")],
    period: Annotated[PeriodType, Query(description="annual / quarterly")] = "annual",
    years: Annotated[int, Query(ge=1, le=20, description="返回最近 N 期")] = 5,
) -> list[FinancialSnapshot]:
    """历史财报时序——按期倒序返回(最近在前)。

    CN 走 AkShare Sina 三表,US 走 FMP 三表,HK 走 yfinance 三表。缓慢上游
    的调用结果依赖 provider 层缓存(HK/US 有 1h TTL,CN 暂无),首次请求
    可能 3-10s。
    """
    provider = get_provider(market)
    return await provider.get_financial_snapshots(symbol, period_type=period, limit=years)
