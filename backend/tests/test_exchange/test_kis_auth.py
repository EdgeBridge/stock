"""Unit tests for KIS Auth token management."""

import json
import time

import pytest
import pytest_asyncio
from aioresponses import aioresponses

from exchange.kis_auth import KISAuth, TOKEN_VALIDITY_SEC


BASE_URL = "https://openapivts.koreainvestment.com:29443"


@pytest_asyncio.fixture
async def auth():
    a = KISAuth(
        app_key="test_app_key",
        app_secret="test_app_secret",
        base_url=BASE_URL,
    )
    yield a
    await a.close()


@pytest.mark.asyncio
async def test_issue_token(auth):
    with aioresponses() as m:
        m.post(
            f"{BASE_URL}/oauth2/tokenP",
            payload={
                "access_token": "mock_token_123",
                "token_type": "Bearer",
                "expires_in": 86400,
            },
        )
        await auth.initialize()

    assert auth.access_token == "mock_token_123"


@pytest.mark.asyncio
async def test_token_failure_raises(auth):
    with aioresponses() as m:
        m.post(
            f"{BASE_URL}/oauth2/tokenP",
            payload={"error": "invalid_client"},
        )
        with pytest.raises(RuntimeError, match="KIS token issuance failed"):
            await auth.initialize()


@pytest.mark.asyncio
async def test_get_auth_headers(auth):
    with aioresponses() as m:
        m.post(
            f"{BASE_URL}/oauth2/tokenP",
            payload={"access_token": "tok_abc"},
        )
        await auth.initialize()

    headers = auth.get_auth_headers("TTTT1002U")
    assert headers["authorization"] == "Bearer tok_abc"
    assert headers["tr_id"] == "TTTT1002U"
    assert headers["appkey"] == "test_app_key"
    assert headers["custtype"] == "P"


@pytest.mark.asyncio
async def test_get_auth_headers_with_hashkey(auth):
    with aioresponses() as m:
        m.post(f"{BASE_URL}/oauth2/tokenP", payload={"access_token": "tok"})
        await auth.initialize()

    headers = auth.get_auth_headers("TTTT1002U", hashkey="hash123")
    assert headers["hashkey"] == "hash123"


@pytest.mark.asyncio
async def test_get_approval_key(auth):
    with aioresponses() as m:
        m.post(f"{BASE_URL}/oauth2/tokenP", payload={"access_token": "tok"})
        m.post(f"{BASE_URL}/oauth2/Approval", payload={"approval_key": "ws_key_456"})
        await auth.initialize()

        key = await auth.get_approval_key()
        assert key == "ws_key_456"

        # Second call returns cached (no extra mock needed)
        key2 = await auth.get_approval_key()
        assert key2 == "ws_key_456"


@pytest.mark.asyncio
async def test_get_hashkey(auth):
    with aioresponses() as m:
        m.post(f"{BASE_URL}/oauth2/tokenP", payload={"access_token": "tok"})
        m.post(f"{BASE_URL}/uapi/hashkey", payload={"HASH": "hash_xyz"})
        await auth.initialize()

        result = await auth.get_hashkey({"CANO": "12345678"})
        assert result == "hash_xyz"


@pytest.mark.asyncio
async def test_should_refresh_before_expiry(auth):
    with aioresponses() as m:
        m.post(f"{BASE_URL}/oauth2/tokenP", payload={"access_token": "tok"})
        await auth.initialize()

    # Token just issued, should not refresh
    assert auth._should_refresh() is False

    # Simulate near expiry
    auth._token_expires_at = time.time() + 1800  # 30 min left
    assert auth._should_refresh() is True


@pytest.mark.asyncio
async def test_access_token_before_init_raises(auth):
    with pytest.raises(RuntimeError, match="not initialized"):
        _ = auth.access_token
