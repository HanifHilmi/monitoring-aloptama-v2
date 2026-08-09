"""FastAPI application entrypoint.

Boot sequence:
1. If ``RESET_DB_ON_BOOT=true`` (dev mode): drop + recreate the public
   schema so every deploy starts clean (backfill is manual from UI).
2. Apply migrations (idempotent).
3. The ingestion worker runs in its own container; the API never starts
   the worker so the async event loop is free to serve HTTP quickly.
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.router import api_router
from app.core.config import settings
from app.db.migrate import reset_database, run_migrations
from app.db.session import AsyncSessionLocal, engine

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s - %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup/shutdown lifecycle."""
    try:
        # 0) Development reset: fresh empty DB each deploy.
        if settings.reset_db_on_boot:
            async with AsyncSessionLocal() as session:
                await reset_database(session)
                # Dispose pooled connections that had timescaledb pre-loaded —
                # migration 001 (CREATE EXTENSION timescaledb) must run on a
                # fresh connection, otherwise it fails with
                # 'extension already loaded with another version'.
                await engine.dispose()
                logger.info("DB reset on boot: schema dropped + recreated")

        # 1) Apply pending migrations (idempotent)
        if settings.enable_migrations_on_boot:
            async with AsyncSessionLocal() as session:
                applied = await run_migrations(session)
                if applied:
                    logger.info("Applied migrations: %s", ", ".join(applied))
        yield
    finally:
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