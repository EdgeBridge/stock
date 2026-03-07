"""Signal Combiner - weighted voting across multiple strategies.

Combines signals from multiple strategies using market-state-adaptive
weight profiles defined in config/strategies.yaml.
"""

import logging

from strategies.base import Signal
from core.enums import SignalType

logger = logging.getLogger(__name__)


class SignalCombiner:
    """Combine multiple strategy signals using weighted voting."""

    def combine(
        self,
        signals: list[Signal],
        weights: dict[str, float],
        min_confidence: float = 0.50,
    ) -> Signal:
        """Combine signals using weighted voting.

        Args:
            signals: List of signals from individual strategies
            weights: Strategy name -> weight mapping from profile
            min_confidence: Minimum combined confidence to act

        Returns:
            Combined signal
        """
        if not signals:
            return Signal(
                signal_type=SignalType.HOLD,
                confidence=0.0,
                strategy_name="combiner",
                reason="No signals",
            )

        buy_score = 0.0
        sell_score = 0.0
        total_weight = 0.0
        reasons = []
        all_indicators = {}

        for signal in signals:
            w = weights.get(signal.strategy_name, 0.0)
            if w <= 0:
                continue

            total_weight += w
            weighted_conf = signal.confidence * w

            if signal.signal_type == SignalType.BUY:
                buy_score += weighted_conf
                reasons.append(f"+{signal.strategy_name}({signal.confidence:.0%})")
            elif signal.signal_type == SignalType.SELL:
                sell_score += weighted_conf
                reasons.append(f"-{signal.strategy_name}({signal.confidence:.0%})")

            # Collect indicators
            for k, v in signal.indicators.items():
                all_indicators[f"{signal.strategy_name}.{k}"] = v

        if total_weight == 0:
            return Signal(
                signal_type=SignalType.HOLD,
                confidence=0.0,
                strategy_name="combiner",
                reason="No weighted strategies",
            )

        # Normalize
        buy_norm = buy_score / total_weight
        sell_norm = sell_score / total_weight

        if buy_norm > sell_norm and buy_norm >= min_confidence:
            return Signal(
                signal_type=SignalType.BUY,
                confidence=buy_norm,
                strategy_name="combiner",
                reason=f"BUY consensus: {', '.join(reasons)}",
                indicators=all_indicators,
            )

        if sell_norm > buy_norm and sell_norm >= min_confidence:
            return Signal(
                signal_type=SignalType.SELL,
                confidence=sell_norm,
                strategy_name="combiner",
                reason=f"SELL consensus: {', '.join(reasons)}",
                indicators=all_indicators,
            )

        return Signal(
            signal_type=SignalType.HOLD,
            confidence=max(buy_norm, sell_norm),
            strategy_name="combiner",
            reason=f"Below threshold ({max(buy_norm, sell_norm):.0%} < {min_confidence:.0%})",
            indicators=all_indicators,
        )
