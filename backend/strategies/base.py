from abc import ABC, abstractmethod
from dataclasses import dataclass, field

import pandas as pd

from core.enums import SignalType


@dataclass
class Signal:
    """Trading signal produced by a strategy."""

    signal_type: SignalType
    confidence: float  # 0.0 to 1.0
    strategy_name: str
    reason: str
    suggested_price: float | None = None
    indicators: dict = field(default_factory=dict)


class BaseStrategy(ABC):
    """Abstract base class for all trading strategies.

    All tunable parameters are loaded from config/strategies.yaml
    and can be updated at runtime via set_params().
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Unique strategy identifier matching config key."""
        ...

    @property
    @abstractmethod
    def display_name(self) -> str:
        ...

    @property
    @abstractmethod
    def applicable_market_types(self) -> list[str]:
        """Market types: 'trending', 'sideways', 'all'."""
        ...

    @property
    @abstractmethod
    def required_timeframe(self) -> str:
        """OHLCV timeframe: '1D', '4h', '1h', etc."""
        ...

    @property
    @abstractmethod
    def min_candles_required(self) -> int:
        ...

    @abstractmethod
    async def analyze(self, df: pd.DataFrame, symbol: str) -> Signal:
        """Analyze OHLCV data and produce a trading signal.

        Args:
            df: DataFrame with columns [open, high, low, close, volume]
                and pre-computed indicators.
            symbol: Stock ticker symbol (e.g. 'AAPL').

        Returns:
            Signal with type, confidence, reason, and indicator snapshot.
        """
        ...

    @abstractmethod
    def get_params(self) -> dict:
        """Return current tunable parameters."""
        ...

    @abstractmethod
    def set_params(self, params: dict) -> None:
        """Update tunable parameters at runtime (from YAML reload)."""
        ...
