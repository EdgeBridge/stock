"""Market State Detector — SPY/VIX based regime detection.

Determines current market regime for adaptive strategy weighting:
  - strong_uptrend: SPY > SMA200, VIX < 18, breadth positive
  - uptrend: SPY > SMA200, VIX < 25
  - sideways: SPY near SMA200, moderate VIX
  - downtrend: SPY < SMA200, VIX > 25
"""

import logging
from dataclasses import dataclass
from enum import Enum

import pandas as pd

logger = logging.getLogger(__name__)


class MarketRegime(str, Enum):
    STRONG_UPTREND = "strong_uptrend"
    UPTREND = "uptrend"
    SIDEWAYS = "sideways"
    WEAK_DOWNTREND = "weak_downtrend"
    DOWNTREND = "downtrend"


@dataclass
class MarketState:
    regime: MarketRegime
    spy_price: float = 0.0
    spy_sma200: float = 0.0
    spy_above_sma200: bool = True
    spy_distance_pct: float = 0.0
    vix_level: float = 0.0
    spy_roc_20d: float = 0.0
    confidence: float = 0.5


class MarketStateDetector:
    """Detects market regime using SPY and VIX data."""

    def __init__(
        self,
        sma_period: int = 200,
        vix_bull_threshold: float = 18.0,
        vix_caution_threshold: float = 25.0,
        vix_bear_threshold: float = 30.0,
        confirmation_days: int = 2,
    ):
        self._sma_period = sma_period
        self._vix_bull = vix_bull_threshold
        self._vix_caution = vix_caution_threshold
        self._vix_bear = vix_bear_threshold
        self._confirmation_days = confirmation_days
        self._last_state: MarketState | None = None
        self._regime_streak = 0
        self._pending_regime: MarketRegime | None = None

    def detect(
        self,
        spy_df: pd.DataFrame,
        vix_level: float | None = None,
    ) -> MarketState:
        """Detect market regime from SPY OHLCV and VIX level.

        Args:
            spy_df: SPY DataFrame with at least 200 rows and 'close' column.
            vix_level: Current VIX index level. If None, uses moderate default.
        """
        if spy_df.empty or len(spy_df) < 50:
            return MarketState(regime=MarketRegime.SIDEWAYS)

        close = spy_df["close"]
        spy_price = float(close.iloc[-1])

        # SMA 200 (or use available data if < 200 bars)
        sma_len = min(self._sma_period, len(close))
        spy_sma200 = float(close.iloc[-sma_len:].mean())

        # Distance from SMA
        distance_pct = ((spy_price - spy_sma200) / spy_sma200 * 100) if spy_sma200 > 0 else 0.0
        above_sma = spy_price > spy_sma200

        # 20-day rate of change
        roc_20d = 0.0
        if len(close) >= 21:
            prev_20 = float(close.iloc[-21])
            if prev_20 > 0:
                roc_20d = (spy_price - prev_20) / prev_20 * 100

        vix = vix_level if vix_level is not None else 20.0

        # Determine regime
        regime = self._classify(above_sma, distance_pct, vix, roc_20d)

        # Asymmetric confirmation: fast risk-off (1 day), slow risk-on (2 days)
        if self._last_state and regime != self._last_state.regime:
            if self._pending_regime != regime:
                self._pending_regime = regime
                self._regime_streak = 1
            else:
                self._regime_streak += 1

            is_risk_off = regime in (MarketRegime.WEAK_DOWNTREND, MarketRegime.DOWNTREND)
            required = 1 if is_risk_off else self._confirmation_days

            if self._regime_streak < required:
                regime = self._last_state.regime
            else:
                self._regime_streak = 0
                self._pending_regime = None
        else:
            self._regime_streak = 0
            self._pending_regime = None

        state = MarketState(
            regime=regime,
            spy_price=round(spy_price, 2),
            spy_sma200=round(spy_sma200, 2),
            spy_above_sma200=above_sma,
            spy_distance_pct=round(distance_pct, 2),
            vix_level=round(vix, 2),
            spy_roc_20d=round(roc_20d, 2),
            confidence=self._calc_confidence(above_sma, distance_pct, vix),
        )
        self._last_state = state
        return state

    def _classify(
        self, above_sma: bool, distance_pct: float, vix: float, roc_20d: float,
    ) -> MarketRegime:
        if above_sma and distance_pct > 3.0 and vix < self._vix_bull and roc_20d > 0:
            return MarketRegime.STRONG_UPTREND
        if above_sma and vix < self._vix_caution:
            return MarketRegime.UPTREND
        if not above_sma and (vix > self._vix_bear or distance_pct < -5.0):
            return MarketRegime.DOWNTREND
        # WEAK_DOWNTREND: below SMA and either elevated VIX or negative distance
        if not above_sma and (vix > self._vix_caution or distance_pct < -2.0):
            return MarketRegime.WEAK_DOWNTREND
        return MarketRegime.SIDEWAYS

    def _calc_confidence(
        self, above_sma: bool, distance_pct: float, vix: float,
    ) -> float:
        """Higher confidence when signals align clearly."""
        conf = 0.5
        abs_dist = abs(distance_pct)
        if abs_dist > 5:
            conf += 0.2
        elif abs_dist > 2:
            conf += 0.1

        if vix < 15 or vix > 35:
            conf += 0.15
        elif vix < 20 or vix > 28:
            conf += 0.05

        return min(round(conf, 2), 0.95)

    @property
    def last_state(self) -> MarketState | None:
        return self._last_state
