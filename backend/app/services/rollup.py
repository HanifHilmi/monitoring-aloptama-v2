"""Pre-aggregated SLA/OLA rollups into ``daily_sla_ola``.

Rebuilds the daily hypertable from ``downtime_events`` so dashboard queries
over 30+ day ranges stay well under 200ms (single hypertable scan, no joins).

Downtime per day is computed by clipping each event to calendar-day
boundaries and summing the clipped durations.
"""

from __future__ import annotations

import logging
from datetime import date, datetime, timezone

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


async def rebuild_daily_rollups(
    session: AsyncSession,
    start_date: date,
    end_date: date,
) -> int:
    """Rebuild ``daily_sla_ola`` for [start_date, end_date].

    Returns the number of rollup rows written.
    """
    if start_date > end_date:
        return 0

    # 1) Delete existing rollups in range (full rebuild keeps math consistent)
    await session.execute(
        text(
            """
            DELETE FROM daily_sla_ola
            WHERE weo_time BETWEEN :start_date AND :end_date
            """
        ),
        {"start_date": start_date, "end_date": end_date},
    )

    # 2) Build per-day clipped downtime from events
    stmt = text(
        """
        WITH clipped AS (
            SELECT
                e.id,
                e.scope_type,
                e.entity_type,
                e.cdp_id,
                e.sensor_id,
                e.site_id,
                d.day_start::timestamptz AS day_start,
                LEAST(
                    COALESCE(e.end_time, NOW()),
                    (d.day_start + interval '1 day')::timestamptz
                ) AS day_end,
                e.end_time IS NULL AS is_open
            FROM downtime_events e
            CROSS JOIN LATERAL (
                SELECT
                    date_trunc('day', ts) AS day_start
                FROM generate_series(
                    e.start_time::date,
                    COALESCE(e.end_time, NOW())::date,
                    interval '1 day'
                ) AS ts
            ) d
        ),
        clipped_valid AS (
            SELECT *
            FROM clipped
            WHERE day_start::date BETWEEN :start_date AND :end_date
              AND day_end > day_start
        ),
        daily_totals AS (
            SELECT
                c.scope_type,
                c.entity_type,
                c.cdp_id,
                c.sensor_id,
                c.site_id,
                c.day_start::date AS weo_time,
                COUNT(DISTINCT c.id) AS total_events,
                COUNT(DISTINCT c.id) FILTER (WHERE c.is_open) AS open_events,
                COUNT(DISTINCT c.id) FILTER (WHERE NOT c.is_open) AS closed_events,
                COALESCE(SUM(
                    EXTRACT(EPOCH FROM (c.day_end - c.day_start))
                ), 0)::bigint AS downtime_seconds
            FROM clipped_valid c
            GROUP BY
                c.scope_type,
                c.entity_type,
                c.cdp_id,
                c.sensor_id,
                c.site_id,
                c.day_start::date
        ),
        calendar AS (
            SELECT day::date AS weo_time
            FROM generate_series(:start_date, :end_date, interval '1 day') AS day
        )
        INSERT INTO daily_sla_ola (
            weo_time, scope_type, entity_type, cdp_id, sensor_id, site_id,
            total_seconds, uptime_seconds, downtime_seconds, uptime_pct,
            open_events, closed_events
        )
        SELECT
            cal.weo_time,
            dt.scope_type,
            dt.entity_type,
            COALESCE(dt.cdp_id, 0),
            COALESCE(dt.sensor_id, 0),
            dt.site_id,
            86400 AS total_seconds,
            86400 - LEAST(dt.downtime_seconds, 86400) AS uptime_seconds,
            LEAST(dt.downtime_seconds, 86400) AS downtime_seconds,
            ROUND(
                (86400 - LEAST(dt.downtime_seconds, 86400))::numeric
                / 86400 * 100, 4
            )::float AS uptime_pct,
            dt.open_events,
            dt.closed_events
        FROM daily_totals dt
        JOIN calendar cal ON cal.weo_time = dt.weo_time
        """
    )
    result = await session.execute(stmt, {"start_date": start_date, "end_date": end_date})
    await session.commit()
    rows = result.rowcount or 0
    logger.info("Rollup rebuilt: %d rows for %s..%s", rows, start_date, end_date)
    return rows


async def rebuild_rollup_range(
    session: AsyncSession,
    start_date: date,
    end_date: date | None = None,
) -> int:
    """Convenience wrapper; defaults end to today."""
    if end_date is None:
        end_date = datetime.now(timezone.utc).date()
    return await rebuild_daily_rollups(session, start_date, end_date)