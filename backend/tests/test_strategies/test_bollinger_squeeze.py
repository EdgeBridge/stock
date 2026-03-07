"""Tests for Bollinger Squeeze Strategy."""

import pytest
import pandas as pd
import numpy as np

from strategies.bollinger_squeeze import BollingerSqueezeStrategy
from core.enums import SignalType


def _make_df(n=60, in_squeeze=False, squeeze_bars=0, breakout_up=False, breakout_down=False):
    """Create DataFrame with BB and KC data."""
    dates = pd.date_range("2023-01-01", periods=n, freq="B")
    closes = 100 + np.random.uniform(-0.5, 0.5, n).cumsum()
    df = pd.DataFrame({
        "open": closes * 0.99,
        "high": closes * 1.01,
        "low": closes * 0.98,
        "close": closes,
        "volume": np.random.randint(1_000_000, 5_000_000, n),
    }, index=dates)

    # Base BB and KC
    for i in range(n):
        mid = closes[i]
        if in_squeeze or (i < n - 1 and i >= n - 1 - squeeze_bars):
            # Squeeze: BB inside KC
            df.loc[df.index[i], "bb_upper"] = mid + 1
            df.loc[df.index[i], "bb_lower"] = mid - 1
            df.loc[df.index[i], "kc_upper"] = mid + 2
            df.loc[df.index[i], "kc_lower"] = mid - 2
        else:
            # No squeeze: BB outside KC
            df.loc[df.index[i], "bb_upper"] = mid + 3
            df.loc[df.index[i], "bb_lower"] = mid - 3
            df.loc[df.index[i], "kc_upper"] = mid + 2
            df.loc[df.index[i], "kc_lower"] = mid - 2

        df.loc[df.index[i], "bb_mid"] = mid

    if breakout_up:
        # Last bar: no squeeze, price > bb_upper
        last_mid = closes[-1]
        df.loc[df.index[-1], "bb_upper"] = last_mid - 1  # price above
        df.loc[df.index[-1], "bb_lower"] = last_mid - 5
        df.loc[df.index[-1], "kc_upper"] = last_mid + 2
        df.loc[df.index[-1], "kc_lower"] = last_mid - 6

    if breakout_down:
        last_mid = closes[-1]
        df.loc[df.index[-1], "bb_lower"] = last_mid + 1  # price below
        df.loc[df.index[-1], "bb_upper"] = last_mid + 5
        df.loc[df.index[-1], "kc_upper"] = last_mid + 6
        df.loc[df.index[-1], "kc_lower"] = last_mid - 2

    df["macd_histogram"] = 0.5 if breakout_up else -0.5
    return df


@pytest.mark.asyncio
async def test_hold_no_squeeze():
    s = BollingerSqueezeStrategy()
    df = _make_df(60, in_squeeze=False, squeeze_bars=0)
    signal = await s.analyze(df, "AAPL")
    assert signal.signal_type == SignalType.HOLD


@pytest.mark.asyncio
async def test_hold_during_squeeze():
    s = BollingerSqueezeStrategy()
    df = _make_df(60, in_squeeze=True)
    signal = await s.analyze(df, "AAPL")
    assert signal.signal_type == SignalType.HOLD


@pytest.mark.asyncio
async def test_buy_squeeze_breakout_up():
    """Squeeze was active for several bars, now released with upward breakout."""
    s = BollingerSqueezeStrategy(params={"squeeze_min_bars": 3})
    n = 60
    dates = pd.date_range("2023-01-01", periods=n, freq="B")
    closes = np.full(n, 100.0)
    closes[-1] = 105.0  # breakout bar
    df = pd.DataFrame({
        "open": closes * 0.99,
        "high": closes * 1.01,
        "low": closes * 0.98,
        "close": closes,
        "volume": np.random.randint(1_000_000, 5_000_000, n),
    }, index=dates)
    mid = 100.0
    # Previous bars: BB inside KC (squeeze)
    for i in range(n):
        if i < n - 1:
            # Squeeze bars
            df.loc[df.index[i], "bb_upper"] = mid + 1
            df.loc[df.index[i], "bb_lower"] = mid - 1
            df.loc[df.index[i], "kc_upper"] = mid + 2
            df.loc[df.index[i], "kc_lower"] = mid - 2
        else:
            # Last bar: squeeze released, BB expands beyond KC
            df.loc[df.index[i], "bb_upper"] = 103.0  # price 105 > bb_upper 103
            df.loc[df.index[i], "bb_lower"] = 97.0
            df.loc[df.index[i], "kc_upper"] = 102.5
            df.loc[df.index[i], "kc_lower"] = 97.5
        df.loc[df.index[i], "bb_mid"] = mid
    df["macd_histogram"] = 0.5
    signal = await s.analyze(df, "AAPL")
    assert signal.signal_type == SignalType.BUY


@pytest.mark.asyncio
async def test_hold_insufficient_data():
    s = BollingerSqueezeStrategy()
    df = _make_df(10)
    signal = await s.analyze(df, "AAPL")
    assert signal.signal_type == SignalType.HOLD


@pytest.mark.asyncio
async def test_params():
    s = BollingerSqueezeStrategy(params={"squeeze_min_bars": 10})
    assert s.get_params()["squeeze_min_bars"] == 10
    s.set_params({"squeeze_min_bars": 4})
    assert s.get_params()["squeeze_min_bars"] == 4


@pytest.mark.asyncio
async def test_strategy_metadata():
    s = BollingerSqueezeStrategy()
    assert s.name == "bollinger_squeeze"
    assert "sideways" in s.applicable_market_types
