"""Tests for Layer 1: Indicator Screener."""

import numpy as np
import pandas as pd
import pytest

from scanner.indicator_screener import IndicatorScreener, ScreenerScore


def _make_bullish_row() -> dict:
    return {
        "open": 148.0, "high": 152.0, "low": 147.0,
        "close": 150.0, "volume": 1_000_000,
        "ema_10": 148.0, "ema_20": 145.0,
        "ema_50": 140.0, "ema_200": 130.0,
        "sma_50": 140.0, "sma_200": 130.0,
        "adx": 35.0, "plus_di": 30.0, "minus_di": 15.0,
        "rsi": 60.0,
        "macd": 2.0, "macd_histogram": 1.5, "macd_signal": 0.5,
        "roc_5": 3.0, "roc_10": 5.0, "roc_20": 8.0,
        "volume_ratio": 1.8, "bb_pct": 0.7,
        "supertrend": 140.0, "supertrend_direction": 1.0,
        "donchian_upper": 152.0, "donchian_lower": 130.0,
        "donchian_mid": 141.0, "atr": 3.0,
        "bb_lower": 135.0, "bb_upper": 155.0,
        "kc_lower": 132.0, "kc_upper": 158.0,
    }


def _make_df(n: int = 50, base_row: dict | None = None) -> pd.DataFrame:
    row = base_row or _make_bullish_row()
    return pd.DataFrame([row] * n)


class TestIndicatorScreener:
    def test_bullish_stock_high_score(self):
        screener = IndicatorScreener()
        df = _make_df()
        score = screener.score(df, "AAPL")
        assert score.total_score > 65
        assert score.grade in ("A", "B")
        assert score.symbol == "AAPL"

    def test_bearish_stock_low_score(self):
        screener = IndicatorScreener()
        bearish = _make_bullish_row()
        bearish.update({
            "open": 105.0, "high": 106.0, "low": 99.0,
            "close": 100.0,
            "ema_10": 105.0, "ema_20": 110.0,
            "ema_50": 120.0, "ema_200": 130.0,
            "sma_50": 120.0, "sma_200": 130.0,
            "rsi": 25.0,
            "macd": -3.0, "macd_histogram": -2.0, "macd_signal": -1.0,
            "roc_5": -5.0, "roc_10": -8.0, "roc_20": -10.0,
            "volume_ratio": 0.4, "supertrend": 110.0,
            "supertrend_direction": -1.0, "adx": 35.0,
            "plus_di": 10.0, "minus_di": 30.0,
            "donchian_upper": 130.0,
        })
        df = _make_df(base_row=bearish)
        score = screener.score(df, "BEAR")
        assert score.total_score < 40
        assert score.grade in ("D", "F")

    def test_empty_df(self):
        screener = IndicatorScreener()
        score = screener.score(pd.DataFrame(), "EMPTY")
        assert score.total_score == 0
        assert score.grade == "F"

    def test_short_df(self):
        screener = IndicatorScreener()
        score = screener.score(pd.DataFrame([{"close": 100.0}] * 5), "SHORT")
        assert score.total_score == 0

    def test_filter_candidates(self):
        screener = IndicatorScreener(min_grade="B")
        scores = [
            ScreenerScore("A", 85, 90, 80, 85, 80, "A", {}, []),
            ScreenerScore("B", 70, 75, 65, 70, 65, "B", {}, []),
            ScreenerScore("C", 45, 50, 40, 45, 40, "C", {}, []),
            ScreenerScore("D", 30, 35, 25, 30, 25, "D", {}, []),
        ]
        filtered = screener.filter_candidates(scores, max_candidates=10)
        assert len(filtered) == 2
        assert filtered[0].symbol == "A"
        assert filtered[1].symbol == "B"

    def test_filter_max_candidates(self):
        screener = IndicatorScreener(min_grade="C")
        scores = [
            ScreenerScore(f"S{i}", 60 + i, 60, 60, 60, 60, "B", {}, [])
            for i in range(10)
        ]
        filtered = screener.filter_candidates(scores, max_candidates=3)
        assert len(filtered) == 3
        assert filtered[0].total_score > filtered[1].total_score

    def test_grade_mapping(self):
        assert IndicatorScreener._to_grade(90) == "A"
        assert IndicatorScreener._to_grade(80) == "A"
        assert IndicatorScreener._to_grade(70) == "B"
        assert IndicatorScreener._to_grade(55) == "C"
        assert IndicatorScreener._to_grade(40) == "D"
        assert IndicatorScreener._to_grade(20) == "F"

    def test_custom_weights(self):
        screener = IndicatorScreener(weights={
            "trend": 0.80, "momentum": 0.10,
            "volatility_volume": 0.05, "support_resistance": 0.05,
        })
        df = _make_df()
        score = screener.score(df, "AAPL")
        assert score.total_score > 0  # Should still work

    def test_score_details(self):
        screener = IndicatorScreener()
        df = _make_df()
        score = screener.score(df, "AAPL")
        assert "ema_alignment" in score.details
        assert "squeeze" in score.details

    # ------------------------------------------------------------------
    # New tests
    # ------------------------------------------------------------------

    def test_golden_cross_detection(self):
        """SMA50 crosses above SMA200 within last 10 rows triggers signal."""
        screener = IndicatorScreener()
        row = _make_bullish_row()
        n = 50
        rows = [dict(row) for _ in range(n)]
        # Before the cross: sma_50 < sma_200
        for i in range(n - 5):
            rows[i]["sma_50"] = 128.0
            rows[i]["sma_200"] = 130.0
        # Cross happens at row n-5
        rows[n - 5]["sma_50"] = 130.0
        rows[n - 5]["sma_200"] = 130.0
        # After cross: sma_50 > sma_200
        for i in range(n - 4, n):
            rows[i]["sma_50"] = 132.0
            rows[i]["sma_200"] = 130.0

        df = pd.DataFrame(rows)
        score = screener.score(df, "GC")
        golden_signals = [s for s in score.signals if "Golden Cross" in s]
        assert len(golden_signals) >= 1, f"Expected golden cross signal, got: {score.signals}"

    def test_dead_cross_detection(self):
        """SMA50 crosses below SMA200 within last 10 rows triggers signal."""
        screener = IndicatorScreener()
        row = _make_bullish_row()
        n = 50
        rows = [dict(row) for _ in range(n)]
        # Before the cross: sma_50 > sma_200
        for i in range(n - 5):
            rows[i]["sma_50"] = 132.0
            rows[i]["sma_200"] = 130.0
        # Cross happens at row n-5
        rows[n - 5]["sma_50"] = 130.0
        rows[n - 5]["sma_200"] = 130.0
        # After cross: sma_50 < sma_200
        for i in range(n - 4, n):
            rows[i]["sma_50"] = 128.0
            rows[i]["sma_200"] = 130.0

        df = pd.DataFrame(rows)
        score = screener.score(df, "DC")
        dead_signals = [s for s in score.signals if "Dead Cross" in s]
        assert len(dead_signals) >= 1, f"Expected dead cross signal, got: {score.signals}"

    def test_signals_populated(self):
        """Bullish stock should have at least one signal populated."""
        screener = IndicatorScreener()
        df = _make_df()
        score = screener.score(df, "AAPL")
        assert isinstance(score.signals, list)
        # A strongly bullish stock with volume_ratio 1.8 should have signals
        assert len(score.signals) > 0, f"Expected signals, got empty list"

    def test_volume_price_confirmation(self):
        """Price up + volume up gives bonus signal."""
        screener = IndicatorScreener()
        row = _make_bullish_row()
        n = 50
        rows = [dict(row) for _ in range(n)]
        # Previous row has lower close
        rows[-2]["close"] = 145.0
        # Current row has higher close + high volume
        rows[-1]["close"] = 150.0
        rows[-1]["volume_ratio"] = 2.5
        df = pd.DataFrame(rows)
        score = screener.score(df, "PVC")
        confirm_signals = [s for s in score.signals if "Price-Volume Confirm" in s]
        assert len(confirm_signals) >= 1

    def test_squeeze_detection_bonus(self):
        """BB squeeze detection adds to score and signal."""
        screener = IndicatorScreener()
        row = _make_bullish_row()
        # Set up squeeze: BB inside KC
        row["bb_lower"] = 140.0
        row["bb_upper"] = 150.0
        row["kc_lower"] = 135.0
        row["kc_upper"] = 155.0
        df = _make_df(base_row=row)
        score = screener.score(df, "SQZ")
        squeeze_signals = [s for s in score.signals if "Squeeze" in s]
        assert len(squeeze_signals) >= 1

    def test_52_week_high(self):
        """Stock near 52-week high gets high volatility_volume score."""
        screener = IndicatorScreener()
        row = _make_bullish_row()
        row["close"] = 150.0
        row["high"] = 151.0
        row["low"] = 148.0
        n = 250
        rows = []
        for i in range(n):
            r = dict(row)
            # Most of history is lower
            if i < n - 10:
                r["close"] = 100.0 + i * 0.1
                r["high"] = 101.0 + i * 0.1
                r["low"] = 99.0 + i * 0.1
            else:
                r["close"] = 150.0
                r["high"] = 151.0
                r["low"] = 148.0
            rows.append(r)
        df = pd.DataFrame(rows)
        score = screener.score(df, "HIGH")
        high_signals = [s for s in score.signals if "52w" in s]
        assert len(high_signals) >= 1

    def test_macd_histogram_direction(self):
        """Increasing positive histogram scores higher than decreasing."""
        screener = IndicatorScreener()

        # Increasing histogram
        row_inc = _make_bullish_row()
        rows_inc = [dict(row_inc) for _ in range(50)]
        rows_inc[-2]["macd_histogram"] = 1.0
        rows_inc[-1]["macd_histogram"] = 2.0
        df_inc = pd.DataFrame(rows_inc)
        score_inc = screener.score(df_inc, "INC")

        # Decreasing histogram
        row_dec = _make_bullish_row()
        rows_dec = [dict(row_dec) for _ in range(50)]
        rows_dec[-2]["macd_histogram"] = 2.0
        rows_dec[-1]["macd_histogram"] = 1.0
        df_dec = pd.DataFrame(rows_dec)
        score_dec = screener.score(df_dec, "DEC")

        # Increasing should score higher
        assert score_inc.momentum_score > score_dec.momentum_score

    def test_breakout_signal(self):
        """Price above donchian upper triggers breakout signal."""
        screener = IndicatorScreener()
        row = _make_bullish_row()
        row["close"] = 155.0
        row["donchian_upper"] = 152.0
        df = _make_df(base_row=row)
        score = screener.score(df, "BRK")
        breakout_signals = [s for s in score.signals if "Breakout" in s]
        assert len(breakout_signals) >= 1
