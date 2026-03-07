"""Shared fixtures for E2E scenario tests.

Provides a fully wired trading engine stack using PaperAdapter,
real strategies, and real risk/order management.
"""

import pytest
import pandas as pd
import numpy as np
from unittest.mock import AsyncMock, MagicMock

from exchange.paper_adapter import PaperAdapter
from data.market_data_service import MarketDataService
from data.indicator_service import IndicatorService
from strategies.combiner import SignalCombiner
from strategies.registry import StrategyRegistry
from strategies.config_loader import StrategyConfigLoader
from engine.risk_manager import RiskManager, RiskParams
from engine.order_manager import OrderManager
from engine.evaluation_loop import EvaluationLoop


def make_ohlcv(n=250, start_price=100.0, trend="up", volatility=0.02):
    """Generate realistic OHLCV DataFrame."""
    dates = pd.date_range("2023-01-01", periods=n, freq="B")
    prices = [start_price]
    for _ in range(n - 1):
        if trend == "up":
            drift = 0.001
        elif trend == "down":
            drift = -0.001
        else:
            drift = 0.0
        change = np.random.normal(drift, volatility)
        prices.append(prices[-1] * (1 + change))

    closes = np.array(prices)
    df = pd.DataFrame({
        "open": closes * (1 + np.random.uniform(-0.005, 0.005, n)),
        "high": closes * (1 + np.random.uniform(0.002, 0.015, n)),
        "low": closes * (1 - np.random.uniform(0.002, 0.015, n)),
        "close": closes,
        "volume": np.random.randint(500_000, 5_000_000, n).astype(float),
    }, index=dates)
    return df


@pytest.fixture
def paper_adapter():
    """PaperAdapter with $100k balance."""
    adapter = PaperAdapter(initial_balance_usd=100_000)
    return adapter


@pytest.fixture
def indicator_svc():
    return IndicatorService()


@pytest.fixture
def risk_manager():
    return RiskManager(params=RiskParams(
        max_position_pct=0.10,
        max_positions=20,
        daily_loss_limit_pct=0.03,
        default_stop_loss_pct=0.08,
        default_take_profit_pct=0.20,
    ))


@pytest.fixture
def order_manager(paper_adapter, risk_manager):
    return OrderManager(adapter=paper_adapter, risk_manager=risk_manager)


@pytest.fixture
def combiner():
    return SignalCombiner()


@pytest.fixture
def registry():
    """Load all enabled strategies from config."""
    return StrategyRegistry()


@pytest.fixture
def mock_market_data(paper_adapter):
    """MarketDataService with mocked get_ohlcv."""
    mds = MagicMock(spec=MarketDataService)
    return mds
