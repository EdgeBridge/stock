"""Multi-Factor Scoring Model.

Ranks stocks systematically using quantitative factors:
1. Momentum Factor — price momentum across multiple timeframes
2. Value Factor — valuation metrics (PE, PB, FCF yield)
3. Quality Factor — profitability and financial health
4. Low Volatility Factor — inverse of realized volatility

Each factor produces a z-score (cross-sectional ranking).
Combined factor score determines stock attractiveness.

References:
- Fama-French 3-factor model (market, size, value)
- Carhart 4-factor model (+momentum)
- AQR quality-minus-junk (profitability, payout, safety)
"""

import logging
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


@dataclass
class FactorScores:
    """Per-stock factor scores (z-scores, higher = better)."""
    symbol: str
    momentum: float = 0.0
    value: float = 0.0
    quality: float = 0.0
    low_volatility: float = 0.0
    composite: float = 0.0
    rank: int = 0


@dataclass
class FactorWeights:
    """Weights for combining factors into composite score."""
    momentum: float = 0.30
    value: float = 0.25
    quality: float = 0.25
    low_volatility: float = 0.20


class MultiFactorModel:
    """Cross-sectional multi-factor stock ranking model."""

    def __init__(self, weights: FactorWeights | None = None):
        self._weights = weights or FactorWeights()

    def score_universe(
        self,
        price_data: dict[str, pd.DataFrame],
        fundamental_data: dict[str, dict] | None = None,
    ) -> list[FactorScores]:
        """Score and rank a universe of stocks by factor model.

        Args:
            price_data: {symbol: OHLCV DataFrame} with at least 252 bars.
            fundamental_data: {symbol: {pe, pb, roe, debt_to_equity, ...}}.

        Returns:
            List of FactorScores sorted by composite score descending.
        """
        if not price_data:
            return []

        symbols = list(price_data.keys())

        # Compute raw factor values
        momentum_raw = self._compute_momentum(price_data)
        volatility_raw = self._compute_volatility(price_data)
        value_raw = self._compute_value(fundamental_data or {}, symbols)
        quality_raw = self._compute_quality(fundamental_data or {}, symbols)

        # Cross-sectional z-score normalization
        momentum_z = self._zscore(momentum_raw)
        vol_z = self._zscore({s: -v for s, v in volatility_raw.items()})  # Invert: lower vol = higher score
        value_z = self._zscore(value_raw)
        quality_z = self._zscore(quality_raw)

        # Composite score
        w = self._weights
        results = []
        for sym in symbols:
            m = momentum_z.get(sym, 0.0)
            v = value_z.get(sym, 0.0)
            q = quality_z.get(sym, 0.0)
            lv = vol_z.get(sym, 0.0)
            composite = (
                m * w.momentum + v * w.value + q * w.quality + lv * w.low_volatility
            )
            results.append(FactorScores(
                symbol=sym,
                momentum=round(m, 3),
                value=round(v, 3),
                quality=round(q, 3),
                low_volatility=round(lv, 3),
                composite=round(composite, 3),
            ))

        # Rank by composite
        results.sort(key=lambda s: s.composite, reverse=True)
        for i, r in enumerate(results):
            r.rank = i + 1

        return results

    def _compute_momentum(self, price_data: dict[str, pd.DataFrame]) -> dict[str, float]:
        """Multi-timeframe momentum factor.

        Composite of:
        - 12-month return excluding last month (classic momentum)
        - 6-month return
        - 1-month return (mean-reversion offset)
        """
        scores = {}
        for sym, df in price_data.items():
            if len(df) < 252:
                scores[sym] = 0.0
                continue

            close = df["close"]
            current = float(close.iloc[-1])

            # 12-month return ex last month (skip recent reversal)
            if len(close) >= 252:
                ret_12m = current / float(close.iloc[-252]) - 1
                ret_1m = current / float(close.iloc[-21]) - 1
                mom_12_1 = ret_12m - ret_1m  # Classic 12-1 momentum
            else:
                mom_12_1 = 0.0

            # 6-month return
            if len(close) >= 126:
                ret_6m = current / float(close.iloc[-126]) - 1
            else:
                ret_6m = 0.0

            # Weighted composite
            scores[sym] = mom_12_1 * 0.5 + ret_6m * 0.3 + ret_1m * 0.2 if len(close) >= 252 else ret_6m

        return scores

    def _compute_volatility(self, price_data: dict[str, pd.DataFrame]) -> dict[str, float]:
        """Realized volatility (annualized standard deviation of daily returns)."""
        scores = {}
        for sym, df in price_data.items():
            if len(df) < 60:
                scores[sym] = 0.5  # Default moderate
                continue
            returns = df["close"].pct_change().dropna().tail(60)
            scores[sym] = float(returns.std() * np.sqrt(252))
        return scores

    def _compute_value(
        self, fundamentals: dict[str, dict], symbols: list[str],
    ) -> dict[str, float]:
        """Value factor from fundamental data.

        Uses:
        - Earnings yield (1/PE) — higher = cheaper
        - Book yield (1/PB) — higher = cheaper
        - FCF yield — higher = better
        """
        scores = {}
        for sym in symbols:
            data = fundamentals.get(sym, {})
            pe = data.get("pe_ratio") or data.get("trailingPE")
            pb = data.get("pb_ratio") or data.get("priceToBook")
            fcf_yield = data.get("fcf_yield")

            components = []
            if pe and pe > 0:
                components.append(1.0 / pe)  # Earnings yield
            if pb and pb > 0:
                components.append(1.0 / pb)  # Book yield
            if fcf_yield:
                components.append(fcf_yield)

            scores[sym] = float(np.mean(components)) if components else 0.0

        return scores

    def _compute_quality(
        self, fundamentals: dict[str, dict], symbols: list[str],
    ) -> dict[str, float]:
        """Quality factor: profitability + financial health.

        Uses:
        - ROE (return on equity)
        - Profit margin
        - Debt-to-equity (inverse, lower = better)
        - Revenue growth
        """
        scores = {}
        for sym in symbols:
            data = fundamentals.get(sym, {})
            roe = data.get("roe") or data.get("returnOnEquity") or 0
            margin = data.get("profit_margin") or data.get("profitMargins") or 0
            de = data.get("debt_to_equity") or data.get("debtToEquity") or 1
            growth = data.get("revenue_growth") or data.get("revenueGrowth") or 0

            # Normalize each component
            roe_score = min(roe, 0.5)  # Cap at 50% ROE
            margin_score = min(margin, 0.4)  # Cap at 40% margin
            de_score = max(0, 1.0 - de) if de < 2 else -0.5  # Penalize high debt
            growth_score = min(growth, 0.5)  # Cap at 50% growth

            scores[sym] = float(np.mean([roe_score, margin_score, de_score, growth_score]))

        return scores

    @staticmethod
    def _zscore(values: dict[str, float]) -> dict[str, float]:
        """Cross-sectional z-score normalization."""
        if not values:
            return {}
        arr = np.array(list(values.values()))
        mean = np.mean(arr)
        std = np.std(arr)
        if std == 0:
            return {s: 0.0 for s in values}
        return {s: float((v - mean) / std) for s, v in values.items()}

    def get_top_n(
        self,
        scores: list[FactorScores],
        n: int = 10,
        min_composite: float = 0.0,
    ) -> list[FactorScores]:
        """Get top N stocks by composite score."""
        return [s for s in scores[:n] if s.composite >= min_composite]
