"""Dynamic Universe Expander.

Discovers stocks dynamically using:
1. yfinance predefined screeners (most_actives, day_gainers, growth_technology, etc.)
2. Sector rotation — expand holdings in top-performing sectors
3. ETF Universe config — sector top_holdings as baseline

Replaces the hardcoded 30-stock base_universe in after_hours_scan.
"""

import logging
from dataclasses import dataclass, field

import yfinance as yf

from scanner.etf_universe import ETFUniverse
from scanner.sector_analyzer import SectorAnalyzer, SectorScore

logger = logging.getLogger(__name__)

# yfinance predefined screener queries
SCREENER_QUERIES = [
    "most_actives",
    "day_gainers",
    "growth_technology_stocks",
    "undervalued_large_caps",
    "undervalued_growth_stocks",
]


@dataclass
class UniverseResult:
    """Result of universe expansion."""
    symbols: list[str]
    sources: dict[str, list[str]] = field(default_factory=dict)
    total_discovered: int = 0


class UniverseExpander:
    """Dynamically discover and expand the stock universe."""

    def __init__(
        self,
        etf_universe: ETFUniverse | None = None,
        sector_analyzer: SectorAnalyzer | None = None,
        max_per_screener: int = 15,
        max_total: int = 80,
    ):
        self._etf = etf_universe or ETFUniverse()
        self._sector_analyzer = sector_analyzer or SectorAnalyzer()
        self._max_per_screener = max_per_screener
        self._max_total = max_total

    async def expand(
        self,
        existing_watchlist: list[str] | None = None,
        sector_data: dict[str, dict] | None = None,
    ) -> UniverseResult:
        """Build an expanded universe from multiple sources.

        Args:
            existing_watchlist: Current watchlist symbols to always include.
            sector_data: Sector performance data for sector-weighted expansion.

        Returns:
            UniverseResult with deduplicated symbols and source tracking.
        """
        sources: dict[str, list[str]] = {}
        all_symbols: set[str] = set()

        # Source 1: Existing watchlist (always included)
        if existing_watchlist:
            sources["watchlist"] = list(existing_watchlist)
            all_symbols.update(existing_watchlist)

        # Source 2: ETF Universe sector holdings (baseline)
        sector_holdings = self._get_sector_holdings(sector_data)
        sources["sector_holdings"] = sector_holdings
        all_symbols.update(sector_holdings)

        # Source 3: yfinance screeners (dynamic discovery)
        screener_symbols = self._run_screeners()
        sources["screeners"] = screener_symbols
        all_symbols.update(screener_symbols)

        # Filter: US stocks only, remove ETFs/non-equity
        filtered = self._filter_symbols(all_symbols)

        result = UniverseResult(
            symbols=sorted(filtered)[: self._max_total],
            sources=sources,
            total_discovered=len(filtered),
        )
        logger.info(
            "Universe expanded: %d symbols (watchlist=%d, sectors=%d, screeners=%d)",
            len(result.symbols),
            len(sources.get("watchlist", [])),
            len(sector_holdings),
            len(screener_symbols),
        )
        return result

    def _get_sector_holdings(
        self, sector_data: dict[str, dict] | None = None,
    ) -> list[str]:
        """Get sector holdings, weighted by sector strength.

        Strong sectors get all top_holdings; weak sectors get fewer.
        """
        sectors = self._etf.get_all_sectors()
        if not sectors:
            return []

        # If we have sector performance, prioritize strong sectors
        sector_scores: dict[str, float] = {}
        if sector_data:
            scored = self._sector_analyzer.analyze(sector_data)
            sector_scores = {s.name: s.strength_score for s in scored}

        holdings: list[str] = []
        for name, sector_etf in sectors.items():
            strength = sector_scores.get(name, 50.0)

            # Strong sectors (>60): all 5 holdings
            # Medium sectors (30-60): top 3 holdings
            # Weak sectors (<30): top 1 holding only
            if strength >= 60:
                n = len(sector_etf.top_holdings)
            elif strength >= 30:
                n = min(3, len(sector_etf.top_holdings))
            else:
                n = min(1, len(sector_etf.top_holdings))

            holdings.extend(sector_etf.top_holdings[:n])

        return holdings

    def _run_screeners(self) -> list[str]:
        """Run yfinance predefined screeners to discover stocks."""
        discovered: list[str] = []

        for query in SCREENER_QUERIES:
            try:
                result = yf.screen(query)
                if not result or "quotes" not in result:
                    continue

                quotes = result["quotes"]
                count = 0
                for q in quotes:
                    if count >= self._max_per_screener:
                        break
                    symbol = q.get("symbol", "")
                    # Only US-listed stocks (no suffix like .L, .TO)
                    if symbol and "." not in symbol and symbol.isalpha():
                        discovered.append(symbol)
                        count += 1

                logger.debug(
                    "Screener '%s': found %d symbols", query, count,
                )
            except Exception as e:
                logger.debug("Screener '%s' failed: %s", query, e)

        return list(dict.fromkeys(discovered))  # dedupe preserving order

    def _filter_symbols(self, symbols: set[str]) -> set[str]:
        """Filter out ETFs, leveraged products, and invalid symbols."""
        # Known ETF symbols to exclude
        etf_symbols = set(self._etf.all_etf_symbols)
        etf_symbols.update(self._etf.safe_haven)

        filtered = set()
        for sym in symbols:
            sym = sym.upper().strip()
            if not sym:
                continue
            # Skip ETFs and leveraged products
            if sym in etf_symbols:
                continue
            # Skip symbols with special characters (warrants, units)
            if not sym.replace("-", "").isalpha():
                continue
            # Skip very short symbols (likely ETFs or indices)
            if len(sym) < 1:
                continue
            filtered.add(sym)

        return filtered
