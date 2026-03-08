"""Tests for API authentication middleware."""

import pytest
from httpx import AsyncClient, ASGITransport

from main import app


@pytest.fixture
def api_token():
    return "test-secret-token-12345"


def _set_token(token: str):
    """Set auth token on app state."""
    app.state.config = type("C", (), {
        "auth": type("A", (), {"api_token": token})()
    })()


class TestAuthMiddleware:
    """Test Bearer token authentication."""

    async def test_health_endpoint_no_auth_required(self, api_token):
        """Health endpoint should work without auth even when token is set."""
        _set_token(api_token)
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/health")
            assert resp.status_code == 200

    async def test_api_blocked_without_token(self, api_token):
        """API endpoints should return 401 without auth when token is set."""
        _set_token(api_token)
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/api/v1/portfolio/summary")
            assert resp.status_code == 401

    async def test_api_allowed_with_valid_token(self, api_token):
        """API endpoints should not get 401 with correct Bearer token."""
        _set_token(api_token)
        transport = ASGITransport(app=app, raise_app_exceptions=False)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get(
                "/api/v1/portfolio/summary",
                headers={"Authorization": f"Bearer {api_token}"},
            )
            # May get 500 (missing app.state.market_data) but NOT 401
            assert resp.status_code != 401

    async def test_api_rejected_with_wrong_token(self, api_token):
        """API endpoints should reject wrong Bearer token."""
        _set_token(api_token)
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get(
                "/api/v1/portfolio/summary",
                headers={"Authorization": "Bearer wrong-token"},
            )
            assert resp.status_code == 401

    async def test_no_auth_when_token_empty(self):
        """Auth should be disabled when API_TOKEN is empty."""
        _set_token("")
        transport = ASGITransport(app=app, raise_app_exceptions=False)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/api/v1/portfolio/summary")
            # Should NOT be 401 (may be other error due to missing state)
            assert resp.status_code != 401
