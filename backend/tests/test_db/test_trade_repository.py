"""Tests for TradeRepository using in-memory SQLite."""

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from core.models import Base
from db.trade_repository import TradeRepository


@pytest_asyncio.fixture
async def session():
    """Create in-memory SQLite async session for testing."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as sess:
        yield sess

    await engine.dispose()


@pytest_asyncio.fixture
async def repo(session):
    return TradeRepository(session)


@pytest.mark.asyncio
async def test_save_and_get_order(repo):
    order = await repo.save_order(
        symbol="AAPL", side="buy", order_type="limit",
        quantity=10, price=180.0, status="filled",
        strategy_name="trend_following", filled_price=180.0,
        filled_quantity=10,
    )
    assert order.id is not None
    assert order.symbol == "AAPL"

    history = await repo.get_trade_history(limit=10)
    assert len(history) == 1
    assert history[0].symbol == "AAPL"


@pytest.mark.asyncio
async def test_update_order_status(repo):
    order = await repo.save_order(
        symbol="MSFT", side="buy", order_type="limit",
        quantity=5, price=400.0, status="pending",
    )
    updated = await repo.update_order_status(
        order.id, status="filled", filled_price=399.50, pnl=None,
    )
    assert updated.status == "filled"
    assert updated.filled_price == 399.50


@pytest.mark.asyncio
async def test_get_trade_history_filter_by_symbol(repo):
    await repo.save_order(symbol="AAPL", side="buy", order_type="market", quantity=10, price=180.0)
    await repo.save_order(symbol="MSFT", side="buy", order_type="market", quantity=5, price=400.0)
    await repo.save_order(symbol="AAPL", side="sell", order_type="market", quantity=10, price=190.0)

    aapl_trades = await repo.get_trade_history(symbol="AAPL")
    assert len(aapl_trades) == 2
    assert all(t.symbol == "AAPL" for t in aapl_trades)

    all_trades = await repo.get_trade_history()
    assert len(all_trades) == 3


@pytest.mark.asyncio
async def test_get_open_orders(repo):
    await repo.save_order(symbol="AAPL", side="buy", order_type="limit", quantity=10, price=180.0, status="pending")
    await repo.save_order(symbol="MSFT", side="buy", order_type="limit", quantity=5, price=400.0, status="filled")

    open_orders = await repo.get_open_orders()
    assert len(open_orders) == 1
    assert open_orders[0].symbol == "AAPL"


@pytest.mark.asyncio
async def test_watchlist_add_and_get(repo):
    await repo.add_to_watchlist("AAPL", name="Apple Inc.")
    await repo.add_to_watchlist("MSFT", name="Microsoft")

    wl = await repo.get_watchlist()
    assert len(wl) == 2
    symbols = [w.symbol for w in wl]
    assert "AAPL" in symbols
    assert "MSFT" in symbols


@pytest.mark.asyncio
async def test_watchlist_remove(repo):
    await repo.add_to_watchlist("AAPL")
    await repo.add_to_watchlist("MSFT")

    removed = await repo.remove_from_watchlist("AAPL")
    assert removed is True

    wl = await repo.get_watchlist(active_only=True)
    assert len(wl) == 1
    assert wl[0].symbol == "MSFT"


@pytest.mark.asyncio
async def test_watchlist_add_duplicate_reactivates(repo):
    await repo.add_to_watchlist("AAPL")
    await repo.remove_from_watchlist("AAPL")

    wl = await repo.get_watchlist(active_only=True)
    assert len(wl) == 0

    # Re-add same symbol
    await repo.add_to_watchlist("AAPL")
    wl = await repo.get_watchlist(active_only=True)
    assert len(wl) == 1


@pytest.mark.asyncio
async def test_watchlist_remove_nonexistent(repo):
    result = await repo.remove_from_watchlist("FAKE")
    assert result is False


@pytest.mark.asyncio
async def test_get_recent_trades(repo):
    """get_recent_trades returns only filled orders within time window."""
    from datetime import datetime

    # Filled order — should appear
    order = await repo.save_order(
        symbol="AAPL", side="buy", order_type="market",
        quantity=10, price=180.0, status="pending",
    )
    await repo.update_order_status(order.id, status="filled", filled_price=180.0)

    # Pending order — should NOT appear
    await repo.save_order(
        symbol="MSFT", side="buy", order_type="limit",
        quantity=5, price=400.0, status="pending",
    )

    recent = await repo.get_recent_trades(hours=24)
    assert len(recent) == 1
    assert recent[0].symbol == "AAPL"


@pytest.mark.asyncio
async def test_get_recent_trades_empty(repo):
    recent = await repo.get_recent_trades(hours=24)
    assert recent == []
