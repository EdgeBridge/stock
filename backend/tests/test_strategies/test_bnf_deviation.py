"""Tests for BNF Deviation (Mean Reversion) Strategy."""

import numpy as np
import pandas as pd
import pytest

from strategies.bnf_deviation import BNFDeviationStrategy
from core.enums import SignalType


def _make_df(n: int = 35, close: float = 100.0, sma_25: float = 100.0,
             rsi: float = 50.0) -> pd.DataFrame:
    """Create DataFrame with deviation scenario."""
    data = {
        "open": [close * 0.999] * n,
        "high": [close * 1.01] * n,
        "low": [close * 0.99] * n,
        "close": [close] * n,
        "volume": [1_000_000.0] * n,
        "sma_25": [sma_25] * n,
        "rsi": [rsi] * n,
    }
    return pd.DataFrame(data)


class TestBNFDeviation:
    async def test_buy_oversold(self):
        """Price -6% below SMA should trigger buy (threshold -5%)."""
        strategy = BNFDeviationStrategy()
        df = _make_df(close=94.0, sma_25=100.0)
        signal = await strategy.analyze(df, "AAPL")
        assert signal.signal_type == SignalType.BUY
        assert "mean reversion buy" in signal.reason.lower()

    async def test_sell_overbought(self):
        """Price +4% above SMA should trigger sell (threshold +3%)."""
        strategy = BNFDeviationStrategy()
        df = _make_df(close=104.0, sma_25=100.0)
        signal = await strategy.analyze(df, "AAPL")
        assert signal.signal_type == SignalType.SELL
        assert "mean reversion sell" in signal.reason.lower()

    async def test_hold_neutral(self):
        """Price near SMA should hold."""
        strategy = BNFDeviationStrategy()
        df = _make_df(close=101.0, sma_25=100.0)
        signal = await strategy.analyze(df, "AAPL")
        assert signal.signal_type == SignalType.HOLD

    async def test_confidence_scales_with_deviation(self):
        strategy = BNFDeviationStrategy()
        df_mild = _make_df(close=94.0, sma_25=100.0)    # -6%
        df_deep = _make_df(close=88.0, sma_25=100.0)    # -12%
        s_mild = await strategy.analyze(df_mild, "AAPL")
        s_deep = await strategy.analyze(df_deep, "AAPL")
        assert s_deep.confidence > s_mild.confidence

    async def test_rsi_boost(self):
        """RSI below threshold should boost confidence."""
        strategy = BNFDeviationStrategy()
        df_no_rsi = _make_df(close=94.0, sma_25=100.0, rsi=50.0)
        df_rsi = _make_df(close=94.0, sma_25=100.0, rsi=25.0)
        s_no = await strategy.analyze(df_no_rsi, "AAPL")
        s_rsi = await strategy.analyze(df_rsi, "AAPL")
        assert s_rsi.confidence > s_no.confidence

    async def test_insufficient_data(self):
        strategy = BNFDeviationStrategy()
        df = pd.DataFrame({"close": [100.0] * 5})
        signal = await strategy.analyze(df, "AAPL")
        assert signal.signal_type == SignalType.HOLD

    async def test_sma_calculated_if_missing(self):
        """SMA should be calculated from raw prices if column missing."""
        strategy = BNFDeviationStrategy()
        closes = [100.0] * 35
        closes[-1] = 90.0  # -10% deviation
        df = pd.DataFrame({
            "open": closes, "high": closes, "low": closes,
            "close": closes, "volume": [1_000_000.0] * 35,
        })
        signal = await strategy.analyze(df, "AAPL")
        assert signal.signal_type == SignalType.BUY

    async def test_sell_confidence_scales(self):
        strategy = BNFDeviationStrategy()
        df_mild = _make_df(close=104.0, sma_25=100.0)   # +4%
        df_strong = _make_df(close=110.0, sma_25=100.0)  # +10%
        s_mild = await strategy.analyze(df_mild, "AAPL")
        s_strong = await strategy.analyze(df_strong, "AAPL")
        assert s_strong.confidence > s_mild.confidence

    async def test_indicators_present(self):
        strategy = BNFDeviationStrategy()
        df = _make_df(close=94.0, sma_25=100.0)
        signal = await strategy.analyze(df, "AAPL")
        assert "deviation_pct" in signal.indicators
        assert "sma" in signal.indicators
        assert signal.indicators["deviation_pct"] == -6.0

    async def test_get_set_params(self):
        strategy = BNFDeviationStrategy()
        params = strategy.get_params()
        assert params["sma_period"] == 25
        assert params["buy_deviation"] == -5.0
        assert params["sell_deviation"] == 3.0
        assert params["rsi_boost_threshold"] == 35.0

        strategy.set_params({"buy_deviation": -7.0, "sell_deviation": 5.0})
        assert strategy.get_params()["buy_deviation"] == -7.0
        assert strategy.get_params()["sell_deviation"] == 5.0

    async def test_custom_params(self):
        """Custom thresholds should work."""
        strategy = BNFDeviationStrategy(params={"buy_deviation": -3.0, "sell_deviation": 2.0})
        df = _make_df(close=96.5, sma_25=100.0)  # -3.5%
        signal = await strategy.analyze(df, "AAPL")
        assert signal.signal_type == SignalType.BUY
