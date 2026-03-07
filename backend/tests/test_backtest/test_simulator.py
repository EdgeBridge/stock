"""Tests for backtest simulator."""

import numpy as np
import pandas as pd
import pytest

from backtest.simulator import BacktestSimulator, SimConfig, SimPosition
from strategies.base import Signal
from core.enums import SignalType


def _make_df(n: int = 50, start_price: float = 100.0) -> pd.DataFrame:
    """Create a simple uptrending DataFrame."""
    np.random.seed(42)
    prices = [start_price]
    for _ in range(n - 1):
        prices.append(prices[-1] * (1 + np.random.normal(0.002, 0.01)))

    close = np.array(prices)
    dates = pd.bdate_range("2021-01-01", periods=n)
    return pd.DataFrame({
        "open": close * 0.999,
        "high": close * 1.01,
        "low": close * 0.99,
        "close": close,
        "volume": np.random.randint(100_000, 500_000, n).astype(float),
    }, index=dates)


def _buy_signal(name: str = "test") -> Signal:
    return Signal(
        signal_type=SignalType.BUY,
        confidence=0.8,
        strategy_name=name,
        reason="test buy",
    )


def _sell_signal(name: str = "test") -> Signal:
    return Signal(
        signal_type=SignalType.SELL,
        confidence=0.8,
        strategy_name=name,
        reason="test sell",
    )


class TestSimulator:
    def test_no_signals_equity_unchanged(self):
        sim = BacktestSimulator(SimConfig(initial_equity=100_000))
        df = _make_df()
        sim.run(df, {}, "AAPL")
        curve = sim.equity_curve
        assert len(curve) == len(df)
        # No trades, equity should stay at initial
        assert curve.iloc[0] == pytest.approx(100_000, rel=0.01)
        assert len(sim.trades) == 0

    def test_buy_and_sell(self):
        config = SimConfig(initial_equity=100_000, slippage_pct=0.0)
        sim = BacktestSimulator(config)
        df = _make_df(50, start_price=100.0)

        signals = {
            5: _buy_signal(),
            25: _sell_signal(),
        }
        sim.run(df, signals, "AAPL")

        assert len(sim.trades) == 1
        trade = sim.trades[0]
        assert trade.symbol == "AAPL"
        assert trade.entry_price > 0
        assert trade.exit_price > 0
        assert trade.quantity > 0

    def test_slippage_applied(self):
        config = SimConfig(initial_equity=100_000, slippage_pct=1.0)
        sim = BacktestSimulator(config)
        df = _make_df(30)
        price_at_5 = float(df.iloc[5]["close"])

        signals = {5: _buy_signal()}
        sim.run(df, signals, "AAPL")

        pos = sim.positions.get("AAPL")
        assert pos is not None
        # Buy price should be higher than close (slippage)
        assert pos.avg_price > price_at_5

    def test_position_sizing_respects_max(self):
        config = SimConfig(initial_equity=100_000, max_position_pct=0.05)
        sim = BacktestSimulator(config)
        df = _make_df(20, start_price=100.0)

        signals = {5: _buy_signal()}
        sim.run(df, signals, "AAPL")

        pos = sim.positions.get("AAPL")
        assert pos is not None
        position_value = pos.quantity * pos.avg_price
        assert position_value <= 100_000 * 0.05 + 200  # allow some tolerance

    def test_max_positions_limit(self):
        config = SimConfig(initial_equity=1_000_000, max_total_positions=1)
        sim = BacktestSimulator(config)
        df = _make_df(20)

        # Buy at bar 5 for AAPL
        signals = {5: _buy_signal()}
        sim.run(df, signals, "AAPL")

        # Try to buy TSLA — should be blocked
        sim.run(df, {5: _buy_signal()}, "TSLA")
        assert "TSLA" not in sim.positions

    def test_no_duplicate_position(self):
        config = SimConfig(initial_equity=100_000, slippage_pct=0.0)
        sim = BacktestSimulator(config)
        df = _make_df(20)

        signals = {3: _buy_signal(), 5: _buy_signal()}
        sim.run(df, signals, "AAPL")

        # Should only have one position
        assert len(sim.positions) == 1

    def test_sell_without_position_ignored(self):
        sim = BacktestSimulator()
        df = _make_df(10)
        sim.run(df, {5: _sell_signal()}, "AAPL")
        assert len(sim.trades) == 0

    def test_pnl_calculation(self):
        config = SimConfig(initial_equity=100_000, slippage_pct=0.0)
        sim = BacktestSimulator(config)

        # Create a dataframe where price goes up
        prices = [100.0] * 5 + [110.0] * 5
        dates = pd.bdate_range("2021-01-01", periods=10)
        df = pd.DataFrame({
            "open": prices,
            "high": [p * 1.01 for p in prices],
            "low": [p * 0.99 for p in prices],
            "close": prices,
            "volume": [1_000_000.0] * 10,
        }, index=dates)

        signals = {1: _buy_signal(), 7: _sell_signal()}
        sim.run(df, signals, "AAPL")

        assert len(sim.trades) == 1
        assert sim.trades[0].pnl > 0
        assert sim.trades[0].pnl_pct == pytest.approx(10.0)

    def test_equity_curve_length(self):
        sim = BacktestSimulator()
        df = _make_df(30)
        sim.run(df, {}, "AAPL")
        assert len(sim.equity_curve) == 30

    def test_reset(self):
        sim = BacktestSimulator(SimConfig(initial_equity=50_000))
        df = _make_df(10)
        sim.run(df, {2: _buy_signal()}, "AAPL")
        assert len(sim.positions) > 0

        sim.reset()
        assert len(sim.positions) == 0
        assert len(sim.trades) == 0
        assert len(sim.equity_curve) == 0

    def test_hold_signal_ignored(self):
        sim = BacktestSimulator()
        df = _make_df(10)
        hold = Signal(
            signal_type=SignalType.HOLD,
            confidence=0.5,
            strategy_name="test",
            reason="hold",
        )
        sim.run(df, {5: hold}, "AAPL")
        assert len(sim.trades) == 0
        assert len(sim.positions) == 0


class TestSimConfig:
    def test_defaults(self):
        c = SimConfig()
        assert c.initial_equity == 100_000.0
        assert c.slippage_pct == 0.05
        assert c.commission_per_order == 0.0
        assert c.max_position_pct == 0.10
        assert c.max_total_positions == 20

    def test_custom_values(self):
        c = SimConfig(initial_equity=50_000, slippage_pct=0.1)
        assert c.initial_equity == 50_000
        assert c.slippage_pct == 0.1
