"""FastAPI application entrypoint.

Boot sequence:
1. Apply pending migrations (idempotent, owned by this process).
2. Start serving HTTP immediately.

Heavy work (historical backfill, CDP probing, telemetry ingestion, rollup
rebuilds) runs exclusively in the dedicated ``worker`` container.  We
deliberately do NOT start the ingestion worker in this process: the worker
performs synchronous NFS/CDP file I/O (``Path.exists``, ``glob``,
``read_text``) which would block the asyncio event loop and make every HTTP
request (including ``/health``) hang — surfacing as 504 Gateway Timeouts at
the proxy.
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

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s - %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup/shutdown lifecycle.

    Only migrations run here (brief, idempotent, advisory-lock guarded).
    No ingestion/backfill/rollup work is started inline so the API is ready
    to answer health checks as soon as uvicorn binds the socket.
    """
    try:
        # Apply pending migrations (idempotent). The worker container runs
        # with ENABLE_MIGRATIONS_ON_BOOT=false to avoid lock races on boot.
        if settings.enable_migrations_on_boot:
            async with AsyncSessionLocal() as session:
                applied = await run_migrations(session)
                if applied:
                    logger.info("Applied migrations: %s", ", ".join(applied))

        logger.info("Monitoring Aloptama V2 API started")
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