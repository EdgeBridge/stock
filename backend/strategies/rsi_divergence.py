"""RSI Divergence Strategy.

Detects bullish/bearish divergence between price and RSI.
BUY: Price makes lower low but RSI makes higher low (bullish divergence).
SELL: Price makes higher high but RSI makes lower high (bearish divergence).
"""

import pandas as pd
import numpy as np

from strategies.base import BaseStrategy, Signal
from core.enums import SignalType


class RSIDivergenceStrategy(BaseStrategy):
    name = "rsi_divergence"
    display_name = "RSI Divergence"
    applicable_market_types = ["sideways", "downtrend"]
    required_timeframe = "1D"
    min_candles_required = 30

    def __init__(self, params: dict | None = None):
        p = params or {}
        self._rsi_period = p.get("rsi_period", 14)
        self._overbought = p.get("overbought", 70)
        self._oversold = p.get("oversold", 30)
        self._divergence_lookback = p.get("divergence_lookback", 14)
        self._min_price_move_pct = p.get("min_price_move_pct", 3.0)

    async def analyze(self, df: pd.DataFrame, symbol: str) -> Signal:
        if len(df) < self.min_candles_required:
            return self._hold("Insufficient data")

        row = df.iloc[-1]
        price = float(row["close"])
        rsi = row.get("rsi")

        if rsi is None or pd.isna(rsi):
            return self._hold("RSI not available")

        rsi = float(rsi)
        lookback = min(self._divergence_lookback, len(df) - 1)
        recent = df.iloc[-lookback:]

        indicators = {"rsi": rsi, "lookback": lookback}

        # Find price and RSI extremes in the lookback window
        price_lows = recent["close"].values
        rsi_values = recent.get("rsi")
        if rsi_values is None or rsi_values.isna().all():
            return self._hold("RSI data incomplete")

        rsi_arr = rsi_values.values

        # Bullish divergence: price lower low, RSI higher low
        price_min_idx = int(np.nanargmin(price_lows))
        if price_min_idx > 0 and price_min_idx < lookback - 1:
            # Compare current low region with earlier low
            first_half = price_lows[:lookback // 2]
            second_half = price_lows[lookback // 2:]
            rsi_first = rsi_arr[:lookback // 2]
            rsi_second = rsi_arr[lookback // 2:]

            if len(first_half) > 0 and len(second_half) > 0:
                first_min_p = float(np.nanmin(first_half))
                second_min_p = float(np.nanmin(second_half))
                first_min_r = float(np.nanmin(rsi_first)) if not np.all(np.isnan(rsi_first)) else 50
                second_min_r = float(np.nanmin(rsi_second)) if not np.all(np.isnan(rsi_second)) else 50

                price_drop = (first_min_p - second_min_p) / first_min_p * 100
                if price_drop > self._min_price_move_pct and second_min_r > first_min_r:
                    # Bullish divergence confirmed
                    if rsi < self._oversold + 10:
                        confidence = 0.7 if rsi < self._oversold else 0.55
                        return Signal(
                            signal_type=SignalType.BUY,
                            confidence=confidence,
                            strategy_name=self.name,
                            reason=f"Bullish divergence: price lower low, RSI higher low, RSI={rsi:.0f}",
                            suggested_price=price,
                            indicators=indicators,
                        )

        # Bearish divergence: price higher high, RSI lower high
        price_max_idx = int(np.nanargmax(price_lows))
        if price_max_idx > 0 and price_max_idx < lookback - 1:
            first_half = price_lows[:lookback // 2]
            second_half = price_lows[lookback // 2:]
            rsi_first = rsi_arr[:lookback // 2]
            rsi_second = rsi_arr[lookback // 2:]

            if len(first_half) > 0 and len(second_half) > 0:
                first_max_p = float(np.nanmax(first_half))
                second_max_p = float(np.nanmax(second_half))
                first_max_r = float(np.nanmax(rsi_first)) if not np.all(np.isnan(rsi_first)) else 50
                second_max_r = float(np.nanmax(rsi_second)) if not np.all(np.isnan(rsi_second)) else 50

                price_rise = (second_max_p - first_max_p) / first_max_p * 100
                if price_rise > self._min_price_move_pct and second_max_r < first_max_r:
                    if rsi > self._overbought - 10:
                        confidence = 0.7 if rsi > self._overbought else 0.55
                        return Signal(
                            signal_type=SignalType.SELL,
                            confidence=confidence,
                            strategy_name=self.name,
                            reason=f"Bearish divergence: price higher high, RSI lower high, RSI={rsi:.0f}",
                            suggested_price=price,
                            indicators=indicators,
                        )

        # Extreme RSI zones as secondary signals
        if rsi < self._oversold:
            return Signal(
                signal_type=SignalType.BUY,
                confidence=0.4,
                strategy_name=self.name,
                reason=f"RSI oversold at {rsi:.0f}",
                suggested_price=price,
                indicators=indicators,
            )

        if rsi > self._overbought:
            return Signal(
                signal_type=SignalType.SELL,
                confidence=0.4,
                strategy_name=self.name,
                reason=f"RSI overbought at {rsi:.0f}",
                suggested_price=price,
                indicators=indicators,
            )

        return self._hold(f"No divergence detected, RSI={rsi:.0f}")

    def _hold(self, reason: str) -> Signal:
        return Signal(
            signal_type=SignalType.HOLD,
            confidence=0.0,
            strategy_name=self.name,
            reason=reason,
        )

    def get_params(self) -> dict:
        return {
            "rsi_period": self._rsi_period,
            "overbought": self._overbought,
            "oversold": self._oversold,
            "divergence_lookback": self._divergence_lookback,
            "min_price_move_pct": self._min_price_move_pct,
        }

    def set_params(self, params: dict) -> None:
        self._rsi_period = params.get("rsi_period", self._rsi_period)
        self._overbought = params.get("overbought", self._overbought)
        self._oversold = params.get("oversold", self._oversold)
        self._divergence_lookback = params.get("divergence_lookback", self._divergence_lookback)
        self._min_price_move_pct = params.get("min_price_move_pct", self._min_price_move_pct)
