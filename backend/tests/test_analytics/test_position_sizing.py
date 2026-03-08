"""Tests for Kelly Criterion Position Sizing."""

import pytest

from analytics.position_sizing import KellyPositionSizer, KellyResult


@pytest.fixture
def sizer():
    return KellyPositionSizer()


class TestKellyFormula:
    def test_positive_edge(self, sizer):
        result = sizer.calculate(
            win_rate=0.60, avg_win=0.10, avg_loss=0.05,
        )
        assert result.kelly_fraction > 0
        assert result.final_allocation_pct > 0
        assert result.reason == "OK"

    def test_no_edge(self, sizer):
        # Win rate too low for the payoff ratio
        result = sizer.calculate(
            win_rate=0.30, avg_win=0.05, avg_loss=0.10,
        )
        assert result.kelly_fraction < 0
        assert result.final_allocation_pct == 0
        assert "no edge" in result.reason.lower()

    def test_breakeven(self, sizer):
        # 50% win rate with 1:1 payoff → Kelly = 0
        result = sizer.calculate(
            win_rate=0.50, avg_win=0.05, avg_loss=0.05,
        )
        assert result.kelly_fraction == 0
        assert result.final_allocation_pct == 0

    def test_missing_trade_data(self, sizer):
        result = sizer.calculate(
            win_rate=0.60, avg_win=0, avg_loss=0,
        )
        assert result.final_allocation_pct == 0
        assert "insufficient" in result.reason.lower()

    def test_fractional_kelly_reduces_size(self):
        full = KellyPositionSizer(kelly_fraction=1.0)
        quarter = KellyPositionSizer(kelly_fraction=0.25)

        r_full = full.calculate(win_rate=0.60, avg_win=0.10, avg_loss=0.05)
        r_quarter = quarter.calculate(win_rate=0.60, avg_win=0.10, avg_loss=0.05)

        assert r_quarter.position_pct < r_full.position_pct


class TestConfidenceBoost:
    def test_higher_confidence_larger_position(self, sizer):
        high = sizer.calculate(
            win_rate=0.60, avg_win=0.10, avg_loss=0.05,
            signal_confidence=0.90,
        )
        low = sizer.calculate(
            win_rate=0.60, avg_win=0.10, avg_loss=0.05,
            signal_confidence=0.50,
        )
        assert high.final_allocation_pct > low.final_allocation_pct

    def test_zero_confidence_still_minimum(self, sizer):
        result = sizer.calculate(
            win_rate=0.60, avg_win=0.10, avg_loss=0.05,
            signal_confidence=0.0,
        )
        assert result.final_allocation_pct == sizer._min_pct


class TestFactorBoost:
    def test_positive_factor_increases_size(self, sizer):
        positive = sizer.calculate(
            win_rate=0.60, avg_win=0.10, avg_loss=0.05,
            factor_score=2.0,
        )
        negative = sizer.calculate(
            win_rate=0.60, avg_win=0.10, avg_loss=0.05,
            factor_score=-2.0,
        )
        assert positive.final_allocation_pct > negative.final_allocation_pct

    def test_zero_factor_neutral(self, sizer):
        result = sizer.calculate(
            win_rate=0.60, avg_win=0.10, avg_loss=0.05,
            factor_score=0.0,
        )
        assert result.factor_boost == 1.0


class TestPositionLimits:
    def test_max_position_cap(self):
        sizer = KellyPositionSizer(max_position_pct=0.10)
        result = sizer.calculate(
            win_rate=0.90, avg_win=0.30, avg_loss=0.02,
            signal_confidence=1.0, factor_score=3.0,
        )
        assert result.final_allocation_pct <= 0.10

    def test_min_position_floor(self):
        sizer = KellyPositionSizer(min_position_pct=0.03)
        result = sizer.calculate(
            win_rate=0.55, avg_win=0.03, avg_loss=0.02,
            signal_confidence=0.3,
        )
        assert result.final_allocation_pct >= 0.03


class TestQuantity:
    def test_calculate_quantity(self, sizer):
        result = KellyResult(
            kelly_fraction=0.2, position_pct=0.05,
            confidence_boost=1, factor_boost=1,
            final_allocation_pct=0.05,
        )
        qty = sizer.calculate_quantity(result, portfolio_value=100000, price=50.0)
        assert qty == 100  # 5% of 100k = 5000 / 50 = 100

    def test_zero_allocation(self, sizer):
        result = KellyResult(
            kelly_fraction=0, position_pct=0,
            confidence_boost=1, factor_boost=1,
            final_allocation_pct=0,
        )
        qty = sizer.calculate_quantity(result, portfolio_value=100000, price=50.0)
        assert qty == 0

    def test_zero_price(self, sizer):
        result = KellyResult(
            kelly_fraction=0.2, position_pct=0.05,
            confidence_boost=1, factor_boost=1,
            final_allocation_pct=0.05,
        )
        qty = sizer.calculate_quantity(result, portfolio_value=100000, price=0)
        assert qty == 0
