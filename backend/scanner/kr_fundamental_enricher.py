"""Korean stock fundamental enricher using yfinance.

Enriches KR stock candidates with:
- PER, PBR
- 배당수익률 (dividend yield)
- 시가총액 (market cap)

Falls back gracefully if yfinance data is unavailable.
"""

import logging
from dataclasses import dataclass

import yfinance as yf

from data.kr_symbol_mapper import to_yfinance

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


class KRFundamentalEnricher:
    """Enrich Korean stocks with fundamental data from yfinance."""

    def __init__(self, date: str | None = None, exchange: str = "KRX"):
        self._date = date  # kept for backward compat, not used by yfinance
        self._exchange = exchange
        self._cache: dict[str, KRFundamentals] = {}

    def get(self, symbol: str) -> KRFundamentals | None:
        """Get fundamentals for a single stock."""
        if symbol in self._cache:
            return self._cache[symbol]

        try:
            yf_sym = to_yfinance(symbol, self._exchange)
            ticker = yf.Ticker(yf_sym)
            info = ticker.info

            f = KRFundamentals(symbol=symbol)
            f.per = float(info.get("trailingPE", 0) or 0)
            f.pbr = float(info.get("priceToBook", 0) or 0)
            f.eps = float(info.get("trailingEps", 0) or 0)
            f.bps = float(info.get("bookValue", 0) or 0)
            f.dividend_yield = float(info.get("dividendYield", 0) or 0) * 100
            f.market_cap = int(info.get("marketCap", 0) or 0)
            f.price = float(info.get("currentPrice", 0) or info.get("previousClose", 0) or 0)

            self._cache[symbol] = f
            return f
        except Exception as e:
            logger.debug("Failed to get fundamentals for %s: %s", symbol, e)
            return None

    def get_batch(self, symbols: list[str]) -> dict[str, KRFundamentals]:
        """Get fundamentals for multiple stocks."""
        result = {}
        for s in symbols:
            f = self.get(s)
            if f:
                result[s] = f
        return result

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
