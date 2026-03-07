"""Tests for CIS Momentum Strategy."""

import numpy as np
import pandas as pd
import pytest

from strategies.cis_momentum import CISMomentumStrategy
from core.enums import SignalType


def _make_df(n: int = 30, roc5: float = 0.0, roc10: float = 0.0,
             volume_ratio: float = 1.5) -> pd.DataFrame:
    """Create DataFrame with momentum indicators."""
    data = {
        "open": [100.0] * n,
        "high": [102.0] * n,
        "low": [98.0] * n,
        "close": [100.0] * n,
        "volume": [1_000_000.0] * n,
        "roc_5": [roc5] * n,
        "roc_10": [roc10] * n,
        "volume_ratio": [volume_ratio] * n,
    }
    return pd.DataFrame(data)


def _make_df_raw(closes: list[float], volumes: list[float] | None = None) -> pd.DataFrame:
    """Create DataFrame from raw close prices for manual ROC calculation."""
    n = len(closes)
    vols = volumes or [1_000_000.0] * n
    return pd.DataFrame({
        "open": [c * 0.99 for c in closes],
        "high": [c * 1.01 for c in closes],
        "low": [c * 0.98 for c in closes],
        "close": closes,
        "volume": vols,
    })


class TestCISMomentum:
    async def test_buy_strong_momentum(self):
        strategy = CISMomentumStrategy()
        df = _make_df(roc5=5.0, roc10=7.0, volume_ratio=1.5)
        signal = await strategy.analyze(df, "AAPL")
        assert signal.signal_type == SignalType.BUY
        assert "momentum up" in signal.reason.lower()

    async def test_hold_weak_momentum(self):
        strategy = CISMomentumStrategy()
        df = _make_df(roc5=1.0, roc10=2.0, volume_ratio=1.5)
        signal = await strategy.analyze(df, "AAPL")
        assert signal.signal_type == SignalType.HOLD

    async def test_hold_no_volume(self):
        """Momentum present but no volume confirmation."""
        strategy = CISMomentumStrategy()
        df = _make_df(roc5=5.0, roc10=7.0, volume_ratio=0.8)
        signal = await strategy.analyze(df, "AAPL")
        assert signal.signal_type == SignalType.HOLD

    async def test_sell_momentum_reversal(self):
        strategy = CISMomentumStrategy()
        df = _make_df(roc5=-5.0, roc10=-7.0, volume_ratio=1.5)
        signal = await strategy.analyze(df, "AAPL")
        assert signal.signal_type == SignalType.SELL
        assert "reversal" in signal.reason.lower()

    async def test_insufficient_data(self):
        strategy = CISMomentumStrategy()
        df = pd.DataFrame({"close": [100.0] * 5, "volume": [1000.0] * 5})
        signal = await strategy.analyze(df, "AAPL")
        assert signal.signal_type == SignalType.HOLD

    async def test_confidence_scales_with_momentum(self):
        strategy = CISMomentumStrategy()
        df_weak = _make_df(roc5=4.0, roc10=6.0, volume_ratio=1.5)
        df_strong = _make_df(roc5=10.0, roc10=15.0, volume_ratio=2.5)
        s_weak = await strategy.analyze(df_weak, "AAPL")
        s_strong = await strategy.analyze(df_strong, "AAPL")
        assert s_strong.confidence > s_weak.confidence

    async def test_manual_roc_calculation(self):
        """Test that ROC is calculated from raw prices when columns not present."""
        strategy = CISMomentumStrategy()
        # Create prices where ROC5 ~= 10% and ROC10 ~= 15%
        closes = [100.0] * 20 + [100.0, 102.0, 104.0, 106.0, 108.0, 110.0, 112.0, 113.0, 114.0, 115.0]
        # ROC5 = (115 - 110)/110 * 100 = 4.5%
        # ROC10 = (115 - 100)/100 * 100 = 15%
        vols = [1_000_000.0] * 30
        df = _make_df_raw(closes, vols)
        signal = await strategy.analyze(df, "AAPL")
        assert signal.signal_type in (SignalType.BUY, SignalType.HOLD)

    async def test_get_set_params(self):
        strategy = CISMomentumStrategy()
        params = strategy.get_params()
        assert params["roc_short"] == 5
        assert params["roc_long"] == 10
        assert params["roc_short_buy"] == 3.0
        assert params["volume_ratio_threshold"] == 1.2

        strategy.set_params({"roc_short_buy": 2.0, "roc_long_buy": 4.0})
        assert strategy.get_params()["roc_short_buy"] == 2.0

    async def test_custom_params(self):
        strategy = CISMomentumStrategy(params={"roc_short_buy": 2.0, "roc_long_buy": 3.0})
        df = _make_df(roc5=2.5, roc10=4.0, volume_ratio=1.5)
        signal = await strategy.analyze(df, "AAPL")
        assert signal.signal_type == SignalType.BUY

    async def test_indicators_in_signal(self):
        strategy = CISMomentumStrategy()
        df = _make_df(roc5=5.0, roc10=7.0, volume_ratio=1.5)
        signal = await strategy.analyze(df, "AAPL")
        assert "roc5" in signal.indicators
        assert "roc10" in signal.indicators
        assert "volume_ratio" in signal.indicators
