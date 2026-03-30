"""Run KR market full pipeline backtest.

Usage:
    cd backend && ../venv/bin/python scripts/run_kr_backtest.py
"""

import asyncio
import sys
import logging

# Add backend to path
sys.path.insert(0, ".")

from backtest.full_pipeline import FullPipelineBacktest, PipelineConfig

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
# Suppress noisy loggers
for name in ("httpx", "urllib3", "yfinance", "peewee"):
    logging.getLogger(name).setLevel(logging.WARNING)


async def main():
    config = PipelineConfig(
        market="KR",
        initial_equity=5_000_000,  # 500만원
        # KR risk params (matching live)
        default_stop_loss_pct=0.12,
        default_take_profit_pct=0.20,
        max_positions=15,
        max_position_pct=0.10,
        # Trading gates (matching live)
        sell_cooldown_days=1,
        whipsaw_max_losses=2,
        min_hold_days=1,
        # Slippage (KR has wider spreads)
        slippage_pct=0.10,
        volume_adjusted_slippage=True,
    )

    bt = FullPipelineBacktest(config)
    print(f"\nKR Backtest — Universe: {len(config.universe)} stocks")
    print(f"Regime symbol: {config.regime_symbol}")
    print(f"Initial equity: ₩{config.initial_equity:,.0f}\n")

    result = await bt.run(period="2y")

    print("\n" + "=" * 60)
    print(result.summary())
    print("=" * 60)

    # Per-strategy breakdown
    if result.strategy_stats:
        print("\nStrategy breakdown:")
        for name, stats in sorted(
            result.strategy_stats.items(),
            key=lambda x: x[1]["trades"], reverse=True,
        ):
            if stats["trades"] > 0:
                print(
                    f"  {name:25s} trades={stats['trades']:3d}  "
                    f"WR={stats['win_rate']:5.1f}%  "
                    f"PnL=₩{stats['pnl']:+,.0f}"
                )

    # Top 10 worst trades
    sells = [t for t in result.trades if t.side == "SELL"]
    worst = sorted(sells, key=lambda t: t.pnl)[:10]
    if worst:
        print("\nWorst 10 trades:")
        for t in worst:
            print(
                f"  {t.symbol:12s} {t.strategy_name:20s} "
                f"PnL=₩{t.pnl:+,.0f} ({t.pnl_pct:+.1f}%)  "
                f"hold={t.holding_days}d"
            )


if __name__ == "__main__":
    asyncio.run(main())
