"""AwosMetrics time-series endpoint (WIDN multi-metric, typed wide columns).

Fetches the wide ``awos_metrics`` hypertable for a site over a window and
returns per-metric ``series`` arrays. For windows wider than 1 day each
numeric column is LTTB-downsampled server-side so 1-month to 1-year
historical requests stay small for the frontend.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.session import get_db
from app.models import AwosMetrics
from app.utils.lttb import downsample_series

router = APIRouter(prefix="/telemetry", tags=["telemetry"])

RANGE_OPTIONS = {
    "15m": timedelta(minutes=15),
    "30m": timedelta(minutes=30),
    "1h": timedelta(hours=1),
    "3h": timedelta(hours=3),
    "12h": timedelta(hours=12),
    "6h": timedelta(hours=6),
    "24h": timedelta(hours=24),
    "7d": timedelta(days=7),
    "30d": timedelta(days=30),
    "today": "today",
    "3d": timedelta(days=3),
    "week": timedelta(days=7),
    "month": timedelta(days=30),
}

# Wide-column metric alias -> awos_metrics column.
WIDE_ALIAS = {
    "TEMP": "temp_c", "DEWP": "dewp_c", "RH": "rh_pct",
    "QNH": "qnh_hpa", "DA": "da_ft",
    "WS": "wind_speed_kt", "WD": "wind_dir_deg",
    "WGS": "gust_speed_kt", "WGD": "gust_dir_deg",
    "RVR": "rvr_m", "VIS": "vis_m", "ALS": "als_cd", "D/N": "als_dn",
    "LR1": "lr1_100ft", "SKY": "sky_condition",
    "RA": "precip_mm", "PW": "present_weather",
    "SOL": "solar_wm2", "LTX": "lightning",
}


def _parse_dt(v: str | None):
    if not v:
        return None
    if v.endswith("Z"):
        v = v[:-1] + "+00:00"
    try:
        return datetime.fromisoformat(v).astimezone(timezone.utc)
    except ValueError:
        return None


@router.get("/{site_slug}")
async def get_wide_telemetry(
    site_slug: str,
    range: str = Query("today", pattern="^(15m|30m|1h|3h|12h|1h|6h|24h|7d|30d|today|3d|week|month|custom)$"),
    start: str | None = Query(default=None, description="ISO-8601 UTC start (overrides range)"),
    end: str | None = Query(default=None, description="ISO-8601 UTC end (overrides range)"),
    metrics: str | None = Query(default=None, description="Comma-separated metric aliases"),
    downsample: int | None = Query(default=None, ge=10, le=10000),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Fetch wide awos_metrics for a site over a window (UTC).

    - metrics: comma-separated aliases (e.g. TEMP,WS,QNH) or wide column
      names (temp_c,wind_speed_kt). Defaults to numeric columns only.
    - Returns: {"site":, "series": {<column>: [{time, value}, ...]}, ...}.
      Series are LTTB-downsampled when the window exceeds 1 day.
    """
    now = datetime.now(timezone.utc)
    rng = RANGE_OPTIONS.get(range, "today")
    if rng == "today":
        s_dt = now.replace(hour=0, minute=0, second=0, microsecond=0)
        e_dt = now
    elif isinstance(rng, timedelta):
        e_dt = now
        s_dt = now - rng
    else:
        s_dt = now.replace(hour=0, minute=0, second=0, microsecond=0)
        e_dt = now
    if start:
        p = _parse_dt(start)
        if p:
            s_dt = p
    if end:
        p = _parse_dt(end)
        if p:
            e_dt = p

    # Resolve requested metrics to wide columns.
    if metrics:
        cols = [WIDE_ALIAS.get(m.strip(), m.strip()) for m in metrics.split(",") if m.strip()]
    else:
        cols = [
            "temp_c", "dewp_c", "rh_pct", "qnh_hpa", "da_ft",
            "wind_speed_kt", "wind_dir_deg", "gust_speed_kt", "gust_dir_deg",
            "rvr_m", "vis_m", "als_cd", "lr1_100ft", "precip_mm", "solar_wm2",
        ]

    valid = {c.name for c in AwosMetrics.__table__.columns if c.name not in ("time", "site_id", "raw_line")}
    cols = [c for c in cols if c in valid]
    if not cols:
        return {
            "site": site_slug, "metrics": [], "count": 0, "series": {},
            "range": range, "start": s_dt, "end": e_dt, "downsampled": False,
        }

    # LTTB when the window exceeds 1 day (or downsample explicitly given).
    window = e_dt - s_dt
    do_downsample = downsample is not None or window > timedelta(days=1)
    threshold = downsample or settings.lttb_default_threshold

    # Fetch ONLY the requested columns as light tuples (not ORM objects), and
    # decimate in SQL when the window would yield far more minutes than the
    # LTTB threshold: pick the LATEST row per time_bucket so Python never
    # processes more than ~2x threshold points, no matter the window size.
    window_seconds = max(1, int(window.total_seconds()))
    bucket_minutes = None
    if window_seconds // 60 > threshold * 2:
        bucket_minutes = max(1, window_seconds // 60 // (threshold * 2))

    col_exprs = [getattr(AwosMetrics, c) for c in cols]
    base = (
        select(AwosMetrics.time, *col_exprs)
        .where(AwosMetrics.site_id == site_slug, AwosMetrics.time >= s_dt, AwosMetrics.time <= e_dt)
    )
    if bucket_minutes:
        bucket_expr = func.time_bucket(timedelta(minutes=bucket_minutes), AwosMetrics.time)
        stmt = base.distinct(bucket_expr).order_by(bucket_expr, AwosMetrics.time.desc())
    else:
        stmt = base.order_by(AwosMetrics.time.asc())
    rows = (await db.execute(stmt)).all()
    if bucket_minutes:
        rows = sorted(rows, key=lambda r: r[0])  # LTTB needs ascending time

    # Group values per requested column: [(datetime, value), ...].
    # Only numeric columns produce a series — TEXT columns (present_weather,
    # sky_condition, als_dn, lightning) are skipped (their values are strings
    # like 'NCD' and never plotted by the frontend).
    per_col: dict[str, list] = {c: [] for c in cols}
    for r in rows:
        for i, c in enumerate(cols):
            v = r[i + 1]
            if isinstance(v, (int, float)) and not isinstance(v, bool):
                per_col[c].append((r[0], float(v)))

    series: dict[str, list[dict]] = {}
    downsampled = 0
    for c in cols:
        pts = per_col[c]
        if do_downsample and len(pts) > threshold:
            t0 = pts[0][0].timestamp()
            sampled = downsample_series(pts, threshold)
            series[c] = [
                {"time": datetime.fromtimestamp(t0 + x, tz=timezone.utc), "value": y}
                for x, y in sampled
            ]
            downsampled += 1
        else:
            series[c] = [{"time": t, "value": v} for t, v in pts]

    return {
        "site": site_slug,
        "metrics": cols,
        "count": len(rows),
        "series": series,
        "range": range,
        "start": s_dt,
        "end": e_dt,
        "downsampled": downsampled > 0,
    }
