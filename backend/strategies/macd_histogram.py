"""MACD Histogram Strategy.

Detects momentum shifts via MACD histogram direction changes.

Buy: MACD histogram turns positive (crosses above zero) with increasing momentum
Sell: MACD histogram turns negative (crosses below zero)
"""

import pandas as pd

from strategies.base import BaseStrategy, Signal
from core.enums import SignalType


class MACDHistogramStrategy(BaseStrategy):
    name = "macd_histogram"
    display_name = "MACD Histogram"
    applicable_market_types = ["all"]
    required_timeframe = "1D"
    min_candles_required = 35

    def __init__(self, params: dict | None = None):
        p = params or {}
        self._min_histogram_change = p.get("min_histogram_change", 0.5)

    async def analyze(self, df: pd.DataFrame, symbol: str) -> Signal:
        if len(df) < self.min_candles_required:
            return self._hold("Insufficient data")

        row = df.iloc[-1]
        prev = df.iloc[-2]
        price = float(row["close"])

        macd_hist = row.get("macd_histogram")
        prev_hist = prev.get("macd_histogram")
        macd = row.get("macd")
        macd_signal = row.get("macd_signal")
        rsi = row.get("rsi")

        if any(v is None or pd.isna(v) for v in [macd_hist, prev_hist]):
            return self._hold("MACD not ready")

        indicators = {
            "macd": float(macd) if macd and not pd.isna(macd) else 0,
            "macd_histogram": float(macd_hist),
            "macd_signal": float(macd_signal) if macd_signal and not pd.isna(macd_signal) else 0,
            "rsi": float(rsi) if rsi and not pd.isna(rsi) else 50,
        }

        # BUY: histogram crosses above zero or accelerates positive
        hist_cross_up = prev_hist <= 0 and macd_hist > 0
        hist_accelerating = (
            macd_hist > 0 and macd_hist > prev_hist
            and (macd_hist - prev_hist) > self._min_histogram_change
        )

        if hist_cross_up:
            confidence = self._calc_confidence(macd_hist, rsi, cross=True)
            return Signal(
                signal_type=SignalType.BUY,
                confidence=confidence,
                strategy_name=self.name,
                reason=f"MACD histogram crossed above zero ({macd_hist:.2f})",
                suggested_price=price,
                indicators=indicators,
            )

        if hist_accelerating and macd and not pd.isna(macd) and macd > 0:
            confidence = self._calc_confidence(macd_hist, rsi, cross=False)
            return Signal(
                signal_type=SignalType.BUY,
                confidence=confidence,
                strategy_name=self.name,
                reason=f"MACD histogram accelerating ({prev_hist:.2f} -> {macd_hist:.2f})",
                suggested_price=price,
                indicators=indicators,
            )

        # SELL: histogram crosses below zero
        hist_cross_down = prev_hist >= 0 and macd_hist < 0

        if hist_cross_down:
            return Signal(
                signal_type=SignalType.SELL,
                confidence=0.65,
                strategy_name=self.name,
                reason=f"MACD histogram crossed below zero ({macd_hist:.2f})",
                suggested_price=price,
                indicators=indicators,
            )

        return self._hold("No MACD signal")

    def _calc_confidence(self, hist, rsi, cross: bool) -> float:
        conf = 0.60 if cross else 0.50
        if rsi and not pd.isna(rsi):
            if 40 < rsi < 65:
                conf += 0.10
            elif rsi < 40:
                conf += 0.15  # Oversold bounce
        if abs(hist) > 1.0:
            conf += 0.10
        return min(conf, 0.90)

    def _hold(self, reason: str) -> Signal:
        return Signal(
            signal_type=SignalType.HOLD,
            confidence=0.0,
            strategy_name=self.name,
            reason=reason,
        )

    def get_params(self) -> dict:
        return {"min_histogram_change": self._min_histogram_change}

    def set_params(self, params: dict) -> None:
        self._min_histogram_change = params.get("min_histogram_change", self._min_histogram_change)
