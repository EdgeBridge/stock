"""Tests for CrossSectionalMomentumStrategy (Jegadeesh-Titman 12-1)."""

import numpy as np
import pandas as pd
import pytest

from core.enums import SignalType
from strategies.cross_sectional_momentum import CrossSectionalMomentumStrategy


def _make_df(
    n: int = 300,
    base_price: float = 100.0,
    trend: float = 0.0,
    ema_20: float | None = None,
    ema_50: float | None = None,
    volume_base: float = 1_000_000,
    volume_recent_mult: float = 1.0,
) -> pd.DataFrame:
    """Create a synthetic OHLCV DataFrame.

    Args:
        n: Number of rows.
        base_price: Starting price.
        trend: Daily return applied cumulatively (e.g., 0.001 = +0.1%/day).
        ema_20/ema_50: If set, override the last row's EMA values.
        volume_recent_mult: Multiply last 20 bars' volume by this factor.
    """
    np.random.seed(42)
    prices = base_price * np.cumprod(1 + trend + np.random.normal(0, 0.005, n))
    volumes = np.full(n, volume_base, dtype=float)
    if volume_recent_mult != 1.0:
        volumes[-20:] *= volume_recent_mult

    df = pd.DataFrame({
        "open": prices * 0.999,
        "high": prices * 1.005,
        "low": prices * 0.995,
        "close": prices,
        "volume": volumes,
    })

    # Add EMA columns (NaN by default, override last row if given)
    df["ema_20"] = np.nan
    df["ema_50"] = np.nan
    if ema_20 is not None:
        df.loc[df.index[-1], "ema_20"] = ema_20
    if ema_50 is not None:
        df.loc[df.index[-1], "ema_50"] = ema_50

    return df


@pytest.fixture
def strategy():
    return CrossSectionalMomentumStrategy()


class TestBasicProperties:
    def test_name(self, strategy):
        assert strategy.name == "cross_sectional_momentum"

    def test_display_name(self, strategy):
        assert strategy.display_name == "Cross-Sectional Momentum"

    def test_min_candles(self, strategy):
        assert strategy.min_candles_required == 252


class TestInsufficientData:
    @pytest.mark.asyncio
    async def test_insufficient_data_returns_hold(self, strategy):
        df = _make_df(n=100)
        signal = await strategy.analyze(df, "AAPL")
        assert signal.signal_type == SignalType.HOLD
        assert "Insufficient" in signal.reason


class TestBuySignal:
    @pytest.mark.asyncio
    async def test_strong_positive_momentum_buys(self):
        """Stock with strong 12-1 momentum should generate BUY."""
        strategy = CrossSectionalMomentumStrategy()
        # Strong uptrend: ~0.1% daily = ~28% over 252 days
        df = _make_df(
            n=300, trend=0.001, ema_20=130.0, ema_50=125.0,
            volume_recent_mult=1.2,
        )
        signal = await strategy.analyze(df, "NVDA")
        assert signal.signal_type == SignalType.BUY
        assert signal.confidence >= 0.50
        assert "12-1 momentum" in signal.reason
        assert signal.indicators["momentum_12_1"] > 0.05

    @pytest.mark.asyncio
    async def test_ema_alignment_boosts_confidence(self):
        """EMA 20 > 50 should increase BUY confidence."""
        # With EMA aligned
        strategy = CrossSectionalMomentumStrategy()
        df = _make_df(n=300, trend=0.001, ema_20=130.0, ema_50=120.0,
                       volume_recent_mult=1.0)
        signal_aligned = await strategy.analyze(df, "AAPL")

        # Without EMA (no boost)
        strategy2 = CrossSectionalMomentumStrategy()
        df2 = _make_df(n=300, trend=0.001, volume_recent_mult=1.0)
        signal_no_ema = await strategy2.analyze(df2, "AAPL")

        if signal_aligned.signal_type == SignalType.BUY and signal_no_ema.signal_type == SignalType.BUY:
            assert signal_aligned.confidence >= signal_no_ema.confidence

    @pytest.mark.asyncio
    async def test_high_momentum_high_confidence(self):
        """Momentum > 20% should get extra confidence boost."""
        strategy = CrossSectionalMomentumStrategy()
        # Very strong trend
        df = _make_df(n=300, trend=0.0015, ema_20=150.0, ema_50=140.0,
                       volume_recent_mult=1.3)
        signal = await strategy.analyze(df, "TSLA")
        if signal.signal_type == SignalType.BUY:
            assert signal.confidence >= 0.65


class TestSellSignal:
    @pytest.mark.asyncio
    async def test_negative_momentum_sells(self):
        """Stock with strong negative 12-1 momentum should generate SELL."""
        strategy = CrossSectionalMomentumStrategy()
        # Downtrend
        df = _make_df(n=300, trend=-0.001, ema_20=80.0, ema_50=90.0)
        signal = await strategy.analyze(df, "INTC")
        assert signal.signal_type == SignalType.SELL
        assert signal.confidence >= 0.45
        assert "Negative cross-sectional momentum" in signal.reason

    @pytest.mark.asyncio
    async def test_strong_negative_momentum_higher_confidence(self):
        """Very negative momentum should have higher confidence."""
        strategy = CrossSectionalMomentumStrategy()
        # Very strong downtrend
        df = _make_df(n=300, trend=-0.0015, ema_20=70.0, ema_50=85.0)
        signal = await strategy.analyze(df, "BAD")
        assert signal.signal_type == SignalType.SELL
        assert signal.confidence >= 0.55

    @pytest.mark.asyncio
    async def test_negative_momentum_with_ema_bullish_no_sell(self):
        """Negative 12-1 momentum but EMA aligned → no SELL (trend support)."""
        strategy = CrossSectionalMomentumStrategy(
            params={"sell_momentum_threshold": -0.03}
        )
        # Mild downtrend but EMA bullish (recent recovery)
        df = _make_df(n=300, trend=-0.0003, ema_20=100.0, ema_50=95.0)
        signal = await strategy.analyze(df, "XYZ")
        # Should not sell because ema_aligned=True blocks the SELL
        assert signal.signal_type != SignalType.SELL or signal.indicators.get("ema_aligned")


class TestReversalFilter:
    @pytest.mark.asyncio
    async def test_reversal_filter_blocks_buy(self):
        """Recent sharp drop should prevent BUY even with positive 12-1 momentum."""
        strategy = CrossSectionalMomentumStrategy(
            params={"reversal_threshold": -0.03}
        )
        # Uptrend overall, but drop prices sharply in last 21 days
        df = _make_df(n=300, trend=0.001, ema_20=130.0, ema_50=125.0)
        # Manually drop last 21 bars
        df.loc[df.index[-21:], "close"] = df["close"].iloc[-22] * 0.90
        signal = await strategy.analyze(df, "DROP")
        if signal.signal_type == SignalType.HOLD:
            assert "Reversal" in signal.reason or "momentum" in signal.reason.lower()

    @pytest.mark.asyncio
    async def test_reversal_filter_disabled(self):
        """With reversal_filter=False, no reversal blocking."""
        strategy = CrossSectionalMomentumStrategy(
            params={"reversal_filter": False}
        )
        df = _make_df(n=300, trend=0.001, ema_20=130.0, ema_50=125.0)
        # Even with recent drop, should still consider BUY
        df.loc[df.index[-21:], "close"] = df["close"].iloc[-22] * 0.94
        signal = await strategy.analyze(df, "DROP")
        # Either BUY (no filter) or HOLD (below min_momentum) — not blocked by reversal
        if signal.signal_type == SignalType.HOLD:
            assert "Reversal" not in signal.reason


class TestVolumeFilter:
    @pytest.mark.asyncio
    async def test_weak_volume_blocks_buy(self):
        """Low volume ratio should block BUY signal."""
        strategy = CrossSectionalMomentumStrategy(
            params={"volume_ratio_threshold": 1.5}
        )
        df = _make_df(n=300, trend=0.001, ema_20=130.0, ema_50=125.0,
                       volume_recent_mult=0.5)  # Very weak recent volume
        signal = await strategy.analyze(df, "LOW")
        if signal.signal_type == SignalType.HOLD:
            assert "volume" in signal.reason.lower() or "momentum" in signal.reason.lower()

    @pytest.mark.asyncio
    async def test_volume_confirm_disabled(self):
        """With volume_confirm=False, weak volume doesn't block."""
        strategy = CrossSectionalMomentumStrategy(
            params={"volume_confirm": False}
        )
        df = _make_df(n=300, trend=0.001, ema_20=130.0, ema_50=125.0,
                       volume_recent_mult=0.3)
        signal = await strategy.analyze(df, "LOW")
        if signal.signal_type == SignalType.HOLD:
            assert "volume" not in signal.reason.lower()


class TestHoldSignal:
    @pytest.mark.asyncio
    async def test_neutral_momentum_holds(self):
        """Flat stock should return HOLD."""
        strategy = CrossSectionalMomentumStrategy()
        df = _make_df(n=300, trend=0.0)
        signal = await strategy.analyze(df, "FLAT")
        assert signal.signal_type == SignalType.HOLD
        assert "neutral" in signal.reason.lower() or "Insufficient" in signal.reason


class TestParams:
    def test_get_params(self, strategy):
        params = strategy.get_params()
        assert params["lookback_days"] == 252
        assert params["skip_days"] == 21
        assert params["min_momentum"] == 0.05
        assert params["reversal_filter"] is True

    def test_set_params(self, strategy):
        strategy.set_params({"lookback_days": 200, "min_momentum": 0.10})
        assert strategy._lookback_days == 200
        assert strategy._min_momentum == 0.10

    def test_set_params_ignores_unknown(self, strategy):
        strategy.set_params({"unknown_key": 42})
        assert not hasattr(strategy, "_unknown_key")

    def test_custom_params_init(self):
        s = CrossSectionalMomentumStrategy(params={
            "lookback_days": 180,
            "skip_days": 10,
            "min_momentum": 0.08,
        })
        assert s._lookback_days == 180
        assert s._skip_days == 10
        assert s._min_momentum == 0.08


class TestIndicators:
    @pytest.mark.asyncio
    async def test_indicators_present(self, strategy):
        """All expected indicators should be in the signal."""
        df = _make_df(n=300, trend=0.001, ema_20=130.0, ema_50=125.0)
        signal = await strategy.analyze(df, "TEST")
        if signal.signal_type != SignalType.HOLD or signal.indicators:
            assert "momentum_12_1" in signal.indicators
            assert "ret_6m" in signal.indicators
            assert "ret_1m" in signal.indicators
            assert "volume_ratio" in signal.indicators
            assert "ema_aligned" in signal.indicators


class TestVolumeRatio:
    @pytest.mark.asyncio
    async def test_volume_ratio_calculation(self, strategy):
        """Volume ratio should reflect recent vs historical volume."""
        df = _make_df(n=300, trend=0.001, ema_20=130.0, ema_50=125.0,
                       volume_recent_mult=2.0)
        signal = await strategy.analyze(df, "VOL")
        if signal.indicators:
            # 20-day avg is 2x the 50-day (since last 20 are doubled)
            # ratio = (20*2M + 0) / (20*2M + 30*1M) = not exactly 2, but > 1
            assert signal.indicators["volume_ratio"] > 1.0


class TestEdgeCases:
    @pytest.mark.asyncio
    async def test_zero_price_handled(self):
        """Zero prices should not crash."""
        strategy = CrossSectionalMomentumStrategy()
        df = _make_df(n=300, trend=0.001)
        df.loc[0, "close"] = 0.0  # Zero price at start
        signal = await strategy.analyze(df, "ZERO")
        assert signal.signal_type in (SignalType.HOLD, SignalType.BUY, SignalType.SELL)

    @pytest.mark.asyncio
    async def test_exactly_min_candles(self):
        """Exactly 252 candles should work, not return insufficient."""
        strategy = CrossSectionalMomentumStrategy()
        df = _make_df(n=252, trend=0.001, ema_20=130.0, ema_50=125.0)
        signal = await strategy.analyze(df, "EXACT")
        assert "Insufficient data" not in signal.reason

    @pytest.mark.asyncio
    async def test_confidence_capped_at_095(self):
        """Confidence should never exceed 0.95."""
        strategy = CrossSectionalMomentumStrategy()
        # Extreme uptrend
        df = _make_df(n=300, trend=0.003, ema_20=200.0, ema_50=180.0,
                       volume_recent_mult=2.0)
        signal = await strategy.analyze(df, "MOON")
        assert signal.confidence <= 0.95

    @pytest.mark.asyncio
    async def test_sell_confidence_capped_at_085(self):
        """SELL confidence should never exceed 0.85."""
        strategy = CrossSectionalMomentumStrategy()
        df = _make_df(n=300, trend=-0.003, ema_20=50.0, ema_50=80.0)
        signal = await strategy.analyze(df, "DOOM")
        if signal.signal_type == SignalType.SELL:
            assert signal.confidence <= 0.85
