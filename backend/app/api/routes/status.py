"""Real-time system status endpoint.

Returns CDP node reachability, per-site sensor health, and recent
connectivity samples so dashboards render immediately on load.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.config import settings
from app.db.session import get_db
from app.models import CdpConnectivity, CdpNode, Site, Telemetry

router = APIRouter(prefix="/status", tags=["status"])


@router.get("/overview")
async def get_status_overview(
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Summarize CDP reachability, site health, and sensor freshness."""
    nodes = (await db.execute(select(CdpNode))).scalars().all()
    sites = (
        await db.execute(select(Site).options(selectinload(Site.sensors)))
    ).scalars().all()

    stale_cutoff = datetime.now(timezone.utc) - timedelta(
        minutes=settings.telemetry_stale_after_minutes
    )

    node_status = []
    for n in nodes:
        # Latest connectivity sample per node
        latest_q = (
            select(CdpConnectivity)
            .where(CdpConnectivity.cdp_id == n.id)
            .order_by(CdpConnectivity.time.desc())
            .limit(1)
        )
        latest = (await db.execute(latest_q)).scalars().first()
        node_status.append(
            {
                "id": n.id,
                "name": n.name,
                "ip_address": str(n.ip_address),
                "role": n.role,
                "status": (
                    "online" if latest and latest.reachable else "offline"
                ),
                "last_check": latest.time if latest else None,
                "last_rtt_ms": latest.rtt_ms if latest else None,
                "error_message": latest.error_message if latest else None,
            }
        )

    site_status = []
    for site in sites:
        sensors = []
        active_sensors = [s for s in site.sensors if s.is_enabled]
        for s in active_sensors:
            latest_ts = (
                await db.execute(
                    select(func.max(Telemetry.time)).where(
                        Telemetry.sensor_id == s.id
                    )
                )
            ).scalar_one()
            fresh = latest_ts is not None and latest_ts >= stale_cutoff
            sensors.append(
                {
                    "id": s.id,
                    "code": s.code,
                    "name": s.name,
                    "category": s.category,
                    "unit": s.unit,
                    "status": "ok" if fresh else "stale",
                    "last_sample_time": latest_ts,
                }
            )
        site_status.append(
            {
                "id": site.id,
                "code": site.code,
                "name": site.name,
                "slug": site.slug,
                "total_sensors": len(active_sensors),
                "online_sensors": sum(
                    1 for s in sensors if s["status"] == "ok"
                ),
                "sensors": sensors,
            }
        )

    return {
        "generated_at": datetime.now(timezone.utc),
        "cdp_nodes": node_status,
        "sites": site_status,
    }


@router.get("/cdp/{cdp_id}/connectivity")
async def get_cdp_connectivity(
    cdp_id: int,
    hours: int = 24,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Recent CDP connectivity samples for SLA timeline charts."""
    if hours <= 0 or hours > 24 * 30:
        raise HTTPException(status_code=422, detail="hours must be in (0, 720]")

    node = await db.get(CdpNode, cdp_id)
    if node is None:
        raise HTTPException(status_code=404, detail="CDP node not found")

    since = datetime.now(timezone.utc) - timedelta(hours=hours)
    rows = (
        await db.execute(
            select(CdpConnectivity)
            .where(
                CdpConnectivity.cdp_id == cdp_id,
                CdpConnectivity.time >= since,
            )
            .order_by(CdpConnectivity.time.asc())
        )
    ).scalars().all()

    return {
        "cdp_id": cdp_id,
        "name": node.name,
        "samples": [
            {
                "time": r.time,
                "reachable": r.reachable,
                "rtt_ms": r.rtt_ms,
                "error_message": r.error_message,
            }
            for r in rows
        ],
    }