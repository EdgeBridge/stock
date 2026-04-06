"""Cross-Sectional Momentum Strategy (Jegadeesh-Titman 12-1).

Ranks stocks by 12-month return excluding the most recent month
(to avoid short-term reversal). BUY top-ranked momentum stocks,
SELL losers with negative momentum and declining trend.

Key signals:
- 12-1 month return (skip last 21 trading days to avoid reversal)
- 6-month return for intermediate confirmation
- 1-month return as reversal filter (avoid recent losers)
- Volume trend confirmation
- EMA alignment (20 > 50) for trend support
"""

import pandas as pd

from core.enums import SignalType
from strategies.base import BaseStrategy, Signal


class CrossSectionalMomentumStrategy(BaseStrategy):
    name = "cross_sectional_momentum"
    display_name = "Cross-Sectional Momentum"
    applicable_market_types = ["trending"]
    required_timeframe = "1D"
    min_candles_required = 252  # ~12 months of daily data

    def __init__(self, params: dict | None = None):
        p = params or {}
        self._lookback_days = p.get("lookback_days", 252)
        self._skip_days = p.get("skip_days", 21)
        self._min_momentum = p.get("min_momentum", 0.05)
        self._sell_momentum_threshold = p.get("sell_momentum_threshold", -0.05)
        self._volume_confirm = p.get("volume_confirm", True)
        self._volume_ratio_threshold = p.get("volume_ratio_threshold", 0.8)
        self._reversal_filter = p.get("reversal_filter", True)
        self._reversal_threshold = p.get("reversal_threshold", -0.05)

    async def analyze(self, df: pd.DataFrame, symbol: str) -> Signal:
        if len(df) < self.min_candles_required:
            return self._hold("Insufficient data")

        close = df["close"]
        price = float(close.iloc[-1])

        # 12-1 momentum: return from T-252 to T-21 (skip last month)
        skip_idx = len(df) - 1 - self._skip_days
        lookback_idx = len(df) - 1 - self._lookback_days
        if lookback_idx < 0 or skip_idx <= lookback_idx:
            return self._hold("Insufficient lookback")

        price_skip = float(close.iloc[skip_idx])
        price_lookback = float(close.iloc[lookback_idx])
        if price_lookback <= 0 or price_skip <= 0:
            return self._hold("Invalid prices")

        momentum_12_1 = (price_skip - price_lookback) / price_lookback

        # 6-month return (intermediate)
        idx_6m = max(0, len(df) - 1 - 126)
        price_6m = float(close.iloc[idx_6m])
        ret_6m = (price - price_6m) / price_6m if price_6m > 0 else 0.0

        # 1-month return (reversal filter)
        idx_1m = max(0, len(df) - 1 - 21)
        price_1m = float(close.iloc[idx_1m])
        ret_1m = (price - price_1m) / price_1m if price_1m > 0 else 0.0

        # Volume trend: 20-day avg vs 50-day avg
        volume_ratio = self._calc_volume_ratio(df)

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
            "momentum_12_1": round(momentum_12_1, 4),
            "ret_6m": round(ret_6m, 4),
            "ret_1m": round(ret_1m, 4),
            "volume_ratio": round(volume_ratio, 2),
            "ema_aligned": ema_aligned,
        }

        # SELL: strong negative momentum + declining trend
        if momentum_12_1 < self._sell_momentum_threshold and not ema_aligned:
            confidence = 0.45
            if momentum_12_1 < -0.15:
                confidence += 0.15
            if ret_6m < -0.10:
                confidence += 0.10
            return Signal(
                signal_type=SignalType.SELL,
                confidence=min(confidence, 0.85),
                strategy_name=self.name,
                reason=(
                    f"Negative cross-sectional momentum "
                    f"12-1={momentum_12_1:.1%}, 6m={ret_6m:.1%}"
                ),
                suggested_price=price,
                indicators=indicators,
            )

        # BUY: strong positive 12-1 momentum
        if momentum_12_1 >= self._min_momentum:
            # Reversal filter: skip if last month was a sharp drop
            if (
                self._reversal_filter
                and ret_1m < self._reversal_threshold
            ):
                return self._hold(
                    f"Reversal filter: 1m return {ret_1m:.1%}"
                )

            # Volume confirmation
            if (
                self._volume_confirm
                and volume_ratio < self._volume_ratio_threshold
            ):
                return self._hold(
                    f"Weak volume ({volume_ratio:.2f}x)"
                )

            confidence = 0.50
            if momentum_12_1 > 0.20:
                confidence += 0.15
            elif momentum_12_1 > 0.10:
                confidence += 0.10
            if ret_6m > 0.10:
                confidence += 0.10
            if ema_aligned:
                confidence += 0.10
            if volume_ratio > 1.2:
                confidence += 0.05

            return Signal(
                signal_type=SignalType.BUY,
                confidence=min(confidence, 0.95),
                strategy_name=self.name,
                reason=(
                    f"Strong 12-1 momentum {momentum_12_1:.1%}, "
                    f"6m={ret_6m:.1%}"
                ),
                suggested_price=price,
                indicators=indicators,
            )

        return self._hold(
            f"Momentum neutral ({momentum_12_1:.1%})"
        )

    def _calc_volume_ratio(self, df: pd.DataFrame) -> float:
        """20-day avg volume / 50-day avg volume."""
        if len(df) < 50:
            return 1.0
        vol = df["volume"]
        avg_20 = float(vol.iloc[-20:].mean())
        avg_50 = float(vol.iloc[-50:].mean())
        if avg_50 <= 0:
            return 1.0
        return avg_20 / avg_50

    def _hold(self, reason: str) -> Signal:
        return Signal(
            signal_type=SignalType.HOLD,
            confidence=0.0,
            strategy_name=self.name,
            reason=reason,
        )

    def get_params(self) -> dict:
        return {
            "lookback_days": self._lookback_days,
            "skip_days": self._skip_days,
            "min_momentum": self._min_momentum,
            "sell_momentum_threshold": self._sell_momentum_threshold,
            "volume_confirm": self._volume_confirm,
            "volume_ratio_threshold": self._volume_ratio_threshold,
            "reversal_filter": self._reversal_filter,
            "reversal_threshold": self._reversal_threshold,
        }

    def set_params(self, params: dict) -> None:
        for key in [
            "lookback_days", "skip_days", "min_momentum",
            "sell_momentum_threshold", "volume_confirm",
            "volume_ratio_threshold", "reversal_filter",
            "reversal_threshold",
        ]:
            if key in params:
                setattr(self, f"_{key}", params[key])
