"""Tests for Korean stock screener (yfinance-based)."""

import pytest
from unittest.mock import patch, MagicMock

from scanner.kr_screener import KRScreener, _KR_UNIVERSE, KRScreenResult


class TestKRScreener:
    def test_init_defaults(self):
        s = KRScreener()
        assert s._max_per_source == 20
        assert s._max_total == 60

    def test_screen_returns_curated_universe(self):
        """Screen always includes curated stocks."""
        s = KRScreener()
        # Bypass yfinance screening by mocking
        with patch.object(s, "_screen_by_yfinance", return_value=[]):
            result = s.screen()
            assert result.total_discovered > 0
            assert "curated" in result.sources
            # Should include major stocks from universe
            assert "005930" in result.symbols  # Samsung

    @patch("scanner.kr_screener.yf")
    def test_screen_by_yfinance_filters(self, mock_yf):
        """yfinance screening filters by market cap and volume."""
        # Mock fast_info for Samsung
        mock_info = MagicMock()
        mock_info.market_cap = 1_000_000_000_000_000  # 1000조
        mock_info.three_month_average_volume = 10_000_000
        mock_ticker = MagicMock()
        mock_ticker.fast_info = mock_info
        mock_yf.Ticker.return_value = mock_ticker

        s = KRScreener(min_market_cap=500_000_000_000)
        result = s._screen_by_yfinance(["005930"])
        assert "005930" in result

    @patch("scanner.kr_screener.yf")
    def test_screen_by_yfinance_excludes_small(self, mock_yf):
        """yfinance screening excludes stocks below thresholds."""
        mock_info = MagicMock()
        mock_info.market_cap = 100_000_000_000  # 1000억 (below 5000억)
        mock_info.three_month_average_volume = 50_000
        mock_ticker = MagicMock()
        mock_ticker.fast_info = mock_info
        mock_yf.Ticker.return_value = mock_ticker

        s = KRScreener(min_market_cap=500_000_000_000)
        result = s._screen_by_yfinance(["999999"])
        assert result == []

    def test_screen_deduplicates(self):
        """Screen deduplicates symbols from multiple sources."""
        s = KRScreener()
        with patch.object(s, "_screen_by_yfinance", return_value=["005930", "000660"]):
            result = s.screen()
            # 005930 should appear once even though it's in both curated and screened
            assert result.symbols.count("005930") == 1

    def test_curated_universe_has_stocks(self):
        """Curated universe includes major Korean stocks."""
        symbols = [s[0] for s in _KR_UNIVERSE]
        assert "005930" in symbols  # Samsung
        assert "000660" in symbols  # SK Hynix
        assert "035420" in symbols  # NAVER
        assert len(symbols) >= 30

    def test_screen_respects_max_total(self):
        """Screen limits total symbols."""
        s = KRScreener(max_total=5)
        with patch.object(s, "_screen_by_yfinance", return_value=[]):
            result = s.screen()
            assert len(result.symbols) <= 5

    def test_get_exchange(self):
        s = KRScreener()
        assert s._get_exchange("005930") == "KRX"
        assert s._get_exchange("247540") == "KOSDAQ"
        assert s._get_exchange("999999") == "KRX"  # default

    def test_screen_backward_compat(self):
        """screen() accepts date and markets kwargs without error."""
        s = KRScreener()
        with patch.object(s, "_screen_by_yfinance", return_value=[]):
            result = s.screen(date="20260309", markets=["KOSPI"])
            assert isinstance(result, KRScreenResult)
