"""Compare return improvement strategies.

Tests:
  A. CURRENT — baseline (ATR SL/TP, 10 positions, 7d cooldown)
  B. WIDE_TP — TP 50% → 200% (let winners run much longer)
  C. NO_TP — TP disabled (only SL + strategy sell + regime sell exits)
  D. CONCENTRATED — 5 positions max, 25% per position
  E. CONC_NO_TP — concentrated + no TP (max conviction, let ride)
  F. TRAIL_ONLY — no fixed TP, trailing stop 8%/5% replaces TP
  G. POS_15 — 15 positions, 10% each (more diversified)
  H. POS_20 — 20 positions, 8% each (max diversification)

Usage:
    cd backend && python -m backtest.compare_returns [period]
    cd backend && python -m backtest.compare_returns 5y
"""

import asyncio
import logging
import sys

from backtest.full_pipeline import FullPipelineBacktest, PipelineConfig

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)

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
        max_watchlist=25,
        kelly_fraction=0.40,
        confidence_exponent=1.2,
        min_position_pct=0.05,
        recovery_watch_days=7,
        dynamic_sl_tp=True,
        default_stop_loss_pct=0.12,
    )

    # A: CURRENT baseline — 10 pos, 15% max, TP 50%
    cfg_a = PipelineConfig(
        **base,
        max_positions=10,
        max_position_pct=0.15,
        max_exposure_pct=0.95,
        default_take_profit_pct=0.50,
        trailing_activation_pct=0.0,
        trailing_trail_pct=0.0,
    )

    # B: WIDE_TP — TP 200% (only take profit on 3x gains)
    cfg_b = PipelineConfig(
        **base,
        max_positions=10,
        max_position_pct=0.15,
        max_exposure_pct=0.95,
        default_take_profit_pct=2.00,
        trailing_activation_pct=0.0,
        trailing_trail_pct=0.0,
    )

    # C: NO_TP — TP effectively disabled (999%), rely on SL + signals + regime
    cfg_c = PipelineConfig(
        **base,
        max_positions=10,
        max_position_pct=0.15,
        max_exposure_pct=0.95,
        default_take_profit_pct=9.99,
        trailing_activation_pct=0.0,
        trailing_trail_pct=0.0,
    )

    # D: CONCENTRATED — 5 positions, 25% each
    cfg_d = PipelineConfig(
        **base,
        max_positions=5,
        max_position_pct=0.25,
        max_exposure_pct=0.95,
        default_take_profit_pct=0.50,
        trailing_activation_pct=0.0,
        trailing_trail_pct=0.0,
    )

    # E: CONC_NO_TP — concentrated + no TP (max conviction, let winners ride)
    cfg_e = PipelineConfig(
        **base,
        max_positions=5,
        max_position_pct=0.25,
        max_exposure_pct=0.95,
        default_take_profit_pct=9.99,
        trailing_activation_pct=0.0,
        trailing_trail_pct=0.0,
    )

    # F: TRAIL — no fixed TP, trailing stop instead (activate at +8%, trail 5%)
    cfg_f = PipelineConfig(
        **base,
        max_positions=10,
        max_position_pct=0.15,
        max_exposure_pct=0.95,
        default_take_profit_pct=9.99,
        trailing_activation_pct=0.08,
        trailing_trail_pct=0.05,
    )

    # G: POS_15 — 15 positions, 10% each (more diversified)
    cfg_g = PipelineConfig(
        **base,
        max_positions=15,
        max_position_pct=0.10,
        max_exposure_pct=0.95,
        default_take_profit_pct=0.50,
        trailing_activation_pct=0.0,
        trailing_trail_pct=0.0,
    )

    # H: POS_20 — 20 positions, 8% each (max diversification)
    cfg_h = PipelineConfig(
        **base,
        max_positions=20,
        max_position_pct=0.08,
        max_exposure_pct=0.95,
        default_take_profit_pct=0.50,
        trailing_activation_pct=0.0,
        trailing_trail_pct=0.0,
    )

    configs = {
        "CURRENT": cfg_a,
        "WIDE_TP": cfg_b,
        "NO_TP": cfg_c,
        "CONC_5": cfg_d,
        "CONC_NOTP": cfg_e,
        "TRAIL": cfg_f,
        "POS_15": cfg_g,
        "POS_20": cfg_h,
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

    logger.info("\n" + "=" * 80)
    logger.info(f"RETURN IMPROVEMENT COMPARISON ({period})")
    logger.info("=" * 80)
    header = f"  {'':20s}" + "".join(f"  {n:>12s}" for n in config_names)
    logger.info(header)
    logger.info(f"  {'-' * (20 + 14 * len(config_names))}")

    def row(label, values, suffix=""):
        parts = f"  {label:20s}"
        for v in values:
            parts += f"  {v:>12{suffix}}"
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
    logger.info(row("Avg Hold Days", [m.avg_holding_days for m in metrics_list], ".0f"))
    logger.info(row("Final Equity", [m.final_equity for m in metrics_list], ",.0f"))
    logger.info(row("Alpha %", [m.alpha for m in metrics_list], ".1f"))
    logger.info(row("SPY %", [m.benchmark_return_pct for m in metrics_list], ".1f"))

    # Strategy breakdown for top 3
    sorted_configs = sorted(
        config_names, key=lambda n: results[n].metrics.total_return_pct, reverse=True,
    )
    for cname in sorted_configs[:3]:
        result = results[cname]
        logger.info(f"\n  [{cname}] {result.metrics.total_trades} trades, "
                     f"CAGR={result.metrics.cagr*100:.1f}%, "
                     f"Avg Hold={result.metrics.avg_holding_days:.0f}d")
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
