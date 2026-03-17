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
        symbol="AAPL",
        side="buy",
        order_type="limit",
        quantity=10,
        price=180.0,
        status="filled",
        strategy_name="trend_following",
        filled_price=180.0,
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
        symbol="MSFT",
        side="buy",
        order_type="limit",
        quantity=5,
        price=400.0,
        status="pending",
    )
    updated = await repo.update_order_status(
        order.id,
        status="filled",
        filled_price=399.50,
        pnl=None,
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
    await repo.save_order(
        symbol="AAPL", side="buy", order_type="limit", quantity=10, price=180.0, status="pending"
    )
    await repo.save_order(
        symbol="MSFT", side="buy", order_type="limit", quantity=5, price=400.0, status="filled"
    )

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
        symbol="AAPL",
        side="buy",
        order_type="market",
        quantity=10,
        price=180.0,
        status="pending",
    )
    await repo.update_order_status(order.id, status="filled", filled_price=180.0)

    # Pending order — should NOT appear
    await repo.save_order(
        symbol="MSFT",
        side="buy",
        order_type="limit",
        quantity=5,
        price=400.0,
        status="pending",
    )

    recent = await repo.get_recent_trades(hours=24)
    assert len(recent) == 1
    assert recent[0].symbol == "AAPL"


@pytest.mark.asyncio
async def test_get_recent_trades_empty(repo):
    recent = await repo.get_recent_trades(hours=24)
    assert recent == []


@pytest.mark.asyncio
async def test_watchlist_market_filter(repo):
    """Watchlist can be filtered by market."""
    await repo.add_to_watchlist("AAPL", market="US")
    await repo.add_to_watchlist("005930", exchange="KRX", market="KR")
    await repo.add_to_watchlist("MSFT", market="US")

    all_wl = await repo.get_watchlist()
    assert len(all_wl) == 3

    us_wl = await repo.get_watchlist(market="US")
    assert len(us_wl) == 2
    assert {w.symbol for w in us_wl} == {"AAPL", "MSFT"}

    kr_wl = await repo.get_watchlist(market="KR")
    assert len(kr_wl) == 1
    assert kr_wl[0].symbol == "005930"


@pytest.mark.asyncio
async def test_watchlist_same_symbol_different_markets(repo):
    """Same symbol code can exist in US and KR markets."""
    await repo.add_to_watchlist("TEST01", market="US")
    await repo.add_to_watchlist("TEST01", exchange="KRX", market="KR")

    all_wl = await repo.get_watchlist()
    assert len(all_wl) == 2

    us_wl = await repo.get_watchlist(market="US")
    assert len(us_wl) == 1
    assert us_wl[0].market == "US"

    kr_wl = await repo.get_watchlist(market="KR")
    assert len(kr_wl) == 1
    assert kr_wl[0].market == "KR"


@pytest.mark.asyncio
async def test_watchlist_remove_with_market(repo):
    """Remove operates within correct market scope."""
    await repo.add_to_watchlist("AAPL", market="US")
    await repo.add_to_watchlist("005930", exchange="KRX", market="KR")

    # Remove from KR market only
    await repo.remove_from_watchlist("005930", market="KR")

    us_wl = await repo.get_watchlist(market="US")
    assert len(us_wl) == 1  # US untouched

    kr_wl = await repo.get_watchlist(market="KR")
    assert len(kr_wl) == 0


@pytest.mark.asyncio
async def test_watchlist_add_kr_with_market(repo):
    """KR stocks added with correct market and exchange."""
    item = await repo.add_to_watchlist(
        "005930",
        exchange="KRX",
        market="KR",
        source="scanner",
    )
    assert item.market == "KR"
    assert item.exchange == "KRX"
    assert item.source == "scanner"


# --- Paper/Live order separation (STOCK-6) ---


@pytest.mark.asyncio
async def test_save_order_with_is_paper(repo):
    """Paper orders are saved with is_paper=True."""
    paper = await repo.save_order(
        symbol="AAPL",
        side="buy",
        order_type="market",
        quantity=10,
        price=150.0,
        status="filled",
        is_paper=True,
    )
    assert paper.is_paper is True

    live = await repo.save_order(
        symbol="MSFT",
        side="buy",
        order_type="limit",
        quantity=5,
        price=400.0,
        status="filled",
        is_paper=False,
    )
    assert live.is_paper is False


@pytest.mark.asyncio
async def test_save_order_is_paper_default_false(repo):
    """Orders default to is_paper=False (live)."""
    order = await repo.save_order(
        symbol="AAPL",
        side="buy",
        order_type="market",
        quantity=10,
        price=150.0,
    )
    assert order.is_paper is False


@pytest.mark.asyncio
async def test_get_trade_history_exclude_paper(repo):
    """get_trade_history with exclude_paper=True filters out paper orders."""
    await repo.save_order(
        symbol="AAPL",
        side="buy",
        order_type="market",
        quantity=10,
        price=150.0,
        is_paper=True,
    )
    await repo.save_order(
        symbol="MSFT",
        side="buy",
        order_type="market",
        quantity=5,
        price=400.0,
        is_paper=False,
    )
    await repo.save_order(
        symbol="GOOGL",
        side="buy",
        order_type="market",
        quantity=3,
        price=170.0,
        is_paper=False,
    )

    # Without filter: all 3
    all_trades = await repo.get_trade_history()
    assert len(all_trades) == 3

    # With filter: only live (2)
    live_trades = await repo.get_trade_history(exclude_paper=True)
    assert len(live_trades) == 2
    assert all(not t.is_paper for t in live_trades)


@pytest.mark.asyncio
async def test_get_open_orders_exclude_paper(repo):
    """get_open_orders with exclude_paper=True filters out paper orders."""
    await repo.save_order(
        symbol="AAPL",
        side="buy",
        order_type="limit",
        quantity=10,
        price=150.0,
        status="pending",
        is_paper=True,
    )
    await repo.save_order(
        symbol="MSFT",
        side="buy",
        order_type="limit",
        quantity=5,
        price=400.0,
        status="pending",
        is_paper=False,
    )

    # Without filter: both
    all_open = await repo.get_open_orders()
    assert len(all_open) == 2

    # With filter: only live
    live_open = await repo.get_open_orders(exclude_paper=True)
    assert len(live_open) == 1
    assert live_open[0].symbol == "MSFT"


@pytest.mark.asyncio
async def test_get_recent_trades_exclude_paper(repo):
    """get_recent_trades with exclude_paper=True filters out paper orders."""
    # Paper filled order
    paper = await repo.save_order(
        symbol="AAPL",
        side="buy",
        order_type="market",
        quantity=10,
        price=150.0,
        status="pending",
        is_paper=True,
    )
    await repo.update_order_status(paper.id, "filled", filled_price=150.0)

    # Live filled order
    live = await repo.save_order(
        symbol="MSFT",
        side="buy",
        order_type="market",
        quantity=5,
        price=400.0,
        status="pending",
        is_paper=False,
    )
    await repo.update_order_status(live.id, "filled", filled_price=400.0)

    # Without filter: both
    all_recent = await repo.get_recent_trades(hours=24)
    assert len(all_recent) == 2

    # With filter: only live
    live_recent = await repo.get_recent_trades(hours=24, exclude_paper=True)
    assert len(live_recent) == 1
    assert live_recent[0].symbol == "MSFT"
