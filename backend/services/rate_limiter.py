"""Token bucket rate limiter for KIS API.

Real account: 20 req/sec
Paper account: 5 req/sec

Priority-based queuing:
  1. Orders (highest)
  2. Balance/positions
  3. Market data
  4. Scanner (lowest)
"""

import asyncio
import time
import logging

logger = logging.getLogger(__name__)


class RateLimiter:
    def __init__(self, max_per_second: int = 20):
        self._max_per_second = max_per_second
        self._tokens = float(max_per_second)
        self._last_refill = time.monotonic()
        self._lock = asyncio.Lock()

    @property
    def max_per_second(self) -> int:
        return self._max_per_second

    async def acquire(self, weight: int = 1) -> None:
        """Wait until a request slot is available."""
        async with self._lock:
            self._refill()
            while self._tokens < weight:
                wait = (weight - self._tokens) / self._max_per_second
                await asyncio.sleep(wait)
                self._refill()
            self._tokens -= weight

    def _refill(self) -> None:
        now = time.monotonic()
        elapsed = now - self._last_refill
        self._tokens = min(
            float(self._max_per_second),
            self._tokens + elapsed * self._max_per_second,
        )
        self._last_refill = now

    @property
    def available_tokens(self) -> float:
        self._refill()
        return self._tokens
