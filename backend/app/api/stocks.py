from typing import Annotated

from fastapi import APIRouter, HTTPException, Query

from app.data.providers import get_provider
from app.data.providers.base import Fundamentals, Stock
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
