"""Tests for Donchian Breakout Strategy (enhanced with ADX/volume/channel width)."""

import numpy as np
import pandas as pd
import pytest

from strategies.donchian_breakout import DonchianBreakoutStrategy
from core.enums import SignalType


def _make_df(
    n: int = 35,
    close: float = 110.0,
    donchian_upper: float = 105.0,
    donchian_lower: float = 90.0,
    prev_close: float = 104.0,
    prev_upper: float = 105.0,
    adx: float = 30.0,
    volume_ratio: float = 2.0,
    atr: float = 2.0,
) -> pd.DataFrame:
    """Create DataFrame with breakout scenario."""
    data = []
    for i in range(n - 2):
        data.append({
            "open": 100.0, "high": 103.0, "low": 97.0,
            "close": 100.0, "volume": 1_000_000.0,
            "donchian_upper": 105.0, "donchian_lower": 90.0,
            "donchian_mid": 97.5, "atr": atr, "adx": adx,
            "volume_ratio": 1.2,
        })
    # Previous bar
    data.append({
        "open": 103.0, "high": 105.0, "low": 102.0,
        "close": prev_close, "volume": 1_200_000.0,
        "donchian_upper": prev_upper, "donchian_lower": 90.0,
        "donchian_mid": 97.5, "atr": atr, "adx": adx,
        "volume_ratio": 1.5,
    })
    # Current bar
    data.append({
        "open": 105.0, "high": 112.0, "low": 104.0,
        "close": close, "volume": 2_000_000.0,
        "donchian_upper": donchian_upper, "donchian_lower": donchian_lower,
        "donchian_mid": 100.0, "atr": atr, "adx": adx,
        "volume_ratio": volume_ratio,
    })
    return pd.DataFrame(data)


class TestDonchianBreakout:
    async def test_buy_on_breakout(self):
        strategy = DonchianBreakoutStrategy()
        df = _make_df(close=110.0, donchian_upper=105.0,
                      prev_close=104.0, prev_upper=105.0)
        signal = await strategy.analyze(df, "AAPL")
        assert signal.signal_type == SignalType.BUY
        assert "breakout" in signal.reason.lower()

    async def test_hold_no_breakout(self):
        strategy = DonchianBreakoutStrategy()
        df = _make_df(close=103.0, donchian_upper=105.0)
        signal = await strategy.analyze(df, "AAPL")
        assert signal.signal_type == SignalType.HOLD

    async def test_sell_below_donchian_lower(self):
        strategy = DonchianBreakoutStrategy()
        df = _make_df(close=85.0, donchian_upper=105.0, donchian_lower=90.0)
        signal = await strategy.analyze(df, "AAPL")
        assert signal.signal_type == SignalType.SELL
        assert "lower" in signal.reason.lower()

    async def test_sell_turtle_exit(self):
        """Price below exit-period low triggers turtle exit."""
        strategy = DonchianBreakoutStrategy()
        # close=91 is above donchian_lower=90 but below recent lows (97)
        df = _make_df(close=91.0, donchian_upper=105.0, donchian_lower=85.0)
        signal = await strategy.analyze(df, "AAPL")
        assert signal.signal_type == SignalType.SELL
        assert "turtle" in signal.reason.lower() or "exit" in signal.reason.lower()

    async def test_insufficient_data(self):
        strategy = DonchianBreakoutStrategy()
        df = pd.DataFrame({"close": [100.0] * 5})
        signal = await strategy.analyze(df, "AAPL")
        assert signal.signal_type == SignalType.HOLD

    async def test_confidence_higher_with_adx(self):
        strategy = DonchianBreakoutStrategy()
        df_weak = _make_df(close=110.0, adx=15.0, volume_ratio=1.0)
        df_strong = _make_df(close=110.0, adx=35.0, volume_ratio=2.0)
        s_weak = await strategy.analyze(df_weak, "AAPL")
        s_strong = await strategy.analyze(df_strong, "AAPL")
        assert s_strong.confidence > s_weak.confidence

    async def test_confidence_higher_with_wide_channel(self):
        strategy = DonchianBreakoutStrategy()
        # Narrow channel: 1% width (105 vs 104), wide: 31% width (105 vs 80)
        # Low ADX, low volume, large ATR to isolate channel width effect
        df_narrow = _make_df(close=110.0, donchian_lower=104.0, adx=15.0, volume_ratio=1.0, atr=100.0)
        df_wide = _make_df(close=110.0, donchian_lower=80.0, adx=15.0, volume_ratio=1.0, atr=100.0)
        s_narrow = await strategy.analyze(df_narrow, "AAPL")
        s_wide = await strategy.analyze(df_wide, "AAPL")
        assert s_wide.confidence > s_narrow.confidence

    async def test_channel_width_in_indicators(self):
        strategy = DonchianBreakoutStrategy()
        df = _make_df(close=110.0)
        signal = await strategy.analyze(df, "AAPL")
        assert "channel_width_pct" in signal.indicators

    async def test_get_set_params(self):
        strategy = DonchianBreakoutStrategy()
        params = strategy.get_params()
        assert params["entry_period"] == 20
        assert params["exit_period"] == 10
        assert params["adx_threshold"] == 25.0
        assert params["volume_multiplier"] == 1.5

        strategy.set_params({"entry_period": 30, "exit_period": 15, "adx_threshold": 30.0})
        assert strategy.get_params()["entry_period"] == 30
        assert strategy.get_params()["adx_threshold"] == 30.0

    async def test_custom_params(self):
        strategy = DonchianBreakoutStrategy(params={"adx_threshold": 20.0, "volume_multiplier": 1.2})
        assert strategy.get_params()["adx_threshold"] == 20.0
        assert strategy.get_params()["volume_multiplier"] == 1.2
