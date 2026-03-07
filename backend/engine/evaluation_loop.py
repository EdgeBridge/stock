"""Trading engine evaluation loop.

Periodically evaluates strategies against market data,
generates combined signals, and executes trades via OrderManager.
"""

import asyncio
import logging

import pandas as pd

from exchange.base import ExchangeAdapter
from data.market_data_service import MarketDataService
from data.indicator_service import IndicatorService
from strategies.registry import StrategyRegistry
from strategies.combiner import SignalCombiner
from engine.order_manager import OrderManager
from engine.risk_manager import RiskManager
from core.enums import SignalType

logger = logging.getLogger(__name__)


class EvaluationLoop:
    """Main trading loop: data -> strategy -> signal -> order."""

    def __init__(
        self,
        adapter: ExchangeAdapter,
        market_data: MarketDataService,
        indicator_svc: IndicatorService,
        registry: StrategyRegistry,
        combiner: SignalCombiner,
        order_manager: OrderManager,
        risk_manager: RiskManager,
        watchlist: list[str] | None = None,
        market_state: str = "uptrend",
        interval_sec: int = 300,
    ):
        self._adapter = adapter
        self._market_data = market_data
        self._indicator_svc = indicator_svc
        self._registry = registry
        self._combiner = combiner
        self._order_manager = order_manager
        self._risk_manager = risk_manager
        self._watchlist = watchlist or []
        self._market_state = market_state
        self._interval_sec = interval_sec
        self._running = False

    @property
    def running(self) -> bool:
        return self._running

    def set_watchlist(self, symbols: list[str]) -> None:
        self._watchlist = symbols

    def set_market_state(self, state: str) -> None:
        self._market_state = state

    async def start(self) -> None:
        """Start the evaluation loop."""
        self._running = True
        logger.info("Evaluation loop started (interval=%ds)", self._interval_sec)

        while self._running:
            try:
                await self._evaluate_all()
            except Exception as e:
                logger.error("Evaluation loop error: %s", e)

            await asyncio.sleep(self._interval_sec)

    async def stop(self) -> None:
        """Stop the evaluation loop."""
        self._running = False
        logger.info("Evaluation loop stopped")

    async def evaluate_symbol(self, symbol: str) -> None:
        """Evaluate a single symbol through all strategies."""
        try:
            # Fetch OHLCV data
            df = await self._market_data.get_ohlcv(symbol, limit=250)
            if df.empty:
                return

            # Add indicators
            df = self._indicator_svc.add_all_indicators(df)

            # Run all enabled strategies
            strategies = self._registry.get_enabled()
            signals = []
            for strategy in strategies:
                try:
                    signal = await strategy.analyze(df, symbol)
                    signals.append(signal)
                except Exception as e:
                    logger.debug("Strategy %s failed on %s: %s", strategy.name, symbol, e)

            # Combine signals
            weights = self._registry.get_profile_weights(self._market_state)
            combined = self._combiner.combine(signals, weights)

            # Execute
            await self._execute_signal(combined, symbol, df)

        except Exception as e:
            logger.error("Failed to evaluate %s: %s", symbol, e)

    async def _evaluate_all(self) -> None:
        """Evaluate all symbols in watchlist."""
        for symbol in self._watchlist:
            await self.evaluate_symbol(symbol)

    async def _execute_signal(
        self, signal, symbol: str, df: pd.DataFrame
    ) -> None:
        """Execute a combined signal."""
        if signal.signal_type == SignalType.HOLD:
            return

        price = float(df.iloc[-1]["close"])

        if signal.signal_type == SignalType.BUY:
            balance = await self._adapter.fetch_balance()
            positions = await self._adapter.fetch_positions()

            await self._order_manager.place_buy(
                symbol=symbol,
                price=price,
                portfolio_value=balance.total,
                cash_available=balance.available,
                current_positions=len(positions),
                strategy_name=signal.strategy_name,
            )

        elif signal.signal_type == SignalType.SELL:
            positions = await self._adapter.fetch_positions()
            pos = next((p for p in positions if p.symbol == symbol), None)
            if pos and pos.quantity > 0:
                await self._order_manager.place_sell(
                    symbol=symbol,
                    quantity=int(pos.quantity),
                    price=price,
                    strategy_name=signal.strategy_name,
                )
