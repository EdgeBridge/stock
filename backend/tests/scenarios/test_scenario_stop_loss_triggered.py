"""Scenario 2: Stop-loss triggered.

1. Buy position at $100
2. Price drops below stop-loss threshold
3. Automatic sell triggered
4. PnL negative recorded
5. Cooldown applied (no re-buy immediately)
"""

import pytest

from exchange.paper_adapter import PaperAdapter
from engine.risk_manager import RiskManager, RiskParams
from engine.order_manager import OrderManager


@pytest.mark.asyncio
async def test_stop_loss_sell():
    """Buy -> price drops -> SL triggered -> sell with negative PnL."""
    adapter = PaperAdapter(initial_balance_usd=100_000)
    await adapter.initialize()

    risk = RiskManager(params=RiskParams(default_stop_loss_pct=0.08))
    om = OrderManager(adapter=adapter, risk_manager=risk)

    # Buy at $100
    entry_price = 100.0
    adapter.set_price("TSLA", entry_price)
    order = await om.place_buy(
        symbol="TSLA", price=entry_price,
        portfolio_value=100_000, cash_available=100_000,
        current_positions=0, strategy_name="trend_following",
    )
    assert order is not None
    qty = order.quantity

    # Price drops to $91 (9% drop, above 8% SL)
    adapter.set_price("TSLA", 91.0)
    assert risk.check_stop_loss(entry_price, 91.0) is True

    # Verify unrealized PnL is negative
    positions = await adapter.fetch_positions()
    assert len(positions) == 1
    assert positions[0].unrealized_pnl < 0

    # Execute stop-loss sell
    sell = await om.place_sell(
        symbol="TSLA", quantity=qty, price=91.0,
        strategy_name="stop_loss",
    )
    assert sell is not None
    assert sell.status == "filled"

    # Position closed
    positions = await adapter.fetch_positions()
    assert len(positions) == 0

    # Balance decreased (loss)
    balance = await adapter.fetch_balance()
    assert balance.total < 100_000


@pytest.mark.asyncio
async def test_stop_loss_not_triggered():
    """Price drops but stays above SL level -> no sell."""
    risk = RiskManager(params=RiskParams(default_stop_loss_pct=0.08))

    # 5% drop: $100 -> $95, SL at $92
    assert risk.check_stop_loss(100.0, 95.0) is False
    assert risk.check_stop_loss(100.0, 93.0) is False
    assert risk.check_stop_loss(100.0, 92.0) is True  # exactly at SL


@pytest.mark.asyncio
async def test_daily_loss_limit_blocks_new_buys():
    """After hitting daily loss limit, new buys are rejected."""
    adapter = PaperAdapter(initial_balance_usd=100_000)
    await adapter.initialize()

    risk = RiskManager(params=RiskParams(daily_loss_limit_pct=0.03))
    om = OrderManager(adapter=adapter, risk_manager=risk)

    # Simulate daily loss of 4% ($4,000 on $100k)
    risk.update_daily_pnl(-4_000)

    adapter.set_price("NVDA", 800.0)
    order = await om.place_buy(
        symbol="NVDA", price=800.0,
        portfolio_value=100_000, cash_available=100_000,
        current_positions=0, strategy_name="trend_following",
    )
    # Should be rejected due to daily loss limit
    assert order is None


@pytest.mark.asyncio
async def test_daily_loss_resets():
    """After daily reset, trading resumes normally."""
    risk = RiskManager(params=RiskParams(daily_loss_limit_pct=0.03))
    risk.update_daily_pnl(-4_000)
    assert risk.daily_pnl == -4_000

    risk.reset_daily()
    assert risk.daily_pnl == 0.0

    # Now position sizing should work again
    result = risk.calculate_position_size(
        symbol="AAPL", price=180.0,
        portfolio_value=100_000, cash_available=100_000,
        current_positions=0,
    )
    assert result.allowed is True
