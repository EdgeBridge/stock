"""Dual Momentum Strategy.

Monthly rebalance using absolute + relative momentum.
BUY: Top-N performers with positive absolute momentum.
SELL: When absolute momentum turns negative (rotate to cash ETF).
"""

import pandas as pd

from strategies.base import BaseStrategy, Signal
from core.enums import SignalType


class DualMomentumStrategy(BaseStrategy):
    name = "dual_momentum"
    display_name = "Dual Momentum"
    applicable_market_types = ["trending"]
    required_timeframe = "1M"
    min_candles_required = 30

    def __init__(self, params: dict | None = None):
        p = params or {}
        self._lookback_months = p.get("lookback_months", 12)
        self._min_absolute_return = p.get("min_absolute_return", 0.0)

    async def analyze(self, df: pd.DataFrame, symbol: str) -> Signal:
        if len(df) < self.min_candles_required:
            return self._hold("Insufficient data")

        row = df.iloc[-1]
        price = float(row["close"])

        # Calculate momentum using ROC columns if available, else manual
        roc_20 = row.get("roc_20")
        rsi = row.get("rsi")
        ema_50 = row.get("ema_50")
        ema_20 = row.get("ema_20")
        volume_ratio = row.get("volume_ratio")

        # Calculate lookback return manually
        lookback_idx = max(0, len(df) - self._lookback_months * 21)  # ~21 trading days/month
        if lookback_idx < len(df) - 1:
            past_price = float(df.iloc[lookback_idx]["close"])
            absolute_return = (price - past_price) / past_price
        else:
            absolute_return = 0.0

        # 3-month momentum for recency
        short_idx = max(0, len(df) - 63)
        short_price = float(df.iloc[short_idx]["close"])
        short_return = (price - short_price) / short_price if short_price > 0 else 0.0

        indicators = {
            "absolute_return": absolute_return,
            "short_return": short_return,
            "rsi": float(rsi) if rsi is not None and not pd.isna(rsi) else 50.0,
        }

        # BUY: positive absolute momentum + strong short-term trend
        if absolute_return > self._min_absolute_return and short_return > 0:
            confidence = 0.5
            if absolute_return > 0.15:
                confidence += 0.15
            elif absolute_return > 0.08:
                confidence += 0.10
            if short_return > 0.05:
                confidence += 0.10
            if ema_20 is not None and ema_50 is not None and not pd.isna(ema_20) and not pd.isna(ema_50):
                if ema_20 > ema_50:
                    confidence += 0.10
            return Signal(
                signal_type=SignalType.BUY,
                confidence=min(confidence, 0.95),
                strategy_name=self.name,
                reason=f"Abs momentum {absolute_return:.1%}, Short {short_return:.1%}",
                suggested_price=price,
                indicators=indicators,
            )

        # SELL: negative absolute momentum
        if absolute_return < 0:
            confidence = 0.6 if absolute_return < -0.05 else 0.4
            return Signal(
                signal_type=SignalType.SELL,
                confidence=confidence,
                strategy_name=self.name,
                reason=f"Negative momentum {absolute_return:.1%}",
                suggested_price=price,
                indicators=indicators,
            )

        return self._hold("Momentum inconclusive")

    def _hold(self, reason: str) -> Signal:
        return Signal(
            signal_type=SignalType.HOLD,
            confidence=0.0,
            strategy_name=self.name,
            reason=reason,
        )

    def get_params(self) -> dict:
        return {
            "lookback_months": self._lookback_months,
            "min_absolute_return": self._min_absolute_return,
        }

    def set_params(self, params: dict) -> None:
        self._lookback_months = params.get("lookback_months", self._lookback_months)
        self._min_absolute_return = params.get("min_absolute_return", self._min_absolute_return)
