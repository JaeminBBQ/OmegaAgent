"""Status endpoint — used by RPi clients for failover health checks."""

import logging
import platform
import time

from fastapi import APIRouter

from api.models import ServiceHealth, StatusResponse

logger = logging.getLogger(__name__)

router = APIRouter()

_start_time: float = time.time()

# Registry of service health check functions.
# Each entry: (name, async callable returning ServiceHealth)
# Agents and core services register themselves here at startup.
_health_checks: list[tuple[str, object]] = []


def register_health_check(name: str, check_fn) -> None:
    """Register an async health check callable for a named service."""
    _health_checks.append((name, check_fn))


@router.get("/status", response_model=StatusResponse)
async def get_status() -> StatusResponse:
    """
    Return overall platform health and per-service status.

    RPi clients hit this with a 2-second timeout to decide whether
    to use this host or fall back to the secondary.
    """
    services: list[ServiceHealth] = []

    for name, check_fn in _health_checks:
        try:
            health = await check_fn()
            services.append(health)
        except Exception as exc:
            logger.warning("Health check failed for %s: %s", name, exc)
            services.append(ServiceHealth(name=name, status="down", detail=str(exc)))

    # Overall status: "ok" if all services ok, "degraded" if any degraded, "down" if any down
    statuses = {s.status for s in services}
    if "down" in statuses:
        overall = "degraded"
    elif "degraded" in statuses:
        overall = "degraded"
    else:
        overall = "ok"

    return StatusResponse(
        status=overall,
        version="0.1.0",
        uptime_seconds=round(time.time() - _start_time, 2),
        hostname=platform.node(),
        services=services,
    )
