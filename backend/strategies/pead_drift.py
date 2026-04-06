"""Post-Earnings Announcement Drift (PEAD) Strategy.

Detects earnings-like events from large gap + volume spikes, then
captures the well-documented drift in the gap direction. Academic
research shows stocks that beat earnings continue to outperform for
60-90 days after announcement.

Implementation uses price-derived signals (no earnings API dependency):
1. Gap detection: |open - prev_close| / prev_close > threshold
2. Volume confirmation: volume > N * 20-day avg → earnings-like event
3. Drift signal: After a confirmed gap, BUY (positive gap) or SELL (negative gap)
4. Momentum persistence: Gap direction + continued price follow-through
"""

import numpy as np
import pandas as pd

from core.enums import SignalType
from strategies.base import BaseStrategy, Signal


class PEADDriftStrategy(BaseStrategy):
    name = "pead_drift"
    display_name = "PEAD Drift"
    applicable_market_types = ["all"]
    required_timeframe = "1D"
    min_candles_required = 60

    def __init__(self, params: dict | None = None):
        p = params or {}
        self._gap_threshold = p.get("gap_threshold", 0.03)
        self._volume_multiplier = p.get("volume_multiplier", 2.0)
        self._drift_window = p.get("drift_window", 5)
        self._max_entry_delay = p.get("max_entry_delay", 10)
        self._min_follow_through = p.get("min_follow_through", 0.005)
        self._fade_protection = p.get("fade_protection", True)

    async def analyze(self, df: pd.DataFrame, symbol: str) -> Signal:
        if len(df) < self.min_candles_required:
            return self._hold("Insufficient data")

        close = df["close"]
        opens = df["open"]
        volume = df["volume"]
        price = float(close.iloc[-1])

        # Calculate 20-day average volume
        avg_vol_20 = float(volume.iloc[-21:-1].mean()) if len(df) > 21 else float(volume.mean())
        if avg_vol_20 <= 0:
            return self._hold("No volume data")

        # Scan for recent earnings-like gap events (within max_entry_delay days)
        gap_event = self._find_recent_gap(
            df, avg_vol_20, self._max_entry_delay,
        )

        if gap_event is None:
            return self._hold("No recent earnings gap detected")

        gap_idx, gap_pct, gap_vol_ratio = gap_event
        days_since_gap = len(df) - 1 - gap_idx

        # Check follow-through: has price continued in gap direction?
        gap_direction = 1 if gap_pct > 0 else -1
        post_gap_return = self._calc_post_gap_return(df, gap_idx)
        follow_through = post_gap_return * gap_direction > self._min_follow_through

        # Fade protection: if price has reversed significantly, skip
        if self._fade_protection and post_gap_return * gap_direction < -abs(gap_pct) * 0.5:
            return self._hold(
                f"Gap faded: gap={gap_pct:.1%}, post={post_gap_return:.1%}"
            )

        # EMA alignment
        ema_20 = df.iloc[-1].get("ema_20")
        ema_50 = df.iloc[-1].get("ema_50")
        ema_aligned = (
            ema_20 is not None
            and ema_50 is not None
            and not pd.isna(ema_20)
            and not pd.isna(ema_50)
            and float(ema_20) > float(ema_50)
        )

        indicators = {
            "gap_pct": round(gap_pct, 4),
            "gap_vol_ratio": round(gap_vol_ratio, 2),
            "days_since_gap": days_since_gap,
            "post_gap_return": round(post_gap_return, 4),
            "follow_through": follow_through,
            "ema_aligned": ema_aligned,
        }

        # Positive gap → BUY (drift continues upward)
        if gap_pct > 0:
            confidence = 0.50
            if abs(gap_pct) > 0.08:
                confidence += 0.15
            elif abs(gap_pct) > 0.05:
                confidence += 0.10
            if follow_through:
                confidence += 0.10
            if gap_vol_ratio > 3.0:
                confidence += 0.05
            if ema_aligned:
                confidence += 0.05
            # Decay confidence as we get further from the gap
            if days_since_gap > 5:
                confidence -= 0.05 * (days_since_gap - 5) / 5
                confidence = max(confidence, 0.40)

            return Signal(
                signal_type=SignalType.BUY,
                confidence=min(confidence, 0.90),
                strategy_name=self.name,
                reason=(
                    f"PEAD: +{gap_pct:.1%} gap {days_since_gap}d ago, "
                    f"vol={gap_vol_ratio:.1f}x, drift={post_gap_return:.1%}"
                ),
                suggested_price=price,
                indicators=indicators,
            )

        # Negative gap → SELL (drift continues downward)
        if gap_pct < 0:
            confidence = 0.50
            if abs(gap_pct) > 0.08:
                confidence += 0.15
            elif abs(gap_pct) > 0.05:
                confidence += 0.10
            if follow_through:
                confidence += 0.10
            if gap_vol_ratio > 3.0:
                confidence += 0.05
            if not ema_aligned:
                confidence += 0.05
            if days_since_gap > 5:
                confidence -= 0.05 * (days_since_gap - 5) / 5
                confidence = max(confidence, 0.40)

            return Signal(
                signal_type=SignalType.SELL,
                confidence=min(confidence, 0.85),
                strategy_name=self.name,
                reason=(
                    f"PEAD: {gap_pct:.1%} gap {days_since_gap}d ago, "
                    f"vol={gap_vol_ratio:.1f}x, drift={post_gap_return:.1%}"
                ),
                suggested_price=price,
                indicators=indicators,
            )

        return self._hold("Gap neutral")

    def _find_recent_gap(
        self,
        df: pd.DataFrame,
        avg_vol_20: float,
        max_lookback: int,
    ) -> tuple[int, float, float] | None:
        """Find the most recent earnings-like gap within max_lookback days.

        Returns (gap_index, gap_pct, volume_ratio) or None.
        """
        close = df["close"]
        opens = df["open"]
        volume = df["volume"]
        end = len(df) - 1

        for i in range(end, max(end - max_lookback, 0), -1):
            if i < 1:
                break
            prev_close = float(close.iloc[i - 1])
            if prev_close <= 0:
                continue
            gap_pct = (float(opens.iloc[i]) - prev_close) / prev_close
            vol_ratio = float(volume.iloc[i]) / avg_vol_20 if avg_vol_20 > 0 else 0

            if abs(gap_pct) >= self._gap_threshold and vol_ratio >= self._volume_multiplier:
                return (i, gap_pct, vol_ratio)

        return None

    def _calc_post_gap_return(self, df: pd.DataFrame, gap_idx: int) -> float:
        """Return from gap-day close to current price."""
        gap_close = float(df["close"].iloc[gap_idx])
        if gap_close <= 0:
            return 0.0
        current = float(df["close"].iloc[-1])
        return (current - gap_close) / gap_close

    def _hold(self, reason: str) -> Signal:
        return Signal(
            signal_type=SignalType.HOLD,
            confidence=0.0,
            strategy_name=self.name,
            reason=reason,
        )

    def get_params(self) -> dict:
        return {
            "gap_threshold": self._gap_threshold,
            "volume_multiplier": self._volume_multiplier,
            "drift_window": self._drift_window,
            "max_entry_delay": self._max_entry_delay,
            "min_follow_through": self._min_follow_through,
            "fade_protection": self._fade_protection,
        }

    def set_params(self, params: dict) -> None:
        for key in [
            "gap_threshold", "volume_multiplier", "drift_window",
            "max_entry_delay", "min_follow_through", "fade_protection",
        ]:
            if key in params:
                setattr(self, f"_{key}", params[key])
