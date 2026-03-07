"""Risk manager for position sizing, stop-loss, and portfolio limits.

Enforces:
- Per-position max allocation
- Total portfolio exposure limits
- Stop-loss / take-profit / trailing stop
- Daily loss limit
"""

import logging
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class RiskParams:
    max_position_pct: float = 0.10  # Max 10% per position
    max_total_exposure_pct: float = 0.90  # Max 90% invested
    max_positions: int = 20
    daily_loss_limit_pct: float = 0.03  # Stop trading at 3% daily loss
    default_stop_loss_pct: float = 0.08
    default_take_profit_pct: float = 0.20


@dataclass
class PositionSizeResult:
    quantity: int
    allocation_usd: float
    risk_per_share: float
    reason: str
    allowed: bool = True


class RiskManager:
    """Enforce risk rules before order placement."""

    def __init__(self, params: RiskParams | None = None):
        self._params = params or RiskParams()
        self._daily_pnl: float = 0.0

    def calculate_position_size(
        self,
        symbol: str,
        price: float,
        portfolio_value: float,
        cash_available: float,
        current_positions: int,
        atr: float | None = None,
    ) -> PositionSizeResult:
        """Calculate allowed position size given risk constraints."""
        # Check position limit
        if current_positions >= self._params.max_positions:
            return PositionSizeResult(
                quantity=0, allocation_usd=0, risk_per_share=0,
                reason=f"Max positions reached ({self._params.max_positions})",
                allowed=False,
            )

        # Check daily loss limit
        if self._daily_pnl < 0:
            daily_loss_pct = abs(self._daily_pnl) / portfolio_value
            if daily_loss_pct >= self._params.daily_loss_limit_pct:
                return PositionSizeResult(
                    quantity=0, allocation_usd=0, risk_per_share=0,
                    reason=f"Daily loss limit hit ({daily_loss_pct:.1%})",
                    allowed=False,
                )

        # Max allocation per position
        max_alloc = portfolio_value * self._params.max_position_pct

        # Respect cash available (with buffer)
        max_from_cash = cash_available * 0.95
        allocation = min(max_alloc, max_from_cash)

        if allocation <= 0 or price <= 0:
            return PositionSizeResult(
                quantity=0, allocation_usd=0, risk_per_share=0,
                reason="No cash available",
                allowed=False,
            )

        quantity = int(allocation / price)
        if quantity <= 0:
            return PositionSizeResult(
                quantity=0, allocation_usd=0, risk_per_share=0,
                reason="Price too high for allocation",
                allowed=False,
            )

        risk_per_share = price * self._params.default_stop_loss_pct

        return PositionSizeResult(
            quantity=quantity,
            allocation_usd=quantity * price,
            risk_per_share=risk_per_share,
            reason="OK",
            allowed=True,
        )

    def check_stop_loss(
        self, entry_price: float, current_price: float, stop_loss_pct: float | None = None
    ) -> bool:
        """Return True if stop-loss is triggered."""
        sl = stop_loss_pct or self._params.default_stop_loss_pct
        return current_price <= entry_price * (1 - sl)

    def check_take_profit(
        self, entry_price: float, current_price: float, take_profit_pct: float | None = None
    ) -> bool:
        """Return True if take-profit is triggered."""
        tp = take_profit_pct or self._params.default_take_profit_pct
        return current_price >= entry_price * (1 + tp)

    def check_trailing_stop(
        self,
        entry_price: float,
        current_price: float,
        highest_price: float,
        activation_pct: float = 0.05,
        trail_pct: float = 0.03,
    ) -> bool:
        """Return True if trailing stop is triggered.

        Trailing stop activates after price rises by activation_pct
        from entry, then triggers if price drops trail_pct from peak.
        """
        gain_from_entry = (highest_price - entry_price) / entry_price
        if gain_from_entry < activation_pct:
            return False  # Not yet activated

        drop_from_peak = (highest_price - current_price) / highest_price
        return drop_from_peak >= trail_pct

    def update_daily_pnl(self, pnl: float) -> None:
        self._daily_pnl += pnl

    def reset_daily(self) -> None:
        self._daily_pnl = 0.0

    @property
    def daily_pnl(self) -> float:
        return self._daily_pnl
