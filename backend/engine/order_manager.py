"""Order manager - handles order creation, tracking, and lifecycle.

Bridges strategy signals with exchange adapter for order execution.
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime

from exchange.base import ExchangeAdapter, OrderResult
from engine.risk_manager import RiskManager, PositionSizeResult

logger = logging.getLogger(__name__)

# Optional trade recorder (set by main.py at startup)
_trade_recorder = None


def set_trade_recorder(recorder):
    global _trade_recorder
    _trade_recorder = recorder


@dataclass
class ManagedOrder:
    order_id: str
    symbol: str
    side: str
    quantity: int
    price: float | None
    strategy_name: str
    status: str = "pending"
    filled_price: float | None = None
    created_at: str = ""
    exchange: str = "NASD"


class OrderManager:
    """Manage order lifecycle: create, track, cancel."""

    def __init__(
        self,
        adapter: ExchangeAdapter,
        risk_manager: RiskManager,
        notification=None,
    ):
        self._adapter = adapter
        self._risk = risk_manager
        self._notification = notification
        self._active_orders: dict[str, ManagedOrder] = {}

    async def place_buy(
        self,
        symbol: str,
        price: float,
        portfolio_value: float,
        cash_available: float,
        current_positions: int,
        strategy_name: str,
        order_type: str = "limit",
        exchange: str = "NASD",
        atr: float | None = None,
    ) -> ManagedOrder | None:
        """Place a buy order after risk checks."""
        sizing = self._risk.calculate_position_size(
            symbol=symbol,
            price=price,
            portfolio_value=portfolio_value,
            cash_available=cash_available,
            current_positions=current_positions,
            atr=atr,
        )

        if not sizing.allowed:
            logger.info("Buy rejected for %s: %s", symbol, sizing.reason)
            if self._notification:
                await self._notification.notify_order_rejected(symbol, sizing.reason)
            return None

        try:
            result = await self._adapter.create_buy_order(
                symbol=symbol,
                quantity=sizing.quantity,
                price=price if order_type == "limit" else None,
                order_type=order_type,
                exchange=exchange,
            )

            order = ManagedOrder(
                order_id=result.order_id,
                symbol=symbol,
                side="BUY",
                quantity=sizing.quantity,
                price=price,
                strategy_name=strategy_name,
                status=result.status,
                filled_price=result.filled_price,
                created_at=datetime.now().isoformat(),
                exchange=exchange,
            )
            self._active_orders[result.order_id] = order
            logger.info(
                "Buy order placed: %s %d shares @ $%.2f (%s)",
                symbol, sizing.quantity, price, strategy_name,
            )
            if self._notification:
                await self._notification.notify_trade_executed(
                    symbol, "BUY", sizing.quantity, price, strategy_name,
                )
            if _trade_recorder:
                _trade_recorder({
                    "symbol": symbol, "side": "BUY", "quantity": sizing.quantity,
                    "price": price, "filled_price": result.filled_price,
                    "strategy": strategy_name, "status": result.status,
                    "created_at": order.created_at,
                })
            return order

        except Exception as e:
            logger.error("Failed to place buy order for %s: %s", symbol, e)
            return None

    async def place_sell(
        self,
        symbol: str,
        quantity: int,
        price: float | None = None,
        strategy_name: str = "",
        order_type: str = "limit",
        exchange: str = "NASD",
    ) -> ManagedOrder | None:
        """Place a sell order."""
        try:
            result = await self._adapter.create_sell_order(
                symbol=symbol,
                quantity=quantity,
                price=price,
                order_type=order_type,
                exchange=exchange,
            )

            order = ManagedOrder(
                order_id=result.order_id,
                symbol=symbol,
                side="SELL",
                quantity=quantity,
                price=price,
                strategy_name=strategy_name,
                status=result.status,
                filled_price=result.filled_price,
                created_at=datetime.now().isoformat(),
                exchange=exchange,
            )
            self._active_orders[result.order_id] = order
            logger.info(
                "Sell order placed: %s %d shares @ %s (%s)",
                symbol, quantity, f"${price:.2f}" if price else "market", strategy_name,
            )
            if self._notification:
                await self._notification.notify_trade_executed(
                    symbol, "SELL", quantity, price or 0, strategy_name,
                )
            if _trade_recorder:
                _trade_recorder({
                    "symbol": symbol, "side": "SELL", "quantity": quantity,
                    "price": price, "filled_price": result.filled_price,
                    "strategy": strategy_name, "status": result.status,
                    "pnl": None,  # caller can update
                    "created_at": order.created_at,
                })
            return order

        except Exception as e:
            logger.error("Failed to place sell order for %s: %s", symbol, e)
            return None

    async def cancel(self, order_id: str, symbol: str) -> bool:
        """Cancel an active order."""
        try:
            success = await self._adapter.cancel_order(order_id, symbol)
            if success and order_id in self._active_orders:
                self._active_orders[order_id].status = "cancelled"
            return success
        except Exception as e:
            logger.error("Failed to cancel order %s: %s", order_id, e)
            return False

    async def sync_order_status(self, order_id: str, symbol: str) -> ManagedOrder | None:
        """Sync order status from exchange."""
        managed = self._active_orders.get(order_id)
        if not managed:
            return None
        try:
            result = await self._adapter.fetch_order(order_id, symbol)
            managed.status = result.status
            managed.filled_price = result.filled_price
            return managed
        except Exception as e:
            logger.error("Failed to sync order %s: %s", order_id, e)
            return managed

    @property
    def active_orders(self) -> dict[str, ManagedOrder]:
        return dict(self._active_orders)

    def clear_completed(self) -> None:
        """Remove completed/cancelled orders from tracking."""
        to_remove = [
            oid for oid, o in self._active_orders.items()
            if o.status in ("filled", "cancelled")
        ]
        for oid in to_remove:
            del self._active_orders[oid]
