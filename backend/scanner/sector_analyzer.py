"""Sector Analyzer - scores and ranks sectors by relative strength.

Uses sector ETF performance data to determine which sectors are
leading/lagging for sector rotation strategy.
"""

import logging
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class SectorScore:
    name: str
    etf: str
    strength_score: float  # 0-100
    return_1w: float
    return_1m: float
    return_3m: float
    trend: str  # "leading", "improving", "lagging", "weakening"
    rank: int = 0


class SectorAnalyzer:
    """Analyze and rank sectors by relative strength."""

    def __init__(self, weights: dict[str, float] | None = None):
        self._weights = weights or {
            "return_1w": 0.20,
            "return_1m": 0.40,
            "return_3m": 0.40,
        }

    def analyze(self, sector_data: dict[str, dict[str, float]]) -> list[SectorScore]:
        """Analyze sector performance data and return ranked scores.

        Args:
            sector_data: Output from ExternalDataService.get_sector_performance()
                {
                    "Technology": {"symbol": "XLK", "return_1d": 0.5, "return_1w": 2.1, ...},
                    ...
                }
        """
        if not sector_data:
            return []

        scores = []
        for name, data in sector_data.items():
            r1w = data.get("return_1w", 0)
            r1m = data.get("return_1m", 0)
            r3m = data.get("return_3m", 0)

            # Weighted return score -> normalized to 0-100
            raw = (
                r1w * self._weights["return_1w"]
                + r1m * self._weights["return_1m"]
                + r3m * self._weights["return_3m"]
            )

            scores.append(SectorScore(
                name=name,
                etf=data.get("symbol", ""),
                strength_score=0,  # normalized below
                return_1w=r1w,
                return_1m=r1m,
                return_3m=r3m,
                trend=self._classify_trend(r1w, r1m, r3m),
            ))

        if not scores:
            return []

        # Normalize raw scores to 0-100 range
        raw_scores = [
            s.return_1w * self._weights["return_1w"]
            + s.return_1m * self._weights["return_1m"]
            + s.return_3m * self._weights["return_3m"]
            for s in scores
        ]
        min_raw = min(raw_scores)
        max_raw = max(raw_scores)
        spread = max_raw - min_raw

        if spread == 0:
            # All same or single entry: assign 100 if positive, 50 if zero, 0 if negative
            for i, s in enumerate(scores):
                s.strength_score = 100.0 if raw_scores[i] > 0 else (0.0 if raw_scores[i] < 0 else 50.0)
        else:
            for i, s in enumerate(scores):
                s.strength_score = round(((raw_scores[i] - min_raw) / spread) * 100, 1)

        # Sort by strength descending and assign ranks
        scores.sort(key=lambda s: s.strength_score, reverse=True)
        for i, s in enumerate(scores):
            s.rank = i + 1

        return scores

    def get_top_sectors(
        self, scores: list[SectorScore], n: int = 3, min_score: float = 60
    ) -> list[SectorScore]:
        """Get top N sectors above minimum strength score."""
        return [s for s in scores[:n] if s.strength_score >= min_score]

    def get_bottom_sectors(
        self, scores: list[SectorScore], n: int = 3
    ) -> list[SectorScore]:
        """Get bottom N weakest sectors."""
        return scores[-n:] if len(scores) >= n else scores

    def _classify_trend(self, r1w: float, r1m: float, r3m: float) -> str:
        """Classify sector trend based on multi-timeframe returns."""
        if r1w > 0 and r1m > 0 and r3m > 0:
            if r1w > r1m / 4:  # Recent acceleration
                return "leading"
            return "improving"
        elif r1w < 0 and r1m < 0:
            return "lagging"
        elif r3m > 0 and r1w < 0:
            return "weakening"
        elif r3m < 0 and r1w > 0:
            return "improving"
        return "improving" if r1m > 0 else "lagging"
