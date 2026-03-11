"""Tests for earnings calendar service."""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from datetime import date, timedelta

from data.earnings_service import EarningsCalendarService, EarningsEvent


class TestEarningsEvent:
    def test_to_dict(self):
        e = EarningsEvent(
            symbol="AAPL", date="2026-03-15", hour="amc",
            eps_estimate=1.50, revenue_estimate=94_000_000_000,
        )
        d = e.to_dict()
        assert d["symbol"] == "AAPL"
        assert d["date"] == "2026-03-15"
        assert d["hour"] == "amc"
        assert d["eps_estimate"] == 1.50


class TestEarningsCalendarService:
    def test_not_available_without_key(self):
        svc = EarningsCalendarService(api_key="")
        assert svc.available is False

    def test_available_with_key(self):
        svc = EarningsCalendarService(api_key="test_key")
        assert svc.available is True

    @pytest.mark.asyncio
    async def test_fetch_earnings_no_key(self):
        svc = EarningsCalendarService(api_key="")
        result = await svc.fetch_earnings("2026-03-01", "2026-03-15")
        assert result == []

    @pytest.mark.asyncio
    async def test_fetch_earnings_success(self):
        svc = EarningsCalendarService(api_key="test")
        mock_resp = AsyncMock()
        mock_resp.status = 200
        mock_resp.json = AsyncMock(return_value={
            "earningsCalendar": [
                {
                    "symbol": "AAPL",
                    "date": "2026-03-15",
                    "hour": "amc",
                    "epsEstimate": 1.50,
                    "epsActual": None,
                    "revenueEstimate": 94e9,
                    "revenueActual": None,
                    "quarter": 1,
                    "year": 2026,
                }
            ]
        })
        mock_resp.__aenter__ = AsyncMock(return_value=mock_resp)
        mock_resp.__aexit__ = AsyncMock(return_value=None)

        mock_session = AsyncMock()
        mock_session.closed = False
        mock_session.get = MagicMock(return_value=mock_resp)
        svc._session = mock_session

        result = await svc.fetch_earnings("2026-03-01", "2026-03-31")
        assert len(result) == 1
        assert result[0].symbol == "AAPL"
        assert result[0].eps_estimate == 1.50

    @pytest.mark.asyncio
    async def test_fetch_earnings_http_error(self):
        svc = EarningsCalendarService(api_key="test")
        mock_resp = AsyncMock()
        mock_resp.status = 429
        mock_resp.__aenter__ = AsyncMock(return_value=mock_resp)
        mock_resp.__aexit__ = AsyncMock(return_value=None)

        mock_session = AsyncMock()
        mock_session.closed = False
        mock_session.get = MagicMock(return_value=mock_resp)
        svc._session = mock_session

        result = await svc.fetch_earnings("2026-03-01", "2026-03-31")
        assert result == []

    def test_has_earnings_within(self):
        svc = EarningsCalendarService(api_key="test")
        today = date.today()
        tomorrow = (today + timedelta(days=1)).isoformat()
        svc._cache = {
            "AAPL": [EarningsEvent(symbol="AAPL", date=tomorrow, hour="amc")],
        }
        assert svc.has_earnings_within("AAPL", 3) is True
        assert svc.has_earnings_within("MSFT", 3) is False

    def test_has_earnings_within_past(self):
        svc = EarningsCalendarService(api_key="test")
        past = (date.today() - timedelta(days=5)).isoformat()
        svc._cache = {
            "AAPL": [EarningsEvent(symbol="AAPL", date=past, hour="amc")],
        }
        assert svc.has_earnings_within("AAPL", 3) is False

    def test_get_sl_multiplier(self):
        svc = EarningsCalendarService(api_key="test")
        tomorrow = (date.today() + timedelta(days=1)).isoformat()
        svc._cache = {
            "AAPL": [EarningsEvent(symbol="AAPL", date=tomorrow, hour="amc")],
        }
        assert svc.get_sl_multiplier("AAPL") == 1.5
        assert svc.get_sl_multiplier("MSFT") is None

    def test_to_dict(self):
        svc = EarningsCalendarService(api_key="test")
        svc._cache = {
            "AAPL": [EarningsEvent(symbol="AAPL", date="2026-03-15", hour="amc")],
        }
        result = svc.to_dict()
        assert len(result) == 1
        assert result[0]["symbol"] == "AAPL"
