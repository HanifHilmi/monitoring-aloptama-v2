"""System health / connectivity status for the dashboard.

Reports whether the API (this process), the database, and the ingestion
worker are reachable/healthy so operators can see infra status without
SSHing into the containers.
"""

from __future__ import annotations

import os
from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.session import get_db
from app.models import CdpNode, Telemetry

router = APIRouter(prefix="/system", tags=["system"])


@router.get("/health")
async def system_health(
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Return health status of API, database, and ingestion worker."""
    generated = datetime.now(timezone.utc)

    # ---- API ----
    api_ok = True

    # ---- Database ----
    db_ok = False
    db_error = None
    try:
        await db.execute(text("SELECT 1"))
        db_ok = True
    except Exception as exc:  # noqa: BLE001
        db_error = str(exc)

    # ---- Worker (local process or separate container) ----
    # The worker container runs `python -m app.ingestion.worker` and writes
    # heartbeat cadence via cdp_connectivity rows. We infer worker liveness
    # from the presence of recent connectivity samples AND whether a
    # separate worker process is running in this container (for the API
    # container it is not; for the worker container it is).
    worker_running = "worker" in (os.getenv("WORKER_MODE", "") or process_name())

    telemetry_count = 0
    try:
        telemetry_count = (
            await db.execute(
                text("SELECT COUNT(*) FROM telemetry")
            )
        ).scalar_one()
    except Exception:
        telemetry_count = 0

    recent_connectivity = False
    try:
        recent_connectivity = (
            await db.execute(
                text(
                    "SELECT COUNT(*) FROM cdp_connectivity "
                    "WHERE time > NOW() - INTERVAL '5 minutes'"
                )
            )
        ).scalar_one() > 0
    except Exception:
        recent_connectivity = False

    return {
        "generated_at": generated,
        "status": "ok" if api_ok and db_ok else "degraded",
        "components": {
            "api": {"status": "ok" if api_ok else "down"},
            "database": {
                "status": "ok" if db_ok else "down",
                "error": db_error,
            },
            "worker": {
                "status": "ok" if worker_running or recent_connectivity else "unknown",
                "running_in_container": worker_running,
                "recent_connectivity": recent_connectivity,
            },
            "data": {
                "telemetry_rows": telemetry_count,
            },
        },
        "config": {
            "cdp1": {
                "ip": settings.cdp1_ip,
                "mount_path": settings.cdp1_mount_path,
            },
            "cdp2": {
                "ip": settings.cdp2_ip,
                "mount_path": settings.cdp2_mount_path,
            },
            "backfill_enabled": settings.enable_backfill_on_boot,
            "backfill_start": settings.backfill_start,
        },
    }


def process_name() -> str:
    """Best-effort name of the current process (``ps`` may be absent)."""
    try:
        with open("/proc/self/comm", "r", encoding="utf-8") as fh:
            return fh.read().strip()
    except OSError:
        return ""