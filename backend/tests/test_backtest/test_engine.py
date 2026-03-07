"""Tests for backtest engine orchestrator."""

from unittest.mock import AsyncMock, MagicMock, patch

import numpy as np
import pandas as pd
import pytest

from backtest.engine import BacktestEngine, BacktestResult
from backtest.data_loader import BacktestData
from backtest.simulator import SimConfig
from backtest.metrics import BacktestMetrics, Trade
from strategies.base import BaseStrategy, Signal
from core.enums import SignalType


class MockStrategy(BaseStrategy):
    """Simple test strategy that alternates BUY/SELL."""

    name = "mock_strategy"
    display_name = "Mock Strategy"
    applicable_market_types = ["stock"]
    required_timeframe = "1D"
    min_candles_required = 10

    def __init__(self):
        self._buy_next = True

    async def analyze(self, df: pd.DataFrame, symbol: str) -> Signal:
        if self._buy_next:
            self._buy_next = False
            return Signal(
                signal_type=SignalType.BUY,
                confidence=0.8,
                strategy_name=self.name,
                reason="test buy",
            )
        else:
            self._buy_next = True
            return Signal(
                signal_type=SignalType.SELL,
                confidence=0.8,
                strategy_name=self.name,
                reason="test sell",
            )

    def get_params(self) -> dict:
        return {"test": True}

    def set_params(self, params: dict) -> None:
        pass


class HoldStrategy(BaseStrategy):
    """Strategy that always holds."""
    name = "hold_strategy"
    display_name = "Hold"
    applicable_market_types = ["stock"]
    required_timeframe = "1D"
    min_candles_required = 5

    async def analyze(self, df: pd.DataFrame, symbol: str) -> Signal:
        return Signal(
            signal_type=SignalType.HOLD,
            confidence=0.5,
            strategy_name=self.name,
            reason="hold",
        )

    def get_params(self) -> dict:
        return {}

    def set_params(self, params: dict) -> None:
        pass


def _make_backtest_data(symbol: str = "AAPL", n: int = 100) -> BacktestData:
    np.random.seed(42)
    prices = 100 * np.cumprod(1 + np.random.normal(0.001, 0.01, n))
    dates = pd.bdate_range("2021-01-01", periods=n)
    df = pd.DataFrame({
        "open": prices * 0.999,
        "high": prices * 1.01,
        "low": prices * 0.99,
        "close": prices,
        "volume": np.random.randint(100_000, 500_000, n).astype(float),
    }, index=dates)
    return BacktestData(
        symbol=symbol,
        df=df,
        start_date=str(dates[0].date()),
        end_date=str(dates[-1].date()),
    )


class TestBacktestEngine:
    @patch("backtest.engine.BacktestDataLoader")
    async def test_run_basic(self, mock_loader_cls):
        data = _make_backtest_data()
        mock_loader = MagicMock()
        mock_loader.load.return_value = data
        mock_loader_cls.return_value = mock_loader

        engine = BacktestEngine(data_loader=mock_loader)
        strategy = MockStrategy()

        result = await engine.run(strategy, "AAPL", period="3y")

        assert isinstance(result, BacktestResult)
        assert result.symbol == "AAPL"
        assert result.strategy_name == "mock_strategy"
        assert result.metrics.trading_days > 0
        assert len(result.trades) > 0

    @patch("backtest.engine.BacktestDataLoader")
    async def test_run_with_hold_strategy(self, mock_loader_cls):
        data = _make_backtest_data()
        mock_loader = MagicMock()
        mock_loader.load.return_value = data
        mock_loader_cls.return_value = mock_loader

        engine = BacktestEngine(data_loader=mock_loader)
        result = await engine.run(HoldStrategy(), "AAPL")

        assert result.metrics.total_trades == 0

    @patch("backtest.engine.BacktestDataLoader")
    async def test_run_multiple(self, mock_loader_cls):
        mock_loader = MagicMock()
        mock_loader.load.side_effect = [
            _make_backtest_data("AAPL"),
            _make_backtest_data("TSLA"),
        ]
        mock_loader_cls.return_value = mock_loader

        engine = BacktestEngine(data_loader=mock_loader)
        results = await engine.run_multiple(MockStrategy(), ["AAPL", "TSLA"])

        assert len(results) == 2
        assert results[0].symbol == "AAPL"
        assert results[1].symbol == "TSLA"

    @patch("backtest.engine.BacktestDataLoader")
    async def test_run_multiple_partial_failure(self, mock_loader_cls):
        mock_loader = MagicMock()
        mock_loader.load.side_effect = [
            _make_backtest_data("AAPL"),
            ValueError("No data"),
        ]
        mock_loader_cls.return_value = mock_loader

        engine = BacktestEngine(data_loader=mock_loader)
        results = await engine.run_multiple(MockStrategy(), ["AAPL", "FAIL"])

        assert len(results) == 1
        assert results[0].symbol == "AAPL"

    @patch("backtest.engine.BacktestDataLoader")
    async def test_custom_sim_config(self, mock_loader_cls):
        data = _make_backtest_data()
        mock_loader = MagicMock()
        mock_loader.load.return_value = data

        config = SimConfig(initial_equity=50_000, slippage_pct=0.1)
        engine = BacktestEngine(data_loader=mock_loader, sim_config=config)
        result = await engine.run(MockStrategy(), "AAPL")

        assert result.metrics.initial_equity == 50_000


class TestBacktestResult:
    def test_summary(self):
        result = BacktestResult(
            symbol="AAPL",
            strategy_name="test",
            metrics=BacktestMetrics(
                total_return_pct=25.0, cagr=0.15,
                sharpe_ratio=1.5, sortino_ratio=2.0,
                max_drawdown_pct=-15.0, max_drawdown_days=30,
                total_trades=20, win_rate=60.0,
                profit_factor=2.0, final_equity=125_000,
                start_date="2021-01-01", end_date="2023-12-31",
                trading_days=756,
            ),
            trades=[],
            equity_curve=pd.Series(dtype=float),
        )
        summary = result.summary()
        assert "PASS" in summary
        assert "AAPL" in summary
        assert "15.0%" in summary

    def test_passed_true(self):
        result = BacktestResult(
            symbol="AAPL",
            strategy_name="test",
            metrics=BacktestMetrics(
                cagr=0.15, sharpe_ratio=1.5, max_drawdown_pct=-20.0,
                win_rate=55.0, profit_factor=2.0,
            ),
            trades=[], equity_curve=pd.Series(dtype=float),
        )
        assert result.passed is True

    def test_passed_false(self):
        result = BacktestResult(
            symbol="AAPL",
            strategy_name="test",
            metrics=BacktestMetrics(
                cagr=0.05, sharpe_ratio=0.5, max_drawdown_pct=-30.0,
                win_rate=30.0, profit_factor=1.0,
            ),
            trades=[], equity_curve=pd.Series(dtype=float),
        )
        assert result.passed is False
