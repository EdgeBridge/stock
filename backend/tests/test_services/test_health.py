"""Tests for HealthMonitor with notification and system metrics."""

import pytest

from services.health import HealthMonitor


class FakeNotification:
    """Capture notification calls."""

    def __init__(self):
        self.errors: list[tuple] = []
        self.events: list[tuple] = []

    async def notify_system_error(self, component, error, details=""):
        self.errors.append((component, error, details))

    async def notify_system_event(self, event_type, message):
        self.events.append((event_type, message))


@pytest.fixture
def monitor():
    return HealthMonitor()


@pytest.fixture
def notif():
    return FakeNotification()


@pytest.mark.asyncio
async def test_healthy_check(monitor):
    async def ok_check():
        return {"mode": "paper"}

    monitor.register_check("adapter", ok_check)
    result = await monitor.check_all()

    assert result["status"] == "healthy"
    assert result["checks"]["adapter"]["status"] == "ok"
    assert result["checks"]["adapter"]["mode"] == "paper"


@pytest.mark.asyncio
async def test_degraded_check(monitor):
    async def fail_check():
        raise RuntimeError("connection refused")

    monitor.register_check("db", fail_check)
    result = await monitor.check_all()

    assert result["status"] == "degraded"
    assert result["checks"]["db"]["status"] == "error"
    assert "connection refused" in result["checks"]["db"]["error"]


@pytest.mark.asyncio
async def test_notify_on_failure(monitor, notif):
    """Should send Discord alert when a check transitions to error."""
    call_count = 0

    async def flaky_check():
        nonlocal call_count
        call_count += 1
        if call_count >= 2:
            raise RuntimeError("db down")

    monitor.set_notification(notif)
    monitor.register_check("db", flaky_check)

    # First call: ok
    await monitor.check_all()
    assert len(notif.errors) == 0

    # Second call: fails → should notify
    await monitor.check_all()
    assert len(notif.errors) == 1
    assert "health_monitor" in notif.errors[0][0]
    assert "1 check(s) failed" in notif.errors[0][1]


@pytest.mark.asyncio
async def test_notify_on_recovery(monitor, notif):
    """Should send recovery notification when check goes error→ok."""
    call_count = 0

    async def flaky_check():
        nonlocal call_count
        call_count += 1
        if call_count == 2:
            raise RuntimeError("temporary")

    monitor.set_notification(notif)
    monitor.register_check("api", flaky_check)

    await monitor.check_all()  # ok
    await monitor.check_all()  # error
    await monitor.check_all()  # ok again → recovery

    assert len(notif.events) == 1
    assert notif.events[0][0] == "health_recovered"
    assert "api" in notif.events[0][1]


@pytest.mark.asyncio
async def test_no_duplicate_failure_notify(monitor, notif):
    """Should NOT re-notify if check stays in error state."""
    async def bad_check():
        raise RuntimeError("always bad")

    monitor.set_notification(notif)
    monitor.register_check("db", bad_check)

    await monitor.check_all()  # first fail → notify
    await monitor.check_all()  # still fail → no new notify
    await monitor.check_all()  # still fail → no new notify

    assert len(notif.errors) == 1


@pytest.mark.asyncio
async def test_no_notify_without_notification_service(monitor):
    """Should work fine without notification service set."""
    async def fail_check():
        raise RuntimeError("oops")

    monitor.register_check("x", fail_check)
    result = await monitor.check_all()  # no crash
    assert result["status"] == "degraded"


def test_system_metrics(monitor):
    metrics = monitor.get_system_metrics()
    assert "cpu_percent" in metrics
    assert "memory_used_gb" in metrics
    assert "memory_total_gb" in metrics
    assert "disk_percent" in metrics
    assert metrics["memory_total_gb"] > 0


@pytest.mark.asyncio
async def test_get_status_report(monitor):
    async def ok_check():
        pass

    monitor.register_check("test", ok_check)
    report = await monitor.get_status_report()

    assert report["status"] == "healthy"
    assert "system" in report
    assert "cpu_percent" in report["system"]
