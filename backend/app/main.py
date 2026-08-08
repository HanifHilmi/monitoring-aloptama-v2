"""FastAPI application entrypoint.

Boot sequence:
1. Ensure migrations applied (docker-compose ``db-migrate`` handles this).
2. If telemetry tables are empty, run the historical auto-backfill
   (defaults to 2026-01-01 → now) so dashboards render immediately.
3. Start the background ingestion worker (CDP active-passive probing,
   telemetry ingestion, rollup rebuilds).
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.router import api_router
from app.core.config import settings
from app.db.migrate import run_migrations
from app.db.session import AsyncSessionLocal
from app.ingestion.worker import build_worker
from app.services.backfill import run_initial_backfill_if_needed

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s - %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup/shutdown lifecycle."""
    worker = None
    try:
        # 1) Apply pending migrations (idempotent)
        if settings.enable_migrations_on_boot:
            async with AsyncSessionLocal() as session:
                applied = await run_migrations(session)
                if applied:
                    logger.info("Applied migrations: %s", ", ".join(applied))

        # 2) Start the ingestion worker.
        #    Historical backfill runs in the dedicated worker container before
        #    ingestion starts — NOT inline here — so the API stays responsive
        #    during the (potentially long) first-boot backfill.
        async with AsyncSessionLocal() as session:
            worker = await build_worker(session)
        await worker.start()
        logger.info("Monitoring Aloptama V2 API started")
        yield
    finally:
        if worker is not None:
            await worker.stop()
        logger.info("Shutdown complete")


app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    description="AWOS Category III monitoring — CDP SLA, sensor OLA, and "
    "1-minute telemetry across Runway 04, Runway 22, and Runway Middle.",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router)


@app.get("/health", tags=["health"])
async def health_check() -> dict:
    """Liveness probe for Coolify / Docker healthchecks."""
    return {"status": "ok", "app": settings.app_name, "version": settings.app_version}