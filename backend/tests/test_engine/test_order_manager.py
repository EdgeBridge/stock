"""Tests for Order Manager."""

from unittest.mock import AsyncMock

import pytest

from engine.order_manager import OrderManager, ManagedOrder
from engine.risk_manager import RiskManager, RiskParams
from exchange.base import OrderResult


@pytest.fixture
def mock_adapter():
    adapter = AsyncMock()
    adapter.create_buy_order = AsyncMock(return_value=OrderResult(
        order_id="ORD001", symbol="AAPL", side="BUY",
        order_type="limit", quantity=10, price=150.0,
        filled_quantity=10, filled_price=150.0, status="filled",
    ))
    adapter.create_sell_order = AsyncMock(return_value=OrderResult(
        order_id="ORD002", symbol="AAPL", side="SELL",
        order_type="limit", quantity=10, price=160.0,
        filled_quantity=10, filled_price=160.0, status="filled",
    ))
    adapter.cancel_order = AsyncMock(return_value=True)
    adapter.fetch_order = AsyncMock(return_value=OrderResult(
        order_id="ORD001", symbol="AAPL", side="BUY",
        order_type="limit", quantity=10, price=150.0,
        status="filled", filled_price=150.0, filled_quantity=10,
    ))
    return adapter


@pytest.fixture
def risk_manager():
    return RiskManager(RiskParams(max_position_pct=0.10, max_positions=20))


@pytest.fixture
def order_manager(mock_adapter, risk_manager):
    return OrderManager(adapter=mock_adapter, risk_manager=risk_manager)


class TestOrderManager:
    async def test_place_buy_success(self, order_manager, mock_adapter):
        order = await order_manager.place_buy(
            symbol="AAPL", price=150.0,
            portfolio_value=100_000, cash_available=50_000,
            current_positions=0, strategy_name="trend_following",
        )
        assert order is not None
        assert order.order_id == "ORD001"
        assert order.side == "BUY"
        assert order.strategy_name == "trend_following"
        mock_adapter.create_buy_order.assert_called_once()

    async def test_place_buy_rejected_by_risk(self, mock_adapter):
        rm = RiskManager(RiskParams(max_positions=0))
        om = OrderManager(adapter=mock_adapter, risk_manager=rm)
        order = await om.place_buy(
            symbol="AAPL", price=150.0,
            portfolio_value=100_000, cash_available=50_000,
            current_positions=0, strategy_name="test",
        )
        assert order is None
        mock_adapter.create_buy_order.assert_not_called()

    async def test_place_sell_success(self, order_manager, mock_adapter):
        order = await order_manager.place_sell(
            symbol="AAPL", quantity=10, price=160.0,
            strategy_name="trend_following",
        )
        assert order is not None
        assert order.order_id == "ORD002"
        assert order.side == "SELL"

    async def test_cancel_order(self, order_manager, mock_adapter):
        # Place then cancel
        await order_manager.place_buy(
            symbol="AAPL", price=150.0,
            portfolio_value=100_000, cash_available=50_000,
            current_positions=0, strategy_name="test",
        )
        success = await order_manager.cancel("ORD001", "AAPL")
        assert success is True

    async def test_sync_order_status(self, order_manager):
        await order_manager.place_buy(
            symbol="AAPL", price=150.0,
            portfolio_value=100_000, cash_available=50_000,
            current_positions=0, strategy_name="test",
        )
        managed = await order_manager.sync_order_status("ORD001", "AAPL")
        assert managed is not None
        assert managed.status == "filled"

    async def test_active_orders_tracked(self, order_manager):
        await order_manager.place_buy(
            symbol="AAPL", price=150.0,
            portfolio_value=100_000, cash_available=50_000,
            current_positions=0, strategy_name="test",
        )
        assert "ORD001" in order_manager.active_orders

    async def test_clear_completed(self, order_manager):
        await order_manager.place_buy(
            symbol="AAPL", price=150.0,
            portfolio_value=100_000, cash_available=50_000,
            current_positions=0, strategy_name="test",
        )
        order_manager.clear_completed()
        assert len(order_manager.active_orders) == 0  # Status was "filled"

    async def test_place_buy_adapter_error(self, order_manager, mock_adapter):
        mock_adapter.create_buy_order.side_effect = Exception("Network error")
        order = await order_manager.place_buy(
            symbol="AAPL", price=150.0,
            portfolio_value=100_000, cash_available=50_000,
            current_positions=0, strategy_name="test",
        )
        assert order is None

    async def test_place_sell_adapter_error(self, order_manager, mock_adapter):
        mock_adapter.create_sell_order.side_effect = Exception("Network error")
        order = await order_manager.place_sell(
            symbol="AAPL", quantity=10, price=160.0,
        )
        assert order is None


class TestDuplicateOrderPrevention:
    """Tests for signal deduplication."""

    async def test_has_pending_order_false_when_empty(self, order_manager):
        assert order_manager.has_pending_order("AAPL") is False

    async def test_has_pending_order_true_for_pending(self, mock_adapter, risk_manager):
        mock_adapter.create_buy_order = AsyncMock(return_value=OrderResult(
            order_id="ORD001", symbol="AAPL", side="BUY",
            order_type="limit", quantity=10, price=150.0,
            filled_quantity=0, filled_price=None, status="pending",
        ))
        om = OrderManager(adapter=mock_adapter, risk_manager=risk_manager)
        await om.place_buy(
            symbol="AAPL", price=150.0,
            portfolio_value=100_000, cash_available=50_000,
            current_positions=0, strategy_name="test",
        )
        assert om.has_pending_order("AAPL") is True
        assert om.has_pending_order("AAPL", "BUY") is True
        assert om.has_pending_order("AAPL", "SELL") is False

    async def test_duplicate_buy_blocked(self, mock_adapter, risk_manager):
        """Second buy for same symbol is blocked when first is pending."""
        mock_adapter.create_buy_order = AsyncMock(return_value=OrderResult(
            order_id="ORD001", symbol="AAPL", side="BUY",
            order_type="limit", quantity=10, price=150.0,
            filled_quantity=0, filled_price=None, status="pending",
        ))
        om = OrderManager(adapter=mock_adapter, risk_manager=risk_manager)

        # First buy succeeds
        first = await om.place_buy(
            symbol="AAPL", price=150.0,
            portfolio_value=100_000, cash_available=50_000,
            current_positions=0, strategy_name="test",
        )
        assert first is not None

        # Second buy for same symbol is blocked
        second = await om.place_buy(
            symbol="AAPL", price=155.0,
            portfolio_value=100_000, cash_available=50_000,
            current_positions=1, strategy_name="test2",
        )
        assert second is None
        assert mock_adapter.create_buy_order.call_count == 1

    async def test_different_symbol_not_blocked(self, mock_adapter, risk_manager):
        """Buy for different symbol is allowed."""
        call_count = 0

        async def create_buy(**kwargs):
            nonlocal call_count
            call_count += 1
            return OrderResult(
                order_id=f"ORD{call_count:03d}", symbol=kwargs["symbol"],
                side="BUY", order_type="limit", quantity=10,
                price=150.0, filled_quantity=0, status="pending",
            )

        mock_adapter.create_buy_order = create_buy
        om = OrderManager(adapter=mock_adapter, risk_manager=risk_manager)

        first = await om.place_buy(
            symbol="AAPL", price=150.0,
            portfolio_value=100_000, cash_available=50_000,
            current_positions=0, strategy_name="test",
        )
        second = await om.place_buy(
            symbol="NVDA", price=800.0,
            portfolio_value=100_000, cash_available=40_000,
            current_positions=1, strategy_name="test",
        )
        assert first is not None
        assert second is not None

    async def test_filled_order_allows_new_buy(self, order_manager):
        """After order fills, new buy for same symbol is allowed."""
        # First buy fills immediately (fixture default)
        await order_manager.place_buy(
            symbol="AAPL", price=150.0,
            portfolio_value=100_000, cash_available=50_000,
            current_positions=0, strategy_name="test",
        )
        # Status is "filled", so has_pending_order should return False
        assert order_manager.has_pending_order("AAPL") is False


class TestSlippageTracking:
    """Tests for slippage measurement."""

    async def test_buy_slippage_positive(self, mock_adapter, risk_manager):
        """Track positive slippage (filled higher than intended)."""
        mock_adapter.create_buy_order = AsyncMock(return_value=OrderResult(
            order_id="ORD001", symbol="AAPL", side="BUY",
            order_type="limit", quantity=10, price=150.0,
            filled_quantity=10, filled_price=150.05, status="filled",
        ))
        om = OrderManager(adapter=mock_adapter, risk_manager=risk_manager)
        order = await om.place_buy(
            symbol="AAPL", price=150.0,
            portfolio_value=100_000, cash_available=50_000,
            current_positions=0, strategy_name="test",
        )
        assert order is not None
        assert abs(order.slippage - 0.05) < 0.001

    async def test_sell_slippage_negative(self, mock_adapter, risk_manager):
        """Track negative slippage (filled lower than intended)."""
        mock_adapter.create_sell_order = AsyncMock(return_value=OrderResult(
            order_id="ORD002", symbol="AAPL", side="SELL",
            order_type="limit", quantity=10, price=160.0,
            filled_quantity=10, filled_price=159.95, status="filled",
        ))
        om = OrderManager(adapter=mock_adapter, risk_manager=risk_manager)
        order = await om.place_sell(
            symbol="AAPL", quantity=10, price=160.0, strategy_name="test",
        )
        assert order is not None
        assert abs(order.slippage - (-0.05)) < 0.001

    async def test_zero_slippage_on_exact_fill(self, order_manager):
        """No slippage when filled at intended price."""
        order = await order_manager.place_buy(
            symbol="AAPL", price=150.0,
            portfolio_value=100_000, cash_available=50_000,
            current_positions=0, strategy_name="test",
        )
        assert order is not None
        assert order.slippage == 0.0


class TestPartialFill:
    """Tests for partial fill tracking."""

    async def test_partial_fill_tracked(self, mock_adapter, risk_manager):
        mock_adapter.create_buy_order = AsyncMock(return_value=OrderResult(
            order_id="ORD001", symbol="AAPL", side="BUY",
            order_type="limit", quantity=100, price=150.0,
            filled_quantity=60, filled_price=150.0, status="partial",
        ))
        om = OrderManager(adapter=mock_adapter, risk_manager=risk_manager)
        order = await om.place_buy(
            symbol="AAPL", price=150.0,
            portfolio_value=100_000, cash_available=50_000,
            current_positions=0, strategy_name="test",
        )
        assert order is not None
        assert order.filled_quantity == 60
        assert order.quantity == 66  # risk-sized quantity

    async def test_zero_fill_tracked(self, mock_adapter, risk_manager):
        mock_adapter.create_buy_order = AsyncMock(return_value=OrderResult(
            order_id="ORD001", symbol="AAPL", side="BUY",
            order_type="limit", quantity=10, price=150.0,
            filled_quantity=0, filled_price=None, status="pending",
        ))
        om = OrderManager(adapter=mock_adapter, risk_manager=risk_manager)
        order = await om.place_buy(
            symbol="AAPL", price=150.0,
            portfolio_value=100_000, cash_available=50_000,
            current_positions=0, strategy_name="test",
        )
        assert order is not None
        assert order.filled_quantity == 0


class TestReconciliation:
    """Tests for order reconciliation with exchange."""

    async def test_reconcile_detects_status_change(self, mock_adapter, risk_manager):
        """Reconciliation detects when order status changes."""
        mock_adapter.create_buy_order = AsyncMock(return_value=OrderResult(
            order_id="ORD001", symbol="AAPL", side="BUY",
            order_type="limit", quantity=10, price=150.0,
            filled_quantity=0, filled_price=None, status="pending",
        ))
        mock_adapter.fetch_order = AsyncMock(return_value=OrderResult(
            order_id="ORD001", symbol="AAPL", side="BUY",
            order_type="limit", quantity=10, price=150.0,
            filled_quantity=10, filled_price=150.0, status="filled",
        ))
        om = OrderManager(adapter=mock_adapter, risk_manager=risk_manager)
        await om.place_buy(
            symbol="AAPL", price=150.0,
            portfolio_value=100_000, cash_available=50_000,
            current_positions=0, strategy_name="test",
        )

        changes = await om.reconcile_all()
        assert len(changes) == 1
        assert changes[0]["old_status"] == "pending"
        assert changes[0]["new_status"] == "filled"

    async def test_reconcile_no_changes(self, order_manager):
        """No changes when order status hasn't changed."""
        # Default fixture creates orders with "filled" status
        await order_manager.place_buy(
            symbol="AAPL", price=150.0,
            portfolio_value=100_000, cash_available=50_000,
            current_positions=0, strategy_name="test",
        )
        changes = await order_manager.reconcile_all()
        # Order was already "filled", so no status change detected
        assert len(changes) == 0

    async def test_reconcile_empty(self, order_manager):
        """No-op when no active orders."""
        changes = await order_manager.reconcile_all()
        assert changes == []

    async def test_reconcile_clears_completed(self, mock_adapter, risk_manager):
        """Reconcile clears filled orders from tracking."""
        mock_adapter.create_buy_order = AsyncMock(return_value=OrderResult(
            order_id="ORD001", symbol="AAPL", side="BUY",
            order_type="limit", quantity=10, price=150.0,
            filled_quantity=0, filled_price=None, status="pending",
        ))
        mock_adapter.fetch_order = AsyncMock(return_value=OrderResult(
            order_id="ORD001", symbol="AAPL", side="BUY",
            order_type="limit", quantity=10, price=150.0,
            filled_quantity=10, filled_price=150.0, status="filled",
        ))
        om = OrderManager(adapter=mock_adapter, risk_manager=risk_manager)
        await om.place_buy(
            symbol="AAPL", price=150.0,
            portfolio_value=100_000, cash_available=50_000,
            current_positions=0, strategy_name="test",
        )
        assert len(om.active_orders) == 1
        await om.reconcile_all()
        assert len(om.active_orders) == 0  # Cleared after fill
