"""Backtest public edition strategies (trend_following + macd_histogram).

Runs individual strategy backtests on representative US stocks,
then a full pipeline backtest with only public strategies enabled.

Usage:
    cd backend && ../venv/bin/python scripts/run_public_backtest.py
"""

import asyncio
import sys
import logging

sys.path.insert(0, ".")

from backtest.engine import BacktestEngine, BacktestResult
from backtest.simulator import SimConfig
from backtest.full_pipeline import FullPipelineBacktest, PipelineConfig
from strategies.trend_following import TrendFollowingStrategy
from strategies.macd_histogram import MACDHistogramStrategy

logging.basicConfig(
    level=logging.WARNING,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
for name in ("httpx", "urllib3", "yfinance", "peewee", "backtest", "strategies", "data"):
    logging.getLogger(name).setLevel(logging.WARNING)


# Representative US stocks across sectors
TEST_SYMBOLS = [
    "AAPL", "MSFT", "NVDA",  # Tech
    "JPM", "GS",              # Financials
    "XOM", "CVX",             # Energy
    "AMZN", "TSLA",           # Consumer/Growth
    "JNJ", "UNH",             # Healthcare
]


async def run_individual_backtests():
    """Run each public strategy on multiple symbols."""
    strategies = [
        ("trend_following", TrendFollowingStrategy()),
        ("macd_histogram", MACDHistogramStrategy()),
    ]

    sim_config = SimConfig(
        initial_equity=100_000,
        slippage_pct=0.05,
        max_position_pct=0.10,
        stop_loss_pct=0.10,
        take_profit_pct=0.20,
        trailing_stop_activation_pct=0.08,
        trailing_stop_trail_pct=0.05,
        volume_adjusted_slippage=True,
    )

    engine = BacktestEngine(sim_config=sim_config)

    for name, strategy in strategies:
        print(f"\n{'='*60}")
        print(f"  Strategy: {name}")
        print(f"{'='*60}")

        results: list[BacktestResult] = []
        for symbol in TEST_SYMBOLS:
            try:
                result = await engine.run(strategy, symbol, period="2y")
                results.append(result)
                status = "PASS" if result.passed else "FAIL"
                m = result.metrics
                print(
                    f"  [{status}] {symbol:6s}  "
                    f"Ret={m.total_return_pct:+6.1f}%  "
                    f"Sharpe={m.sharpe_ratio:+5.2f}  "
                    f"MDD={m.max_drawdown_pct:5.1f}%  "
                    f"PF={m.profit_factor:5.2f}  "
                    f"Trades={m.total_trades:3d}  "
                    f"WR={m.win_rate:5.1f}%"
                )
            except Exception as e:
                print(f"  [ERROR] {symbol}: {e}")

        if results:
            avg_ret = sum(r.metrics.total_return_pct for r in results) / len(results)
            avg_sharpe = sum(r.metrics.sharpe_ratio for r in results) / len(results)
            avg_mdd = sum(r.metrics.max_drawdown_pct for r in results) / len(results)
            avg_pf = sum(r.metrics.profit_factor for r in results) / len(results)
            avg_wr = sum(r.metrics.win_rate for r in results) / len(results)
            print(f"\n  AVERAGE: Ret={avg_ret:+.1f}%  Sharpe={avg_sharpe:+.2f}  "
                  f"MDD={avg_mdd:.1f}%  PF={avg_pf:.2f}  WR={avg_wr:.1f}%")


async def run_full_pipeline():
    """Run full pipeline with only public strategies."""
    print(f"\n{'='*60}")
    print(f"  Full Pipeline Backtest (Public Strategies Only)")
    print(f"{'='*60}")

    config = PipelineConfig(
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
        # Disable all strategies except the public ones
        disabled_strategies=[
            "dual_momentum", "donchian_breakout", "supertrend",
            "rsi_divergence", "bollinger_squeeze", "volume_profile",
            "cis_momentum", "larry_williams", "bnf_deviation",
            "volume_surge", "cross_sectional_momentum", "quality_factor",
            "pead_drift",
        ],
    )

    bt = FullPipelineBacktest(config)
    result = await bt.run(period="2y")

    print(result.summary())

    if result.strategy_stats:
        print("\nStrategy breakdown:")
        for name, stats in sorted(
            result.strategy_stats.items(),
            key=lambda x: x[1]["pnl"], reverse=True,
        ):
            if stats["trades"] > 0:
                print(
                    f"  {name:25s} trades={stats['trades']:3d}  "
                    f"WR={stats['win_rate']:5.1f}%  "
                    f"PnL=${stats['pnl']:+,.0f}"
                )


async def main():
    print("=" * 60)
    print("  StockBot Public Edition — Strategy Backtest")
    print("  Strategies: trend_following, macd_histogram, ETF engine")
    print("=" * 60)

    await run_individual_backtests()
    await run_full_pipeline()

    print("\n" + "=" * 60)
    print("  Done. Use these results to verify public config params.")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
