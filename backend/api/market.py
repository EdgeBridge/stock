"""Market data API endpoints."""

from fastapi import APIRouter, Depends, Query

from api.dependencies import get_market_data
from data.market_data_service import MarketDataService

router = APIRouter(prefix="/market", tags=["market"])


@router.get("/price/{symbol}")
async def get_price(
    symbol: str,
    exchange: str = Query("NASD"),
    market_data: MarketDataService = Depends(get_market_data),
):
    """Get current price for a symbol."""
    ticker = await market_data.get_ticker(symbol, exchange)
    return {
        "symbol": ticker.symbol,
        "price": ticker.price,
        "change_pct": ticker.change_pct,
        "volume": ticker.volume,
    }


@router.get("/chart/{symbol}")
async def get_chart(
    symbol: str,
    timeframe: str = Query("1D"),
    limit: int = Query(200, ge=10, le=500),
    exchange: str = Query("NASD"),
    market_data: MarketDataService = Depends(get_market_data),
):
    """Get OHLCV chart data."""
    df = await market_data.get_ohlcv(symbol, timeframe, limit, exchange)
    if df.empty:
        return {"symbol": symbol, "data": []}

    records = df.to_dict(orient="records")
    return {"symbol": symbol, "timeframe": timeframe, "data": records}
