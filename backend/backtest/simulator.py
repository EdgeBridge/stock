"""Backtest order simulator.

Simulates order execution with slippage, tracks positions and equity.
"""

import logging
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from backtest.metrics import Trade
from strategies.base import Signal
from core.enums import SignalType

logger = logging.getLogger(__name__)


@dataclass
class SimPosition:
    symbol: str
    quantity: float
    avg_price: float
    entry_date: str
    strategy_name: str = ""


@dataclass
class SimConfig:
    initial_equity: float = 100_000.0
    slippage_pct: float = 0.05  # 0.05% default
    commission_per_order: float = 0.0  # KIS US stocks: $0
    fx_spread_pct: float = 0.25  # KRW/USD spread
    max_position_pct: float = 0.10  # max 10% per position
    max_total_positions: int = 20


class BacktestSimulator:
    """Simulates trading on historical data."""

    def __init__(self, config: SimConfig | None = None):
        self._config = config or SimConfig()
        self._equity = self._config.initial_equity
        self._cash = self._config.initial_equity
        self._positions: dict[str, SimPosition] = {}
        self._trades: list[Trade] = []
        self._equity_curve: list[float] = []
        self._equity_dates: list = []

    @property
    def trades(self) -> list[Trade]:
        return self._trades

    @property
    def equity_curve(self) -> pd.Series:
        if not self._equity_curve:
            return pd.Series(dtype=float)
        return pd.Series(self._equity_curve, index=self._equity_dates)

    @property
    def positions(self) -> dict[str, SimPosition]:
        return self._positions

    def run(
        self,
        df: pd.DataFrame,
        signals: dict[int, Signal],
        symbol: str,
    ) -> None:
        """Run simulation on a single symbol.

        Args:
            df: OHLCV DataFrame with indicators
            signals: Dict mapping row index -> Signal
            symbol: Stock symbol
        """
        for i in range(len(df)):
            row = df.iloc[i]
            date = df.index[i]
            price = float(row["close"])

            signal = signals.get(i)
            if signal:
                self._process_signal(signal, symbol, price, date)

            # Update equity
            self._update_equity(price, symbol, date)

    def _process_signal(
        self, signal: Signal, symbol: str, price: float, date
    ) -> None:
        if signal.signal_type == SignalType.BUY:
            self._open_position(symbol, price, date, signal)
        elif signal.signal_type == SignalType.SELL:
            self._close_position(symbol, price, date)

    def _open_position(
        self, symbol: str, price: float, date, signal: Signal
    ) -> None:
        if symbol in self._positions:
            return  # Already holding
        if len(self._positions) >= self._config.max_total_positions:
            return

        # Position sizing
        max_allocation = self._equity * self._config.max_position_pct
        allocation = min(max_allocation, self._cash * 0.95)  # Keep 5% buffer
        if allocation <= 0:
            return

        # Apply slippage (buy higher)
        exec_price = price * (1 + self._config.slippage_pct / 100)
        quantity = int(allocation / exec_price)
        if quantity <= 0:
            return

        cost = quantity * exec_price + self._config.commission_per_order
        if cost > self._cash:
            return

        self._cash -= cost
        self._positions[symbol] = SimPosition(
            symbol=symbol,
            quantity=quantity,
            avg_price=exec_price,
            entry_date=str(date),
            strategy_name=signal.strategy_name,
        )

    def _close_position(self, symbol: str, price: float, date) -> None:
        pos = self._positions.get(symbol)
        if not pos:
            return

        # Apply slippage (sell lower)
        exec_price = price * (1 - self._config.slippage_pct / 100)
        proceeds = pos.quantity * exec_price - self._config.commission_per_order
        self._cash += proceeds

        pnl = (exec_price - pos.avg_price) * pos.quantity
        pnl_pct = (exec_price - pos.avg_price) / pos.avg_price * 100

        # Calculate holding days
        try:
            entry = pd.Timestamp(pos.entry_date)
            exit_ = pd.Timestamp(str(date))
            holding_days = (exit_ - entry).days
        except Exception:
            holding_days = 0

        self._trades.append(Trade(
            symbol=symbol,
            side="SELL",
            entry_date=pos.entry_date,
            entry_price=pos.avg_price,
            exit_date=str(date),
            exit_price=exec_price,
            quantity=pos.quantity,
            pnl=pnl,
            pnl_pct=pnl_pct,
            holding_days=holding_days,
            strategy_name=pos.strategy_name,
        ))

        del self._positions[symbol]

    def _update_equity(self, price: float, symbol: str, date) -> None:
        position_value = sum(
            pos.quantity * (price if pos.symbol == symbol else pos.avg_price)
            for pos in self._positions.values()
        )
        self._equity = self._cash + position_value
        self._equity_curve.append(self._equity)
        self._equity_dates.append(date)

    def reset(self) -> None:
        """Reset simulator state."""
        self._equity = self._config.initial_equity
        self._cash = self._config.initial_equity
        self._positions.clear()
        self._trades.clear()
        self._equity_curve.clear()
        self._equity_dates.clear()
