"""Tests for Regime Switch Strategy."""

import pytest
import pandas as pd
import numpy as np

from strategies.regime_switch import RegimeSwitchStrategy
from core.enums import SignalType


def _make_df(n=250, trend="up"):
    dates = pd.date_range("2023-01-01", periods=n, freq="B")
    if trend == "up":
        closes = 100 + np.arange(n) * 0.3
    elif trend == "down":
        closes = 200 - np.arange(n) * 0.3
    else:
        closes = 150 + np.random.uniform(-1, 1, n).cumsum() * 0.1
    df = pd.DataFrame({
        "open": closes * 0.99,
        "high": closes * 1.01,
        "low": closes * 0.98,
        "close": closes,
        "volume": np.random.randint(1_000_000, 5_000_000, n),
    }, index=dates)
    df["sma_200"] = df["close"].rolling(200).mean()
    df["sma_50"] = df["close"].rolling(50).mean()
    df["ema_20"] = df["close"].ewm(span=20).mean()
    df["adx"] = 30.0
    df["rsi"] = 55.0
    return df


@pytest.mark.asyncio
async def test_buy_bull_regime():
    s = RegimeSwitchStrategy(params={"confirmation_days": 2})
    df = _make_df(250, trend="up")
    signal = await s.analyze(df, "TQQQ")
    assert signal.signal_type == SignalType.BUY
    assert "Bull" in signal.reason


@pytest.mark.asyncio
async def test_sell_bear_regime():
    s = RegimeSwitchStrategy(params={"confirmation_days": 2})
    df = _make_df(250, trend="down")
    signal = await s.analyze(df, "SPY")
    assert signal.signal_type == SignalType.SELL
    assert "Bear" in signal.reason


@pytest.mark.asyncio
async def test_hold_insufficient_data():
    s = RegimeSwitchStrategy()
    df = _make_df(20, trend="up")
    signal = await s.analyze(df, "SPY")
    assert signal.signal_type == SignalType.HOLD


@pytest.mark.asyncio
async def test_hold_no_ma():
    s = RegimeSwitchStrategy()
    df = _make_df(60, trend="up")
    df.drop(columns=["sma_200", "sma_50"], inplace=True)
    signal = await s.analyze(df, "SPY")
    assert signal.signal_type == SignalType.HOLD


@pytest.mark.asyncio
async def test_params():
    s = RegimeSwitchStrategy(params={"spy_sma_period": 100, "confirmation_days": 5})
    assert s.get_params()["spy_sma_period"] == 100
    assert s.get_params()["confirmation_days"] == 5
    s.set_params({"vix_bull_threshold": 18})
    assert s.get_params()["vix_bull_threshold"] == 18


@pytest.mark.asyncio
async def test_strategy_metadata():
    s = RegimeSwitchStrategy()
    assert s.name == "regime_switch"
    assert "all" in s.applicable_market_types
