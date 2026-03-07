"""Tests for IndicatorService."""

import numpy as np
import pandas as pd
import pytest

from data.indicator_service import IndicatorService


def _make_ohlcv(n: int = 250, trend: str = "up") -> pd.DataFrame:
    """Generate synthetic OHLCV data for testing."""
    np.random.seed(42)
    base = 100.0
    prices = []
    for i in range(n):
        if trend == "up":
            base += np.random.normal(0.1, 1.0)
        elif trend == "down":
            base -= np.random.normal(0.1, 1.0)
        else:
            base += np.random.normal(0.0, 1.0)
        prices.append(max(base, 1.0))

    close = np.array(prices)
    high = close * (1 + np.random.uniform(0, 0.02, n))
    low = close * (1 - np.random.uniform(0, 0.02, n))
    open_ = close * (1 + np.random.normal(0, 0.005, n))
    volume = np.random.randint(100_000, 1_000_000, n).astype(float)

    return pd.DataFrame({
        "open": open_,
        "high": high,
        "low": low,
        "close": close,
        "volume": volume,
    })


class TestIndicatorService:
    def test_add_all_indicators(self):
        df = _make_ohlcv(250)
        result = IndicatorService.add_all_indicators(df)

        # Check key indicators exist
        assert "ema_10" in result.columns
        assert "ema_20" in result.columns
        assert "ema_50" in result.columns
        assert "ema_200" in result.columns
        assert "sma_50" in result.columns
        assert "sma_200" in result.columns
        assert "rsi" in result.columns
        assert "macd" in result.columns
        assert "macd_signal" in result.columns
        assert "macd_histogram" in result.columns
        assert "bb_lower" in result.columns
        assert "bb_upper" in result.columns
        assert "atr" in result.columns
        assert "adx" in result.columns
        assert "obv" in result.columns
        assert "supertrend" in result.columns
        assert "donchian_lower" in result.columns
        assert "donchian_upper" in result.columns
        assert "roc_5" in result.columns
        assert "volume_ratio" in result.columns
        assert "stoch_rsi_k" in result.columns
        assert "kc_lower" in result.columns

    def test_add_indicators_short_data(self):
        df = _make_ohlcv(50)
        result = IndicatorService.add_all_indicators(df)
        # Should still work, but EMA 200 not added
        assert "ema_10" in result.columns
        assert "ema_200" not in result.columns

    def test_add_indicators_empty_df(self):
        df = pd.DataFrame()
        result = IndicatorService.add_all_indicators(df)
        assert result.empty

    def test_add_indicators_too_few_rows(self):
        df = _make_ohlcv(5)
        result = IndicatorService.add_all_indicators(df)
        # Returns unchanged since < 10 rows
        assert len(result) == 5
        assert "rsi" not in result.columns

    def test_rsi_in_range(self):
        df = _make_ohlcv(250)
        result = IndicatorService.add_all_indicators(df)
        rsi = result["rsi"].dropna()
        assert (rsi >= 0).all()
        assert (rsi <= 100).all()

    def test_bollinger_bands_ordering(self):
        df = _make_ohlcv(250)
        result = IndicatorService.add_all_indicators(df)
        valid = result.dropna(subset=["bb_lower", "bb_mid", "bb_upper"])
        assert (valid["bb_lower"] <= valid["bb_mid"]).all()
        assert (valid["bb_mid"] <= valid["bb_upper"]).all()

    def test_atr_positive(self):
        df = _make_ohlcv(250)
        result = IndicatorService.add_all_indicators(df)
        atr = result["atr"].dropna()
        assert (atr > 0).all()

    def test_volume_ratio(self):
        df = _make_ohlcv(250)
        result = IndicatorService.add_all_indicators(df)
        vr = result["volume_ratio"].dropna()
        assert (vr > 0).all()

    def test_does_not_mutate_input(self):
        df = _make_ohlcv(250)
        original_cols = list(df.columns)
        IndicatorService.add_all_indicators(df)
        assert list(df.columns) == original_cols


class TestEMAAlignment:
    def test_perfect_bull(self):
        df = pd.DataFrame([{
            "close": 200.0,
            "ema_10": 195.0,
            "ema_20": 190.0,
            "ema_50": 180.0,
            "ema_200": 170.0,
        }])
        assert IndicatorService.detect_ema_alignment(df) == "PERFECT_BULL"

    def test_perfect_bear(self):
        df = pd.DataFrame([{
            "close": 100.0,
            "ema_10": 105.0,
            "ema_20": 110.0,
            "ema_50": 120.0,
            "ema_200": 130.0,
        }])
        assert IndicatorService.detect_ema_alignment(df) == "PERFECT_BEAR"

    def test_partial_bull_no_200(self):
        df = pd.DataFrame([{
            "close": 200.0,
            "ema_10": 195.0,
            "ema_20": 190.0,
            "ema_50": 180.0,
        }])
        assert IndicatorService.detect_ema_alignment(df) == "PARTIAL_BULL"

    def test_partial_bear_no_200(self):
        df = pd.DataFrame([{
            "close": 100.0,
            "ema_10": 105.0,
            "ema_20": 110.0,
            "ema_50": 120.0,
        }])
        assert IndicatorService.detect_ema_alignment(df) == "PARTIAL_BEAR"

    def test_mixed(self):
        df = pd.DataFrame([{
            "close": 150.0,
            "ema_10": 155.0,
            "ema_20": 145.0,
            "ema_50": 160.0,
        }])
        assert IndicatorService.detect_ema_alignment(df) == "MIXED"

    def test_empty_df(self):
        df = pd.DataFrame()
        assert IndicatorService.detect_ema_alignment(df) == "MIXED"

    def test_missing_emas(self):
        df = pd.DataFrame([{"close": 100.0}])
        assert IndicatorService.detect_ema_alignment(df) == "MIXED"


class TestSqueeze:
    def test_squeeze_detected(self):
        df = pd.DataFrame([{
            "bb_lower": 95.0,
            "bb_upper": 105.0,
            "kc_lower": 90.0,
            "kc_upper": 110.0,
        }])
        assert IndicatorService.detect_squeeze(df) == True

    def test_no_squeeze(self):
        df = pd.DataFrame([{
            "bb_lower": 85.0,
            "bb_upper": 115.0,
            "kc_lower": 90.0,
            "kc_upper": 110.0,
        }])
        assert IndicatorService.detect_squeeze(df) == False

    def test_squeeze_empty(self):
        assert IndicatorService.detect_squeeze(pd.DataFrame()) is False

    def test_squeeze_missing_columns(self):
        df = pd.DataFrame([{"bb_lower": 95.0}])
        assert IndicatorService.detect_squeeze(df) is False
