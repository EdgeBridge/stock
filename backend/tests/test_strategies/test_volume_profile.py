"""Tests for Volume Profile Strategy."""

import pytest
import pandas as pd
import numpy as np

from strategies.volume_profile import VolumeProfileStrategy
from core.enums import SignalType


def _make_df(n=60, volume_ratio=1.0, up_day=True, obv_trend="up"):
    dates = pd.date_range("2023-01-01", periods=n, freq="B")
    if up_day:
        closes = 100 + np.arange(n) * 0.5
    else:
        closes = 150 - np.arange(n) * 0.5
    df = pd.DataFrame({
        "open": closes * 0.99,
        "high": closes * 1.01,
        "low": closes * 0.98,
        "close": closes,
        "volume": np.random.randint(1_000_000, 5_000_000, n),
    }, index=dates)
    df["volume_ratio"] = volume_ratio
    df["ema_20"] = df["close"].ewm(span=20).mean()
    df["rsi"] = 55.0
    if obv_trend == "up":
        df["obv"] = np.cumsum(np.random.uniform(100, 500, n))
    else:
        df["obv"] = np.cumsum(np.random.uniform(-500, -100, n))
    return df


@pytest.mark.asyncio
async def test_buy_volume_surge_up_day():
    s = VolumeProfileStrategy()
    df = _make_df(60, volume_ratio=2.5, up_day=True, obv_trend="up")
    signal = await s.analyze(df, "AAPL")
    assert signal.signal_type == SignalType.BUY
    assert "surge" in signal.reason.lower()


@pytest.mark.asyncio
async def test_sell_volume_surge_down_day():
    s = VolumeProfileStrategy()
    df = _make_df(60, volume_ratio=2.5, up_day=False, obv_trend="down")
    signal = await s.analyze(df, "AAPL")
    assert signal.signal_type == SignalType.SELL


@pytest.mark.asyncio
async def test_hold_low_volume():
    s = VolumeProfileStrategy()
    df = _make_df(60, volume_ratio=0.8, up_day=True, obv_trend="up")
    signal = await s.analyze(df, "AAPL")
    assert signal.signal_type == SignalType.HOLD


@pytest.mark.asyncio
async def test_hold_insufficient_data():
    s = VolumeProfileStrategy()
    df = _make_df(10, volume_ratio=2.5)
    signal = await s.analyze(df, "AAPL")
    assert signal.signal_type == SignalType.HOLD


@pytest.mark.asyncio
async def test_hold_no_volume_ratio():
    s = VolumeProfileStrategy()
    df = _make_df(60, volume_ratio=2.5)
    df["volume_ratio"] = np.nan
    signal = await s.analyze(df, "AAPL")
    assert signal.signal_type == SignalType.HOLD


@pytest.mark.asyncio
async def test_params():
    s = VolumeProfileStrategy(params={"volume_surge_threshold": 3.0, "obv_ma_period": 30})
    assert s.get_params()["volume_surge_threshold"] == 3.0
    s.set_params({"obv_ma_period": 10})
    assert s.get_params()["obv_ma_period"] == 10


@pytest.mark.asyncio
async def test_strategy_metadata():
    s = VolumeProfileStrategy()
    assert s.name == "volume_profile"
    assert s.display_name == "Volume Profile"
