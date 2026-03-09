"""Tests for Korean fundamental enricher."""

import pytest
from unittest.mock import patch, MagicMock
import pandas as pd

from scanner.kr_fundamental_enricher import KRFundamentalEnricher, KRFundamentals


class TestKRFundamentals:
    def test_default_values(self):
        f = KRFundamentals(symbol="005930")
        assert f.per == 0.0
        assert f.pbr == 0.0
        assert f.dividend_yield == 0.0


class TestKRFundamentalEnricher:
    @patch("scanner.kr_fundamental_enricher.pykrx_stock")
    def test_get_loads_data(self, mock_stock):
        fund_df = pd.DataFrame(
            {"PER": [10.5], "PBR": [1.2], "EPS": [5000], "BPS": [50000],
             "DIV": [3.0], "DPS": [2000]},
            index=["005930"],
        )
        cap_df = pd.DataFrame(
            {"시가총액": [500_000_000_000_000], "거래대금": [1_000_000_000_000],
             "종가": [72300], "거래량": [10000000], "상장주식수": [5000000000]},
            index=["005930"],
        )
        mock_stock.get_market_fundamental.return_value = fund_df
        mock_stock.get_market_cap.return_value = cap_df

        enricher = KRFundamentalEnricher(date="20260309")
        result = enricher.get("005930")

        assert result is not None
        assert result.per == 10.5
        assert result.pbr == 1.2
        assert result.dividend_yield == 3.0
        assert result.market_cap == 500_000_000_000_000
        assert result.price == 72300

    @patch("scanner.kr_fundamental_enricher.pykrx_stock")
    def test_get_missing_symbol(self, mock_stock):
        mock_stock.get_market_fundamental.return_value = pd.DataFrame(
            columns=["PER", "PBR", "EPS", "BPS", "DIV", "DPS"]
        )
        mock_stock.get_market_cap.return_value = pd.DataFrame(
            columns=["시가총액", "거래대금", "종가", "거래량", "상장주식수"]
        )

        enricher = KRFundamentalEnricher(date="20260309")
        assert enricher.get("999999") is None

    @patch("scanner.kr_fundamental_enricher.pykrx_stock")
    def test_score_value_stock(self, mock_stock):
        fund_df = pd.DataFrame(
            {"PER": [8.0], "PBR": [0.8], "EPS": [5000], "BPS": [60000],
             "DIV": [4.5], "DPS": [2500]},
            index=["005930"],
        )
        cap_df = pd.DataFrame(
            {"시가총액": [500e12], "거래대금": [1e12], "종가": [72300],
             "거래량": [10e6], "상장주식수": [5e9]},
            index=["005930"],
        )
        mock_stock.get_market_fundamental.return_value = fund_df
        mock_stock.get_market_cap.return_value = cap_df

        enricher = KRFundamentalEnricher(date="20260309")
        score = enricher.score("005930")
        # PER=8 (+20), PBR=0.8 (+15), DIV=4.5 (+15) = 50+20+15+15 = 100
        assert score == 100.0

    @patch("scanner.kr_fundamental_enricher.pykrx_stock")
    def test_score_growth_stock(self, mock_stock):
        fund_df = pd.DataFrame(
            {"PER": [30.0], "PBR": [5.5], "EPS": [1000], "BPS": [10000],
             "DIV": [0.0], "DPS": [0]},
            index=["035420"],
        )
        cap_df = pd.DataFrame(
            {"시가총액": [50e12], "거래대금": [500e9], "종가": [200000],
             "거래량": [1e6], "상장주식수": [500e6]},
            index=["035420"],
        )
        mock_stock.get_market_fundamental.return_value = fund_df
        mock_stock.get_market_cap.return_value = cap_df

        enricher = KRFundamentalEnricher(date="20260309")
        score = enricher.score("035420")
        # PER=30 (+0), PBR=5.5 (-5), DIV=0 (+0) = 50+0-5+0 = 45
        assert score == 45.0

    @patch("scanner.kr_fundamental_enricher.pykrx_stock")
    def test_get_batch(self, mock_stock):
        fund_df = pd.DataFrame(
            {"PER": [10.0, 15.0], "PBR": [1.0, 2.0], "EPS": [5000, 3000],
             "BPS": [50000, 30000], "DIV": [3.0, 1.0], "DPS": [2000, 500]},
            index=["005930", "000660"],
        )
        cap_df = pd.DataFrame(
            {"시가총액": [500e12, 100e12], "거래대금": [1e12, 500e9],
             "종가": [72300, 150000], "거래량": [10e6, 5e6],
             "상장주식수": [5e9, 1e9]},
            index=["005930", "000660"],
        )
        mock_stock.get_market_fundamental.return_value = fund_df
        mock_stock.get_market_cap.return_value = cap_df

        enricher = KRFundamentalEnricher(date="20260309")
        batch = enricher.get_batch(["005930", "000660", "999999"])
        assert len(batch) == 2
        assert "005930" in batch
        assert "000660" in batch
