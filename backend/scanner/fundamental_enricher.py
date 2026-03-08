"""Layer 2: Fundamental Enricher.

Enriches screened candidates with yfinance fundamental data:
- Analyst consensus (target price, ratings)
- Fundamentals (PE, growth, margins)
- Smart money (institutional %, insider activity)
"""

import logging
from dataclasses import dataclass

from data.external_data_service import ExternalDataService, StockProfile

logger = logging.getLogger(__name__)


@dataclass
class EnrichedCandidate:
    symbol: str
    indicator_score: float
    consensus_score: float
    fundamental_score: float
    smart_money_score: float
    combined_score: float
    profile: StockProfile | None = None
    grade: str = ""


class FundamentalEnricher:
    """Enrich indicator-screened candidates with fundamental data."""

    def __init__(
        self,
        data_service: ExternalDataService | None = None,
        weights: dict[str, float] | None = None,
    ):
        self._data_svc = data_service or ExternalDataService()
        self._weights = weights or {
            "consensus": 0.35,
            "fundamental": 0.35,
            "smart_money": 0.30,
        }

    async def enrich(
        self,
        symbol: str,
        indicator_score: float,
        current_price: float = 0.0,
    ) -> EnrichedCandidate:
        """Enrich a single candidate with fundamental data."""
        profile = await self._data_svc.get_stock_profile(symbol, current_price)

        consensus = self._score_consensus(profile)
        fundamental = self._score_fundamentals(profile)
        smart_money = self._score_smart_money(profile)

        combined = (
            consensus * self._weights["consensus"]
            + fundamental * self._weights["fundamental"]
            + smart_money * self._weights["smart_money"]
        )

        # Blend with indicator score (50/50)
        blended = (indicator_score + combined) / 2

        return EnrichedCandidate(
            symbol=symbol,
            indicator_score=indicator_score,
            consensus_score=round(consensus, 1),
            fundamental_score=round(fundamental, 1),
            smart_money_score=round(smart_money, 1),
            combined_score=round(blended, 1),
            profile=profile,
            grade=self._to_grade(blended),
        )

    async def enrich_batch(
        self,
        candidates: list[tuple[str, float, float]],
    ) -> list[EnrichedCandidate]:
        """Enrich multiple candidates: [(symbol, indicator_score, price)]."""
        results = []
        for symbol, score, price in candidates:
            try:
                enriched = await self.enrich(symbol, score, price)
                results.append(enriched)
            except Exception as e:
                logger.warning("Failed to enrich %s: %s", symbol, e)
        results.sort(key=lambda c: c.combined_score, reverse=True)
        return results

    def _score_consensus(self, profile: StockProfile) -> float:
        score = 50.0
        c = profile.consensus

        if c.analyst_count > 0:
            bull_pct = (c.strong_buy + c.buy) / c.analyst_count * 100
            if bull_pct > 70:
                score += 25
            elif bull_pct > 50:
                score += 15
            elif bull_pct < 30:
                score -= 15

        if c.target_upside_pct > 20:
            score += 15
        elif c.target_upside_pct > 10:
            score += 10
        elif c.target_upside_pct < -10:
            score -= 15

        return max(0, min(100, score))

    def _score_fundamentals(self, profile: StockProfile) -> float:
        """Score fundamentals using research-backed factors.

        Empirical IC results (60 stocks, 5yr):
        - Revenue growth: IC=0.23 (strongest predictor)
        - Earnings growth: IC=0.19
        - Profit margin: IC=0.18, IR=1.39 (most consistent)
        - ROE: IC=0.11
        - GARP (growth/PE): IC=0.20
        """
        score = 50.0
        f = profile.fundamentals

        # Revenue growth (IC=0.23 — strongest predictor)
        if f.revenue_growth is not None:
            if f.revenue_growth > 0.25:
                score += 18
            elif f.revenue_growth > 0.15:
                score += 12
            elif f.revenue_growth > 0.05:
                score += 5
            elif f.revenue_growth < -0.05:
                score -= 12

        # Earnings growth (IC=0.19)
        if f.earnings_growth is not None:
            if f.earnings_growth > 0.25:
                score += 15
            elif f.earnings_growth > 0.10:
                score += 8
            elif f.earnings_growth < -0.10:
                score -= 10

        # Profit margin (IC=0.18, IR=1.39 — most consistent signal)
        if f.profit_margin is not None:
            if f.profit_margin > 0.25:
                score += 12
            elif f.profit_margin > 0.15:
                score += 8
            elif f.profit_margin > 0.05:
                score += 3
            elif f.profit_margin < 0:
                score -= 12

        # ROE (IC=0.11)
        if f.roe is not None:
            if f.roe > 0.25:
                score += 8
            elif f.roe > 0.15:
                score += 5
            elif f.roe < 0.05:
                score -= 5

        # GARP: growth relative to PE (IC=0.20)
        if f.revenue_growth is not None and f.forward_pe is not None and f.forward_pe > 0:
            garp = f.revenue_growth / f.forward_pe * 100
            if garp > 1.0:
                score += 10
            elif garp > 0.5:
                score += 5
            elif garp < -0.2:
                score -= 5

        return max(0, min(100, score))

    def _score_smart_money(self, profile: StockProfile) -> float:
        score = 50.0
        s = profile.smart_money

        if s.institutional_pct is not None:
            if s.institutional_pct > 0.70:
                score += 10
            elif s.institutional_pct < 0.30:
                score -= 10

        if s.insider_buy_count_90d > s.insider_sell_count_90d:
            score += 15
        elif s.insider_sell_count_90d > s.insider_buy_count_90d * 2:
            score -= 10

        if s.short_ratio is not None:
            if s.short_ratio > 5:
                score -= 10  # High short interest = risk
            elif s.short_ratio < 2:
                score += 5

        return max(0, min(100, score))

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
