"""Sector Rotation Strategy.

Monthly rotation into strongest sectors based on relative strength.
BUY: Sector shows strong momentum vs SPY (top-N sectors).
SELL: Sector loses relative strength.
"""

import pandas as pd

from strategies.base import BaseStrategy, Signal
from core.enums import SignalType


class SectorRotationStrategy(BaseStrategy):
    name = "sector_rotation"
    display_name = "Sector Rotation"
    applicable_market_types = ["trending", "sideways"]
    required_timeframe = "1M"
    min_candles_required = 30

    def __init__(self, params: dict | None = None):
        p = params or {}
        self._lookback_weeks = p.get("lookback_weeks", 12)
        self._min_strength_score = p.get("min_strength_score", 60)

    async def analyze(self, df: pd.DataFrame, symbol: str) -> Signal:
        if len(df) < self.min_candles_required:
            return self._hold("Insufficient data")

        row = df.iloc[-1]
        price = float(row["close"])

        # Calculate multi-timeframe momentum for sector strength
        lookback_days = self._lookback_weeks * 5  # ~5 trading days/week
        lookback_idx = max(0, len(df) - lookback_days)
        past_price = float(df.iloc[lookback_idx]["close"])
        period_return = (price - past_price) / past_price if past_price > 0 else 0

        # Shorter-term momentum (4 weeks)
        short_idx = max(0, len(df) - 20)
        short_price = float(df.iloc[short_idx]["close"])
        short_return = (price - short_price) / short_price if short_price > 0 else 0

        # Strength score: blend of period and short-term return
        strength_score = (period_return * 60 + short_return * 40) * 100

        ema_20 = row.get("ema_20")
        ema_50 = row.get("ema_50")
        rsi = row.get("rsi")
        volume_ratio = row.get("volume_ratio")

        indicators = {
            "period_return": period_return,
            "short_return": short_return,
            "strength_score": strength_score,
            "rsi": float(rsi) if rsi is not None and not pd.isna(rsi) else 50,
        }

        # BUY: Strong sector momentum
        if strength_score >= self._min_strength_score:
            confidence = 0.50
            if strength_score > self._min_strength_score * 1.5:
                confidence += 0.15
            elif strength_score > self._min_strength_score * 1.2:
                confidence += 0.10
            if ema_20 is not None and ema_50 is not None and not pd.isna(ema_20) and not pd.isna(ema_50):
                if float(ema_20) > float(ema_50):
                    confidence += 0.10
            if volume_ratio is not None and not pd.isna(volume_ratio) and float(volume_ratio) > 1.2:
                confidence += 0.05
            return Signal(
                signal_type=SignalType.BUY,
                confidence=min(confidence, 0.95),
                strategy_name=self.name,
                reason=f"Sector strength {strength_score:.0f}, return {period_return:.1%}",
                suggested_price=price,
                indicators=indicators,
            )

        # SELL: Weak sector
        if strength_score < 0 and short_return < -0.03:
            confidence = 0.5
            if strength_score < -self._min_strength_score:
                confidence += 0.15
            return Signal(
                signal_type=SignalType.SELL,
                confidence=min(confidence, 0.95),
                strategy_name=self.name,
                reason=f"Sector weakness {strength_score:.0f}, short return {short_return:.1%}",
                suggested_price=price,
                indicators=indicators,
            )

        return self._hold(f"Strength={strength_score:.0f}, below threshold")

    def _hold(self, reason: str) -> Signal:
        return Signal(
            signal_type=SignalType.HOLD,
            confidence=0.0,
            strategy_name=self.name,
            reason=reason,
        )

    def get_params(self) -> dict:
        return {
            "lookback_weeks": self._lookback_weeks,
            "min_strength_score": self._min_strength_score,
        }

    def set_params(self, params: dict) -> None:
        self._lookback_weeks = params.get("lookback_weeks", self._lookback_weeks)
        self._min_strength_score = params.get("min_strength_score", self._min_strength_score)
