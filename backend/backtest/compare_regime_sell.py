"""Compare full pipeline backtest with and without regime-change protective sells.

Usage:
    cd backend && python -m backtest.compare_regime_sell
"""

import asyncio
import logging
import sys

from backtest.full_pipeline import FullPipelineBacktest, PipelineConfig

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)

# Smaller universe for faster comparison
TEST_UNIVERSE = [
    "AAPL", "MSFT", "GOOGL", "AMZN", "NVDA", "META", "TSLA", "AVGO",
    "AMD", "INTC", "QCOM", "CRM", "ADBE", "ORCL",
    "JPM", "BAC", "GS", "WFC",
    "UNH", "JNJ", "LLY", "MRK",
    "WMT", "HD", "COST", "NKE",
    "XOM", "CVX", "COP",
    "CAT", "BA", "HON",
]


async def main():
    period = sys.argv[1] if len(sys.argv) > 1 else "3y"

    base_cfg = dict(
        universe=list(TEST_UNIVERSE),
        initial_equity=100_000,
        max_positions=15,
        max_watchlist=20,
        screen_interval=20,
    )

    # Run WITHOUT regime sells
    cfg_off = PipelineConfig(**base_cfg, enable_regime_sells=False)
    engine_off = FullPipelineBacktest(cfg_off)
    logger.info("=" * 60)
    logger.info("Running WITHOUT regime protective sells...")
    logger.info("=" * 60)
    result_off = await engine_off.run(period=period)

    # Run WITH regime sells
    cfg_on = PipelineConfig(**base_cfg, enable_regime_sells=True)
    engine_on = FullPipelineBacktest(cfg_on)
    logger.info("\n" + "=" * 60)
    logger.info("Running WITH regime protective sells...")
    logger.info("=" * 60)
    result_on = await engine_on.run(period=period)

    # Compare
    m_off = result_off.metrics
    m_on = result_on.metrics

    logger.info("\n" + "=" * 60)
    logger.info("COMPARISON: Regime Protective Sells")
    logger.info("=" * 60)

    def fmt(label, val_off, val_on, suffix="", higher_better=True):
        diff = val_on - val_off
        direction = "+" if diff > 0 else ""
        better = (diff > 0) == higher_better
        marker = " <<" if better and abs(diff) > 0.1 else ""
        return (
            f"  {label:20s}  {val_off:>10{suffix}}  {val_on:>10{suffix}}"
            f"  ({direction}{diff:{suffix}}){marker}"
        )

    logger.info(f"  {'':20s}  {'OFF':>10s}  {'ON':>10s}  {'DIFF':>10s}")
    logger.info(f"  {'-' * 60}")
    logger.info(fmt("CAGR", m_off.cagr * 100, m_on.cagr * 100, ".1f"))
    logger.info(fmt("Total Return %", m_off.total_return_pct, m_on.total_return_pct, ".1f"))
    logger.info(fmt("Sharpe", m_off.sharpe_ratio, m_on.sharpe_ratio, ".2f"))
    logger.info(fmt("Sortino", m_off.sortino_ratio, m_on.sortino_ratio, ".2f"))
    logger.info(fmt("MDD %", m_off.max_drawdown_pct, m_on.max_drawdown_pct, ".1f", higher_better=False))
    logger.info(fmt("MDD Days", m_off.max_drawdown_days, m_on.max_drawdown_days, ".0f", higher_better=False))
    logger.info(fmt("Win Rate %", m_off.win_rate, m_on.win_rate, ".1f"))
    logger.info(fmt("Profit Factor", m_off.profit_factor, m_on.profit_factor, ".2f"))
    logger.info(fmt("Total Trades", m_off.total_trades, m_on.total_trades, ".0f"))
    logger.info(fmt("Final Equity", m_off.final_equity, m_on.final_equity, ",.0f"))
    logger.info(fmt("Alpha %", m_off.alpha, m_on.alpha, ".1f"))

    # Count regime sells
    regime_sells = [t for t in result_on.trades if t.strategy_name == "regime_protect"]
    if regime_sells:
        regime_pnl = sum(t.pnl for t in regime_sells)
        regime_winners = sum(1 for t in regime_sells if t.pnl > 0)
        logger.info(f"\n  Regime sells: {len(regime_sells)} trades, "
                     f"PnL=${regime_pnl:+,.0f}, "
                     f"WR={regime_winners/len(regime_sells)*100:.0f}%")
    else:
        logger.info("\n  No regime sells triggered during this period")


if __name__ == "__main__":
    asyncio.run(main())
