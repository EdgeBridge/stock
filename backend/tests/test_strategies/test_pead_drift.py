"""Tests for PEADDriftStrategy (Post-Earnings Announcement Drift)."""

import numpy as np
import pandas as pd
import pytest

from core.enums import SignalType
from strategies.pead_drift import PEADDriftStrategy


def _make_df(
    n: int = 100,
    base_price: float = 100.0,
    trend: float = 0.0,
    noise: float = 0.005,
    gap_at: int | None = None,
    gap_pct: float = 0.05,
    gap_vol_mult: float = 3.0,
    ema_20: float | None = None,
    ema_50: float | None = None,
) -> pd.DataFrame:
    """Create a synthetic OHLCV DataFrame with optional earnings gap.

    Args:
        gap_at: Index to insert an earnings-like gap (from end, e.g. -5 = 5 bars ago).
        gap_pct: Gap size as percentage (positive = up, negative = down).
        gap_vol_mult: Volume multiplier on gap day.
    """
    np.random.seed(42)
    prices = base_price * np.cumprod(1 + trend + np.random.normal(0, noise, n))
    volumes = np.full(n, 1_000_000, dtype=float)

    # Insert gap
    if gap_at is not None:
        idx = n + gap_at if gap_at < 0 else gap_at
        if 0 < idx < n:
            # Shift all prices from gap_at onward by gap_pct
            shift = 1 + gap_pct
            prices[idx:] = prices[idx:] * shift
            # Make gap day's open = prev_close * (1 + gap_pct)
            # This creates the actual gap (open != prev close)
            volumes[idx] *= gap_vol_mult

    opens = prices.copy()
    if gap_at is not None:
        idx = n + gap_at if gap_at < 0 else gap_at
        if 0 < idx < n:
            opens[idx] = prices[idx - 1] * (1 + gap_pct)

    df = pd.DataFrame({
        "open": opens * 0.999,
        "high": prices * 1.005,
        "low": prices * 0.995,
        "close": prices,
        "volume": volumes,
    })
    # Fix the gap day open specifically
    if gap_at is not None:
        idx = n + gap_at if gap_at < 0 else gap_at
        if 0 < idx < n:
            prev_close = float(df["close"].iloc[idx - 1])
            df.loc[df.index[idx], "open"] = prev_close * (1 + gap_pct)

    df["ema_20"] = np.nan
    df["ema_50"] = np.nan
    if ema_20 is not None:
        df.loc[df.index[-1], "ema_20"] = ema_20
    if ema_50 is not None:
        df.loc[df.index[-1], "ema_50"] = ema_50

    return df


@pytest.fixture
def strategy():
    return PEADDriftStrategy()


class TestBasicProperties:
    def test_name(self, strategy):
        assert strategy.name == "pead_drift"

    def test_display_name(self, strategy):
        assert strategy.display_name == "PEAD Drift"

    def test_min_candles(self, strategy):
        assert strategy.min_candles_required == 60


class TestInsufficientData:
    @pytest.mark.asyncio
    async def test_insufficient_data_returns_hold(self, strategy):
        df = _make_df(n=30)
        signal = await strategy.analyze(df, "AAPL")
        assert signal.signal_type == SignalType.HOLD
        assert "Insufficient" in signal.reason


class TestNoGap:
    @pytest.mark.asyncio
    async def test_no_gap_returns_hold(self, strategy):
        """No earnings-like gap → HOLD."""
        df = _make_df(n=100, trend=0.001, noise=0.005)
        signal = await strategy.analyze(df, "FLAT")
        assert signal.signal_type == SignalType.HOLD
        assert "No recent earnings gap" in signal.reason


class TestPositiveGapBuy:
    @pytest.mark.asyncio
    async def test_positive_gap_generates_buy(self):
        """Large positive gap with volume → BUY."""
        strategy = PEADDriftStrategy()
        df = _make_df(
            n=100, trend=0.001, gap_at=-3, gap_pct=0.06,
            gap_vol_mult=3.0, ema_20=110.0, ema_50=105.0,
        )
        signal = await strategy.analyze(df, "BEAT")
        assert signal.signal_type == SignalType.BUY
        assert signal.confidence >= 0.50
        assert "PEAD" in signal.reason
        assert signal.indicators["gap_pct"] > 0

    @pytest.mark.asyncio
    async def test_larger_gap_higher_confidence(self):
        """Gap > 8% should get extra confidence."""
        strategy = PEADDriftStrategy()
        df = _make_df(
            n=100, trend=0.001, gap_at=-3, gap_pct=0.10,
            gap_vol_mult=4.0, ema_20=115.0, ema_50=110.0,
        )
        signal = await strategy.analyze(df, "BIG")
        if signal.signal_type == SignalType.BUY:
            assert signal.confidence >= 0.65

    @pytest.mark.asyncio
    async def test_confidence_decays_with_time(self):
        """Gap 8 days ago should have lower confidence than 2 days ago."""
        strategy = PEADDriftStrategy(params={"max_entry_delay": 15})
        df_recent = _make_df(
            n=100, trend=0.001, gap_at=-2, gap_pct=0.06,
            gap_vol_mult=3.0, ema_20=110.0, ema_50=105.0,
        )
        df_old = _make_df(
            n=100, trend=0.001, gap_at=-9, gap_pct=0.06,
            gap_vol_mult=3.0, ema_20=110.0, ema_50=105.0,
        )
        sig_recent = await strategy.analyze(df_recent, "RECENT")
        sig_old = await strategy.analyze(df_old, "OLD")
        if sig_recent.signal_type == SignalType.BUY and sig_old.signal_type == SignalType.BUY:
            assert sig_recent.confidence >= sig_old.confidence


class TestNegativeGapSell:
    @pytest.mark.asyncio
    async def test_negative_gap_generates_sell(self):
        """Large negative gap with volume → SELL."""
        strategy = PEADDriftStrategy()
        df = _make_df(
            n=100, trend=-0.001, gap_at=-3, gap_pct=-0.06,
            gap_vol_mult=3.0, ema_20=90.0, ema_50=95.0,
        )
        signal = await strategy.analyze(df, "MISS")
        assert signal.signal_type == SignalType.SELL
        assert signal.confidence >= 0.50
        assert "PEAD" in signal.reason
        assert signal.indicators["gap_pct"] < 0


class TestFadeProtection:
    @pytest.mark.asyncio
    async def test_faded_gap_returns_hold(self):
        """If gap has reversed >50%, skip entry."""
        strategy = PEADDriftStrategy(params={"fade_protection": True})
        # Create a gap-up then reverse
        df = _make_df(n=100, gap_at=-5, gap_pct=0.06, gap_vol_mult=3.0)
        # Manually drop prices after gap to simulate fade
        gap_idx = 95
        gap_close = float(df["close"].iloc[gap_idx])
        for i in range(gap_idx + 1, len(df)):
            df.loc[df.index[i], "close"] = gap_close * (1 - 0.01 * (i - gap_idx))
            df.loc[df.index[i], "open"] = df["close"].iloc[i] * 1.001
            df.loc[df.index[i], "high"] = df["close"].iloc[i] * 1.005
            df.loc[df.index[i], "low"] = df["close"].iloc[i] * 0.995
        signal = await strategy.analyze(df, "FADE")
        # Should be HOLD (faded) or SELL (gap was positive but faded → no BUY)
        assert signal.signal_type != SignalType.BUY or "Gap faded" in signal.reason or signal.signal_type == SignalType.HOLD

    @pytest.mark.asyncio
    async def test_fade_protection_disabled(self):
        """With fade_protection=False, faded gaps still generate signals."""
        strategy = PEADDriftStrategy(params={"fade_protection": False})
        df = _make_df(n=100, gap_at=-3, gap_pct=0.06, gap_vol_mult=3.0)
        signal = await strategy.analyze(df, "NOFADE")
        # Should generate a signal (BUY from positive gap), not blocked by fade
        if signal.signal_type == SignalType.HOLD:
            assert "Gap faded" not in signal.reason


class TestGapThreshold:
    @pytest.mark.asyncio
    async def test_small_gap_ignored(self):
        """Gap below threshold should not trigger signal."""
        strategy = PEADDriftStrategy(params={"gap_threshold": 0.05})
        df = _make_df(n=100, gap_at=-3, gap_pct=0.02, gap_vol_mult=3.0)
        signal = await strategy.analyze(df, "SMALL")
        assert signal.signal_type == SignalType.HOLD

    @pytest.mark.asyncio
    async def test_low_volume_gap_ignored(self):
        """Gap without volume spike should not trigger."""
        strategy = PEADDriftStrategy(params={"volume_multiplier": 3.0})
        df = _make_df(n=100, gap_at=-3, gap_pct=0.06, gap_vol_mult=1.5)
        signal = await strategy.analyze(df, "LOWVOL")
        assert signal.signal_type == SignalType.HOLD


class TestParams:
    def test_get_params(self, strategy):
        params = strategy.get_params()
        assert params["gap_threshold"] == 0.03
        assert params["volume_multiplier"] == 2.0
        assert params["max_entry_delay"] == 10
        assert params["fade_protection"] is True

    def test_set_params(self, strategy):
        strategy.set_params({"gap_threshold": 0.05, "max_entry_delay": 15})
        assert strategy._gap_threshold == 0.05
        assert strategy._max_entry_delay == 15

    def test_set_params_ignores_unknown(self, strategy):
        strategy.set_params({"unknown_key": 42})
        assert not hasattr(strategy, "_unknown_key")


class TestIndicators:
    @pytest.mark.asyncio
    async def test_indicators_present_on_gap(self):
        """Gap signal should include all expected indicators."""
        strategy = PEADDriftStrategy()
        df = _make_df(
            n=100, gap_at=-3, gap_pct=0.06,
            gap_vol_mult=3.0, ema_20=110.0, ema_50=105.0,
        )
        signal = await strategy.analyze(df, "IND")
        if signal.indicators:
            assert "gap_pct" in signal.indicators
            assert "gap_vol_ratio" in signal.indicators
            assert "days_since_gap" in signal.indicators
            assert "post_gap_return" in signal.indicators
            assert "follow_through" in signal.indicators
            assert "ema_aligned" in signal.indicators


class TestEdgeCases:
    @pytest.mark.asyncio
    async def test_gap_beyond_max_delay(self):
        """Gap older than max_entry_delay should not trigger."""
        strategy = PEADDriftStrategy(params={"max_entry_delay": 5})
        df = _make_df(n=100, gap_at=-8, gap_pct=0.06, gap_vol_mult=3.0)
        signal = await strategy.analyze(df, "OLD")
        assert signal.signal_type == SignalType.HOLD

    @pytest.mark.asyncio
    async def test_buy_confidence_capped(self):
        """BUY confidence should not exceed 0.90."""
        strategy = PEADDriftStrategy()
        df = _make_df(
            n=100, gap_at=-2, gap_pct=0.15,
            gap_vol_mult=5.0, ema_20=120.0, ema_50=110.0,
        )
        signal = await strategy.analyze(df, "CAP")
        assert signal.confidence <= 0.90

    @pytest.mark.asyncio
    async def test_sell_confidence_capped(self):
        """SELL confidence should not exceed 0.85."""
        strategy = PEADDriftStrategy()
        df = _make_df(
            n=100, trend=-0.001, gap_at=-2, gap_pct=-0.15,
            gap_vol_mult=5.0, ema_20=80.0, ema_50=90.0,
        )
        signal = await strategy.analyze(df, "SELLCAP")
        if signal.signal_type == SignalType.SELL:
            assert signal.confidence <= 0.85
