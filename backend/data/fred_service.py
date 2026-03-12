"""FRED Economic Data Service.

Fetches macroeconomic indicators from the Federal Reserve Economic Data (FRED) API.
Used for macro-level market regime assessment and strategy adaptation.

Key indicators:
  - Federal Funds Rate (FEDFUNDS)
  - 10-Year Treasury Yield (DGS10)
  - 2-Year Treasury Yield (DGS2)
  - Yield Curve Spread (10Y - 2Y)
  - Unemployment Rate (UNRATE)
  - CPI YoY Change (CPIAUCSL)
  - Initial Jobless Claims (ICSA)
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta

import pandas as pd

logger = logging.getLogger(__name__)


@dataclass
class MacroIndicators:
    """Snapshot of key macroeconomic indicators."""
    fed_funds_rate: float | None = None
    treasury_10y: float | None = None
    treasury_2y: float | None = None
    yield_spread: float | None = None  # 10Y - 2Y
    unemployment_rate: float | None = None
    cpi_yoy: float | None = None
    initial_claims: float | None = None
    fetched_at: str = ""

    @property
    def yield_curve_inverted(self) -> bool:
        """True if yield curve is inverted (recession signal)."""
        if self.yield_spread is not None:
            return self.yield_spread < 0
        return False

    @property
    def rate_environment(self) -> str:
        """Classify rate environment: 'low', 'moderate', 'high'."""
        if self.fed_funds_rate is None:
            return "unknown"
        if self.fed_funds_rate < 2.0:
            return "low"
        if self.fed_funds_rate < 4.5:
            return "moderate"
        return "high"

    def to_dict(self) -> dict:
        return {
            "fed_funds_rate": self.fed_funds_rate,
            "treasury_10y": self.treasury_10y,
            "treasury_2y": self.treasury_2y,
            "yield_spread": self.yield_spread,
            "yield_curve_inverted": self.yield_curve_inverted,
            "unemployment_rate": self.unemployment_rate,
            "cpi_yoy": self.cpi_yoy,
            "initial_claims": self.initial_claims,
            "rate_environment": self.rate_environment,
            "fetched_at": self.fetched_at,
        }


# Series IDs for FRED API
FRED_SERIES = {
    "fed_funds_rate": "FEDFUNDS",
    "treasury_10y": "DGS10",
    "treasury_2y": "DGS2",
    "unemployment_rate": "UNRATE",
    "cpi": "CPIAUCSL",
    "initial_claims": "ICSA",
}


class FREDService:
    """FRED API client for macroeconomic data."""

    def __init__(self, api_key: str = ""):
        self._api_key = api_key
        self._fred = None
        self._last_indicators: MacroIndicators | None = None

    def _get_client(self):
        if self._fred is None:
            if not self._api_key:
                raise ValueError("FRED API key not configured (EXTERNAL_FRED_API_KEY)")
            from fredapi import Fred
            self._fred = Fred(api_key=self._api_key)
        return self._fred

    @property
    def available(self) -> bool:
        return bool(self._api_key)

    @property
    def last_indicators(self) -> MacroIndicators | None:
        return self._last_indicators

    def _fetch_series_sync(
        self,
        series_id: str,
        start: str | None = None,
        end: str | None = None,
        periods: int = 12,
    ) -> pd.Series:
        """Synchronous FRED fetch (use fetch_series for async context)."""
        try:
            fred = self._get_client()
            if start:
                data = fred.get_series(series_id, observation_start=start, observation_end=end)
            else:
                data = fred.get_series(series_id)
                if len(data) > periods:
                    data = data.tail(periods)
            return data.dropna()
        except Exception as e:
            logger.warning("Failed to fetch FRED series %s: %s", series_id, e)
            return pd.Series(dtype=float)

    async def fetch_series(
        self,
        series_id: str,
        start: str | None = None,
        end: str | None = None,
        periods: int = 12,
    ) -> pd.Series:
        """Fetch a FRED time series (runs in thread to avoid blocking event loop)."""
        import asyncio
        return await asyncio.to_thread(
            self._fetch_series_sync, series_id, start, end, periods,
        )

    async def fetch_latest(self, series_id: str) -> float | None:
        """Fetch the most recent value for a FRED series."""
        data = await self.fetch_series(series_id, periods=5)
        if data.empty:
            return None
        return float(data.iloc[-1])

    async def fetch_macro_indicators(self) -> MacroIndicators:
        """Fetch all key macro indicators and return a snapshot."""
        indicators = MacroIndicators(fetched_at=datetime.now().isoformat())

        if not self.available:
            logger.warning("FRED API key not configured, skipping macro fetch")
            return indicators

        try:
            indicators.fed_funds_rate = await self.fetch_latest(FRED_SERIES["fed_funds_rate"])
            indicators.treasury_10y = await self.fetch_latest(FRED_SERIES["treasury_10y"])
            indicators.treasury_2y = await self.fetch_latest(FRED_SERIES["treasury_2y"])

            if indicators.treasury_10y is not None and indicators.treasury_2y is not None:
                indicators.yield_spread = round(
                    indicators.treasury_10y - indicators.treasury_2y, 2
                )

            indicators.unemployment_rate = await self.fetch_latest(FRED_SERIES["unemployment_rate"])
            indicators.initial_claims = await self.fetch_latest(FRED_SERIES["initial_claims"])

            # CPI YoY: compute from last 13 months
            cpi_data = await self.fetch_series(FRED_SERIES["cpi"], periods=14)
            if len(cpi_data) >= 13:
                cpi_latest = float(cpi_data.iloc[-1])
                cpi_year_ago = float(cpi_data.iloc[-13])
                if cpi_year_ago > 0:
                    indicators.cpi_yoy = round(
                        (cpi_latest - cpi_year_ago) / cpi_year_ago * 100, 2
                    )

            self._last_indicators = indicators
            logger.info(
                "FRED macro: FFR=%.2f, 10Y=%.2f, 2Y=%.2f, spread=%.2f, unemp=%.1f",
                indicators.fed_funds_rate or 0,
                indicators.treasury_10y or 0,
                indicators.treasury_2y or 0,
                indicators.yield_spread or 0,
                indicators.unemployment_rate or 0,
            )

        except Exception as e:
            logger.error("Failed to fetch macro indicators: %s", e)

        return indicators

    async def get_yield_curve_history(
        self, months: int = 24
    ) -> pd.DataFrame:
        """Get yield curve spread history (10Y - 2Y) for trend analysis."""
        start = (datetime.now() - timedelta(days=months * 30)).strftime("%Y-%m-%d")
        try:
            t10 = await self.fetch_series(FRED_SERIES["treasury_10y"], start=start)
            t2 = await self.fetch_series(FRED_SERIES["treasury_2y"], start=start)

            if t10.empty or t2.empty:
                return pd.DataFrame()

            df = pd.DataFrame({"treasury_10y": t10, "treasury_2y": t2}).dropna()
            df["spread"] = df["treasury_10y"] - df["treasury_2y"]
            return df

        except Exception as e:
            logger.warning("Failed to fetch yield curve history: %s", e)
            return pd.DataFrame()
