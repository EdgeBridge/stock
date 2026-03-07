"""Tests for CacheService.

Covers get/set/delete, JSON helpers, graceful fallback when Redis is
unavailable, initialization failure handling, and the available property.
"""

import json
from unittest.mock import AsyncMock, patch

import pytest

from services.cache import CacheService


# ── Fixtures ─────────────────────────────────────────────────────────

@pytest.fixture
def mock_redis():
    """Return an AsyncMock that behaves like a redis.asyncio.Redis client."""
    r = AsyncMock()
    r.ping = AsyncMock(return_value=True)
    r.get = AsyncMock(return_value=None)
    r.set = AsyncMock(return_value=True)
    r.delete = AsyncMock(return_value=1)
    r.close = AsyncMock()
    return r


@pytest.fixture
def cache():
    """Uninitialised CacheService (no Redis connection)."""
    return CacheService(url="redis://localhost:6379/1")


# ── Initialization ───────────────────────────────────────────────────

async def test_initialize_success(cache, mock_redis):
    with patch("services.cache.redis.from_url", return_value=mock_redis):
        await cache.initialize()

    assert cache.available is True
    mock_redis.ping.assert_awaited_once()


async def test_initialize_failure_sets_redis_none(cache):
    """If Redis is unreachable, _redis is set to None without crashing."""
    failing_redis = AsyncMock()
    failing_redis.ping = AsyncMock(side_effect=ConnectionError("refused"))

    with patch("services.cache.redis.from_url", return_value=failing_redis):
        await cache.initialize()

    assert cache.available is False
    assert cache._redis is None


# ── available property ───────────────────────────────────────────────

async def test_available_false_before_init(cache):
    assert cache.available is False


async def test_available_true_after_successful_init(cache, mock_redis):
    with patch("services.cache.redis.from_url", return_value=mock_redis):
        await cache.initialize()
    assert cache.available is True


# ── get / set / delete with mock Redis ───────────────────────────────

async def test_get_returns_value(cache, mock_redis):
    mock_redis.get = AsyncMock(return_value="bar")
    with patch("services.cache.redis.from_url", return_value=mock_redis):
        await cache.initialize()

    result = await cache.get("foo")
    assert result == "bar"
    mock_redis.get.assert_awaited_with("foo")


async def test_set_stores_value(cache, mock_redis):
    with patch("services.cache.redis.from_url", return_value=mock_redis):
        await cache.initialize()

    result = await cache.set("foo", "bar", ex=300)
    assert result is True
    mock_redis.set.assert_awaited_with("foo", "bar", ex=300)


async def test_set_without_expiry(cache, mock_redis):
    with patch("services.cache.redis.from_url", return_value=mock_redis):
        await cache.initialize()

    result = await cache.set("key", "val")
    assert result is True
    mock_redis.set.assert_awaited_with("key", "val", ex=None)


async def test_delete_removes_key(cache, mock_redis):
    with patch("services.cache.redis.from_url", return_value=mock_redis):
        await cache.initialize()

    result = await cache.delete("foo")
    assert result is True
    mock_redis.delete.assert_awaited_with("foo")


# ── Graceful fallback (Redis unavailable) ────────────────────────────

async def test_get_returns_none_when_unavailable(cache):
    assert cache.available is False
    result = await cache.get("foo")
    assert result is None


async def test_set_returns_false_when_unavailable(cache):
    assert cache.available is False
    result = await cache.set("foo", "bar")
    assert result is False


async def test_delete_returns_false_when_unavailable(cache):
    assert cache.available is False
    result = await cache.delete("foo")
    assert result is False


async def test_get_json_returns_none_when_unavailable(cache):
    assert cache.available is False
    result = await cache.get_json("foo")
    assert result is None


async def test_set_json_returns_false_when_unavailable(cache):
    assert cache.available is False
    result = await cache.set_json("foo", {"a": 1})
    assert result is False


# ── Error handling (Redis connected but command fails) ───────────────

async def test_get_returns_none_on_redis_error(cache, mock_redis):
    mock_redis.get = AsyncMock(side_effect=ConnectionError("lost"))
    with patch("services.cache.redis.from_url", return_value=mock_redis):
        await cache.initialize()

    result = await cache.get("foo")
    assert result is None


async def test_set_returns_false_on_redis_error(cache, mock_redis):
    mock_redis.set = AsyncMock(side_effect=ConnectionError("lost"))
    with patch("services.cache.redis.from_url", return_value=mock_redis):
        await cache.initialize()

    result = await cache.set("foo", "bar")
    assert result is False


async def test_delete_returns_false_on_redis_error(cache, mock_redis):
    mock_redis.delete = AsyncMock(side_effect=ConnectionError("lost"))
    with patch("services.cache.redis.from_url", return_value=mock_redis):
        await cache.initialize()

    result = await cache.delete("foo")
    assert result is False


# ── JSON helpers ─────────────────────────────────────────────────────

async def test_get_json_returns_parsed_dict(cache, mock_redis):
    data = {"access_token": "tok123", "expires_at": 1700000000}
    mock_redis.get = AsyncMock(return_value=json.dumps(data))
    with patch("services.cache.redis.from_url", return_value=mock_redis):
        await cache.initialize()

    result = await cache.get_json("kis:token")
    assert result == data
    assert isinstance(result, dict)


async def test_get_json_returns_none_for_missing_key(cache, mock_redis):
    mock_redis.get = AsyncMock(return_value=None)
    with patch("services.cache.redis.from_url", return_value=mock_redis):
        await cache.initialize()

    result = await cache.get_json("nonexistent")
    assert result is None


async def test_set_json_serialises_and_stores(cache, mock_redis):
    with patch("services.cache.redis.from_url", return_value=mock_redis):
        await cache.initialize()

    data = {"key": "value", "num": 42}
    result = await cache.set_json("my:key", data, ex=600)
    assert result is True
    mock_redis.set.assert_awaited_with("my:key", json.dumps(data), ex=600)


# ── close ────────────────────────────────────────────────────────────

async def test_close_delegates_to_redis(cache, mock_redis):
    with patch("services.cache.redis.from_url", return_value=mock_redis):
        await cache.initialize()

    await cache.close()
    mock_redis.close.assert_awaited_once()


async def test_close_noop_when_unavailable(cache):
    """close() does not raise when Redis was never connected."""
    await cache.close()  # should not raise
