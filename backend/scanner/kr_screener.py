"""Korean stock screener using pykrx.

Discovers KR stocks by:
1. Market cap ranking (시가총액 상위)
2. Trading value ranking (거래대금 상위)
3. Fundamental screening (저PER, 고배당)
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta

import pandas as pd
from pykrx import stock as pykrx_stock

logger = logging.getLogger(__name__)


@dataclass
class KRScreenResult:
    """Result from KR stock screening."""
    symbols: list[str] = field(default_factory=list)
    sources: dict[str, list[str]] = field(default_factory=dict)
    total_discovered: int = 0


def _get_latest_trading_date() -> str:
    """Get the most recent trading date (skip weekends)."""
    dt = datetime.now()
    # If before market close, use previous day
    if dt.hour < 16:
        dt -= timedelta(days=1)
    # Skip weekends
    while dt.weekday() >= 5:
        dt -= timedelta(days=1)
    return dt.strftime("%Y%m%d")


class KRScreener:
    """Korean stock screener using pykrx data."""

    def __init__(
        self,
        max_per_source: int = 20,
        max_total: int = 60,
        min_market_cap: int = 500_000_000_000,  # 5000억원
        min_trading_value: int = 10_000_000_000,  # 100억원
    ):
        self._max_per_source = max_per_source
        self._max_total = max_total
        self._min_market_cap = min_market_cap
        self._min_trading_value = min_trading_value

    def screen(
        self,
        date: str | None = None,
        markets: list[str] | None = None,
    ) -> KRScreenResult:
        """Run all screening criteria and return combined results.

        Args:
            date: Target date (YYYYMMDD). Defaults to latest trading day.
            markets: List of markets to screen ('KOSPI', 'KOSDAQ'). Default both.
        """
        if date is None:
            date = _get_latest_trading_date()
        if markets is None:
            markets = ["KOSPI", "KOSDAQ"]

        result = KRScreenResult()

        for market in markets:
            # Source 1: Market cap leaders
            try:
                mcap_syms = self._screen_by_market_cap(date, market)
                result.sources[f"market_cap_{market.lower()}"] = mcap_syms
                result.symbols.extend(mcap_syms)
            except Exception as e:
                logger.warning("KR market cap screening failed (%s): %s", market, e)

            # Source 2: Trading value leaders
            try:
                tv_syms = self._screen_by_trading_value(date, market)
                result.sources[f"trading_value_{market.lower()}"] = tv_syms
                result.symbols.extend(tv_syms)
            except Exception as e:
                logger.warning("KR trading value screening failed (%s): %s", market, e)

            # Source 3: Value stocks (low PER + decent dividend)
            try:
                val_syms = self._screen_value_stocks(date, market)
                result.sources[f"value_{market.lower()}"] = val_syms
                result.symbols.extend(val_syms)
            except Exception as e:
                logger.warning("KR value screening failed (%s): %s", market, e)

        # Deduplicate
        seen = set()
        unique = []
        for s in result.symbols:
            if s not in seen:
                seen.add(s)
                unique.append(s)
        result.symbols = unique[:self._max_total]
        result.total_discovered = len(unique)
        return result

    def _screen_by_market_cap(self, date: str, market: str) -> list[str]:
        """Top stocks by market cap (시가총액)."""
        df = pykrx_stock.get_market_cap(date, market=market)
        if df.empty:
            return []
        # Filter by minimum market cap and sort
        df = df[df["시가총액"] >= self._min_market_cap]
        df = df.sort_values("시가총액", ascending=False)
        return df.index.tolist()[:self._max_per_source]

    def _screen_by_trading_value(self, date: str, market: str) -> list[str]:
        """Top stocks by trading value (거래대금)."""
        df = pykrx_stock.get_market_cap(date, market=market)
        if df.empty:
            return []
        df = df[df["거래대금"] >= self._min_trading_value]
        df = df.sort_values("거래대금", ascending=False)
        return df.index.tolist()[:self._max_per_source]

    def _screen_value_stocks(self, date: str, market: str) -> list[str]:
        """Value stocks: positive PER < 15, PBR < 2, DIV > 1%."""
        df = pykrx_stock.get_market_fundamental(date, market=market)
        if df.empty:
            return []
        # Filter: positive PER, reasonable valuation, dividend yield
        mask = (
            (df["PER"] > 0) & (df["PER"] < 15)
            & (df["PBR"] > 0) & (df["PBR"] < 2)
            & (df["DIV"] > 1.0)
        )
        filtered = df[mask].copy()
        if filtered.empty:
            return []
        # Score by combined value (lower PER + higher DIV = better)
        filtered["value_score"] = (1 / filtered["PER"]) + filtered["DIV"]
        filtered = filtered.sort_values("value_score", ascending=False)
        return filtered.index.tolist()[:self._max_per_source]
