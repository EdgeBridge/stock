"""Backtest performance metrics calculator.

Computes CAGR, Sharpe, MDD, win rate, profit factor, etc.
from a series of trades and equity curve.
"""

import logging
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

TRADING_DAYS_PER_YEAR = 252
RISK_FREE_RATE = 0.04  # ~4% (US T-bill)


@dataclass
class Trade:
    symbol: str
    side: str  # BUY or SELL
    entry_date: str
    entry_price: float
    exit_date: str | None = None
    exit_price: float | None = None
    quantity: float = 0.0
    pnl: float = 0.0
    pnl_pct: float = 0.0
    holding_days: int = 0
    strategy_name: str = ""


@dataclass
class BacktestMetrics:
    # Returns
    total_return_pct: float = 0.0
    cagr: float = 0.0
    # Risk
    sharpe_ratio: float = 0.0
    sortino_ratio: float = 0.0
    max_drawdown_pct: float = 0.0
    max_drawdown_days: int = 0
    # Trade stats
    total_trades: int = 0
    winning_trades: int = 0
    losing_trades: int = 0
    win_rate: float = 0.0
    profit_factor: float = 0.0
    avg_win_pct: float = 0.0
    avg_loss_pct: float = 0.0
    avg_holding_days: float = 0.0
    # Benchmark
    benchmark_return_pct: float = 0.0
    alpha: float = 0.0
    # Summary
    start_date: str = ""
    end_date: str = ""
    trading_days: int = 0
    final_equity: float = 0.0
    initial_equity: float = 0.0

    def passes_minimum(
        self,
        min_cagr: float = 0.12,
        min_sharpe: float = 1.0,
        max_mdd: float = 0.25,
        min_win_rate: float = 0.45,
        min_profit_factor: float = 1.5,
    ) -> bool:
        """Check if backtest meets minimum criteria for live deployment."""
        return (
            self.cagr >= min_cagr
            and self.sharpe_ratio >= min_sharpe
            and abs(self.max_drawdown_pct) <= max_mdd * 100
            and self.win_rate >= min_win_rate * 100
            and self.profit_factor >= min_profit_factor
        )


class MetricsCalculator:
    """Calculate performance metrics from equity curve and trades."""

    @staticmethod
    def calculate(
        equity_curve: pd.Series,
        trades: list[Trade],
        initial_equity: float,
        benchmark_returns: pd.Series | None = None,
    ) -> BacktestMetrics:
        metrics = BacktestMetrics()

        if equity_curve.empty or len(equity_curve) < 2:
            return metrics

        metrics.initial_equity = initial_equity
        metrics.final_equity = float(equity_curve.iloc[-1])
        metrics.trading_days = len(equity_curve)
        metrics.start_date = str(equity_curve.index[0])
        metrics.end_date = str(equity_curve.index[-1])

        # Returns
        metrics.total_return_pct = (
            (metrics.final_equity - initial_equity) / initial_equity * 100
        )

        # CAGR
        years = metrics.trading_days / TRADING_DAYS_PER_YEAR
        if years > 0 and metrics.final_equity > 0:
            metrics.cagr = (metrics.final_equity / initial_equity) ** (1 / years) - 1

        # Daily returns
        daily_returns = equity_curve.pct_change().dropna()

        # Sharpe
        if len(daily_returns) > 1 and daily_returns.std() > 0:
            excess_return = daily_returns.mean() - RISK_FREE_RATE / TRADING_DAYS_PER_YEAR
            metrics.sharpe_ratio = (
                excess_return / daily_returns.std() * np.sqrt(TRADING_DAYS_PER_YEAR)
            )

        # Sortino
        downside = daily_returns[daily_returns < 0]
        if len(downside) > 1 and downside.std() > 0:
            excess_return = daily_returns.mean() - RISK_FREE_RATE / TRADING_DAYS_PER_YEAR
            metrics.sortino_ratio = (
                excess_return / downside.std() * np.sqrt(TRADING_DAYS_PER_YEAR)
            )

        # MDD
        cummax = equity_curve.cummax()
        drawdown = (equity_curve - cummax) / cummax
        metrics.max_drawdown_pct = float(drawdown.min() * 100)

        # MDD duration
        in_drawdown = drawdown < 0
        if in_drawdown.any():
            dd_groups = (~in_drawdown).cumsum()
            dd_lengths = in_drawdown.groupby(dd_groups).sum()
            metrics.max_drawdown_days = int(dd_lengths.max()) if len(dd_lengths) > 0 else 0

        # Trade stats
        metrics.total_trades = len(trades)
        if trades:
            winners = [t for t in trades if t.pnl > 0]
            losers = [t for t in trades if t.pnl <= 0]
            metrics.winning_trades = len(winners)
            metrics.losing_trades = len(losers)
            metrics.win_rate = len(winners) / len(trades) * 100

            gross_profit = sum(t.pnl for t in winners)
            gross_loss = abs(sum(t.pnl for t in losers))
            metrics.profit_factor = (
                min(gross_profit / gross_loss, 100.0) if gross_loss > 0 else (
                    100.0 if gross_profit > 0 else 0.0
                )
            )

            if winners:
                metrics.avg_win_pct = np.mean([t.pnl_pct for t in winners])
            if losers:
                metrics.avg_loss_pct = np.mean([t.pnl_pct for t in losers])

            metrics.avg_holding_days = np.mean([t.holding_days for t in trades])

        # Benchmark comparison
        if benchmark_returns is not None and not benchmark_returns.empty:
            bench_total = float((1 + benchmark_returns).prod() - 1) * 100
            metrics.benchmark_return_pct = bench_total
            metrics.alpha = metrics.total_return_pct - bench_total

        return metrics
