"""Scenario 7: Market hours behavior.

1. Evaluation loop start/stop lifecycle
2. Watchlist management (add/remove symbols)
3. Market state affects strategy evaluation
4. Engine running state management
"""

import pytest
import asyncio

from exchange.paper_adapter import PaperAdapter
from data.indicator_service import IndicatorService
from data.market_data_service import MarketDataService
from strategies.combiner import SignalCombiner
from strategies.registry import StrategyRegistry
from engine.risk_manager import RiskManager
from engine.order_manager import OrderManager
from engine.evaluation_loop import EvaluationLoop
from unittest.mock import AsyncMock, MagicMock
import pandas as pd


def _make_loop(adapter=None, watchlist=None, market_state="uptrend"):
    if adapter is None:
        adapter = PaperAdapter(initial_balance_usd=100_000)

    market_data = AsyncMock(spec=MarketDataService)
    market_data.get_ohlcv = AsyncMock(return_value=MagicMock(empty=True))

    return EvaluationLoop(
        adapter=adapter,
        market_data=market_data,
        indicator_svc=IndicatorService(),
        registry=StrategyRegistry(),
        combiner=SignalCombiner(),
        order_manager=OrderManager(adapter=adapter, risk_manager=RiskManager()),
        risk_manager=RiskManager(),
        watchlist=watchlist or [],
        market_state=market_state,
        interval_sec=1,
    )


@pytest.mark.asyncio
async def test_start_stop_lifecycle():
    """Engine starts and stops cleanly."""
    loop = _make_loop()

    assert loop.running is False

    # Start in background
    task = asyncio.create_task(loop.start())
    await asyncio.sleep(0.1)
    assert loop.running is True

    # Stop
    await loop.stop()
    await asyncio.sleep(0.1)
    assert loop.running is False
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass


@pytest.mark.asyncio
async def test_watchlist_management():
    """Symbols can be added/removed from watchlist."""
    loop = _make_loop(watchlist=["AAPL", "MSFT"])
    assert loop._watchlist == ["AAPL", "MSFT"]

    loop.set_watchlist(["AAPL", "MSFT", "GOOGL", "NVDA"])
    assert len(loop._watchlist) == 4
    assert "NVDA" in loop._watchlist

    loop.set_watchlist(["AAPL"])
    assert loop._watchlist == ["AAPL"]


@pytest.mark.asyncio
async def test_market_state_change():
    """Market state can be updated at runtime."""
    loop = _make_loop(market_state="uptrend")
    assert loop._market_state == "uptrend"

    loop.set_market_state("downtrend")
    assert loop._market_state == "downtrend"

    loop.set_market_state("sideways")
    assert loop._market_state == "sideways"


@pytest.mark.asyncio
async def test_empty_watchlist_no_error():
    """Evaluation with empty watchlist doesn't error."""
    loop = _make_loop(watchlist=[])
    await loop._evaluate_all()  # should complete without error


@pytest.mark.asyncio
async def test_evaluate_all_calls_each_symbol():
    """Each symbol in watchlist gets evaluated."""
    adapter = PaperAdapter(initial_balance_usd=100_000)
    market_data = AsyncMock(spec=MarketDataService)
    market_data.get_ohlcv = AsyncMock(return_value=MagicMock(empty=True))

    loop = EvaluationLoop(
        adapter=adapter,
        market_data=market_data,
        indicator_svc=IndicatorService(),
        registry=StrategyRegistry(),
        combiner=SignalCombiner(),
        order_manager=OrderManager(adapter=adapter, risk_manager=RiskManager()),
        risk_manager=RiskManager(),
        watchlist=["AAPL", "MSFT", "GOOGL"],
    )

    await loop._evaluate_all()
    assert market_data.get_ohlcv.call_count == 3


@pytest.mark.asyncio
async def test_engine_status_api_integration():
    """Scheduler status reflects running state."""
    from engine.scheduler import TradingScheduler

    scheduler = TradingScheduler()
    assert scheduler.running is False

    status = scheduler.get_status()
    assert status["running"] is False
    assert "market_phase" in status
