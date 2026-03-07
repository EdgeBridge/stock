"""Unit tests for PaperAdapter."""

import pytest
import pytest_asyncio

from exchange.paper_adapter import PaperAdapter


@pytest_asyncio.fixture
async def adapter():
    a = PaperAdapter(initial_balance_usd=10_000)
    await a.initialize()
    a.set_price("AAPL", 150.0)
    a.set_price("NVDA", 800.0)
    yield a
    await a.close()


@pytest.mark.asyncio
async def test_initial_balance(adapter):
    balance = await adapter.fetch_balance()
    assert balance.total == 10_000
    assert balance.available == 10_000
    assert balance.currency == "USD"


@pytest.mark.asyncio
async def test_buy_order_success(adapter):
    result = await adapter.create_buy_order("AAPL", quantity=10, price=150.0)
    assert result.status == "filled"
    assert result.filled_quantity == 10
    assert result.side == "buy"
    assert result.order_id != ""

    # Check position created
    positions = await adapter.fetch_positions()
    assert len(positions) == 1
    assert positions[0].symbol == "AAPL"
    assert positions[0].quantity == 10
    assert positions[0].avg_price == 150.0

    # Check cash reduced
    balance = await adapter.fetch_balance()
    assert balance.available < 10_000


@pytest.mark.asyncio
async def test_buy_order_insufficient_funds(adapter):
    result = await adapter.create_buy_order("NVDA", quantity=100, price=800.0)
    assert result.status == "failed"


@pytest.mark.asyncio
async def test_sell_order_success(adapter):
    await adapter.create_buy_order("AAPL", quantity=10, price=150.0)

    # Sell at higher price
    adapter.set_price("AAPL", 160.0)
    result = await adapter.create_sell_order("AAPL", quantity=5, price=160.0)
    assert result.status == "filled"
    assert result.filled_quantity == 5

    # Check partial position remains
    positions = await adapter.fetch_positions()
    assert len(positions) == 1
    assert positions[0].quantity == 5


@pytest.mark.asyncio
async def test_sell_full_position_removes_it(adapter):
    await adapter.create_buy_order("AAPL", quantity=10, price=150.0)
    await adapter.create_sell_order("AAPL", quantity=10, price=155.0)

    positions = await adapter.fetch_positions()
    assert len(positions) == 0


@pytest.mark.asyncio
async def test_sell_without_position_fails(adapter):
    result = await adapter.create_sell_order("TSLA", quantity=5)
    assert result.status == "failed"


@pytest.mark.asyncio
async def test_sell_more_than_held_fails(adapter):
    await adapter.create_buy_order("AAPL", quantity=5, price=150.0)
    result = await adapter.create_sell_order("AAPL", quantity=10)
    assert result.status == "failed"


@pytest.mark.asyncio
async def test_multiple_buys_average_price(adapter):
    await adapter.create_buy_order("AAPL", quantity=10, price=150.0)
    await adapter.create_buy_order("AAPL", quantity=10, price=160.0)

    positions = await adapter.fetch_positions()
    assert positions[0].quantity == 20
    assert positions[0].avg_price == pytest.approx(155.0, rel=0.01)


@pytest.mark.asyncio
async def test_set_price_updates_unrealized_pnl(adapter):
    await adapter.create_buy_order("AAPL", quantity=10, price=150.0)
    adapter.set_price("AAPL", 160.0)

    positions = await adapter.fetch_positions()
    assert positions[0].unrealized_pnl == pytest.approx(100.0, rel=0.01)
    assert positions[0].unrealized_pnl_pct == pytest.approx(6.67, rel=0.1)


@pytest.mark.asyncio
async def test_fetch_ticker(adapter):
    ticker = await adapter.fetch_ticker("AAPL")
    assert ticker.symbol == "AAPL"
    assert ticker.price == 150.0


@pytest.mark.asyncio
async def test_cancel_order(adapter):
    result = await adapter.create_buy_order("AAPL", quantity=10, price=150.0)
    cancelled = await adapter.cancel_order(result.order_id, "AAPL")
    assert cancelled is True


@pytest.mark.asyncio
async def test_fetch_order(adapter):
    buy_result = await adapter.create_buy_order("AAPL", quantity=10, price=150.0)
    fetched = await adapter.fetch_order(buy_result.order_id, "AAPL")
    assert fetched.status == "filled"
    assert fetched.symbol == "AAPL"


@pytest.mark.asyncio
async def test_fetch_nonexistent_order(adapter):
    result = await adapter.fetch_order("nonexistent", "AAPL")
    assert result.status == "not_found"
