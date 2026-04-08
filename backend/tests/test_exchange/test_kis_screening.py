"""Unit tests for KIS adapter screening/ranking methods."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from exchange.kis_adapter import KISAdapter, RankedStock


@pytest.fixture
def mock_adapter():
    """Create a KIS adapter with mocked internals."""
    config = MagicMock()
    config.base_url = "https://openapivts.koreainvestment.com:29443"  # paper
    auth = MagicMock()
    auth.ensure_valid_token = AsyncMock()
    auth.get_auth_headers = MagicMock(return_value={"authorization": "Bearer test"})

    adapter = KISAdapter(config=config, auth=auth)
    adapter._session = MagicMock()
    return adapter


class TestParseRanked:
    """Test _parse_ranked helper."""

    def test_parse_output2(self, mock_adapter):
        data = {
            "rt_cd": "0",
            "output2": [
                {"symb": "AAPL", "name": "Apple", "last": "185.50", "rate": "2.1", "tvol": "50000000"},
                {"symb": "NVDA", "name": "NVIDIA", "last": "900.00", "rate": "3.5", "tvol": "80000000"},
                {"symb": "", "name": "Empty"},  # should be skipped
            ],
        }
        result = mock_adapter._parse_ranked(data, "test", limit=10)
        assert len(result) == 2
        assert result[0].symbol == "AAPL"
        assert result[0].price == 185.50
        assert result[0].change_pct == 2.1
        assert result[0].volume == 50000000
        assert result[0].source == "test"
        assert result[1].symbol == "NVDA"

    def test_parse_with_limit(self, mock_adapter):
        data = {
            "output2": [
                {"symb": f"SYM{i}", "last": "100"} for i in range(20)
            ],
        }
        result = mock_adapter._parse_ranked(data, "test", limit=5)
        assert len(result) == 5

    def test_parse_empty_response(self, mock_adapter):
        result = mock_adapter._parse_ranked({}, "test", limit=10)
        assert result == []

    def test_parse_fallback_output(self, mock_adapter):
        """Falls back to 'output' if 'output2' missing."""
        data = {
            "output": [
                {"symb": "TSLA", "last": "250.00", "rate": "1.5", "tvol": "30000000"},
            ],
        }
        result = mock_adapter._parse_ranked(data, "test", limit=10)
        assert len(result) == 1
        assert result[0].symbol == "TSLA"

    def test_parse_alternative_field_names(self, mock_adapter):
        """Handles alternative KIS field names."""
        data = {
            "output2": [
                {
                    "stck_shrn_iscd": "AMD",
                    "hts_kor_isnm": "AMD",
                    "stck_prpr": "160.00",
                    "prdy_ctrt": "4.2",
                    "acml_vol": "25000000",
                },
            ],
        }
        result = mock_adapter._parse_ranked(data, "test", limit=10)
        assert len(result) == 1
        assert result[0].symbol == "AMD"
        assert result[0].price == 160.00
        assert result[0].change_pct == 4.2

    def test_parse_handles_none_values(self, mock_adapter):
        """Handles None values in numeric fields."""
        data = {
            "output2": [
                {"symb": "AAPL", "last": None, "rate": None, "tvol": None},
            ],
        }
        result = mock_adapter._parse_ranked(data, "test", limit=10)
        assert len(result) == 1
        assert result[0].price == 0.0
        assert result[0].change_pct == 0.0
        assert result[0].volume == 0.0


class TestRankedStock:
    """Test RankedStock dataclass."""

    def test_defaults(self):
        stock = RankedStock(symbol="AAPL")
        assert stock.symbol == "AAPL"
        assert stock.name == ""
        assert stock.price == 0.0
        assert stock.source == ""

    def test_full_init(self):
        stock = RankedStock(
            symbol="TSLA", name="Tesla", price=250.0,
            change_pct=3.5, volume=1000000, source="volume_surge",
        )
        assert stock.symbol == "TSLA"
        assert stock.source == "volume_surge"


class TestFetchUpdownRateParams:
    """Regression: fetch_updown_rate must include NDAY parameter.

    2026-04-09: KIS API returned `OPSQ2001 ERROR INPUT FIELD NOT FOUND
    [NDAY]` because the params dict was missing NDAY. Fix added
    `NDAY: "0"` (today's gainers/losers). This test locks in the fix.
    """

    @pytest.mark.asyncio
    async def test_fetch_updown_rate_passes_nday(self, mock_adapter):
        captured: dict = {}

        async def fake_get(path, tr_id, params):
            captured["path"] = path
            captured["tr_id"] = tr_id
            captured["params"] = dict(params)
            return {"rt_cd": "0", "output2": []}

        mock_adapter._get = fake_get  # type: ignore[assignment]

        await mock_adapter.fetch_updown_rate(exchange="NAS", direction="up")

        assert captured["path"] == "/uapi/overseas-stock/v1/ranking/updown-rate"
        # Required parameters per KIS HHDFS76290000
        assert captured["params"]["NDAY"] == "0", "NDAY must be set or KIS returns OPSQ2001"
        assert captured["params"]["EXCD"] == "NAS"
        assert captured["params"]["GUBN"] == "1"  # up
        assert captured["params"]["VOL_RANG"] == "1"

    @pytest.mark.asyncio
    async def test_fetch_updown_rate_down_direction(self, mock_adapter):
        captured: dict = {}

        async def fake_get(path, tr_id, params):
            captured["params"] = dict(params)
            return {"rt_cd": "0", "output2": []}

        mock_adapter._get = fake_get  # type: ignore[assignment]
        await mock_adapter.fetch_updown_rate(exchange="NYS", direction="down")

        assert captured["params"]["NDAY"] == "0"
        assert captured["params"]["EXCD"] == "NYS"
        assert captured["params"]["GUBN"] == "0"  # down

    @pytest.mark.asyncio
    async def test_fetch_new_highlow_passes_nday(self, mock_adapter):
        """Same NDAY-required bug as updown-rate.

        After the first NDAY fix to fetch_updown_rate, the journalctl
        still showed one OPSQ2001 warning per startup. Tracing it
        showed fetch_new_highlow (HHDFS76300000) also requires NDAY.
        """
        captured: dict = {}

        async def fake_get(path, tr_id, params):
            captured["path"] = path
            captured["params"] = dict(params)
            return {"rt_cd": "0", "output2": []}

        mock_adapter._get = fake_get  # type: ignore[assignment]
        await mock_adapter.fetch_new_highlow(exchange="NAS", high=True)

        assert captured["path"] == "/uapi/overseas-stock/v1/ranking/new-highlow"
        assert captured["params"]["NDAY"] == "0", "NDAY required for HHDFS76300000"
        assert captured["params"]["GUBN"] == "1"  # high
        assert captured["params"]["GUBN2"] == "1"  # sustained
