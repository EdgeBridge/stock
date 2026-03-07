"""Strategy parameter optimizer using grid search and walk-forward analysis."""

import itertools
import logging
import time
from dataclasses import dataclass, field

from backtest.engine import BacktestEngine, BacktestResult
from backtest.simulator import SimConfig
from strategies.base import BaseStrategy

logger = logging.getLogger(__name__)


@dataclass
class OptimizationResult:
    strategy_name: str
    best_params: dict
    best_metrics: dict  # sharpe, cagr, max_dd, win_rate
    all_results: list[dict]  # params + metrics for each combination
    optimization_time_sec: float


@dataclass
class WalkForwardSplit:
    """A single train/test split in walk-forward analysis."""
    split_index: int
    train_start: str
    train_end: str
    test_start: str
    test_end: str
    best_params: dict
    in_sample_metrics: dict
    out_of_sample_metrics: dict


@dataclass
class WalkForwardResult:
    strategy_name: str
    splits: list[WalkForwardSplit]
    avg_in_sample: dict   # averaged metrics across splits
    avg_out_of_sample: dict
    robustness_ratio: dict  # out-of-sample / in-sample for key metrics
    optimization_time_sec: float


class StrategyOptimizer:
    """Optimize strategy parameters via grid search and walk-forward analysis.

    Uses the existing BacktestEngine to evaluate each parameter combination,
    so all simulation logic (slippage, commission, position sizing) is reused.
    """

    def __init__(
        self,
        engine: BacktestEngine | None = None,
        sim_config: SimConfig | None = None,
    ):
        self._sim_config = sim_config or SimConfig()
        self._engine = engine or BacktestEngine(sim_config=self._sim_config)

    async def grid_search(
        self,
        strategy: BaseStrategy,
        symbol: str,
        param_grid: dict[str, list],
        period: str = "3y",
        start: str | None = None,
        end: str | None = None,
        metric: str = "sharpe_ratio",
    ) -> OptimizationResult:
        """Run backtest for each parameter combination, return best.

        Args:
            strategy: Strategy instance (params will be mutated via set_params).
            symbol: Stock ticker to backtest on.
            param_grid: Mapping of param name -> list of values to try.
                        Example: {"ema_fast": [10, 15, 20], "ema_slow": [40, 50, 60]}
            period: Data period when start/end not specified.
            start: Start date YYYY-MM-DD (overrides period).
            end: End date YYYY-MM-DD.
            metric: Metric to optimize (sharpe_ratio, cagr, win_rate, etc.).

        Returns:
            OptimizationResult with best params and full results grid.
        """
        combinations = self._generate_combinations(param_grid)
        if not combinations:
            raise ValueError("param_grid produced no combinations")

        original_params = strategy.get_params()
        all_results: list[dict] = []
        t0 = time.monotonic()

        for combo in combinations:
            strategy.set_params(combo)
            try:
                result = await self._engine.run(
                    strategy, symbol,
                    period=period, start=start, end=end,
                )
                metrics_dict = self._extract_metrics(result)
                all_results.append({"params": combo, **metrics_dict})
            except Exception as e:
                logger.warning(
                    "Grid search failed for params %s: %s", combo, e,
                )
                all_results.append({
                    "params": combo,
                    "error": str(e),
                    "sharpe_ratio": float("-inf"),
                    "cagr": float("-inf"),
                    "max_drawdown_pct": float("-inf"),
                    "win_rate": 0.0,
                })

        # Restore original parameters
        strategy.set_params(original_params)

        # Sort by target metric (descending — higher is better)
        valid = [r for r in all_results if "error" not in r]
        if not valid:
            raise RuntimeError("All parameter combinations failed")

        valid.sort(key=lambda r: r.get(metric, float("-inf")), reverse=True)
        best = valid[0]

        elapsed = time.monotonic() - t0
        logger.info(
            "Grid search complete: %d combos in %.1fs. Best %s=%.4f with %s",
            len(combinations), elapsed, metric, best[metric], best["params"],
        )

        return OptimizationResult(
            strategy_name=strategy.name,
            best_params=best["params"],
            best_metrics={
                k: v for k, v in best.items() if k != "params"
            },
            all_results=all_results,
            optimization_time_sec=elapsed,
        )

    async def walk_forward(
        self,
        strategy: BaseStrategy,
        symbol: str,
        param_grid: dict[str, list],
        total_period: str = "5y",
        train_pct: float = 0.7,
        n_splits: int = 3,
        metric: str = "sharpe_ratio",
        start: str | None = None,
        end: str | None = None,
    ) -> WalkForwardResult:
        """Walk-forward optimization to reduce overfitting.

        Splits the total date range into overlapping train/test windows.
        For each split, optimizes on train and validates on test.

        Args:
            strategy: Strategy instance.
            symbol: Stock ticker.
            param_grid: Parameter grid for optimization.
            total_period: Total data period (used if start not given).
            train_pct: Fraction of each window used for training (0.5-0.9).
            n_splits: Number of walk-forward splits.
            metric: Optimization target metric.
            start: Start date YYYY-MM-DD (overrides total_period).
            end: End date YYYY-MM-DD.

        Returns:
            WalkForwardResult with per-split and aggregate results.
        """
        if not 0.3 <= train_pct <= 0.9:
            raise ValueError("train_pct must be between 0.3 and 0.9")
        if n_splits < 1:
            raise ValueError("n_splits must be >= 1")

        # Load data to determine date range
        data = self._engine._data_loader.load(
            symbol, period=total_period, start=start, end=end,
        )
        dates = data.df.index
        n_total = len(dates)

        if n_total < 60:
            raise ValueError(
                f"Insufficient data: {n_total} bars (need at least 60)"
            )

        # Calculate window sizes
        window_size = n_total // n_splits
        train_size = int(window_size * train_pct)
        test_size = window_size - train_size

        if train_size < 30 or test_size < 10:
            raise ValueError(
                f"Window too small: train={train_size}, test={test_size} bars. "
                "Reduce n_splits or increase data period."
            )

        original_params = strategy.get_params()
        splits: list[WalkForwardSplit] = []
        t0 = time.monotonic()

        for i in range(n_splits):
            split_start = i * window_size
            train_end_idx = split_start + train_size
            test_end_idx = min(split_start + window_size, n_total)

            train_start_date = str(dates[split_start].date())
            train_end_date = str(dates[train_end_idx - 1].date())
            test_start_date = str(dates[train_end_idx].date())
            test_end_date = str(dates[test_end_idx - 1].date())

            # Optimize on training window
            train_result = await self.grid_search(
                strategy, symbol, param_grid,
                start=train_start_date, end=train_end_date,
                metric=metric,
            )

            # Validate best params on test window
            strategy.set_params(train_result.best_params)
            try:
                test_backtest = await self._engine.run(
                    strategy, symbol,
                    start=test_start_date, end=test_end_date,
                )
                oos_metrics = self._extract_metrics(test_backtest)
            except Exception as e:
                logger.warning("Walk-forward test split %d failed: %s", i, e)
                oos_metrics = {
                    "sharpe_ratio": 0.0,
                    "cagr": 0.0,
                    "max_drawdown_pct": 0.0,
                    "win_rate": 0.0,
                }

            splits.append(WalkForwardSplit(
                split_index=i,
                train_start=train_start_date,
                train_end=train_end_date,
                test_start=test_start_date,
                test_end=test_end_date,
                best_params=train_result.best_params,
                in_sample_metrics=train_result.best_metrics,
                out_of_sample_metrics=oos_metrics,
            ))

        # Restore original parameters
        strategy.set_params(original_params)

        # Aggregate metrics
        avg_is = self._average_metrics([s.in_sample_metrics for s in splits])
        avg_oos = self._average_metrics([s.out_of_sample_metrics for s in splits])
        robustness = self._calc_robustness(avg_is, avg_oos)

        elapsed = time.monotonic() - t0
        logger.info(
            "Walk-forward complete: %d splits in %.1fs. "
            "Robustness ratio (sharpe): %.2f",
            n_splits, elapsed, robustness.get("sharpe_ratio", 0),
        )

        return WalkForwardResult(
            strategy_name=strategy.name,
            splits=splits,
            avg_in_sample=avg_is,
            avg_out_of_sample=avg_oos,
            robustness_ratio=robustness,
            optimization_time_sec=elapsed,
        )

    def _generate_combinations(self, param_grid: dict[str, list]) -> list[dict]:
        """Generate all parameter combinations from grid."""
        if not param_grid:
            return []

        keys = list(param_grid.keys())
        values = list(param_grid.values())
        return [
            dict(zip(keys, combo))
            for combo in itertools.product(*values)
        ]

    @staticmethod
    def _extract_metrics(result: BacktestResult) -> dict:
        """Extract key metrics from a BacktestResult."""
        m = result.metrics
        return {
            "sharpe_ratio": m.sharpe_ratio,
            "cagr": m.cagr,
            "max_drawdown_pct": m.max_drawdown_pct,
            "win_rate": m.win_rate,
            "sortino_ratio": m.sortino_ratio,
            "total_return_pct": m.total_return_pct,
            "profit_factor": m.profit_factor,
            "total_trades": m.total_trades,
        }

    @staticmethod
    def _average_metrics(metrics_list: list[dict]) -> dict:
        """Average numeric metrics across splits."""
        if not metrics_list:
            return {}

        keys = [
            k for k in metrics_list[0]
            if isinstance(metrics_list[0][k], (int, float))
        ]
        result = {}
        for key in keys:
            values = [m.get(key, 0) for m in metrics_list]
            result[key] = sum(values) / len(values) if values else 0.0
        return result

    @staticmethod
    def _calc_robustness(avg_is: dict, avg_oos: dict) -> dict:
        """Calculate out-of-sample / in-sample ratio for key metrics.

        A ratio close to 1.0 indicates robust parameters (no overfitting).
        Ratios well below 1.0 suggest overfitting.
        """
        robustness = {}
        for key in ("sharpe_ratio", "cagr", "win_rate", "profit_factor"):
            is_val = avg_is.get(key, 0)
            oos_val = avg_oos.get(key, 0)
            if is_val and is_val != 0:
                robustness[key] = oos_val / is_val
            else:
                robustness[key] = 0.0
        return robustness
