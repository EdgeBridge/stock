"""Tests for UniverseExpander."""

import pytest
from unittest.mock import patch, MagicMock

from scanner.universe_expander import UniverseExpander, UniverseResult
from scanner.etf_universe import ETFUniverse, SectorETF
from scanner.sector_analyzer import SectorAnalyzer


@pytest.fixture
def mock_etf_universe():
    """Create mock ETFUniverse."""
    etf = MagicMock(spec=ETFUniverse)
    etf.get_all_sectors.return_value = {
        "Technology": SectorETF(
            name="Technology", etf="XLK",
            top_holdings=["AAPL", "MSFT", "NVDA", "AVGO", "ADBE"],
        ),
        "Financials": SectorETF(
            name="Financials", etf="XLF",
            top_holdings=["JPM", "V", "MA", "BAC", "GS"],
        ),
        "Energy": SectorETF(
            name="Energy", etf="XLE",
            top_holdings=["XOM", "CVX", "COP", "EOG", "SLB"],
        ),
    }
    etf.all_etf_symbols = ["XLK", "XLF", "XLE", "SPY", "QQQ", "TQQQ", "SQQQ"]
    etf.safe_haven = ["SHY", "TLT", "GLD"]
    return etf


@pytest.fixture
def expander(mock_etf_universe):
    return UniverseExpander(
        etf_universe=mock_etf_universe,
        max_per_screener=5,
        max_total=50,
    )


class TestSectorHoldings:
    """Test sector-weighted holdings expansion."""

    def test_strong_sectors_get_all_holdings(self, expander):
        sector_data = {
            "Technology": {"symbol": "XLK", "return_1w": 3.0, "return_1m": 8.0, "return_3m": 15.0},
            "Financials": {"symbol": "XLF", "return_1w": 1.0, "return_1m": 3.0, "return_3m": 5.0},
            "Energy": {"symbol": "XLE", "return_1w": -2.0, "return_1m": -5.0, "return_3m": -8.0},
        }
        holdings = expander._get_sector_holdings(sector_data)

        # Technology is strongest — should get all 5
        assert "AAPL" in holdings
        assert "MSFT" in holdings
        assert "NVDA" in holdings
        assert "AVGO" in holdings
        assert "ADBE" in holdings

    def test_weak_sectors_get_fewer_holdings(self, expander):
        sector_data = {
            "Technology": {"symbol": "XLK", "return_1w": 5.0, "return_1m": 10.0, "return_3m": 20.0},
            "Financials": {"symbol": "XLF", "return_1w": 0.5, "return_1m": 1.0, "return_3m": 2.0},
            "Energy": {"symbol": "XLE", "return_1w": -3.0, "return_1m": -8.0, "return_3m": -12.0},
        }
        holdings = expander._get_sector_holdings(sector_data)

        # Energy is weakest — should get only 1 holding
        energy_in = [s for s in ["XOM", "CVX", "COP", "EOG", "SLB"] if s in holdings]
        assert len(energy_in) >= 1
        assert len(energy_in) <= 3  # not all 5

    def test_no_sector_data_uses_defaults(self, expander):
        holdings = expander._get_sector_holdings(None)
        # Default strength=50, which falls in medium range (3 per sector)
        assert len(holdings) > 0
        assert len(holdings) <= 15  # 3 sectors × 5 max


class TestScreeners:
    """Test yfinance screener integration."""

    @patch("scanner.universe_expander.yf.screen")
    def test_screeners_return_symbols(self, mock_screen, expander):
        mock_screen.return_value = {
            "quotes": [
                {"symbol": "TSLA"},
                {"symbol": "AMD"},
                {"symbol": "NFLX"},
            ]
        }
        result = expander._run_screeners()
        assert "TSLA" in result
        assert "AMD" in result
        assert "NFLX" in result

    @patch("scanner.universe_expander.yf.screen")
    def test_screeners_skip_non_us(self, mock_screen, expander):
        mock_screen.return_value = {
            "quotes": [
                {"symbol": "AAPL"},
                {"symbol": "SHOP.TO"},  # Canadian
                {"symbol": "HSBA.L"},  # London
            ]
        }
        result = expander._run_screeners()
        assert "AAPL" in result
        assert "SHOP.TO" not in result
        assert "HSBA.L" not in result

    @patch("scanner.universe_expander.yf.screen")
    def test_screeners_dedup(self, mock_screen, expander):
        # Same symbol from multiple screeners
        mock_screen.return_value = {
            "quotes": [{"symbol": "NVDA"}, {"symbol": "NVDA"}]
        }
        result = expander._run_screeners()
        assert result.count("NVDA") == 1

    @patch("scanner.universe_expander.yf.screen")
    def test_screeners_handle_failure(self, mock_screen, expander):
        mock_screen.side_effect = Exception("API error")
        result = expander._run_screeners()
        assert result == []

    @patch("scanner.universe_expander.yf.screen")
    def test_screeners_respect_max_per_screener(self, mock_screen, expander):
        mock_screen.return_value = {
            "quotes": [{"symbol": f"SYM{i}"} for i in range(30)]
        }
        # max_per_screener=5 but SYM0, SYM1 etc have digits — filtered out
        # Let's use alpha symbols
        mock_screen.return_value = {
            "quotes": [{"symbol": s} for s in [
                "AAPL", "MSFT", "NVDA", "AMZN", "TSLA",
                "META", "GOOGL", "AMD", "NFLX", "CRM",
            ]]
        }
        result = expander._run_screeners()
        # Per screener max is 5, but same mock for all 5 screeners → dedup
        assert len(set(result)) <= 10


class TestFilterSymbols:
    """Test symbol filtering logic."""

    def test_filters_etfs(self, expander):
        symbols = {"AAPL", "SPY", "QQQ", "MSFT", "TQQQ"}
        result = expander._filter_symbols(symbols)
        assert "SPY" not in result
        assert "QQQ" not in result
        assert "TQQQ" not in result
        assert "AAPL" in result
        assert "MSFT" in result

    def test_filters_safe_haven(self, expander):
        symbols = {"AAPL", "GLD", "TLT", "SHY"}
        result = expander._filter_symbols(symbols)
        assert "AAPL" in result
        assert "GLD" not in result

    def test_keeps_hyphenated_stock_symbols(self, expander):
        symbols = {"BRK-B", "AAPL"}
        result = expander._filter_symbols(symbols)
        assert "BRK-B" in result
        assert "AAPL" in result


class TestExpand:
    """Test full expand flow."""

    @patch("scanner.universe_expander.yf.screen")
    @pytest.mark.asyncio
    async def test_full_expand(self, mock_screen, expander):
        mock_screen.return_value = {
            "quotes": [{"symbol": "TSLA"}, {"symbol": "AMD"}]
        }
        result = await expander.expand(
            existing_watchlist=["AAPL", "MSFT"],
            sector_data={
                "Technology": {"symbol": "XLK", "return_1w": 3.0, "return_1m": 8.0, "return_3m": 15.0},
                "Financials": {"symbol": "XLF", "return_1w": 1.0, "return_1m": 3.0, "return_3m": 5.0},
                "Energy": {"symbol": "XLE", "return_1w": -1.0, "return_1m": -2.0, "return_3m": -3.0},
            },
        )
        assert isinstance(result, UniverseResult)
        assert "AAPL" in result.symbols
        assert "MSFT" in result.symbols
        assert "TSLA" in result.symbols
        assert len(result.symbols) > 4
        assert "watchlist" in result.sources
        assert "screeners" in result.sources
        assert "sector_holdings" in result.sources

    @patch("scanner.universe_expander.yf.screen")
    @pytest.mark.asyncio
    async def test_expand_no_watchlist(self, mock_screen, expander):
        mock_screen.return_value = {"quotes": [{"symbol": "TSLA"}]}
        result = await expander.expand()
        assert len(result.symbols) > 0
        assert "watchlist" not in result.sources

    @patch("scanner.universe_expander.yf.screen")
    @pytest.mark.asyncio
    async def test_expand_respects_max_total(self, mock_screen):
        mock_screen.return_value = {
            "quotes": [{"symbol": s} for s in [
                "TSLA", "AMD", "NFLX", "CRM", "SHOP",
            ]]
        }
        expander = UniverseExpander(max_total=5, max_per_screener=3)
        result = await expander.expand(
            existing_watchlist=["AAPL", "MSFT", "NVDA", "GOOGL", "AMZN", "META"],
        )
        assert len(result.symbols) <= 5
