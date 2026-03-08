"""Tests for engine.recovery — CircuitBreaker, TaskRecovery, RecoveryManager."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from engine.recovery import (
    CircuitBreaker,
    CircuitOpenError,
    CircuitState,
    RecoveryManager,
    TaskRecovery,
)


# ---------------------------------------------------------------------------
# CircuitBreaker
# ---------------------------------------------------------------------------

class TestCircuitBreaker:
    """Tests for the CircuitBreaker class."""

    def test_initial_state_is_closed(self):
        cb = CircuitBreaker("test")
        assert cb.state == CircuitState.CLOSED
        assert cb.failure_count == 0

    def test_allow_request_when_closed(self):
        cb = CircuitBreaker("test")
        assert cb.allow_request() is True

    def test_failure_count_increments(self):
        cb = CircuitBreaker("test", failure_threshold=3)
        cb.record_failure()
        assert cb.failure_count == 1
        cb.record_failure()
        assert cb.failure_count == 2

    def test_closed_to_open_after_threshold(self):
        cb = CircuitBreaker("test", failure_threshold=3)
        cb.record_failure()
        cb.record_failure()
        assert cb._state == CircuitState.CLOSED
        cb.record_failure()
        assert cb._state == CircuitState.OPEN

    def test_allow_request_when_open(self):
        cb = CircuitBreaker("test", failure_threshold=2)
        cb.record_failure()
        cb.record_failure()
        assert cb.allow_request() is False

    @patch("engine.recovery.time.monotonic")
    def test_open_to_half_open_after_cooldown(self, mock_mono):
        cb = CircuitBreaker("test", failure_threshold=2, cooldown_sec=30.0)
        mock_mono.return_value = 100.0
        cb.record_failure()
        cb.record_failure()
        assert cb._state == CircuitState.OPEN

        # Before cooldown elapsed
        mock_mono.return_value = 125.0
        assert cb.state == CircuitState.OPEN

        # After cooldown elapsed
        mock_mono.return_value = 131.0
        assert cb.state == CircuitState.HALF_OPEN

    @patch("engine.recovery.time.monotonic")
    def test_allow_request_half_open_limited(self, mock_mono):
        cb = CircuitBreaker("test", failure_threshold=1, cooldown_sec=10.0, half_open_max=1)
        mock_mono.return_value = 100.0
        cb.record_failure()  # CLOSED -> OPEN

        # Transition to HALF_OPEN
        mock_mono.return_value = 111.0
        assert cb.allow_request() is True  # first call allowed

        # Simulate that one half-open call is in progress
        cb._half_open_calls = 1
        assert cb.allow_request() is False  # max reached

    @patch("engine.recovery.time.monotonic")
    def test_half_open_to_closed_on_success(self, mock_mono):
        cb = CircuitBreaker("test", failure_threshold=1, cooldown_sec=10.0)
        mock_mono.return_value = 100.0
        cb.record_failure()  # -> OPEN

        mock_mono.return_value = 111.0
        assert cb.state == CircuitState.HALF_OPEN

        cb.record_success()
        assert cb._state == CircuitState.CLOSED
        assert cb.failure_count == 0

    @patch("engine.recovery.time.monotonic")
    def test_half_open_to_open_on_failure(self, mock_mono):
        cb = CircuitBreaker("test", failure_threshold=1, cooldown_sec=10.0)
        mock_mono.return_value = 100.0
        cb.record_failure()  # -> OPEN

        mock_mono.return_value = 111.0
        assert cb.state == CircuitState.HALF_OPEN

        mock_mono.return_value = 112.0
        cb.record_failure()
        assert cb._state == CircuitState.OPEN

    def test_success_decrements_failure_count_in_closed(self):
        cb = CircuitBreaker("test", failure_threshold=5)
        cb.record_failure()
        cb.record_failure()
        assert cb.failure_count == 2
        cb.record_success()
        assert cb.failure_count == 1
        cb.record_success()
        assert cb.failure_count == 0
        # Won't go below zero
        cb.record_success()
        assert cb.failure_count == 0

    def test_manual_reset(self):
        cb = CircuitBreaker("test", failure_threshold=2)
        cb.record_failure()
        cb.record_failure()
        assert cb._state == CircuitState.OPEN

        cb.reset()
        assert cb._state == CircuitState.CLOSED
        assert cb.failure_count == 0
        assert cb._half_open_calls == 0
        assert cb.allow_request() is True

    def test_get_status(self):
        cb = CircuitBreaker("my_service", failure_threshold=5, cooldown_sec=30.0)
        cb.record_failure()
        status = cb.get_status()

        assert status["name"] == "my_service"
        assert status["state"] == "closed"
        assert status["failure_count"] == 1
        assert status["failure_threshold"] == 5
        assert status["cooldown_sec"] == 30.0

    @patch("engine.recovery.time.monotonic")
    def test_get_status_reflects_open_state(self, mock_mono):
        cb = CircuitBreaker("svc", failure_threshold=1, cooldown_sec=60.0)
        mock_mono.return_value = 0.0
        cb.record_failure()
        status = cb.get_status()
        assert status["state"] == "open"

    @pytest.mark.asyncio
    async def test_call_success(self):
        cb = CircuitBreaker("test")
        fn = AsyncMock(return_value="ok")
        result = await cb.call(fn, 1, key="val")
        assert result == "ok"
        fn.assert_awaited_once_with(1, key="val")

    @pytest.mark.asyncio
    async def test_call_failure_records_and_reraises(self):
        cb = CircuitBreaker("test", failure_threshold=5)
        fn = AsyncMock(side_effect=ValueError("boom"))

        with pytest.raises(ValueError, match="boom"):
            await cb.call(fn)

        assert cb.failure_count == 1

    @pytest.mark.asyncio
    async def test_call_raises_circuit_open_error(self):
        cb = CircuitBreaker("test", failure_threshold=1)
        cb.record_failure()  # -> OPEN

        fn = AsyncMock()
        with pytest.raises(CircuitOpenError, match="OPEN"):
            await cb.call(fn)

        fn.assert_not_awaited()

    @pytest.mark.asyncio
    @patch("engine.recovery.time.monotonic")
    async def test_call_in_half_open_increments_counter(self, mock_mono):
        cb = CircuitBreaker("test", failure_threshold=1, cooldown_sec=10.0, half_open_max=1)
        mock_mono.return_value = 100.0
        cb.record_failure()  # -> OPEN

        mock_mono.return_value = 111.0  # -> HALF_OPEN via property
        fn = AsyncMock(return_value="recovered")

        result = await cb.call(fn)
        assert result == "recovered"
        assert cb._state == CircuitState.CLOSED

    @pytest.mark.asyncio
    @patch("engine.recovery.time.monotonic")
    async def test_call_in_half_open_failure_reopens(self, mock_mono):
        cb = CircuitBreaker("test", failure_threshold=1, cooldown_sec=10.0, half_open_max=1)
        mock_mono.return_value = 100.0
        cb.record_failure()  # -> OPEN

        mock_mono.return_value = 111.0  # -> HALF_OPEN
        fn = AsyncMock(side_effect=RuntimeError("still bad"))

        with pytest.raises(RuntimeError, match="still bad"):
            await cb.call(fn)

        assert cb._state == CircuitState.OPEN


# ---------------------------------------------------------------------------
# CircuitOpenError
# ---------------------------------------------------------------------------

class TestCircuitOpenError:
    def test_is_exception(self):
        err = CircuitOpenError("circuit is open")
        assert isinstance(err, Exception)
        assert str(err) == "circuit is open"

    def test_raised_and_caught(self):
        with pytest.raises(CircuitOpenError):
            raise CircuitOpenError("blocked")


# ---------------------------------------------------------------------------
# TaskRecovery
# ---------------------------------------------------------------------------

class TestTaskRecovery:

    @pytest.mark.asyncio
    async def test_successful_execution(self):
        fn = AsyncMock()
        tr = TaskRecovery("task1", fn, max_retries=2)

        result = await tr.execute()
        assert result is True
        fn.assert_awaited_once()
        assert tr._total_successes == 1
        assert tr._consecutive_failures == 0

    @pytest.mark.asyncio
    @patch("engine.recovery.asyncio.sleep", new_callable=AsyncMock)
    async def test_retry_then_succeed(self, mock_sleep):
        fn = AsyncMock(side_effect=[RuntimeError("fail1"), "ok"])
        tr = TaskRecovery("task1", fn, max_retries=2, backoff_base=5.0)

        result = await tr.execute()
        assert result is True
        assert fn.await_count == 2
        assert tr._total_successes == 1
        assert tr._total_failures == 1
        # Check backoff sleep called with correct delay: 5.0 * 2^0 = 5.0
        mock_sleep.assert_awaited_once_with(5.0)

    @pytest.mark.asyncio
    @patch("engine.recovery.asyncio.sleep", new_callable=AsyncMock)
    async def test_all_retries_exhausted(self, mock_sleep):
        fn = AsyncMock(side_effect=RuntimeError("always fails"))
        tr = TaskRecovery("task1", fn, max_retries=2, backoff_base=2.0)

        result = await tr.execute()
        assert result is False
        # 1 initial + 2 retries = 3 calls total
        assert fn.await_count == 3
        assert tr._total_failures == 3
        assert tr._consecutive_failures == 1
        # Circuit should have recorded a failure
        assert tr.circuit.failure_count == 1

    @pytest.mark.asyncio
    @patch("engine.recovery.asyncio.sleep", new_callable=AsyncMock)
    async def test_backoff_delay_capped_at_max(self, mock_sleep):
        fn = AsyncMock(side_effect=RuntimeError("fail"))
        tr = TaskRecovery("task1", fn, max_retries=3, backoff_base=10.0, backoff_max=25.0)

        await tr.execute()
        # attempt 0: delay = 10 * 2^0 = 10
        # attempt 1: delay = 10 * 2^1 = 20
        # attempt 2: delay = min(10 * 2^2, 25) = 25  (capped)
        delays = [call.args[0] for call in mock_sleep.await_args_list]
        assert delays == [10.0, 20.0, 25.0]

    @pytest.mark.asyncio
    @patch("engine.recovery.asyncio.sleep", new_callable=AsyncMock)
    async def test_on_failure_callback_called(self, mock_sleep):
        fn = AsyncMock(side_effect=RuntimeError("kaboom"))
        on_fail = AsyncMock()
        tr = TaskRecovery("task1", fn, max_retries=0, on_failure=on_fail)

        result = await tr.execute()
        assert result is False
        on_fail.assert_awaited_once_with("task1", fn.side_effect)

    @pytest.mark.asyncio
    @patch("engine.recovery.asyncio.sleep", new_callable=AsyncMock)
    async def test_on_failure_callback_error_handled(self, mock_sleep):
        """Failure callback exception does not propagate."""
        fn = AsyncMock(side_effect=RuntimeError("original"))
        on_fail = AsyncMock(side_effect=TypeError("callback broke"))
        tr = TaskRecovery("task1", fn, max_retries=0, on_failure=on_fail)

        result = await tr.execute()
        assert result is False  # still returns False, no exception escapes

    @pytest.mark.asyncio
    async def test_skipped_when_circuit_open(self):
        fn = AsyncMock()
        circuit = CircuitBreaker("task1", failure_threshold=1)
        circuit.record_failure()  # -> OPEN
        tr = TaskRecovery("task1", fn, circuit=circuit)

        result = await tr.execute()
        assert result is False
        fn.assert_not_awaited()

    @pytest.mark.asyncio
    @patch("engine.recovery.asyncio.sleep", new_callable=AsyncMock)
    async def test_circuit_opens_after_repeated_exhaustions(self, mock_sleep):
        """Exhaust retries enough times to trip the circuit breaker."""
        fn = AsyncMock(side_effect=RuntimeError("fail"))
        circuit = CircuitBreaker("task1", failure_threshold=2)
        tr = TaskRecovery("task1", fn, max_retries=0, circuit=circuit)

        await tr.execute()
        assert circuit._state == CircuitState.CLOSED  # 1 failure, threshold=2

        await tr.execute()
        assert circuit._state == CircuitState.OPEN  # 2 failures -> OPEN

        # Next execution is skipped
        result = await tr.execute()
        assert result is False
        assert fn.await_count == 2  # no new call

    @pytest.mark.asyncio
    @patch("engine.recovery.time.monotonic")
    @patch("engine.recovery.asyncio.sleep", new_callable=AsyncMock)
    async def test_execute_in_half_open_success_recovers(self, mock_sleep, mock_mono):
        mock_mono.return_value = 100.0
        fn = AsyncMock(side_effect=[RuntimeError("fail"), RuntimeError("fail"), "ok"])
        circuit = CircuitBreaker("task1", failure_threshold=2, cooldown_sec=10.0)
        tr = TaskRecovery("task1", fn, max_retries=0, circuit=circuit)

        # Exhaust retries twice -> OPEN
        await tr.execute()
        await tr.execute()
        assert circuit._state == CircuitState.OPEN

        # Advance past cooldown -> HALF_OPEN
        mock_mono.return_value = 111.0
        fn.side_effect = None
        fn.return_value = None
        result = await tr.execute()
        assert result is True
        assert circuit._state == CircuitState.CLOSED

    def test_get_status(self):
        fn = AsyncMock()
        tr = TaskRecovery("task1", fn, max_retries=2)
        tr._total_successes = 5
        tr._total_failures = 2
        tr._consecutive_failures = 1

        status = tr.get_status()
        assert status["name"] == "task1"
        assert status["total_successes"] == 5
        assert status["total_failures"] == 2
        assert status["consecutive_failures"] == 1
        assert "circuit" in status
        assert status["circuit"]["name"] == "task1"

    @pytest.mark.asyncio
    async def test_default_circuit_created(self):
        fn = AsyncMock()
        tr = TaskRecovery("task1", fn)
        assert tr.circuit is not None
        assert tr.circuit.name == "task1"


# ---------------------------------------------------------------------------
# RecoveryManager
# ---------------------------------------------------------------------------

class TestRecoveryManager:

    def test_wrap_task_creates_recovery(self):
        mgr = RecoveryManager()
        fn = AsyncMock()
        recovery = mgr.wrap_task("my_task", fn, max_retries=3, failure_threshold=4)

        assert isinstance(recovery, TaskRecovery)
        assert recovery.name == "my_task"
        assert recovery.max_retries == 3
        assert recovery.circuit.failure_threshold == 4
        assert "my_task" in mgr._recoveries

    def test_wrap_task_with_custom_params(self):
        mgr = RecoveryManager()
        fn = AsyncMock()
        recovery = mgr.wrap_task(
            "task2", fn,
            max_retries=5,
            backoff_base=10.0,
            failure_threshold=3,
            cooldown_sec=120.0,
        )
        assert recovery.max_retries == 5
        assert recovery.backoff_base == 10.0
        assert recovery.circuit.cooldown_sec == 120.0

    @pytest.mark.asyncio
    @patch("engine.recovery.asyncio.sleep", new_callable=AsyncMock)
    async def test_handle_failure_sends_notification(self, mock_sleep):
        notif = AsyncMock()
        notif.notify_system_error = AsyncMock()
        mgr = RecoveryManager(notification=notif)

        fn = AsyncMock(side_effect=RuntimeError("api down"))
        recovery = mgr.wrap_task("pos_check", fn, max_retries=0)

        await recovery.execute()

        notif.notify_system_error.assert_awaited_once()
        call_kwargs = notif.notify_system_error.call_args[1]
        assert call_kwargs["component"] == "pos_check"
        assert "api down" in call_kwargs["error"]
        assert "Circuit breaker state" in call_kwargs["details"]

    @pytest.mark.asyncio
    @patch("engine.recovery.asyncio.sleep", new_callable=AsyncMock)
    async def test_handle_failure_no_notification(self, mock_sleep):
        """When no notification service is configured, failure still works."""
        mgr = RecoveryManager(notification=None)
        fn = AsyncMock(side_effect=RuntimeError("fail"))
        recovery = mgr.wrap_task("task1", fn, max_retries=0)

        result = await recovery.execute()
        assert result is False  # no crash

    def test_reset_circuit_existing(self):
        mgr = RecoveryManager()
        fn = AsyncMock()
        recovery = mgr.wrap_task("task1", fn, failure_threshold=1)
        recovery.circuit.record_failure()  # -> OPEN

        assert recovery.circuit._state == CircuitState.OPEN
        result = mgr.reset_circuit("task1")
        assert result is True
        assert recovery.circuit._state == CircuitState.CLOSED

    def test_reset_circuit_nonexistent(self):
        mgr = RecoveryManager()
        result = mgr.reset_circuit("no_such_task")
        assert result is False

    def test_reset_all(self):
        mgr = RecoveryManager()
        fn = AsyncMock()

        r1 = mgr.wrap_task("t1", fn, failure_threshold=1)
        r2 = mgr.wrap_task("t2", fn, failure_threshold=1)
        r1.circuit.record_failure()  # -> OPEN
        r2.circuit.record_failure()  # -> OPEN

        mgr.reset_all()
        assert r1.circuit._state == CircuitState.CLOSED
        assert r2.circuit._state == CircuitState.CLOSED
        assert r1.circuit.failure_count == 0
        assert r2.circuit.failure_count == 0

    def test_get_status_empty(self):
        mgr = RecoveryManager()
        assert mgr.get_status() == {}

    def test_get_status_multiple_tasks(self):
        mgr = RecoveryManager()
        fn = AsyncMock()
        mgr.wrap_task("task_a", fn)
        mgr.wrap_task("task_b", fn)

        status = mgr.get_status()
        assert "task_a" in status
        assert "task_b" in status
        assert status["task_a"]["name"] == "task_a"
        assert status["task_b"]["name"] == "task_b"
        assert "circuit" in status["task_a"]

    @pytest.mark.asyncio
    @patch("engine.recovery.asyncio.sleep", new_callable=AsyncMock)
    async def test_wrap_task_on_failure_wired_to_handle_failure(self, mock_sleep):
        """Verify that wrap_task wires on_failure to _handle_failure."""
        mgr = RecoveryManager()
        fn = AsyncMock(side_effect=RuntimeError("err"))
        recovery = mgr.wrap_task("task1", fn, max_retries=0)

        assert recovery._on_failure == mgr._handle_failure
        assert recovery._on_recovery == mgr._handle_recovery

    @pytest.mark.asyncio
    @patch("engine.recovery.time.monotonic")
    @patch("engine.recovery.asyncio.sleep", new_callable=AsyncMock)
    async def test_recovery_notification_sent(self, mock_sleep, mock_mono):
        """Verify notification sent when circuit recovers from OPEN."""
        notif = AsyncMock()
        notif.notify_system_error = AsyncMock()
        notif.notify_system_event = AsyncMock()
        mgr = RecoveryManager(notification=notif)

        call_count = 0

        async def failing_then_ok():
            nonlocal call_count
            call_count += 1
            if call_count <= 1:
                raise RuntimeError("fail")

        mock_mono.return_value = 100.0
        recovery = mgr.wrap_task(
            "test_task", failing_then_ok,
            max_retries=0, failure_threshold=1, cooldown_sec=10.0,
        )

        # Fail -> OPEN
        await recovery.execute()
        assert recovery.circuit._state == CircuitState.OPEN

        # Advance past cooldown -> HALF_OPEN, next call succeeds
        mock_mono.return_value = 111.0
        result = await recovery.execute()
        assert result is True
        assert recovery.circuit._state == CircuitState.CLOSED

        # Recovery notification sent
        notif.notify_system_event.assert_awaited_once_with(
            "circuit_recovered",
            "Task 'test_task' has recovered and is running normally again.",
        )

    @pytest.mark.asyncio
    @patch("engine.recovery.asyncio.sleep", new_callable=AsyncMock)
    async def test_end_to_end_recovery_flow(self, mock_sleep):
        """Full flow: failures trip circuit, cooldown, half-open recovery."""
        notif = AsyncMock()
        notif.notify_system_error = AsyncMock()
        mgr = RecoveryManager(notification=notif)

        call_count = 0

        async def flaky_fn():
            nonlocal call_count
            call_count += 1
            if call_count <= 4:
                raise RuntimeError(f"fail #{call_count}")
            # succeeds after that

        recovery = mgr.wrap_task(
            "flaky", flaky_fn,
            max_retries=1,
            failure_threshold=2,
            cooldown_sec=30.0,
        )

        # Round 1: 2 attempts (initial + 1 retry) both fail -> circuit records 1 failure
        result = await recovery.execute()
        assert result is False
        assert recovery.circuit.failure_count == 1

        # Round 2: 2 more attempts fail -> circuit records 2nd failure -> OPEN
        result = await recovery.execute()
        assert result is False
        assert recovery.circuit._state == CircuitState.OPEN

        # Round 3: circuit is OPEN -> skipped
        result = await recovery.execute()
        assert result is False

        # Simulate cooldown elapsed
        with patch("engine.recovery.time.monotonic", return_value=time_after_cooldown()):
            # call_count is now 4; next call (5th) will succeed
            result = await recovery.execute()
            assert result is True
            assert recovery.circuit._state == CircuitState.CLOSED


def time_after_cooldown():
    """Return a time far enough in the future to pass any cooldown."""
    import time
    return time.monotonic() + 99999
