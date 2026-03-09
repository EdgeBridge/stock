"""Market data API endpoints."""

from fastapi import APIRouter, Depends, Query, Request

from data.market_data_service import MarketDataService

router = APIRouter(prefix="/market", tags=["market"])


def _get_market_data(request, market: str = "US") -> MarketDataService:
    """Select market data service based on market parameter."""
    if market == "KR":
        return getattr(request.app.state, "kr_market_data", None) or request.app.state.market_data
    return request.app.state.market_data


@router.get("/price/{symbol}")
async def get_price(
    request: Request,
    symbol: str,
    exchange: str = Query("NASD"),
    market: str = Query("US"),
):
    """Get current price for a symbol."""
    md = _get_market_data(request, market)
    ticker = await md.get_ticker(symbol, exchange)
    return {
        "symbol": ticker.symbol,
        "price": ticker.price,
        "change_pct": ticker.change_pct,
        "volume": ticker.volume,
    }


@router.get("/chart/{symbol}")
async def get_chart(
    request: Request,
    symbol: str,
    timeframe: str = Query("1D"),
    limit: int = Query(200, ge=10, le=500),
    exchange: str = Query("NASD"),
    market: str = Query("US"),
):
    """Get OHLCV chart data."""
    md = _get_market_data(request, market)
    df = await md.get_ohlcv(symbol, timeframe, limit, exchange)
    if df.empty:
        return {"symbol": symbol, "data": []}

    # Ensure timestamp column exists (yfinance uses tz-aware DatetimeIndex)
    if "timestamp" not in df.columns and hasattr(df.index, 'date'):
        df = df.copy()
        idx = df.index
        if hasattr(idx, 'tz') and idx.tz is not None:
            idx = idx.tz_convert('UTC')
        df["timestamp"] = [int(t.timestamp()) for t in idx]

    records = df[["timestamp", "open", "high", "low", "close", "volume"]].to_dict(orient="records")
    return {"symbol": symbol, "timeframe": timeframe, "data": records}
