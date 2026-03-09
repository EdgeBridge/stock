"""Korean stock fundamental enricher using pykrx.

Enriches KR stock candidates with:
- PER, PBR, EPS, BPS
- 배당수익률 (dividend yield)
- 시가총액 (market cap)
- 거래대금 (trading value)
"""

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta

from pykrx import stock as pykrx_stock

logger = logging.getLogger(__name__)


@dataclass
class KRFundamentals:
    """Fundamental data for a Korean stock."""
    symbol: str
    per: float = 0.0
    pbr: float = 0.0
    eps: float = 0.0
    bps: float = 0.0
    dividend_yield: float = 0.0
    market_cap: int = 0         # 시가총액 (원)
    trading_value: int = 0      # 거래대금 (원)
    price: float = 0.0          # 종가


def _get_latest_trading_date() -> str:
    dt = datetime.now()
    if dt.hour < 16:
        dt -= timedelta(days=1)
    while dt.weekday() >= 5:
        dt -= timedelta(days=1)
    return dt.strftime("%Y%m%d")


class KRFundamentalEnricher:
    """Enrich Korean stocks with fundamental data from pykrx."""

    def __init__(self, date: str | None = None):
        self._date = date or _get_latest_trading_date()
        self._fundamental_cache: dict[str, KRFundamentals] = {}
        self._loaded = False

    def _ensure_loaded(self, market: str = "ALL") -> None:
        """Lazy-load all fundamentals + market cap for the date."""
        if self._loaded:
            return
        try:
            # Load fundamentals (PER/PBR/EPS/BPS/DIV)
            fund_df = pykrx_stock.get_market_fundamental(self._date, market=market)
            # Load market cap + trading value
            cap_df = pykrx_stock.get_market_cap(self._date, market=market)

            for ticker in fund_df.index:
                f = KRFundamentals(symbol=ticker)
                row = fund_df.loc[ticker]
                f.per = float(row.get("PER", 0))
                f.pbr = float(row.get("PBR", 0))
                f.eps = float(row.get("EPS", 0))
                f.bps = float(row.get("BPS", 0))
                f.dividend_yield = float(row.get("DIV", 0))

                if ticker in cap_df.index:
                    cap_row = cap_df.loc[ticker]
                    f.market_cap = int(cap_row.get("시가총액", 0))
                    f.trading_value = int(cap_row.get("거래대금", 0))
                    f.price = float(cap_row.get("종가", 0))

                self._fundamental_cache[ticker] = f

            self._loaded = True
            logger.info(
                "KR fundamentals loaded: %d stocks for %s",
                len(self._fundamental_cache), self._date,
            )
        except Exception as e:
            logger.error("Failed to load KR fundamentals: %s", e)
            self._loaded = True  # Don't retry on failure

    def get(self, symbol: str) -> KRFundamentals | None:
        """Get fundamentals for a single stock."""
        self._ensure_loaded()
        return self._fundamental_cache.get(symbol)

    def get_batch(self, symbols: list[str]) -> dict[str, KRFundamentals]:
        """Get fundamentals for multiple stocks."""
        self._ensure_loaded()
        return {s: self._fundamental_cache[s] for s in symbols if s in self._fundamental_cache}

    def score(self, symbol: str) -> float:
        """Calculate a fundamental score (0-100) for a stock.

        Scoring:
        - PER: 0-10 best, 10-20 good, >20 or negative = poor
        - PBR: <1 best, 1-2 good, >3 poor
        - Dividend yield: >3% best, 1-3% good, 0 poor
        """
        f = self.get(symbol)
        if not f:
            return 50.0  # neutral default

        score = 50.0

        # PER component (max +20)
        if 0 < f.per <= 10:
            score += 20
        elif 0 < f.per <= 15:
            score += 12
        elif 0 < f.per <= 20:
            score += 5
        elif f.per <= 0:
            score -= 5  # negative earnings

        # PBR component (max +15)
        if 0 < f.pbr < 1:
            score += 15
        elif 0 < f.pbr < 1.5:
            score += 10
        elif 0 < f.pbr < 2:
            score += 5
        elif f.pbr > 5:
            score -= 5

        # Dividend yield component (max +15)
        if f.dividend_yield >= 4:
            score += 15
        elif f.dividend_yield >= 2:
            score += 10
        elif f.dividend_yield >= 1:
            score += 5

        return max(0, min(100, score))
