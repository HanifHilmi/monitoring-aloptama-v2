"""Availability endpoints (SLA / OLA + components).

Semantics (per product definition):
- CDP Uptime   = uptime % of each CDP node from availability / connectivity.
- SLA          = (CDP1 uptime + CDP2 uptime) / 2.
- DataAvail    = per-site availability of valid sensor data
                 (7 components per site; RWY04 ALS counts into RVR_ALS).
- OLA          = (RWY04 DA + RWYMID DA + RWY22 DA) / 3.

All queries use SQL GROUP BY so requests stay well under the proxy/cloudflare
timeout even over 365-day ranges.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.models import CdpConnectivity, CdpNode, Site, Telemetry

router = APIRouter(prefix="/sla-ola", tags=["sla-ola"])


def _range_start(range_key: str, now: datetime) -> datetime:
    if range_key == "today":
        return now.replace(hour=0, minute=0, second=0, microsecond=0)
    if range_key == "week":
        return now - timedelta(days=7)
    if range_key == "month":
        return now - timedelta(days=30)
    return now - timedelta(days=365)


async def _cdp_uptime(db: AsyncSession, node: CdpNode, start: datetime, end: datetime) -> dict:
    """Single-row SQL aggregation per CDP node (fast over any range)."""
    row = (
        await db.execute(
            select(
                func.count(CdpConnectivity.time).label("total"),
                func.count(CdpConnectivity.time)
                .filter(CdpConnectivity.reachable.is_(True))
                .label("up"),
            ).where(
                CdpConnectivity.cdp_id == node.id,
                CdpConnectivity.time >= start,
                CdpConnectivity.time <= end,
            )
        )
    ).one()
    total = row.total or 0
    up = row.up or 0
    total_secs = max((end - start).total_seconds(), 1)
    uptime_pct = (up / total * 100.0) if total else 0.0
    downtime = int(total_secs - (uptime_pct / 100.0 * total_secs))
    return {
        "cdp_id": node.id,
        "name": node.name,
        "ip_address": str(node.ip_address),
        "uptime_pct": round(uptime_pct, 4),
        "downtime_seconds": downtime,
        "samples": total,
    }


async def _site_data_availability(db: AsyncSession, site: Site, start: datetime, end: datetime) -> dict:
    """Per-site Data Availability via one GROUP BY per site."""
    sensors = [s for s in site.sensors if s.is_enabled]
    if not sensors:
        return {"site_id": site.id, "slug": site.slug, "code": site.code, "name": site.name,
                "data_availability_pct": 0.0, "components": []}

    # RWY04: ALS merges into RVR_ALS -> exactly 7 components.
    components: dict[str, list[int]] = {}
    for s in sensors:
        comp = s.component or s.code
        components.setdefault(comp, []).append(s.id)

    rows = (
        await db.execute(
            select(
                Telemetry.sensor_id,
                func.count(Telemetry.time).label("total"),
                func.count(Telemetry.time).filter(Telemetry.is_valid.is_(True)).label("valid"),
            )
            .where(
                Telemetry.sensor_id.in_([s.id for s in sensors]),
                Telemetry.time >= start,
                Telemetry.time <= end,
            )
            .group_by(Telemetry.sensor_id)
        )
    ).all()
    stats = {r.sensor_id: (r.total or 0, r.valid or 0) for r in rows}

    comp_rows = []
    overall_total = 0
    overall_valid = 0
    for comp, ids in sorted(components.items()):
        total = sum(stats.get(i, (0, 0))[0] for i in ids)
        valid = sum(stats.get(i, (0, 0))[1] for i in ids)
        pct = (valid / total * 100.0) if total else 0.0
        comp_rows.append({"component": comp, "uptime_pct": round(pct, 4), "samples": total})
        overall_total += total
        overall_valid += valid

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
    """SLA/OLA history buckets via SQL GROUP BY on calendar day."""
    now = datetime.now(timezone.utc)
    if span == "year":
        start = now - timedelta(days=365)
    elif span == "5year":
        start = now - timedelta(days=365 * 5)
    else:
        start = now - timedelta(days=30)

    day_expr = func.date_trunc("day", CdpConnectivity.time).label("day")
    cdp_rows = (
        await db.execute(
            select(
                day_expr,
                func.count(CdpConnectivity.time)
                .filter(CdpConnectivity.reachable.is_(True)).label("up"),
                func.count(CdpConnectivity.time).label("total"),
            )
            .where(CdpConnectivity.time >= start)
            .group_by(func.date_trunc("day", CdpConnectivity.time))
        )
    ).all()

    tel_day = func.date_trunc("day", Telemetry.time).label("day")
    tel_rows = (
        await db.execute(
            select(
                tel_day,
                func.count(Telemetry.time).filter(Telemetry.is_valid.is_(True)).label("valid"),
                func.count(Telemetry.time).label("total"),
            )
            .where(Telemetry.time >= start)
            .group_by(func.date_trunc("day", Telemetry.time))
        )
    ).all()

    buckets: dict[str, dict] = {}
    for day, up, total in cdp_rows:
        key = day.date().isoformat()
        b = buckets.setdefault(key, {"day": key, "cdp_up": 0, "cdp_total": 0, "sensor_valid": 0, "sensor_total": 0})
        b["cdp_up"] = up or 0
        b["cdp_total"] = total or 0
    for day, valid, total in tel_rows:
        key = day.date().isoformat()
        b = buckets.setdefault(key, {"day": key, "cdp_up": 0, "cdp_total": 0, "sensor_valid": 0, "sensor_total": 0})
        b["sensor_valid"] = valid or 0
        b["sensor_total"] = total or 0

    rows = []
    for day, b in sorted(buckets.items()):
        sla = (b["cdp_up"] / b["cdp_total"] * 100.0) if b["cdp_total"] else 0.0
        ola = (b["sensor_valid"] / b["sensor_total"] * 100.0) if b["sensor_total"] else 0.0
        rows.append({"day": day, "sla_pct": round(sla, 4), "ola_pct": round(ola, 4)})

    return {"span": span, "bucket": bucket, "start_date": start, "end_date": now, "rows": rows}