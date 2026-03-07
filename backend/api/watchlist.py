"""Watchlist API endpoints."""

from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter(prefix="/watchlist", tags=["watchlist"])

# In-memory watchlist (replaced by DB in production)
_watchlist: list[str] = []


class WatchlistAdd(BaseModel):
    symbol: str


@router.get("/")
async def get_watchlist():
    """Get current watchlist."""
    return {"symbols": _watchlist}


@router.post("/")
async def add_symbol(req: WatchlistAdd):
    """Add a symbol to watchlist."""
    symbol = req.symbol.upper()
    if symbol not in _watchlist:
        _watchlist.append(symbol)
    return {"symbols": _watchlist}


@router.delete("/{symbol}")
async def remove_symbol(symbol: str):
    """Remove a symbol from watchlist."""
    symbol = symbol.upper()
    if symbol in _watchlist:
        _watchlist.remove(symbol)
    return {"symbols": _watchlist}
