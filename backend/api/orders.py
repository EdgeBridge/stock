"""Orders API endpoint — account-scoped order/trade history from DB.

GET /orders?account_id=X&market=US|KR|ALL&limit=50&offset=0

- account_id: optional; if provided must match a configured account (→ 404 if not)
- market: "US" | "KR" | "ALL" (default None = all markets)
- limit/offset: pagination (default 50, max 200)

Reads directly from the DB via TradeRepository. Borrows the session factory
from api.trades (set by main.py lifespan via init_trades()).

Market filter is pushed down to the DB query so that limit/offset pagination
applies to the already-filtered set (not to the full mixed-market result set).
"""

import logging
from typing import Literal, Optional

from fastapi import APIRouter, Depends, Query

from api.accounts import validate_account_id_or_404
from api.trades import order_to_dict
from db.trade_repository import TradeRepository

router = APIRouter(prefix="/orders", tags=["orders"])
logger = logging.getLogger(__name__)


@router.get("/")
async def get_orders(
    account_id: Optional[str] = Depends(validate_account_id_or_404),
    market: Optional[Literal["US", "KR", "ALL"]] = None,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> list[dict]:
    """Return order history from DB, optionally filtered by account and market.

    account_id is validated against configured accounts; unknown IDs return 404.
    market filter is applied at DB level so limit/offset paginate the filtered set.
    Omitting market (or passing "ALL") returns orders for all markets.
    """
    from api.trades import _session_factory

    if not _session_factory:
        logger.warning(
            "GET /orders called but _session_factory is not initialised "
            "(init_trades() not yet called); returning empty list"
        )
        return []

    # Normalise "ALL" to None so the repository returns all markets
    db_market = market if market and market != "ALL" else None

    try:
        async with _session_factory() as session:
            repo = TradeRepository(session)
            orders = await repo.get_trade_history(
                limit=limit,
                offset=offset,
                account_id=account_id,
                market=db_market,
            )
            # Materialise to plain dicts while the session is still open.
            # SQLAlchemy async ORM objects become detached after session close;
            # accessing attributes outside the session raises MissingGreenlet
            # for any lazily-loaded column or relationship.
            return [order_to_dict(o) for o in orders]
    except Exception as e:
        logger.error("Failed to fetch orders from DB: %s", e)
        return []
