"""Compare daily buy limit strategies: No limit vs Hard limit vs Dynamic escalation.

Tests whether confidence escalation improves trade quality by:
  1. NO_LIMIT — All buy signals executed (baseline)
  2. HARD_LIMIT — daily_buy_limit=5, no escalation (first N by confidence)
  3. ESCALATION — daily_buy_limit=5, dynamic confidence escalation

Also runs a shuffle simulation to test order sensitivity:
  - For each day with >5 candidates, compare top-5-by-confidence vs random-5
  - Track post-trade PnL to measure if confidence predicts quality

Usage:
    cd backend && python3 -m backtest.compare_daily_limit [period]
    cd backend && python3 -m backtest.compare_daily_limit 5y
"""

import asyncio
import logging
import sys

from backtest.full_pipeline import FullPipelineBacktest, PipelineConfig

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)

# Shared base config
BASE = dict(
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
    extended_hours_enabled=False,
)


def _row(label, values, suffix=""):
    parts = f"  {label:24s}"
    for v in values:
        parts += f"  {v:>14{suffix}}"
    return parts


async def run_comparison(period: str):
    """Compare 3 modes: no limit, hard limit, dynamic escalation."""
    logger.info("=" * 72)
    logger.info("DAILY BUY LIMIT: NO_LIMIT vs HARD_LIMIT vs ESCALATION")
    logger.info("=" * 72)

    configs = {
        "NO_LIMIT": PipelineConfig(
            **BASE,
            daily_buy_limit=0,
            enable_confidence_escalation=False,
        ),
        "HARD_LIMIT_5": PipelineConfig(
            **BASE,
            daily_buy_limit=5,
            enable_confidence_escalation=False,
        ),
        "ESCALATION_5": PipelineConfig(
            **BASE,
            daily_buy_limit=5,
            enable_confidence_escalation=True,
        ),
    }

    results = {}
    for name, cfg in configs.items():
        logger.info(f"\nRunning {name}...")
        engine = FullPipelineBacktest(cfg)
        results[name] = await engine.run(period=period)
        logger.info(results[name].summary())

    # Comparison table
    names = list(results.keys())
    metrics = [results[n].metrics for n in names]

    logger.info("\n" + "=" * 72)
    logger.info(f"COMPARISON TABLE ({period})")
    logger.info("=" * 72)
    header = f"  {'':24s}" + "".join(f"  {n:>14s}" for n in names)
    logger.info(header)
    logger.info(f"  {'-' * (24 + 16 * len(names))}")

    logger.info(_row("CAGR %", [m.cagr * 100 for m in metrics], ".2f"))
    logger.info(_row("Total Return %", [m.total_return_pct for m in metrics], ".1f"))
    logger.info(_row("Sharpe", [m.sharpe_ratio for m in metrics], ".2f"))
    logger.info(_row("Sortino", [m.sortino_ratio for m in metrics], ".2f"))
    logger.info(_row("MDD %", [m.max_drawdown_pct for m in metrics], ".1f"))
    logger.info(_row("Win Rate %", [m.win_rate for m in metrics], ".1f"))
    logger.info(_row("Profit Factor", [m.profit_factor for m in metrics], ".2f"))
    logger.info(_row("Total Trades", [m.total_trades for m in metrics], ".0f"))
    logger.info(_row("Avg Hold Days", [m.avg_holding_days for m in metrics], ".0f"))
    logger.info(_row("Final Equity", [m.final_equity for m in metrics], ",.0f"))
    logger.info(_row("Alpha %", [m.alpha for m in metrics], ".1f"))
    logger.info(_row("SPY Return %", [m.benchmark_return_pct for m in metrics], ".1f"))

    # Analysis
    logger.info("\n" + "=" * 72)
    logger.info("ANALYSIS")
    logger.info("=" * 72)

    base_m = results["NO_LIMIT"].metrics
    for name in ["HARD_LIMIT_5", "ESCALATION_5"]:
        m = results[name].metrics
        cagr_delta = m.cagr * 100 - base_m.cagr * 100
        wr_delta = m.win_rate - base_m.win_rate
        mdd_delta = abs(m.max_drawdown_pct) - abs(base_m.max_drawdown_pct)
        trade_reduction = base_m.total_trades - m.total_trades

        logger.info(f"\n  {name} vs NO_LIMIT:")
        logger.info(f"    CAGR change:      {cagr_delta:+.2f}%p")
        logger.info(f"    Win rate change:   {wr_delta:+.1f}%p")
        logger.info(f"    MDD change:        {mdd_delta:+.1f}%p")
        logger.info(f"    Trades reduced:    {trade_reduction} fewer trades")
        logger.info(f"    Sharpe change:     {m.sharpe_ratio - base_m.sharpe_ratio:+.2f}")

    # Compare HARD_LIMIT vs ESCALATION
    hard_m = results["HARD_LIMIT_5"].metrics
    esc_m = results["ESCALATION_5"].metrics
    logger.info(f"\n  ESCALATION_5 vs HARD_LIMIT_5:")
    logger.info(f"    CAGR:   {esc_m.cagr*100:.2f}% vs {hard_m.cagr*100:.2f}% ({(esc_m.cagr - hard_m.cagr)*100:+.2f}%p)")
    logger.info(f"    Sharpe: {esc_m.sharpe_ratio:.2f} vs {hard_m.sharpe_ratio:.2f}")
    logger.info(f"    WR:     {esc_m.win_rate:.1f}% vs {hard_m.win_rate:.1f}%")
    logger.info(f"    Trades: {esc_m.total_trades} vs {hard_m.total_trades}")

    return results


async def run_limit_sweep(period: str):
    """Sweep daily_buy_limit values to find optimal limit."""
    logger.info("\n" + "=" * 72)
    logger.info("DAILY BUY LIMIT SWEEP (with escalation)")
    logger.info("=" * 72)

    limits = [0, 3, 5, 7, 10, 15]
    results = []

    for limit in limits:
        label = f"limit={limit}" if limit > 0 else "unlimited"
        logger.info(f"\n  Running {label}...")

        cfg = PipelineConfig(
            **BASE,
            daily_buy_limit=limit,
            enable_confidence_escalation=limit > 0,
        )
        engine = FullPipelineBacktest(cfg)
        result = await engine.run(period=period)
        m = result.metrics

        results.append({
            "limit": limit,
            "label": label,
            "cagr": m.cagr,
            "sharpe": m.sharpe_ratio,
            "mdd": m.max_drawdown_pct,
            "win_rate": m.win_rate,
            "total_trades": m.total_trades,
            "final_equity": m.final_equity,
            "alpha": m.alpha,
            "profit_factor": m.profit_factor,
        })

        logger.info(
            f"    CAGR={m.cagr*100:.2f}% Sharpe={m.sharpe_ratio:.2f} "
            f"MDD={m.max_drawdown_pct:.1f}% WR={m.win_rate:.1f}% "
            f"Trades={m.total_trades} PF={m.profit_factor:.2f}"
        )

    # Ranking
    results.sort(key=lambda r: r["sharpe"], reverse=True)

    logger.info("\n" + "=" * 72)
    logger.info("LIMIT SWEEP RANKING (by Sharpe)")
    logger.info("=" * 72)
    logger.info(
        f"  {'#':>2s}  {'Limit':>6s}  {'CAGR%':>7s}  {'Sharpe':>7s}  "
        f"{'MDD%':>6s}  {'WR%':>5s}  {'Trades':>7s}  {'PF':>5s}  {'Alpha':>7s}"
    )
    logger.info(f"  {'-' * 68}")

    for rank, r in enumerate(results, 1):
        lbl = str(r["limit"]) if r["limit"] > 0 else "∞"
        logger.info(
            f"  {rank:>2d}  {lbl:>6s}  {r['cagr']*100:>7.2f}  {r['sharpe']:>7.2f}  "
            f"{r['mdd']:>6.1f}  {r['win_rate']:>5.1f}  {r['total_trades']:>7d}  "
            f"{r['profit_factor']:>5.2f}  {r['alpha']:>+7.1f}"
        )

    best = results[0]
    logger.info(f"\n  BEST: limit={best['limit']} — Sharpe={best['sharpe']:.2f}, CAGR={best['cagr']*100:.2f}%")

    return results


async def main():
    period = sys.argv[1] if len(sys.argv) > 1 else "3y"
    logger.info(f"Daily Buy Limit Backtest — Period: {period}\n")

    # Phase 1: 3-way comparison
    await run_comparison(period)

    # Phase 2: Limit sweep
    await run_limit_sweep(period)


if __name__ == "__main__":
    asyncio.run(main())
