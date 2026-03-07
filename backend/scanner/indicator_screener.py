"""Layer 1: Indicator Screener.

Pure technical indicator-based stock screening using KIS data only.
Scores stocks on trend, momentum, volatility/volume, and support/resistance.
"""

import logging
from dataclasses import dataclass, field

import pandas as pd

from data.indicator_service import IndicatorService

logger = logging.getLogger(__name__)


@dataclass
class ScreenerScore:
    symbol: str
    total_score: float  # 0-100
    trend_score: float
    momentum_score: float
    volatility_volume_score: float
    support_resistance_score: float
    grade: str  # A, B, C, D, F
    details: dict
    signals: list[str] = field(default_factory=list)


class IndicatorScreener:
    """Score stocks based on technical indicators only."""

    def __init__(
        self,
        weights: dict[str, float] | None = None,
        min_grade: str = "B",
    ):
        self._weights = weights or {
            "trend": 0.40,
            "momentum": 0.25,
            "volatility_volume": 0.20,
            "support_resistance": 0.15,
        }
        self._min_grade = min_grade

    def score(self, df: pd.DataFrame, symbol: str) -> ScreenerScore:
        """Score a stock based on its OHLCV + indicators DataFrame."""
        if df.empty or len(df) < 20:
            return ScreenerScore(
                symbol=symbol, total_score=0, trend_score=0,
                momentum_score=0, volatility_volume_score=0,
                support_resistance_score=0, grade="F", details={},
                signals=[],
            )

        row = df.iloc[-1]
        signals: list[str] = []

        trend = self._score_trend(df, row, signals)
        momentum = self._score_momentum(df, row, signals)
        vol = self._score_volatility_volume(df, row, signals)
        sr = self._score_support_resistance(df, row, signals)

        total = (
            trend * self._weights["trend"]
            + momentum * self._weights["momentum"]
            + vol * self._weights["volatility_volume"]
            + sr * self._weights["support_resistance"]
        )

        grade = self._to_grade(total)

        return ScreenerScore(
            symbol=symbol,
            total_score=round(total, 1),
            trend_score=round(trend, 1),
            momentum_score=round(momentum, 1),
            volatility_volume_score=round(vol, 1),
            support_resistance_score=round(sr, 1),
            grade=grade,
            details={
                "ema_alignment": IndicatorService.detect_ema_alignment(df),
                "squeeze": bool(IndicatorService.detect_squeeze(df)),
            },
            signals=signals,
        )

    def filter_candidates(
        self, scores: list[ScreenerScore], max_candidates: int = 50
    ) -> list[ScreenerScore]:
        """Filter and rank candidates by score."""
        grade_order = {"A": 0, "B": 1, "C": 2, "D": 3, "F": 4}
        min_rank = grade_order.get(self._min_grade, 1)
        filtered = [s for s in scores if grade_order.get(s.grade, 4) <= min_rank]
        filtered.sort(key=lambda s: s.total_score, reverse=True)
        return filtered[:max_candidates]

    # ------------------------------------------------------------------
    # Trend scoring
    # ------------------------------------------------------------------

    def _score_trend(
        self, df: pd.DataFrame, row: pd.Series, signals: list[str],
    ) -> float:
        ema_score = self._score_ema_alignment(df, row)
        adx_score = self._score_adx_strength(row)
        price_ma_score = self._score_price_vs_ma(row)

        # Golden / Dead cross detection (bonus applied to ema_score)
        cross_bonus = self._detect_golden_dead_cross(df, signals)
        ema_score = _clamp(ema_score + cross_bonus)

        trend = ema_score * 0.40 + adx_score * 0.30 + price_ma_score * 0.30
        return _clamp(trend)

    @staticmethod
    def _score_ema_alignment(df: pd.DataFrame, row: pd.Series) -> float:
        alignment = IndicatorService.detect_ema_alignment(df)
        alignment_map = {
            "PERFECT_BULL": 100,
            "PARTIAL_BULL": 70,
            "PARTIAL_BEAR": 30,
            "PERFECT_BEAR": 0,
        }
        if alignment in alignment_map:
            return float(alignment_map[alignment])

        # MIXED: check for partial conditions
        price = row.get("close")
        ema20 = row.get("ema_20")
        ema50 = row.get("ema_50")
        if (
            price is not None
            and ema20 is not None
            and ema50 is not None
            and not pd.isna(price)
            and not pd.isna(ema20)
            and not pd.isna(ema50)
            and price > ema20
            and ema20 > ema50
        ):
            return 50.0
        return 30.0

    @staticmethod
    def _detect_golden_dead_cross(
        df: pd.DataFrame, signals: list[str],
    ) -> float:
        """Detect SMA50/SMA200 golden or dead cross within last 10 rows."""
        if len(df) < 2:
            return 0.0

        sma50_col = "sma_50"
        sma200_col = "sma_200"

        if sma50_col not in df.columns or sma200_col not in df.columns:
            return 0.0

        lookback = min(10, len(df) - 1)
        tail = df.iloc[-(lookback + 1):]

        sma50 = tail[sma50_col]
        sma200 = tail[sma200_col]

        if sma50.isna().all() or sma200.isna().all():
            return 0.0

        diff = sma50 - sma200
        bonus = 0.0

        for i in range(1, len(diff)):
            prev_val = diff.iloc[i - 1]
            curr_val = diff.iloc[i]
            if pd.isna(prev_val) or pd.isna(curr_val):
                continue
            if prev_val <= 0 < curr_val:
                days_ago = len(diff) - 1 - i
                signals.append(f"Golden Cross ({days_ago}d ago)")
                bonus = 15.0
            elif prev_val >= 0 > curr_val:
                days_ago = len(diff) - 1 - i
                signals.append(f"Dead Cross ({days_ago}d ago)")
                bonus = -15.0

        return bonus

    @staticmethod
    def _score_adx_strength(row: pd.Series) -> float:
        adx = row.get("adx")
        if adx is None or pd.isna(adx):
            return 30.0  # neutral when unavailable

        if adx > 50:
            base = 100.0
        elif adx >= 40:
            base = 90.0
        elif adx >= 30:
            base = 75.0
        elif adx >= 25:
            base = 60.0
        elif adx >= 20:
            base = 40.0
        else:
            base = 10.0

        # Direction check: if -DI dominates, halve the contribution
        plus_di = row.get("plus_di")
        minus_di = row.get("minus_di")
        if (
            plus_di is not None
            and minus_di is not None
            and not pd.isna(plus_di)
            and not pd.isna(minus_di)
            and plus_di < minus_di
        ):
            base *= 0.5

        return base

    @staticmethod
    def _score_price_vs_ma(row: pd.Series) -> float:
        """Score based on price distance from SMA200 and SMA50."""
        price = row.get("close")
        if price is None or pd.isna(price) or price == 0:
            return 30.0

        def _distance_score(ma_val: float | None) -> float | None:
            if ma_val is None or pd.isna(ma_val) or ma_val == 0:
                return None
            pct = (price - ma_val) / ma_val
            if pct > 0.10:
                return 100.0
            if pct > 0.05:
                return 80.0
            if pct > 0.0:
                return 60.0
            if pct > -0.05:
                return 30.0
            return 10.0

        sma200_score = _distance_score(row.get("sma_200"))
        sma50_score = _distance_score(row.get("sma_50"))

        # Also accept ema_ variants if sma_ not available
        if sma200_score is None:
            sma200_score = _distance_score(row.get("ema_200"))
        if sma50_score is None:
            sma50_score = _distance_score(row.get("ema_50"))

        if sma200_score is not None and sma50_score is not None:
            return (sma200_score + sma50_score) / 2.0
        if sma200_score is not None:
            return sma200_score
        if sma50_score is not None:
            return sma50_score
        return 30.0

    # ------------------------------------------------------------------
    # Momentum scoring
    # ------------------------------------------------------------------

    def _score_momentum(
        self, df: pd.DataFrame, row: pd.Series, signals: list[str],
    ) -> float:
        rsi_score = self._score_rsi(row)
        macd_score = self._score_macd(df, row, signals)
        roc_score = self._score_roc(row)

        momentum = rsi_score * 0.35 + macd_score * 0.35 + roc_score * 0.30
        return _clamp(momentum)

    @staticmethod
    def _score_rsi(row: pd.Series) -> float:
        rsi = row.get("rsi")
        if rsi is None or pd.isna(rsi):
            return 50.0

        if 55 <= rsi <= 70:
            return 100.0
        if 50 <= rsi < 55:
            return 80.0
        if 70 < rsi <= 80:
            return 60.0
        if rsi > 80:
            return 30.0
        if 40 <= rsi < 50:
            return 40.0
        if 30 <= rsi < 40:
            return 20.0
        return 10.0  # rsi < 30

    @staticmethod
    def _score_macd(
        df: pd.DataFrame, row: pd.Series, signals: list[str],
    ) -> float:
        hist = row.get("macd_histogram")
        if hist is None or pd.isna(hist):
            return 50.0

        # Histogram direction: compare with previous row
        base = 50.0
        if len(df) >= 2:
            prev_hist = df.iloc[-2].get("macd_histogram")
            if prev_hist is not None and not pd.isna(prev_hist):
                if hist > 0 and hist > prev_hist:
                    base = 100.0
                elif hist > 0 and hist <= prev_hist:
                    base = 60.0
                elif hist < 0 and hist > prev_hist:
                    base = 50.0
                elif hist < 0 and hist <= prev_hist:
                    base = 10.0
                # hist == 0 stays at 50
            else:
                # Fallback: just sign
                base = 70.0 if hist > 0 else 30.0
        else:
            base = 70.0 if hist > 0 else 30.0

        # MACD signal line cross detection within last 5 days
        cross_bonus = 0.0
        if len(df) >= 2 and "macd" in df.columns and "macd_signal" in df.columns:
            lookback = min(5, len(df) - 1)
            tail = df.iloc[-(lookback + 1):]
            macd_vals = tail["macd"]
            sig_vals = tail["macd_signal"]
            diff = macd_vals - sig_vals

            for i in range(1, len(diff)):
                prev_d = diff.iloc[i - 1]
                curr_d = diff.iloc[i]
                if pd.isna(prev_d) or pd.isna(curr_d):
                    continue
                if prev_d <= 0 < curr_d:
                    days_ago = len(diff) - 1 - i
                    signals.append(f"MACD Bullish Cross ({days_ago}d ago)")
                    cross_bonus = 20.0
                elif prev_d >= 0 > curr_d:
                    days_ago = len(diff) - 1 - i
                    signals.append(f"MACD Bearish Cross ({days_ago}d ago)")
                    cross_bonus = -20.0

        return _clamp(base + cross_bonus)

    @staticmethod
    def _score_roc(row: pd.Series) -> float:
        roc5 = row.get("roc_5")
        roc10 = row.get("roc_10")
        roc20 = row.get("roc_20")

        # Determine positivity, treating None/NaN as unavailable
        def _positive(v: float | None) -> bool | None:
            if v is None or pd.isna(v):
                return None
            return v > 0

        p5 = _positive(roc5)
        p10 = _positive(roc10)
        p20 = _positive(roc20)

        # If all available are positive
        available = [x for x in [p5, p10, p20] if x is not None]
        if not available:
            return 50.0

        all_pos = all(available)
        all_neg = not any(available)

        if all_pos:
            return 100.0

        # ROC(5,10) positive, ROC(20) negative → recent recovery
        if p5 is True and p10 is True and p20 is False:
            return 70.0

        # Only ROC(5) positive
        if p5 is True and (p10 is False or p20 is False):
            return 40.0

        if all_neg:
            return 10.0

        # Mixed cases
        pos_count = sum(1 for x in available if x)
        return 30.0 + pos_count * 15.0

    # ------------------------------------------------------------------
    # Volatility / Volume scoring
    # ------------------------------------------------------------------

    def _score_volatility_volume(
        self, df: pd.DataFrame, row: pd.Series, signals: list[str],
    ) -> float:
        volume_score = self._score_volume(df, row, signals)
        atr_score = self._score_atr_position(df, row, signals)
        week52_score = self._score_52w_position(df, row, signals)

        result = volume_score * 0.40 + atr_score * 0.30 + week52_score * 0.30
        return _clamp(result)

    @staticmethod
    def _score_volume(
        df: pd.DataFrame, row: pd.Series, signals: list[str],
    ) -> float:
        volume_ratio = row.get("volume_ratio")
        if volume_ratio is None or pd.isna(volume_ratio):
            return 45.0

        if volume_ratio > 3.0:
            base = 100.0
            signals.append(f"Volume {volume_ratio:.1f}x")
        elif volume_ratio > 2.0:
            base = 80.0
            signals.append(f"Volume {volume_ratio:.1f}x")
        elif volume_ratio > 1.5:
            base = 65.0
        elif volume_ratio > 1.0:
            base = 45.0
        else:
            base = 20.0

        # Price-volume confirmation
        price_change_bonus = 0.0
        if len(df) >= 2:
            curr_close = row.get("close")
            prev_close = df.iloc[-2].get("close")
            if (
                curr_close is not None
                and prev_close is not None
                and not pd.isna(curr_close)
                and not pd.isna(prev_close)
                and prev_close != 0
            ):
                price_up = curr_close > prev_close
                vol_up = volume_ratio > 1.0
                if price_up and vol_up:
                    signals.append("Price-Volume Confirm")
                    price_change_bonus = 15.0
                elif not price_up and vol_up:
                    signals.append("Distribution Warning")
                    price_change_bonus = -15.0

        return _clamp(base + price_change_bonus)

    @staticmethod
    def _score_atr_position(
        df: pd.DataFrame, row: pd.Series, signals: list[str],
    ) -> float:
        atr = row.get("atr")
        price = row.get("close")
        if (
            atr is None
            or price is None
            or pd.isna(atr)
            or pd.isna(price)
            or price == 0
        ):
            return 50.0

        atr_pct = (atr / price) * 100.0

        if 1.0 <= atr_pct <= 2.0:
            base = 100.0
        elif 2.0 < atr_pct <= 3.0:
            base = 80.0
        elif 3.0 < atr_pct <= 5.0:
            base = 60.0
        elif atr_pct < 1.0:
            base = 40.0
        else:
            base = 30.0

        # BB squeeze bonus
        squeeze = IndicatorService.detect_squeeze(df)
        if squeeze:
            signals.append("BB Squeeze")
            base += 20.0

        return _clamp(base)

    @staticmethod
    def _score_52w_position(
        df: pd.DataFrame, row: pd.Series, signals: list[str],
    ) -> float:
        price = row.get("close")
        if price is None or pd.isna(price):
            return 45.0

        # Use up to 250 rows for approximate 52-week range
        lookback = min(250, len(df))
        window = df.iloc[-lookback:]

        if "high" in window.columns:
            high_col = window["high"].dropna()
            low_col = window["low"].dropna() if "low" in window.columns else window["close"].dropna()
        else:
            high_col = window["close"].dropna()
            low_col = window["close"].dropna()

        if high_col.empty or low_col.empty:
            return 45.0

        hi = high_col.max()
        lo = low_col.min()

        if hi == lo:
            return 50.0

        position = (price - lo) / (hi - lo)

        if position > 0.95:
            signals.append("Near 52w High")
            return 100.0
        if position > 0.85:
            return 85.0
        if position > 0.70:
            return 70.0
        if position > 0.50:
            return 45.0
        if position > 0.30:
            return 25.0
        return 10.0

    # ------------------------------------------------------------------
    # Support / Resistance scoring
    # ------------------------------------------------------------------

    def _score_support_resistance(
        self, df: pd.DataFrame, row: pd.Series, signals: list[str],
    ) -> float:
        breakout_score = self._score_breakout(row, signals)
        support_score = self._score_support_strength(row)
        supertrend_score = self._score_supertrend(row)

        # Consecutive up-days bonus
        up_bonus = self._consecutive_up_bonus(df, signals)
        breakout_score = _clamp(breakout_score + up_bonus)

        result = (
            breakout_score * 0.50
            + support_score * 0.30
            + supertrend_score * 0.20
        )
        return _clamp(result)

    @staticmethod
    def _score_breakout(row: pd.Series, signals: list[str]) -> float:
        price = row.get("close")
        donchian_upper = row.get("donchian_upper")

        if (
            price is None
            or donchian_upper is None
            or pd.isna(price)
            or pd.isna(donchian_upper)
            or donchian_upper == 0
        ):
            return 40.0

        if price >= donchian_upper:
            signals.append("Donchian Breakout")
            return 100.0
        if price >= donchian_upper * 0.98:
            signals.append("Breakout Imminent")
            return 80.0
        if price >= donchian_upper * 0.95:
            return 60.0
        return 40.0

    @staticmethod
    def _score_support_strength(row: pd.Series) -> float:
        price = row.get("close")
        ema50 = row.get("ema_50")

        if (
            price is None
            or ema50 is None
            or pd.isna(price)
            or pd.isna(ema50)
            or ema50 == 0
        ):
            return 50.0

        distance = (price - ema50) / ema50

        if distance < 0:
            return 20.0
        if distance <= 0.03:
            return 100.0
        if distance <= 0.08:
            return 80.0
        return 60.0

    @staticmethod
    def _score_supertrend(row: pd.Series) -> float:
        price = row.get("close")
        supertrend = row.get("supertrend")

        if (
            price is None
            or supertrend is None
            or pd.isna(price)
            or pd.isna(supertrend)
        ):
            return 50.0

        return 80.0 if price > supertrend else 20.0

    @staticmethod
    def _consecutive_up_bonus(
        df: pd.DataFrame, signals: list[str],
    ) -> float:
        if "open" not in df.columns or "close" not in df.columns:
            return 0.0

        lookback = min(10, len(df))
        tail = df.iloc[-lookback:]

        up_count = 0
        for _, r in tail.iterrows():
            o = r.get("open")
            c = r.get("close")
            if (
                o is not None
                and c is not None
                and not pd.isna(o)
                and not pd.isna(c)
                and c > o
            ):
                up_count += 1

        if up_count >= 7:
            signals.append(f"{up_count} Up Days (10d)")
            return 15.0
        if up_count >= 5:
            signals.append(f"{up_count} Up Days (10d)")
            return 10.0
        return 0.0

    # ------------------------------------------------------------------
    # Grade mapping
    # ------------------------------------------------------------------

    @staticmethod
    def _to_grade(score: float) -> str:
        if score >= 80:
            return "A"
        if score >= 65:
            return "B"
        if score >= 50:
            return "C"
        if score >= 35:
            return "D"
        return "F"


def _clamp(value: float, lo: float = 0.0, hi: float = 100.0) -> float:
    """Clamp value between lo and hi."""
    return max(lo, min(hi, value))
