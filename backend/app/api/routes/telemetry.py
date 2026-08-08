"""Telemetry time-series endpoint with LTTB downsampling.

Queries the ``telemetry`` hypertable for a sensor within a time range,
then applies LTTB in-process to keep chart payloads small and rendering
non-blocking (>1000 points get downsampled to the configured threshold).
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.config import settings
from app.db.session import get_db
from app.models import Site, Telemetry
from app.utils.lttb import downsample_series

router = APIRouter(prefix="/telemetry", tags=["telemetry"])

RANGE_OPTIONS = {
    "1h": timedelta(hours=1),
    "6h": timedelta(hours=6),
    "24h": timedelta(hours=24),
    "7d": timedelta(days=7),
    "30d": timedelta(days=30),
}


@router.get("/{site_slug}/{sensor_code}")
async def get_sensor_telemetry(
    site_slug: str,
    sensor_code: str,
    range: str = Query("24h", pattern="^(1h|6h|24h|7d|30d)$"),
    downsample: int = Query(
        default=None,
        ge=10,
        le=10000,
        description="Max points after LTTB. Defaults to configured threshold.",
    ),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Fetch one sensor's time-series for a site over a time range."""
    range_delta = RANGE_OPTIONS.get(range)
    if range_delta is None:
        raise HTTPException(status_code=422, detail="invalid range")

    site = (
        await db.execute(
            select(Site).where(Site.slug == site_slug).options(selectinload(Site.sensors))
        )
    ).scalars().first()
    if site is None:
        raise HTTPException(status_code=404, detail="site not found")

    sensor = next((s for s in site.sensors if s.code == sensor_code), None)
    if sensor is None:
        raise HTTPException(status_code=404, detail="sensor not found")
    if not sensor.is_enabled:
        raise HTTPException(status_code=404, detail="sensor disabled")

    since = datetime.now(timezone.utc) - range_delta
    rows = (
        await db.execute(
            select(Telemetry)
            .where(
                Telemetry.sensor_id == sensor.id,
                Telemetry.time >= since,
            )
            .order_by(Telemetry.time.asc())
        )
    ).scalars().all()

    pairs = [(r.time, r.value) for r in rows if r.value is not None]
    threshold = downsample or settings.lttb_default_threshold
    # Output x is epoch offset from first sample; convert back to ISO timestamps
    t0 = pairs[0][0].timestamp() if pairs else 0.0
    sampled = downsample_series(pairs, threshold)

    # Status timeline: compressed (time, status) pairs for OLA state grids
    status_pairs = [
        {"time": r.time, "status": r.status}
        for r in rows
        if r.time and r.status
    ]

    series = [
        {
            "time": datetime.fromtimestamp(t0 + x, tz=timezone.utc),
            "value": y,
        }
        for x, y in sampled
    ]

    return {
        "site": {"slug": site.slug, "code": site.code, "name": site.name},
        "sensor": {
            "id": sensor.id,
            "code": sensor.code,
            "name": sensor.name,
            "category": sensor.category,
            "unit": sensor.unit,
        },
        "range": range,
        "points": len(rows),
        "downsampled_to": len(sampled),
        "series": series,
        # `samples` is the contract the frontend SensorCard consumes:
        # [{time, value}, ...]
        "samples": series,
        "status": status_pairs,
        "downsample_enabled": len(rows) > threshold,
    }
