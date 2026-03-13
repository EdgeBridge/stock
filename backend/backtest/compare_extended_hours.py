"""Compare extended hours vs baseline + parameter optimization.

Tests:
  1. BASELINE — no extended hours (current live config)
  2. EXT_DEFAULT — extended hours with default params
  3. Grid search over key extended hours parameters

Pass criteria (from plan):
  - Extended hours CAGR > baseline CAGR
  - Extended hours win rate >= 40%
  - MDD worsening <= 2%p

Usage:
    cd backend && python3 -m backtest.compare_extended_hours [period]
    cd backend && python3 -m backtest.compare_extended_hours 5y
"""

import asyncio
import itertools
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

# Shared base config (matches compare_returns.py tuned params)
BASE = dict(
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
    max_positions=10,
    max_position_pct=0.15,
    max_exposure_pct=0.95,
    default_take_profit_pct=0.50,
    trailing_activation_pct=0.0,
    trailing_trail_pct=0.0,
)


def _row(label, values, suffix=""):
    parts = f"  {label:24s}"
    for v in values:
        parts += f"  {v:>12{suffix}}"
    return parts


async def run_comparison(period: str):
    """Phase 1: Baseline vs Extended Hours (default params)."""
    logger.info("=" * 70)
    logger.info("PHASE 1: BASELINE vs EXTENDED HOURS")
    logger.info("=" * 70)

    cfg_baseline = PipelineConfig(**BASE, extended_hours_enabled=False)
    cfg_ext = PipelineConfig(
        **BASE,
        extended_hours_enabled=True,
        extended_hours_max_position_pct=0.03,
        extended_hours_slippage_multiplier=3.0,
        extended_hours_fill_probability=0.70,
        extended_hours_min_confidence=0.70,
    )

    results = {}
    for name, cfg in [("BASELINE", cfg_baseline), ("EXT_DEFAULT", cfg_ext)]:
        logger.info(f"\nRunning {name}...")
        engine = FullPipelineBacktest(cfg)
        results[name] = await engine.run(period=period)
        logger.info(results[name].summary())

    # Print comparison table
    names = list(results.keys())
    metrics = [results[n].metrics for n in names]

    logger.info("\n" + "=" * 70)
    logger.info(f"COMPARISON TABLE ({period})")
    logger.info("=" * 70)
    header = f"  {'':24s}" + "".join(f"  {n:>12s}" for n in names)
    logger.info(header)
    logger.info(f"  {'-' * (24 + 14 * len(names))}")

    logger.info(_row("CAGR %", [m.cagr * 100 for m in metrics], ".2f"))
    logger.info(_row("Total Return %", [m.total_return_pct for m in metrics], ".1f"))
    logger.info(_row("Sharpe", [m.sharpe_ratio for m in metrics], ".2f"))
    logger.info(_row("Sortino", [m.sortino_ratio for m in metrics], ".2f"))
    logger.info(_row("MDD %", [m.max_drawdown_pct for m in metrics], ".1f"))
    logger.info(_row("MDD Days", [m.max_drawdown_days for m in metrics], ".0f"))
    logger.info(_row("Win Rate %", [m.win_rate for m in metrics], ".1f"))
    logger.info(_row("Profit Factor", [m.profit_factor for m in metrics], ".2f"))
    logger.info(_row("Total Trades", [m.total_trades for m in metrics], ".0f"))
    logger.info(_row("Avg Hold Days", [m.avg_holding_days for m in metrics], ".0f"))
    logger.info(_row("Final Equity", [m.final_equity for m in metrics], ",.0f"))
    logger.info(_row("Alpha %", [m.alpha for m in metrics], ".1f"))
    logger.info(_row("SPY %", [m.benchmark_return_pct for m in metrics], ".1f"))

    # Extended hours detail
    ext_m = results["EXT_DEFAULT"].metrics
    logger.info(f"\n  Extended Hours Detail:")
    logger.info(f"    Trades: {ext_m.extended_trades}")
    logger.info(f"    Wins:   {ext_m.extended_wins}")
    logger.info(f"    WR:     {ext_m.extended_win_rate:.1f}%")
    logger.info(f"    PnL:    ${ext_m.extended_pnl:+,.0f}")

    # Pass criteria check
    base_m = results["BASELINE"].metrics
    logger.info(f"\n  PASS CRITERIA:")
    cagr_pass = ext_m.cagr > base_m.cagr
    wr_pass = ext_m.extended_win_rate >= 40.0
    mdd_delta = abs(ext_m.max_drawdown_pct) - abs(base_m.max_drawdown_pct)
    mdd_pass = mdd_delta <= 2.0

    logger.info(f"    CAGR improvement:   {ext_m.cagr*100:.2f}% vs {base_m.cagr*100:.2f}% → {'PASS' if cagr_pass else 'FAIL'}")
    logger.info(f"    Ext WR >= 40%%:      {ext_m.extended_win_rate:.1f}% → {'PASS' if wr_pass else 'FAIL'}")
    logger.info(f"    MDD worsening <= 2: {mdd_delta:+.1f}%p → {'PASS' if mdd_pass else 'FAIL'}")

    all_pass = cagr_pass and wr_pass and mdd_pass
    logger.info(f"    OVERALL: {'✓ ALL PASS' if all_pass else '✗ FAIL'}")

    return results


async def run_optimization(period: str):
    """Phase 2: Grid search over extended hours parameters."""
    logger.info("\n" + "=" * 70)
    logger.info("PHASE 2: EXTENDED HOURS PARAMETER OPTIMIZATION")
    logger.info("=" * 70)

    # Parameter grid
    grid = {
        "max_position_pct": [0.02, 0.03, 0.05],
        "slippage_mult": [2.0, 3.0, 4.0],
        "fill_prob": [0.50, 0.70, 0.90],
        "min_conf": [0.55, 0.65, 0.75],
    }

    # Use Latin Hypercube-like sampling: pick interesting combos, not full grid (81 runs!)
    # Key combos: vary one param at a time from default, then test promising corners
    combos = [
        # Default
        {"max_position_pct": 0.03, "slippage_mult": 3.0, "fill_prob": 0.70, "min_conf": 0.70},
        # Vary position size
        {"max_position_pct": 0.02, "slippage_mult": 3.0, "fill_prob": 0.70, "min_conf": 0.70},
        {"max_position_pct": 0.05, "slippage_mult": 3.0, "fill_prob": 0.70, "min_conf": 0.70},
        # Vary slippage
        {"max_position_pct": 0.03, "slippage_mult": 2.0, "fill_prob": 0.70, "min_conf": 0.70},
        {"max_position_pct": 0.03, "slippage_mult": 4.0, "fill_prob": 0.70, "min_conf": 0.70},
        # Vary fill probability
        {"max_position_pct": 0.03, "slippage_mult": 3.0, "fill_prob": 0.50, "min_conf": 0.70},
        {"max_position_pct": 0.03, "slippage_mult": 3.0, "fill_prob": 0.90, "min_conf": 0.70},
        # Vary confidence
        {"max_position_pct": 0.03, "slippage_mult": 3.0, "fill_prob": 0.70, "min_conf": 0.55},
        {"max_position_pct": 0.03, "slippage_mult": 3.0, "fill_prob": 0.70, "min_conf": 0.80},
        # Promising corners: aggressive (bigger, looser) vs conservative (smaller, tighter)
        {"max_position_pct": 0.05, "slippage_mult": 2.0, "fill_prob": 0.90, "min_conf": 0.55},  # aggressive
        {"max_position_pct": 0.02, "slippage_mult": 4.0, "fill_prob": 0.50, "min_conf": 0.80},  # conservative
        # Balanced corners
        {"max_position_pct": 0.05, "slippage_mult": 3.0, "fill_prob": 0.70, "min_conf": 0.55},  # bigger + looser conf
        {"max_position_pct": 0.03, "slippage_mult": 2.0, "fill_prob": 0.90, "min_conf": 0.65},  # better fills
    ]

    results = []
    for i, params in enumerate(combos, 1):
        label = (
            f"pos={params['max_position_pct']:.0%} "
            f"slip={params['slippage_mult']:.0f}x "
            f"fill={params['fill_prob']:.0%} "
            f"conf={params['min_conf']:.0%}"
        )
        logger.info(f"\n  [{i}/{len(combos)}] {label}")

        cfg = PipelineConfig(
            **BASE,
            extended_hours_enabled=True,
            extended_hours_max_position_pct=params["max_position_pct"],
            extended_hours_slippage_multiplier=params["slippage_mult"],
            extended_hours_fill_probability=params["fill_prob"],
            extended_hours_min_confidence=params["min_conf"],
        )
        engine = FullPipelineBacktest(cfg)
        result = await engine.run(period=period)
        m = result.metrics

        results.append({
            "params": params,
            "label": label,
            "cagr": m.cagr,
            "sharpe": m.sharpe_ratio,
            "mdd": m.max_drawdown_pct,
            "win_rate": m.win_rate,
            "total_trades": m.total_trades,
            "final_equity": m.final_equity,
            "alpha": m.alpha,
            "ext_trades": m.extended_trades,
            "ext_wr": m.extended_win_rate,
            "ext_pnl": m.extended_pnl,
        })

        logger.info(
            f"    CAGR={m.cagr*100:.2f}% Sharpe={m.sharpe_ratio:.2f} "
            f"MDD={m.max_drawdown_pct:.1f}% WR={m.win_rate:.1f}% "
            f"ExtTrades={m.extended_trades} ExtWR={m.extended_win_rate:.0f}% ExtPnL=${m.extended_pnl:+,.0f}"
        )

    # Sort by CAGR and print ranking
    results.sort(key=lambda r: r["cagr"], reverse=True)

    logger.info("\n" + "=" * 70)
    logger.info("OPTIMIZATION RANKING (by CAGR)")
    logger.info("=" * 70)
    logger.info(
        f"  {'#':>2s}  {'CAGR%':>7s}  {'Sharpe':>7s}  {'MDD%':>6s}  "
        f"{'WR%':>5s}  {'ExtT':>5s}  {'ExtWR':>5s}  {'ExtPnL':>8s}  Config"
    )
    logger.info(f"  {'-' * 90}")

    for rank, r in enumerate(results, 1):
        logger.info(
            f"  {rank:>2d}  {r['cagr']*100:>7.2f}  {r['sharpe']:>7.2f}  "
            f"{r['mdd']:>6.1f}  {r['win_rate']:>5.1f}  {r['ext_trades']:>5d}  "
            f"{r['ext_wr']:>5.0f}  {r['ext_pnl']:>+8,.0f}  {r['label']}"
        )

    # Best config
    best = results[0]
    logger.info(f"\n  BEST CONFIG: {best['label']}")
    logger.info(f"    CAGR={best['cagr']*100:.2f}% Sharpe={best['sharpe']:.2f} MDD={best['mdd']:.1f}%")
    logger.info(f"    Extended: {best['ext_trades']} trades, WR={best['ext_wr']:.0f}%, PnL=${best['ext_pnl']:+,.0f}")

    return results


async def main():
    period = sys.argv[1] if len(sys.argv) > 1 else "3y"
    logger.info(f"Extended Hours Backtest — Period: {period}\n")

    # Phase 1: Baseline vs Extended
    comparison = await run_comparison(period)

    # Phase 2: Parameter optimization
    opt_results = await run_optimization(period)

    # Final recommendation
    base_m = comparison["BASELINE"].metrics
    best = opt_results[0]

    logger.info("\n" + "=" * 70)
    logger.info("FINAL RECOMMENDATION")
    logger.info("=" * 70)

    cagr_delta = best["cagr"] * 100 - base_m.cagr * 100
    mdd_delta = abs(best["mdd"]) - abs(base_m.max_drawdown_pct)

    logger.info(f"  Baseline CAGR:     {base_m.cagr*100:.2f}%")
    logger.info(f"  Best ext CAGR:     {best['cagr']*100:.2f}% ({cagr_delta:+.2f}%p)")
    logger.info(f"  MDD change:        {mdd_delta:+.1f}%p")
    logger.info(f"  Ext trades WR:     {best['ext_wr']:.0f}%")

    recommend = cagr_delta > 0 and best["ext_wr"] >= 40 and mdd_delta <= 2.0
    if recommend:
        bp = best["params"]
        logger.info(f"\n  → RECOMMEND ENABLING with:")
        logger.info(f"    EXTENDED_HOURS_ENABLED=true")
        logger.info(f"    EXTENDED_HOURS_MAX_POSITION_PCT={bp['max_position_pct']}")
        logger.info(f"    EXTENDED_HOURS_SLIPPAGE_MULTIPLIER={bp['slippage_mult']}")
        logger.info(f"    EXTENDED_HOURS_FILL_PROBABILITY={bp['fill_prob']}")
        logger.info(f"    EXTENDED_HOURS_MIN_CONFIDENCE={bp['min_conf']}")
    else:
        logger.info(f"\n  → DO NOT ENABLE yet. Criteria not met.")
        if cagr_delta <= 0:
            logger.info(f"    - CAGR did not improve")
        if best["ext_wr"] < 40:
            logger.info(f"    - Ext WR {best['ext_wr']:.0f}% < 40%")
        if mdd_delta > 2.0:
            logger.info(f"    - MDD worsened by {mdd_delta:.1f}%p > 2%p")


if __name__ == "__main__":
    asyncio.run(main())
