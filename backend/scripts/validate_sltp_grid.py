"""SL/TP grid search — zoom into the winner from structural experiments.

H_wider_sl_tp (SL=15%, TP=30%) was the clear winner.
Now grid-search around that region + combine with cash parking.

Usage:
    cd backend && ../venv/bin/python scripts/validate_sltp_grid.py
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


BASE = dict(
    market="US",
    initial_equity=100_000,
    max_positions=20,
    max_position_pct=0.08,
    sell_cooldown_days=1,
    whipsaw_max_losses=2,
    min_hold_days=1,
    slippage_pct=0.05,
    volume_adjusted_slippage=True,
    min_confidence=0.50,
    held_sell_bias=0.05,
    held_min_confidence=0.40,
    disabled_strategies=[
        "bollinger_squeeze", "volume_profile",
        "cis_momentum", "larry_williams", "bnf_deviation",
    ],
)


# SL/TP grid + trailing stop variants
VARIANTS = {}

# Grid: SL ∈ {10%, 12%, 15%, 18%} × TP ∈ {20%, 25%, 30%, 35%, 40%}
for sl in [0.10, 0.12, 0.15, 0.18]:
    for tp in [0.20, 0.25, 0.30, 0.35, 0.40]:
        name = f"SL{int(sl*100):02d}_TP{int(tp*100):02d}"
        VARIANTS[name] = {
            "default_stop_loss_pct": sl,
            "default_take_profit_pct": tp,
        }

# Best SL/TP combos + cash parking
for sl, tp in [(0.15, 0.30), (0.15, 0.35), (0.18, 0.30), (0.18, 0.35)]:
    name = f"SL{int(sl*100):02d}_TP{int(tp*100):02d}_park"
    VARIANTS[name] = {
        "default_stop_loss_pct": sl,
        "default_take_profit_pct": tp,
        "enable_cash_parking": True,
        "cash_parking_threshold": 0.25,
    }

# Trailing stop variations on the winner
for trail_act, trail_pct in [(0.06, 0.03), (0.08, 0.04), (0.10, 0.05), (0.12, 0.05)]:
    name = f"SL15_TP30_trail{int(trail_act*100):02d}_{int(trail_pct*100):02d}"
    VARIANTS[name] = {
        "default_stop_loss_pct": 0.15,
        "default_take_profit_pct": 0.30,
        "trailing_activation_pct": trail_act,
        "trailing_trail_pct": trail_pct,
    }


async def run_variant(name: str, overrides: dict) -> dict:
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
    print("=" * 95)
    print("  SL/TP Grid Search — Full Pipeline Backtest (US, 2Y)")
    print(f"  {len(VARIANTS)} variants")
    print("=" * 95)
    print()

    results = []
    for i, (name, overrides) in enumerate(VARIANTS.items()):
        desc = ", ".join(f"{k}={v}" for k, v in overrides.items())
        print(f"[{i+1}/{len(VARIANTS)}] {name}: {desc}")
        r = await run_variant(name, overrides)
        results.append(r)
        print(f"  → Ret={r['return']:+.1f}%  Sharpe={r['sharpe']:.2f}  "
              f"MDD={r['mdd']:.1f}%  Alpha={r['alpha']:+.1f}%  ({r['elapsed']:.0f}s)")

    # Sort by Sharpe
    results.sort(key=lambda x: x["sharpe"], reverse=True)

    print()
    print("=" * 95)
    print("  Results sorted by Sharpe ratio")
    print("=" * 95)
    print(f"{'Rank':<5} {'Variant':<28} {'Ret%':>7} {'Sharpe':>7} {'Sortino':>8} "
          f"{'MDD%':>7} {'Trades':>7} {'WR%':>6} {'PF':>6} {'Alpha%':>8}")
    print("-" * 95)

    for i, r in enumerate(results):
        print(f"{i+1:<5} {r['name']:<28} {r['return']:>+7.1f} {r['sharpe']:>7.2f} "
              f"{r['sortino']:>8.2f} {r['mdd']:>7.1f} {r['trades']:>7d} {r['win_rate']:>6.1f} "
              f"{r['pf']:>6.2f} {r['alpha']:>+8.1f}")

    print("-" * 95)
    print(f"{'':5} {'Benchmark (SPY)':<28} {results[0]['bench']:>+7.1f}")
    print()

    # Top 5 highlight
    print("═" * 60)
    print("  TOP 5")
    print("═" * 60)
    for i, r in enumerate(results[:5]):
        print(f"  #{i+1} {r['name']}: Ret={r['return']:+.1f}%  Sharpe={r['sharpe']:.2f}  "
              f"MDD={r['mdd']:.1f}%  Alpha={r['alpha']:+.1f}%  PF={r['pf']:.2f}")
    print()

    # SL/TP heatmap (text-based)
    print("SL/TP Sharpe Heatmap:")
    sls = sorted(set(int(r["name"].split("_")[0][2:]) for r in results if r["name"].startswith("SL") and "_TP" in r["name"] and "park" not in r["name"] and "trail" not in r["name"]))
    tps = sorted(set(int(r["name"].split("_")[1][2:]) for r in results if r["name"].startswith("SL") and "_TP" in r["name"] and "park" not in r["name"] and "trail" not in r["name"]))

    sharpe_map = {}
    for r in results:
        if r["name"].startswith("SL") and "park" not in r["name"] and "trail" not in r["name"]:
            parts = r["name"].split("_")
            if len(parts) == 2:
                sharpe_map[(parts[0], parts[1])] = r["sharpe"]

    print(f"{'':>8}", end="")
    for tp in tps:
        print(f"  TP{tp:02d}", end="")
    print()

    for sl in sls:
        print(f"  SL{sl:02d}  ", end="")
        for tp in tps:
            key = (f"SL{sl:02d}", f"TP{tp:02d}")
            s = sharpe_map.get(key, 0)
            if s >= 1.0:
                print(f" {s:5.2f}★", end="")
            elif s >= 0.7:
                print(f" {s:5.2f}+", end="")
            else:
                print(f" {s:5.2f} ", end="")
        print()
    print()


if __name__ == "__main__":
    asyncio.run(main())
