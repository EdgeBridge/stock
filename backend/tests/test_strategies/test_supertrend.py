"""Tests for Supertrend Strategy."""

import pandas as pd
import pytest

from strategies.supertrend_strategy import SupertrendStrategy
from core.enums import SignalType


def _make_df(
    n: int = 25,
    direction: float = 1.0,
    close: float = 150.0,
    supertrend: float = 140.0,
) -> pd.DataFrame:
    data = []
    for _ in range(n):
        data.append({
            "open": close - 1, "high": close + 2,
            "low": close - 2, "close": close,
            "volume": 1_000_000.0,
            "supertrend": supertrend,
            "supertrend_direction": direction,
            "adx": 30.0, "rsi": 55.0,
        })
    return pd.DataFrame(data)


class TestSupertrend:
    async def test_buy_bullish_confirmed(self):
        strategy = SupertrendStrategy()
        df = _make_df(direction=1.0, close=150.0, supertrend=140.0)
        signal = await strategy.analyze(df, "AAPL")
        assert signal.signal_type == SignalType.BUY
        assert signal.confidence > 0.5

    async def test_sell_bearish(self):
        strategy = SupertrendStrategy()
        df = _make_df(direction=-1.0, close=130.0, supertrend=140.0)
        signal = await strategy.analyze(df, "AAPL")
        assert signal.signal_type == SignalType.SELL

    async def test_hold_not_confirmed(self):
        strategy = SupertrendStrategy(params={"confirmation_bars": 3})
        # Direction switches: not all recent bars bullish
        data = []
        for i in range(25):
            d = -1.0 if i < 23 else 1.0
            data.append({
                "open": 149.0, "high": 152.0, "low": 148.0, "close": 150.0,
                "volume": 1_000_000.0,
                "supertrend": 140.0, "supertrend_direction": d,
                "adx": 30.0, "rsi": 55.0,
            })
        df = pd.DataFrame(data)
        signal = await strategy.analyze(df, "AAPL")
        assert signal.signal_type == SignalType.HOLD

    async def test_hold_bullish_but_price_below_supertrend(self):
        strategy = SupertrendStrategy()
        df = _make_df(direction=1.0, close=135.0, supertrend=140.0)
        signal = await strategy.analyze(df, "AAPL")
        assert signal.signal_type == SignalType.HOLD

    async def test_insufficient_data(self):
        strategy = SupertrendStrategy()
        df = pd.DataFrame({"close": [100.0] * 5})
        signal = await strategy.analyze(df, "AAPL")
        assert signal.signal_type == SignalType.HOLD

    async def test_get_set_params(self):
        strategy = SupertrendStrategy()
        assert strategy.get_params()["confirmation_bars"] == 2
        strategy.set_params({"confirmation_bars": 5})
        assert strategy.get_params()["confirmation_bars"] == 5
