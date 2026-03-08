"""Scenario 6: API failure and recovery.

1. Exchange adapter raises exception on order
2. OrderManager handles error gracefully (returns None)
3. Evaluation loop catches and logs errors
4. After recovery, normal operation resumes
5. Rate limiter still functions after errors
"""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock

from exchange.paper_adapter import PaperAdapter
from exchange.base import Balance, OrderResult
from engine.risk_manager import RiskManager
from engine.order_manager import OrderManager
from engine.evaluation_loop import EvaluationLoop
from data.indicator_service import IndicatorService
from data.market_data_service import MarketDataService
from strategies.combiner import SignalCombiner
from strategies.registry import StrategyRegistry
from services.rate_limiter import RateLimiter


@pytest.mark.asyncio
async def test_order_failure_returns_none():
    """OrderManager returns None when adapter raises."""
    adapter = AsyncMock()
    adapter.create_buy_order.side_effect = ConnectionError("KIS API timeout")

    risk = RiskManager()
    om = OrderManager(adapter=adapter, risk_manager=risk)

    result = await om.place_buy(
        symbol="AAPL", price=180.0,
        portfolio_value=100_000, cash_available=100_000,
        current_positions=0, strategy_name="test",
    )
    assert result is None


@pytest.mark.asyncio
async def test_sell_failure_returns_none():
    """OrderManager returns None when sell fails."""
    adapter = AsyncMock()
    adapter.create_sell_order.side_effect = Exception("Network error")

    risk = RiskManager()
    om = OrderManager(adapter=adapter, risk_manager=risk)

    result = await om.place_sell(
        symbol="AAPL", quantity=10, price=180.0,
        strategy_name="test",
    )
    assert result is None


@pytest.mark.asyncio
async def test_evaluation_loop_survives_ohlcv_error():
    """Evaluation loop continues after market data error."""
    adapter = PaperAdapter(initial_balance_usd=100_000)
    await adapter.initialize()

    market_data = AsyncMock(spec=MarketDataService)
    # Factor score update calls get_ohlcv for each symbol first (2 calls),
    # then evaluate_symbol calls for each symbol (2 calls) = 4 total
    market_data.get_ohlcv = AsyncMock(side_effect=[
        ConnectionError("API down"),  # factor: AAPL
        MagicMock(empty=True),        # factor: MSFT
        MagicMock(empty=True),        # evaluate: AAPL
        MagicMock(empty=True),        # evaluate: MSFT
    ])

    loop = EvaluationLoop(
        adapter=adapter,
        market_data=market_data,
        indicator_svc=IndicatorService(),
        registry=StrategyRegistry(),
        combiner=SignalCombiner(),
        order_manager=OrderManager(adapter=adapter, risk_manager=RiskManager()),
        risk_manager=RiskManager(),
        watchlist=["AAPL", "MSFT"],
    )

    # Should not raise despite errors
    await loop._evaluate_all()
    assert market_data.get_ohlcv.call_count == 4


@pytest.mark.asyncio
async def test_recovery_after_failure():
    """After API failure, subsequent operations work normally."""
    adapter = PaperAdapter(initial_balance_usd=100_000)
    await adapter.initialize()

    risk = RiskManager()
    om = OrderManager(adapter=adapter, risk_manager=risk)

    # Simulate temporary failure by patching
    original_create = adapter.create_buy_order

    call_count = 0

    async def flaky_buy(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            raise ConnectionError("Temporary failure")
        return await original_create(*args, **kwargs)

    adapter.create_buy_order = flaky_buy

    # First attempt fails
    adapter.set_price("AAPL", 180.0)
    result1 = await om.place_buy(
        symbol="AAPL", price=180.0,
        portfolio_value=100_000, cash_available=100_000,
        current_positions=0, strategy_name="test",
    )
    assert result1 is None

    # Second attempt succeeds
    result2 = await om.place_buy(
        symbol="AAPL", price=180.0,
        portfolio_value=100_000, cash_available=100_000,
        current_positions=0, strategy_name="test",
    )
    assert result2 is not None
    assert result2.status == "filled"


@pytest.mark.asyncio
async def test_rate_limiter_survives_errors():
    """Rate limiter doesn't break after exceptions in operations."""
    limiter = RateLimiter(max_per_second=10)

    # Normal acquire
    await limiter.acquire()

    # Simulate error in between
    try:
        raise ConnectionError("API down")
    except ConnectionError:
        pass

    # Rate limiter should still work
    await limiter.acquire()
    assert True  # no exception means success


@pytest.mark.asyncio
async def test_cancel_order_failure_handled():
    """Cancel order failure doesn't crash."""
    adapter = AsyncMock()
    adapter.cancel_order.side_effect = Exception("Cancel failed")

    risk = RiskManager()
    om = OrderManager(adapter=adapter, risk_manager=risk)

    result = await om.cancel("fake-id", "AAPL")
    assert result is False
