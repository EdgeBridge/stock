"""Backtest data loader using yfinance.

Loads historical OHLCV data and prepares it with technical indicators
for strategy backtesting.
"""

import logging
from dataclasses import dataclass

import pandas as pd
import yfinance as yf

from data.indicator_service import IndicatorService

logger = logging.getLogger(__name__)


@dataclass
class BacktestData:
    symbol: str
    df: pd.DataFrame
    start_date: str
    end_date: str

    @property
    def trading_days(self) -> int:
        return len(self.df)


class BacktestDataLoader:
    """Load and prepare historical data for backtesting."""

    def __init__(self, indicator_service: IndicatorService | None = None):
        self._indicator_svc = indicator_service or IndicatorService()

    def load(
        self,
        symbol: str,
        period: str = "3y",
        interval: str = "1d",
        start: str | None = None,
        end: str | None = None,
    ) -> BacktestData:
        """Load historical data from yfinance.

        Args:
            symbol: Ticker symbol (e.g. 'AAPL')
            period: Data period ('1y', '3y', '5y', 'max')
            interval: Data interval ('1d', '1wk')
            start: Start date (YYYY-MM-DD), overrides period
            end: End date (YYYY-MM-DD)

        Returns:
            BacktestData with OHLCV + indicators
        """
        ticker = yf.Ticker(symbol)

        if start:
            df = ticker.history(start=start, end=end, interval=interval)
        else:
            df = ticker.history(period=period, interval=interval)

        if df.empty:
            raise ValueError(f"No data available for {symbol}")

        df.columns = [c.lower().replace(" ", "_") for c in df.columns]
        df = df[["open", "high", "low", "close", "volume"]].copy()
        df = df.dropna()

        # Add technical indicators
        df = self._indicator_svc.add_all_indicators(df)

        start_date = str(df.index[0].date()) if hasattr(df.index[0], "date") else str(df.index[0])
        end_date = str(df.index[-1].date()) if hasattr(df.index[-1], "date") else str(df.index[-1])

        logger.info(
            "Loaded %d bars for %s (%s to %s)",
            len(df), symbol, start_date, end_date,
        )

        return BacktestData(
            symbol=symbol,
            df=df,
            start_date=start_date,
            end_date=end_date,
        )

    def load_multiple(
        self,
        symbols: list[str],
        period: str = "3y",
        interval: str = "1d",
    ) -> dict[str, BacktestData]:
        """Load data for multiple symbols."""
        result = {}
        for symbol in symbols:
            try:
                result[symbol] = self.load(symbol, period=period, interval=interval)
            except Exception as e:
                logger.warning("Failed to load data for %s: %s", symbol, e)
        return result
