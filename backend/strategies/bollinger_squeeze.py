"""Bollinger Squeeze Strategy.

Detects volatility squeeze (BB inside Keltner Channel) and trades the breakout.
BUY: Squeeze fires + price breaks above upper BB + MACD histogram positive.
SELL: Price drops below BB mid or squeeze re-engages after breakout.
"""

import pandas as pd

from strategies.base import BaseStrategy, Signal
from core.enums import SignalType


class BollingerSqueezeStrategy(BaseStrategy):
    name = "bollinger_squeeze"
    display_name = "Bollinger Squeeze"
    applicable_market_types = ["sideways", "trending"]
    required_timeframe = "1D"
    min_candles_required = 30

    def __init__(self, params: dict | None = None):
        p = params or {}
        self._squeeze_min_bars = p.get("squeeze_min_bars", 3)

    async def analyze(self, df: pd.DataFrame, symbol: str) -> Signal:
        if len(df) < self.min_candles_required:
            return self._hold("Insufficient data")

        row = df.iloc[-1]
        price = float(row["close"])

        bb_upper = row.get("bb_upper")
        bb_lower = row.get("bb_lower")
        bb_mid = row.get("bb_mid")
        kc_upper = row.get("kc_upper")
        kc_lower = row.get("kc_lower")
        macd_hist = row.get("macd_histogram")

        required = [bb_upper, bb_lower, bb_mid, kc_upper, kc_lower]
        if any(v is None or pd.isna(v) for v in required):
            return self._hold("Indicators not ready")

        indicators = {
            "bb_upper": float(bb_upper),
            "bb_lower": float(bb_lower),
            "bb_mid": float(bb_mid),
            "kc_upper": float(kc_upper),
            "kc_lower": float(kc_lower),
            "macd_histogram": float(macd_hist) if macd_hist is not None and not pd.isna(macd_hist) else 0,
        }

        # Check squeeze state: BB inside KC
        in_squeeze = bb_lower > kc_lower and bb_upper < kc_upper

        # Count consecutive squeeze bars in recent history
        squeeze_bars = 0
        for i in range(2, min(self._squeeze_min_bars + 5, len(df))):
            prev = df.iloc[-i]
            prev_bb_l = prev.get("bb_lower")
            prev_bb_u = prev.get("bb_upper")
            prev_kc_l = prev.get("kc_lower")
            prev_kc_u = prev.get("kc_upper")
            if any(v is None or pd.isna(v) for v in [prev_bb_l, prev_bb_u, prev_kc_l, prev_kc_u]):
                break
            if prev_bb_l > prev_kc_l and prev_bb_u < prev_kc_u:
                squeeze_bars += 1
            else:
                break

        indicators["squeeze_bars"] = squeeze_bars
        indicators["in_squeeze"] = in_squeeze

        # Squeeze just released (was in squeeze, now breaking out)
        squeeze_released = not in_squeeze and squeeze_bars >= self._squeeze_min_bars

        if squeeze_released:
            macd_positive = macd_hist is not None and not pd.isna(macd_hist) and float(macd_hist) > 0
            price_above_upper = price > float(bb_upper)

            if price_above_upper and macd_positive:
                confidence = 0.65
                if squeeze_bars >= self._squeeze_min_bars + 3:
                    confidence += 0.10
                return Signal(
                    signal_type=SignalType.BUY,
                    confidence=min(confidence, 0.95),
                    strategy_name=self.name,
                    reason=f"Squeeze fired after {squeeze_bars} bars, price > BB upper, MACD positive",
                    suggested_price=price,
                    indicators=indicators,
                )

            if price < float(bb_lower) and not macd_positive:
                return Signal(
                    signal_type=SignalType.SELL,
                    confidence=0.6,
                    strategy_name=self.name,
                    reason=f"Squeeze fired bearish after {squeeze_bars} bars",
                    suggested_price=price,
                    indicators=indicators,
                )

        # Already in position: sell if price drops below BB mid
        if not in_squeeze and price < float(bb_mid):
            prev_close = float(df.iloc[-2]["close"]) if len(df) >= 2 else price
            if prev_close > float(bb_mid):
                return Signal(
                    signal_type=SignalType.SELL,
                    confidence=0.5,
                    strategy_name=self.name,
                    reason="Price crossed below BB mid",
                    suggested_price=price,
                    indicators=indicators,
                )

        return self._hold(f"Squeeze={'active' if in_squeeze else 'none'}, bars={squeeze_bars}")

    def _hold(self, reason: str) -> Signal:
        return Signal(
            signal_type=SignalType.HOLD,
            confidence=0.0,
            strategy_name=self.name,
            reason=reason,
        )

    def get_params(self) -> dict:
        return {"squeeze_min_bars": self._squeeze_min_bars}

    def set_params(self, params: dict) -> None:
        self._squeeze_min_bars = params.get("squeeze_min_bars", self._squeeze_min_bars)
