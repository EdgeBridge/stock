"""Health check service for monitoring system components."""

import logging
import time
from typing import Any

import psutil

logger = logging.getLogger(__name__)


class HealthMonitor:
    """Monitor health of system components with state-change notifications."""

    def __init__(self):
        self._start_time = time.time()
        self._checks: dict[str, dict] = {}
        self._notification = None
        self._prev_status: str = "healthy"
        self._consecutive_failures: dict[str, int] = {}

    def set_notification(self, notification) -> None:
        """Set notification service for alerts."""
        self._notification = notification

    def register_check(self, name: str, check_fn) -> None:
        """Register a health check function."""
        self._checks[name] = {"fn": check_fn, "last_status": "unknown"}
        self._consecutive_failures[name] = 0

    async def check_all(self) -> dict:
        """Run all health checks, notify on state change."""
        results = {}
        all_healthy = True
        newly_failed = []
        recovered = []

        for name, check in self._checks.items():
            prev = check["last_status"]
            try:
                status = await check["fn"]()
                results[name] = {"status": "ok", **status} if isinstance(status, dict) else {"status": "ok"}
                check["last_status"] = "ok"
                if prev == "error":
                    recovered.append(name)
                self._consecutive_failures[name] = 0
            except Exception as e:
                results[name] = {"status": "error", "error": str(e)}
                check["last_status"] = "error"
                all_healthy = False
                self._consecutive_failures[name] = self._consecutive_failures.get(name, 0) + 1
                if prev != "error":
                    newly_failed.append((name, str(e)))
                logger.warning("Health check failed: %s - %s", name, e)

        current_status = "healthy" if all_healthy else "degraded"

        # Notify on state changes
        if self._notification:
            if newly_failed:
                failed_msg = "\n".join(f"- **{n}**: {e}" for n, e in newly_failed)
                await self._notification.notify_system_error(
                    "health_monitor",
                    f"{len(newly_failed)} check(s) failed",
                    f"Failed components:\n{failed_msg}",
                )
            if recovered:
                await self._notification.notify_system_event(
                    "health_recovered",
                    f"Recovered: {', '.join(recovered)}",
                )

        self._prev_status = current_status

        uptime = time.time() - self._start_time
        return {
            "status": current_status,
            "uptime_seconds": int(uptime),
            "checks": results,
        }

    def get_system_metrics(self) -> dict[str, Any]:
        """Collect system-level metrics (CPU, memory, disk)."""
        cpu_pct = psutil.cpu_percent(interval=0.5)
        mem = psutil.virtual_memory()
        disk = psutil.disk_usage("/")
        uptime = time.time() - self._start_time

        return {
            "uptime_seconds": int(uptime),
            "cpu_percent": cpu_pct,
            "memory_used_gb": round(mem.used / (1024**3), 1),
            "memory_total_gb": round(mem.total / (1024**3), 1),
            "memory_percent": mem.percent,
            "disk_used_gb": round(disk.used / (1024**3), 1),
            "disk_total_gb": round(disk.total / (1024**3), 1),
            "disk_percent": disk.percent,
        }

    async def get_status_report(self) -> dict[str, Any]:
        """Full status report: health checks + system metrics."""
        health = await self.check_all()
        metrics = self.get_system_metrics()
        return {**health, "system": metrics}

    @property
    def uptime(self) -> float:
        return time.time() - self._start_time
