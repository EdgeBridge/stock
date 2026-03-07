"""Volume Profile Strategy.

Volume surge + OBV trend analysis.
BUY: Volume surge above threshold + OBV uptrend + price above EMA.
SELL: Volume surge on down day + OBV diverging from price.
"""

import pandas as pd

from strategies.base import BaseStrategy, Signal
from core.enums import SignalType


class VolumeProfileStrategy(BaseStrategy):
    name = "volume_profile"
    display_name = "Volume Profile"
    applicable_market_types = ["trending", "sideways"]
    required_timeframe = "1D"
    min_candles_required = 30

    def __init__(self, params: dict | None = None):
        p = params or {}
        self._volume_surge_threshold = p.get("volume_surge_threshold", 2.0)
        self._obv_ma_period = p.get("obv_ma_period", 20)

    async def analyze(self, df: pd.DataFrame, symbol: str) -> Signal:
        if len(df) < self.min_candles_required:
            return self._hold("Insufficient data")

        row = df.iloc[-1]
        price = float(row["close"])
        prev_close = float(df.iloc[-2]["close"])
        is_up_day = price > prev_close

        volume_ratio = row.get("volume_ratio")
        obv = row.get("obv")
        ema_20 = row.get("ema_20")
        rsi = row.get("rsi")

        if volume_ratio is None or pd.isna(volume_ratio):
            return self._hold("Volume ratio not available")

        volume_ratio = float(volume_ratio)
        indicators = {"volume_ratio": volume_ratio, "is_up_day": is_up_day}

        if obv is not None and not pd.isna(obv):
            indicators["obv"] = float(obv)

        # Calculate OBV trend: compare current OBV vs its moving average
        obv_trending_up = False
        obv_trending_down = False
        if "obv" in df.columns and len(df) >= self._obv_ma_period:
            obv_ma = df["obv"].iloc[-self._obv_ma_period:].mean()
            current_obv = float(df.iloc[-1]["obv"]) if not pd.isna(df.iloc[-1]["obv"]) else 0
            obv_trending_up = current_obv > obv_ma
            obv_trending_down = current_obv < obv_ma
            indicators["obv_vs_ma"] = "above" if obv_trending_up else "below"

        volume_surge = volume_ratio >= self._volume_surge_threshold

        # BUY: Volume surge on up day + OBV uptrend + price above EMA
        if volume_surge and is_up_day and obv_trending_up:
            confidence = 0.55
            if volume_ratio > self._volume_surge_threshold * 1.5:
                confidence += 0.10
            if ema_20 is not None and not pd.isna(ema_20) and price > float(ema_20):
                confidence += 0.10
            if rsi is not None and not pd.isna(rsi) and 40 < float(rsi) < 70:
                confidence += 0.05
            return Signal(
                signal_type=SignalType.BUY,
                confidence=min(confidence, 0.95),
                strategy_name=self.name,
                reason=f"Volume surge {volume_ratio:.1f}x on up day, OBV trending up",
                suggested_price=price,
                indicators=indicators,
            )

        # SELL: Volume surge on down day + OBV diverging
        if volume_surge and not is_up_day and obv_trending_down:
            confidence = 0.55
            if volume_ratio > self._volume_surge_threshold * 1.5:
                confidence += 0.10
            return Signal(
                signal_type=SignalType.SELL,
                confidence=min(confidence, 0.95),
                strategy_name=self.name,
                reason=f"Volume surge {volume_ratio:.1f}x on down day, OBV declining",
                suggested_price=price,
                indicators=indicators,
            )

        return self._hold(f"Vol ratio={volume_ratio:.1f}, no signal")

    def _hold(self, reason: str) -> Signal:
        return Signal(
            signal_type=SignalType.HOLD,
            confidence=0.0,
            strategy_name=self.name,
            reason=reason,
        )

    def get_params(self) -> dict:
        return {
            "volume_surge_threshold": self._volume_surge_threshold,
            "obv_ma_period": self._obv_ma_period,
        }

    def set_params(self, params: dict) -> None:
        self._volume_surge_threshold = params.get("volume_surge_threshold", self._volume_surge_threshold)
        self._obv_ma_period = params.get("obv_ma_period", self._obv_ma_period)
