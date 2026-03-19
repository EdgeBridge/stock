"""CIS Momentum Strategy — Pure momentum with volume confirmation.

Adapted from coin project (4h crypto -> 1D stocks).
ROC thresholds adjusted for daily stock movements.

Buy: ROC5 > threshold AND ROC10 > threshold AND volume + trend confirmed
Sell (strong): ROC5 < -3% AND ROC10 < -5% (momentum reversal)
Sell (decay):  ROC5 < -1% AND ROC10 < -2% (gradual decline, lower confidence)
"""

import pandas as pd

from core.enums import SignalType
from strategies.base import BaseStrategy, Signal


class CISMomentumStrategy(BaseStrategy):
    name = "cis_momentum"
    display_name = "CIS Momentum"
    applicable_market_types = ["trending"]
    required_timeframe = "1D"
    min_candles_required = 55  # need 50 bars for SMA trend filter

    def __init__(self, params: dict | None = None):
        p = params or {}
        self._roc_short = p.get("roc_short", 5)
        self._roc_long = p.get("roc_long", 10)
        self._roc_short_buy = p.get("roc_short_buy", 3.0)
        self._roc_long_buy = p.get("roc_long_buy", 5.0)
        self._roc_short_sell = p.get("roc_short_sell", -3.0)
        self._roc_long_sell = p.get("roc_long_sell", -5.0)
        self._volume_ratio_threshold = p.get("volume_ratio_threshold", 1.2)
        # Trend filter: require price > SMA to buy (prevents buying into downtrends)
        self._trend_sma_period = p.get("trend_sma_period", 50)
        # Momentum decay: softer sell thresholds for gradual declines (STOCK-35)
        self._roc_short_sell_weak = p.get("roc_short_sell_weak", -1.0)
        self._roc_long_sell_weak = p.get("roc_long_sell_weak", -2.0)

    async def analyze(self, df: pd.DataFrame, symbol: str) -> Signal:
        if len(df) < self.min_candles_required:
            return self._hold("Insufficient data")

        close = df["close"]
        price = float(close.iloc[-1])

        # Use pre-computed ROC columns if available, otherwise calculate
        roc5 = self._get_roc(df, close, self._roc_short)
        roc10 = self._get_roc(df, close, self._roc_long)

        if roc5 is None or roc10 is None:
            return self._hold("ROC values not available")

        # Volume ratio from pre-computed column or calculate
        volume_ratio = self._get_volume_ratio(df)

        # Trend filter: SMA check to prevent buying into downtrends (STOCK-35)
        above_trend = self._is_above_trend(close)

        indicators = {
            "roc5": round(roc5, 2),
            "roc10": round(roc10, 2),
            "volume_ratio": round(volume_ratio, 2),
            "price": price,
            "above_trend": above_trend,
        }

        # BUY: strong upward momentum + volume confirmation + trend filter
        if (
            roc5 > self._roc_short_buy
            and roc10 > self._roc_long_buy
            and volume_ratio > self._volume_ratio_threshold
            and above_trend
        ):
            momentum_strength = min((roc5 + roc10) / 15.0, 1.0)
            confidence = 0.55 + momentum_strength * 0.25
            if volume_ratio > 2.0:
                confidence += 0.10
            return Signal(
                signal_type=SignalType.BUY,
                confidence=round(min(confidence, 0.95), 2),
                strategy_name=self.name,
                reason=(
                    f"Momentum up: ROC5={roc5:+.1f}%, ROC10={roc10:+.1f}%, Vol={volume_ratio:.1f}x"
                ),
                suggested_price=price,
                indicators=indicators,
            )

        # SELL (strong): sharp momentum reversal — high confidence
        if roc5 < self._roc_short_sell and roc10 < self._roc_long_sell:
            momentum_strength = min((abs(roc5) + abs(roc10)) / 15.0, 1.0)
            confidence = 0.55 + momentum_strength * 0.25
            return Signal(
                signal_type=SignalType.SELL,
                confidence=round(min(confidence, 0.95), 2),
                strategy_name=self.name,
                reason=f"Momentum reversal: ROC5={roc5:+.1f}%, ROC10={roc10:+.1f}%",
                suggested_price=price,
                indicators=indicators,
            )

        # SELL (weak): momentum decay — gradual decline, lower confidence (STOCK-35)
        # Catches slow bleed-outs that never trigger the sharp reversal thresholds.
        if roc5 < self._roc_short_sell_weak and roc10 < self._roc_long_sell_weak:
            momentum_strength = min((abs(roc5) + abs(roc10)) / 20.0, 0.3)
            confidence = 0.40 + momentum_strength
            return Signal(
                signal_type=SignalType.SELL,
                confidence=round(min(confidence, 0.65), 2),
                strategy_name=self.name,
                reason=f"Momentum decay: ROC5={roc5:+.1f}%, ROC10={roc10:+.1f}%",
                suggested_price=price,
                indicators=indicators,
            )

        return Signal(
            signal_type=SignalType.HOLD,
            confidence=0.0,
            strategy_name=self.name,
            reason=f"Momentum unclear: ROC5={roc5:+.1f}%, ROC10={roc10:+.1f}%",
            indicators=indicators,
        )

    def _get_roc(self, df: pd.DataFrame, close: pd.Series, period: int) -> float | None:
        col = f"roc_{period}"
        if col in df.columns:
            val = df[col].iloc[-1]
            if not pd.isna(val):
                return float(val)
        # Calculate manually
        if len(close) > period:
            prev_price = float(close.iloc[-1 - period])
            if prev_price > 0:
                return (float(close.iloc[-1]) - prev_price) / prev_price * 100
        return None

    def _get_volume_ratio(self, df: pd.DataFrame) -> float:
        if "volume_ratio" in df.columns:
            val = df["volume_ratio"].iloc[-1]
            if not pd.isna(val):
                return float(val)
        vol = df["volume"]
        vol_ma = vol.rolling(20).mean().iloc[-1]
        current_vol = float(vol.iloc[-1])
        if vol_ma > 0 and not pd.isna(vol_ma) and not pd.isna(current_vol):
            return current_vol / float(vol_ma)
        return 1.0

    def _is_above_trend(self, close: pd.Series) -> bool:
        """Check if current price is above the trend SMA (STOCK-35).

        Returns True if insufficient data for SMA (fail-open).
        """
        period = self._trend_sma_period
        if len(close) < period:
            return True  # fail-open: not enough data for SMA
        sma = float(close.rolling(period).mean().iloc[-1])
        if pd.isna(sma) or sma <= 0:
            return True
        return float(close.iloc[-1]) > sma

    def _hold(self, reason: str) -> Signal:
        return Signal(
            signal_type=SignalType.HOLD,
            confidence=0.0,
            strategy_name=self.name,
            reason=reason,
        )

    def get_params(self) -> dict:
        return {
            "roc_short": self._roc_short,
            "roc_long": self._roc_long,
            "roc_short_buy": self._roc_short_buy,
            "roc_long_buy": self._roc_long_buy,
            "roc_short_sell": self._roc_short_sell,
            "roc_long_sell": self._roc_long_sell,
            "volume_ratio_threshold": self._volume_ratio_threshold,
            "trend_sma_period": self._trend_sma_period,
            "roc_short_sell_weak": self._roc_short_sell_weak,
            "roc_long_sell_weak": self._roc_long_sell_weak,
        }

    def set_params(self, params: dict) -> None:
        for key in [
            "roc_short",
            "roc_long",
            "roc_short_buy",
            "roc_long_buy",
            "roc_short_sell",
            "roc_long_sell",
            "volume_ratio_threshold",
            "trend_sma_period",
            "roc_short_sell_weak",
            "roc_long_sell_weak",
        ]:
            if key in params:
                setattr(self, f"_{key}", params[key])
