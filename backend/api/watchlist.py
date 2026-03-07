"""Watchlist API endpoints (DB-backed)."""

from fastapi import APIRouter
from pydantic import BaseModel

from db.session import get_session_factory
from db.trade_repository import TradeRepository

router = APIRouter(prefix="/watchlist", tags=["watchlist"])


class WatchlistAdd(BaseModel):
    symbol: str
    exchange: str = "NASD"


async def _get_symbols() -> list[dict]:
    """Get active watchlist from DB."""
    factory = get_session_factory()
    async with factory() as session:
        repo = TradeRepository(session)
        items = await repo.get_watchlist(active_only=True)
        return [
            {
                "symbol": w.symbol,
                "exchange": w.exchange,
                "name": w.name,
                "sector": w.sector,
                "source": w.source,
                "added_at": w.added_at.isoformat() if w.added_at else None,
            }
            for w in items
        ]


@router.get("/")
async def get_watchlist():
    """Get current watchlist."""
    items = await _get_symbols()
    return {
        "symbols": [w["symbol"] for w in items],
        "items": items,
    }


@router.post("/")
async def add_symbol(req: WatchlistAdd):
    """Add a symbol to watchlist."""
    symbol = req.symbol.upper()
    factory = get_session_factory()
    async with factory() as session:
        repo = TradeRepository(session)
        await repo.add_to_watchlist(symbol=symbol, exchange=req.exchange)
    items = await _get_symbols()
    return {
        "symbols": [w["symbol"] for w in items],
        "items": items,
    }


@router.delete("/{symbol}")
async def remove_symbol(symbol: str):
    """Remove a symbol from watchlist."""
    symbol = symbol.upper()
    factory = get_session_factory()
    async with factory() as session:
        repo = TradeRepository(session)
        await repo.remove_from_watchlist(symbol)
    items = await _get_symbols()
    return {
        "symbols": [w["symbol"] for w in items],
        "items": items,
    }
