"""Tests for SectorAnalyzer."""

import pytest

from scanner.sector_analyzer import SectorAnalyzer


@pytest.fixture
def analyzer():
    return SectorAnalyzer()


@pytest.fixture
def sector_data():
    return {
        "Technology": {"symbol": "XLK", "return_1d": 0.5, "return_1w": 3.0, "return_1m": 8.0, "return_3m": 15.0},
        "Financials": {"symbol": "XLF", "return_1d": -0.2, "return_1w": 1.0, "return_1m": 4.0, "return_3m": 10.0},
        "Energy": {"symbol": "XLE", "return_1d": -1.0, "return_1w": -2.0, "return_1m": -5.0, "return_3m": -8.0},
        "Healthcare": {"symbol": "XLV", "return_1d": 0.1, "return_1w": 0.5, "return_1m": 2.0, "return_3m": 5.0},
        "Utilities": {"symbol": "XLU", "return_1d": 0.3, "return_1w": -0.5, "return_1m": 1.0, "return_3m": 3.0},
    }


def test_analyze_returns_ranked(analyzer, sector_data):
    scores = analyzer.analyze(sector_data)
    assert len(scores) == 5
    # Technology should be #1 (highest returns)
    assert scores[0].name == "Technology"
    assert scores[0].rank == 1
    # Energy should be last (negative returns)
    assert scores[-1].name == "Energy"
    assert scores[-1].rank == 5


def test_strength_scores_normalized(analyzer, sector_data):
    scores = analyzer.analyze(sector_data)
    # Top should be 100, bottom should be 0
    assert scores[0].strength_score == 100.0
    assert scores[-1].strength_score == 0.0
    # All between 0-100
    for s in scores:
        assert 0 <= s.strength_score <= 100


def test_trend_classification(analyzer, sector_data):
    scores = analyzer.analyze(sector_data)
    score_map = {s.name: s for s in scores}
    # Technology: all positive, 1w acceleration -> leading
    assert score_map["Technology"].trend == "leading"
    # Energy: all negative -> lagging
    assert score_map["Energy"].trend == "lagging"


def test_get_top_sectors(analyzer, sector_data):
    scores = analyzer.analyze(sector_data)
    top = analyzer.get_top_sectors(scores, n=2, min_score=50)
    assert len(top) <= 2
    assert all(s.strength_score >= 50 for s in top)


def test_get_bottom_sectors(analyzer, sector_data):
    scores = analyzer.analyze(sector_data)
    bottom = analyzer.get_bottom_sectors(scores, n=2)
    assert len(bottom) == 2
    assert bottom[0].rank >= 4


def test_empty_data(analyzer):
    scores = analyzer.analyze({})
    assert scores == []


def test_single_sector(analyzer):
    data = {
        "Technology": {"symbol": "XLK", "return_1w": 2.0, "return_1m": 5.0, "return_3m": 10.0},
    }
    scores = analyzer.analyze(data)
    assert len(scores) == 1
    assert scores[0].strength_score == 100.0  # only one, gets max
    assert scores[0].rank == 1


def test_custom_weights():
    analyzer = SectorAnalyzer(weights={"return_1w": 1.0, "return_1m": 0.0, "return_3m": 0.0})
    data = {
        "A": {"symbol": "A", "return_1w": 10.0, "return_1m": -5.0, "return_3m": -10.0},
        "B": {"symbol": "B", "return_1w": -5.0, "return_1m": 20.0, "return_3m": 30.0},
    }
    scores = analyzer.analyze(data)
    # With 100% weight on 1w, A should rank first
    assert scores[0].name == "A"


def test_weakening_trend(analyzer):
    data = {
        "Sector": {"symbol": "X", "return_1w": -1.0, "return_1m": 2.0, "return_3m": 8.0},
    }
    scores = analyzer.analyze(data)
    assert scores[0].trend == "weakening"
