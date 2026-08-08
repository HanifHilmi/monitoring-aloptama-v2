"""Aggregate all API route modules into a single versioned router."""

from fastapi import APIRouter

from app.api.routes import sla_ola, status, system, telemetry
from app.core.config import settings

api_router = APIRouter(prefix=settings.api_prefix)

# Each route module already declares its own prefix (e.g. /status), so
# do NOT re-prefix here — doing so produced /api/v1/status/status/... 404s.
api_router.include_router(status.router, tags=["status"])
api_router.include_router(telemetry.router, tags=["telemetry"])
api_router.include_router(sla_ola.router, tags=["sla-ola"])
api_router.include_router(system.router, tags=["system"])
