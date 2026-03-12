"""Tests for backtest metrics calculator."""

import numpy as np
import pandas as pd
import pytest

from backtest.metrics import MetricsCalculator, BacktestMetrics, Trade


def _make_equity_curve(
    initial: float = 100_000,
    days: int = 252,
    daily_return: float = 0.0005,
    volatility: float = 0.01,
) -> pd.Series:
    """Generate synthetic equity curve."""
    np.random.seed(42)
    returns = np.random.normal(daily_return, volatility, days)
    prices = initial * np.cumprod(1 + returns)
    dates = pd.bdate_range("2021-01-01", periods=days)
    return pd.Series(prices, index=dates)


def _make_trades(n_winners: int = 6, n_losers: int = 4) -> list[Trade]:
    """Generate sample trades."""
    trades = []
    for i in range(n_winners):
        trades.append(Trade(
            symbol="AAPL", side="SELL",
            entry_date="2021-01-01", entry_price=100.0,
            exit_date="2021-02-01", exit_price=110.0,
            quantity=10, pnl=100.0, pnl_pct=10.0,
            holding_days=30, strategy_name="test",
        ))
    for i in range(n_losers):
        trades.append(Trade(
            symbol="AAPL", side="SELL",
            entry_date="2021-01-01", entry_price=100.0,
            exit_date="2021-02-01", exit_price=95.0,
            quantity=10, pnl=-50.0, pnl_pct=-5.0,
            holding_days=30, strategy_name="test",
        ))
    return trades


class TestMetricsCalculator:
    def test_basic_metrics(self):
        curve = _make_equity_curve()
        trades = _make_trades()
        metrics = MetricsCalculator.calculate(curve, trades, 100_000)

        assert metrics.total_trades == 10
        assert metrics.winning_trades == 6
        assert metrics.losing_trades == 4
        assert metrics.win_rate == 60.0
        assert metrics.initial_equity == 100_000
        assert metrics.final_equity > 0
        assert metrics.trading_days == 252

    def test_cagr_positive(self):
        curve = _make_equity_curve(daily_return=0.001)
        metrics = MetricsCalculator.calculate(curve, [], 100_000)
        assert metrics.cagr > 0

    def test_sharpe_ratio(self):
        curve = _make_equity_curve(daily_return=0.001, volatility=0.005)
        metrics = MetricsCalculator.calculate(curve, [], 100_000)
        assert metrics.sharpe_ratio > 0

    def test_sortino_ratio(self):
        curve = _make_equity_curve(daily_return=0.001)
        metrics = MetricsCalculator.calculate(curve, [], 100_000)
        assert metrics.sortino_ratio > 0

    def test_mdd_negative(self):
        curve = _make_equity_curve()
        metrics = MetricsCalculator.calculate(curve, [], 100_000)
        assert metrics.max_drawdown_pct <= 0  # MDD is always negative or zero

    def test_profit_factor(self):
        trades = _make_trades(n_winners=6, n_losers=4)
        curve = _make_equity_curve()
        metrics = MetricsCalculator.calculate(curve, trades, 100_000)
        # 6 * 100 = 600 gross profit, 4 * 50 = 200 gross loss → PF = 3.0
        assert metrics.profit_factor == pytest.approx(3.0)

    def test_avg_win_loss(self):
        trades = _make_trades()
        curve = _make_equity_curve()
        metrics = MetricsCalculator.calculate(curve, trades, 100_000)
        assert metrics.avg_win_pct == pytest.approx(10.0)
        assert metrics.avg_loss_pct == pytest.approx(-5.0)

    def test_avg_holding_days(self):
        trades = _make_trades()
        curve = _make_equity_curve()
        metrics = MetricsCalculator.calculate(curve, trades, 100_000)
        assert metrics.avg_holding_days == 30.0

    def test_empty_curve(self):
        metrics = MetricsCalculator.calculate(pd.Series(dtype=float), [], 100_000)
        assert metrics.total_return_pct == 0.0
        assert metrics.cagr == 0.0

    def test_no_trades(self):
        curve = _make_equity_curve()
        metrics = MetricsCalculator.calculate(curve, [], 100_000)
        assert metrics.total_trades == 0
        assert metrics.win_rate == 0.0
        assert metrics.profit_factor == 0.0

    def test_all_winners(self):
        trades = _make_trades(n_winners=5, n_losers=0)
        curve = _make_equity_curve()
        metrics = MetricsCalculator.calculate(curve, trades, 100_000)
        assert metrics.win_rate == 100.0
        assert metrics.profit_factor == 100.0

    def test_benchmark_comparison(self):
        curve = _make_equity_curve(daily_return=0.001)
        np.random.seed(99)
        bench = pd.Series(
            np.random.normal(0.0003, 0.01, 252),
            index=pd.bdate_range("2021-01-01", periods=252),
        )
        metrics = MetricsCalculator.calculate(curve, [], 100_000, benchmark_returns=bench)
        assert metrics.benchmark_return_pct != 0
        assert metrics.alpha != 0


class TestBacktestMetrics:
    def test_passes_minimum_good(self):
        m = BacktestMetrics(
            cagr=0.15, sharpe_ratio=1.5, max_drawdown_pct=-20.0,
            win_rate=55.0, profit_factor=2.0,
        )
        assert m.passes_minimum() is True

    def test_fails_cagr(self):
        m = BacktestMetrics(
            cagr=0.05, sharpe_ratio=1.5, max_drawdown_pct=-20.0,
            win_rate=55.0, profit_factor=2.0,
        )
        assert m.passes_minimum() is False

    def test_fails_sharpe(self):
        m = BacktestMetrics(
            cagr=0.15, sharpe_ratio=0.5, max_drawdown_pct=-20.0,
            win_rate=55.0, profit_factor=2.0,
        )
        assert m.passes_minimum() is False

    def test_fails_mdd(self):
        m = BacktestMetrics(
            cagr=0.15, sharpe_ratio=1.5, max_drawdown_pct=-30.0,
            win_rate=55.0, profit_factor=2.0,
        )
        assert m.passes_minimum() is False

    def test_fails_win_rate(self):
        m = BacktestMetrics(
            cagr=0.15, sharpe_ratio=1.5, max_drawdown_pct=-20.0,
            win_rate=30.0, profit_factor=2.0,
        )
        assert m.passes_minimum() is False

    def test_fails_profit_factor(self):
        m = BacktestMetrics(
            cagr=0.15, sharpe_ratio=1.5, max_drawdown_pct=-20.0,
            win_rate=55.0, profit_factor=1.2,
        )
        assert m.passes_minimum() is False

    def test_custom_thresholds(self):
        m = BacktestMetrics(
            cagr=0.08, sharpe_ratio=0.8, max_drawdown_pct=-15.0,
            win_rate=40.0, profit_factor=1.3,
        )
        assert m.passes_minimum(
            min_cagr=0.05, min_sharpe=0.7, max_mdd=0.20,
            min_win_rate=0.35, min_profit_factor=1.2,
        ) is True


class TestTrade:
    def test_trade_defaults(self):
        t = Trade(symbol="AAPL", side="BUY", entry_date="2021-01-01", entry_price=150.0)
        assert t.exit_date is None
        assert t.pnl == 0.0
        assert t.holding_days == 0
