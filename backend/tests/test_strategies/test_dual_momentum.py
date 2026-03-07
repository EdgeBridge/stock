"""Tests for Dual Momentum Strategy."""

import pytest
import pandas as pd
import numpy as np

from strategies.dual_momentum import DualMomentumStrategy
from core.enums import SignalType


def _make_df(n=100, trend="up"):
    """Create a DataFrame with price data."""
    dates = pd.date_range("2023-01-01", periods=n, freq="B")
    if trend == "up":
        closes = 100 + np.cumsum(np.random.uniform(0.1, 0.5, n))
    elif trend == "down":
        closes = 200 - np.cumsum(np.random.uniform(0.1, 0.5, n))
    else:
        closes = 100 + np.random.uniform(-0.5, 0.5, n).cumsum() * 0.1 + 100
    df = pd.DataFrame({
        "open": closes * 0.99,
        "high": closes * 1.01,
        "low": closes * 0.98,
        "close": closes,
        "volume": np.random.randint(1_000_000, 5_000_000, n),
    }, index=dates)
    # Add indicators
    df["ema_20"] = df["close"].ewm(span=20).mean()
    df["ema_50"] = df["close"].ewm(span=50).mean()
    df["rsi"] = 55.0
    df["roc_20"] = df["close"].pct_change(20) * 100
    df["volume_ratio"] = 1.2
    return df


@pytest.mark.asyncio
async def test_buy_signal_uptrend():
    s = DualMomentumStrategy()
    df = _make_df(300, trend="up")
    signal = await s.analyze(df, "AAPL")
    assert signal.signal_type == SignalType.BUY
    assert signal.confidence > 0


@pytest.mark.asyncio
async def test_sell_signal_downtrend():
    s = DualMomentumStrategy()
    df = _make_df(300, trend="down")
    signal = await s.analyze(df, "AAPL")
    assert signal.signal_type == SignalType.SELL


@pytest.mark.asyncio
async def test_hold_insufficient_data():
    s = DualMomentumStrategy()
    df = _make_df(10, trend="up")
    signal = await s.analyze(df, "AAPL")
    assert signal.signal_type == SignalType.HOLD


@pytest.mark.asyncio
async def test_params_override():
    s = DualMomentumStrategy(params={"lookback_months": 6, "min_absolute_return": 0.05})
    assert s.get_params()["lookback_months"] == 6
    assert s.get_params()["min_absolute_return"] == 0.05


@pytest.mark.asyncio
async def test_set_params():
    s = DualMomentumStrategy()
    s.set_params({"lookback_months": 3})
    assert s.get_params()["lookback_months"] == 3


@pytest.mark.asyncio
async def test_strategy_name():
    s = DualMomentumStrategy()
    assert s.name == "dual_momentum"
    assert s.display_name == "Dual Momentum"
