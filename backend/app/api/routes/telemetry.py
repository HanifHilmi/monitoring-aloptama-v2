"""Telemetry time-series endpoint (WIDN multi-metric, typed).

Queries the ``telemetry`` hypertable for a sensor within a time range,
optionally filtered by metric, then applies LTTB to numeric series.
String metrics (PW, SKY, D/N, LTX) are returned as text samples.
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
    "today": "today",
    "3d": timedelta(days=3),
    "week": timedelta(days=7),
    "month": timedelta(days=30),
}


@router.get("/{site_slug}/{sensor_code}")
async def get_sensor_telemetry(
    site_slug: str,
    sensor_code: str,
    range: str = Query("today", pattern="^(1h|6h|24h|7d|30d|today|3d|week|month)$"),
    start: str | None = Query(default=None, description="ISO-8601 UTC start (overrides range)"),
    end: str | None = Query(default=None, description="ISO-8601 UTC end (overrides range)"),
    metric: str | None = Query(default=None),
    downsample: int = Query(
        default=None, ge=10, le=10000,
        description="Max points after LTTB for numeric series.",
    ),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Fetch one sensor's typed time-series for a site over a range.

    When a numeric metric is selected, `series` is LTTB-downsampled. All
    rows (numeric + text) are returned in `samples` with `is_valid`.
    """
    def _parse_dt(v):
        if not v:
            return None
        if v.endswith("Z"):
            v = v[:-1] + "+00:00"
        try:
            return datetime.fromisoformat(v).astimezone(timezone.utc)
        except ValueError:
            return None

    s_dt = _parse_dt(start)
    e_dt = _parse_dt(end)
    if s_dt is None or e_dt is None:
        delta = RANGE_OPTIONS.get(range)
        if range == "today":
            s_dt = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
            e_dt = datetime.now(timezone.utc)
        elif delta is None:
            raise HTTPException(status_code=422, detail="invalid range")
        else:
            e_dt = datetime.now(timezone.utc)
            s_dt = e_dt - delta

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

    stmt = select(Telemetry).where(
        Telemetry.sensor_id == sensor.id,
        Telemetry.time >= s_dt,
        Telemetry.time <= e_dt,
    )
    if metric:
        stmt = stmt.where(Telemetry.metric == metric)
    stmt = stmt.order_by(Telemetry.time.asc())
    rows = (await db.execute(stmt)).scalars().all()

    # Determine available metrics (for chart-type-aware frontend).
    metrics = sorted({r.metric for r in rows})
    # Pick the requested metric or the first numeric one present / 'value'.
    selected = (
        metric
        or next((m for m in metrics if m in {"TEMP", "WS", "QNH", "RVR", "VIS", "SOL", "RA", "LR1", "ALS_INT"}),
                None)
        or (metrics[0] if metrics else "value")
    )

    samples = [
        {
            "time": r.time,
            "value": r.value,
            "text_value": r.text_value,
            "is_valid": r.is_valid,
            "status": r.status,
        }
        for r in rows
        if r.metric == selected
    ]

    pairs = [(s["time"], s["value"]) for s in samples if s["value"] is not None]
    threshold = downsample or settings.lttb_default_threshold
    t0 = pairs[0][0].timestamp() if pairs else 0.0
    sampled = downsample_series(pairs, threshold) if pairs else []

    series = [
        {"time": datetime.fromtimestamp(t0 + x, tz=timezone.utc), "value": y}
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
            "symbol": sensor.symbol,
            "station": sensor.station,
        },
        "range": range,
        "start_date": s_dt,
        "end_date": e_dt,
        "metric": selected,
        "metrics": metrics,
        "points": len(samples),
        "downsampled_to": len(series),
        "series": series,
        "samples": samples,  # frontend SensorCard contract
        "downsample_enabled": len(pairs) > threshold,
    }


@router.get("/{site_slug}/availability")
async def site_component_availability(
    site_slug: str,
    start: str,
    end: str,
    db: AsyncSession = Depends(get_db),
):
    """Per-day count of enabled COMPONENTS (sensors) that have telemetry
    rows in the window. Drives the DCP state graph: DCP is ONLINE on a day
    when at least one other component delivered data."""
    site = (await db.execute(select(Site).where(Site.slug == site_slug))).scalars().first()
    if site is None:
        raise HTTPException(status_code=404, detail="site not found")
    sensors = (await db.execute(
        select(Sensor).where(Sensor.site_id == site.id, Sensor.is_enabled.is_(True), Sensor.is_state.is_(False))
    )).scalars().all()
    s_dt = datetime.fromisoformat(start.replace('Z', '+00:00')).astimezone(timezone.utc)
    e_dt = datetime.fromisoformat(end.replace('Z', '+00:00')).astimezone(timezone.utc)
    rows = (await db.execute(
        text("SELECT DISTINCT date_trunc('day', time)::date AS d, sensor_id FROM telemetry WHERE sensor_id = ANY(:ids) AND time >= :s AND time < :e"),
        {"ids": [x.id for x in sensors], "s": s_dt, "e": e_dt}
    )).all()
    per_day = {}
    for d, _sid in rows:
        per_day[d.isoformat()] = per_day.get(d.isoformat(), 0) + 1
    out = []
    day = s_dt.date()
    while day <= min(e_dt.date(), datetime.now(timezone.utc).date()):
        out.append({"day": day.isoformat(), "components_with_data": per_day.get(day.isoformat(), 0), "total_components": len(sensors)})
        day += timedelta(days=1)
    return {"site": site_slug, "days": out}
