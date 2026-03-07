"""Internal event bus for decoupled component communication."""

import asyncio
import logging
from collections import deque
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import Callable, Awaitable

logger = logging.getLogger(__name__)

EventHandler = Callable[["Event"], Awaitable[None]]


class EventType(str, Enum):
    # Trade lifecycle
    TRADE_EXECUTED = "trade_executed"
    TRADE_FAILED = "trade_failed"

    # Signal
    SIGNAL_GENERATED = "signal_generated"

    # Position lifecycle
    POSITION_OPENED = "position_opened"
    POSITION_CLOSED = "position_closed"

    # Stop / take-profit
    STOP_LOSS_TRIGGERED = "stop_loss_triggered"
    TAKE_PROFIT_TRIGGERED = "take_profit_triggered"
    TRAILING_STOP_TRIGGERED = "trailing_stop_triggered"

    # Risk
    RISK_LIMIT_REACHED = "risk_limit_reached"

    # Market
    MARKET_PHASE_CHANGED = "market_phase_changed"

    # System
    SYSTEM_ERROR = "system_error"
    SYSTEM_RECOVERED = "system_recovered"

    # Scanner
    SCANNER_COMPLETED = "scanner_completed"


@dataclass
class Event:
    event_type: EventType
    data: dict
    source: str
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))


class EventBus:
    """Publish-subscribe event bus for async handlers.

    All handlers must be async callables that accept an ``Event``.
    Handler errors are logged but never propagate to the publisher or
    other handlers.
    """

    _MAX_HISTORY = 200

    def __init__(self) -> None:
        self._subscribers: dict[EventType, list[EventHandler]] = {}
        self._history: deque[Event] = deque(maxlen=self._MAX_HISTORY)

    # ------------------------------------------------------------------
    # Subscription management
    # ------------------------------------------------------------------

    def subscribe(self, event_type: EventType, handler: EventHandler) -> None:
        """Register an async handler for *event_type*."""
        self._subscribers.setdefault(event_type, []).append(handler)

    def unsubscribe(self, event_type: EventType, handler: EventHandler) -> None:
        """Remove a previously registered handler.

        Silently does nothing if the handler was not subscribed.
        """
        handlers = self._subscribers.get(event_type, [])
        try:
            handlers.remove(handler)
        except ValueError:
            pass

    def clear(self) -> None:
        """Remove all subscriptions."""
        self._subscribers.clear()

    # ------------------------------------------------------------------
    # Publishing
    # ------------------------------------------------------------------

    def publish(self, event: Event) -> None:
        """Fire-and-forget: schedule handlers as tasks, don't block the publisher."""
        self._history.append(event)
        handlers = self._subscribers.get(event.event_type, [])
        for handler in handlers:
            asyncio.ensure_future(self._safe_call(handler, event))

    async def publish_sync(self, event: Event) -> None:
        """Dispatch *event* and **await** all handlers before returning."""
        self._history.append(event)
        handlers = self._subscribers.get(event.event_type, [])
        await asyncio.gather(
            *(self._safe_call(handler, event) for handler in handlers),
            return_exceptions=True,
        )

    # ------------------------------------------------------------------
    # History
    # ------------------------------------------------------------------

    def get_history(
        self,
        event_type: EventType | None = None,
        limit: int = 50,
    ) -> list[Event]:
        """Return the most recent events, optionally filtered by type."""
        if event_type is None:
            items = list(self._history)
        else:
            items = [e for e in self._history if e.event_type == event_type]
        return items[-limit:]

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    @staticmethod
    async def _safe_call(handler: EventHandler, event: Event) -> None:
        try:
            await handler(event)
        except Exception:
            logger.exception(
                "EventBus handler %s failed for %s",
                getattr(handler, "__name__", handler),
                event.event_type,
            )


# Global singleton -- import and use directly.
event_bus = EventBus()
