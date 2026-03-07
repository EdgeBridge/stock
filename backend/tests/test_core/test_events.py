"""Tests for the internal event bus."""

import asyncio

import pytest

from core.events import Event, EventBus, EventType, event_bus


def _make_event(
    event_type: EventType = EventType.TRADE_EXECUTED,
    source: str = "test",
    data: dict | None = None,
) -> Event:
    return Event(event_type=event_type, data=data or {}, source=source)


class TestSubscribeUnsubscribe:
    def test_subscribe_registers_handler(self):
        bus = EventBus()

        async def handler(e: Event) -> None: ...

        bus.subscribe(EventType.TRADE_EXECUTED, handler)
        assert handler in bus._subscribers[EventType.TRADE_EXECUTED]

    def test_unsubscribe_removes_handler(self):
        bus = EventBus()

        async def handler(e: Event) -> None: ...

        bus.subscribe(EventType.TRADE_EXECUTED, handler)
        bus.unsubscribe(EventType.TRADE_EXECUTED, handler)
        assert handler not in bus._subscribers.get(EventType.TRADE_EXECUTED, [])

    def test_unsubscribe_nonexistent_handler_is_silent(self):
        bus = EventBus()

        async def handler(e: Event) -> None: ...

        # Should not raise
        bus.unsubscribe(EventType.TRADE_EXECUTED, handler)

    def test_clear_removes_all_subscriptions(self):
        bus = EventBus()

        async def h1(e: Event) -> None: ...
        async def h2(e: Event) -> None: ...

        bus.subscribe(EventType.TRADE_EXECUTED, h1)
        bus.subscribe(EventType.SIGNAL_GENERATED, h2)
        bus.clear()
        assert bus._subscribers == {}


class TestPublish:
    async def test_publish_fires_handler(self):
        bus = EventBus()
        received: list[Event] = []

        async def handler(e: Event) -> None:
            received.append(e)

        bus.subscribe(EventType.TRADE_EXECUTED, handler)
        event = _make_event()
        bus.publish(event)

        # Give fire-and-forget tasks time to run
        await asyncio.sleep(0.05)
        assert len(received) == 1
        assert received[0] is event

    async def test_publish_multiple_handlers(self):
        bus = EventBus()
        calls: list[str] = []

        async def h1(e: Event) -> None:
            calls.append("h1")

        async def h2(e: Event) -> None:
            calls.append("h2")

        bus.subscribe(EventType.TRADE_EXECUTED, h1)
        bus.subscribe(EventType.TRADE_EXECUTED, h2)
        bus.publish(_make_event())

        await asyncio.sleep(0.05)
        assert sorted(calls) == ["h1", "h2"]

    async def test_publish_does_not_block_publisher(self):
        bus = EventBus()

        async def slow_handler(e: Event) -> None:
            await asyncio.sleep(0.5)

        bus.subscribe(EventType.TRADE_EXECUTED, slow_handler)

        # publish() should return immediately
        bus.publish(_make_event())
        # If we reach here without waiting 0.5s, the publisher was not blocked.

    async def test_publish_no_subscribers_is_safe(self):
        bus = EventBus()
        bus.publish(_make_event())  # No error


class TestPublishSync:
    async def test_publish_sync_awaits_all_handlers(self):
        bus = EventBus()
        results: list[int] = []

        async def h1(e: Event) -> None:
            await asyncio.sleep(0.02)
            results.append(1)

        async def h2(e: Event) -> None:
            await asyncio.sleep(0.02)
            results.append(2)

        bus.subscribe(EventType.TRADE_EXECUTED, h1)
        bus.subscribe(EventType.TRADE_EXECUTED, h2)

        await bus.publish_sync(_make_event())

        # Both handlers must have completed by the time publish_sync returns.
        assert sorted(results) == [1, 2]

    async def test_publish_sync_no_subscribers_is_safe(self):
        bus = EventBus()
        await bus.publish_sync(_make_event())  # No error


class TestHandlerErrors:
    async def test_handler_error_does_not_crash_other_handlers(self):
        bus = EventBus()
        results: list[str] = []

        async def bad_handler(e: Event) -> None:
            raise RuntimeError("boom")

        async def good_handler(e: Event) -> None:
            results.append("ok")

        bus.subscribe(EventType.TRADE_EXECUTED, bad_handler)
        bus.subscribe(EventType.TRADE_EXECUTED, good_handler)

        await bus.publish_sync(_make_event())
        assert results == ["ok"]

    async def test_handler_error_is_logged(self, caplog):
        bus = EventBus()

        async def bad_handler(e: Event) -> None:
            raise ValueError("test error")

        bus.subscribe(EventType.TRADE_EXECUTED, bad_handler)

        with caplog.at_level("ERROR", logger="core.events"):
            await bus.publish_sync(_make_event())

        assert "bad_handler" in caplog.text
        assert "TRADE_EXECUTED" in caplog.text

    async def test_publish_fire_and_forget_error_does_not_crash(self):
        bus = EventBus()

        async def bad_handler(e: Event) -> None:
            raise RuntimeError("boom")

        bus.subscribe(EventType.TRADE_EXECUTED, bad_handler)
        bus.publish(_make_event())
        await asyncio.sleep(0.05)
        # If we reach here, the bus survived the handler error.


class TestEventHistory:
    def test_history_records_events(self):
        bus = EventBus()
        e1 = _make_event(EventType.TRADE_EXECUTED)
        e2 = _make_event(EventType.SIGNAL_GENERATED)

        bus.publish(e1)
        bus.publish(e2)

        history = bus.get_history()
        assert len(history) == 2
        assert history[0] is e1
        assert history[1] is e2

    def test_history_filter_by_type(self):
        bus = EventBus()
        bus.publish(_make_event(EventType.TRADE_EXECUTED))
        bus.publish(_make_event(EventType.SIGNAL_GENERATED))
        bus.publish(_make_event(EventType.TRADE_EXECUTED))

        filtered = bus.get_history(event_type=EventType.TRADE_EXECUTED)
        assert len(filtered) == 2
        assert all(e.event_type == EventType.TRADE_EXECUTED for e in filtered)

    def test_history_respects_limit(self):
        bus = EventBus()
        for _ in range(10):
            bus.publish(_make_event())

        assert len(bus.get_history(limit=3)) == 3

    def test_history_max_size_is_200(self):
        bus = EventBus()
        for i in range(250):
            bus.publish(_make_event(data={"i": i}))

        history = bus.get_history(limit=300)
        assert len(history) == 200
        # Oldest events should have been evicted
        assert history[0].data["i"] == 50

    async def test_publish_sync_also_records_history(self):
        bus = EventBus()
        await bus.publish_sync(_make_event())
        assert len(bus.get_history()) == 1


class TestGlobalSingleton:
    def test_module_level_event_bus_exists(self):
        assert isinstance(event_bus, EventBus)
