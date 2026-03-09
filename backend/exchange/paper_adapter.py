"""Paper trading adapter for backtesting and simulation.

Simulates order execution without touching real APIs.
Mirrors ExchangeAdapter interface for seamless swapping.
"""

import time
import uuid
import logging

from exchange.base import (
    Balance,
    Candle,
    ExchangeAdapter,
    OrderBook,
    OrderResult,
    Position,
    Ticker,
)

logger = logging.getLogger(__name__)


class PaperAdapter(ExchangeAdapter):
    """In-memory paper trading adapter."""

    def __init__(self, initial_balance_usd: float = 10_000, currency: str = "USD"):
        self._cash = initial_balance_usd
        self._initial_cash = initial_balance_usd
        self._currency = currency
        self._positions: dict[str, Position] = {}
        self._orders: dict[str, OrderResult] = {}
        self._prices: dict[str, float] = {}  # symbol -> last known price

    async def initialize(self) -> None:
        logger.info("Paper adapter initialized (balance=$%.2f)", self._cash)

    async def close(self) -> None:
        pass

    # -- Market Data (must be fed externally) --

    def set_price(self, symbol: str, price: float) -> None:
        """Set current price for simulation."""
        self._prices[symbol] = price
        if symbol in self._positions:
            pos = self._positions[symbol]
            pos.current_price = price
            pos.unrealized_pnl = (price - pos.avg_price) * pos.quantity
            pos.unrealized_pnl_pct = (
                ((price - pos.avg_price) / pos.avg_price * 100) if pos.avg_price > 0 else 0
            )

    async def fetch_ticker(self, symbol: str, exchange: str = "NASD") -> Ticker:
        price = self._prices.get(symbol, 0.0)
        return Ticker(symbol=symbol, price=price)

    async def fetch_ohlcv(
        self, symbol: str, timeframe: str = "1D", limit: int = 100, exchange: str = "NASD"
    ) -> list[Candle]:
        raise NotImplementedError("Paper adapter needs external OHLCV data feed")

    async def fetch_orderbook(
        self, symbol: str, exchange: str = "NASD", limit: int = 20
    ) -> OrderBook:
        price = self._prices.get(symbol, 100.0)
        spread = price * 0.001
        return OrderBook(
            symbol=symbol,
            bids=[(price - spread, 100)],
            asks=[(price + spread, 100)],
        )

    # -- Account --

    async def fetch_balance(self) -> Balance:
        total = self._cash + sum(
            p.current_price * p.quantity for p in self._positions.values()
        )
        return Balance(currency=self._currency, total=total, available=self._cash)

    async def fetch_positions(self) -> list[Position]:
        return [p for p in self._positions.values() if p.quantity > 0]

    async def fetch_buying_power(self) -> float:
        return self._cash

    # -- Orders --

    async def create_buy_order(
        self,
        symbol: str,
        quantity: int,
        price: float | None = None,
        order_type: str = "market",
        exchange: str = "NASD",
    ) -> OrderResult:
        fill_price = price or self._prices.get(symbol, 0.0)
        cost = fill_price * quantity
        slippage = cost * 0.0005  # 0.05% slippage

        if cost + slippage > self._cash:
            return OrderResult(
                order_id="",
                symbol=symbol,
                side="buy",
                order_type=order_type,
                quantity=quantity,
                price=fill_price,
                status="failed",
            )

        self._cash -= cost + slippage

        if symbol in self._positions:
            pos = self._positions[symbol]
            total_qty = pos.quantity + quantity
            pos.avg_price = (pos.avg_price * pos.quantity + fill_price * quantity) / total_qty
            pos.quantity = total_qty
        else:
            self._positions[symbol] = Position(
                symbol=symbol,
                exchange=exchange,
                quantity=quantity,
                avg_price=fill_price,
                current_price=fill_price,
            )

        order_id = str(uuid.uuid4())[:8]
        result = OrderResult(
            order_id=order_id,
            symbol=symbol,
            side="buy",
            order_type=order_type,
            quantity=quantity,
            price=fill_price,
            filled_quantity=quantity,
            filled_price=fill_price,
            status="filled",
            timestamp=int(time.time()),
        )
        self._orders[order_id] = result
        logger.info("Paper BUY %s x%d @ $%.2f", symbol, quantity, fill_price)
        return result

    async def create_sell_order(
        self,
        symbol: str,
        quantity: int,
        price: float | None = None,
        order_type: str = "market",
        exchange: str = "NASD",
    ) -> OrderResult:
        pos = self._positions.get(symbol)
        if not pos or pos.quantity < quantity:
            return OrderResult(
                order_id="",
                symbol=symbol,
                side="sell",
                order_type=order_type,
                quantity=quantity,
                status="failed",
            )

        fill_price = price or self._prices.get(symbol, pos.current_price)
        revenue = fill_price * quantity
        slippage = revenue * 0.0005

        self._cash += revenue - slippage
        pos.quantity -= quantity
        if pos.quantity <= 0:
            del self._positions[symbol]

        order_id = str(uuid.uuid4())[:8]
        result = OrderResult(
            order_id=order_id,
            symbol=symbol,
            side="sell",
            order_type=order_type,
            quantity=quantity,
            price=fill_price,
            filled_quantity=quantity,
            filled_price=fill_price,
            status="filled",
            timestamp=int(time.time()),
        )
        self._orders[order_id] = result
        pnl = (fill_price - (pos.avg_price if pos else fill_price)) * quantity
        logger.info("Paper SELL %s x%d @ $%.2f (PnL=$%.2f)", symbol, quantity, fill_price, pnl)
        return result

    async def cancel_order(self, order_id: str, symbol: str) -> bool:
        if order_id in self._orders:
            self._orders[order_id].status = "cancelled"
            return True
        return False

    async def fetch_order(self, order_id: str, symbol: str) -> OrderResult:
        if order_id in self._orders:
            return self._orders[order_id]
        return OrderResult(
            order_id=order_id, symbol=symbol, side="unknown",
            order_type="unknown", quantity=0, status="not_found",
        )

    async def fetch_pending_orders(self) -> list[OrderResult]:
        return [o for o in self._orders.values() if o.status in ("pending", "open")]
