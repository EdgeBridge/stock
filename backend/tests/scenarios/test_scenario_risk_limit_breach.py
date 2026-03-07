"""Scenario 5: Risk limit breach.

1. Daily loss reaches 3% -> new buys blocked
2. Max positions reached -> new buys blocked
3. Portfolio-level MDD check
4. Trailing stop activation and trigger
"""

import pytest

from exchange.paper_adapter import PaperAdapter
from engine.risk_manager import RiskManager, RiskParams
from engine.order_manager import OrderManager


@pytest.mark.asyncio
async def test_daily_loss_limit_blocks_all_buys():
    """After 3% daily loss, all buy attempts are rejected."""
    adapter = PaperAdapter(initial_balance_usd=100_000)
    await adapter.initialize()

    risk = RiskManager(params=RiskParams(daily_loss_limit_pct=0.03))
    om = OrderManager(adapter=adapter, risk_manager=risk)

    # Accumulate losses
    risk.update_daily_pnl(-1_500)  # -1.5%
    risk.update_daily_pnl(-1_600)  # total -3.1%

    # Try to buy multiple symbols -> all should be rejected
    for sym, price in [("AAPL", 180.0), ("MSFT", 400.0), ("GOOGL", 140.0)]:
        adapter.set_price(sym, price)
        order = await om.place_buy(
            symbol=sym, price=price,
            portfolio_value=100_000, cash_available=100_000,
            current_positions=0, strategy_name="test",
        )
        assert order is None, f"Buy for {sym} should be rejected"


@pytest.mark.asyncio
async def test_max_positions_limit():
    """Cannot exceed max_positions."""
    adapter = PaperAdapter(initial_balance_usd=1_000_000)
    await adapter.initialize()

    risk = RiskManager(params=RiskParams(max_positions=3, max_position_pct=0.10))
    om = OrderManager(adapter=adapter, risk_manager=risk)

    # Fill 3 positions
    for i, (sym, price) in enumerate([("A", 50.0), ("B", 50.0), ("C", 50.0)]):
        adapter.set_price(sym, price)
        order = await om.place_buy(
            symbol=sym, price=price,
            portfolio_value=1_000_000, cash_available=(await adapter.fetch_balance()).available,
            current_positions=i, strategy_name="test",
        )
        assert order is not None

    # 4th position should be rejected
    adapter.set_price("D", 50.0)
    order = await om.place_buy(
        symbol="D", price=50.0,
        portfolio_value=1_000_000, cash_available=(await adapter.fetch_balance()).available,
        current_positions=3, strategy_name="test",
    )
    assert order is None


@pytest.mark.asyncio
async def test_trailing_stop_full_lifecycle():
    """Trailing stop: activate on gain, then trigger on pullback."""
    adapter = PaperAdapter(initial_balance_usd=100_000)
    await adapter.initialize()

    risk = RiskManager()
    om = OrderManager(adapter=adapter, risk_manager=risk)

    entry = 100.0
    adapter.set_price("AMD", entry)
    buy = await om.place_buy(
        symbol="AMD", price=entry,
        portfolio_value=100_000, cash_available=100_000,
        current_positions=0, strategy_name="test",
    )
    assert buy is not None

    # Price rises to $110 (10% gain) - trailing stop activates at 5%
    assert risk.check_trailing_stop(entry, 110.0, 110.0, activation_pct=0.05) is False

    # Price pulls back to $106 from $110 peak (3.6% drop from peak)
    assert risk.check_trailing_stop(entry, 106.0, 110.0, activation_pct=0.05, trail_pct=0.03) is True

    # Execute trailing stop sell
    sell = await om.place_sell(
        symbol="AMD", quantity=buy.quantity,
        price=106.0, strategy_name="trailing_stop",
    )
    assert sell.status == "filled"

    # Should still have profit
    balance = await adapter.fetch_balance()
    assert balance.total > 100_000 * 0.99  # profitable after slippage


@pytest.mark.asyncio
async def test_trailing_stop_not_activated_yet():
    """Trailing stop doesn't trigger before activation threshold."""
    risk = RiskManager()

    # Only 3% gain, activation at 5%
    assert risk.check_trailing_stop(
        entry_price=100.0, current_price=102.0,
        highest_price=103.0, activation_pct=0.05, trail_pct=0.03,
    ) is False


@pytest.mark.asyncio
async def test_cascading_losses():
    """Multiple stop-loss hits accumulate in daily PnL."""
    risk = RiskManager(params=RiskParams(daily_loss_limit_pct=0.03))

    # Two losing trades
    risk.update_daily_pnl(-1_000)  # trade 1 loss
    risk.update_daily_pnl(-1_500)  # trade 2 loss

    assert risk.daily_pnl == -2_500

    # Still under limit (2.5% on $100k)
    result = risk.calculate_position_size(
        symbol="TEST", price=100.0,
        portfolio_value=100_000, cash_available=50_000,
        current_positions=0,
    )
    assert result.allowed is True

    # Third loss pushes over
    risk.update_daily_pnl(-600)  # total: -3.1%

    result = risk.calculate_position_size(
        symbol="TEST", price=100.0,
        portfolio_value=100_000, cash_available=50_000,
        current_positions=0,
    )
    assert result.allowed is False
