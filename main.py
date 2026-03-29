"""OmegaAgent — Personal AI Platform.

FastAPI entry point. Start with:
    uvicorn main:app --host 0.0.0.0 --port 8080 --reload
"""

import logging
import time
from datetime import datetime

from fastapi import FastAPI

from api.models import ServiceHealth
from api.routes.agents import router as agents_router
from api.routes.status import register_health_check, router as status_router
from core.config import LOG_LEVEL
from core.db import DBClient
from core.llm import LLMClient
from core.scraper import ScraperClient
from core.search import SearchClient
from scheduler import jobs as scheduler_jobs

logging.basicConfig(
    level=getattr(logging, LOG_LEVEL, logging.INFO),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="OmegaAgent",
    description="Self-hosted modular AI platform",
    version="0.1.0",
)

# --- Core service instances (shared across agents) --------------------------
db = DBClient()
llm = LLMClient()
search = SearchClient()
scraper = ScraperClient()


# --- Health check factories --------------------------------------------------
async def _check_db() -> ServiceHealth:
    start = time.time()
    ok = await db.health_check()
    return ServiceHealth(
        name="supabase",
        status="ok" if ok else "down",
        latency_ms=round((time.time() - start) * 1000, 1),
        last_checked=datetime.utcnow(),
    )


async def _check_llm() -> ServiceHealth:
    start = time.time()
    ok = await llm.health_check()
    return ServiceHealth(
        name="anthropic",
        status="ok" if ok else "down",
        latency_ms=round((time.time() - start) * 1000, 1),
        last_checked=datetime.utcnow(),
    )


async def _check_search() -> ServiceHealth:
    start = time.time()
    ok = await search.health_check()
    return ServiceHealth(
        name="serper",
        status="ok" if ok else "down",
        latency_ms=round((time.time() - start) * 1000, 1),
        last_checked=datetime.utcnow(),
    )


async def _check_scraper() -> ServiceHealth:
    start = time.time()
    ok = await scraper.health_check()
    return ServiceHealth(
        name="playwright",
        status="ok" if ok else "down",
        latency_ms=round((time.time() - start) * 1000, 1),
        last_checked=datetime.utcnow(),
    )



# --- Register health checks -------------------------------------------------
register_health_check("supabase", _check_db)
register_health_check("anthropic", _check_llm)
register_health_check("serper", _check_search)
register_health_check("playwright", _check_scraper)

# --- Routes ------------------------------------------------------------------
app.include_router(status_router)
app.include_router(agents_router)


# --- Lifecycle ---------------------------------------------------------------
@app.on_event("startup")
async def on_startup() -> None:
    # Register scheduled agent jobs
    from agents.weather import WeatherAgent

    weather_agent = WeatherAgent(llm=llm, db=db, search=search)
    scheduler_jobs.add_interval_job(
        weather_agent.run, job_id="weather_reno", hours=2
    )

    scheduler_jobs.start()
    logger.info("OmegaAgent v0.1.0 started — scheduler running")


@app.on_event("shutdown")
async def on_shutdown() -> None:
    scheduler_jobs.shutdown()
    logger.info("OmegaAgent shutting down")
