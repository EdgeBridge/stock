"""Market data service with caching layer.

Provides OHLCV, tickers, and orderbooks with Redis/in-memory caching
to minimize KIS API calls within rate limits.
"""

import time
import logging
from typing import Any

import pandas as pd

from exchange.base import ExchangeAdapter, Candle, Ticker
from services.rate_limiter import RateLimiter

logger = logging.getLogger(__name__)

# Cache TTLs
TICKER_CACHE_TTL = 10      # seconds
OHLCV_CACHE_TTL = 60       # seconds


class MarketDataService:
    def __init__(
        self,
        adapter: ExchangeAdapter,
        rate_limiter: RateLimiter | None = None,
    ):
        self._adapter = adapter
        self._rate_limiter = rate_limiter or RateLimiter(max_per_second=20)
        self._ticker_cache: dict[str, tuple[Ticker, float]] = {}
        self._ohlcv_cache: dict[str, tuple[pd.DataFrame, float]] = {}

    async def get_ticker(self, symbol: str, exchange: str = "NASD") -> Ticker:
        """Get current ticker with caching."""
        cache_key = f"{exchange}:{symbol}"
        now = time.time()

        cached = self._ticker_cache.get(cache_key)
        if cached and (now - cached[1]) < TICKER_CACHE_TTL:
            return cached[0]

        await self._rate_limiter.acquire()
        ticker = await self._adapter.fetch_ticker(symbol, exchange)
        self._ticker_cache[cache_key] = (ticker, now)
        return ticker

    async def get_ohlcv(
        self,
        symbol: str,
        timeframe: str = "1D",
        limit: int = 200,
        exchange: str = "NASD",
    ) -> pd.DataFrame:
        """Get OHLCV data as DataFrame with caching."""
        cache_key = f"{exchange}:{symbol}:{timeframe}:{limit}"
        now = time.time()

        cached = self._ohlcv_cache.get(cache_key)
        if cached and (now - cached[1]) < OHLCV_CACHE_TTL:
            return cached[0]

        await self._rate_limiter.acquire()
        candles = await self._adapter.fetch_ohlcv(symbol, timeframe, limit, exchange)

        if not candles:
            df = pd.DataFrame(columns=["timestamp", "open", "high", "low", "close", "volume"])
        else:
            df = pd.DataFrame([
                {
                    "timestamp": c.timestamp,
                    "open": c.open,
                    "high": c.high,
                    "low": c.low,
                    "close": c.close,
                    "volume": c.volume,
                }
                for c in candles
            ])

        self._ohlcv_cache[cache_key] = (df, now)
        return df

    async def get_price(self, symbol: str, exchange: str = "NASD") -> float:
        """Get current price (convenience wrapper)."""
        ticker = await self.get_ticker(symbol, exchange)
        return ticker.price

    async def get_multiple_tickers(
        self, symbols: list[str], exchange: str = "NASD"
    ) -> dict[str, Ticker]:
        """Get tickers for multiple symbols."""
        result = {}
        for symbol in symbols:
            try:
                result[symbol] = await self.get_ticker(symbol, exchange)
            except Exception as e:
                logger.warning("Failed to fetch ticker for %s: %s", symbol, e)
        return result

    def invalidate_cache(self, symbol: str | None = None) -> None:
        """Clear cache for a symbol or all."""
        if symbol:
            keys_to_remove = [k for k in self._ticker_cache if symbol in k]
            for k in keys_to_remove:
                del self._ticker_cache[k]
            keys_to_remove = [k for k in self._ohlcv_cache if symbol in k]
            for k in keys_to_remove:
                del self._ohlcv_cache[k]
        else:
            self._ticker_cache.clear()
            self._ohlcv_cache.clear()
