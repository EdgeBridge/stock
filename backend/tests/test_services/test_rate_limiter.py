"""Tests for token bucket rate limiter."""

import asyncio
import time

import pytest

from services.rate_limiter import RateLimiter


class TestRateLimiter:
    def test_initial_tokens(self):
        limiter = RateLimiter(max_per_second=10)
        assert limiter.max_per_second == 10
        assert limiter.available_tokens == pytest.approx(10.0, abs=0.5)

    async def test_acquire_single(self):
        limiter = RateLimiter(max_per_second=20)
        await limiter.acquire()
        assert limiter.available_tokens < 20.0

    async def test_acquire_with_weight(self):
        limiter = RateLimiter(max_per_second=20)
        await limiter.acquire(weight=5)
        assert limiter.available_tokens < 16.0

    async def test_acquire_blocks_when_exhausted(self):
        limiter = RateLimiter(max_per_second=2)
        # Exhaust tokens
        await limiter.acquire(weight=2)

        start = time.monotonic()
        await limiter.acquire(weight=1)
        elapsed = time.monotonic() - start

        # Should have waited ~0.5s for 1 token at 2/sec rate
        assert elapsed >= 0.3

    async def test_token_refill_over_time(self):
        limiter = RateLimiter(max_per_second=10)
        await limiter.acquire(weight=10)
        # Wait for partial refill
        await asyncio.sleep(0.2)
        tokens = limiter.available_tokens
        assert tokens > 0
        assert tokens <= 10.0

    async def test_tokens_cap_at_max(self):
        limiter = RateLimiter(max_per_second=5)
        await asyncio.sleep(0.5)  # Would generate 2.5 extra tokens
        assert limiter.available_tokens <= 5.0

    async def test_concurrent_acquire(self):
        limiter = RateLimiter(max_per_second=10)

        async def worker():
            await limiter.acquire()

        # Run 5 concurrent acquires - should all succeed without deadlock
        await asyncio.gather(*[worker() for _ in range(5)])
        assert limiter.available_tokens < 10.0

    async def test_acquire_respects_rate(self):
        limiter = RateLimiter(max_per_second=5)

        start = time.monotonic()
        for _ in range(7):
            await limiter.acquire()
        elapsed = time.monotonic() - start

        # 5 tokens available immediately, 2 more need ~0.4s
        assert elapsed >= 0.3
