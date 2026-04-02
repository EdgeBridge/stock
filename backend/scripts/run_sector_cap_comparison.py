"""Compare US strategy combos with/without sector cap.

Usage:
    cd backend && ../venv/bin/python scripts/run_sector_cap_comparison.py
"""

import asyncio
import logging
import sys

sys.path.insert(0, ".")

from backtest.full_pipeline import FullPipelineBacktest, PipelineConfig

logging.basicConfig(level=logging.WARNING)
for name in (
    "httpx", "urllib3", "yfinance", "peewee",
    "backtest", "strategies", "data",
):
    logging.getLogger(name).setLevel(logging.WARNING)

ALL_STRATEGIES = [
    "trend_following", "donchian_breakout", "supertrend",
    "macd_histogram", "dual_momentum", "rsi_divergence",
    "bollinger_squeeze", "volume_profile", "regime_switch",
    "sector_rotation", "cis_momentum", "larry_williams",
    "bnf_deviation", "volume_surge",
]


def disable_except(keep):
    return [s for s in ALL_STRATEGIES if s not in keep]


async def run(config):
    bt = FullPipelineBacktest(config)
    result = await bt.run(period="5y")
    return result


def base_config(**overrides):
    """Grid search optimal US params as base."""
    defaults = dict(
        market="US",
        initial_equity=100_000,
        default_stop_loss_pct=0.07,
        default_take_profit_pct=0.15,
        dynamic_sl_tp=False,
        kelly_fraction=1.50,
        min_position_pct=0.15,
        max_positions=5,
        max_position_pct=0.30,
        min_confidence=0.30,
        min_active_ratio=0.0,
        slippage_pct=0.05,
        volume_adjusted_slippage=True,
        sell_cooldown_days=1,
        whipsaw_max_losses=2,
        min_hold_days=1,
    )
    defaults.update(overrides)
    return PipelineConfig(**defaults)


async def main():
    combos = [
        (
            "A. Top3 (baseline)",
            ["sector_rotation", "volume_profile", "volume_surge"],
            {},
        ),
        (
            "B. Top3 + dual_momentum (no cap)",
            ["sector_rotation", "volume_profile", "volume_surge", "dual_momentum"],
            {},
        ),
        (
            "C. Top3 + dual_momentum (sector 50% cap)",
            ["sector_rotation", "volume_profile", "volume_surge", "dual_momentum"],
            {"max_sector_pct": 0.50},
        ),
        (
            "D. Top3 + dual_momentum (sector 40% cap)",
            ["sector_rotation", "volume_profile", "volume_surge", "dual_momentum"],
            {"max_sector_pct": 0.40},
        ),
    ]

    print("=" * 130)
    print("US STRATEGY COMBO COMPARISON — sector cap test")
    print("=" * 130)
    hdr = (
        f"{'Config':55s} {'Ret':>7s} {'Sharpe':>7s} "
        f"{'MDD':>7s} {'Trades':>6s} {'WR':>6s} {'PF':>6s}"
    )
    print(hdr)
    print("-" * 130)

    results = []
    for label, keep, extra in combos:
        disabled = disable_except(keep)
        try:
            result = await run(base_config(
                disabled_strategies=disabled,
                **extra,
            ))
            m = result.metrics
            # Per-strategy breakdown
            strat_lines = []
            for sname, stats in sorted(
                result.strategy_stats.items(),
                key=lambda x: x[1]["pnl"],
                reverse=True,
            ):
                if stats["trades"] > 0:
                    strat_lines.append(
                        f"{sname}={stats['trades']}t/"
                        f"WR{stats['win_rate']:.0f}%/"
                        f"PnL{stats['pnl']:+,.0f}"
                    )

            print(
                f"  {label:53s} {m.total_return_pct:>+6.1f}% "
                f"{m.sharpe_ratio:>+6.2f} {m.max_drawdown_pct:>6.1f}% "
                f"{m.total_trades:>5d} {m.win_rate:>5.1f}% "
                f"{m.profit_factor:>5.2f}"
            )
            print(f"    {' | '.join(strat_lines)}")
            results.append((label, m))
        except Exception as e:
            print(f"  {label:53s} ERROR: {e}")

    print("\n" + "=" * 130)
    print("SUMMARY:")
    for label, m in results:
        print(
            f"  {label:53s} Ret={m.total_return_pct:+.1f}%  "
            f"Sharpe={m.sharpe_ratio:+.2f}  MDD={m.max_drawdown_pct:.1f}%  "
            f"Trades={m.total_trades}  WR={m.win_rate:.1f}%  "
            f"PF={m.profit_factor:.2f}"
        )
    print("=" * 130)


if __name__ == "__main__":
    asyncio.run(main())
