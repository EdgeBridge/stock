"""Tests for strategy parameter optimizer."""

from unittest.mock import AsyncMock, MagicMock, patch

import numpy as np
import pandas as pd
import pytest

from backtest.engine import BacktestEngine, BacktestResult
from backtest.metrics import BacktestMetrics, Trade
from backtest.optimizer import (
    OptimizationResult,
    StrategyOptimizer,
    WalkForwardResult,
    WalkForwardSplit,
)
from backtest.simulator import SimConfig
from strategies.base import BaseStrategy, Signal
from core.enums import SignalType


# ---------------------------------------------------------------------------
# Test helpers
# ---------------------------------------------------------------------------

class FakeStrategy(BaseStrategy):
    """Strategy with tunable params for optimization tests."""

    name = "fake_strategy"
    display_name = "Fake"
    applicable_market_types = ["all"]
    required_timeframe = "1D"
    min_candles_required = 10

    def __init__(self, params: dict | None = None):
        p = params or {}
        self._ema_fast = p.get("ema_fast", 10)
        self._ema_slow = p.get("ema_slow", 50)
        self._threshold = p.get("threshold", 0.5)

    async def analyze(self, df: pd.DataFrame, symbol: str) -> Signal:
        return Signal(
            signal_type=SignalType.HOLD,
            confidence=0.0,
            strategy_name=self.name,
            reason="fake",
        )

    def get_params(self) -> dict:
        return {
            "ema_fast": self._ema_fast,
            "ema_slow": self._ema_slow,
            "threshold": self._threshold,
        }

    def set_params(self, params: dict) -> None:
        self._ema_fast = params.get("ema_fast", self._ema_fast)
        self._ema_slow = params.get("ema_slow", self._ema_slow)
        self._threshold = params.get("threshold", self._threshold)


def _make_backtest_result(
    sharpe: float = 1.5,
    cagr: float = 0.15,
    max_dd: float = -10.0,
    win_rate: float = 55.0,
    total_trades: int = 20,
) -> BacktestResult:
    """Create a BacktestResult with specified metrics."""
    return BacktestResult(
        symbol="AAPL",
        strategy_name="fake_strategy",
        metrics=BacktestMetrics(
            sharpe_ratio=sharpe,
            cagr=cagr,
            max_drawdown_pct=max_dd,
            win_rate=win_rate,
            total_trades=total_trades,
            sortino_ratio=sharpe * 1.2,
            total_return_pct=cagr * 300,
            profit_factor=1.8,
        ),
        trades=[],
        equity_curve=pd.Series(dtype=float),
    )


def _make_backtest_data_df(n: int = 252) -> pd.DataFrame:
    """Create a simple OHLCV DataFrame for testing."""
    np.random.seed(42)
    prices = 100 * np.cumprod(1 + np.random.normal(0.001, 0.01, n))
    dates = pd.bdate_range("2020-01-01", periods=n)
    return pd.DataFrame({
        "open": prices * 0.999,
        "high": prices * 1.01,
        "low": prices * 0.99,
        "close": prices,
        "volume": np.random.randint(100_000, 500_000, n).astype(float),
    }, index=dates)


# ---------------------------------------------------------------------------
# _generate_combinations tests
# ---------------------------------------------------------------------------

class TestGenerateCombinations:
    def test_single_param(self):
        optimizer = StrategyOptimizer()
        combos = optimizer._generate_combinations({"ema_fast": [10, 20, 30]})
        assert len(combos) == 3
        assert combos[0] == {"ema_fast": 10}
        assert combos[1] == {"ema_fast": 20}
        assert combos[2] == {"ema_fast": 30}

    def test_two_params(self):
        optimizer = StrategyOptimizer()
        combos = optimizer._generate_combinations({
            "ema_fast": [10, 20],
            "ema_slow": [40, 50],
        })
        assert len(combos) == 4
        assert {"ema_fast": 10, "ema_slow": 40} in combos
        assert {"ema_fast": 10, "ema_slow": 50} in combos
        assert {"ema_fast": 20, "ema_slow": 40} in combos
        assert {"ema_fast": 20, "ema_slow": 50} in combos

    def test_three_params(self):
        optimizer = StrategyOptimizer()
        combos = optimizer._generate_combinations({
            "a": [1, 2],
            "b": [3, 4],
            "c": [5, 6],
        })
        assert len(combos) == 8  # 2 * 2 * 2

    def test_empty_grid(self):
        optimizer = StrategyOptimizer()
        combos = optimizer._generate_combinations({})
        assert combos == []

    def test_single_value_per_param(self):
        optimizer = StrategyOptimizer()
        combos = optimizer._generate_combinations({
            "ema_fast": [10],
            "ema_slow": [50],
        })
        assert len(combos) == 1
        assert combos[0] == {"ema_fast": 10, "ema_slow": 50}

    def test_preserves_param_order(self):
        optimizer = StrategyOptimizer()
        combos = optimizer._generate_combinations({
            "alpha": [1],
            "beta": [2],
            "gamma": [3],
        })
        assert list(combos[0].keys()) == ["alpha", "beta", "gamma"]


# ---------------------------------------------------------------------------
# _extract_metrics tests
# ---------------------------------------------------------------------------

class TestExtractMetrics:
    def test_extracts_all_key_metrics(self):
        result = _make_backtest_result(sharpe=2.0, cagr=0.20)
        metrics = StrategyOptimizer._extract_metrics(result)

        assert metrics["sharpe_ratio"] == 2.0
        assert metrics["cagr"] == 0.20
        assert "max_drawdown_pct" in metrics
        assert "win_rate" in metrics
        assert "sortino_ratio" in metrics
        assert "total_return_pct" in metrics
        assert "profit_factor" in metrics
        assert "total_trades" in metrics


# ---------------------------------------------------------------------------
# _average_metrics tests
# ---------------------------------------------------------------------------

class TestAverageMetrics:
    def test_averages_correctly(self):
        metrics_list = [
            {"sharpe_ratio": 1.0, "cagr": 0.10},
            {"sharpe_ratio": 2.0, "cagr": 0.20},
            {"sharpe_ratio": 3.0, "cagr": 0.30},
        ]
        avg = StrategyOptimizer._average_metrics(metrics_list)
        assert avg["sharpe_ratio"] == pytest.approx(2.0)
        assert avg["cagr"] == pytest.approx(0.20)

    def test_empty_list(self):
        assert StrategyOptimizer._average_metrics([]) == {}

    def test_single_entry(self):
        avg = StrategyOptimizer._average_metrics([{"sharpe_ratio": 1.5}])
        assert avg["sharpe_ratio"] == pytest.approx(1.5)

    def test_ignores_non_numeric(self):
        avg = StrategyOptimizer._average_metrics([
            {"sharpe_ratio": 1.0, "error": "bad"},
            {"sharpe_ratio": 2.0, "error": "also bad"},
        ])
        assert "sharpe_ratio" in avg
        assert "error" not in avg


# ---------------------------------------------------------------------------
# _calc_robustness tests
# ---------------------------------------------------------------------------

class TestCalcRobustness:
    def test_perfect_robustness(self):
        metrics = {"sharpe_ratio": 2.0, "cagr": 0.15, "win_rate": 60.0, "profit_factor": 2.0}
        rob = StrategyOptimizer._calc_robustness(metrics, metrics)
        assert rob["sharpe_ratio"] == pytest.approx(1.0)
        assert rob["cagr"] == pytest.approx(1.0)

    def test_overfitting(self):
        is_metrics = {"sharpe_ratio": 3.0, "cagr": 0.30, "win_rate": 70.0, "profit_factor": 3.0}
        oos_metrics = {"sharpe_ratio": 0.5, "cagr": 0.05, "win_rate": 40.0, "profit_factor": 0.8}
        rob = StrategyOptimizer._calc_robustness(is_metrics, oos_metrics)
        assert rob["sharpe_ratio"] < 0.5
        assert rob["cagr"] < 0.5

    def test_zero_in_sample(self):
        is_metrics = {"sharpe_ratio": 0.0, "cagr": 0.0, "win_rate": 0.0, "profit_factor": 0.0}
        oos_metrics = {"sharpe_ratio": 1.0, "cagr": 0.1, "win_rate": 50.0, "profit_factor": 1.5}
        rob = StrategyOptimizer._calc_robustness(is_metrics, oos_metrics)
        assert rob["sharpe_ratio"] == 0.0  # graceful handling


# ---------------------------------------------------------------------------
# grid_search tests
# ---------------------------------------------------------------------------

class TestGridSearch:
    async def test_finds_best_params(self):
        """Grid search returns params with highest target metric."""
        strategy = FakeStrategy()
        engine = MagicMock(spec=BacktestEngine)

        # Each combo gets a different sharpe: higher ema_fast -> higher sharpe
        results = [
            _make_backtest_result(sharpe=1.0),  # ema_fast=10
            _make_backtest_result(sharpe=2.0),  # ema_fast=20
            _make_backtest_result(sharpe=3.0),  # ema_fast=30
        ]
        engine.run = AsyncMock(side_effect=results)

        optimizer = StrategyOptimizer(engine=engine)
        result = await optimizer.grid_search(
            strategy, "AAPL",
            param_grid={"ema_fast": [10, 20, 30]},
            metric="sharpe_ratio",
        )

        assert isinstance(result, OptimizationResult)
        assert result.best_params["ema_fast"] == 30
        assert result.best_metrics["sharpe_ratio"] == 3.0
        assert result.strategy_name == "fake_strategy"
        assert len(result.all_results) == 3
        assert result.optimization_time_sec >= 0

    async def test_multiple_params(self):
        """Grid search works with multiple parameters (cartesian product)."""
        strategy = FakeStrategy()
        engine = MagicMock(spec=BacktestEngine)

        # 2 x 2 = 4 combinations
        results = [
            _make_backtest_result(sharpe=1.0),
            _make_backtest_result(sharpe=1.5),
            _make_backtest_result(sharpe=2.5),
            _make_backtest_result(sharpe=2.0),
        ]
        engine.run = AsyncMock(side_effect=results)

        optimizer = StrategyOptimizer(engine=engine)
        result = await optimizer.grid_search(
            strategy, "AAPL",
            param_grid={"ema_fast": [10, 20], "ema_slow": [40, 50]},
        )

        assert len(result.all_results) == 4
        assert result.best_metrics["sharpe_ratio"] == 2.5
        assert engine.run.call_count == 4

    async def test_optimize_by_cagr(self):
        """Grid search can optimize by CAGR instead of sharpe."""
        strategy = FakeStrategy()
        engine = MagicMock(spec=BacktestEngine)

        results = [
            _make_backtest_result(sharpe=3.0, cagr=0.10),
            _make_backtest_result(sharpe=1.0, cagr=0.30),
        ]
        engine.run = AsyncMock(side_effect=results)

        optimizer = StrategyOptimizer(engine=engine)
        result = await optimizer.grid_search(
            strategy, "AAPL",
            param_grid={"ema_fast": [10, 20]},
            metric="cagr",
        )

        # Higher cagr wins despite lower sharpe
        assert result.best_metrics["cagr"] == 0.30

    async def test_restores_original_params(self):
        """Strategy params are restored after grid search."""
        strategy = FakeStrategy({"ema_fast": 99, "ema_slow": 88, "threshold": 0.7})
        engine = MagicMock(spec=BacktestEngine)
        engine.run = AsyncMock(return_value=_make_backtest_result())

        optimizer = StrategyOptimizer(engine=engine)
        await optimizer.grid_search(
            strategy, "AAPL",
            param_grid={"ema_fast": [10, 20]},
        )

        # Original params restored
        params = strategy.get_params()
        assert params["ema_fast"] == 99
        assert params["ema_slow"] == 88

    async def test_sets_params_for_each_combo(self):
        """Each combination is applied to the strategy before backtest."""
        strategy = FakeStrategy()
        engine = MagicMock(spec=BacktestEngine)
        engine.run = AsyncMock(return_value=_make_backtest_result())

        optimizer = StrategyOptimizer(engine=engine)
        await optimizer.grid_search(
            strategy, "AAPL",
            param_grid={"ema_fast": [10, 20], "threshold": [0.3, 0.7]},
        )

        # 4 combos -> 4 engine.run calls
        assert engine.run.call_count == 4

    async def test_handles_partial_failures(self):
        """Failed backtests are recorded with error, not crash."""
        strategy = FakeStrategy()
        engine = MagicMock(spec=BacktestEngine)
        engine.run = AsyncMock(side_effect=[
            _make_backtest_result(sharpe=2.0),
            ValueError("No data"),
            _make_backtest_result(sharpe=1.0),
        ])

        optimizer = StrategyOptimizer(engine=engine)
        result = await optimizer.grid_search(
            strategy, "AAPL",
            param_grid={"ema_fast": [10, 20, 30]},
        )

        assert len(result.all_results) == 3
        assert result.best_metrics["sharpe_ratio"] == 2.0
        # The failed entry should have error key
        errors = [r for r in result.all_results if "error" in r]
        assert len(errors) == 1

    async def test_all_failures_raises(self):
        """If every combination fails, raise RuntimeError."""
        strategy = FakeStrategy()
        engine = MagicMock(spec=BacktestEngine)
        engine.run = AsyncMock(side_effect=ValueError("No data"))

        optimizer = StrategyOptimizer(engine=engine)

        with pytest.raises(RuntimeError, match="All parameter combinations failed"):
            await optimizer.grid_search(
                strategy, "AAPL",
                param_grid={"ema_fast": [10, 20]},
            )

    async def test_empty_grid_raises(self):
        """Empty param_grid raises ValueError."""
        strategy = FakeStrategy()
        engine = MagicMock(spec=BacktestEngine)
        optimizer = StrategyOptimizer(engine=engine)

        with pytest.raises(ValueError, match="no combinations"):
            await optimizer.grid_search(
                strategy, "AAPL",
                param_grid={},
            )

    async def test_passes_period_and_dates(self):
        """Period, start, and end are forwarded to engine.run."""
        strategy = FakeStrategy()
        engine = MagicMock(spec=BacktestEngine)
        engine.run = AsyncMock(return_value=_make_backtest_result())

        optimizer = StrategyOptimizer(engine=engine)
        await optimizer.grid_search(
            strategy, "TSLA",
            param_grid={"ema_fast": [10]},
            start="2022-01-01",
            end="2023-01-01",
        )

        call_kwargs = engine.run.call_args
        assert call_kwargs.kwargs.get("start") == "2022-01-01"
        assert call_kwargs.kwargs.get("end") == "2023-01-01"

    async def test_all_results_include_params(self):
        """Every entry in all_results contains the tested params."""
        strategy = FakeStrategy()
        engine = MagicMock(spec=BacktestEngine)
        engine.run = AsyncMock(return_value=_make_backtest_result())

        optimizer = StrategyOptimizer(engine=engine)
        result = await optimizer.grid_search(
            strategy, "AAPL",
            param_grid={"ema_fast": [10, 20]},
        )

        for entry in result.all_results:
            assert "params" in entry
            assert "ema_fast" in entry["params"]


# ---------------------------------------------------------------------------
# walk_forward tests
# ---------------------------------------------------------------------------

class TestWalkForward:
    def _make_data_loader_mock(self, n: int = 504):
        """Create a mock data loader returning n bars of data."""
        from backtest.data_loader import BacktestData
        df = _make_backtest_data_df(n)
        data = BacktestData(
            symbol="AAPL",
            df=df,
            start_date=str(df.index[0].date()),
            end_date=str(df.index[-1].date()),
        )
        loader = MagicMock()
        loader.load.return_value = data
        return loader

    async def test_basic_walk_forward(self):
        """Walk-forward produces correct number of splits."""
        strategy = FakeStrategy()
        loader = self._make_data_loader_mock(n=504)

        engine = MagicMock(spec=BacktestEngine)
        engine._data_loader = loader
        engine.run = AsyncMock(return_value=_make_backtest_result())

        optimizer = StrategyOptimizer(engine=engine)
        result = await optimizer.walk_forward(
            strategy, "AAPL",
            param_grid={"ema_fast": [10, 20]},
            total_period="5y",
            n_splits=3,
        )

        assert isinstance(result, WalkForwardResult)
        assert result.strategy_name == "fake_strategy"
        assert len(result.splits) == 3
        assert result.optimization_time_sec >= 0

    async def test_split_dates_are_contiguous(self):
        """Train end should be before test start in each split."""
        strategy = FakeStrategy()
        loader = self._make_data_loader_mock(n=504)

        engine = MagicMock(spec=BacktestEngine)
        engine._data_loader = loader
        engine.run = AsyncMock(return_value=_make_backtest_result())

        optimizer = StrategyOptimizer(engine=engine)
        result = await optimizer.walk_forward(
            strategy, "AAPL",
            param_grid={"ema_fast": [10]},
            n_splits=3,
            train_pct=0.7,
        )

        for split in result.splits:
            assert split.train_end < split.test_start

    async def test_robustness_ratio_computed(self):
        """Robustness ratio is computed for key metrics."""
        strategy = FakeStrategy()
        loader = self._make_data_loader_mock(n=504)

        engine = MagicMock(spec=BacktestEngine)
        engine._data_loader = loader
        engine.run = AsyncMock(return_value=_make_backtest_result())

        optimizer = StrategyOptimizer(engine=engine)
        result = await optimizer.walk_forward(
            strategy, "AAPL",
            param_grid={"ema_fast": [10]},
            n_splits=2,
        )

        assert "sharpe_ratio" in result.robustness_ratio
        assert "cagr" in result.robustness_ratio
        assert "win_rate" in result.robustness_ratio

    async def test_avg_metrics_populated(self):
        """Average in-sample and out-of-sample metrics are computed."""
        strategy = FakeStrategy()
        loader = self._make_data_loader_mock(n=504)

        engine = MagicMock(spec=BacktestEngine)
        engine._data_loader = loader
        engine.run = AsyncMock(return_value=_make_backtest_result(sharpe=2.0))

        optimizer = StrategyOptimizer(engine=engine)
        result = await optimizer.walk_forward(
            strategy, "AAPL",
            param_grid={"ema_fast": [10]},
            n_splits=2,
        )

        assert "sharpe_ratio" in result.avg_in_sample
        assert "sharpe_ratio" in result.avg_out_of_sample

    async def test_restores_params_after_walk_forward(self):
        """Strategy params restored after walk-forward."""
        strategy = FakeStrategy({"ema_fast": 99, "ema_slow": 88, "threshold": 0.7})
        loader = self._make_data_loader_mock(n=504)

        engine = MagicMock(spec=BacktestEngine)
        engine._data_loader = loader
        engine.run = AsyncMock(return_value=_make_backtest_result())

        optimizer = StrategyOptimizer(engine=engine)
        await optimizer.walk_forward(
            strategy, "AAPL",
            param_grid={"ema_fast": [10, 20]},
            n_splits=2,
        )

        params = strategy.get_params()
        assert params["ema_fast"] == 99
        assert params["ema_slow"] == 88

    async def test_invalid_train_pct_raises(self):
        """train_pct outside [0.3, 0.9] raises ValueError."""
        strategy = FakeStrategy()
        engine = MagicMock(spec=BacktestEngine)
        optimizer = StrategyOptimizer(engine=engine)

        with pytest.raises(ValueError, match="train_pct"):
            await optimizer.walk_forward(
                strategy, "AAPL",
                param_grid={"ema_fast": [10]},
                train_pct=0.95,
            )

        with pytest.raises(ValueError, match="train_pct"):
            await optimizer.walk_forward(
                strategy, "AAPL",
                param_grid={"ema_fast": [10]},
                train_pct=0.1,
            )

    async def test_invalid_n_splits_raises(self):
        """n_splits < 1 raises ValueError."""
        strategy = FakeStrategy()
        engine = MagicMock(spec=BacktestEngine)
        optimizer = StrategyOptimizer(engine=engine)

        with pytest.raises(ValueError, match="n_splits"):
            await optimizer.walk_forward(
                strategy, "AAPL",
                param_grid={"ema_fast": [10]},
                n_splits=0,
            )

    async def test_insufficient_data_raises(self):
        """Too few bars raises ValueError."""
        strategy = FakeStrategy()
        loader = self._make_data_loader_mock(n=30)  # too few

        engine = MagicMock(spec=BacktestEngine)
        engine._data_loader = loader

        optimizer = StrategyOptimizer(engine=engine)

        with pytest.raises(ValueError, match="Insufficient data"):
            await optimizer.walk_forward(
                strategy, "AAPL",
                param_grid={"ema_fast": [10]},
                n_splits=3,
            )

    async def test_each_split_has_best_params(self):
        """Each split records the best params found during training."""
        strategy = FakeStrategy()
        loader = self._make_data_loader_mock(n=504)

        call_count = 0

        async def varying_run(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            sharpe = 1.0 + (call_count % 3) * 0.5
            return _make_backtest_result(sharpe=sharpe)

        engine = MagicMock(spec=BacktestEngine)
        engine._data_loader = loader
        engine.run = AsyncMock(side_effect=varying_run)

        optimizer = StrategyOptimizer(engine=engine)
        result = await optimizer.walk_forward(
            strategy, "AAPL",
            param_grid={"ema_fast": [10, 20]},
            n_splits=2,
        )

        for split in result.splits:
            assert "ema_fast" in split.best_params

    async def test_walk_forward_handles_test_failure(self):
        """If test-phase backtest fails, OOS metrics default to zero."""
        strategy = FakeStrategy()
        loader = self._make_data_loader_mock(n=504)

        call_idx = 0

        async def run_side_effect(*args, **kwargs):
            nonlocal call_idx
            call_idx += 1
            # grid_search calls succeed, but test validation fails
            # for n_splits=1, param_grid has 1 value -> 1 grid call + 1 test call
            if call_idx == 2:
                raise ValueError("Test window has no data")
            return _make_backtest_result(sharpe=2.0)

        engine = MagicMock(spec=BacktestEngine)
        engine._data_loader = loader
        engine.run = AsyncMock(side_effect=run_side_effect)

        optimizer = StrategyOptimizer(engine=engine)
        result = await optimizer.walk_forward(
            strategy, "AAPL",
            param_grid={"ema_fast": [10]},
            n_splits=1,
        )

        # Should still produce a result, OOS metrics zeroed
        assert len(result.splits) == 1
        assert result.splits[0].out_of_sample_metrics["sharpe_ratio"] == 0.0


# ---------------------------------------------------------------------------
# Constructor / SimConfig tests
# ---------------------------------------------------------------------------

class TestStrategyOptimizerInit:
    def test_default_engine_created(self):
        """Optimizer creates a default BacktestEngine if none provided."""
        optimizer = StrategyOptimizer()
        assert optimizer._engine is not None

    def test_custom_sim_config(self):
        """Custom SimConfig is forwarded to engine."""
        config = SimConfig(initial_equity=50_000)
        optimizer = StrategyOptimizer(sim_config=config)
        assert optimizer._sim_config.initial_equity == 50_000

    def test_custom_engine(self):
        """Can inject a custom BacktestEngine."""
        engine = MagicMock(spec=BacktestEngine)
        optimizer = StrategyOptimizer(engine=engine)
        assert optimizer._engine is engine


# ---------------------------------------------------------------------------
# OptimizationResult / WalkForwardResult dataclass tests
# ---------------------------------------------------------------------------

class TestOptimizationResult:
    def test_fields(self):
        result = OptimizationResult(
            strategy_name="test",
            best_params={"a": 1},
            best_metrics={"sharpe_ratio": 2.0},
            all_results=[{"params": {"a": 1}, "sharpe_ratio": 2.0}],
            optimization_time_sec=1.5,
        )
        assert result.strategy_name == "test"
        assert result.best_params == {"a": 1}
        assert result.optimization_time_sec == 1.5


class TestWalkForwardResult:
    def test_fields(self):
        result = WalkForwardResult(
            strategy_name="test",
            splits=[],
            avg_in_sample={"sharpe_ratio": 2.0},
            avg_out_of_sample={"sharpe_ratio": 1.5},
            robustness_ratio={"sharpe_ratio": 0.75},
            optimization_time_sec=10.0,
        )
        assert result.robustness_ratio["sharpe_ratio"] == 0.75
        assert len(result.splits) == 0


class TestWalkForwardSplit:
    def test_fields(self):
        split = WalkForwardSplit(
            split_index=0,
            train_start="2020-01-01",
            train_end="2021-06-30",
            test_start="2021-07-01",
            test_end="2022-01-01",
            best_params={"ema_fast": 20},
            in_sample_metrics={"sharpe_ratio": 2.0},
            out_of_sample_metrics={"sharpe_ratio": 1.5},
        )
        assert split.split_index == 0
        assert split.best_params["ema_fast"] == 20
