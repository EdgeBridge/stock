"""Portfolio API endpoints."""

from fastapi import APIRouter, Request

from data.stock_name_service import get_name, resolve_names

router = APIRouter(prefix="/portfolio", tags=["portfolio"])


@router.get("/summary")
async def portfolio_summary(request: Request, market: str = "ALL"):
    """Get portfolio summary: balance + positions + PnL.

    market=ALL returns unified view (KRW primary + USD positions).
    market=US or market=KR returns single-market view.
    """
    if market == "ALL":
        return await _combined_summary(request)

    md = _get_market_data(request, market)
    if not md:
        return {"error": f"Market {market} not configured"}

    balance = await md.get_balance()
    positions = await md.get_positions()

    total_position_value = sum(p.current_price * p.quantity for p in positions)
    total_unrealized_pnl = sum(p.unrealized_pnl for p in positions)

    return {
        "market": market,
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


async def _combined_summary(request: Request) -> dict:
    """Build unified summary from both US and KR adapters."""
    us_md = getattr(request.app.state, "market_data", None)
    kr_md = getattr(request.app.state, "kr_market_data", None)

    kr_balance = None
    us_balance = None
    kr_positions = []
    us_positions = []

    if kr_md:
        try:
            kr_balance = await kr_md.get_balance()
            kr_positions = await kr_md.get_positions()
        except Exception:
            pass
    if us_md:
        try:
            us_balance = await us_md.get_balance()
            us_positions = await us_md.get_positions()
        except Exception:
            pass

    # KRW is the base currency (single account)
    krw_total = kr_balance.total if kr_balance else 0
    krw_available = kr_balance.available if kr_balance else 0
    usd_total = us_balance.total if us_balance else 0
    usd_available = us_balance.available if us_balance else 0

    all_positions = kr_positions + us_positions
    total_unrealized_pnl_krw = sum(p.unrealized_pnl for p in kr_positions)
    total_unrealized_pnl_usd = sum(p.unrealized_pnl for p in us_positions)

    return {
        "market": "ALL",
        "balance": {
            "currency": "KRW",
            "total": krw_total,
            "available": krw_available,
        },
        "usd_balance": {
            "total": usd_total,
            "available": usd_available,
        },
        "positions_count": len(all_positions),
        "total_unrealized_pnl": total_unrealized_pnl_krw,
        "total_unrealized_pnl_usd": total_unrealized_pnl_usd,
        "total_equity": krw_total,
    }


@router.get("/positions")
async def list_positions(request: Request, market: str = "ALL"):
    """List all current positions. market=ALL returns both US and KR."""
    if market == "ALL":
        results = []
        for m in ("US", "KR"):
            md = _get_market_data(request, m)
            if not md:
                continue
            try:
                positions = await md.get_positions()
                results.extend(await _enrich_positions(positions, m, request))
            except Exception:
                continue
        return results

    md = _get_market_data(request, market)
    if not md:
        return []

    positions = await md.get_positions()
    return await _enrich_positions(positions, market, request)


async def _enrich_positions(positions, market: str, request: Request) -> list[dict]:
    """Build position dicts with names and SL/TP info from position tracker."""
    # Resolve missing names in background
    unknown = [p.symbol for p in positions if not get_name(p.symbol, market)]
    if unknown:
        try:
            await resolve_names(unknown, market)
        except Exception:
            pass

    # Get tracked position info (SL/TP/trailing stop)
    tracker = _get_position_tracker(request, market)
    tracked_map = {}
    if tracker:
        for t in tracker.get_status():
            tracked_map[t["symbol"]] = t

    results = []
    for p in positions:
        entry = {
            "symbol": p.symbol,
            "name": get_name(p.symbol, market) or "",
            "exchange": p.exchange,
            "quantity": p.quantity,
            "avg_price": p.avg_price,
            "current_price": p.current_price,
            "unrealized_pnl": p.unrealized_pnl,
            "unrealized_pnl_pct": p.unrealized_pnl_pct,
            "market": market,
        }
        # Add SL/TP tracking info if available
        tracked = tracked_map.get(p.symbol)
        if tracked:
            entry["stop_loss_pct"] = tracked.get("stop_loss_pct")
            entry["take_profit_pct"] = tracked.get("take_profit_pct")
            entry["highest_price"] = tracked.get("highest_price")
            entry["trailing_active"] = tracked.get("trailing_active", False)
        results.append(entry)
    return results


@router.get("/equity-history")
async def equity_history(request: Request, days: int = 30, market: str = "US"):
    """Get portfolio equity history for charting."""
    if market == "KR":
        pm = getattr(request.app.state, "kr_portfolio_manager", None)
    else:
        pm = getattr(request.app.state, "portfolio_manager", None)
    if not pm:
        return []
    return await pm.get_equity_history(days=days)


def _get_market_data(request: Request, market: str = "US"):
    """Get market data service for the specified market."""
    if market == "KR":
        return getattr(request.app.state, "kr_market_data", None)
    return getattr(request.app.state, "market_data", None)


def _get_position_tracker(request: Request, market: str = "US"):
    """Get position tracker for the specified market."""
    if market == "KR":
        return getattr(request.app.state, "kr_position_tracker", None)
    return getattr(request.app.state, "position_tracker", None)
