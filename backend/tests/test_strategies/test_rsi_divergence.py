"""Tests for RSI Divergence Strategy."""

import pytest
import pandas as pd
import numpy as np

from strategies.rsi_divergence import RSIDivergenceStrategy
from core.enums import SignalType


def _make_df(n=60, rsi_values=None, prices=None):
    """Create DataFrame with RSI data."""
    dates = pd.date_range("2023-01-01", periods=n, freq="B")
    if prices is None:
        prices = 100 + np.random.uniform(-1, 1, n).cumsum()
    df = pd.DataFrame({
        "open": prices * 0.99,
        "high": prices * 1.01,
        "low": prices * 0.98,
        "close": prices,
        "volume": np.random.randint(1_000_000, 5_000_000, n),
    }, index=dates)
    if rsi_values is not None:
        df["rsi"] = rsi_values
    else:
        df["rsi"] = 50.0
    return df


@pytest.mark.asyncio
async def test_oversold_buy():
    s = RSIDivergenceStrategy()
    df = _make_df(60)
    df["rsi"] = 25.0  # Below oversold
    signal = await s.analyze(df, "AAPL")
    assert signal.signal_type == SignalType.BUY
    assert "oversold" in signal.reason


@pytest.mark.asyncio
async def test_overbought_sell():
    s = RSIDivergenceStrategy()
    df = _make_df(60)
    df["rsi"] = 75.0  # Above overbought
    signal = await s.analyze(df, "AAPL")
    assert signal.signal_type == SignalType.SELL
    assert "overbought" in signal.reason


@pytest.mark.asyncio
async def test_hold_neutral_rsi():
    s = RSIDivergenceStrategy()
    df = _make_df(60)
    df["rsi"] = 50.0
    signal = await s.analyze(df, "AAPL")
    assert signal.signal_type == SignalType.HOLD


@pytest.mark.asyncio
async def test_hold_insufficient_data():
    s = RSIDivergenceStrategy()
    df = _make_df(10)
    signal = await s.analyze(df, "AAPL")
    assert signal.signal_type == SignalType.HOLD


@pytest.mark.asyncio
async def test_hold_no_rsi():
    s = RSIDivergenceStrategy()
    df = _make_df(60)
    df["rsi"] = np.nan
    signal = await s.analyze(df, "AAPL")
    assert signal.signal_type == SignalType.HOLD


@pytest.mark.asyncio
async def test_bullish_divergence():
    """Price lower low but RSI higher low -> BUY."""
    s = RSIDivergenceStrategy(params={"min_price_move_pct": 2.0, "divergence_lookback": 14})
    n = 60
    # Price makes lower lows
    prices = np.array([100.0] * n)
    prices[:n // 2] = np.linspace(100, 95, n // 2)  # first half drops to 95
    prices[n // 2:] = np.linspace(95, 90, n - n // 2)  # second half drops to 90
    # RSI makes higher lows (divergence)
    rsi_vals = np.array([50.0] * n)
    rsi_vals[:n // 2] = np.linspace(50, 20, n // 2)  # first half drops to 20
    rsi_vals[n // 2:] = np.linspace(25, 28, n - n // 2)  # second half: higher low at ~25-28
    df = _make_df(n, rsi_values=rsi_vals, prices=prices)
    signal = await s.analyze(df, "AAPL")
    # Should detect divergence or at least oversold
    assert signal.signal_type == SignalType.BUY


@pytest.mark.asyncio
async def test_params():
    s = RSIDivergenceStrategy(params={"overbought": 80, "oversold": 20})
    assert s.get_params()["overbought"] == 80
    assert s.get_params()["oversold"] == 20
    s.set_params({"overbought": 75})
    assert s.get_params()["overbought"] == 75
