"""Pre-aggregated SLA/OLA summary endpoints.

Reads exclusively from the ``daily_sla_ola`` hypertable so 30+ day range
queries execute as a single hypertable scan — well under 200ms.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.models import (
    CdpNode,
    DailySlaOla,
    DowntimeEvent,
    Sensor,
    Site,
)

router = APIRouter(prefix="/sla-ola", tags=["sla-ola"])

RANGE_DAYS = {"7d": 7, "30d": 30, "90d": 90, "365d": 365}


@router.get("/summary")
async def get_sla_ola_summary(
    range: str = Query("30d", pattern="^(7d|30d|90d|365d)$"),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """System-wide SLA (per CDP) and OLA (per sensor) for the period.

    Uptime % = ((Total Seconds - Downtime Seconds) / Total Seconds) * 100
    computed from per-day rollup rows clipped to the requested window.
    """
    days = RANGE_DAYS.get(range, 30)
    end_date = datetime.now(timezone.utc).date()
    start_date = end_date - timedelta(days=days - 1)

    cdp_rows = (
        await db.execute(
            select(DailySlaOla)
            .where(
                DailySlaOla.scope_type == "sla",
                DailySlaOla.weo_time >= start_date,
                DailySlaOla.weo_time <= end_date,
            )
            .order_by(DailySlaOla.cdp_id, DailySlaOla.weo_time)
        )
    ).scalars().all()

    ola_rows = (
        await db.execute(
            select(DailySlaOla)
            .where(
                DailySlaOla.scope_type == "ola",
                DailySlaOla.weo_time >= start_date,
                DailySlaOla.weo_time <= end_date,
            )
            .order_by(DailySlaOla.sensor_id, DailySlaOla.weo_time)
        )
    ).scalars().all()

    nodes = {n.id: n for n in (await db.execute(select(CdpNode))).scalars().all()}
    sensors = {
        s.id: s
        for s in (await db.execute(select(Sensor))).scalars().all()
    }
    sites = {s.id: s for s in (await db.execute(select(Site))).scalars().all()}

    # Aggregate SLA per CDP
    sla_by_cdp: dict[int, dict] = {}
    total_seconds = days * 86400
    for r in cdp_rows:
        if r.cdp_id is None:
            continue
        agg = sla_by_cdp.setdefault(
            r.cdp_id,
            {"cdp_id": r.cdp_id, "downtime_seconds": 0, "days": 0},
        )
        agg["downtime_seconds"] += r.downtime_seconds
        agg["days"] += 1

    sla_summary = []
    for cdp_id, agg in sorted(sla_by_cdp.items()):
        node = nodes.get(cdp_id)
        downtime = agg["downtime_seconds"]
        uptime = max(total_seconds - downtime, 0)
        sla_summary.append(
            {
                "cdp_id": cdp_id,
                "name": node.name if node else f"CDP-{cdp_id}",
                "ip_address": str(node.ip_address) if node else None,
                "role": node.role if node else None,
                "period_days": days,
                "total_seconds": total_seconds,
                "uptime_seconds": uptime,
                "downtime_seconds": downtime,
                "uptime_pct": round(
                    (uptime / total_seconds) * 100.0, 4
                ),
                "days_with_data": agg["days"],
            }
        )

    # Aggregate OLA per sensor
    ola_by_sensor: dict[int, dict] = {}
    for r in ola_rows:
        if r.sensor_id is None:
            continue
        agg = ola_by_sensor.setdefault(
            r.sensor_id,
            {"sensor_id": r.sensor_id, "downtime_seconds": 0, "days": 0},
        )
        agg["downtime_seconds"] += r.downtime_seconds
        agg["days"] += 1

    sites_payload: dict[str, dict] = {}
    for sensor_id, agg in ola_by_sensor.items():
        sensor = sensors.get(sensor_id)
        if sensor is None:
            continue
        site = sites.get(sensor.site_id)
        if site is None:
            continue
        downtime = agg["downtime_seconds"]
        uptime = max(total_seconds - downtime, 0)
        entry = {
            "sensor_id": sensor_id,
            "code": sensor.code,
            "name": sensor.name,
            "category": sensor.category,
            "unit": sensor.unit,
            "period_days": days,
            "total_seconds": total_seconds,
            "uptime_seconds": uptime,
            "downtime_seconds": downtime,
            "uptime_pct": round((uptime / total_seconds) * 100.0, 4),
            "days_with_data": agg["days"],
        }
        sites_payload.setdefault(
            site.slug,
            {"site": {"slug": site.slug, "code": site.code, "name": site.name},
             "sensors": []},
        )["sensors"].append(entry)

    return {
        "generated_at": datetime.now(timezone.utc),
        "range": range,
        "start_date": start_date,
        "end_date": end_date,
        "sla": sla_summary,
        "ola": [v for k, v in sorted(sites_payload.items())],
    }


@router.get("/daily")
async def get_daily_rollup(
    scope: str = Query("sla", pattern="^(sla|ola)$"),
    entity_type: str = Query("cdp", pattern="^(cdp|sensor)$"),
    entity_id: int = Query(..., gt=0),
    days: int = Query(30, ge=1, le=365),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Daily uptime/downtime series for charts (from pre-aggregated rollup)."""
    end_date = datetime.now(timezone.utc).date()
    start_date = end_date - timedelta(days=days - 1)

    stmt = select(DailySlaOla).where(
        DailySlaOla.scope_type == scope,
        DailySlaOla.entity_type == entity_type,
        DailySlaOla.weo_time >= start_date,
        DailySlaOla.weo_time <= end_date,
    )
    if scope == "sla":
        stmt = stmt.where(DailySlaOla.cdp_id == entity_id)
    else:
        stmt = stmt.where(DailySlaOla.sensor_id == entity_id)
    stmt = stmt.order_by(DailySlaOla.weo_time)

    rows = (await db.execute(stmt)).scalars().all()
    return {
        "scope": scope,
        "entity_type": entity_type,
        "entity_id": entity_id,
        "start_date": start_date,
        "end_date": end_date,
        "daily": [
            {
                "date": r.weo_time,
                "total_seconds": r.total_seconds,
                "uptime_seconds": r.uptime_seconds,
                "downtime_seconds": r.downtime_seconds,
                "uptime_pct": r.uptime_pct,
                "open_events": r.open_events,
                "closed_events": r.closed_events,
            }
            for r in rows
        ],
    }


@router.get("/events")
async def get_downtime_events(
    scope: str = Query("ola", pattern="^(sla|ola)$"),
    site_slug: str | None = Query(default=None),
    sensor_code: str | None = Query(default=None),
    limit: int = Query(100, ge=1, le=1000),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Recent downtime events (open + closed) for state-machine records."""
    stmt = select(DowntimeEvent).where(DowntimeEvent.scope_type == scope)

    if site_slug is not None:
        site = (
            await db.execute(select(Site).where(Site.slug == site_slug))
        ).scalars().first()
        if site is None:
            raise HTTPException(status_code=404, detail="site not found")
        stmt = stmt.where(DowntimeEvent.site_id == site.id)

    if sensor_code is not None and scope == "ola":
        sensor = (
            await db.execute(select(Sensor).where(Sensor.code == sensor_code))
        ).scalars().first()
        if sensor is None:
            raise HTTPException(status_code=404, detail="sensor not found")
        stmt = stmt.where(DowntimeEvent.sensor_id == sensor.id)

    stmt = stmt.order_by(DowntimeEvent.start_time.desc()).limit(limit)
    rows = (await db.execute(stmt)).scalars().all()

    sites = {s.id: s for s in (await db.execute(select(Site))).scalars().all()}
    sensors = {
        s.id: s
        for s in (await db.execute(select(Sensor))).scalars().all()
    }
    nodes = {n.id: n for n in (await db.execute(select(CdpNode))).scalars().all()}

    events = []
    for ev in rows:
        duration = None
        if ev.start_time and ev.end_time:
            duration = int((ev.end_time - ev.start_time).total_seconds())
        label = None
        if ev.cdp_id is not None and ev.cdp_id in nodes:
            label = nodes[ev.cdp_id].name
        elif ev.sensor_id is not None and ev.sensor_id in sensors:
            label = sensors[ev.sensor_id].name
        events.append(
            {
                "id": ev.id,
                "scope": ev.scope_type,
                "entity_type": ev.entity_type,
                "cdp_id": ev.cdp_id,
                "sensor_id": ev.sensor_id,
                "site_id": ev.site_id,
                "site_slug": sites.get(ev.site_id).slug if ev.site_id in sites else None,
                "label": label,
                "start_time": ev.start_time,
                "end_time": ev.end_time,
                "duration_seconds": duration,
                "is_open": ev.end_time is None,
                "reason_code": ev.reason_code,
            }
        )

    return {
        "scope": scope,
        "count": len(events),
        "events": events,
    }