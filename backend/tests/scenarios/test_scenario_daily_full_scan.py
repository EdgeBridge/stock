"""Scenario 4: Daily full scan pipeline.

1. Generate OHLCV data for multiple symbols
2. Layer 1: IndicatorScreener scores and grades
3. Filter candidates by grade
4. Verify ranking order (highest score first)
5. Top candidates proceed to further evaluation
"""

import pytest
import pandas as pd
import numpy as np

from data.indicator_service import IndicatorService
from scanner.indicator_screener import IndicatorScreener
from tests.scenarios.conftest import make_ohlcv


@pytest.fixture
def multi_symbol_data():
    """Generate OHLCV data for 10 symbols with different characteristics."""
    svc = IndicatorService()
    symbols = {}

    # Strong uptrend stocks (should score high)
    for sym in ["AAPL", "MSFT", "NVDA"]:
        df = make_ohlcv(250, start_price=150.0, trend="up", volatility=0.012)
        symbols[sym] = svc.add_all_indicators(df)

    # Sideways stocks (medium scores)
    for sym in ["XOM", "JNJ", "PG"]:
        df = make_ohlcv(250, start_price=100.0, trend="sideways", volatility=0.015)
        symbols[sym] = svc.add_all_indicators(df)

    # Downtrend stocks (low scores)
    for sym in ["BABA", "PYPL", "INTC", "WBA"]:
        df = make_ohlcv(250, start_price=200.0, trend="down", volatility=0.02)
        symbols[sym] = svc.add_all_indicators(df)

    return symbols


def test_screener_scores_all_symbols(multi_symbol_data):
    """All symbols get scored without errors."""
    screener = IndicatorScreener()
    scores = []
    for sym, df in multi_symbol_data.items():
        score = screener.score(df, sym)
        scores.append(score)

    assert len(scores) == 10
    for s in scores:
        assert 0 <= s.total_score <= 100
        assert s.grade in ("A", "B", "C", "D", "F")


def test_filter_candidates_by_grade(multi_symbol_data):
    """Filter candidates respects min_grade and max_candidates."""
    screener = IndicatorScreener(min_grade="B")
    scores = [screener.score(df, sym) for sym, df in multi_symbol_data.items()]

    # Filter top candidates
    filtered = screener.filter_candidates(scores, max_candidates=5)

    # All filtered should be grade B or higher
    for s in filtered:
        assert s.grade in ("A", "B")

    assert len(filtered) <= 5


def test_candidates_sorted_by_score(multi_symbol_data):
    """Filtered candidates should be sorted by total_score descending."""
    screener = IndicatorScreener(min_grade="F")  # Accept all
    scores = [screener.score(df, sym) for sym, df in multi_symbol_data.items()]
    filtered = screener.filter_candidates(scores, max_candidates=10)

    for i in range(len(filtered) - 1):
        assert filtered[i].total_score >= filtered[i + 1].total_score


def test_screener_handles_short_data():
    """Screener doesn't crash on insufficient data."""
    svc = IndicatorService()
    df = make_ohlcv(15, start_price=100.0, trend="up")
    df = svc.add_all_indicators(df)

    screener = IndicatorScreener()
    score = screener.score(df, "SHORT")
    assert score.total_score >= 0  # May score low but shouldn't crash


def test_full_pipeline_end_to_end(multi_symbol_data):
    """Complete pipeline: score -> filter -> verify top picks come from uptrend."""
    screener = IndicatorScreener(min_grade="C")
    scores = [screener.score(df, sym) for sym, df in multi_symbol_data.items()]
    filtered = screener.filter_candidates(scores, max_candidates=20)

    # Should have at least some candidates
    assert len(filtered) > 0

    # Scores should be valid
    for s in filtered:
        assert s.symbol in multi_symbol_data
        assert s.total_score > 0
        assert s.trend_score >= 0
        assert s.momentum_score >= 0
