"""Tests for MACD Histogram Strategy."""

import pandas as pd
import pytest

from strategies.macd_histogram import MACDHistogramStrategy
from core.enums import SignalType


def _make_df(
    n: int = 40,
    macd_hist_prev: float = -0.5,
    macd_hist_curr: float = 0.5,
    macd: float = 1.0,
    rsi: float = 55.0,
) -> pd.DataFrame:
    data = []
    for i in range(n - 2):
        data.append({
            "open": 100.0, "high": 102.0, "low": 98.0, "close": 100.0,
            "volume": 1_000_000.0,
            "macd": 0.0, "macd_histogram": -1.0, "macd_signal": 0.0,
            "rsi": 50.0,
        })
    # Previous bar
    data.append({
        "open": 100.0, "high": 102.0, "low": 98.0, "close": 100.0,
        "volume": 1_000_000.0,
        "macd": macd - 0.2, "macd_histogram": macd_hist_prev, "macd_signal": 0.0,
        "rsi": rsi,
    })
    # Current bar
    data.append({
        "open": 101.0, "high": 103.0, "low": 99.0, "close": 102.0,
        "volume": 1_200_000.0,
        "macd": macd, "macd_histogram": macd_hist_curr, "macd_signal": 0.0,
        "rsi": rsi,
    })
    return pd.DataFrame(data)


class TestMACDHistogram:
    async def test_buy_histogram_crosses_up(self):
        strategy = MACDHistogramStrategy()
        df = _make_df(macd_hist_prev=-0.5, macd_hist_curr=0.5)
        signal = await strategy.analyze(df, "AAPL")
        assert signal.signal_type == SignalType.BUY
        assert "crossed above zero" in signal.reason

    async def test_sell_histogram_crosses_down(self):
        strategy = MACDHistogramStrategy()
        df = _make_df(macd_hist_prev=0.5, macd_hist_curr=-0.5)
        signal = await strategy.analyze(df, "AAPL")
        assert signal.signal_type == SignalType.SELL

    async def test_buy_histogram_accelerating(self):
        strategy = MACDHistogramStrategy()
        df = _make_df(macd_hist_prev=0.5, macd_hist_curr=1.5, macd=2.0)
        signal = await strategy.analyze(df, "AAPL")
        assert signal.signal_type == SignalType.BUY
        assert "accelerating" in signal.reason

    async def test_hold_no_crossover(self):
        strategy = MACDHistogramStrategy()
        df = _make_df(macd_hist_prev=1.0, macd_hist_curr=1.0)
        signal = await strategy.analyze(df, "AAPL")
        assert signal.signal_type == SignalType.HOLD

    async def test_hold_negative_not_crossing(self):
        strategy = MACDHistogramStrategy()
        df = _make_df(macd_hist_prev=-1.0, macd_hist_curr=-0.5)
        signal = await strategy.analyze(df, "AAPL")
        assert signal.signal_type == SignalType.HOLD

    async def test_insufficient_data(self):
        strategy = MACDHistogramStrategy()
        df = pd.DataFrame({"close": [100.0] * 10})
        signal = await strategy.analyze(df, "AAPL")
        assert signal.signal_type == SignalType.HOLD

    async def test_get_set_params(self):
        strategy = MACDHistogramStrategy()
        assert strategy.get_params()["min_histogram_change"] == 0.5
        strategy.set_params({"min_histogram_change": 1.0})
        assert strategy.get_params()["min_histogram_change"] == 1.0
