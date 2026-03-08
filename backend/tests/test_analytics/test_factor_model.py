"""Tests for Multi-Factor Scoring Model."""

import numpy as np
import pandas as pd
import pytest

from analytics.factor_model import FactorScores, FactorWeights, MultiFactorModel


@pytest.fixture
def model():
    return MultiFactorModel()


@pytest.fixture
def price_data():
    """Generate synthetic OHLCV data for 3 stocks with different profiles."""
    np.random.seed(42)
    dates = pd.date_range("2024-01-01", periods=300, freq="B")

    def make_ohlcv(trend: float, volatility: float) -> pd.DataFrame:
        returns = np.random.normal(trend, volatility, len(dates))
        close = 100 * np.exp(np.cumsum(returns))
        return pd.DataFrame({
            "open": close * (1 + np.random.uniform(-0.01, 0.01, len(dates))),
            "high": close * (1 + np.abs(np.random.normal(0, 0.01, len(dates)))),
            "low": close * (1 - np.abs(np.random.normal(0, 0.01, len(dates)))),
            "close": close,
            "volume": np.random.randint(1_000_000, 10_000_000, len(dates)),
        }, index=dates)

    return {
        "WINNER": make_ohlcv(0.001, 0.015),    # Strong uptrend, moderate vol
        "LOSER": make_ohlcv(-0.0005, 0.025),   # Slight downtrend, high vol
        "STEADY": make_ohlcv(0.0003, 0.008),   # Slight uptrend, low vol
    }


@pytest.fixture
def fundamental_data():
    return {
        "WINNER": {
            "trailingPE": 18, "priceToBook": 4.0, "fcf_yield": 0.06,
            "returnOnEquity": 0.25, "profitMargins": 0.20,
            "debtToEquity": 0.5, "revenueGrowth": 0.15,
        },
        "LOSER": {
            "trailingPE": 35, "priceToBook": 8.0, "fcf_yield": 0.01,
            "returnOnEquity": 0.05, "profitMargins": 0.05,
            "debtToEquity": 1.8, "revenueGrowth": -0.05,
        },
        "STEADY": {
            "trailingPE": 15, "priceToBook": 2.5, "fcf_yield": 0.08,
            "returnOnEquity": 0.18, "profitMargins": 0.15,
            "debtToEquity": 0.3, "revenueGrowth": 0.08,
        },
    }


class TestFactorScores:
    def test_default_values(self):
        fs = FactorScores(symbol="AAPL")
        assert fs.momentum == 0.0
        assert fs.composite == 0.0
        assert fs.rank == 0


class TestFactorWeights:
    def test_default_sum_to_one(self):
        w = FactorWeights()
        total = w.momentum + w.value + w.quality + w.low_volatility
        assert abs(total - 1.0) < 1e-9

    def test_custom_weights(self):
        w = FactorWeights(momentum=0.5, value=0.2, quality=0.2, low_volatility=0.1)
        assert w.momentum == 0.5


class TestScoreUniverse:
    def test_returns_sorted_by_composite(self, model, price_data, fundamental_data):
        results = model.score_universe(price_data, fundamental_data)
        assert len(results) == 3
        composites = [r.composite for r in results]
        assert composites == sorted(composites, reverse=True)

    def test_ranks_assigned_correctly(self, model, price_data, fundamental_data):
        results = model.score_universe(price_data, fundamental_data)
        ranks = [r.rank for r in results]
        assert ranks == [1, 2, 3]

    def test_winner_ranks_higher_than_loser(self, model, price_data, fundamental_data):
        results = model.score_universe(price_data, fundamental_data)
        symbol_rank = {r.symbol: r.rank for r in results}
        assert symbol_rank["WINNER"] < symbol_rank["LOSER"]

    def test_empty_price_data(self, model):
        assert model.score_universe({}) == []

    def test_without_fundamentals(self, model, price_data):
        results = model.score_universe(price_data)
        assert len(results) == 3
        # Value and quality factors should be zero for all
        for r in results:
            assert r.value == 0.0
            assert r.quality == 0.0

    def test_short_price_data_handled(self, model):
        short_df = pd.DataFrame({
            "close": [100 + i for i in range(50)],
        })
        results = model.score_universe({"SHORT": short_df})
        assert len(results) == 1
        assert results[0].momentum == 0.0


class TestMomentum:
    def test_positive_momentum_for_uptrend(self, model, price_data):
        scores = model._compute_momentum(price_data)
        assert scores["WINNER"] > scores["LOSER"]

    def test_returns_zero_for_short_data(self, model):
        short_df = pd.DataFrame({"close": [100 + i for i in range(50)]})
        scores = model._compute_momentum({"SHORT": short_df})
        assert scores["SHORT"] == 0.0


class TestVolatility:
    def test_high_vol_stock_higher(self, model, price_data):
        scores = model._compute_volatility(price_data)
        assert scores["LOSER"] > scores["STEADY"]

    def test_default_for_short_data(self, model):
        short_df = pd.DataFrame({"close": [100 + i for i in range(10)]})
        scores = model._compute_volatility({"SHORT": short_df})
        assert scores["SHORT"] == 0.5


class TestValue:
    def test_cheaper_stock_scores_higher(self, model, fundamental_data):
        symbols = list(fundamental_data.keys())
        scores = model._compute_value(fundamental_data, symbols)
        # STEADY has PE=15, PB=2.5 (cheapest) -> highest value score
        assert scores["STEADY"] > scores["LOSER"]

    def test_missing_fundamentals_return_zero(self, model):
        scores = model._compute_value({}, ["AAPL"])
        assert scores["AAPL"] == 0.0


class TestQuality:
    def test_high_quality_stock_scores_higher(self, model, fundamental_data):
        symbols = list(fundamental_data.keys())
        scores = model._compute_quality(fundamental_data, symbols)
        assert scores["WINNER"] > scores["LOSER"]

    def test_high_debt_penalized(self, model):
        data = {"DEBT": {"debtToEquity": 3.0, "returnOnEquity": 0.1}}
        scores = model._compute_quality(data, ["DEBT"])
        assert scores["DEBT"] < 0  # High debt penalty


class TestZScore:
    def test_zscore_normalization(self):
        values = {"A": 10, "B": 20, "C": 30}
        z = MultiFactorModel._zscore(values)
        assert abs(z["B"]) < 0.01  # Middle value ~ 0
        assert z["C"] > 0
        assert z["A"] < 0

    def test_zscore_empty(self):
        assert MultiFactorModel._zscore({}) == {}

    def test_zscore_uniform(self):
        values = {"A": 5.0, "B": 5.0, "C": 5.0}
        z = MultiFactorModel._zscore(values)
        for v in z.values():
            assert v == 0.0


class TestGetTopN:
    def test_get_top_n(self, model, price_data, fundamental_data):
        scores = model.score_universe(price_data, fundamental_data)
        top2 = model.get_top_n(scores, n=2)
        assert len(top2) == 2
        assert top2[0].rank == 1

    def test_min_composite_filter(self, model, price_data, fundamental_data):
        scores = model.score_universe(price_data, fundamental_data)
        filtered = model.get_top_n(scores, n=10, min_composite=999.0)
        assert len(filtered) == 0


class TestCustomWeights:
    def test_momentum_heavy_weights(self, price_data, fundamental_data):
        # Heavily momentum-weighted model should favor WINNER even more
        heavy_mom = MultiFactorModel(weights=FactorWeights(
            momentum=0.70, value=0.10, quality=0.10, low_volatility=0.10,
        ))
        results = heavy_mom.score_universe(price_data, fundamental_data)
        assert results[0].symbol == "WINNER"
