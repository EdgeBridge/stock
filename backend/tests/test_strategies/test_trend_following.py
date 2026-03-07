"""Tests for Trend Following Strategy."""

import numpy as np
import pandas as pd
import pytest

from strategies.trend_following import TrendFollowingStrategy
from core.enums import SignalType


def _make_df(**overrides) -> pd.DataFrame:
    """Create a single-row DataFrame with indicator values."""
    data = {
        "close": 150.0,
        "ema_20": 145.0,
        "ema_50": 140.0,
        "ema_200": 130.0,
        "adx": 30.0,
        "volume_ratio": 1.5,
        "rsi": 55.0,
    }
    data.update(overrides)
    # Pad with enough rows to meet min_candles_required
    rows = [data] * 51
    return pd.DataFrame(rows)


class TestTrendFollowing:
    async def test_buy_signal_ema_aligned(self):
        strategy = TrendFollowingStrategy()
        df = _make_df()
        signal = await strategy.analyze(df, "AAPL")
        assert signal.signal_type == SignalType.BUY
        assert signal.confidence > 0.5
        assert "EMA aligned" in signal.reason

    async def test_hold_when_ema_not_aligned(self):
        strategy = TrendFollowingStrategy()
        df = _make_df(ema_20=155.0)  # price < ema_fast
        signal = await strategy.analyze(df, "AAPL")
        # Should sell (price < ema_fast)
        assert signal.signal_type == SignalType.SELL

    async def test_sell_when_price_below_ema(self):
        strategy = TrendFollowingStrategy()
        df = _make_df(close=140.0, ema_20=145.0, adx=15.0)
        signal = await strategy.analyze(df, "AAPL")
        assert signal.signal_type == SignalType.SELL

    async def test_hold_weak_adx(self):
        strategy = TrendFollowingStrategy()
        # EMA aligned but ADX too low for buy, not low enough for sell
        df = _make_df(adx=20.0)
        signal = await strategy.analyze(df, "AAPL")
        assert signal.signal_type == SignalType.HOLD

    async def test_hold_low_volume(self):
        strategy = TrendFollowingStrategy()
        df = _make_df(volume_ratio=0.5)
        signal = await strategy.analyze(df, "AAPL")
        assert signal.signal_type == SignalType.HOLD

    async def test_insufficient_data(self):
        strategy = TrendFollowingStrategy()
        df = pd.DataFrame({"close": [100.0] * 10})
        signal = await strategy.analyze(df, "AAPL")
        assert signal.signal_type == SignalType.HOLD

    async def test_confidence_higher_with_strong_adx(self):
        strategy = TrendFollowingStrategy()
        df_weak = _make_df(adx=26.0)
        df_strong = _make_df(adx=40.0)
        s_weak = await strategy.analyze(df_weak, "AAPL")
        s_strong = await strategy.analyze(df_strong, "AAPL")
        assert s_strong.confidence > s_weak.confidence

    async def test_custom_params(self):
        strategy = TrendFollowingStrategy(params={"adx_threshold": 15})
        df = _make_df(adx=18.0)
        signal = await strategy.analyze(df, "AAPL")
        assert signal.signal_type == SignalType.BUY

    async def test_get_set_params(self):
        strategy = TrendFollowingStrategy()
        params = strategy.get_params()
        assert params["ema_fast"] == 20
        assert params["adx_threshold"] == 25

        strategy.set_params({"adx_threshold": 30})
        assert strategy.get_params()["adx_threshold"] == 30

    async def test_indicators_in_signal(self):
        strategy = TrendFollowingStrategy()
        df = _make_df()
        signal = await strategy.analyze(df, "AAPL")
        assert "ema_fast" in signal.indicators
        assert "adx" in signal.indicators
