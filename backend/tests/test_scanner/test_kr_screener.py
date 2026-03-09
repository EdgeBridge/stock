"""Tests for Korean stock screener."""

import pytest
from unittest.mock import patch, MagicMock
import pandas as pd

from scanner.kr_screener import KRScreener, _get_latest_trading_date


class TestGetLatestTradingDate:
    @patch("scanner.kr_screener.datetime")
    def test_weekday(self, mock_dt):
        mock_dt.now.return_value = MagicMock(
            hour=17, weekday=MagicMock(return_value=2),  # Wednesday
            strftime=MagicMock(return_value="20260309"),
        )
        mock_dt.now.return_value.__sub__ = MagicMock()
        # Just verify it doesn't crash
        result = _get_latest_trading_date()
        assert isinstance(result, str)
        assert len(result) == 8


class TestKRScreener:
    def test_init_defaults(self):
        s = KRScreener()
        assert s._max_per_source == 20
        assert s._max_total == 60

    @patch("scanner.kr_screener.pykrx_stock")
    def test_screen_by_market_cap(self, mock_stock):
        df = pd.DataFrame(
            {"시가총액": [1_000_000_000_000, 800_000_000_000, 200_000_000_000],
             "거래대금": [50_000_000_000, 30_000_000_000, 5_000_000_000]},
            index=["005930", "000660", "999999"],
        )
        mock_stock.get_market_cap.return_value = df

        screener = KRScreener(min_market_cap=500_000_000_000)
        result = screener._screen_by_market_cap("20260309", "KOSPI")
        assert result == ["005930", "000660"]

    @patch("scanner.kr_screener.pykrx_stock")
    def test_screen_by_trading_value(self, mock_stock):
        df = pd.DataFrame(
            {"시가총액": [1_000_000_000_000, 800_000_000_000],
             "거래대금": [50_000_000_000, 30_000_000_000]},
            index=["005930", "000660"],
        )
        mock_stock.get_market_cap.return_value = df

        screener = KRScreener(min_trading_value=20_000_000_000)
        result = screener._screen_by_trading_value("20260309", "KOSPI")
        assert "005930" in result
        assert "000660" in result

    @patch("scanner.kr_screener.pykrx_stock")
    def test_screen_value_stocks(self, mock_stock):
        df = pd.DataFrame(
            {"PER": [8.5, 25.0, -3.0, 12.0],
             "PBR": [0.8, 3.5, 1.2, 1.5],
             "EPS": [5000, 2000, -500, 3000],
             "BPS": [50000, 20000, 30000, 25000],
             "DIV": [3.5, 0.5, 0.0, 2.0],
             "DPS": [2000, 500, 0, 1000]},
            index=["005930", "AAAA", "BBBB", "CCCC"],
        )
        mock_stock.get_market_fundamental.return_value = df

        screener = KRScreener()
        result = screener._screen_value_stocks("20260309", "KOSPI")
        # 005930 (PER=8.5, PBR=0.8, DIV=3.5) and CCCC (PER=12, PBR=1.5, DIV=2.0) qualify
        assert "005930" in result
        assert "CCCC" in result
        assert "AAAA" not in result  # PER=25 too high
        assert "BBBB" not in result  # negative PER

    @patch("scanner.kr_screener.pykrx_stock")
    def test_screen_deduplicates(self, mock_stock):
        # Same stock appears in both market cap and trading value
        df = pd.DataFrame(
            {"시가총액": [1_000_000_000_000],
             "거래대금": [50_000_000_000]},
            index=["005930"],
        )
        mock_stock.get_market_cap.return_value = df
        mock_stock.get_market_fundamental.return_value = pd.DataFrame()

        screener = KRScreener(min_market_cap=500_000_000_000, min_trading_value=20_000_000_000)
        result = screener.screen("20260309", ["KOSPI"])
        assert result.symbols.count("005930") == 1

    @patch("scanner.kr_screener.pykrx_stock")
    def test_screen_empty_market(self, mock_stock):
        mock_stock.get_market_cap.return_value = pd.DataFrame()
        mock_stock.get_market_fundamental.return_value = pd.DataFrame()

        screener = KRScreener()
        result = screener.screen("20260309", ["KOSPI"])
        assert result.symbols == []
