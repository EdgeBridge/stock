"""Larry Williams Volatility Breakout + Williams %R Strategy.

Adapted from coin project (4h crypto -> 1D stocks).

Buy: close > open + k*(prev_high - prev_low) AND %R oversold exit AND close > SMA
Sell: close < open - k*(prev_high - prev_low) AND %R overbought
"""

import pandas as pd

from strategies.base import BaseStrategy, Signal
from core.enums import SignalType


class LarryWilliamsStrategy(BaseStrategy):
    name = "larry_williams"
    display_name = "Larry Williams"
    applicable_market_types = ["trending"]
    required_timeframe = "1D"
    min_candles_required = 25

    def __init__(self, params: dict | None = None):
        p = params or {}
        self._k = p.get("k", 0.5)
        self._willr_period = p.get("willr_period", 14)
        self._willr_oversold = p.get("willr_oversold", -80.0)
        self._willr_overbought = p.get("willr_overbought", -20.0)
        self._sma_period = p.get("sma_period", 20)

    async def analyze(self, df: pd.DataFrame, symbol: str) -> Signal:
        if len(df) < self.min_candles_required:
            return self._hold("Insufficient data")

        current = df.iloc[-1]
        prev = df.iloc[-2]

        current_close = float(current["close"])
        current_open = float(current["open"])
        prev_high = float(prev["high"])
        prev_low = float(prev["low"])
        prev_range = prev_high - prev_low

        if prev_range <= 0:
            return self._hold("No previous range")

        # Breakout levels
        breakout_up = current_open + self._k * prev_range
        breakout_down = current_open - self._k * prev_range

        # Williams %R
        willr = self._get_williams_r(df)
        if willr is None:
            return self._hold("Williams %R not available")

        prev_willr = self._get_williams_r(df, offset=-2)

        # SMA trend filter
        sma = self._get_sma(df)
        above_sma = current_close > sma if sma is not None else True

        indicators = {
            "breakout_up": round(breakout_up, 2),
            "breakout_down": round(breakout_down, 2),
            "williams_r": round(willr, 2),
            "prev_range": round(prev_range, 2),
            "above_sma": above_sma,
            "price": current_close,
        }

        # BUY: upward breakout + %R oversold exit + above SMA
        willr_oversold_exit = willr > self._willr_oversold
        if prev_willr is not None:
            willr_oversold_exit = prev_willr <= self._willr_oversold and willr > self._willr_oversold

        if current_close > breakout_up and willr_oversold_exit and above_sma:
            breakout_strength = (current_close - breakout_up) / prev_range
            confidence = 0.55 + min(breakout_strength * 0.3, 0.30)
            if willr < -60:
                confidence += 0.05
            return Signal(
                signal_type=SignalType.BUY,
                confidence=round(min(confidence, 0.95), 2),
                strategy_name=self.name,
                reason=f"Volatility breakout: target={breakout_up:.2f}, %R={willr:.0f}",
                suggested_price=current_close,
                indicators=indicators,
            )

        # SELL: downward breakout + %R overbought
        if current_close < breakout_down and willr > self._willr_overbought:
            breakout_strength = (breakout_down - current_close) / prev_range
            confidence = 0.55 + min(breakout_strength * 0.3, 0.30)
            return Signal(
                signal_type=SignalType.SELL,
                confidence=round(min(confidence, 0.95), 2),
                strategy_name=self.name,
                reason=f"Volatility breakdown: target={breakout_down:.2f}, %R={willr:.0f}",
                suggested_price=current_close,
                indicators=indicators,
            )

        return self._hold(f"No breakout: price={current_close:.2f}, %R={willr:.0f}")

    def _get_williams_r(self, df: pd.DataFrame, offset: int = -1) -> float | None:
        # Check for pre-computed column
        for col in [f"willr_{self._willr_period}", f"WILLR_{self._willr_period}", "willr"]:
            if col in df.columns:
                val = df[col].iloc[offset]
                if not pd.isna(val):
                    return float(val)
        # Calculate manually
        if len(df) < self._willr_period:
            return None
        idx = len(df) + offset
        if idx < self._willr_period:
            return None
        window = df.iloc[idx - self._willr_period + 1:idx + 1]
        highest = float(window["high"].max())
        lowest = float(window["low"].min())
        if highest == lowest:
            return None
        close_val = float(df.iloc[offset]["close"])
        return ((highest - close_val) / (highest - lowest)) * -100

    def _get_sma(self, df: pd.DataFrame) -> float | None:
        for col in [f"sma_{self._sma_period}", f"SMA_{self._sma_period}"]:
            if col in df.columns:
                val = df[col].iloc[-1]
                if not pd.isna(val):
                    return float(val)
        if len(df) >= self._sma_period:
            return float(df["close"].iloc[-self._sma_period:].mean())
        return None

    def _hold(self, reason: str) -> Signal:
        return Signal(
            signal_type=SignalType.HOLD,
            confidence=0.0,
            strategy_name=self.name,
            reason=reason,
        )

    def get_params(self) -> dict:
        return {
            "k": self._k,
            "willr_period": self._willr_period,
            "willr_oversold": self._willr_oversold,
            "willr_overbought": self._willr_overbought,
            "sma_period": self._sma_period,
        }

    def set_params(self, params: dict) -> None:
        for key in ["k", "willr_period", "willr_oversold", "willr_overbought", "sma_period"]:
            if key in params:
                setattr(self, f"_{key}", params[key])
