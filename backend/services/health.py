"""Health check service for monitoring system components."""

import logging
import time

logger = logging.getLogger(__name__)


class HealthMonitor:
    """Monitor health of system components."""

    def __init__(self):
        self._start_time = time.time()
        self._checks: dict[str, dict] = {}

    def register_check(self, name: str, check_fn) -> None:
        """Register a health check function."""
        self._checks[name] = {"fn": check_fn, "last_status": "unknown"}

    async def check_all(self) -> dict:
        """Run all health checks and return status."""
        results = {}
        all_healthy = True

        for name, check in self._checks.items():
            try:
                status = await check["fn"]()
                results[name] = {"status": "ok", **status} if isinstance(status, dict) else {"status": "ok"}
                check["last_status"] = "ok"
            except Exception as e:
                results[name] = {"status": "error", "error": str(e)}
                check["last_status"] = "error"
                all_healthy = False
                logger.warning("Health check failed: %s - %s", name, e)

        uptime = time.time() - self._start_time
        return {
            "status": "healthy" if all_healthy else "degraded",
            "uptime_seconds": int(uptime),
            "checks": results,
        }

    @property
    def uptime(self) -> float:
        return time.time() - self._start_time
