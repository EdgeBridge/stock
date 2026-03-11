"""Tests for insider trading service."""

import pytest
from unittest.mock import AsyncMock, MagicMock

from data.insider_service import InsiderTradingService, InsiderTransaction


class TestInsiderTransaction:
    def test_value_calculation(self):
        t = InsiderTransaction(
            symbol="AAPL", name="Tim Cook", share=100000,
            change=5000, filing_date="2026-03-10",
            transaction_date="2026-03-08", transaction_code="P",
            transaction_price=150.0,
        )
        assert t.value == 750_000.0
        assert t.is_purchase is True
        assert t.is_sale is False

    def test_sale(self):
        t = InsiderTransaction(
            symbol="AAPL", name="CFO", share=50000,
            change=-10000, filing_date="2026-03-10",
            transaction_date="2026-03-08", transaction_code="S",
            transaction_price=150.0,
        )
        assert t.value == 1_500_000.0
        assert t.is_purchase is False
        assert t.is_sale is True

    def test_value_no_price(self):
        t = InsiderTransaction(
            symbol="AAPL", name="X", share=0, change=100,
            filing_date="", transaction_date="",
            transaction_code="P", transaction_price=None,
        )
        assert t.value == 0.0

    def test_to_dict(self):
        t = InsiderTransaction(
            symbol="AAPL", name="Tim Cook", share=100000,
            change=5000, filing_date="2026-03-10",
            transaction_date="2026-03-08", transaction_code="P",
            transaction_price=150.0,
        )
        d = t.to_dict()
        assert d["symbol"] == "AAPL"
        assert d["value"] == 750_000.0


class TestInsiderTradingService:
    def test_not_available_without_key(self):
        svc = InsiderTradingService(api_key="")
        assert svc.available is False

    def test_signal_adjustment_large_purchase(self):
        svc = InsiderTradingService(api_key="test")
        svc._cache = {
            "AAPL": [
                InsiderTransaction(
                    symbol="AAPL", name="CEO", share=100000,
                    change=5000, filing_date="2026-03-10",
                    transaction_date="2026-03-08",
                    transaction_code="P", transaction_price=150.0,
                ),  # $750k > $500k threshold
            ]
        }
        assert svc.get_signal_adjustment("AAPL") == 0.10

    def test_signal_adjustment_large_sale(self):
        svc = InsiderTradingService(api_key="test")
        svc._cache = {
            "AAPL": [
                InsiderTransaction(
                    symbol="AAPL", name="CFO", share=50000,
                    change=-10000, filing_date="2026-03-10",
                    transaction_date="2026-03-08",
                    transaction_code="S", transaction_price=150.0,
                ),  # $1.5M > $1M threshold
            ]
        }
        assert svc.get_signal_adjustment("AAPL") == -0.10

    def test_signal_adjustment_no_data(self):
        svc = InsiderTradingService(api_key="test")
        assert svc.get_signal_adjustment("AAPL") == 0.0

    def test_signal_adjustment_small_trade(self):
        svc = InsiderTradingService(api_key="test")
        svc._cache = {
            "AAPL": [
                InsiderTransaction(
                    symbol="AAPL", name="VP", share=1000,
                    change=100, filing_date="2026-03-10",
                    transaction_date="2026-03-08",
                    transaction_code="P", transaction_price=150.0,
                ),  # $15k < $500k threshold
            ]
        }
        assert svc.get_signal_adjustment("AAPL") == 0.0

    def test_get_notable_bullish(self):
        svc = InsiderTradingService(api_key="test")
        svc._cache = {
            "AAPL": [
                InsiderTransaction(
                    symbol="AAPL", name="CEO", share=100000,
                    change=5000, filing_date="2026-03-10",
                    transaction_date="2026-03-08",
                    transaction_code="P", transaction_price=150.0,
                ),
            ]
        }
        notable = svc.get_notable()
        assert len(notable) == 1
        assert notable[0]["signal"] == "BULLISH"
        assert notable[0]["top_buyer"] == "CEO"

    @pytest.mark.asyncio
    async def test_fetch_success(self):
        svc = InsiderTradingService(api_key="test")
        mock_resp = AsyncMock()
        mock_resp.status = 200
        mock_resp.json = AsyncMock(return_value={
            "data": [
                {
                    "name": "Tim Cook",
                    "share": 100000,
                    "change": 5000,
                    "filingDate": "2026-03-10",
                    "transactionDate": "2026-03-08",
                    "transactionCode": "P",
                    "transactionPrice": 150.0,
                },
                {
                    "name": "VP",
                    "share": 1000,
                    "change": 100,
                    "filingDate": "2026-03-10",
                    "transactionDate": "2026-03-08",
                    "transactionCode": "M",  # Exercise — should be filtered
                    "transactionPrice": 50.0,
                },
            ]
        })

        mock_resp.__aenter__ = AsyncMock(return_value=mock_resp)
        mock_resp.__aexit__ = AsyncMock(return_value=None)

        mock_session = AsyncMock()
        mock_session.closed = False
        mock_session.get = MagicMock(return_value=mock_resp)
        svc._session = mock_session

        result = await svc.fetch_insider_transactions("AAPL")
        assert len(result) == 1  # Only P/S, not M
        assert result[0].name == "Tim Cook"
