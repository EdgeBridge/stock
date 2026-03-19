"""Tests for CIS Momentum Strategy."""

import pandas as pd

from core.enums import SignalType
from strategies.cis_momentum import CISMomentumStrategy


def _make_df(
    n: int = 60,
    roc5: float = 0.0,
    roc10: float = 0.0,
    volume_ratio: float = 1.5,
    close_price: float = 101.0,
) -> pd.DataFrame:
    """Create DataFrame with momentum indicators.

    Default close_price=101.0 with remaining bars at 100.0 ensures
    price > SMA(50) ≈ 100.02, so the trend filter passes for BUY tests.
    """
    closes = [100.0] * (n - 1) + [close_price]
    data = {
        "open": [100.0] * n,
        "high": [102.0] * n,
        "low": [98.0] * n,
        "close": closes,
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
    return pd.DataFrame(
        {
            "open": [c * 0.99 for c in closes],
            "high": [c * 1.01 for c in closes],
            "low": [c * 0.98 for c in closes],
            "close": closes,
            "volume": vols,
        }
    )


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
        # Need 55+ bars for min_candles_required; price rises to be above SMA
        closes = [100.0] * 50 + [
            100.0,
            102.0,
            104.0,
            106.0,
            108.0,
            110.0,
            112.0,
            113.0,
            114.0,
            115.0,
        ]
        # ROC5 = (115 - 110)/110 * 100 = 4.5%
        # ROC10 = (115 - 100)/100 * 100 = 15%
        vols = [1_000_000.0] * 60
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
        # STOCK-35: new params
        assert params["trend_sma_period"] == 50
        assert params["roc_short_sell_weak"] == -1.0
        assert params["roc_long_sell_weak"] == -2.0

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
        assert "above_trend" in signal.indicators


class TestCISMomentumTrendFilter:
    """Tests for SMA trend filter (STOCK-35)."""

    async def test_buy_blocked_when_below_trend(self):
        """BUY signal should be blocked when price < SMA(50)."""
        strategy = CISMomentumStrategy()
        # close_price=99.0 < SMA(50)≈100.0 → below trend
        df = _make_df(roc5=5.0, roc10=7.0, volume_ratio=1.5, close_price=99.0)
        signal = await strategy.analyze(df, "AAPL")
        assert signal.signal_type != SignalType.BUY
        # Should be HOLD (momentum unclear) since trend filter blocks buy
        assert signal.signal_type == SignalType.HOLD

    async def test_buy_allowed_when_above_trend(self):
        """BUY signal fires when price > SMA(50)."""
        strategy = CISMomentumStrategy()
        # close_price=101.0 > SMA(50)≈100.02 → above trend
        df = _make_df(roc5=5.0, roc10=7.0, volume_ratio=1.5, close_price=101.0)
        signal = await strategy.analyze(df, "AAPL")
        assert signal.signal_type == SignalType.BUY

    async def test_sell_not_affected_by_trend_filter(self):
        """SELL signals should fire regardless of trend (exit is always allowed)."""
        strategy = CISMomentumStrategy()
        # Price below SMA, but sell should still fire
        df = _make_df(roc5=-5.0, roc10=-7.0, volume_ratio=1.5, close_price=99.0)
        signal = await strategy.analyze(df, "AAPL")
        assert signal.signal_type == SignalType.SELL

    async def test_trend_filter_failopen_insufficient_data(self):
        """Trend filter should fail-open when not enough data for SMA."""
        strategy = CISMomentumStrategy(params={"trend_sma_period": 200})
        # Only 60 bars but SMA needs 200 → fail-open, allow buy
        df = _make_df(n=60, roc5=5.0, roc10=7.0, volume_ratio=1.5)
        signal = await strategy.analyze(df, "AAPL")
        assert signal.signal_type == SignalType.BUY

    async def test_trend_sma_period_configurable(self):
        """trend_sma_period should be configurable via params."""
        # Use SMA(10) instead of SMA(50) — close_price=99.0 would be below SMA(10)=100
        strategy = CISMomentumStrategy(params={"trend_sma_period": 10})
        df = _make_df(roc5=5.0, roc10=7.0, volume_ratio=1.5, close_price=99.0)
        signal = await strategy.analyze(df, "AAPL")
        assert signal.signal_type == SignalType.HOLD  # blocked by trend filter

    async def test_above_trend_in_indicators(self):
        """above_trend flag should be included in signal indicators."""
        strategy = CISMomentumStrategy()
        df = _make_df(roc5=1.0, roc10=2.0, volume_ratio=1.5, close_price=101.0)
        signal = await strategy.analyze(df, "AAPL")
        assert signal.indicators["above_trend"] is True

        df2 = _make_df(roc5=1.0, roc10=2.0, volume_ratio=1.5, close_price=99.0)
        signal2 = await strategy.analyze(df2, "AAPL")
        assert signal2.indicators["above_trend"] is False


class TestCISMomentumDecaySell:
    """Tests for momentum decay sell signal (STOCK-35).

    Catches gradual declines (ROC5 < -1%, ROC10 < -2%) that never trigger
    the stricter reversal thresholds (ROC5 < -3%, ROC10 < -5%).
    """

    async def test_momentum_decay_sell(self):
        """Gradual decline should trigger decay SELL."""
        strategy = CISMomentumStrategy()
        # ROC5=-1.5%, ROC10=-2.5%: below weak thresholds but above strong thresholds
        df = _make_df(roc5=-1.5, roc10=-2.5, volume_ratio=1.0)
        signal = await strategy.analyze(df, "AAPL")
        assert signal.signal_type == SignalType.SELL
        assert "decay" in signal.reason.lower()

    async def test_momentum_decay_lower_confidence_than_reversal(self):
        """Decay SELL should have lower confidence than reversal SELL."""
        strategy = CISMomentumStrategy()
        df_decay = _make_df(roc5=-1.5, roc10=-2.5, volume_ratio=1.0)
        df_reversal = _make_df(roc5=-5.0, roc10=-7.0, volume_ratio=1.0)
        s_decay = await strategy.analyze(df_decay, "AAPL")
        s_reversal = await strategy.analyze(df_reversal, "AAPL")
        assert s_decay.signal_type == SignalType.SELL
        assert s_reversal.signal_type == SignalType.SELL
        assert s_decay.confidence < s_reversal.confidence

    async def test_momentum_decay_max_confidence_capped(self):
        """Decay SELL confidence should be capped at 0.65."""
        strategy = CISMomentumStrategy()
        # Even with moderately negative ROC, decay confidence should cap
        df = _make_df(roc5=-2.5, roc10=-4.5, volume_ratio=1.0)
        signal = await strategy.analyze(df, "AAPL")
        assert signal.signal_type == SignalType.SELL
        # This should still be a strong reversal since -2.5 < -3 is False,
        # but -4.5 < -5 is also False. So -2.5 < -1.0 and -4.5 < -2.0 → decay
        assert signal.confidence <= 0.65

    async def test_no_decay_sell_when_momentum_slightly_negative(self):
        """No sell when ROC is negative but above weak thresholds."""
        strategy = CISMomentumStrategy()
        # ROC5=-0.5% > -1.0 threshold → no decay sell
        df = _make_df(roc5=-0.5, roc10=-1.5, volume_ratio=1.0)
        signal = await strategy.analyze(df, "AAPL")
        assert signal.signal_type == SignalType.HOLD

    async def test_strong_reversal_takes_priority_over_decay(self):
        """Strong reversal (both thresholds met) should fire instead of decay."""
        strategy = CISMomentumStrategy()
        df = _make_df(roc5=-4.0, roc10=-6.0, volume_ratio=1.0)
        signal = await strategy.analyze(df, "AAPL")
        assert signal.signal_type == SignalType.SELL
        assert "reversal" in signal.reason.lower()
        assert "decay" not in signal.reason.lower()

    async def test_decay_sell_configurable_thresholds(self):
        """Weak sell thresholds should be configurable."""
        strategy = CISMomentumStrategy(
            params={
                "roc_short_sell_weak": -0.5,
                "roc_long_sell_weak": -1.0,
            }
        )
        # ROC5=-0.8 < -0.5 and ROC10=-1.5 < -1.0 → decay sell
        df = _make_df(roc5=-0.8, roc10=-1.5, volume_ratio=1.0)
        signal = await strategy.analyze(df, "AAPL")
        assert signal.signal_type == SignalType.SELL
        assert "decay" in signal.reason.lower()

    async def test_set_params_updates_weak_thresholds(self):
        """set_params should update weak sell thresholds at runtime."""
        strategy = CISMomentumStrategy()
        strategy.set_params(
            {
                "roc_short_sell_weak": -0.5,
                "roc_long_sell_weak": -1.0,
            }
        )
        params = strategy.get_params()
        assert params["roc_short_sell_weak"] == -0.5
        assert params["roc_long_sell_weak"] == -1.0

    async def test_set_params_updates_trend_sma_period(self):
        """set_params should update trend_sma_period at runtime."""
        strategy = CISMomentumStrategy()
        strategy.set_params({"trend_sma_period": 100})
        assert strategy.get_params()["trend_sma_period"] == 100
