"""Insider trading service — Finnhub insider transactions API.

Monitors insider purchases/sales for signal confidence adjustment.
Large insider buys = bullish, large C-suite sells = bearish.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from datetime import date, timedelta

import aiohttp

logger = logging.getLogger(__name__)

FINNHUB_BASE_URL = "https://finnhub.io/api/v1"


@dataclass
class InsiderTransaction:
    symbol: str
    name: str
    share: int  # total shares held after
    change: int  # net change (+buy / -sell)
    filing_date: str
    transaction_date: str
    transaction_code: str  # P=purchase, S=sale, M=exercise
    transaction_price: float | None = None

    @property
    def value(self) -> float:
        """Estimated transaction value in USD."""
        if self.transaction_price and self.transaction_price > 0:
            return abs(self.change) * self.transaction_price
        return 0.0

    @property
    def is_purchase(self) -> bool:
        return self.transaction_code == "P"

    @property
    def is_sale(self) -> bool:
        return self.transaction_code == "S"

    def to_dict(self) -> dict:
        return {
            "symbol": self.symbol,
            "name": self.name,
            "change": self.change,
            "transaction_code": self.transaction_code,
            "transaction_date": self.transaction_date,
            "transaction_price": self.transaction_price,
            "value": round(self.value, 2),
        }


class InsiderTradingService:
    """Fetch and analyze insider transactions from Finnhub."""

    # Configurable params (for backtesting)
    bullish_purchase_threshold: float = 500_000  # min $ for bullish signal
    bearish_sale_threshold: float = 1_000_000  # min $ for bearish signal
    lookback_days: int = 90
    confidence_boost: float = 0.10
    confidence_penalty: float = 0.10

    def __init__(self, api_key: str = ""):
        self._api_key = api_key
        self._session: aiohttp.ClientSession | None = None
        self._cache: dict[str, list[InsiderTransaction]] = {}

    @property
    def available(self) -> bool:
        return bool(self._api_key)

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=15),
            )
        return self._session

    async def fetch_insider_transactions(
        self, symbol: str,
    ) -> list[InsiderTransaction]:
        """Fetch insider transactions for a single symbol."""
        if not self.available:
            return []
        session = await self._get_session()
        url = f"{FINNHUB_BASE_URL}/stock/insider-transactions"
        params = {"symbol": symbol, "token": self._api_key}
        try:
            async with session.get(url, params=params) as resp:
                if resp.status != 200:
                    logger.debug("Finnhub insider %s: HTTP %d", symbol, resp.status)
                    return []
                data = await resp.json()

            txns = []
            for item in data.get("data", []):
                code = item.get("transactionCode", "")
                if code not in ("P", "S"):
                    continue  # Skip exercises, gifts, etc.
                txns.append(InsiderTransaction(
                    symbol=symbol,
                    name=item.get("name", ""),
                    share=item.get("share", 0),
                    change=item.get("change", 0),
                    filing_date=item.get("filingDate", ""),
                    transaction_date=item.get("transactionDate", ""),
                    transaction_code=code,
                    transaction_price=item.get("transactionPrice"),
                ))
            return txns
        except Exception as e:
            logger.debug("Finnhub insider fetch failed for %s: %s", symbol, e)
            return []

    async def refresh(self, symbols: list[str]) -> None:
        """Batch fetch insider transactions for watchlist symbols."""
        if not self.available:
            return

        self._cache.clear()
        cutoff = (date.today() - timedelta(days=self.lookback_days)).isoformat()

        for symbol in symbols:
            # Skip KR symbols (Finnhub doesn't cover)
            if symbol.isdigit():
                continue
            txns = await self.fetch_insider_transactions(symbol)
            # Filter to recent transactions only
            recent = [t for t in txns if t.transaction_date >= cutoff]
            if recent:
                self._cache[symbol] = recent
            await asyncio.sleep(0.2)  # rate limit

        total = sum(len(v) for v in self._cache.values())
        logger.info(
            "Insider transactions: %d transactions for %d symbols (last %d days)",
            total, len(self._cache), self.lookback_days,
        )

    def get_signal_adjustment(self, symbol: str) -> float:
        """Confidence adjustment based on insider activity.

        Returns:
            +boost for large insider purchases,
            -penalty for large insider sales,
            0.0 otherwise.
        """
        txns = self._cache.get(symbol, [])
        if not txns:
            return 0.0

        total_buy_value = sum(t.value for t in txns if t.is_purchase)
        total_sell_value = sum(t.value for t in txns if t.is_sale)

        if total_buy_value >= self.bullish_purchase_threshold:
            return self.confidence_boost
        if total_sell_value >= self.bearish_sale_threshold:
            return -self.confidence_penalty
        return 0.0

    def get_recent(self, symbol: str) -> list[InsiderTransaction]:
        """Get cached recent transactions for a symbol."""
        return self._cache.get(symbol, [])

    def get_notable(self) -> list[dict]:
        """Get notable insider transactions across all symbols."""
        notable = []
        for symbol, txns in self._cache.items():
            buys = [t for t in txns if t.is_purchase]
            sells = [t for t in txns if t.is_sale]
            buy_val = sum(t.value for t in buys)
            sell_val = sum(t.value for t in sells)
            if buy_val >= self.bullish_purchase_threshold:
                notable.append({
                    "symbol": symbol,
                    "signal": "BULLISH",
                    "total_value": round(buy_val, 2),
                    "count": len(buys),
                    "top_buyer": max(buys, key=lambda t: t.value).name if buys else "",
                })
            elif sell_val >= self.bearish_sale_threshold:
                notable.append({
                    "symbol": symbol,
                    "signal": "BEARISH",
                    "total_value": round(sell_val, 2),
                    "count": len(sells),
                    "top_seller": max(sells, key=lambda t: t.value).name if sells else "",
                })
        notable.sort(key=lambda x: x["total_value"], reverse=True)
        return notable

    def to_dict(self) -> list[dict]:
        """Serialize notable insider activity for API."""
        return self.get_notable()

    async def close(self) -> None:
        if self._session and not self._session.closed:
            await self._session.close()
