"""KIS REST API adapter for US stock trading.

Wraps 한국투자증권 Open API endpoints for:
- Market data (quotes, OHLCV, orderbook)
- Order management (buy, sell, cancel, modify)
- Account (balance, positions, buying power)
- Scanner (volume surge, price movers, new highs/lows)
"""

import logging
from typing import Any

import aiohttp

from config import KISConfig
from exchange.base import (
    Balance,
    Candle,
    ExchangeAdapter,
    OrderBook,
    OrderResult,
    Position,
    Ticker,
)
from exchange.kis_auth import KISAuth

logger = logging.getLogger(__name__)

# TR_ID mappings for US stock operations
TR_ID_LIVE = {
    # Market data (same for live/paper)
    "PRICE": "HHDFS00000300",
    "PRICE_DETAIL": "HHDFS76200200",
    "ORDERBOOK": "HHDFS76200100",
    "MINUTE_CANDLE": "HHDFS76950200",
    "DAILY_CANDLE": "HHDFS76240000",
    # Orders
    "BUY_US": "TTTT1002U",
    "SELL_US": "TTTT1006U",
    "CANCEL_US": "TTTT1004U",
    # Account
    "BALANCE": "TTTS3012R",
    "BUYING_POWER": "TTTS3007R",
    "ORDER_HISTORY": "TTTS3035R",
    "PENDING_ORDERS": "TTTS3018R",
    # Scanner
    "VOLUME_SURGE": "HHDFS76410000",
}

TR_ID_PAPER = {
    **TR_ID_LIVE,
    # Paper-specific overrides (TT -> VT prefix)
    "BUY_US": "VTTT1002U",
    "SELL_US": "VTTT1006U",
    "CANCEL_US": "VTTT1004U",
    "BALANCE": "VTTS3012R",
    "BUYING_POWER": "VTTS3007R",
    "ORDER_HISTORY": "VTTS3035R",
    "PENDING_ORDERS": "VTTS3018R",
}


# Market data endpoints use 3-char codes; trading endpoints use 4-char codes
_EXCD_MARKET = {"NASD": "NAS", "NYSE": "NYS", "AMEX": "AMS"}


class KISAdapter(ExchangeAdapter):
    """KIS REST API adapter."""

    def __init__(self, config: KISConfig, auth: KISAuth):
        self._config = config
        self._auth = auth
        self._session: aiohttp.ClientSession | None = None
        self._is_paper = "vts" in config.base_url
        self._tr = TR_ID_PAPER if self._is_paper else TR_ID_LIVE

    async def initialize(self) -> None:
        self._session = aiohttp.ClientSession()
        await self._auth.initialize()
        logger.info(
            "KIS adapter initialized (mode=%s)", "paper" if self._is_paper else "live"
        )

    async def close(self) -> None:
        if self._session:
            await self._session.close()
        await self._auth.close()

    # -- Market Data --

    async def fetch_ticker(self, symbol: str, exchange: str = "NASD") -> Ticker:
        await self._auth.ensure_valid_token()
        params = {
            "AUTH": "",
            "EXCD": _EXCD_MARKET.get(exchange, exchange),
            "SYMB": symbol,
        }
        data = await self._get(
            "/uapi/overseas-price/v1/quotations/price",
            self._tr["PRICE"],
            params,
        )
        output = data.get("output", {})
        return Ticker(
            symbol=symbol,
            price=float(output.get("last", 0)),
            change_pct=float(output.get("rate", 0)),
            volume=float(output.get("tvol", 0)),
        )

    async def fetch_ohlcv(
        self,
        symbol: str,
        timeframe: str = "1D",
        limit: int = 100,
        exchange: str = "NASD",
    ) -> list[Candle]:
        await self._auth.ensure_valid_token()

        # Map timeframe to KIS period type
        period_map = {"1D": "D", "1W": "W", "1M": "M"}
        period = period_map.get(timeframe, "D")

        params = {
            "AUTH": "",
            "EXCD": _EXCD_MARKET.get(exchange, exchange),
            "SYMB": symbol,
            "GUBN": period,
            "BYMD": "",  # empty = latest
            "MODP": "1",
        }
        data = await self._get(
            "/uapi/overseas-price/v1/quotations/dailyprice",
            self._tr["DAILY_CANDLE"],
            params,
        )
        candles = []
        for item in data.get("output2", [])[:limit]:
            try:
                candles.append(
                    Candle(
                        timestamp=int(item.get("xymd", "0")),
                        open=float(item.get("open", 0)),
                        high=float(item.get("high", 0)),
                        low=float(item.get("low", 0)),
                        close=float(item.get("clos", 0)),
                        volume=float(item.get("tvol", 0)),
                    )
                )
            except (ValueError, KeyError):
                continue
        candles.reverse()  # oldest first
        return candles

    async def fetch_orderbook(
        self, symbol: str, exchange: str = "NASD", limit: int = 20
    ) -> OrderBook:
        await self._auth.ensure_valid_token()
        # KIS orderbook endpoint for overseas stocks
        params = {
            "AUTH": "",
            "EXCD": _EXCD_MARKET.get(exchange, exchange),
            "SYMB": symbol,
        }
        data = await self._get(
            "/uapi/overseas-price/v1/quotations/inquire-asking-price",
            self._tr["ORDERBOOK"],
            params,
        )
        # Parse bid/ask from response
        output = data.get("output", {})
        bids = []
        asks = []
        for i in range(1, min(limit, 11)):
            bp = float(output.get(f"bidp{i}", 0))
            bq = float(output.get(f"bidq{i}", 0))
            ap = float(output.get(f"askp{i}", 0))
            aq = float(output.get(f"askq{i}", 0))
            if bp > 0:
                bids.append((bp, bq))
            if ap > 0:
                asks.append((ap, aq))
        return OrderBook(symbol=symbol, bids=bids, asks=asks)

    # -- Account --

    async def fetch_balance(self) -> Balance:
        await self._auth.ensure_valid_token()

        # 1. Position-based balance (total equity, realized P&L)
        bal_params = {
            "CANO": self._config.account_no,
            "ACNT_PRDT_CD": self._config.account_product,
            "OVRS_EXCG_CD": "NASD",
            "TR_CRCY_CD": "USD",
            "CTX_AREA_FK200": "",
            "CTX_AREA_NK200": "",
        }
        data = await self._get(
            "/uapi/overseas-stock/v1/trading/inquire-balance",
            self._tr["BALANCE"],
            bal_params,
        )
        output2 = data.get("output2", {})
        if isinstance(output2, list) and output2:
            output2 = output2[0]
        position_value = float(output2.get("frcr_buy_amt_smtl1", 0))

        # 2. Buying power (available cash for orders)
        # ITEM_CD + OVRS_ORD_UNPR required; use dummy values to get total buying power
        bp_params = {
            "CANO": self._config.account_no,
            "ACNT_PRDT_CD": self._config.account_product,
            "OVRS_EXCG_CD": "NASD",
            "OVRS_ORD_UNPR": "1",
            "ITEM_CD": "AAPL",
        }
        bp_data = await self._get(
            "/uapi/overseas-stock/v1/trading/inquire-psamount",
            self._tr["BUYING_POWER"],
            bp_params,
        )
        bp_output = bp_data.get("output", {})
        available = float(bp_output.get("ord_psbl_frcr_amt", 0))

        total = available + position_value
        return Balance(
            currency="USD",
            total=total,
            available=available,
            locked=position_value,
        )

    async def fetch_positions(self) -> list[Position]:
        await self._auth.ensure_valid_token()
        params = {
            "CANO": self._config.account_no,
            "ACNT_PRDT_CD": self._config.account_product,
            "OVRS_EXCG_CD": "NASD",
            "TR_CRCY_CD": "USD",
            "CTX_AREA_FK200": "",
            "CTX_AREA_NK200": "",
        }
        data = await self._get(
            "/uapi/overseas-stock/v1/trading/inquire-balance",
            self._tr["BALANCE"],
            params,
        )
        positions = []
        for item in data.get("output1", []):
            qty = float(item.get("ovrs_cblc_qty", 0))
            if qty <= 0:
                continue
            avg_price = float(item.get("pchs_avg_pric", 0))
            cur_price = float(item.get("now_pric2", 0))
            pnl = float(item.get("frcr_evlu_pfls_amt", 0))
            positions.append(
                Position(
                    symbol=item.get("ovrs_pdno", ""),
                    exchange=item.get("ovrs_excg_cd", "NASD"),
                    quantity=qty,
                    avg_price=avg_price,
                    current_price=cur_price,
                    unrealized_pnl=pnl,
                    unrealized_pnl_pct=(
                        ((cur_price - avg_price) / avg_price * 100) if avg_price > 0 else 0
                    ),
                )
            )
        return positions

    async def fetch_buying_power(self) -> float:
        balance = await self.fetch_balance()
        return balance.available

    # -- Orders --

    async def create_buy_order(
        self,
        symbol: str,
        quantity: int,
        price: float | None = None,
        order_type: str = "limit",
        exchange: str = "NASD",
    ) -> OrderResult:
        return await self._place_order(
            symbol, "buy", quantity, price, order_type, exchange, self._tr["BUY_US"]
        )

    async def create_sell_order(
        self,
        symbol: str,
        quantity: int,
        price: float | None = None,
        order_type: str = "limit",
        exchange: str = "NASD",
    ) -> OrderResult:
        return await self._place_order(
            symbol, "sell", quantity, price, order_type, exchange, self._tr["SELL_US"]
        )

    async def cancel_order(self, order_id: str, symbol: str) -> bool:
        await self._auth.ensure_valid_token()
        body = {
            "CANO": self._config.account_no,
            "ACNT_PRDT_CD": self._config.account_product,
            "OVRS_EXCG_CD": "NASD",
            "PDNO": symbol,
            "ORGN_ODNO": order_id,
            "RVSE_CNCL_DVSN_CD": "02",  # 02 = cancel
            "ORD_QTY": "0",  # full cancel
            "OVRS_ORD_UNPR": "0",
        }
        hashkey = await self._auth.get_hashkey(body)
        data = await self._post(
            "/uapi/overseas-stock/v1/trading/order-rvsecncl",
            self._tr["CANCEL_US"],
            body,
            hashkey,
        )
        return data.get("rt_cd") == "0"

    async def fetch_order(self, order_id: str, symbol: str) -> OrderResult:
        # KIS doesn't have single-order lookup; search in history
        orders = await self.fetch_pending_orders()
        for o in orders:
            if o.order_id == order_id:
                return o
        return OrderResult(
            order_id=order_id,
            symbol=symbol,
            side="unknown",
            order_type="unknown",
            quantity=0,
            status="not_found",
        )

    async def fetch_pending_orders(self) -> list[OrderResult]:
        await self._auth.ensure_valid_token()
        params = {
            "CANO": self._config.account_no,
            "ACNT_PRDT_CD": self._config.account_product,
            "OVRS_EXCG_CD": "NASD",
            "SORT_SQN": "DS",
            "CTX_AREA_FK200": "",
            "CTX_AREA_NK200": "",
        }
        data = await self._get(
            "/uapi/overseas-stock/v1/trading/inquire-nccs",
            self._tr["PENDING_ORDERS"],
            params,
        )
        results = []
        for item in data.get("output", []):
            results.append(
                OrderResult(
                    order_id=item.get("odno", ""),
                    symbol=item.get("pdno", ""),
                    side="buy" if item.get("sll_buy_dvsn_cd") == "02" else "sell",
                    order_type="limit",
                    quantity=float(item.get("ft_ord_qty", 0)),
                    price=float(item.get("ft_ord_unpr3", 0)),
                    filled_quantity=float(item.get("ft_ccld_qty", 0)),
                    status="open",
                )
            )
        return results

    # -- Private helpers --

    async def _place_order(
        self,
        symbol: str,
        side: str,
        quantity: int,
        price: float | None,
        order_type: str,
        exchange: str,
        tr_id: str,
    ) -> OrderResult:
        await self._auth.ensure_valid_token()

        ord_dvsn = "00" if order_type == "limit" else "01"
        body = {
            "CANO": self._config.account_no,
            "ACNT_PRDT_CD": self._config.account_product,
            "OVRS_EXCG_CD": exchange,
            "PDNO": symbol,
            "ORD_QTY": str(quantity),
            "OVRS_ORD_UNPR": str(price) if price else "0",
            "ORD_SVR_DVSN_CD": "0",
            "ORD_DVSN": ord_dvsn,
        }

        hashkey = await self._auth.get_hashkey(body)
        data = await self._post(
            "/uapi/overseas-stock/v1/trading/order",
            tr_id,
            body,
            hashkey,
        )

        output = data.get("output", {})
        success = data.get("rt_cd") == "0"

        return OrderResult(
            order_id=output.get("ODNO", ""),
            symbol=symbol,
            side=side,
            order_type=order_type,
            quantity=quantity,
            price=price,
            status="pending" if success else "failed",
        )

    async def _get(
        self, path: str, tr_id: str, params: dict[str, str]
    ) -> dict[str, Any]:
        url = f"{self._config.base_url}{path}"
        headers = self._auth.get_auth_headers(tr_id)
        async with self._session.get(url, headers=headers, params=params) as resp:
            data = await resp.json()
            if data.get("rt_cd") != "0":
                logger.warning("KIS API error: %s %s", data.get("msg_cd"), data.get("msg1"))
            return data

    async def _post(
        self, path: str, tr_id: str, body: dict, hashkey: str = ""
    ) -> dict[str, Any]:
        url = f"{self._config.base_url}{path}"
        headers = self._auth.get_auth_headers(tr_id, hashkey)
        async with self._session.post(url, headers=headers, json=body) as resp:
            data = await resp.json()
            if data.get("rt_cd") != "0":
                logger.warning("KIS API error: %s %s", data.get("msg_cd"), data.get("msg1"))
            return data
