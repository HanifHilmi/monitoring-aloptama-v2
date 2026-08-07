"""Aggregate all API route modules into a single versioned router."""

from fastapi import APIRouter

from app.api.routes import sla_ola, status, telemetry
from app.core.config import settings

api_router = APIRouter(prefix=settings.api_prefix)

api_router.include_router(status.router, prefix="/status", tags=["status"])
api_router.include_router(telemetry.router, prefix="/telemetry", tags=["telemetry"])
api_router.include_router(sla_ola.router, prefix="/sla-ola", tags=["sla-ola"])