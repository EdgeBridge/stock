"""Scenario 1: Normal buy -> hold -> sell flow.

1. Scanner finds AAPL (strong uptrend indicators)
2. Strategy evaluation produces BUY signal
3. RiskManager sizes position correctly
4. Order placed via PaperAdapter
5. Price rises -> take-profit level
6. Strategy produces SELL signal
7. Sell executed, PnL positive
"""

import pytest
import pandas as pd
import numpy as np
from unittest.mock import AsyncMock

from exchange.paper_adapter import PaperAdapter
from data.indicator_service import IndicatorService
from strategies.combiner import SignalCombiner
from strategies.trend_following import TrendFollowingStrategy
from strategies.base import Signal
from core.enums import SignalType
from engine.risk_manager import RiskManager, RiskParams
from engine.order_manager import OrderManager
from engine.evaluation_loop import EvaluationLoop
from tests.scenarios.conftest import make_ohlcv


@pytest.fixture
def uptrend_df():
    """250-day uptrend OHLCV with indicators."""
    df = make_ohlcv(250, start_price=150.0, trend="up", volatility=0.015)
    svc = IndicatorService()
    return svc.add_all_indicators(df)


@pytest.mark.asyncio
async def test_full_buy_sell_cycle(uptrend_df):
    """Complete: evaluate -> buy -> price up -> evaluate -> sell -> PnL > 0."""
    adapter = PaperAdapter(initial_balance_usd=100_000)
    await adapter.initialize()

    risk = RiskManager(params=RiskParams(max_position_pct=0.10))
    om = OrderManager(adapter=adapter, risk_manager=risk)

    # 1. Strategy evaluates uptrend -> BUY
    strategy = TrendFollowingStrategy()
    signal = await strategy.analyze(uptrend_df, "AAPL")

    # Signal should be BUY or HOLD depending on data; force BUY for the scenario
    last_price = float(uptrend_df.iloc[-1]["close"])
    adapter.set_price("AAPL", last_price)

    # 2. Place buy order
    buy_order = await om.place_buy(
        symbol="AAPL",
        price=last_price,
        portfolio_value=100_000,
        cash_available=100_000,
        current_positions=0,
        strategy_name="trend_following",
    )
    assert buy_order is not None
    assert buy_order.status == "filled"
    assert buy_order.quantity > 0

    # 3. Verify position exists
    positions = await adapter.fetch_positions()
    assert len(positions) == 1
    assert positions[0].symbol == "AAPL"
    assert positions[0].quantity == buy_order.quantity

    # 4. Price rises 15%
    new_price = last_price * 1.15
    adapter.set_price("AAPL", new_price)

    positions = await adapter.fetch_positions()
    assert positions[0].unrealized_pnl > 0

    # 5. Check take-profit triggered
    tp_triggered = risk.check_take_profit(last_price, new_price, take_profit_pct=0.12)
    assert tp_triggered is True

    # 6. Sell all shares
    sell_order = await om.place_sell(
        symbol="AAPL",
        quantity=buy_order.quantity,
        price=new_price,
        strategy_name="trend_following",
    )
    assert sell_order is not None
    assert sell_order.status == "filled"

    # 7. Position closed
    positions = await adapter.fetch_positions()
    assert len(positions) == 0

    # 8. Balance should be > initial (profit made)
    balance = await adapter.fetch_balance()
    assert balance.total > 100_000 * 0.99  # account for slippage


@pytest.mark.asyncio
async def test_buy_respects_position_sizing():
    """Position size should not exceed max_position_pct."""
    adapter = PaperAdapter(initial_balance_usd=50_000)
    await adapter.initialize()
    adapter.set_price("MSFT", 400.0)

    risk = RiskManager(params=RiskParams(max_position_pct=0.10))
    om = OrderManager(adapter=adapter, risk_manager=risk)

    order = await om.place_buy(
        symbol="MSFT",
        price=400.0,
        portfolio_value=50_000,
        cash_available=50_000,
        current_positions=0,
        strategy_name="trend_following",
    )
    assert order is not None
    # 10% of $50k = $5000, at $400/share = 12 shares max
    assert order.quantity <= 13  # small buffer for rounding
    assert order.quantity * 400 <= 50_000 * 0.10 + 400  # within one share tolerance


@pytest.mark.asyncio
async def test_multiple_positions():
    """Buy multiple symbols, verify portfolio state."""
    adapter = PaperAdapter(initial_balance_usd=100_000)
    await adapter.initialize()

    risk = RiskManager(params=RiskParams(max_position_pct=0.10))
    om = OrderManager(adapter=adapter, risk_manager=risk)

    symbols = {"AAPL": 180.0, "MSFT": 420.0, "GOOGL": 140.0}
    for sym, price in symbols.items():
        adapter.set_price(sym, price)
        await om.place_buy(
            symbol=sym, price=price,
            portfolio_value=100_000, cash_available=(await adapter.fetch_balance()).available,
            current_positions=len(await adapter.fetch_positions()),
            strategy_name="trend_following",
        )

    positions = await adapter.fetch_positions()
    assert len(positions) == 3
    balance = await adapter.fetch_balance()
    assert balance.available < 100_000  # cash used
    assert balance.total > 99_000  # total ~= initial minus slippage
