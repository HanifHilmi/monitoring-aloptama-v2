"""AwosMetrics time-series endpoint (WIDN multi-metric, typed wide columns).

Fetches the wide ``awos_metrics`` hypertable for a site over a window and
returns per-metric ``series`` arrays. For windows wider than 1 day each
numeric column is LTTB-downsampled server-side so 1-month to 1-year
historical requests stay small for the frontend.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select, text
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

# awos_metrics columns that hold TEXT values (categorical, not numeric).
_TEXT_COLUMNS = {"als_dn", "sky_condition", "present_weather", "lightning"}

# Event/text columns that are BLANK when the sensor is ONLINE ('' = no
# event) — they never go NULL except via '///', so counting them would mask
# real outages (e.g. Present Weather was always ~100% while RA was offline).
# sky_condition and als_dn are value-always and stay as availability
# indicators.
_EVENT_TEXT_COLUMNS = {"present_weather", "lightning"}

# Columns used for the wind summary (wind rose + gust stats).
_WIND_COLUMNS = {"wind_speed_kt", "wind_dir_deg", "gust_speed_kt", "gust_dir_deg"}

# Wind rose speed categories (kt).
_WIND_CATEGORIES = ("calm", "light", "moderate", "strong", "gale")


async def _compute_wind(db: AsyncSession, slug: str, s_dt: datetime, e_dt: datetime) -> dict:
    """Wind summary over the raw 1-minute data (independent of LTTB).

    - windrose: minutes per 16 direction sectors x 5 speed categories.
    - max/min sustained wind speed.
    - gust events (gust_speed_kt > 0): count, max, and direction at the max.
    """
    rows = (
        await db.execute(
            text(
                "SELECT sector, "
                "COUNT(*) FILTER (WHERE speed < 1) AS calm, "
                "COUNT(*) FILTER (WHERE speed >= 1 AND speed < 10) AS light, "
                "COUNT(*) FILTER (WHERE speed >= 10 AND speed < 20) AS moderate, "
                "COUNT(*) FILTER (WHERE speed >= 20 AND speed < 30) AS strong, "
                "COUNT(*) FILTER (WHERE speed >= 30) AS gale "
                "FROM ("
                "  SELECT (floor(wind_dir_deg / 22.5)::int % 16) AS sector, "
                "         wind_speed_kt AS speed "
                "  FROM awos_metrics "
                "  WHERE site_id = :slug AND time >= :s AND time <= :e "
                "    AND wind_dir_deg IS NOT NULL AND wind_speed_kt IS NOT NULL"
                ") x GROUP BY sector ORDER BY sector"
            ),
            {"slug": slug, "s": s_dt, "e": e_dt},
        )
    ).all()
    windrose = [
        {"sector": i, "calm": 0, "light": 0, "moderate": 0, "strong": 0, "gale": 0}
        for i in range(16)
    ]
    for r in rows:
        windrose[r[0]] = {
            "sector": r[0], "calm": r[1], "light": r[2],
            "moderate": r[3], "strong": r[4], "gale": r[5],
        }

    speed = (
        await db.execute(
            text(
                "SELECT MAX(wind_speed_kt), MIN(wind_speed_kt) FROM awos_metrics "
                "WHERE site_id = :slug AND time >= :s AND time <= :e "
                "AND wind_speed_kt IS NOT NULL"
            ),
            {"slug": slug, "s": s_dt, "e": e_dt},
        )
    ).one()

    gust = (
        await db.execute(
            text(
                "SELECT COUNT(*) FILTER (WHERE gust_speed_kt > 0) AS cnt, "
                "MAX(gust_speed_kt) AS mx FROM awos_metrics "
                "WHERE site_id = :slug AND time >= :s AND time <= :e "
                "AND gust_speed_kt IS NOT NULL"
            ),
            {"slug": slug, "s": s_dt, "e": e_dt},
        )
    ).one()

    gust_cnt = gust.cnt or 0
    gust_max = None
    gust_dir = None
    if gust_cnt > 0:
        gust_max = gust.mx
        gd = (
            await db.execute(
                text(
                    "SELECT gust_dir_deg FROM awos_metrics "
                    "WHERE site_id = :slug AND time >= :s AND time <= :e "
                    "AND gust_speed_kt IS NOT NULL "
                    "ORDER BY gust_speed_kt DESC, time ASC LIMIT 1"
                ),
                {"slug": slug, "s": s_dt, "e": e_dt},
            )
        ).one()
        gust_dir = gd[0]

    return {
        "windrose": windrose,
        "max_speed_kt": speed[0],
        "min_speed_kt": speed[1],
        "gust": {
            "count": gust_cnt,
            "max_speed_kt": gust_max,
            "direction_deg": gust_dir,
        },
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
            "textSeries": {}, "textCounts": {}, "wind": None, "availability_pct": None,
            "range": range, "start": s_dt, "end": e_dt, "downsampled": False,
        }

    numeric_cols = [c for c in cols if c not in _TEXT_COLUMNS]
    text_cols = [c for c in cols if c in _TEXT_COLUMNS]

    # ---- Numeric series: LTTB when window > 1 day (or downsample given) ----
    window = e_dt - s_dt
    do_downsample = downsample is not None or window > timedelta(days=1)
    threshold = downsample or settings.lttb_default_threshold

    series: dict[str, list[dict]] = {}
    downsampled = 0
    count = 0
    if numeric_cols:
        # Fetch ONLY the requested numeric columns as light tuples (not ORM
        # objects), and decimate in SQL when the window would yield far more
        # minutes than the LTTB threshold: pick the LATEST row per time_bucket
        # so Python never processes more than ~2x threshold points.
        window_seconds = max(1, int(window.total_seconds()))
        bucket_minutes = None
        if window_seconds // 60 > threshold * 2:
            bucket_minutes = max(1, window_seconds // 60 // (threshold * 2))

        col_exprs = [getattr(AwosMetrics, c) for c in numeric_cols]
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
        count = len(rows)

        per_col: dict[str, list] = {c: [] for c in numeric_cols}
        for r in rows:
            for i, c in enumerate(numeric_cols):
                v = r[i + 1]
                # Keep NULL minutes so the frontend can break the line at
                # gaps (sensor offline). LTTB still filters them out.
                per_col[c].append((
                    r[0],
                    float(v) if isinstance(v, (int, float)) and not isinstance(v, bool) else None,
                ))

        for c in numeric_cols:
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

    # ---- Text series: value change points + per-value minute counts ----
    text_series: dict[str, list[dict]] = {}
    text_counts: dict[str, list[dict]] = {}
    for c in text_cols:
        trans = (
            await db.execute(
                text(
                    "SELECT time, " + c + " AS v FROM ("
                    "  SELECT time, " + c + ", LAG(" + c + ") OVER (ORDER BY time) AS prev "
                    "  FROM awos_metrics WHERE site_id = :slug AND time >= :s AND time <= :e"
                    ") sub WHERE " + c + " IS DISTINCT FROM prev OR prev IS NULL LIMIT 1000"
                ),
                {"slug": site_slug, "s": s_dt, "e": e_dt},
            )
        ).all()
        text_series[c] = [
            {"time": t, "value": v if v is not None else ""} for t, v in trans
        ]
        cnt = (
            await db.execute(
                text(
                    "SELECT " + c + " AS v, COUNT(*) AS n FROM awos_metrics "
                    "WHERE site_id = :slug AND time >= :s AND time <= :e "
                    "AND " + c + " IS NOT NULL AND " + c + " <> '' "
                    "GROUP BY " + c + " ORDER BY n DESC LIMIT 20"
                ),
                {"slug": site_slug, "s": s_dt, "e": e_dt},
            )
        ).all()
        text_counts[c] = [{"value": v, "count": n} for v, n in cnt]

    # Wind summary (ANEM wind rose + gust stats) from raw data when wind
    # columns are requested.
    wind = None
    if _WIND_COLUMNS.intersection(cols):
        wind = await _compute_wind(db, site_slug, s_dt, e_dt)

    # Data availability: % of minutes in the window where the sensor was
    # delivering data. Blank-when-online event texts (present_weather,
    # lightning) are excluded so they can't mask real outages; if every
    # requested column is such an event text (e.g. Lightning), fall back to
    # them so the sensor still reports an availability figure.
    availability_pct = None
    avail_cols = [c for c in cols if c not in _EVENT_TEXT_COLUMNS]
    if not avail_cols:
        avail_cols = cols
    if avail_cols:
        cond = " OR ".join(f"{c} IS NOT NULL" for c in avail_cols)
        avail = (
            await db.execute(
                text(
                    "SELECT COUNT(*) FILTER (WHERE " + cond + ") FROM awos_metrics "
                    "WHERE site_id = :slug AND time >= :s AND time <= :e"
                ),
                {"slug": site_slug, "s": s_dt, "e": e_dt},
            )
        ).scalar_one()
        total_min = max(1, int(window.total_seconds() // 60))
        availability_pct = round(min(100.0, (avail or 0) / total_min * 100.0), 1)

    return {
        "site": site_slug,
        "metrics": cols,
        "count": count,
        "series": series,
        "textSeries": text_series,
        "textCounts": text_counts,
        "wind": wind,
        "availability_pct": availability_pct,
        "range": range,
        "start": s_dt,
        "end": e_dt,
        "downsampled": downsampled > 0,
    }
