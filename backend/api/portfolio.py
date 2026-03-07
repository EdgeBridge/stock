"""Portfolio API endpoints."""

from fastapi import APIRouter, Depends, Request

from api.dependencies import get_adapter
from exchange.base import ExchangeAdapter

router = APIRouter(prefix="/portfolio", tags=["portfolio"])


@router.get("/summary")
async def portfolio_summary(adapter: ExchangeAdapter = Depends(get_adapter)):
    """Get portfolio summary: balance + positions + PnL."""
    balance = await adapter.fetch_balance()
    positions = await adapter.fetch_positions()

    total_position_value = sum(p.current_price * p.quantity for p in positions)
    total_unrealized_pnl = sum(p.unrealized_pnl for p in positions)

    return {
        "balance": {
            "currency": balance.currency,
            "total": balance.total,
            "available": balance.available,
            "locked": balance.locked,
        },
        "positions_count": len(positions),
        "total_position_value": total_position_value,
        "total_unrealized_pnl": total_unrealized_pnl,
        "total_equity": balance.total,
    }


@router.get("/positions")
async def list_positions(adapter: ExchangeAdapter = Depends(get_adapter)):
    """List all current positions."""
    positions = await adapter.fetch_positions()
    return [
        {
            "symbol": p.symbol,
            "exchange": p.exchange,
            "quantity": p.quantity,
            "avg_price": p.avg_price,
            "current_price": p.current_price,
            "unrealized_pnl": p.unrealized_pnl,
            "unrealized_pnl_pct": p.unrealized_pnl_pct,
        }
        for p in positions
    ]


@router.get("/equity-history")
async def equity_history(request: Request, days: int = 30):
    """Get portfolio equity history for charting."""
    pm = getattr(request.app.state, "portfolio_manager", None)
    if not pm:
        return []
    return await pm.get_equity_history(days=days)
