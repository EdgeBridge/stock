"""Donchian Channel Breakout Strategy.

Enhanced turtle-style breakout strategy with ADX filter,
volume confirmation, and channel width confidence scaling.

Buy: Price breaks above N-period high (Donchian upper)
Sell: Price breaks below exit-period low (turtle exit) or Donchian lower
"""

import pandas as pd

from strategies.base import BaseStrategy, Signal
from core.enums import SignalType


class DonchianBreakoutStrategy(BaseStrategy):
    name = "donchian_breakout"
    display_name = "Donchian Breakout"
    applicable_market_types = ["trending"]
    required_timeframe = "1D"
    min_candles_required = 30

    def __init__(self, params: dict | None = None):
        p = params or {}
        self._entry_period = p.get("entry_period", 20)
        self._exit_period = p.get("exit_period", 10)
        self._adx_threshold = p.get("adx_threshold", 25.0)
        self._volume_multiplier = p.get("volume_multiplier", 1.5)

    async def analyze(self, df: pd.DataFrame, symbol: str) -> Signal:
        if len(df) < self.min_candles_required:
            return self._hold("Insufficient data")

        row = df.iloc[-1]
        prev = df.iloc[-2]
        price = float(row["close"])

        donchian_upper = row.get("donchian_upper")
        donchian_lower = row.get("donchian_lower")
        atr = row.get("atr")
        adx = row.get("adx")
        volume_ratio = row.get("volume_ratio")

        if any(v is None or pd.isna(v) for v in [donchian_upper, donchian_lower]):
            return self._hold("Indicators not ready")

        donchian_upper = float(donchian_upper)
        donchian_lower = float(donchian_lower)

        # Channel width as percentage
        channel_width = 0.0
        if donchian_lower > 0:
            channel_width = (donchian_upper - donchian_lower) / donchian_lower * 100

        # Exit period low (turtle exit) — use prior bars (exclude current bar)
        if len(df) > self._exit_period + 1:
            exit_low = float(df["low"].iloc[-(self._exit_period + 1):-1].min())
        else:
            exit_low = float(df["low"].iloc[:-1].min())

        indicators = {
            "donchian_upper": donchian_upper,
            "donchian_lower": donchian_lower,
            "channel_width_pct": round(channel_width, 2),
            "atr": float(atr) if atr and not pd.isna(atr) else 0,
            "adx": float(adx) if adx and not pd.isna(adx) else 0,
            "volume_ratio": float(volume_ratio) if volume_ratio and not pd.isna(volume_ratio) else 0,
        }

        # BUY: breakout above prior Donchian upper
        # Use previous bar's upper channel (current bar is included in donchian calc)
        prev_upper = prev.get("donchian_upper")
        if prev_upper is not None and not pd.isna(prev_upper):
            prev_upper = float(prev_upper)
        else:
            prev_upper = donchian_upper
        prev_close = float(prev["close"])
        if price > prev_upper and prev_close <= prev_upper:
            confidence = self._calc_buy_confidence(
                adx, volume_ratio, atr, price, prev_upper, channel_width,
            )
            return Signal(
                signal_type=SignalType.BUY,
                confidence=confidence,
                strategy_name=self.name,
                reason=f"Donchian breakout: price {price:.2f} > upper {prev_upper:.2f} (width={channel_width:.1f}%)",
                suggested_price=price,
                indicators=indicators,
            )

        # SELL: break below prior Donchian lower (full reversal)
        prev_lower = prev.get("donchian_lower")
        if prev_lower is not None and not pd.isna(prev_lower):
            prev_lower = float(prev_lower)
        else:
            prev_lower = donchian_lower
        if price < prev_lower:
            width_bonus = min(channel_width / 20.0, 0.15)
            confidence = min(0.60 + width_bonus, 0.95)
            return Signal(
                signal_type=SignalType.SELL,
                confidence=confidence,
                strategy_name=self.name,
                reason=f"Donchian lower break: price {price:.2f} < lower {prev_lower:.2f}",
                suggested_price=price,
                indicators=indicators,
            )

        # SELL: turtle exit — break below exit-period low
        if price < exit_low:
            return Signal(
                signal_type=SignalType.SELL,
                confidence=0.55,
                strategy_name=self.name,
                reason=f"Turtle exit: price {price:.2f} < {self._exit_period}-day low {exit_low:.2f}",
                suggested_price=price,
                indicators=indicators,
            )

        return self._hold("No breakout")

    def _calc_buy_confidence(
        self, adx, volume_ratio, atr, price, upper, channel_width,
    ) -> float:
        # Base confidence from channel width (wider channel = stronger breakout)
        width_bonus = min(channel_width / 20.0, 0.15)
        conf = 0.55 + width_bonus

        # ADX bonus: strong trend confirmation
        if adx and not pd.isna(adx) and float(adx) > self._adx_threshold:
            conf += 0.10

        # Volume bonus: breakout with volume confirmation
        if volume_ratio and not pd.isna(volume_ratio) and float(volume_ratio) > self._volume_multiplier:
            conf += 0.10

        # Breakout strength: how far above channel
        if atr and not pd.isna(atr) and float(atr) > 0:
            breakout_atr = (price - upper) / float(atr)
            if breakout_atr > 0.5:
                conf += 0.05

        return min(round(conf, 2), 0.95)

    def _hold(self, reason: str) -> Signal:
        return Signal(
            signal_type=SignalType.HOLD,
            confidence=0.0,
            strategy_name=self.name,
            reason=reason,
        )

    def get_params(self) -> dict:
        return {
            "entry_period": self._entry_period,
            "exit_period": self._exit_period,
            "adx_threshold": self._adx_threshold,
            "volume_multiplier": self._volume_multiplier,
        }

    def set_params(self, params: dict) -> None:
        self._entry_period = params.get("entry_period", self._entry_period)
        self._exit_period = params.get("exit_period", self._exit_period)
        self._adx_threshold = params.get("adx_threshold", self._adx_threshold)
        self._volume_multiplier = params.get("volume_multiplier", self._volume_multiplier)
