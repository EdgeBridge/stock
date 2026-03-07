"""Tests for Sector Rotation Strategy."""

import pytest
import pandas as pd
import numpy as np

from strategies.sector_rotation import SectorRotationStrategy
from core.enums import SignalType


def _make_df(n=100, trend="up"):
    dates = pd.date_range("2023-01-01", periods=n, freq="B")
    if trend == "strong_up":
        closes = 100 + np.arange(n) * 1.0  # Strong upward
    elif trend == "up":
        closes = 100 + np.arange(n) * 0.3
    elif trend == "down":
        closes = 200 - np.arange(n) * 0.5
    else:
        closes = 100 + np.random.uniform(-0.5, 0.5, n).cumsum() * 0.1
    df = pd.DataFrame({
        "open": closes * 0.99,
        "high": closes * 1.01,
        "low": closes * 0.98,
        "close": closes,
        "volume": np.random.randint(1_000_000, 5_000_000, n),
    }, index=dates)
    df["ema_20"] = df["close"].ewm(span=20).mean()
    df["ema_50"] = df["close"].ewm(span=50).mean()
    df["rsi"] = 55.0
    df["volume_ratio"] = 1.3
    return df


@pytest.mark.asyncio
async def test_buy_strong_sector():
    s = SectorRotationStrategy(params={"min_strength_score": 20})
    df = _make_df(100, trend="strong_up")
    signal = await s.analyze(df, "XLK")
    assert signal.signal_type == SignalType.BUY
    assert "strength" in signal.reason.lower()


@pytest.mark.asyncio
async def test_sell_weak_sector():
    s = SectorRotationStrategy(params={"min_strength_score": 20})
    df = _make_df(100, trend="down")
    signal = await s.analyze(df, "XLE")
    assert signal.signal_type == SignalType.SELL


@pytest.mark.asyncio
async def test_hold_insufficient_data():
    s = SectorRotationStrategy()
    df = _make_df(10)
    signal = await s.analyze(df, "XLK")
    assert signal.signal_type == SignalType.HOLD


@pytest.mark.asyncio
async def test_hold_below_threshold():
    s = SectorRotationStrategy(params={"min_strength_score": 9999})
    df = _make_df(100, trend="up")
    signal = await s.analyze(df, "XLK")
    assert signal.signal_type in (SignalType.HOLD, SignalType.SELL)


@pytest.mark.asyncio
async def test_params():
    s = SectorRotationStrategy(params={"lookback_weeks": 8, "min_strength_score": 50})
    assert s.get_params()["lookback_weeks"] == 8
    s.set_params({"min_strength_score": 70})
    assert s.get_params()["min_strength_score"] == 70


@pytest.mark.asyncio
async def test_strategy_metadata():
    s = SectorRotationStrategy()
    assert s.name == "sector_rotation"
    assert s.display_name == "Sector Rotation"
    assert "trending" in s.applicable_market_types
