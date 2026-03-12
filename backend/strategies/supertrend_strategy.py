"""Supertrend Strategy.

Uses the Supertrend indicator for trend direction with confirmation.

Buy: Supertrend direction flips bullish (direction changes from -1 to 1) with confirmation
Sell: Supertrend direction flips bearish
"""

import pandas as pd

from strategies.base import BaseStrategy, Signal
from core.enums import SignalType


class SupertrendStrategy(BaseStrategy):
    name = "supertrend"
    display_name = "Supertrend"
    applicable_market_types = ["trending"]
    required_timeframe = "1D"
    min_candles_required = 20

    def __init__(self, params: dict | None = None):
        p = params or {}
        self._confirmation_bars = p.get("confirmation_bars", 2)

    async def analyze(self, df: pd.DataFrame, symbol: str) -> Signal:
        if len(df) < self.min_candles_required:
            return self._hold("Insufficient data")

        row = df.iloc[-1]
        price = float(row["close"])

        st_dir = row.get("supertrend_direction")
        supertrend = row.get("supertrend")
        adx = row.get("adx")
        rsi = row.get("rsi")

        if st_dir is None or pd.isna(st_dir):
            return self._hold("Supertrend not ready")

        indicators = {
            "supertrend": float(supertrend) if supertrend and not pd.isna(supertrend) else 0,
            "supertrend_direction": float(st_dir),
            "adx": float(adx) if adx and not pd.isna(adx) else 0,
            "rsi": float(rsi) if rsi and not pd.isna(rsi) else 50,
        }

        # Check confirmation: direction consistent for N bars
        confirmed_bull = self._check_confirmation(df, bullish=True)
        confirmed_bear = self._check_confirmation(df, bullish=False)

        # BUY: bullish supertrend confirmed
        if st_dir > 0 and confirmed_bull and price > supertrend:
            confidence = self._calc_confidence(adx, rsi, price, supertrend)
            return Signal(
                signal_type=SignalType.BUY,
                confidence=confidence,
                strategy_name=self.name,
                reason=f"Supertrend bullish (confirmed {self._confirmation_bars} bars)",
                suggested_price=price,
                indicators=indicators,
            )

        # SELL: bearish supertrend confirmed
        if st_dir < 0 and confirmed_bear and price < supertrend:
            return Signal(
                signal_type=SignalType.SELL,
                confidence=0.7,
                strategy_name=self.name,
                reason="Supertrend bearish",
                suggested_price=price,
                indicators=indicators,
            )

        return self._hold("No supertrend signal")

    def _check_confirmation(self, df: pd.DataFrame, bullish: bool = True) -> bool:
        """Check if supertrend direction is consistent for N bars."""
        if len(df) < self._confirmation_bars + 1:
            return False

        recent = df.iloc[-self._confirmation_bars:]
        directions = recent.get("supertrend_direction")
        if directions is None:
            return False

        if bullish:
            return all(not pd.isna(d) and d > 0 for d in directions)
        return all(not pd.isna(d) and d < 0 for d in directions)

    def _calc_confidence(self, adx, rsi, price, supertrend) -> float:
        conf = 0.55
        if adx and not pd.isna(adx) and adx > 25:
            conf += 0.15
        if rsi and not pd.isna(rsi) and 40 < rsi < 70:
            conf += 0.10
        if supertrend and not pd.isna(supertrend) and supertrend > 0:
            gap_pct = (price - supertrend) / supertrend * 100
            if 1 < gap_pct < 5:
                conf += 0.10
        return min(conf, 0.95)

    def _hold(self, reason: str) -> Signal:
        return Signal(
            signal_type=SignalType.HOLD,
            confidence=0.0,
            strategy_name=self.name,
            reason=reason,
        )

    def get_params(self) -> dict:
        return {"confirmation_bars": self._confirmation_bars}

    def set_params(self, params: dict) -> None:
        self._confirmation_bars = params.get("confirmation_bars", self._confirmation_bars)
