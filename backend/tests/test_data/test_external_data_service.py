"""Tests for ExternalDataService (yfinance integration)."""

from unittest.mock import patch, MagicMock, PropertyMock

import pandas as pd
import pytest

from data.external_data_service import (
    ExternalDataService,
    StockProfile,
    ConsensusData,
    FundamentalData,
    SmartMoneyData,
    StockInfo,
)


def _mock_ticker_info():
    return {
        "shortName": "Apple Inc.",
        "sector": "Technology",
        "industry": "Consumer Electronics",
        "marketCap": 3_000_000_000_000,
        "beta": 1.2,
        "fiftyTwoWeekHigh": 200.0,
        "fiftyTwoWeekLow": 120.0,
        "averageVolume": 50_000_000,
        "revenueGrowth": 0.08,
        "earningsGrowth": 0.15,
        "profitMargins": 0.25,
        "returnOnEquity": 0.45,
        "debtToEquity": 180.0,
        "freeCashflow": 100_000_000_000,
        "trailingPE": 28.0,
        "forwardPE": 25.0,
        "pegRatio": 1.5,
        "priceToSalesTrailing12Months": 7.5,
        "heldPercentInstitutions": 0.60,
        "shortRatio": 2.5,
    }


def _mock_recommendations():
    return pd.DataFrame([
        {"strongBuy": 10, "buy": 15, "hold": 8, "sell": 2, "strongSell": 1},
    ])


def _mock_price_targets():
    return {"mean": 200.0, "high": 250.0, "low": 160.0}


@pytest.fixture
def service():
    return ExternalDataService()


class TestStockProfile:
    @patch("data.external_data_service.yf.Ticker")
    async def test_get_stock_profile(self, mock_ticker_cls, service):
        mock_ticker = MagicMock()
        mock_ticker.info = _mock_ticker_info()
        mock_ticker.recommendations = _mock_recommendations()
        mock_ticker.analyst_price_targets = _mock_price_targets()
        mock_ticker.upgrades_downgrades = pd.DataFrame()
        mock_ticker.insider_transactions = pd.DataFrame()
        mock_ticker_cls.return_value = mock_ticker

        profile = await service.get_stock_profile("AAPL", current_price=175.0)

        assert profile.symbol == "AAPL"
        assert profile.info.name == "Apple Inc."
        assert profile.info.sector == "Technology"
        assert profile.info.market_cap == 3_000_000_000_000
        assert profile.fundamentals.pe_ratio == 28.0
        assert profile.fundamentals.revenue_growth == 0.08
        assert profile.consensus.target_mean == 200.0
        assert profile.consensus.target_upside_pct > 0  # 200/175 - 1

    @patch("data.external_data_service.yf.Ticker")
    async def test_get_stock_profile_api_failure(self, mock_ticker_cls, service):
        mock_ticker_cls.side_effect = Exception("Network error")

        profile = await service.get_stock_profile("AAPL")
        assert profile.symbol == "AAPL"
        assert profile.info.name == ""  # defaults

    @patch("data.external_data_service.yf.Ticker")
    async def test_consensus_analyst_count(self, mock_ticker_cls, service):
        mock_ticker = MagicMock()
        mock_ticker.info = _mock_ticker_info()
        mock_ticker.recommendations = _mock_recommendations()
        mock_ticker.analyst_price_targets = _mock_price_targets()
        mock_ticker.upgrades_downgrades = pd.DataFrame()
        mock_ticker.insider_transactions = pd.DataFrame()
        mock_ticker_cls.return_value = mock_ticker

        profile = await service.get_stock_profile("AAPL", current_price=175.0)
        # 10 + 15 + 8 + 2 + 1 = 36
        assert profile.consensus.analyst_count == 36
        assert profile.consensus.strong_buy == 10
        assert profile.consensus.buy == 15

    @patch("data.external_data_service.yf.Ticker")
    async def test_consensus_no_recommendations(self, mock_ticker_cls, service):
        mock_ticker = MagicMock()
        mock_ticker.info = _mock_ticker_info()
        mock_ticker.recommendations = None
        mock_ticker.analyst_price_targets = None
        mock_ticker.upgrades_downgrades = None
        mock_ticker.insider_transactions = None
        mock_ticker_cls.return_value = mock_ticker

        profile = await service.get_stock_profile("AAPL")
        assert profile.consensus.analyst_count == 0


class TestHistory:
    @patch("data.external_data_service.yf.Ticker")
    async def test_get_history(self, mock_ticker_cls, service):
        mock_ticker = MagicMock()
        mock_ticker.history.return_value = pd.DataFrame({
            "Open": [100.0, 101.0],
            "High": [102.0, 103.0],
            "Low": [99.0, 100.0],
            "Close": [101.0, 102.0],
            "Volume": [1_000_000, 1_100_000],
            "Stock Splits": [0, 0],
        })
        mock_ticker_cls.return_value = mock_ticker

        df = await service.get_history("AAPL", period="1mo")
        assert not df.empty
        assert "close" in df.columns
        assert "stock_splits" in df.columns

    @patch("data.external_data_service.yf.Ticker")
    async def test_get_history_empty(self, mock_ticker_cls, service):
        mock_ticker = MagicMock()
        mock_ticker.history.return_value = pd.DataFrame()
        mock_ticker_cls.return_value = mock_ticker

        df = await service.get_history("UNKNOWN")
        assert df.empty

    @patch("data.external_data_service.yf.Ticker")
    async def test_get_history_api_failure(self, mock_ticker_cls, service):
        mock_ticker = MagicMock()
        mock_ticker.history.side_effect = Exception("API error")
        mock_ticker_cls.return_value = mock_ticker

        df = await service.get_history("AAPL")
        assert df.empty


class TestMultipleProfiles:
    @patch("data.external_data_service.yf.Ticker")
    async def test_get_multiple_profiles(self, mock_ticker_cls, service):
        mock_ticker = MagicMock()
        mock_ticker.info = _mock_ticker_info()
        mock_ticker.recommendations = None
        mock_ticker.analyst_price_targets = None
        mock_ticker.upgrades_downgrades = None
        mock_ticker.insider_transactions = None
        mock_ticker_cls.return_value = mock_ticker

        profiles = await service.get_multiple_profiles(
            ["AAPL", "TSLA"],
            current_prices={"AAPL": 175.0, "TSLA": 250.0},
        )
        assert len(profiles) == 2
        assert profiles[0].symbol == "AAPL"
        assert profiles[1].symbol == "TSLA"


class TestSmartMoney:
    @patch("data.external_data_service.yf.Ticker")
    async def test_smart_money_data(self, mock_ticker_cls, service):
        mock_ticker = MagicMock()
        info = _mock_ticker_info()
        mock_ticker.info = info
        mock_ticker.recommendations = None
        mock_ticker.analyst_price_targets = None
        mock_ticker.upgrades_downgrades = None
        mock_ticker.insider_transactions = pd.DataFrame({
            "Transaction": ["Purchase", "Sale", "Purchase", "Sale"],
        })
        mock_ticker_cls.return_value = mock_ticker

        profile = await service.get_stock_profile("AAPL")
        assert profile.smart_money.institutional_pct == 0.60
        assert profile.smart_money.short_ratio == 2.5
        assert profile.smart_money.insider_buy_count_90d == 2
        assert profile.smart_money.insider_sell_count_90d == 2


class TestDataclassDefaults:
    def test_consensus_defaults(self):
        c = ConsensusData()
        assert c.analyst_count == 0
        assert c.target_mean == 0.0

    def test_fundamental_defaults(self):
        f = FundamentalData()
        assert f.pe_ratio is None
        assert f.revenue_growth is None

    def test_smart_money_defaults(self):
        s = SmartMoneyData()
        assert s.institutional_pct is None
        assert s.insider_buy_count_90d == 0

    def test_stock_info_defaults(self):
        i = StockInfo()
        assert i.symbol == ""
        assert i.market_cap == 0

    def test_stock_profile_defaults(self):
        p = StockProfile(symbol="TEST")
        assert p.symbol == "TEST"
        assert p.info.symbol == ""
        assert p.consensus.analyst_count == 0
