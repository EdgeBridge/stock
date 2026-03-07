"""KIS API-based stock scanner.

Discovers candidate stocks using KIS market data APIs:
- Volume surges (active trading)
- Price movers (top gainers/losers)
- 52-week highs (breakout candidates)

Works independently of the 3-layer pipeline as a symbol discovery tool.
Feeds symbols into the ScannerPipeline for scoring.
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


@dataclass
class ScanResult:
    symbol: str
    name: str
    price: float
    change_pct: float
    volume: int
    scan_type: str  # "volume_surge", "top_gainer", "top_loser", "new_high"
    score: float = 0.0  # scan-specific relevance score
    metadata: dict = field(default_factory=dict)


@dataclass
class ScanSummary:
    scan_time: str
    total_found: int
    by_type: dict[str, int]
    results: list[ScanResult]


class StockScanner:
    """Discover candidate stocks from KIS market data.

    Provides multiple scan modes that can run independently or together.
    Results feed into the ScannerPipeline for deeper analysis.
    """

    def __init__(
        self,
        adapter=None,
        market_data=None,
        volume_threshold: float = 2.0,
        min_price: float = 5.0,
        max_price: float = 500.0,
        min_volume: int = 500_000,
    ):
        self._adapter = adapter
        self._market_data = market_data
        self._volume_threshold = volume_threshold
        self._min_price = min_price
        self._max_price = max_price
        self._min_volume = min_volume
        self._last_scan: ScanSummary | None = None

    async def run_all_scans(
        self, watchlist: list[str] | None = None
    ) -> ScanSummary:
        """Run all scan types and return combined results."""
        results: list[ScanResult] = []

        scan_fns = [
            self.scan_volume_surges,
            self.scan_top_gainers,
            self.scan_top_losers,
            self.scan_new_highs,
        ]

        for scan_fn in scan_fns:
            try:
                partial = await scan_fn(watchlist)
                results.extend(partial)
            except Exception as e:
                logger.warning("Scan %s failed: %s", scan_fn.__name__, e)

        # Deduplicate by symbol, keeping highest score
        seen: dict[str, ScanResult] = {}
        for r in results:
            if r.symbol not in seen or r.score > seen[r.symbol].score:
                seen[r.symbol] = r
        deduped = list(seen.values())
        deduped.sort(key=lambda r: r.score, reverse=True)

        summary = ScanSummary(
            scan_time=datetime.now(timezone.utc).isoformat(),
            total_found=len(deduped),
            by_type=self._count_by_type(deduped),
            results=deduped,
        )
        self._last_scan = summary
        return summary

    async def scan_volume_surges(
        self, watchlist: list[str] | None = None
    ) -> list[ScanResult]:
        """Find stocks with unusually high volume."""
        symbols = watchlist or []
        if not symbols or not self._market_data:
            return []

        results = []
        for symbol in symbols:
            try:
                df = await self._market_data.get_ohlcv(symbol, limit=30)
                if df.empty or len(df) < 21:
                    continue

                current_vol = float(df.iloc[-1]["volume"])
                avg_vol = float(df.iloc[-21:-1]["volume"].mean())

                if avg_vol <= 0:
                    continue

                ratio = current_vol / avg_vol
                price = float(df.iloc[-1]["close"])
                change_pct = float(
                    (df.iloc[-1]["close"] - df.iloc[-2]["close"])
                    / df.iloc[-2]["close"] * 100
                ) if len(df) >= 2 else 0.0

                if ratio >= self._volume_threshold and self._passes_filters(price, current_vol):
                    score = min(100.0, ratio * 25)
                    results.append(ScanResult(
                        symbol=symbol,
                        name=symbol,
                        price=price,
                        change_pct=round(change_pct, 2),
                        volume=int(current_vol),
                        scan_type="volume_surge",
                        score=round(score, 1),
                        metadata={"volume_ratio": round(ratio, 2), "avg_volume": int(avg_vol)},
                    ))
            except Exception as e:
                logger.debug("Volume scan failed for %s: %s", symbol, e)

        results.sort(key=lambda r: r.score, reverse=True)
        return results

    async def scan_top_gainers(
        self, watchlist: list[str] | None = None
    ) -> list[ScanResult]:
        """Find stocks with largest positive price change."""
        return await self._scan_movers(watchlist, direction="up")

    async def scan_top_losers(
        self, watchlist: list[str] | None = None
    ) -> list[ScanResult]:
        """Find stocks with largest negative price change."""
        return await self._scan_movers(watchlist, direction="down")

    async def scan_new_highs(
        self, watchlist: list[str] | None = None
    ) -> list[ScanResult]:
        """Find stocks near or at 52-week highs."""
        symbols = watchlist or []
        if not symbols or not self._market_data:
            return []

        results = []
        for symbol in symbols:
            try:
                df = await self._market_data.get_ohlcv(symbol, limit=252)
                if df.empty or len(df) < 50:
                    continue

                price = float(df.iloc[-1]["close"])
                high_52w = float(df["high"].max())
                low_52w = float(df["low"].min())
                volume = float(df.iloc[-1]["volume"])

                if high_52w <= low_52w:
                    continue

                position = (price - low_52w) / (high_52w - low_52w)

                if position >= 0.90 and self._passes_filters(price, volume):
                    score = min(100.0, position * 100)
                    change_pct = float(
                        (df.iloc[-1]["close"] - df.iloc[-2]["close"])
                        / df.iloc[-2]["close"] * 100
                    ) if len(df) >= 2 else 0.0

                    results.append(ScanResult(
                        symbol=symbol,
                        name=symbol,
                        price=price,
                        change_pct=round(change_pct, 2),
                        volume=int(volume),
                        scan_type="new_high",
                        score=round(score, 1),
                        metadata={
                            "52w_high": round(high_52w, 2),
                            "52w_low": round(low_52w, 2),
                            "52w_position": round(position, 3),
                        },
                    ))
            except Exception as e:
                logger.debug("New high scan failed for %s: %s", symbol, e)

        results.sort(key=lambda r: r.score, reverse=True)
        return results

    async def _scan_movers(
        self, watchlist: list[str] | None, direction: str
    ) -> list[ScanResult]:
        """Common implementation for top gainers/losers."""
        symbols = watchlist or []
        if not symbols or not self._market_data:
            return []

        results = []
        for symbol in symbols:
            try:
                df = await self._market_data.get_ohlcv(symbol, limit=5)
                if df.empty or len(df) < 2:
                    continue

                price = float(df.iloc[-1]["close"])
                prev = float(df.iloc[-2]["close"])
                volume = float(df.iloc[-1]["volume"])

                if prev <= 0:
                    continue

                change_pct = (price - prev) / prev * 100

                if not self._passes_filters(price, volume):
                    continue

                if direction == "up" and change_pct > 2.0:
                    score = min(100.0, change_pct * 10)
                    results.append(ScanResult(
                        symbol=symbol, name=symbol, price=price,
                        change_pct=round(change_pct, 2), volume=int(volume),
                        scan_type="top_gainer", score=round(score, 1),
                    ))
                elif direction == "down" and change_pct < -2.0:
                    score = min(100.0, abs(change_pct) * 10)
                    results.append(ScanResult(
                        symbol=symbol, name=symbol, price=price,
                        change_pct=round(change_pct, 2), volume=int(volume),
                        scan_type="top_loser", score=round(score, 1),
                    ))
            except Exception as e:
                logger.debug("Mover scan failed for %s: %s", symbol, e)

        results.sort(key=lambda r: r.score, reverse=True)
        return results

    def _passes_filters(self, price: float, volume: float) -> bool:
        """Check if stock passes basic price/volume filters."""
        if price < self._min_price or price > self._max_price:
            return False
        if volume < self._min_volume:
            return False
        return True

    @staticmethod
    def _count_by_type(results: list[ScanResult]) -> dict[str, int]:
        counts: dict[str, int] = {}
        for r in results:
            counts[r.scan_type] = counts.get(r.scan_type, 0) + 1
        return counts

    @property
    def last_scan(self) -> ScanSummary | None:
        return self._last_scan

    def get_symbols(self, max_results: int = 30) -> list[str]:
        """Get unique symbols from last scan results."""
        if not self._last_scan:
            return []
        return [r.symbol for r in self._last_scan.results[:max_results]]
