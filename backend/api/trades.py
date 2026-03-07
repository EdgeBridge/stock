"""Trade history API endpoints."""

from fastapi import APIRouter, Query

router = APIRouter(prefix="/trades", tags=["trades"])

# In-memory trade log (fallback when no DB)
_trade_log: list[dict] = []


@router.get("/")
async def get_trades(
    limit: int = Query(50, le=200),
    symbol: str | None = None,
):
    """Get trade history."""
    trades = _trade_log
    if symbol:
        trades = [t for t in trades if t.get("symbol") == symbol.upper()]
    return trades[-limit:]


@router.get("/summary")
async def trade_summary():
    """Get aggregated trade stats."""
    if not _trade_log:
        return {
            "total_trades": 0,
            "wins": 0,
            "losses": 0,
            "total_pnl": 0.0,
            "win_rate": 0.0,
        }

    sells = [t for t in _trade_log if t.get("side") == "SELL" and t.get("pnl") is not None]
    wins = [t for t in sells if t["pnl"] > 0]
    losses = [t for t in sells if t["pnl"] <= 0]
    total_pnl = sum(t["pnl"] for t in sells)

    return {
        "total_trades": len(_trade_log),
        "wins": len(wins),
        "losses": len(losses),
        "total_pnl": total_pnl,
        "win_rate": len(wins) / len(sells) * 100 if sells else 0.0,
    }


def record_trade(trade: dict) -> None:
    """Record a trade to the in-memory log. Called by OrderManager."""
    _trade_log.append(trade)
