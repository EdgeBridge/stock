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
        status="filled", filled_price=150.0,
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
