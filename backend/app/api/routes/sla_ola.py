"""Availability endpoints (SLA / OLA + components).

Semantics (per product definition):
- CDP Uptime   = uptime % of each CDP node from connectivity.
- SLA          = (CDP1 uptime + CDP2 uptime) / 2.
- DataAvail    = per-site availability of valid sensor data
                 (7 components per site; RWY04 ALS counts into RVR_ALS).
- OLA          = (RWY04 DA + RWYMID DA + RWY22 DA) / 3.

All aggregates use raw SQL (COUNT(*) FILTER) so they compile correctly on
asyncpg and stay well under the proxy timeout.

Both endpoints accept an explicit UTC window via ``start``/``end`` ISO
parameters (Frontend time-range picker uses these). When absent they fall
back to the preset keys ``today`` | ``3d`` | ``week`` | ``month`` | ``year``.
"""

from __future__ import annotations

import calendar as _cal
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.ingestion.components import COMPONENT_COLUMNS, SITE_COMPONENTS
from app.models import AwosMetrics, CdpNode, Sensor, Site

router = APIRouter(prefix="/sla-ola", tags=["sla-ola"])


def _parse_dt(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    v = value
    if v.endswith("Z"):
        v = v[:-1] + "+00:00"
    try:
        return datetime.fromisoformat(v).astimezone(timezone.utc)
    except ValueError:
        return None


def _default_window(range_key: str, now: datetime) -> tuple[datetime, datetime]:
    if range_key == "today":
        start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    elif range_key == "3d":
        start = now - timedelta(days=3)
    elif range_key == "week":
        start = now - timedelta(days=7)
    elif range_key == "month":
        start = now - timedelta(days=30)
    else:  # year
        start = now - timedelta(days=365)
    return start, now


async def _cdp_uptime(db: AsyncSession, node: CdpNode, start: datetime, end: datetime) -> dict:
    """CDP uptime = UP minutes / TOTAL PERIOD minutes.

    A minute WITHOUT a connectivity row counts as DOWN (missing data =
    not delivering). This is computed entirely in SQL so the frontend never
    does the heavy math.
    """
    row = (
        await db.execute(
            text(
                "SELECT COUNT(*) FILTER (WHERE reachable) AS up "
                "FROM cdp_connectivity "
                "WHERE cdp_id = :cid AND time >= :start AND time <= :end"
            ),
            {"cid": node.id, "start": start, "end": end},
        )
    ).one()
    up = row.up or 0
    total_minutes = max(1, int((end - start).total_seconds() // 60))
    uptime_pct = min(100.0, up / total_minutes * 100.0)
    downtime_minutes = max(0, total_minutes - up)
    return {
        "cdp_id": node.id,
        "name": node.name,
        "ip_address": str(node.ip_address),
        "uptime_pct": round(uptime_pct, 4),
        "downtime_seconds": downtime_minutes * 60,
        "samples": up,
    }


async def _site_data_availability(db: AsyncSession, site: Site, start: datetime, end: datetime) -> dict:
    # Query sensors explicitly — accessing the lazy relationship
    # (site.sensors) inside sync list-comprehension triggers an async
    # MissingGreenlet (500) on the deployed backend.
    sensors = (
        await db.execute(
            select(Sensor).where(Sensor.site_id == site.id, Sensor.is_enabled.is_(True))
        )
    ).scalars().all()
    if not sensors:
        return {"site_id": site.id, "slug": site.slug, "code": site.code, "name": site.name,
                "data_availability_pct": 0.0, "components": []}

    components: dict[str, list[int]] = {}
    for s in sensors:
        comp = s.component or s.code
        components.setdefault(comp, []).append(s.id)

    # NEW OLA source: component validity from the WIDE awos_metrics table.
    total_period_minutes = max(1, int((end - start).total_seconds() // 60))
    all_rows = (
        await db.execute(
            select(AwosMetrics)
            .where(AwosMetrics.site_id == site.slug, AwosMetrics.time >= start, AwosMetrics.time <= end)
        )
    ).scalars().all()

    comp_counts: dict[str, int] = {}
    dcp_present = 0
    for r in all_rows:
        for comp, cols in COMPONENT_COLUMNS.items():
            if any(getattr(r, c) is not None for c in cols):
                comp_counts[comp] = comp_counts.get(comp, 0) + 1
                if comp in {"ATRH", "BARO", "ANEM", "RVR", "CEL", "PWX", "RAIN", "SOLR", "LIGH"}:
                    dcp_present += 0
        if any(getattr(r, c) is not None for c in
               [cc for cols in COMPONENT_COLUMNS.values() for cc in cols]):
            dcp_present = max(dcp_present, 1)

    comp_rows = []
    overall_valid = 0
    overall_expected = 0
    codes = list(SITE_COMPONENTS.get(site.slug, list(COMPONENT_COLUMNS))) + ["DCP"] if False else None
    from app.ingestion.components import SITE_COMPONENTS
    codes = list(SITE_COMPONENTS.get(site.slug, [])) + ["DCP"]
    for comp in codes:
        if comp == "DCP":
            observed = dcp_present if dcp_present else 0
            valid = dcp_present
        else:
            observed = comp_counts.get(comp, 0)
            valid = observed
        expected = total_period_minutes
        pct = (valid / expected * 100.0) if expected else 0.0
        comp_rows.append({"component": comp, "uptime_pct": round(pct, 4), "samples": observed})
        overall_expected += expected
        overall_valid += valid

    data_avail = (overall_valid / overall_expected * 100.0) if overall_expected else 0.0
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
    range: str = Query("month", pattern="^(today|3d|week|month|year|custom)$"),
    start: str | None = Query(default=None, description="ISO-8601 UTC start (overrides range)"),
    end: str | None = Query(default=None, description="ISO-8601 UTC end (overrides range)"),
    db: AsyncSession = Depends(get_db),
) -> dict:
    now = datetime.now(timezone.utc)
    s = _parse_dt(start)
    e = _parse_dt(end)
    if s is None or e is None:
        s, e = _default_window(range, now)
    if e <= s:
        e = s + timedelta(minutes=1)

    nodes = (await db.execute(select(CdpNode))).scalars().all()
    sites = (await db.execute(select(Site))).scalars().all()

    cdps = [await _cdp_uptime(db, n, s, e) for n in nodes]
    site_das = [await _site_data_availability(db, site, s, e) for site in sites]

    sla_pct = round(sum(c["uptime_pct"] for c in cdps) / len(cdps), 4) if cdps else 0.0
    ola_pct = round(sum(d["data_availability_pct"] for d in site_das) / len(site_das), 4) if site_das else 0.0

    return {
        "generated_at": now,
        "range": range,
        "start_date": s,
        "end_date": e,
        "sla_pct": sla_pct,
        "ola_pct": ola_pct,
        "cdp_uptime": cdps,
        "sites": site_das,
    }


@router.get("/history")
async def get_history(
    bucket: str = Query("daily", pattern="^(daily|weekly|monthly|yearly)$"),
    span: str = Query("month", pattern="^(month|year|5year)$"),
    start: str | None = Query(default=None, description="ISO-8601 UTC start"),
    end: str | None = Query(default=None, description="ISO-8601 UTC end"),
    db: AsyncSession = Depends(get_db),
) -> dict:
    now = datetime.now(timezone.utc)
    s = _parse_dt(start)
    e = _parse_dt(end)
    if s is None or e is None:
        if span == "year":
            s, e = now - timedelta(days=365), now
        elif span == "5year":
            s, e = now - timedelta(days=365 * 5), now
        else:
            s, e = now - timedelta(days=30), now

    cdp_rows = (
        await db.execute(
            text(
                "SELECT date_trunc('day', time) AS day, "
                "COUNT(*) FILTER (WHERE reachable) AS up, COUNT(*) AS total "
                "FROM cdp_connectivity WHERE time >= :start AND time <= :end GROUP BY 1"
            ),
            {"start": s, "end": e},
        )
    ).all()
    tel_rows = (
        await db.execute(
            text(
                "SELECT date_trunc('day', time) AS day, "
                "COUNT(*) FILTER (WHERE is_valid) AS valid, COUNT(*) AS total "
                "FROM telemetry WHERE time >= :start AND time <= :end GROUP BY 1"
            ),
            {"start": s, "end": e},
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

    return {"span": span, "bucket": bucket, "start_date": s, "end_date": e, "rows": rows}


@router.get("/downtime-map")
async def downtime_map(
    year: int = Query(2026, ge=2026, le=2099),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Per-CDP per-day downtime minutes for a year (calendar heatmap input).

    Each CDP node gets its own day list: down = expected minutes - up
    minutes; a minute without a connectivity row counts as DOWN.
    """
    now = datetime.now(timezone.utc)
    nodes = (await db.execute(select(CdpNode))).scalars().all()
    start = datetime(year, 1, 1, tzinfo=timezone.utc)
    end = datetime(year + 1, 1, 1, tzinfo=timezone.utc)
    if start >= now or not nodes:
        return {"year": year, "cdps": []}

    up_rows = (
        await db.execute(
            text(
                "SELECT cdp_id, date_trunc('day', time) AS d, "
                "COUNT(*) FILTER (WHERE reachable) AS up "
                "FROM cdp_connectivity "
                "WHERE time >= :start AND time < :end "
                "GROUP BY cdp_id, date_trunc('day', time)"
            ),
            {"start": start, "end": end},
        )
    ).all()
    up_by: dict[int, dict[str, int]] = {}
    for cdp_id, d, up in up_rows:
        up_by.setdefault(cdp_id, {})[d.date().isoformat()] = up or 0

    last_day = now.date() if year == now.year else datetime(year, 12, 31, tzinfo=timezone.utc).date()
    out_cdps = []
    for n in nodes:
        days = []
        day = start
        while day.date() <= last_day:
            day_end = min(day + timedelta(days=1), now)
            total_min = max(1, int((day_end - day).total_seconds() // 60))
            up = min(up_by.get(n.id, {}).get(day.date().isoformat(), 0), total_min)
            days.append({"day": day.date().isoformat(), "downtime_minutes": max(0, total_min - up)})
            day += timedelta(days=1)
        out_cdps.append({"cdp_id": n.id, "name": n.name, "days": days})

    return {"year": year, "cdps": out_cdps}