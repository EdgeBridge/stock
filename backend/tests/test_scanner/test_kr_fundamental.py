"""Tests for Korean fundamental enricher (yfinance-based)."""

import pytest
from unittest.mock import patch, MagicMock

from scanner.kr_fundamental_enricher import KRFundamentalEnricher, KRFundamentals


class TestKRFundamentals:
    def test_default_values(self):
        f = KRFundamentals(symbol="005930")
        assert f.per == 0.0
        assert f.pbr == 0.0
        assert f.dividend_yield == 0.0


class TestKRFundamentalEnricher:
    @patch("scanner.kr_fundamental_enricher.yf")
    def test_get_loads_data(self, mock_yf):
        mock_info = {
            "trailingPE": 10.5,
            "priceToBook": 1.2,
            "trailingEps": 5000,
            "bookValue": 50000,
            "dividendYield": 0.03,  # 3%
            "marketCap": 500_000_000_000_000,
            "currentPrice": 72300,
        }
        mock_ticker = MagicMock()
        mock_ticker.info = mock_info
        mock_yf.Ticker.return_value = mock_ticker

        enricher = KRFundamentalEnricher()
        result = enricher.get("005930")

        assert result is not None
        assert result.per == 10.5
        assert result.pbr == 1.2
        assert result.dividend_yield == 3.0
        assert result.market_cap == 500_000_000_000_000
        assert result.price == 72300

    @patch("scanner.kr_fundamental_enricher.yf")
    def test_get_missing_symbol(self, mock_yf):
        mock_yf.Ticker.side_effect = Exception("Not found")

        enricher = KRFundamentalEnricher()
        assert enricher.get("999999") is None

    @patch("scanner.kr_fundamental_enricher.yf")
    def test_get_caches_result(self, mock_yf):
        mock_info = {"trailingPE": 10, "priceToBook": 1, "dividendYield": 0.02,
                     "marketCap": 100e12, "currentPrice": 50000}
        mock_ticker = MagicMock()
        mock_ticker.info = mock_info
        mock_yf.Ticker.return_value = mock_ticker

        enricher = KRFundamentalEnricher()
        enricher.get("005930")
        enricher.get("005930")  # Should use cache
        assert mock_yf.Ticker.call_count == 1

    @patch("scanner.kr_fundamental_enricher.yf")
    def test_score_value_stock(self, mock_yf):
        mock_info = {"trailingPE": 8.0, "priceToBook": 0.8, "dividendYield": 0.045,
                     "marketCap": 500e12, "currentPrice": 72300,
                     "trailingEps": 5000, "bookValue": 60000}
        mock_ticker = MagicMock()
        mock_ticker.info = mock_info
        mock_yf.Ticker.return_value = mock_ticker

        enricher = KRFundamentalEnricher()
        score = enricher.score("005930")
        # PER=8 (+20), PBR=0.8 (+15), DIV=4.5 (+15) = 50+20+15+15 = 100
        assert score == 100.0

    @patch("scanner.kr_fundamental_enricher.yf")
    def test_score_growth_stock(self, mock_yf):
        mock_info = {"trailingPE": 30.0, "priceToBook": 5.5, "dividendYield": 0,
                     "marketCap": 50e12, "currentPrice": 200000,
                     "trailingEps": 1000, "bookValue": 10000}
        mock_ticker = MagicMock()
        mock_ticker.info = mock_info
        mock_yf.Ticker.return_value = mock_ticker

        enricher = KRFundamentalEnricher()
        score = enricher.score("035420")
        # PER=30 (+0), PBR=5.5 (-5), DIV=0 (+0) = 50+0-5+0 = 45
        assert score == 45.0

    @patch("scanner.kr_fundamental_enricher.yf")
    def test_get_batch(self, mock_yf):
        def make_ticker(info):
            t = MagicMock()
            t.info = info
            return t

        infos = {
            "005930.KS": {"trailingPE": 10, "priceToBook": 1, "dividendYield": 0.03,
                          "marketCap": 500e12, "currentPrice": 72300},
            "000660.KS": {"trailingPE": 15, "priceToBook": 2, "dividendYield": 0.01,
                          "marketCap": 100e12, "currentPrice": 150000},
        }

        def ticker_factory(sym):
            if sym in infos:
                return make_ticker(infos[sym])
            raise Exception("Not found")

        mock_yf.Ticker.side_effect = ticker_factory

        enricher = KRFundamentalEnricher()
        batch = enricher.get_batch(["005930", "000660", "999999"])
        assert len(batch) == 2
        assert "005930" in batch
        assert "000660" in batch
