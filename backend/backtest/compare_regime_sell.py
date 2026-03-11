"""Compare full pipeline backtest: SL/TP strategies.

Usage:
    cd backend && python -m backtest.compare_regime_sell [period]
    cd backend && python -m backtest.compare_regime_sell 5y
"""

import asyncio
import logging
import sys

from backtest.full_pipeline import FullPipelineBacktest, PipelineConfig

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)

# Broad universe for meaningful backtest
TEST_UNIVERSE = [
    # Mega-cap tech
    "AAPL", "MSFT", "GOOGL", "AMZN", "NVDA", "META", "TSLA", "AVGO",
    # Tech / Semis
    "AMD", "INTC", "QCOM", "CRM", "ADBE", "ORCL",
    # Finance
    "JPM", "BAC", "GS", "WFC",
    # Healthcare
    "UNH", "JNJ", "LLY", "MRK",
    # Consumer
    "WMT", "HD", "COST", "NKE",
    # Energy
    "XOM", "CVX", "COP",
    # Industrial
    "CAT", "BA", "HON",
]


async def main():
    period = sys.argv[1] if len(sys.argv) > 1 else "3y"

    base = dict(
        universe=list(TEST_UNIVERSE),
        initial_equity=100_000,
        enable_regime_sells=True,
        min_active_ratio=0.05,
        min_confidence=0.35,
        min_screen_grade="C",
        screen_interval=10,
        max_positions=10,
        max_watchlist=25,
        max_position_pct=0.15,
        max_exposure_pct=0.95,
        kelly_fraction=0.40,
        confidence_exponent=1.2,
        min_position_pct=0.05,
        recovery_watch_days=30,
    )

    # ── A: Current best — ATR dynamic SL/TP (default) ──────────────
    cfg_a = PipelineConfig(
        **base,
        dynamic_sl_tp=True,
        default_stop_loss_pct=0.12,
        default_take_profit_pct=0.50,
    )

    # ── B: Fixed 12% SL / 50% TP (no ATR) ──────────────────────────
    cfg_b = PipelineConfig(
        **base,
        dynamic_sl_tp=False,
        default_stop_loss_pct=0.12,
        default_take_profit_pct=0.50,
    )

    # ── C: Fixed tighter 8% SL / 20% TP ────────────────────────────
    cfg_c = PipelineConfig(
        **base,
        dynamic_sl_tp=False,
        default_stop_loss_pct=0.08,
        default_take_profit_pct=0.20,
    )

    # ── D: Fixed 8% SL / 30% TP ────────────────────────────────────
    cfg_d = PipelineConfig(
        **base,
        dynamic_sl_tp=False,
        default_stop_loss_pct=0.08,
        default_take_profit_pct=0.30,
    )

    # ── E: Fixed 10% SL / 25% TP ───────────────────────────────────
    cfg_e = PipelineConfig(
        **base,
        dynamic_sl_tp=False,
        default_stop_loss_pct=0.10,
        default_take_profit_pct=0.25,
    )

    configs = {
        "ATR_DYN": cfg_a,
        "FIX12/50": cfg_b,
        "FIX8/20": cfg_c,
        "FIX8/30": cfg_d,
        "FIX10/25": cfg_e,
    }
    results = {}

    for name, cfg in configs.items():
        logger.info("\n" + "=" * 60)
        logger.info(f"Running {name} config...")
        logger.info("=" * 60)
        engine = FullPipelineBacktest(cfg)
        results[name] = await engine.run(period=period)

    # ── Compare ───────────────────────────────────────────────────────
    config_names = list(results.keys())
    metrics_list = [results[n].metrics for n in config_names]

    logger.info("\n" + "=" * 70)
    logger.info("COMPARISON")
    logger.info("=" * 70)
    header = f"  {'':20s}" + "".join(f"  {n:>10s}" for n in config_names)
    logger.info(header)
    logger.info(f"  {'-' * (20 + 12 * len(config_names))}")

    def row(label, values, suffix=""):
        parts = f"  {label:20s}"
        for v in values:
            parts += f"  {v:>10{suffix}}"
        return parts

    logger.info(row("CAGR %", [m.cagr * 100 for m in metrics_list], ".1f"))
    logger.info(row("Total Return %", [m.total_return_pct for m in metrics_list], ".1f"))
    logger.info(row("Sharpe", [m.sharpe_ratio for m in metrics_list], ".2f"))
    logger.info(row("Sortino", [m.sortino_ratio for m in metrics_list], ".2f"))
    logger.info(row("MDD %", [m.max_drawdown_pct for m in metrics_list], ".1f"))
    logger.info(row("MDD Days", [m.max_drawdown_days for m in metrics_list], ".0f"))
    logger.info(row("Win Rate %", [m.win_rate for m in metrics_list], ".1f"))
    logger.info(row("Profit Factor", [m.profit_factor for m in metrics_list], ".2f"))
    logger.info(row("Total Trades", [m.total_trades for m in metrics_list], ".0f"))
    logger.info(row("Final Equity", [m.final_equity for m in metrics_list], ",.0f"))
    logger.info(row("Alpha %", [m.alpha for m in metrics_list], ".1f"))
    logger.info(row("SPY %", [m.benchmark_return_pct for m in metrics_list], ".1f"))

    # Strategy breakdown for top 2 configs
    sorted_configs = sorted(
        config_names, key=lambda n: results[n].metrics.total_return_pct, reverse=True,
    )
    for cname in sorted_configs[:2]:
        result = results[cname]
        logger.info(f"\n  [{cname}] {result.metrics.total_trades} trades")
        for sname, stats in sorted(
            result.strategy_stats.items(),
            key=lambda x: x[1]["pnl"], reverse=True,
        ):
            if stats["trades"] > 0:
                logger.info(
                    f"    {sname:20s}: {stats['trades']:3d} trades, "
                    f"WR={stats['win_rate']:4.0f}%, PnL=${stats['pnl']:+,.0f}"
                )


if __name__ == "__main__":
    asyncio.run(main())
