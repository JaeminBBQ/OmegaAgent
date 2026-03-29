"""APScheduler setup for recurring agent jobs.

Integrates with FastAPI lifecycle — scheduler starts/stops with the app.
Agents register their schedules here.
"""

import logging
from typing import Any, Callable, Coroutine

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

logger = logging.getLogger(__name__)

scheduler = AsyncIOScheduler(timezone="America/Los_Angeles")


def add_interval_job(
    func: Callable[..., Coroutine[Any, Any, Any]],
    *,
    job_id: str,
    hours: int = 0,
    minutes: int = 0,
    seconds: int = 0,
    **kwargs: Any,
) -> None:
    """Schedule an async function to run at a fixed interval."""
    scheduler.add_job(
        func,
        IntervalTrigger(hours=hours, minutes=minutes, seconds=seconds),
        id=job_id,
        replace_existing=True,
        **kwargs,
    )
    logger.info(
        "Scheduled interval job %s: every %dh %dm %ds",
        job_id, hours, minutes, seconds,
    )


def add_cron_job(
    func: Callable[..., Coroutine[Any, Any, Any]],
    *,
    job_id: str,
    hour: int | str = "*",
    minute: int | str = "0",
    day_of_week: str = "*",
    **kwargs: Any,
) -> None:
    """Schedule an async function using cron-style timing."""
    scheduler.add_job(
        func,
        CronTrigger(hour=hour, minute=minute, day_of_week=day_of_week),
        id=job_id,
        replace_existing=True,
        **kwargs,
    )
    logger.info(
        "Scheduled cron job %s: hour=%s minute=%s dow=%s",
        job_id, hour, minute, day_of_week,
    )


def start() -> None:
    """Start the scheduler if not already running."""
    if not scheduler.running:
        scheduler.start()
        logger.info("Scheduler started with %d jobs", len(scheduler.get_jobs()))


def shutdown() -> None:
    """Gracefully shut down the scheduler."""
    if scheduler.running:
        scheduler.shutdown(wait=False)
        logger.info("Scheduler shut down")


def list_jobs() -> list[dict[str, Any]]:
    """Return a summary of all scheduled jobs."""
    return [
        {
            "id": job.id,
            "name": job.name,
            "next_run": str(job.next_run_time) if job.next_run_time else None,
            "trigger": str(job.trigger),
        }
        for job in scheduler.get_jobs()
    ]
