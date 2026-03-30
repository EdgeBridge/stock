"""Volume Profile Strategy.

Volume surge + OBV trend analysis with OBV acceleration
and volume intensity scaling.
BUY: Volume surge above threshold + OBV uptrend + price above EMA.
SELL: Volume surge on down day + OBV diverging from price.
OBV acceleration (2nd derivative) provides earlier signal detection.
Volume intensity scales confidence proportionally.
"""

import numpy as np
import pandas as pd

from core.enums import SignalType
from strategies.base import BaseStrategy, Signal


class VolumeProfileStrategy(BaseStrategy):
    name = "volume_profile"
    display_name = "Volume Profile"
    applicable_market_types = ["trending", "sideways"]
    required_timeframe = "1D"
    min_candles_required = 30

    def __init__(self, params: dict | None = None):
        p = params or {}
        self._volume_surge_threshold = p.get(
            "volume_surge_threshold", 2.0
        )
        self._obv_ma_period = p.get("obv_ma_period", 20)
        self._obv_accel_period = p.get("obv_accel_period", 5)
        self._volume_intensity_cap = p.get(
            "volume_intensity_cap", 1.3
        )

    async def analyze(
        self, df: pd.DataFrame, symbol: str
    ) -> Signal:
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
        indicators: dict = {
            "volume_ratio": volume_ratio,
            "is_up_day": is_up_day,
        }

        if obv is not None and not pd.isna(obv):
            indicators["obv"] = float(obv)

        # Calculate OBV trend: compare current OBV vs MA
        obv_trending_up = False
        obv_trending_down = False
        if (
            "obv" in df.columns
            and len(df) >= self._obv_ma_period
        ):
            obv_series = df["obv"].iloc[
                -self._obv_ma_period :
            ]
            obv_ma = obv_series.mean()
            last_obv = df.iloc[-1]["obv"]
            current_obv = (
                float(last_obv)
                if not pd.isna(last_obv)
                else 0
            )
            obv_trending_up = current_obv > obv_ma
            obv_trending_down = current_obv < obv_ma
            indicators["obv_vs_ma"] = (
                "above" if obv_trending_up else "below"
            )

        # --- OBV acceleration (2nd derivative) ---
        obv_accel = self._calc_obv_acceleration(
            df, indicators
        )

        # --- Volume intensity ---
        vol_intensity = self._calc_volume_intensity(
            df, indicators
        )

        volume_surge = (
            volume_ratio >= self._volume_surge_threshold
        )

        # BUY signal
        if volume_surge and is_up_day and obv_trending_up:
            confidence = 0.55
            if (
                volume_ratio
                > self._volume_surge_threshold * 1.5
            ):
                confidence += 0.10
            if (
                ema_20 is not None
                and not pd.isna(ema_20)
                and price > float(ema_20)
            ):
                confidence += 0.10
            if (
                rsi is not None
                and not pd.isna(rsi)
                and 40 < float(rsi) < 70
            ):
                confidence += 0.05
            # OBV acceleration bonus for BUY
            if obv_accel is not None and obv_accel > 0:
                confidence += 0.05
            # Volume intensity scaling
            confidence = self._apply_volume_intensity(
                confidence, vol_intensity
            )
            return Signal(
                signal_type=SignalType.BUY,
                confidence=min(confidence, 0.95),
                strategy_name=self.name,
                reason=(
                    f"Volume surge {volume_ratio:.1f}x"
                    f" on up day, OBV trending up"
                ),
                suggested_price=price,
                indicators=indicators,
            )

        # SELL signal
        if (
            volume_surge
            and not is_up_day
            and obv_trending_down
        ):
            confidence = 0.55
            if (
                volume_ratio
                > self._volume_surge_threshold * 1.5
            ):
                confidence += 0.10
            # OBV deceleration bonus for SELL
            if obv_accel is not None and obv_accel < 0:
                confidence += 0.05
            # Volume intensity scaling
            confidence = self._apply_volume_intensity(
                confidence, vol_intensity
            )
            return Signal(
                signal_type=SignalType.SELL,
                confidence=min(confidence, 0.95),
                strategy_name=self.name,
                reason=(
                    f"Volume surge {volume_ratio:.1f}x"
                    f" on down day, OBV declining"
                ),
                suggested_price=price,
                indicators=indicators,
            )

        return self._hold(
            f"Vol ratio={volume_ratio:.1f}, no signal"
        )

    def _calc_obv_acceleration(
        self,
        df: pd.DataFrame,
        indicators: dict,
    ) -> float | None:
        """Compute OBV 2nd derivative (acceleration).

        1st derivative = diff of OBV (momentum).
        2nd derivative = diff of 1st derivative
        (acceleration/deceleration).
        Positive = OBV momentum accelerating (bullish).
        Negative = OBV momentum decelerating (bearish).
        """
        period = self._obv_accel_period
        min_needed = period + 2  # need 2 extra for diffs
        if "obv" not in df.columns:
            return None
        if len(df) < min_needed:
            return None

        obv_slice = df["obv"].iloc[-(period + 2) :]
        if obv_slice.isna().any():
            return None

        obv_vals = obv_slice.values.astype(float)
        # 1st derivative (momentum)
        obv_mom = np.diff(obv_vals)
        # 2nd derivative (acceleration)
        obv_acc = np.diff(obv_mom)
        # Average acceleration over the period
        avg_accel = float(np.mean(obv_acc[-period:]))

        indicators["obv_acceleration"] = round(
            avg_accel, 4
        )
        return avg_accel

    def _calc_volume_intensity(
        self,
        df: pd.DataFrame,
        indicators: dict,
    ) -> float | None:
        """Compute volume intensity ratio.

        volume_intensity = current_volume / avg_volume.
        Higher values indicate stronger conviction behind
        the price move.
        """
        if "volume" not in df.columns:
            return None
        period = self._obv_ma_period
        if len(df) < period:
            return None

        vol_slice = df["volume"].iloc[-period:]
        if vol_slice.isna().any():
            return None

        avg_vol = vol_slice.mean()
        if avg_vol <= 0:
            return None

        current_vol = float(df.iloc[-1]["volume"])
        intensity = current_vol / float(avg_vol)

        indicators["volume_intensity"] = round(
            intensity, 4
        )
        return intensity

    def _apply_volume_intensity(
        self,
        confidence: float,
        vol_intensity: float | None,
    ) -> float:
        """Scale confidence by volume intensity.

        intensity > 1 boosts confidence (capped).
        intensity < 1 dampens confidence.
        """
        if vol_intensity is None:
            return confidence
        scale = min(vol_intensity, self._volume_intensity_cap)
        # Normalize: intensity=1 -> no change,
        # >1 -> boost, <1 -> dampen
        # Use sqrt to prevent over-amplification
        adjustment = scale ** 0.5
        return confidence * adjustment

    def _hold(self, reason: str) -> Signal:
        return Signal(
            signal_type=SignalType.HOLD,
            confidence=0.0,
            strategy_name=self.name,
            reason=reason,
        )

    def get_params(self) -> dict:
        return {
            "volume_surge_threshold": (
                self._volume_surge_threshold
            ),
            "obv_ma_period": self._obv_ma_period,
            "obv_accel_period": self._obv_accel_period,
            "volume_intensity_cap": (
                self._volume_intensity_cap
            ),
        }

    def set_params(self, params: dict) -> None:
        self._volume_surge_threshold = params.get(
            "volume_surge_threshold",
            self._volume_surge_threshold,
        )
        self._obv_ma_period = params.get(
            "obv_ma_period", self._obv_ma_period
        )
        self._obv_accel_period = params.get(
            "obv_accel_period", self._obv_accel_period
        )
        self._volume_intensity_cap = params.get(
            "volume_intensity_cap",
            self._volume_intensity_cap,
        )
