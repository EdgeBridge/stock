"""Tests for FRED Service."""

from unittest.mock import MagicMock, patch, AsyncMock
import pandas as pd
import pytest

from data.fred_service import FREDService, MacroIndicators, FRED_SERIES


class TestMacroIndicators:
    def test_yield_curve_inverted(self):
        ind = MacroIndicators(yield_spread=-0.5)
        assert ind.yield_curve_inverted is True

    def test_yield_curve_normal(self):
        ind = MacroIndicators(yield_spread=1.2)
        assert ind.yield_curve_inverted is False

    def test_yield_curve_none(self):
        ind = MacroIndicators()
        assert ind.yield_curve_inverted is False

    def test_rate_environment_low(self):
        ind = MacroIndicators(fed_funds_rate=1.5)
        assert ind.rate_environment == "low"

    def test_rate_environment_moderate(self):
        ind = MacroIndicators(fed_funds_rate=3.5)
        assert ind.rate_environment == "moderate"

    def test_rate_environment_high(self):
        ind = MacroIndicators(fed_funds_rate=5.25)
        assert ind.rate_environment == "high"

    def test_rate_environment_unknown(self):
        ind = MacroIndicators()
        assert ind.rate_environment == "unknown"

    def test_to_dict(self):
        ind = MacroIndicators(
            fed_funds_rate=5.25,
            treasury_10y=4.5,
            treasury_2y=4.8,
            yield_spread=-0.3,
            unemployment_rate=3.7,
            cpi_yoy=3.2,
        )
        d = ind.to_dict()
        assert d["fed_funds_rate"] == 5.25
        assert d["yield_curve_inverted"] is True
        assert d["rate_environment"] == "high"
        assert d["cpi_yoy"] == 3.2


class TestFREDService:
    def test_not_available_without_key(self):
        svc = FREDService(api_key="")
        assert svc.available is False

    def test_available_with_key(self):
        svc = FREDService(api_key="test_key")
        assert svc.available is True

    def test_last_indicators_initially_none(self):
        svc = FREDService(api_key="test")
        assert svc.last_indicators is None

    @pytest.mark.asyncio
    async def test_fetch_macro_no_key(self):
        svc = FREDService(api_key="")
        result = await svc.fetch_macro_indicators()
        assert result.fed_funds_rate is None

    @patch("data.fred_service.FREDService._get_client")
    @pytest.mark.asyncio
    async def test_fetch_latest(self, mock_client):
        mock_fred = MagicMock()
        mock_fred.get_series.return_value = pd.Series([4.5, 4.55, 4.6])
        mock_client.return_value = mock_fred

        svc = FREDService(api_key="test")
        svc._fred = mock_fred
        val = await svc.fetch_latest("DGS10")
        assert val == 4.6

    @patch("data.fred_service.FREDService._get_client")
    @pytest.mark.asyncio
    async def test_fetch_series_empty(self, mock_client):
        mock_fred = MagicMock()
        mock_fred.get_series.side_effect = Exception("network error")
        mock_client.return_value = mock_fred

        svc = FREDService(api_key="test")
        svc._fred = mock_fred
        result = await svc.fetch_series("BAD_SERIES")
        assert result.empty

    @patch("data.fred_service.FREDService.fetch_latest", new_callable=AsyncMock)
    @patch("data.fred_service.FREDService.fetch_series", new_callable=AsyncMock)
    @pytest.mark.asyncio
    async def test_fetch_macro_indicators(self, mock_series, mock_latest):
        mock_latest.side_effect = [5.25, 4.5, 4.8, 3.7, 230_000]
        # CPI series: 13 months
        mock_series.return_value = pd.Series(
            [300 + i * 0.5 for i in range(14)]
        )

        svc = FREDService(api_key="test")
        result = await svc.fetch_macro_indicators()

        assert result.fed_funds_rate == 5.25
        assert result.treasury_10y == 4.5
        assert result.treasury_2y == 4.8
        assert result.yield_spread == -0.3
        assert result.yield_curve_inverted is True
        assert result.unemployment_rate == 3.7
        assert result.cpi_yoy is not None
        assert svc.last_indicators is not None
