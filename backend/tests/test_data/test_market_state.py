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


def _make_controlled_df(price: float, sma200: float, n: int = 250) -> pd.DataFrame:
    """Create a DataFrame where last price and SMA200 are controlled."""
    # Build a series that gives the desired SMA200 and final price
    base = np.full(n, sma200)
    # Set last value to desired price
    base[-1] = price
    return pd.DataFrame({
        "open": base * 0.999,
        "high": base * 1.005,
        "low": base * 0.995,
        "close": base,
        "volume": np.full(n, 80_000_000.0),
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

    def test_confirmation_delays_risk_on(self):
        """Risk-on (uptrend) transitions require full confirmation_days."""
        detector = MarketStateDetector(confirmation_days=2)
        df_up = _make_spy_df(250, "up")
        df_down = _make_spy_df(250, "down")

        # Start in downtrend
        detector.detect(df_down, vix_level=32.0)
        initial = detector.last_state.regime

        # First day of uptrend should keep old regime (risk-on needs 2 days)
        state2 = detector.detect(df_up, vix_level=15.0)
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

    # --- WEAK_DOWNTREND regime tests ---

    def test_weak_downtrend_below_sma_elevated_vix(self):
        """Below SMA200 with VIX 26 (> caution 25) → WEAK_DOWNTREND."""
        detector = MarketStateDetector(confirmation_days=0)
        # Price below SMA, moderate VIX (25-30 range), distance not extreme
        df = _make_controlled_df(price=440, sma200=450, n=250)
        state = detector.detect(df, vix_level=26.0)
        assert state.regime == MarketRegime.WEAK_DOWNTREND

    def test_weak_downtrend_below_sma_negative_distance(self):
        """Below SMA200 with distance < -2% → WEAK_DOWNTREND."""
        detector = MarketStateDetector(confirmation_days=0)
        # Price ~3% below SMA, VIX moderate (not > 30)
        df = _make_controlled_df(price=436, sma200=450, n=250)
        state = detector.detect(df, vix_level=22.0)
        assert state.regime == MarketRegime.WEAK_DOWNTREND

    def test_full_downtrend_requires_extreme(self):
        """Full DOWNTREND still requires VIX > 30 or distance < -5%."""
        detector = MarketStateDetector(confirmation_days=0)
        df = _make_spy_df(250, "down")
        state = detector.detect(df, vix_level=32.0)
        assert state.regime == MarketRegime.DOWNTREND

    def test_weak_downtrend_in_enum(self):
        """WEAK_DOWNTREND is a valid MarketRegime member."""
        assert hasattr(MarketRegime, "WEAK_DOWNTREND")
        assert MarketRegime.WEAK_DOWNTREND.value == "weak_downtrend"

    # --- Asymmetric confirmation tests ---

    def test_risk_off_confirms_faster(self):
        """Downtrend transition confirms in 1 day (fast risk-off)."""
        detector = MarketStateDetector(confirmation_days=2)
        df_up = _make_spy_df(250, "up")
        df_down = _make_spy_df(250, "down")

        # Start in uptrend
        detector.detect(df_up, vix_level=15.0)

        # 1 day of downtrend data should switch (risk-off = fast)
        state = detector.detect(df_down, vix_level=32.0)
        assert state.regime == MarketRegime.DOWNTREND

    def test_risk_on_requires_full_confirmation(self):
        """Uptrend transition requires full confirmation_days (slow risk-on)."""
        detector = MarketStateDetector(confirmation_days=2)
        df_up = _make_spy_df(250, "up")
        df_down = _make_spy_df(250, "down")

        # Start in downtrend (need to get there first with confirmation_days=0)
        detector2 = MarketStateDetector(confirmation_days=0)
        detector2.detect(df_down, vix_level=32.0)

        # Re-create with confirmation_days=2 and set state
        detector = MarketStateDetector(confirmation_days=2)
        detector.detect(df_down, vix_level=32.0)  # establish downtrend

        # First day of uptrend: should NOT switch yet (slow risk-on)
        state = detector.detect(df_up, vix_level=15.0)
        assert state.regime == MarketRegime.DOWNTREND  # still downtrend

        # Second day: should switch
        state = detector.detect(df_up, vix_level=15.0)
        assert state.regime == MarketRegime.STRONG_UPTREND
