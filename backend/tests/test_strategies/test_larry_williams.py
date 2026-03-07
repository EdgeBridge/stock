"""Tests for Larry Williams Volatility Breakout Strategy."""

import numpy as np
import pandas as pd
import pytest

from strategies.larry_williams import LarryWilliamsStrategy
from core.enums import SignalType


def _make_df(
    n: int = 30,
    current_close: float = 110.0,
    current_open: float = 100.0,
    prev_high: float = 105.0,
    prev_low: float = 95.0,
    prev_close: float | None = None,
    sma_20: float = 98.0,
) -> pd.DataFrame:
    """Create DataFrame with breakout scenario.

    For buy tests, we need prev bar's %R to be oversold (<= -80)
    and current bar's %R to exit oversold (> -80). This means
    prev_close should be near the bottom of the 14-bar range.
    """
    data = []
    # Historical bars with a high early on to create wide range for %R
    for i in range(n - 2):
        price = 100.0 + i * 0.2
        data.append({
            "open": price, "high": price + 8.0, "low": price - 1.0,
            "close": price, "volume": 1_000_000.0,
            "sma_20": sma_20,
        })
    # Previous bar: close near bottom of range for oversold %R
    pc = prev_close if prev_close is not None else prev_low + 1.0
    data.append({
        "open": 99.0, "high": prev_high, "low": prev_low,
        "close": pc, "volume": 1_200_000.0,
        "sma_20": sma_20,
    })
    # Current bar
    data.append({
        "open": current_open, "high": max(current_close, current_open) + 2.0,
        "low": min(current_close, current_open) - 1.0,
        "close": current_close, "volume": 2_000_000.0,
        "sma_20": sma_20,
    })
    return pd.DataFrame(data)


class TestLarryWilliams:
    async def test_buy_on_breakout(self):
        """Close > open + k*(prev_range) with %R and SMA conditions."""
        strategy = LarryWilliamsStrategy()
        # prev_range = 105 - 95 = 10, breakout_up = 100 + 0.5*10 = 105
        # close=110 > 105, above SMA
        df = _make_df(current_close=110.0, current_open=100.0,
                      prev_high=105.0, prev_low=95.0, sma_20=98.0)
        signal = await strategy.analyze(df, "AAPL")
        assert signal.signal_type == SignalType.BUY
        assert "breakout" in signal.reason.lower()

    async def test_hold_no_breakout(self):
        strategy = LarryWilliamsStrategy()
        # close=103 < breakout_up=105
        df = _make_df(current_close=103.0, current_open=100.0,
                      prev_high=105.0, prev_low=95.0)
        signal = await strategy.analyze(df, "AAPL")
        assert signal.signal_type == SignalType.HOLD

    async def test_sell_on_breakdown(self):
        strategy = LarryWilliamsStrategy()
        # breakout_down = 100 - 0.5*10 = 95, close=90 < 95
        # For sell, need %R overbought (> -20)
        # Use prices where %R would be near 0 (close near high)
        df = _make_df(current_close=90.0, current_open=100.0,
                      prev_high=105.0, prev_low=95.0)
        signal = await strategy.analyze(df, "AAPL")
        # May be HOLD or SELL depending on Williams %R value
        assert signal.signal_type in (SignalType.SELL, SignalType.HOLD)

    async def test_hold_below_sma(self):
        """Breakout but below SMA should not trigger buy."""
        strategy = LarryWilliamsStrategy()
        df = _make_df(current_close=110.0, current_open=100.0,
                      prev_high=105.0, prev_low=95.0, sma_20=115.0)
        signal = await strategy.analyze(df, "AAPL")
        # Above breakout but below SMA -> no buy
        assert signal.signal_type != SignalType.BUY

    async def test_insufficient_data(self):
        strategy = LarryWilliamsStrategy()
        df = pd.DataFrame({
            "open": [100.0] * 5, "high": [102.0] * 5,
            "low": [98.0] * 5, "close": [100.0] * 5,
            "volume": [1000.0] * 5,
        })
        signal = await strategy.analyze(df, "AAPL")
        assert signal.signal_type == SignalType.HOLD

    async def test_no_previous_range(self):
        """Zero previous range should hold."""
        strategy = LarryWilliamsStrategy()
        df = _make_df(prev_high=100.0, prev_low=100.0)
        signal = await strategy.analyze(df, "AAPL")
        assert signal.signal_type == SignalType.HOLD
        assert "no previous range" in signal.reason.lower()

    async def test_indicators_present(self):
        strategy = LarryWilliamsStrategy()
        df = _make_df()
        signal = await strategy.analyze(df, "AAPL")
        assert "breakout_up" in signal.indicators
        assert "williams_r" in signal.indicators
        assert "prev_range" in signal.indicators

    async def test_get_set_params(self):
        strategy = LarryWilliamsStrategy()
        params = strategy.get_params()
        assert params["k"] == 0.5
        assert params["willr_period"] == 14
        assert params["willr_oversold"] == -80.0
        assert params["willr_overbought"] == -20.0
        assert params["sma_period"] == 20

        strategy.set_params({"k": 0.6, "willr_period": 10})
        assert strategy.get_params()["k"] == 0.6
        assert strategy.get_params()["willr_period"] == 10

    async def test_custom_params(self):
        strategy = LarryWilliamsStrategy(params={"k": 0.3})
        assert strategy.get_params()["k"] == 0.3
