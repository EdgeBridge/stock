"""Trend Following Strategy.

Core trend-following strategy using EMA alignment + ADX + volume confirmation.

Buy: Price > EMA_fast > EMA_slow > EMA_long, ADX > threshold, volume above average
Sell: Price < EMA_fast or ADX declining below threshold
"""

import pandas as pd

from strategies.base import BaseStrategy, Signal
from core.enums import SignalType


class TrendFollowingStrategy(BaseStrategy):
    name = "trend_following"
    display_name = "Trend Following"
    applicable_market_types = ["trending"]
    required_timeframe = "1D"
    min_candles_required = 50

    def __init__(self, params: dict | None = None):
        p = params or {}
        self._ema_fast = p.get("ema_fast", 20)
        self._ema_slow = p.get("ema_slow", 50)
        self._ema_long = p.get("ema_long", 200)
        self._adx_threshold = p.get("adx_threshold", 25)
        self._volume_min_ratio = p.get("volume_min_ratio", 1.0)

    async def analyze(self, df: pd.DataFrame, symbol: str) -> Signal:
        if len(df) < self.min_candles_required:
            return self._hold("Insufficient data")

        row = df.iloc[-1]
        price = float(row["close"])

        ema_fast = row.get(f"ema_{self._ema_fast}")
        ema_slow = row.get(f"ema_{self._ema_slow}")
        adx = row.get("adx")
        volume_ratio = row.get("volume_ratio")
        rsi = row.get("rsi")

        if any(v is None or pd.isna(v) for v in [ema_fast, ema_slow, adx]):
            return self._hold("Indicators not ready")

        indicators = {
            "ema_fast": float(ema_fast),
            "ema_slow": float(ema_slow),
            "adx": float(adx),
            "volume_ratio": float(volume_ratio) if volume_ratio and not pd.isna(volume_ratio) else 0,
            "rsi": float(rsi) if rsi and not pd.isna(rsi) else 50,
        }

        # Check for EMA long if available
        ema_long = row.get(f"ema_{self._ema_long}")
        has_long = ema_long is not None and not pd.isna(ema_long)
        if has_long:
            indicators["ema_long"] = float(ema_long)

        # BUY conditions
        ema_aligned = price > ema_fast > ema_slow
        if has_long:
            ema_aligned = ema_aligned and ema_slow > ema_long

        strong_trend = adx > self._adx_threshold
        volume_ok = (volume_ratio or 0) >= self._volume_min_ratio

        if ema_aligned and strong_trend and volume_ok:
            confidence = self._calc_buy_confidence(adx, volume_ratio, rsi)
            return Signal(
                signal_type=SignalType.BUY,
                confidence=confidence,
                strategy_name=self.name,
                reason=f"EMA aligned, ADX={adx:.0f}, VolRatio={volume_ratio:.1f}",
                suggested_price=price,
                indicators=indicators,
            )

        # SELL conditions
        ema_broken = price < ema_fast
        trend_weakening = adx < self._adx_threshold * 0.7

        if ema_broken or trend_weakening:
            confidence = 0.7 if ema_broken and trend_weakening else 0.5
            return Signal(
                signal_type=SignalType.SELL,
                confidence=confidence,
                strategy_name=self.name,
                reason=f"EMA broken={ema_broken}, ADX weakening={trend_weakening}",
                suggested_price=price,
                indicators=indicators,
            )

        return self._hold("No clear signal")

    def _calc_buy_confidence(self, adx, volume_ratio, rsi) -> float:
        conf = 0.5
        if adx > 35:
            conf += 0.15
        elif adx > 30:
            conf += 0.10
        if volume_ratio and volume_ratio > 1.5:
            conf += 0.10
        if rsi and 40 < rsi < 70:
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
        return {
            "ema_fast": self._ema_fast,
            "ema_slow": self._ema_slow,
            "ema_long": self._ema_long,
            "adx_threshold": self._adx_threshold,
            "volume_min_ratio": self._volume_min_ratio,
        }

    def set_params(self, params: dict) -> None:
        self._ema_fast = params.get("ema_fast", self._ema_fast)
        self._ema_slow = params.get("ema_slow", self._ema_slow)
        self._ema_long = params.get("ema_long", self._ema_long)
        self._adx_threshold = params.get("adx_threshold", self._adx_threshold)
        self._volume_min_ratio = params.get("volume_min_ratio", self._volume_min_ratio)
