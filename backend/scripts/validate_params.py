"""Parameter validation via full pipeline backtest.

Compares baseline (current live) vs proposed parameter changes.
Runs each variant and prints side-by-side metrics.

Usage:
    cd backend && ../venv/bin/python scripts/validate_params.py
"""

import asyncio
import sys
import logging
import time

sys.path.insert(0, ".")

from backtest.full_pipeline import FullPipelineBacktest, PipelineConfig

logging.basicConfig(
    level=logging.WARNING,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
for name in ("httpx", "urllib3", "yfinance", "peewee", "backtest", "strategies", "data"):
    logging.getLogger(name).setLevel(logging.WARNING)


# ── Shared base config (current live US settings) ──────────────────────
BASE = dict(
    market="US",
    initial_equity=100_000,
    default_stop_loss_pct=0.12,
    default_take_profit_pct=0.20,
    max_positions=20,
    max_position_pct=0.08,
    sell_cooldown_days=1,
    whipsaw_max_losses=2,
    min_hold_days=1,
    slippage_pct=0.05,
    volume_adjusted_slippage=True,
    disabled_strategies=[
        "bollinger_squeeze", "volume_profile",
        "cis_momentum", "larry_williams", "bnf_deviation",
    ],
)


# ── Variants to test ───────────────────────────────────────────────────
VARIANTS = {
    "A_baseline": {
        # Current live: min_confidence=0.50, held_sell_bias=0.05, held_min_confidence=0.40
        "min_confidence": 0.50,
        "held_sell_bias": 0.05,
        "held_min_confidence": 0.40,
    },
    "B_conf055": {
        # Raise min_confidence 0.50 → 0.55 (stricter entry)
        "min_confidence": 0.55,
        "held_sell_bias": 0.05,
        "held_min_confidence": 0.40,
    },
    "C_sell_bias012": {
        # Raise held_sell_bias 0.05 → 0.12 (more aggressive exits)
        "min_confidence": 0.50,
        "held_sell_bias": 0.12,
        "held_min_confidence": 0.40,
    },
    "D_held_conf035": {
        # Lower held_min_confidence 0.40 → 0.35 (easier to sell losers)
        "min_confidence": 0.50,
        "held_sell_bias": 0.05,
        "held_min_confidence": 0.35,
    },
    "E_combined": {
        # All proposed changes together
        "min_confidence": 0.55,
        "held_sell_bias": 0.12,
        "held_min_confidence": 0.35,
    },
    "F_profit_protect": {
        # Enable profit protection at 20% (force sell big winners)
        "min_confidence": 0.50,
        "held_sell_bias": 0.05,
        "held_min_confidence": 0.40,
        "profit_protection_pct": 0.20,
    },
    "G_stale_sell": {
        # Sell stale losers at -3% (was -5%)
        "min_confidence": 0.50,
        "held_sell_bias": 0.05,
        "held_min_confidence": 0.40,
        "stale_pnl_threshold": -0.03,
    },
}


async def run_variant(name: str, overrides: dict) -> dict:
    """Run a single backtest variant and return key metrics."""
    config = PipelineConfig(**{**BASE, **overrides})
    engine = FullPipelineBacktest(config)

    t0 = time.time()
    result = await engine.run(period="2y")
    elapsed = time.time() - t0

    m = result.metrics
    return {
        "name": name,
        "return": m.total_return_pct,
        "cagr": m.cagr * 100 if m.cagr else 0,
        "sharpe": m.sharpe_ratio,
        "sortino": m.sortino_ratio,
        "mdd": m.max_drawdown_pct,
        "trades": m.total_trades,
        "win_rate": m.win_rate,
        "pf": m.profit_factor,
        "alpha": m.alpha,
        "bench": m.benchmark_return_pct,
        "elapsed": elapsed,
    }


async def main():
    print("=" * 90)
    print("  Parameter Validation — Full Pipeline Backtest (US, 2Y)")
    print("=" * 90)
    print()

    # Run all variants sequentially (yfinance data is cached after first run)
    results = []
    for name, overrides in VARIANTS.items():
        desc = ", ".join(f"{k}={v}" for k, v in overrides.items())
        print(f"▶ Running {name}: {desc}")
        r = await run_variant(name, overrides)
        results.append(r)
        print(f"  → Return={r['return']:+.1f}%  Sharpe={r['sharpe']:.2f}  "
              f"MDD={r['mdd']:.1f}%  Alpha={r['alpha']:+.1f}%  ({r['elapsed']:.0f}s)")
        print()

    # ── Summary table ──
    print()
    print("=" * 90)
    print(f"{'Variant':<20} {'Ret%':>7} {'CAGR%':>7} {'Sharpe':>7} {'Sortino':>8} "
          f"{'MDD%':>7} {'Trades':>7} {'WR%':>6} {'PF':>6} {'Alpha%':>8}")
    print("-" * 90)

    baseline = results[0]
    for r in results:
        # Highlight improvements over baseline
        ret_delta = r["return"] - baseline["return"]
        sharpe_delta = r["sharpe"] - baseline["sharpe"]

        marker = ""
        if r["name"] != "A_baseline":
            if ret_delta > 0 and sharpe_delta > 0:
                marker = " ✓"
            elif ret_delta < -2 or sharpe_delta < -0.1:
                marker = " ✗"

        print(f"{r['name']:<20} {r['return']:>+7.1f} {r['cagr']:>7.1f} {r['sharpe']:>7.2f} "
              f"{r['sortino']:>8.2f} {r['mdd']:>7.1f} {r['trades']:>7d} {r['win_rate']:>6.1f} "
              f"{r['pf']:>6.2f} {r['alpha']:>+8.1f}{marker}")

    print("-" * 90)
    print(f"{'Benchmark (SPY)':<20} {baseline['bench']:>+7.1f}")
    print()

    # ── Delta table vs baseline ──
    print("Delta vs baseline (A):")
    print(f"{'Variant':<20} {'ΔRet%':>7} {'ΔSharpe':>8} {'ΔMDD%':>7} {'ΔAlpha%':>8} {'ΔWR%':>7} {'ΔPF':>6}")
    print("-" * 65)
    for r in results[1:]:
        print(f"{r['name']:<20} "
              f"{r['return'] - baseline['return']:>+7.1f} "
              f"{r['sharpe'] - baseline['sharpe']:>+8.2f} "
              f"{r['mdd'] - baseline['mdd']:>+7.1f} "
              f"{r['alpha'] - baseline['alpha']:>+8.1f} "
              f"{r['win_rate'] - baseline['win_rate']:>+7.1f} "
              f"{r['pf'] - baseline['pf']:>+6.2f}")
    print()


if __name__ == "__main__":
    asyncio.run(main())
