"""Tests for Volume Profile Strategy."""

import numpy as np
import pandas as pd
import pytest

from core.enums import SignalType
from strategies.volume_profile import VolumeProfileStrategy


def _make_df(
    n=60,
    volume_ratio=1.0,
    up_day=True,
    obv_trend="up",
    volume_base=2_000_000,
    last_volume=None,
):
    dates = pd.date_range("2023-01-01", periods=n, freq="B")
    if up_day:
        closes = 100 + np.arange(n) * 0.5
    else:
        closes = 150 - np.arange(n) * 0.5
    volumes = np.full(n, volume_base)
    if last_volume is not None:
        volumes[-1] = last_volume
    df = pd.DataFrame(
        {
            "open": closes * 0.99,
            "high": closes * 1.01,
            "low": closes * 0.98,
            "close": closes,
            "volume": volumes,
        },
        index=dates,
    )
    df["volume_ratio"] = volume_ratio
    df["ema_20"] = df["close"].ewm(span=20).mean()
    df["rsi"] = 55.0
    if obv_trend == "up":
        df["obv"] = np.cumsum(
            np.random.uniform(100, 500, n)
        )
    else:
        df["obv"] = np.cumsum(
            np.random.uniform(-500, -100, n)
        )
    return df


@pytest.mark.asyncio
async def test_buy_volume_surge_up_day():
    s = VolumeProfileStrategy()
    df = _make_df(
        60, volume_ratio=2.5, up_day=True, obv_trend="up"
    )
    signal = await s.analyze(df, "AAPL")
    assert signal.signal_type == SignalType.BUY
    assert "surge" in signal.reason.lower()


@pytest.mark.asyncio
async def test_sell_volume_surge_down_day():
    s = VolumeProfileStrategy()
    df = _make_df(
        60,
        volume_ratio=2.5,
        up_day=False,
        obv_trend="down",
    )
    signal = await s.analyze(df, "AAPL")
    assert signal.signal_type == SignalType.SELL


@pytest.mark.asyncio
async def test_hold_low_volume():
    s = VolumeProfileStrategy()
    df = _make_df(
        60, volume_ratio=0.8, up_day=True, obv_trend="up"
    )
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
    s = VolumeProfileStrategy(
        params={
            "volume_surge_threshold": 3.0,
            "obv_ma_period": 30,
        }
    )
    assert s.get_params()["volume_surge_threshold"] == 3.0
    s.set_params({"obv_ma_period": 10})
    assert s.get_params()["obv_ma_period"] == 10


@pytest.mark.asyncio
async def test_strategy_metadata():
    s = VolumeProfileStrategy()
    assert s.name == "volume_profile"
    assert s.display_name == "Volume Profile"


# --- OBV acceleration tests ---


@pytest.mark.asyncio
async def test_obv_acceleration_indicator_present():
    """OBV acceleration indicator should be in output."""
    s = VolumeProfileStrategy()
    df = _make_df(
        60, volume_ratio=2.5, up_day=True, obv_trend="up"
    )
    signal = await s.analyze(df, "AAPL")
    assert "obv_acceleration" in signal.indicators


@pytest.mark.asyncio
async def test_obv_acceleration_positive_boosts_buy():
    """Positive OBV accel should boost BUY confidence."""
    s = VolumeProfileStrategy()
    # Create df with accelerating OBV (quadratic growth)
    n = 60
    dates = pd.date_range(
        "2023-01-01", periods=n, freq="B"
    )
    closes = 100 + np.arange(n) * 0.5
    df = pd.DataFrame(
        {
            "open": closes * 0.99,
            "high": closes * 1.01,
            "low": closes * 0.98,
            "close": closes,
            "volume": np.full(n, 2_000_000),
        },
        index=dates,
    )
    df["volume_ratio"] = 2.5
    df["ema_20"] = df["close"].ewm(span=20).mean()
    df["rsi"] = 55.0
    # Quadratic OBV -> positive acceleration
    df["obv"] = (np.arange(n) ** 2) * 100.0

    signal = await s.analyze(df, "AAPL")
    assert signal.signal_type == SignalType.BUY
    assert signal.indicators["obv_acceleration"] > 0
    # Base BUY = 0.55 + 0.10(ema) + 0.05(rsi) + 0.05(accel)
    assert signal.confidence >= 0.70


@pytest.mark.asyncio
async def test_obv_acceleration_negative_boosts_sell():
    """Negative OBV accel should boost SELL confidence."""
    s = VolumeProfileStrategy()
    n = 60
    dates = pd.date_range(
        "2023-01-01", periods=n, freq="B"
    )
    # Down day
    closes = 150 - np.arange(n) * 0.5
    df = pd.DataFrame(
        {
            "open": closes * 1.01,
            "high": closes * 1.01,
            "low": closes * 0.98,
            "close": closes,
            "volume": np.full(n, 2_000_000),
        },
        index=dates,
    )
    df["volume_ratio"] = 2.5
    df["ema_20"] = df["close"].ewm(span=20).mean()
    df["rsi"] = 55.0
    # Negative quadratic OBV -> negative acceleration
    df["obv"] = -((np.arange(n) ** 2) * 100.0)

    signal = await s.analyze(df, "AAPL")
    assert signal.signal_type == SignalType.SELL
    assert signal.indicators["obv_acceleration"] < 0
    # Base SELL = 0.55 + 0.05(accel)
    assert signal.confidence >= 0.55


@pytest.mark.asyncio
async def test_obv_acceleration_no_obv_column():
    """No OBV column -> acceleration is None."""
    s = VolumeProfileStrategy()
    df = _make_df(
        60, volume_ratio=0.5, up_day=True, obv_trend="up"
    )
    df.drop(columns=["obv"], inplace=True)
    signal = await s.analyze(df, "AAPL")
    assert "obv_acceleration" not in signal.indicators


@pytest.mark.asyncio
async def test_obv_acceleration_insufficient_data():
    """Not enough data for acceleration calculation."""
    s = VolumeProfileStrategy(
        params={"obv_accel_period": 50}
    )
    df = _make_df(
        30, volume_ratio=0.5, up_day=True, obv_trend="up"
    )
    signal = await s.analyze(df, "AAPL")
    # With period=50, need 52 bars, only 30 -> no accel
    assert "obv_acceleration" not in signal.indicators


# --- Volume intensity tests ---


@pytest.mark.asyncio
async def test_volume_intensity_indicator_present():
    """Volume intensity should be in indicators."""
    s = VolumeProfileStrategy()
    df = _make_df(
        60, volume_ratio=2.5, up_day=True, obv_trend="up"
    )
    signal = await s.analyze(df, "AAPL")
    assert "volume_intensity" in signal.indicators


@pytest.mark.asyncio
async def test_volume_intensity_high_boosts_confidence():
    """High volume intensity should boost confidence."""
    s = VolumeProfileStrategy()

    # Low volume intensity (all same volume)
    df_base = _make_df(
        60,
        volume_ratio=2.5,
        up_day=True,
        obv_trend="up",
        volume_base=2_000_000,
    )
    # Make OBV deterministic for comparison
    df_base["obv"] = np.cumsum(np.full(60, 300.0))
    signal_base = await s.analyze(df_base, "AAPL")

    # High volume intensity (last bar 4x average)
    df_high = _make_df(
        60,
        volume_ratio=2.5,
        up_day=True,
        obv_trend="up",
        volume_base=2_000_000,
        last_volume=8_000_000,
    )
    df_high["obv"] = np.cumsum(np.full(60, 300.0))
    signal_high = await s.analyze(df_high, "AAPL")

    assert signal_base.signal_type == SignalType.BUY
    assert signal_high.signal_type == SignalType.BUY
    # High volume should give higher confidence
    assert signal_high.confidence > signal_base.confidence
    # Volume intensity should reflect the higher vol
    assert (
        signal_high.indicators["volume_intensity"]
        > signal_base.indicators["volume_intensity"]
    )


@pytest.mark.asyncio
async def test_volume_intensity_low_dampens_confidence():
    """Low volume intensity should dampen confidence."""
    s = VolumeProfileStrategy()

    # Normal volume
    df_base = _make_df(
        60,
        volume_ratio=2.5,
        up_day=True,
        obv_trend="up",
        volume_base=2_000_000,
    )
    df_base["obv"] = np.cumsum(np.full(60, 300.0))
    signal_base = await s.analyze(df_base, "AAPL")

    # Low last-bar volume (0.25x average)
    df_low = _make_df(
        60,
        volume_ratio=2.5,
        up_day=True,
        obv_trend="up",
        volume_base=2_000_000,
        last_volume=500_000,
    )
    df_low["obv"] = np.cumsum(np.full(60, 300.0))
    signal_low = await s.analyze(df_low, "AAPL")

    assert signal_base.signal_type == SignalType.BUY
    assert signal_low.signal_type == SignalType.BUY
    # Low volume should give lower confidence
    assert signal_low.confidence < signal_base.confidence


@pytest.mark.asyncio
async def test_volume_intensity_cap():
    """Volume intensity should be capped."""
    s = VolumeProfileStrategy(
        params={"volume_intensity_cap": 1.5}
    )
    df = _make_df(
        60,
        volume_ratio=2.5,
        up_day=True,
        obv_trend="up",
        volume_base=1_000_000,
        last_volume=100_000_000,  # 100x average
    )
    df["obv"] = np.cumsum(np.full(60, 300.0))
    signal = await s.analyze(df, "AAPL")
    # Even extreme volume shouldn't push confidence > 0.95
    assert signal.confidence <= 0.95


@pytest.mark.asyncio
async def test_volume_intensity_no_volume_column():
    """No volume column -> intensity not calculated."""
    s = VolumeProfileStrategy()
    df = _make_df(
        60, volume_ratio=0.5, up_day=True, obv_trend="up"
    )
    df.drop(columns=["volume"], inplace=True)
    signal = await s.analyze(df, "AAPL")
    assert "volume_intensity" not in signal.indicators


# --- Params tests for new params ---


@pytest.mark.asyncio
async def test_new_params_get_set():
    """New params should be gettable and settable."""
    s = VolumeProfileStrategy(
        params={
            "obv_accel_period": 10,
            "volume_intensity_cap": 2.0,
        }
    )
    p = s.get_params()
    assert p["obv_accel_period"] == 10
    assert p["volume_intensity_cap"] == 2.0

    s.set_params(
        {
            "obv_accel_period": 3,
            "volume_intensity_cap": 1.1,
        }
    )
    p = s.get_params()
    assert p["obv_accel_period"] == 3
    assert p["volume_intensity_cap"] == 1.1


@pytest.mark.asyncio
async def test_sell_volume_intensity_scaling():
    """Volume intensity should also scale SELL signals."""
    s = VolumeProfileStrategy()

    # Normal volume sell
    df_base = _make_df(
        60,
        volume_ratio=2.5,
        up_day=False,
        obv_trend="down",
        volume_base=2_000_000,
    )
    df_base["obv"] = np.cumsum(np.full(60, -300.0))
    signal_base = await s.analyze(df_base, "AAPL")

    # High volume sell
    df_high = _make_df(
        60,
        volume_ratio=2.5,
        up_day=False,
        obv_trend="down",
        volume_base=2_000_000,
        last_volume=8_000_000,
    )
    df_high["obv"] = np.cumsum(np.full(60, -300.0))
    signal_high = await s.analyze(df_high, "AAPL")

    assert signal_base.signal_type == SignalType.SELL
    assert signal_high.signal_type == SignalType.SELL
    assert signal_high.confidence > signal_base.confidence


@pytest.mark.asyncio
async def test_obv_accel_with_nan_obv():
    """OBV column with NaN values -> no acceleration."""
    s = VolumeProfileStrategy()
    df = _make_df(
        60, volume_ratio=0.5, up_day=True, obv_trend="up"
    )
    # Inject NaN in recent OBV values
    df.loc[df.index[-3:], "obv"] = np.nan
    signal = await s.analyze(df, "AAPL")
    assert "obv_acceleration" not in signal.indicators
