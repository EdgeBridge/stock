"""Tests for StockScanner."""

from unittest.mock import AsyncMock, MagicMock

import pandas as pd
import pytest

from scanner.stock_scanner import StockScanner, ScanResult


@pytest.fixture
def mock_market_data():
    return AsyncMock()


def _make_df(prices, volumes, n=30):
    """Create a simple OHLCV DataFrame with n rows."""
    if len(prices) < n:
        prices = [prices[0]] * (n - len(prices)) + prices
    if len(volumes) < n:
        volumes = [volumes[0]] * (n - len(volumes)) + volumes
    data = {
        "open": prices,
        "high": [p * 1.01 for p in prices],
        "low": [p * 0.99 for p in prices],
        "close": prices,
        "volume": volumes,
    }
    return pd.DataFrame(data)


class TestScanVolumeSurges:
    @pytest.mark.asyncio
    async def test_detects_volume_surge(self, mock_market_data):
        # 20 bars of low volume, then 1 bar of high volume
        prices = [100.0] * 30
        volumes = [500_000] * 29 + [2_000_000]  # 4x surge on last bar
        mock_market_data.get_ohlcv = AsyncMock(return_value=_make_df(prices, volumes))

        scanner = StockScanner(market_data=mock_market_data)
        results = await scanner.scan_volume_surges(["AAPL"])

        assert len(results) == 1
        assert results[0].symbol == "AAPL"
        assert results[0].scan_type == "volume_surge"
        assert results[0].metadata["volume_ratio"] >= 2.0

    @pytest.mark.asyncio
    async def test_ignores_low_volume(self, mock_market_data):
        prices = [100.0] * 30
        volumes = [500_000] * 30  # No surge
        mock_market_data.get_ohlcv = AsyncMock(return_value=_make_df(prices, volumes))

        scanner = StockScanner(market_data=mock_market_data)
        results = await scanner.scan_volume_surges(["AAPL"])
        assert len(results) == 0

    @pytest.mark.asyncio
    async def test_empty_watchlist(self, mock_market_data):
        scanner = StockScanner(market_data=mock_market_data)
        results = await scanner.scan_volume_surges([])
        assert results == []

    @pytest.mark.asyncio
    async def test_no_market_data(self):
        scanner = StockScanner()
        results = await scanner.scan_volume_surges(["AAPL"])
        assert results == []


class TestScanTopGainers:
    @pytest.mark.asyncio
    async def test_detects_gainer(self, mock_market_data):
        prices = [100.0, 100.0, 100.0, 100.0, 105.0]  # +5%
        volumes = [1_000_000] * 5
        mock_market_data.get_ohlcv = AsyncMock(return_value=_make_df(prices, volumes, n=5))

        scanner = StockScanner(market_data=mock_market_data, min_volume=0)
        results = await scanner.scan_top_gainers(["AAPL"])
        assert len(results) == 1
        assert results[0].change_pct > 2.0
        assert results[0].scan_type == "top_gainer"

    @pytest.mark.asyncio
    async def test_ignores_small_move(self, mock_market_data):
        prices = [100.0, 100.0, 100.0, 100.0, 101.0]  # +1% (below 2% threshold)
        volumes = [1_000_000] * 5
        mock_market_data.get_ohlcv = AsyncMock(return_value=_make_df(prices, volumes, n=5))

        scanner = StockScanner(market_data=mock_market_data, min_volume=0)
        results = await scanner.scan_top_gainers(["AAPL"])
        assert len(results) == 0


class TestScanTopLosers:
    @pytest.mark.asyncio
    async def test_detects_loser(self, mock_market_data):
        prices = [100.0, 100.0, 100.0, 100.0, 95.0]  # -5%
        volumes = [1_000_000] * 5
        mock_market_data.get_ohlcv = AsyncMock(return_value=_make_df(prices, volumes, n=5))

        scanner = StockScanner(market_data=mock_market_data, min_volume=0)
        results = await scanner.scan_top_losers(["AAPL"])
        assert len(results) == 1
        assert results[0].change_pct < -2.0
        assert results[0].scan_type == "top_loser"


class TestScanNewHighs:
    @pytest.mark.asyncio
    async def test_detects_near_52w_high(self, mock_market_data):
        # Gradually rising prices with current near the top
        prices = list(range(50, 50 + 252))  # 50 to 301
        volumes = [1_000_000] * 252
        mock_market_data.get_ohlcv = AsyncMock(return_value=_make_df(prices, volumes, n=252))

        scanner = StockScanner(market_data=mock_market_data, min_volume=0, min_price=0, max_price=1000)
        results = await scanner.scan_new_highs(["AAPL"])
        assert len(results) == 1
        assert results[0].scan_type == "new_high"
        assert results[0].metadata["52w_position"] >= 0.90

    @pytest.mark.asyncio
    async def test_ignores_low_position(self, mock_market_data):
        # Price at bottom of range
        prices = list(range(300, 300 - 252, -1))  # Declining
        volumes = [1_000_000] * 252
        mock_market_data.get_ohlcv = AsyncMock(return_value=_make_df(prices, volumes, n=252))

        scanner = StockScanner(market_data=mock_market_data, min_volume=0, min_price=0, max_price=1000)
        results = await scanner.scan_new_highs(["AAPL"])
        assert len(results) == 0


class TestRunAllScans:
    @pytest.mark.asyncio
    async def test_combines_results(self, mock_market_data):
        # Set up data that triggers volume surge and new high
        prices = list(range(50, 50 + 252))
        volumes = [500_000] * 251 + [2_000_000]
        mock_market_data.get_ohlcv = AsyncMock(return_value=_make_df(prices, volumes, n=252))

        scanner = StockScanner(
            market_data=mock_market_data,
            min_volume=0, min_price=0, max_price=1000,
        )
        summary = await scanner.run_all_scans(["AAPL"])
        assert summary.total_found >= 1
        assert summary.scan_time
        assert scanner.last_scan is summary

    @pytest.mark.asyncio
    async def test_deduplicates_by_symbol(self, mock_market_data):
        prices = list(range(50, 50 + 252))
        volumes = [500_000] * 251 + [2_000_000]
        mock_market_data.get_ohlcv = AsyncMock(return_value=_make_df(prices, volumes, n=252))

        scanner = StockScanner(
            market_data=mock_market_data,
            min_volume=0, min_price=0, max_price=1000,
        )
        summary = await scanner.run_all_scans(["AAPL"])
        symbols = [r.symbol for r in summary.results]
        assert len(symbols) == len(set(symbols))  # No duplicates

    @pytest.mark.asyncio
    async def test_empty_watchlist(self, mock_market_data):
        scanner = StockScanner(market_data=mock_market_data)
        summary = await scanner.run_all_scans([])
        assert summary.total_found == 0


class TestFilters:
    @pytest.mark.asyncio
    async def test_min_price_filter(self, mock_market_data):
        prices = [3.0, 3.0, 3.0, 3.0, 3.5]  # Below min_price=5
        volumes = [1_000_000] * 5
        mock_market_data.get_ohlcv = AsyncMock(return_value=_make_df(prices, volumes, n=5))

        scanner = StockScanner(market_data=mock_market_data, min_price=5.0)
        results = await scanner.scan_top_gainers(["PENNY"])
        assert len(results) == 0

    @pytest.mark.asyncio
    async def test_max_price_filter(self, mock_market_data):
        prices = [600.0, 600.0, 600.0, 600.0, 650.0]  # Above max_price=500
        volumes = [1_000_000] * 5
        mock_market_data.get_ohlcv = AsyncMock(return_value=_make_df(prices, volumes, n=5))

        scanner = StockScanner(market_data=mock_market_data, max_price=500.0)
        results = await scanner.scan_top_gainers(["HIGH"])
        assert len(results) == 0


class TestGetSymbols:
    @pytest.mark.asyncio
    async def test_returns_symbols_from_last_scan(self, mock_market_data):
        prices = list(range(50, 50 + 252))
        volumes = [500_000] * 251 + [2_000_000]
        mock_market_data.get_ohlcv = AsyncMock(return_value=_make_df(prices, volumes, n=252))

        scanner = StockScanner(
            market_data=mock_market_data,
            min_volume=0, min_price=0, max_price=1000,
        )
        await scanner.run_all_scans(["AAPL", "MSFT"])
        symbols = scanner.get_symbols()
        assert isinstance(symbols, list)

    def test_returns_empty_before_scan(self):
        scanner = StockScanner()
        assert scanner.get_symbols() == []
