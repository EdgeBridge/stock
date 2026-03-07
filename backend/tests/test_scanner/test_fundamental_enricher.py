"""Tests for Layer 2: Fundamental Enricher."""

from unittest.mock import AsyncMock, patch, MagicMock

import pytest

from scanner.fundamental_enricher import FundamentalEnricher, EnrichedCandidate
from data.external_data_service import (
    ExternalDataService, StockProfile, StockInfo,
    ConsensusData, FundamentalData, SmartMoneyData,
)


def _make_profile(
    consensus_bull_pct: float = 0.7,
    target_upside: float = 15.0,
    revenue_growth: float = 0.15,
    profit_margin: float = 0.22,
    forward_pe: float = 20.0,
    institutional_pct: float = 0.65,
) -> StockProfile:
    total = 30
    buy_count = int(total * consensus_bull_pct)
    return StockProfile(
        symbol="AAPL",
        info=StockInfo(symbol="AAPL", name="Apple Inc."),
        consensus=ConsensusData(
            analyst_count=total, strong_buy=buy_count // 2,
            buy=buy_count - buy_count // 2,
            hold=total - buy_count, sell=0, strong_sell=0,
            target_upside_pct=target_upside,
        ),
        fundamentals=FundamentalData(
            revenue_growth=revenue_growth,
            profit_margin=profit_margin,
            forward_pe=forward_pe,
            peg_ratio=1.2,
        ),
        smart_money=SmartMoneyData(
            institutional_pct=institutional_pct,
            insider_buy_count_90d=3,
            insider_sell_count_90d=1,
            short_ratio=1.5,
        ),
    )


@pytest.fixture
def mock_data_service():
    svc = AsyncMock(spec=ExternalDataService)
    svc.get_stock_profile = AsyncMock(return_value=_make_profile())
    return svc


class TestFundamentalEnricher:
    async def test_enrich_good_stock(self, mock_data_service):
        enricher = FundamentalEnricher(data_service=mock_data_service)
        result = await enricher.enrich("AAPL", indicator_score=75.0, current_price=175.0)

        assert result.symbol == "AAPL"
        assert result.indicator_score == 75.0
        assert result.combined_score > 50
        assert result.consensus_score > 50
        assert result.fundamental_score > 50

    async def test_enrich_weak_stock(self, mock_data_service):
        mock_data_service.get_stock_profile.return_value = _make_profile(
            consensus_bull_pct=0.2,
            target_upside=-15.0,
            revenue_growth=-0.10,
            profit_margin=-0.05,
            forward_pe=80.0,
            institutional_pct=0.20,
        )
        enricher = FundamentalEnricher(data_service=mock_data_service)
        result = await enricher.enrich("WEAK", indicator_score=30.0)
        assert result.combined_score < 40

    async def test_enrich_batch(self, mock_data_service):
        enricher = FundamentalEnricher(data_service=mock_data_service)
        candidates = [
            ("AAPL", 80.0, 175.0),
            ("TSLA", 70.0, 250.0),
        ]
        results = await enricher.enrich_batch(candidates)
        assert len(results) == 2
        # Should be sorted by combined_score descending
        assert results[0].combined_score >= results[1].combined_score

    async def test_enrich_batch_partial_failure(self, mock_data_service):
        mock_data_service.get_stock_profile.side_effect = [
            _make_profile(),
            Exception("API error"),
        ]
        enricher = FundamentalEnricher(data_service=mock_data_service)
        results = await enricher.enrich_batch([
            ("AAPL", 80.0, 175.0),
            ("FAIL", 70.0, 0.0),
        ])
        assert len(results) == 1

    async def test_grade_assignment(self, mock_data_service):
        enricher = FundamentalEnricher(data_service=mock_data_service)
        result = await enricher.enrich("AAPL", indicator_score=80.0)
        assert result.grade in ("A", "B", "C", "D", "F")

    async def test_custom_weights(self, mock_data_service):
        enricher = FundamentalEnricher(
            data_service=mock_data_service,
            weights={"consensus": 0.80, "fundamental": 0.10, "smart_money": 0.10},
        )
        result = await enricher.enrich("AAPL", indicator_score=75.0)
        assert result.combined_score > 0


class TestEnrichedCandidate:
    def test_defaults(self):
        c = EnrichedCandidate(
            symbol="TEST", indicator_score=50, consensus_score=50,
            fundamental_score=50, smart_money_score=50, combined_score=50,
        )
        assert c.profile is None
        assert c.grade == ""
