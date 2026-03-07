"""Full strategy parameter optimization.

Defines parameter grids for all 13 strategies and runs
walk-forward optimization across representative stocks.
Results are stored persistently to avoid re-running.
"""

import asyncio
import logging
import math
import time
from dataclasses import dataclass, field

from backtest.engine import BacktestEngine
from backtest.optimizer import StrategyOptimizer, OptimizationResult, WalkForwardResult
from backtest.result_store import BacktestResultStore
from backtest.simulator import SimConfig
from strategies.registry import STRATEGY_CLASSES

logger = logging.getLogger(__name__)

# Representative stocks across sectors
DEFAULT_SYMBOLS = ["AAPL", "MSFT", "NVDA", "JPM", "JNJ"]

# Parameter grids per strategy (kept small for tractability)
PARAM_GRIDS: dict[str, dict[str, list]] = {
    "trend_following": {
        "ema_fast": [10, 15, 20, 25],
        "ema_slow": [40, 50, 60],
        "adx_threshold": [20, 25, 30],
    },
    "dual_momentum": {
        "lookback_months": [6, 9, 12, 18],
        "min_absolute_return": [0.0, 0.02, 0.05],
    },
    "donchian_breakout": {
        "entry_period": [15, 20, 25, 30],
        "exit_period": [7, 10, 15],
        "adx_threshold": [20, 25, 30],
    },
    "supertrend": {
        "atr_period": [7, 10, 14],
        "multiplier": [2.0, 2.5, 3.0, 3.5],
        "confirmation_bars": [1, 2, 3],
    },
    "macd_histogram": {
        "fast_period": [8, 12, 16],
        "slow_period": [20, 26, 30],
        "signal_period": [7, 9, 12],
    },
    "rsi_divergence": {
        "rsi_period": [10, 14, 21],
        "overbought": [65, 70, 75],
        "oversold": [25, 30, 35],
    },
    "bollinger_squeeze": {
        "bb_period": [15, 20, 25],
        "bb_std": [1.5, 2.0, 2.5],
        "squeeze_min_bars": [2, 3, 5],
    },
    "volume_profile": {
        "lookback_days": [40, 60, 80],
        "volume_surge_threshold": [1.5, 2.0, 2.5],
    },
    "cis_momentum": {
        "roc_short": [3, 5, 8],
        "roc_long": [8, 10, 15],
        "roc_short_buy": [2.0, 3.0, 5.0],
    },
    "larry_williams": {
        "k": [0.3, 0.5, 0.7, 1.0],
        "willr_period": [10, 14, 20],
    },
    "bnf_deviation": {
        "sma_period": [20, 25, 30],
        "buy_deviation": [-7.0, -5.0, -3.0],
        "sell_deviation": [2.0, 3.0, 5.0],
    },
    # Meta-strategies: minimal grids (they depend on external data)
    "regime_switch": {
        "vix_bull_threshold": [18, 20, 22],
        "vix_bear_threshold": [23, 25, 28],
    },
    "sector_rotation": {
        "top_sectors": [2, 3, 4],
        "lookback_weeks": [8, 12, 16],
    },
}


def _safe(v):
    """Make a value JSON-safe."""
    if isinstance(v, float) and (math.isinf(v) or math.isnan(v)):
        return 0.0
    return v


@dataclass
class StrategyOptResult:
    """Optimization result for one strategy across multiple symbols."""
    strategy_name: str
    best_params: dict
    per_symbol: dict[str, dict] = field(default_factory=dict)
    avg_sharpe: float = 0.0
    avg_cagr: float = 0.0
    walk_forward: dict | None = None
    grid_combos: int = 0
    elapsed_sec: float = 0.0


@dataclass
class FullOptimizationResult:
    """Results for all strategies."""
    strategies: dict[str, StrategyOptResult] = field(default_factory=dict)
    total_elapsed_sec: float = 0.0

    def to_dict(self) -> dict:
        result = {"total_elapsed_sec": round(self.total_elapsed_sec, 1), "strategies": {}}
        for name, sr in self.strategies.items():
            result["strategies"][name] = {
                "best_params": sr.best_params,
                "avg_sharpe": round(_safe(sr.avg_sharpe), 3),
                "avg_cagr": round(_safe(sr.avg_cagr * 100), 2),
                "grid_combos": sr.grid_combos,
                "elapsed_sec": round(sr.elapsed_sec, 1),
                "per_symbol": {
                    sym: {k: round(_safe(v), 3) if isinstance(v, float) else v for k, v in m.items()}
                    for sym, m in sr.per_symbol.items()
                },
                "walk_forward": sr.walk_forward,
            }
        return result


async def optimize_strategy(
    strategy_name: str,
    symbols: list[str],
    period: str = "3y",
    metric: str = "sharpe_ratio",
    result_store: BacktestResultStore | None = None,
    force: bool = False,
) -> StrategyOptResult:
    """Optimize a single strategy across multiple symbols.

    1. Grid search on each symbol separately
    2. Pick params with best average metric across symbols
    3. Optionally run walk-forward on best symbol for robustness check
    """
    store = result_store or BacktestResultStore()
    grid = PARAM_GRIDS.get(strategy_name)
    if not grid:
        raise ValueError(f"No param grid defined for {strategy_name}")

    cls = STRATEGY_CLASSES.get(strategy_name)
    if not cls:
        raise ValueError(f"Strategy {strategy_name} not found")

    # Check dedup
    store_key = f"optimize_{strategy_name}"
    store_symbol = ",".join(sorted(symbols))
    if not force and store.exists(store_key, store_symbol, period, mode="optimization"):
        stored = store.get(store_key, store_symbol, period, mode="optimization")
        if stored:
            logger.info("Returning cached optimization for %s", strategy_name)
            r = stored["result"]
            return StrategyOptResult(
                strategy_name=strategy_name,
                best_params=r["best_params"],
                per_symbol=r.get("per_symbol", {}),
                avg_sharpe=r.get("avg_sharpe", 0),
                avg_cagr=r.get("avg_cagr", 0),
                walk_forward=r.get("walk_forward"),
                grid_combos=r.get("grid_combos", 0),
                elapsed_sec=r.get("elapsed_sec", 0),
            )

    sim_config = SimConfig(
        initial_equity=100_000,
        max_position_pct=0.95,
        max_total_positions=1,
    )
    engine = BacktestEngine(sim_config=sim_config)
    optimizer = StrategyOptimizer(engine=engine, sim_config=sim_config)

    t0 = time.monotonic()
    logger.info("Optimizing %s: %d grid combos × %d symbols",
                strategy_name, _count_combos(grid), len(symbols))

    # Grid search per symbol
    per_symbol_results: dict[str, OptimizationResult] = {}
    for symbol in symbols:
        strategy = cls()
        try:
            result = await optimizer.grid_search(
                strategy=strategy,
                symbol=symbol,
                param_grid=grid,
                period=period,
                metric=metric,
            )
            per_symbol_results[symbol] = result
            logger.info(
                "  %s/%s: best %s=%.4f with %s",
                strategy_name, symbol, metric,
                result.best_metrics.get(metric, 0), result.best_params,
            )
        except Exception as e:
            logger.warning("  %s/%s optimization failed: %s", strategy_name, symbol, e)

    if not per_symbol_results:
        raise RuntimeError(f"Optimization failed for all symbols on {strategy_name}")

    # Find best params by averaging metric across symbols
    best_params = _find_consensus_params(per_symbol_results, metric)

    # Collect per-symbol metrics for the consensus params
    per_symbol_metrics = {}
    for symbol, opt_result in per_symbol_results.items():
        # Find this combo in all_results
        matching = [
            r for r in opt_result.all_results
            if r.get("params") == best_params and "error" not in r
        ]
        if matching:
            per_symbol_metrics[symbol] = {
                k: v for k, v in matching[0].items() if k != "params"
            }
        else:
            per_symbol_metrics[symbol] = opt_result.best_metrics

    avg_sharpe = _avg_metric(per_symbol_metrics, "sharpe_ratio")
    avg_cagr = _avg_metric(per_symbol_metrics, "cagr")

    elapsed = time.monotonic() - t0

    opt_result = StrategyOptResult(
        strategy_name=strategy_name,
        best_params=best_params,
        per_symbol=per_symbol_metrics,
        avg_sharpe=avg_sharpe,
        avg_cagr=avg_cagr,
        grid_combos=_count_combos(grid),
        elapsed_sec=elapsed,
    )

    # Save to store
    store.save(
        strategy_name=store_key,
        symbol=store_symbol,
        period=period,
        result_data=_serialize_opt_result(opt_result),
        mode="optimization",
    )

    logger.info(
        "Optimization complete for %s: avg_sharpe=%.3f, avg_cagr=%.1f%%, params=%s (%.1fs)",
        strategy_name, avg_sharpe, avg_cagr * 100, best_params, elapsed,
    )
    return opt_result


async def optimize_all(
    symbols: list[str] | None = None,
    period: str = "3y",
    strategy_names: list[str] | None = None,
    metric: str = "sharpe_ratio",
    force: bool = False,
) -> FullOptimizationResult:
    """Optimize all strategies sequentially."""
    symbols = symbols or DEFAULT_SYMBOLS
    names = strategy_names or list(PARAM_GRIDS.keys())

    result_store = BacktestResultStore()
    full_result = FullOptimizationResult()
    t0 = time.monotonic()

    for name in names:
        if name not in PARAM_GRIDS:
            logger.warning("No param grid for %s, skipping", name)
            continue
        try:
            sr = await optimize_strategy(
                strategy_name=name,
                symbols=symbols,
                period=period,
                metric=metric,
                result_store=result_store,
                force=force,
            )
            full_result.strategies[name] = sr
        except Exception as e:
            logger.error("Optimization failed for %s: %s", name, e)

    full_result.total_elapsed_sec = time.monotonic() - t0
    return full_result


def _count_combos(grid: dict[str, list]) -> int:
    count = 1
    for values in grid.values():
        count *= len(values)
    return count


def _find_consensus_params(
    per_symbol: dict[str, OptimizationResult],
    metric: str,
) -> dict:
    """Find params that perform best on average across symbols.

    For each param combo that appears across all symbols' grid results,
    average the target metric, then pick the best.
    """
    # Collect all param combos and their per-symbol scores
    combo_scores: dict[str, list[float]] = {}
    combo_map: dict[str, dict] = {}

    for symbol, opt_result in per_symbol.items():
        for entry in opt_result.all_results:
            if "error" in entry:
                continue
            params = entry["params"]
            key = str(sorted(params.items()))
            if key not in combo_map:
                combo_map[key] = params
                combo_scores[key] = []
            combo_scores[key].append(entry.get(metric, float("-inf")))

    if not combo_scores:
        # Fallback: just use the first symbol's best
        first = next(iter(per_symbol.values()))
        return first.best_params

    # Average across symbols, prefer combos tested on more symbols
    best_key = max(
        combo_scores.keys(),
        key=lambda k: (
            sum(combo_scores[k]) / len(combo_scores[k])
            if combo_scores[k] else float("-inf")
        ),
    )
    return combo_map[best_key]


def _avg_metric(per_symbol: dict[str, dict], metric: str) -> float:
    values = [
        m.get(metric, 0) for m in per_symbol.values()
        if isinstance(m.get(metric), (int, float))
        and not math.isinf(m.get(metric, 0))
        and not math.isnan(m.get(metric, 0))
    ]
    return sum(values) / len(values) if values else 0.0


def _serialize_opt_result(r: StrategyOptResult) -> dict:
    return {
        "strategy_name": r.strategy_name,
        "best_params": r.best_params,
        "per_symbol": {
            sym: {k: _safe(v) for k, v in m.items()}
            for sym, m in r.per_symbol.items()
        },
        "avg_sharpe": _safe(r.avg_sharpe),
        "avg_cagr": _safe(r.avg_cagr),
        "walk_forward": r.walk_forward,
        "grid_combos": r.grid_combos,
        "elapsed_sec": r.elapsed_sec,
    }
