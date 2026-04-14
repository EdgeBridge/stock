"""Structural alpha experiments — beyond parameter tuning.

Tests architectural changes:
  1. Cash parking (idle cash → SPY)
  2. Concentrated portfolio (fewer, bigger positions)
  3. Momentum factor tilt (favor high-momentum stocks)
  4. Quality amplification (boost winning strategies)
  5. No regime sells (let positions ride through volatility)
  6. Leveraged ETF overlay (TQQQ in uptrend)
  7. Best combination

Usage:
    cd backend && ../venv/bin/python scripts/validate_structural.py
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
    min_confidence=0.50,
    held_sell_bias=0.05,
    held_min_confidence=0.40,
    disabled_strategies=[
        "bollinger_squeeze", "volume_profile",
        "cis_momentum", "larry_williams", "bnf_deviation",
    ],
)


VARIANTS = {
    "A_baseline": {},

    "B_cash_park": {
        # Park idle cash in SPY to reduce cash drag
        "enable_cash_parking": True,
        "cash_parking_threshold": 0.25,  # Park when >25% cash
    },

    "C_concentrated": {
        # Fewer positions, bigger sizing → less diversification drag
        "max_positions": 10,
        "max_position_pct": 0.15,
        "max_exposure_pct": 0.95,
    },

    "D_momentum_tilt": {
        # Factor-based position sizing: high momentum → bigger position
        "enable_momentum_tilt": True,
        "momentum_update_interval": 10,
    },

    "E_quality_amp": {
        # Boost weights of winning strategies based on live PnL
        "enable_quality_amplification": True,
        "quality_blend_alpha": 0.4,
        "min_trades_for_quality": 20,
    },

    "F_no_regime_sell": {
        # Don't panic-sell on regime change — let positions ride
        "enable_regime_sells": False,
    },

    "G_leveraged_etf": {
        # TQQQ overlay in uptrend regimes (20% max)
        "enable_leveraged_etf": True,
        "etf_max_allocation_pct": 0.20,
    },

    "H_wider_sl_tp": {
        # Wider SL/TP: let winners run, tolerate more drawdown
        "default_stop_loss_pct": 0.15,
        "default_take_profit_pct": 0.30,
        "trailing_activation_pct": 0.08,
        "trailing_trail_pct": 0.04,
    },

    "I_aggressive_combo": {
        # Best-looking structural changes combined
        "enable_cash_parking": True,
        "cash_parking_threshold": 0.25,
        "max_positions": 12,
        "max_position_pct": 0.12,
        "max_exposure_pct": 0.95,
        "enable_momentum_tilt": True,
        "enable_leveraged_etf": True,
        "etf_max_allocation_pct": 0.15,
        "default_stop_loss_pct": 0.15,
        "default_take_profit_pct": 0.30,
    },

    "J_full_send": {
        # Maximum aggression: concentrated + leveraged + momentum + no regime sells
        "enable_cash_parking": True,
        "cash_parking_threshold": 0.20,
        "max_positions": 8,
        "max_position_pct": 0.18,
        "max_exposure_pct": 0.98,
        "enable_momentum_tilt": True,
        "enable_leveraged_etf": True,
        "etf_max_allocation_pct": 0.25,
        "enable_regime_sells": False,
        "default_stop_loss_pct": 0.15,
        "default_take_profit_pct": 0.35,
    },
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
    print("  Structural Alpha Experiments — Full Pipeline Backtest (US, 2Y)")
    print("=" * 95)
    print()

    results = []
    for name, overrides in VARIANTS.items():
        if overrides:
            desc = ", ".join(f"{k}={v}" for k, v in overrides.items())
        else:
            desc = "current live config"
        print(f"▶ {name}: {desc}")
        r = await run_variant(name, overrides)
        results.append(r)
        print(f"  → Ret={r['return']:+.1f}%  Sharpe={r['sharpe']:.2f}  "
              f"MDD={r['mdd']:.1f}%  Alpha={r['alpha']:+.1f}%  ({r['elapsed']:.0f}s)\n")

    # ── Summary table ──
    print("=" * 95)
    print(f"{'Variant':<22} {'Ret%':>7} {'CAGR%':>7} {'Sharpe':>7} {'Sortino':>8} "
          f"{'MDD%':>7} {'Trades':>7} {'WR%':>6} {'PF':>6} {'Alpha%':>8}")
    print("-" * 95)

    baseline = results[0]
    for r in results:
        marker = ""
        if r["name"] != "A_baseline":
            ret_d = r["return"] - baseline["return"]
            sh_d = r["sharpe"] - baseline["sharpe"]
            if ret_d > 2 and sh_d > 0:
                marker = " ★"
            elif ret_d > 0 and sh_d >= 0:
                marker = " ✓"
            elif ret_d < -2 or sh_d < -0.15:
                marker = " ✗"

        print(f"{r['name']:<22} {r['return']:>+7.1f} {r['cagr']:>7.1f} {r['sharpe']:>7.2f} "
              f"{r['sortino']:>8.2f} {r['mdd']:>7.1f} {r['trades']:>7d} {r['win_rate']:>6.1f} "
              f"{r['pf']:>6.2f} {r['alpha']:>+8.1f}{marker}")

    print("-" * 95)
    print(f"{'Benchmark (SPY)':<22} {baseline['bench']:>+7.1f}")
    print()

    # ── Delta table ──
    print("Delta vs baseline:")
    print(f"{'Variant':<22} {'ΔRet%':>7} {'ΔSharpe':>8} {'ΔMDD%':>7} {'ΔAlpha%':>8} {'ΔWR%':>7} {'ΔPF':>6}")
    print("-" * 70)
    for r in results[1:]:
        print(f"{r['name']:<22} "
              f"{r['return'] - baseline['return']:>+7.1f} "
              f"{r['sharpe'] - baseline['sharpe']:>+8.2f} "
              f"{r['mdd'] - baseline['mdd']:>+7.1f} "
              f"{r['alpha'] - baseline['alpha']:>+8.1f} "
              f"{r['win_rate'] - baseline['win_rate']:>+7.1f} "
              f"{r['pf'] - baseline['pf']:>+6.2f}")
    print()


if __name__ == "__main__":
    asyncio.run(main())
