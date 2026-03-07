"""Tests for Signal Combiner."""

import pytest

from strategies.combiner import SignalCombiner
from strategies.base import Signal
from core.enums import SignalType


def _signal(name: str, sig_type: SignalType, conf: float = 0.7) -> Signal:
    return Signal(
        signal_type=sig_type,
        confidence=conf,
        strategy_name=name,
        reason="test",
        indicators={"test_val": 1.0},
    )


class TestSignalCombiner:
    def test_unanimous_buy(self):
        combiner = SignalCombiner()
        signals = [
            _signal("trend_following", SignalType.BUY, 0.8),
            _signal("donchian_breakout", SignalType.BUY, 0.7),
            _signal("supertrend", SignalType.BUY, 0.9),
        ]
        weights = {
            "trend_following": 0.35,
            "donchian_breakout": 0.20,
            "supertrend": 0.20,
        }
        result = combiner.combine(signals, weights)
        assert result.signal_type == SignalType.BUY
        assert result.confidence > 0.5

    def test_unanimous_sell(self):
        combiner = SignalCombiner()
        signals = [
            _signal("trend_following", SignalType.SELL, 0.8),
            _signal("supertrend", SignalType.SELL, 0.7),
        ]
        weights = {"trend_following": 0.5, "supertrend": 0.5}
        result = combiner.combine(signals, weights)
        assert result.signal_type == SignalType.SELL

    def test_mixed_signals_buy_wins(self):
        combiner = SignalCombiner()
        signals = [
            _signal("trend_following", SignalType.BUY, 0.9),
            _signal("donchian_breakout", SignalType.BUY, 0.8),
            _signal("supertrend", SignalType.SELL, 0.6),
        ]
        weights = {
            "trend_following": 0.35,
            "donchian_breakout": 0.25,
            "supertrend": 0.20,
        }
        result = combiner.combine(signals, weights)
        assert result.signal_type == SignalType.BUY

    def test_below_min_confidence_hold(self):
        combiner = SignalCombiner()
        signals = [
            _signal("trend_following", SignalType.BUY, 0.3),
        ]
        weights = {"trend_following": 0.5}
        result = combiner.combine(signals, weights, min_confidence=0.5)
        assert result.signal_type == SignalType.HOLD

    def test_no_signals(self):
        combiner = SignalCombiner()
        result = combiner.combine([], {})
        assert result.signal_type == SignalType.HOLD
        assert result.confidence == 0.0

    def test_zero_weight_ignored(self):
        combiner = SignalCombiner()
        signals = [
            _signal("trend_following", SignalType.BUY, 0.9),
            _signal("ignored", SignalType.SELL, 0.9),
        ]
        weights = {"trend_following": 1.0, "ignored": 0.0}
        result = combiner.combine(signals, weights)
        assert result.signal_type == SignalType.BUY

    def test_unweighted_strategy_ignored(self):
        combiner = SignalCombiner()
        signals = [_signal("unknown_strat", SignalType.BUY, 0.9)]
        weights = {"trend_following": 0.5}
        result = combiner.combine(signals, weights)
        assert result.signal_type == SignalType.HOLD

    def test_indicators_aggregated(self):
        combiner = SignalCombiner()
        signals = [
            _signal("a", SignalType.BUY, 0.8),
            _signal("b", SignalType.BUY, 0.7),
        ]
        weights = {"a": 0.5, "b": 0.5}
        result = combiner.combine(signals, weights)
        assert "a.test_val" in result.indicators
        assert "b.test_val" in result.indicators

    def test_hold_signals_dont_contribute(self):
        combiner = SignalCombiner()
        signals = [
            _signal("a", SignalType.HOLD, 0.5),
            _signal("b", SignalType.BUY, 0.8),
        ]
        weights = {"a": 0.5, "b": 0.5}
        result = combiner.combine(signals, weights)
        # Only b contributes buy, a is hold (neither buy nor sell)
        assert result.signal_type == SignalType.HOLD  # buy_norm = 0.4, below 0.5
