"""Tests for Market State Detector."""

import numpy as np
import pandas as pd
import pytest

from data.market_state import MarketStateDetector, MarketRegime


def _make_spy_df(n: int = 250, trend: str = "up") -> pd.DataFrame:
    """Create mock SPY data."""
    np.random.seed(42)
    if trend == "up":
        close = 400 * np.cumprod(1 + np.random.normal(0.001, 0.008, n))
    elif trend == "down":
        close = 500 * np.cumprod(1 + np.random.normal(-0.001, 0.008, n))
    else:  # sideways
        close = 450 + np.random.normal(0, 3, n).cumsum() * 0.1
        close = np.clip(close, 430, 470)

    return pd.DataFrame({
        "open": close * 0.999,
        "high": close * 1.005,
        "low": close * 0.995,
        "close": close,
        "volume": np.random.randint(50_000_000, 100_000_000, n).astype(float),
    })


class TestMarketStateDetector:
    def test_strong_uptrend(self):
        detector = MarketStateDetector(confirmation_days=0)
        df = _make_spy_df(250, "up")
        state = detector.detect(df, vix_level=15.0)
        assert state.regime == MarketRegime.STRONG_UPTREND
        assert state.spy_above_sma200 is True
        assert state.vix_level == 15.0

    def test_downtrend(self):
        detector = MarketStateDetector(confirmation_days=0)
        df = _make_spy_df(250, "down")
        state = detector.detect(df, vix_level=32.0)
        assert state.regime == MarketRegime.DOWNTREND
        assert state.spy_above_sma200 is False

    def test_sideways(self):
        detector = MarketStateDetector(confirmation_days=0)
        df = _make_spy_df(250, "sideways")
        state = detector.detect(df, vix_level=22.0)
        assert state.regime in (MarketRegime.SIDEWAYS, MarketRegime.UPTREND)

    def test_uptrend_moderate_vix(self):
        detector = MarketStateDetector(confirmation_days=0)
        df = _make_spy_df(250, "up")
        state = detector.detect(df, vix_level=22.0)
        assert state.regime == MarketRegime.UPTREND

    def test_empty_data(self):
        detector = MarketStateDetector()
        state = detector.detect(pd.DataFrame())
        assert state.regime == MarketRegime.SIDEWAYS

    def test_short_data(self):
        detector = MarketStateDetector()
        df = _make_spy_df(30, "up")
        state = detector.detect(df)
        # Should not crash, uses available data for SMA
        assert state.regime in MarketRegime

    def test_default_vix(self):
        detector = MarketStateDetector(confirmation_days=0)
        df = _make_spy_df(250, "up")
        state = detector.detect(df)  # vix_level=None -> defaults to 20
        assert state.vix_level == 20.0

    def test_confirmation_delays_change(self):
        detector = MarketStateDetector(confirmation_days=2)
        df_up = _make_spy_df(250, "up")
        df_down = _make_spy_df(250, "down")

        state1 = detector.detect(df_up, vix_level=15.0)
        initial = state1.regime

        # First detect with different data should keep old regime
        state2 = detector.detect(df_down, vix_level=32.0)
        assert state2.regime == initial  # confirmation not met yet

    def test_state_has_all_fields(self):
        detector = MarketStateDetector(confirmation_days=0)
        df = _make_spy_df(250, "up")
        state = detector.detect(df, vix_level=18.0)
        assert state.spy_price > 0
        assert state.spy_sma200 > 0
        assert isinstance(state.spy_distance_pct, float)
        assert isinstance(state.spy_roc_20d, float)
        assert 0 <= state.confidence <= 1.0

    def test_confidence_higher_with_clear_signals(self):
        detector = MarketStateDetector(confirmation_days=0)
        df_clear = _make_spy_df(250, "up")
        df_unclear = _make_spy_df(250, "sideways")
        s_clear = detector.detect(df_clear, vix_level=12.0)

        detector2 = MarketStateDetector(confirmation_days=0)
        s_unclear = detector2.detect(df_unclear, vix_level=22.0)

        assert s_clear.confidence >= s_unclear.confidence
