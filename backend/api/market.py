"""Market data API endpoints."""

from fastapi import APIRouter, Query, Request

from data.market_data_service import MarketDataService
from data.stock_name_service import resolve_names

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


@router.get("/events")
async def get_market_events(request: Request, market: str = Query("US")):
    """Get event calendar data (earnings, macro, insider)."""
    if market == "KR":
        kr_macro = getattr(request.app.state, "kr_macro_calendar", None)
        if not kr_macro:
            return {"earnings": [], "macro": [], "insider": []}
        return {"earnings": [], "macro": kr_macro.to_dict(), "insider": []}

    event_svc = getattr(request.app.state, "event_calendar", None)
    if not event_svc:
        return {"earnings": [], "macro": [], "insider": [], "updated_at": None}
    return event_svc.to_dict()


@router.get("/names")
async def get_stock_names(
    symbols: str = Query(..., description="Comma-separated symbols"),
    market: str = Query("US"),
):
    """Resolve stock names for given symbols."""
    symbol_list = [s.strip() for s in symbols.split(",") if s.strip()]
    names = await resolve_names(symbol_list, market)
    return names
