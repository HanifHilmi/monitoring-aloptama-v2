"""Availability endpoints (SLA / OLA + components).

Semantics (per product definition):
- CDP Uptime   = uptime % of each CDP node from availability / connectivity.
- SLA          = (CDP1 uptime + CDP2 uptime) / 2.
- DataAvail    = per-site availability of valid sensor data
                 (7 components per site; RWY04 ALS counts into RVR_ALS).
- OLA          = (RWY04 DA + RWYMID DA + RWY22 DA) / 3.

Drives the dashboard: row1 SLA/OLA %, row2 history graph, row3 CDP uptime
& downtime, row4 sites.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.models import CdpConnectivity, CdpNode, DailySlaOla, Site, Telemetry

router = APIRouter(prefix="/sla-ola", tags=["sla-ola"])

RANGES = {
    "today": "day",
    "week": "week",
    "month": "month",
    "year": "year",
}


def _range_start(range_key: str, now: datetime) -> datetime:
    if range_key == "today":
        return now.replace(hour=0, minute=0, second=0, microsecond=0)
    if range_key == "week":
        return now - timedelta(days=7)
    if range_key == "month":
        return now - timedelta(days=30)
    return now - timedelta(days=365)


async def _cdp_uptime(db: AsyncSession, node: CdpNode, start: datetime, end: datetime) -> dict:
    total = (end - start).total_seconds()
    rows = (
        await db.execute(
            select(CdpConnectivity)
            .where(
                CdpConnectivity.cdp_id == node.id,
                CdpConnectivity.time >= start,
                CdpConnectivity.time <= end,
            )
        )
    ).scalars().all()
    up = sum(1 for r in rows if r.reachable)
    uptime_pct = (up / len(rows) * 100.0) if rows else 0.0
    downtime = int(total - (uptime_pct * total / 100.0))
    return {
        "cdp_id": node.id,
        "name": node.name,
        "ip_address": str(node.ip_address),
        "uptime_pct": round(uptime_pct, 4),
        "downtime_seconds": downtime,
        "samples": len(rows),
    }


async def _site_data_availability(db: AsyncSession, site: Site, start: datetime, end: datetime) -> dict:
    """Per-site Data Availability = valid component-minutes / expected."""
    sensors = [s for s in site.sensors if s.is_enabled]
    # RWY04: ALS merges into RVR_ALS -> exactly 7 components.
    components: dict[str, list[int]] = {}
    for s in sensors:
        comp = s.component or s.code
        components.setdefault(comp, []).append(s.id)

    rows = (
        await db.execute(
            select(Telemetry.sensor_id, Telemetry.is_valid)
            .where(
                Telemetry.sensor_id.in_([s.id for s in sensors]),
                Telemetry.time >= start,
                Telemetry.time <= end,
            )
        )
    ).all()

    valid_by_sensor: dict[int, int] = {}
    total_by_sensor: dict[int, int] = {}
    for sensor_id, is_valid in rows:
        total_by_sensor[sensor_id] = total_by_sensor.get(sensor_id, 0) + 1
        if is_valid:
            valid_by_sensor[sensor_id] = valid_by_sensor.get(sensor_id, 0) + 1

    comp_rows = []
    for comp, ids in sorted(components.items()):
        total = sum(total_by_sensor.get(i, 0) for i in ids)
        valid = sum(valid_by_sensor.get(i, 0) for i in ids)
        pct = (valid / total * 100.0) if total else 0.0
        comp_rows.append({"component": comp, "uptime_pct": round(pct, 4), "samples": total})

    # Data Availability = avg of the 7 components (same as valid/total overall).
    overall_total = sum(r["samples"] for r in comp_rows)
    overall_valid = sum((r["uptime_pct"] / 100.0) * r["samples"] for r in comp_rows)
    data_avail = (overall_valid / overall_total * 100.0) if overall_total else 0.0

    return {
        "site_id": site.id,
        "slug": site.slug,
        "code": site.code,
        "name": site.name,
        "data_availability_pct": round(data_avail, 4),
        "components": comp_rows,
    }


@router.get("/summary")
async def get_summary(
    range: str = Query("month", pattern="^(today|week|month|year)$"),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """SLA, OLA, per-CDP uptime, and per-site data availability."""
    now = datetime.now(timezone.utc)
    start = _range_start(range, now)

    nodes = (await db.execute(select(CdpNode))).scalars().all()
    sites = (await db.execute(select(Site))).scalars().all()

    cdps = [await _cdp_uptime(db, n, start, now) for n in nodes]
    site_das = [await _site_data_availability(db, s, start, now) for s in sites]

    # SLA = (CDP1 + CDP2) / 2 ; OLA = (3 sites) / 3
    sla_pct = round(sum(c["uptime_pct"] for c in cdps) / len(cdps), 4) if cdps else 0.0
    ola_pct = round(sum(d["data_availability_pct"] for d in site_das) / len(site_das), 4) if site_das else 0.0

    return {
        "generated_at": now,
        "range": range,
        "start_date": start,
        "end_date": now,
        "sla_pct": sla_pct,
        "ola_pct": ola_pct,
        "cdp_uptime": cdps,
        "sites": site_das,
    }


@router.get("/history")
async def get_history(
    bucket: str = Query("daily", pattern="^(daily|weekly|monthly|yearly)$"),
    span: str = Query("month", pattern="^(month|year|5year)$"),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """SLA/OLA history buckets for the main dashboard graph."""
    now = datetime.now(timezone.utc)
    if span == "year":
        start = now - timedelta(days=365)
    elif span == "5year":
        start = now - timedelta(days=365 * 5)
    else:
        start = now - timedelta(days=30)

    nodes = (await db.execute(select(CdpNode))).scalars().all()
    sites = (await db.execute(select(Site))).scalars().all()

    # Pull all data in one pass, fold into buckets by day.
    cdp_rows = (
        await db.execute(
            select(CdpConnectivity.time, CdpConnectivity.cdp_id, CdpConnectivity.reachable)
            .where(CdpConnectivity.time >= start)
        )
    ).all()
    tel_rows = (
        await db.execute(
            select(Telemetry.time, Telemetry.sensor_id, Telemetry.is_valid)
            .where(Telemetry.time >= start)
        )
    ).all()

    buckets: dict[str, dict] = {}
    for t, cdp_id, reachable in cdp_rows:
        day = t.date().isoformat()
        b = buckets.setdefault(day, {"day": day, "cdp_up": 0, "cdp_total": 0, "sensor_valid": 0, "sensor_total": 0})
        b["cdp_total"] += 1
        if reachable:
            b["cdp_up"] += 1
    for t, sensor_id, is_valid in tel_rows:
        day = t.date().isoformat()
        b = buckets.setdefault(day, {"day": day, "cdp_up": 0, "cdp_total": 0, "sensor_valid": 0, "sensor_total": 0})
        b["sensor_total"] += 1
        if is_valid:
            b["sensor_valid"] += 1

    rows = []
    for day, b in sorted(buckets.items()):
        sla = (b["cdp_up"] / b["cdp_total"] * 100.0) if b["cdp_total"] else 0.0
        ola = (b["sensor_valid"] / b["sensor_total"] * 100.0) if b["sensor_total"] else 0.0
        rows.append({"day": day, "sla_pct": round(sla, 4), "ola_pct": round(ola, 4)})

    return {"span": span, "bucket": bucket, "start_date": start, "end_date": now, "rows": rows}