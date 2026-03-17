"""Tests for trade history module: restore, reconciliation, persistence."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from api.trades import (
    _trade_log,
    record_trade,
    restore_trade_log,
    reconcile_pending_orders,
    update_order_in_db,
    init_trades,
    _order_to_dict,
)


@pytest.fixture(autouse=True)
def clear_trade_log():
    """Clear in-memory trade log before/after each test."""
    _trade_log.clear()
    yield
    _trade_log.clear()


class TestRecordTrade:
    def test_appends_to_in_memory_log(self):
        record_trade({"symbol": "AAPL", "side": "BUY", "status": "pending"})
        assert len(_trade_log) == 1
        assert _trade_log[0]["symbol"] == "AAPL"

    def test_includes_order_id(self):
        record_trade(
            {
                "order_id": "KIS123",
                "symbol": "MSFT",
                "side": "BUY",
                "status": "pending",
            }
        )
        assert _trade_log[0]["order_id"] == "KIS123"


class TestRestoreTradeLog:
    @pytest.mark.asyncio
    async def test_restore_from_db(self):
        """Restore trade log populates _trade_log from DB orders."""
        mock_order = MagicMock()
        mock_order.id = 1
        mock_order.kis_order_id = "KIS001"
        mock_order.symbol = "AAPL"
        mock_order.side = "BUY"
        mock_order.quantity = 10
        mock_order.price = 150.0
        mock_order.filled_price = 150.5
        mock_order.filled_quantity = 10
        mock_order.status = "filled"
        mock_order.strategy_name = "trend_following"
        mock_order.pnl = None
        mock_order.market = "US"
        mock_order.created_at = "2026-03-10 10:00:00"

        mock_repo = AsyncMock()
        mock_repo.get_trade_history = AsyncMock(return_value=[mock_order])

        mock_session = AsyncMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)
        mock_factory = MagicMock(return_value=mock_session)

        with patch("api.trades._session_factory", mock_factory):
            with patch("db.trade_repository.TradeRepository", return_value=mock_repo):
                count = await restore_trade_log()

        assert count == 1
        assert _trade_log[0]["symbol"] == "AAPL"
        assert _trade_log[0]["order_id"] == "KIS001"
        assert _trade_log[0]["status"] == "filled"

    @pytest.mark.asyncio
    async def test_restore_no_session_factory(self):
        with patch("api.trades._session_factory", None):
            count = await restore_trade_log()
        assert count == 0


class TestReconcilePendingOrders:
    @pytest.mark.asyncio
    async def test_buy_held_marked_filled(self):
        """Pending BUY order for held symbol → filled."""
        mock_order = MagicMock()
        mock_order.id = 1
        mock_order.symbol = "AAPL"
        mock_order.side = "BUY"
        mock_order.price = 150.0
        mock_order.quantity = 10

        mock_repo = AsyncMock()
        mock_repo.get_open_orders = AsyncMock(return_value=[mock_order])
        mock_repo.update_order_status = AsyncMock()

        mock_session = AsyncMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)
        mock_factory = MagicMock(return_value=mock_session)

        with patch("api.trades._session_factory", mock_factory):
            with patch("db.trade_repository.TradeRepository", return_value=mock_repo):
                updated = await reconcile_pending_orders({"AAPL", "MSFT"})

        assert updated == 1
        mock_repo.update_order_status.assert_called_once_with(
            1,
            "filled",
            filled_price=150.0,
            filled_quantity=10,
        )

    @pytest.mark.asyncio
    async def test_buy_not_held_marked_cancelled(self):
        """Pending BUY order for non-held symbol → cancelled."""
        mock_order = MagicMock()
        mock_order.id = 2
        mock_order.symbol = "TSLA"
        mock_order.side = "BUY"
        mock_order.price = 200.0
        mock_order.quantity = 5

        mock_repo = AsyncMock()
        mock_repo.get_open_orders = AsyncMock(return_value=[mock_order])
        mock_repo.update_order_status = AsyncMock()

        mock_session = AsyncMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)
        mock_factory = MagicMock(return_value=mock_session)

        with patch("api.trades._session_factory", mock_factory):
            with patch("db.trade_repository.TradeRepository", return_value=mock_repo):
                updated = await reconcile_pending_orders({"AAPL"})

        assert updated == 1
        mock_repo.update_order_status.assert_called_once_with(2, "cancelled")

    @pytest.mark.asyncio
    async def test_sell_not_held_marked_filled(self):
        """Pending SELL order for non-held symbol → filled."""
        mock_order = MagicMock()
        mock_order.id = 3
        mock_order.symbol = "AAPL"
        mock_order.side = "SELL"
        mock_order.price = 160.0
        mock_order.quantity = 10

        mock_repo = AsyncMock()
        mock_repo.get_open_orders = AsyncMock(return_value=[mock_order])
        mock_repo.update_order_status = AsyncMock()

        mock_session = AsyncMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)
        mock_factory = MagicMock(return_value=mock_session)

        with patch("api.trades._session_factory", mock_factory):
            with patch("db.trade_repository.TradeRepository", return_value=mock_repo):
                updated = await reconcile_pending_orders(set())

        assert updated == 1
        mock_repo.update_order_status.assert_called_once_with(
            3,
            "filled",
            filled_price=160.0,
            filled_quantity=10,
        )


class TestUpdateOrderInDb:
    @pytest.mark.asyncio
    async def test_updates_db_and_trade_log(self):
        """Update DB and in-memory trade log by kis_order_id."""
        _trade_log.append(
            {
                "order_id": "KIS123",
                "symbol": "AAPL",
                "status": "pending",
                "filled_price": None,
            }
        )

        mock_order = MagicMock()
        mock_order.id = 1

        mock_repo = AsyncMock()
        mock_repo.find_by_kis_order_id = AsyncMock(return_value=mock_order)
        mock_repo.update_order_status = AsyncMock()

        mock_session = AsyncMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)
        mock_factory = MagicMock(return_value=mock_session)

        with patch("api.trades._session_factory", mock_factory):
            with patch("db.trade_repository.TradeRepository", return_value=mock_repo):
                ok = await update_order_in_db("KIS123", "filled", 155.0, 10)

        assert ok is True
        assert _trade_log[0]["status"] == "filled"
        assert _trade_log[0]["filled_price"] == 155.0

    @pytest.mark.asyncio
    async def test_no_order_id_returns_false(self):
        ok = await update_order_in_db("", "filled")
        assert ok is False


class TestOrderToDict:
    def test_converts_order_to_dict(self):
        mock_order = MagicMock()
        mock_order.id = 5
        mock_order.kis_order_id = "KIS555"
        mock_order.symbol = "NVDA"
        mock_order.side = "BUY"
        mock_order.quantity = 20
        mock_order.price = 300.0
        mock_order.filled_price = 301.0
        mock_order.filled_quantity = 20
        mock_order.status = "filled"
        mock_order.strategy_name = "bnf_deviation"
        mock_order.pnl = 50.0
        mock_order.is_paper = False
        mock_order.market = "US"
        mock_order.created_at = "2026-03-10 15:30:00"

        d = _order_to_dict(mock_order)
        assert d["order_id"] == "KIS555"
        assert d["symbol"] == "NVDA"
        assert d["status"] == "filled"
        assert d["db_id"] == 5
        assert d["is_paper"] is False

    def test_converts_paper_order_to_dict(self):
        mock_order = MagicMock()
        mock_order.id = 6
        mock_order.kis_order_id = ""
        mock_order.symbol = "AAPL"
        mock_order.side = "BUY"
        mock_order.quantity = 10
        mock_order.price = 150.0
        mock_order.filled_price = 150.0
        mock_order.filled_quantity = 10
        mock_order.status = "filled"
        mock_order.strategy_name = "trend_following"
        mock_order.pnl = None
        mock_order.is_paper = True
        mock_order.market = "US"
        mock_order.created_at = "2026-03-10 10:00:00"

        d = _order_to_dict(mock_order)
        assert d["is_paper"] is True
        assert d["order_id"] == ""


# --- Paper/Live order separation tests (STOCK-6) ---


class TestPaperOrderSeparation:
    def test_record_trade_preserves_is_paper(self):
        """is_paper flag is preserved in in-memory trade log."""
        record_trade(
            {
                "order_id": "abc123",
                "symbol": "AAPL",
                "side": "BUY",
                "status": "filled",
                "is_paper": True,
            }
        )
        assert _trade_log[0]["is_paper"] is True

    def test_record_trade_defaults_is_paper_false(self):
        """Trade without is_paper flag defaults to False (live)."""
        record_trade(
            {
                "order_id": "KIS123",
                "symbol": "MSFT",
                "side": "BUY",
                "status": "filled",
            }
        )
        # is_paper key may not be present, but get() defaults to False
        assert _trade_log[0].get("is_paper", False) is False

    @pytest.mark.asyncio
    async def test_trade_summary_excludes_paper(self):
        """Trade summary excludes paper orders from PnL calculations."""
        from api.trades import trade_summary

        # Paper order with PnL
        record_trade(
            {
                "symbol": "AAPL",
                "side": "SELL",
                "pnl": 100.0,
                "is_paper": True,
                "market": "US",
            }
        )
        # Live order with PnL
        record_trade(
            {
                "symbol": "MSFT",
                "side": "SELL",
                "pnl": 50.0,
                "is_paper": False,
                "market": "US",
            }
        )
        # Live order without is_paper (legacy) — should be included
        record_trade(
            {
                "symbol": "GOOGL",
                "side": "SELL",
                "pnl": 25.0,
                "market": "US",
            }
        )

        summary = await trade_summary()
        # Paper order excluded: total_pnl = 50 + 25 = 75
        assert summary["total_pnl"] == 75.0
        # total_trades excludes paper
        assert summary["total_trades"] == 2

    @pytest.mark.asyncio
    async def test_reconcile_excludes_paper_orders(self):
        """Reconciliation only processes live (non-paper) orders."""
        mock_repo = AsyncMock()
        mock_repo.get_open_orders = AsyncMock(return_value=[])
        mock_repo.update_order_status = AsyncMock()

        mock_session = AsyncMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)
        mock_factory = MagicMock(return_value=mock_session)

        with patch("api.trades._session_factory", mock_factory):
            with patch("db.trade_repository.TradeRepository", return_value=mock_repo):
                await reconcile_pending_orders({"AAPL"})

        # Verify exclude_paper=True was passed
        mock_repo.get_open_orders.assert_called_once_with(exclude_paper=True)

    @pytest.mark.asyncio
    async def test_restore_trade_log_excludes_paper(self):
        """restore_trade_log excludes paper orders by default."""
        mock_repo = AsyncMock()
        mock_repo.get_trade_history = AsyncMock(return_value=[])

        mock_session = AsyncMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)
        mock_factory = MagicMock(return_value=mock_session)

        with patch("api.trades._session_factory", mock_factory):
            with patch("db.trade_repository.TradeRepository", return_value=mock_repo):
                await restore_trade_log()

        # Verify exclude_paper=True was passed
        mock_repo.get_trade_history.assert_called_once_with(
            limit=200,
            exclude_paper=True,
        )


# --- Exchange field propagation tests (STOCK-5) ---


class TestExchangeFieldPersistence:
    """Tests for correct exchange field propagation from trade recorder to DB.

    STOCK-5: exchange field was dropped in _persist_trade, causing all orders
    (including KR) to be stored with default exchange='NASD'.
    """

    @pytest.mark.asyncio
    async def test_persist_trade_passes_exchange_kr(self):
        """_persist_trade passes exchange='KRX' for KR trades to save_order."""
        from api.trades import _persist_trade

        mock_repo = AsyncMock()
        mock_repo.save_order = AsyncMock()

        mock_session = AsyncMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)
        mock_factory = MagicMock(return_value=mock_session)

        trade = {
            "order_id": "KR001",
            "symbol": "005930",
            "side": "BUY",
            "quantity": 10,
            "price": 70000.0,
            "filled_quantity": 10,
            "filled_price": 70000.0,
            "status": "filled",
            "strategy": "supertrend",
            "exchange": "KRX",
            "market": "KR",
            "session": "regular",
            "is_paper": False,
        }

        with patch("api.trades._session_factory", mock_factory):
            with patch(
                "db.trade_repository.TradeRepository", return_value=mock_repo
            ):
                await _persist_trade(trade)

        mock_repo.save_order.assert_called_once()
        call_kwargs = mock_repo.save_order.call_args.kwargs
        assert call_kwargs["exchange"] == "KRX"
        assert call_kwargs["market"] == "KR"

    @pytest.mark.asyncio
    async def test_persist_trade_passes_exchange_us(self):
        """_persist_trade passes exchange='NASD' for US trades."""
        from api.trades import _persist_trade

        mock_repo = AsyncMock()
        mock_repo.save_order = AsyncMock()

        mock_session = AsyncMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)
        mock_factory = MagicMock(return_value=mock_session)

        trade = {
            "order_id": "US001",
            "symbol": "AAPL",
            "side": "BUY",
            "quantity": 10,
            "price": 150.0,
            "exchange": "NASD",
            "market": "US",
        }

        with patch("api.trades._session_factory", mock_factory):
            with patch(
                "db.trade_repository.TradeRepository", return_value=mock_repo
            ):
                await _persist_trade(trade)

        call_kwargs = mock_repo.save_order.call_args.kwargs
        assert call_kwargs["exchange"] == "NASD"

    @pytest.mark.asyncio
    async def test_persist_trade_passes_exchange_nyse(self):
        """_persist_trade passes exchange='NYSE' for NYSE trades."""
        from api.trades import _persist_trade

        mock_repo = AsyncMock()
        mock_repo.save_order = AsyncMock()

        mock_session = AsyncMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)
        mock_factory = MagicMock(return_value=mock_session)

        trade = {
            "order_id": "US002",
            "symbol": "BAC",
            "side": "BUY",
            "quantity": 50,
            "price": 40.0,
            "exchange": "NYSE",
            "market": "US",
        }

        with patch("api.trades._session_factory", mock_factory):
            with patch(
                "db.trade_repository.TradeRepository", return_value=mock_repo
            ):
                await _persist_trade(trade)

        call_kwargs = mock_repo.save_order.call_args.kwargs
        assert call_kwargs["exchange"] == "NYSE"

    @pytest.mark.asyncio
    async def test_persist_trade_defaults_exchange_nasd(self):
        """_persist_trade defaults to 'NASD' when exchange not in trade dict."""
        from api.trades import _persist_trade

        mock_repo = AsyncMock()
        mock_repo.save_order = AsyncMock()

        mock_session = AsyncMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)
        mock_factory = MagicMock(return_value=mock_session)

        # Legacy trade dict without exchange field
        trade = {
            "order_id": "OLD001",
            "symbol": "AAPL",
            "side": "BUY",
            "quantity": 10,
            "price": 150.0,
        }

        with patch("api.trades._session_factory", mock_factory):
            with patch(
                "db.trade_repository.TradeRepository", return_value=mock_repo
            ):
                await _persist_trade(trade)

        call_kwargs = mock_repo.save_order.call_args.kwargs
        assert call_kwargs["exchange"] == "NASD"
