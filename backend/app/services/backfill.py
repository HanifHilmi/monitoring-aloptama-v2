"""Initial auto-backfill service.

On first boot (when telemetry tables are uninitialized/empty), this service
runs a historical backfill starting from ``settings.backfill_start``
(2026-01-01 by default) so dashboards render immediately.

Backfill flow:
1. Detect empty state (no telemetry + no connectivity samples).
2. Step forward from the configured start date to ``now`` in day chunks.
3. For each chunk, resolve the 1-minute log files and parse with raw-DCP
   fallback, feeding the same state machine transitions as live ingestion.
4. Rebuild the daily SLA/OLA rollup for the full backfill range.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.ingestion.parsers import parse_site_batch, parse_timestamp_from_filename
from app.ingestion.state_machine import (
    DowntimeStateMachine,
    transition_ola,
    transition_sla,
)
from app.models import (
    CdpConnectivity,
    CdpNode,
    Sensor,
    Site,
    Telemetry,
)
from app.ingestion.cdp_reader import CdpReader
from app.services.rollup import rebuild_daily_rollups

logger = logging.getLogger(__name__)


def _parse_backfill_start(value: str) -> datetime:
    """Parse ``2026-01-01T00:00:00Z`` style config into UTC datetime."""
    if value.endswith("Z"):
        value = value[:-1] + "+00:00"
    return datetime.fromisoformat(value).astimezone(timezone.utc)


async def is_database_uninitialized(session: AsyncSession) -> bool:
    """True when no telemetry exists.

    Live CDP connectivity probes run continuously, so cdp_connectivity rows
    appear even on a fresh database. Telemetry is the true signal for whether
    the historical backfill has populated sensor data.
    """
    tel = (await session.execute(select(func.count(Telemetry.time)))).scalar_one()
    return tel == 0


async def run_initial_backfill_if_needed(
    session: AsyncSession,
    *,
    force: bool = False,
) -> bool:
    """Run the historical backfill when the database is empty (or forced).

    Returns True when a backfill ran.
    """
    if not force and not await is_database_uninitialized(session):
        logger.info("Database already initialized — skipping backfill")
        return False

    start = _parse_backfill_start(settings.backfill_start)
    end = datetime.now(timezone.utc)
    if start >= end:
        logger.warning("Backfill start is in the future — nothing to do")
        return False

    logger.info("Starting historical backfill %s -> %s", start, end)
    await _run_backfill(session, start, end)

    await rebuild_daily_rollups(session, start.date(), end.date())
    logger.info("Backfill complete")
    return True


async def _run_backfill(
    session: AsyncSession,
    start: datetime,
    end: datetime,
) -> None:
    """Iterate hour-by-hour over the range, ingest, and feed state machines."""
    # Build runtime reader + state machine from master data
    nodes = (await session.execute(select(CdpNode))).scalars().all()
    node_dicts = [
        {
            "id": n.id,
            "name": n.name,
            "ip_address": str(n.ip_address),
            "mount_path": n.mount_path,
            "role": n.role,
        }
        for n in nodes
    ]
    reader = CdpReader(node_dicts)
    sm = DowntimeStateMachine()

    sites = (await session.execute(select(Site))).scalars().all()
    sensors = (await session.execute(select(Sensor))).scalars().all()

    cursor = start
    chunk = timedelta(days=settings.backfill_batch_days)
    while cursor < end:
        chunk_end = min(cursor + chunk, end)
        await _backfill_chunk(session, reader, sm, sites, sensors, cursor, chunk_end)
        await session.commit()
        logger.info("Backfill progress: %s .. %s", cursor, chunk_end)
        cursor = chunk_end
        # Yield to allow other coroutines to make progress on huge ranges
        await asyncio.sleep(0)


async def _backfill_chunk(
    session: AsyncSession,
    reader: CdpReader,
    sm: DowntimeStateMachine,
    sites: list[Site],
    sensors: list[Sensor],
    start: datetime,
    end: datetime,
) -> None:
    """Ingest every minute in [start, end) for all sites with SLA/OLA."""
    # Refresh node reachability once per chunk
    await reader.check_all()

    sensors_by_site: dict[int, list[Sensor]] = {}
    for s in sensors:
        sensors_by_site.setdefault(s.site_id, []).append(s)

    # SLA: transition CDP nodes from current reachability as of `start`
    for node in nodes_from_state(reader):
        await transition_sla(
            session, sm, cdp_id=node.cdp_id, site_id=None,
            reachable=node.reachable, ts=start,
        )

    minute = start
    while minute < end:
        await _ingest_minute(session, reader, sm, sites, sensors_by_site, minute)
        minute += timedelta(minutes=1)


async def _ingest_minute(
    session: AsyncSession,
    reader: CdpReader,
    sm: DowntimeStateMachine,
    sites: list[Site],
    sensors_by_site: dict[int, list[Sensor]],
    ts: datetime,
) -> None:
    for site in sites:
        site_sensors = sensors_by_site.get(site.id, [])
        if not site_sensors:
            continue

        # Build unified sensor specs (position for 1-min, fallback_slice for raw)
        specs: dict[str, dict] = {}
        for s in site_sensors:
            if not s.is_enabled:
                continue
            entry: dict = {"sensor_id": s.id}
            if s.position:
                entry["position"] = s.position
            if s.fallback_slice:
                entry["fallback_slice"] = s.fallback_slice
            if s.symbol:
                entry["symbol"] = s.symbol
            if s.station:
                entry["station"] = s.station
            specs[s.code] = entry

        # Try each site file prefix
        parsed_batch: dict = {}
        for prefix in site.file_prefixes or []:
            one_min_path = reader.resolve_site_file(prefix, ts)
            raw_path = reader.resolve_raw_sensor_file(prefix, ts)
            if one_min_path is None or raw_path is None:
                continue
            default_ts = parse_timestamp_from_filename(one_min_path.name) or ts
            parsed_batch = parse_site_batch(one_min_path, raw_path, specs, default_ts)
            if parsed_batch:
                break

        if not parsed_batch:
            continue

        sensor_by_code = {s.code: s for s in site_sensors}
        for code, samples in parsed_batch.items():
            sensor = sensor_by_code.get(code)
            if sensor is None or not samples:
                continue
            sample = samples[-1]
            is_down = sample.status != "ok"
            reason = sample.status if is_down else "ok"

            await transition_ola(
                session, sm, sensor_id=sensor.id, site_id=site.id,
                is_down=is_down, ts=ts, reason=reason,
            )

            # Upsert telemetry for this minute
            await session.execute(
                insert(Telemetry)
                .values(
                    time=ts, sensor_id=sensor.id,
                    value=sample.value, status=sample.status,
                    raw_line=sample.raw or None,
                )
                .on_conflict_do_update(
                    index_elements=["time", "sensor_id"],
                    set_={
                        "value": sample.value,
                        "status": sample.status,
                        "raw_line": sample.raw or None,
                    },
                )
            )


def nodes_from_state(reader: CdpReader) -> list:
    """Expose the reader's live node states as lightweight objects."""
    return list(reader.state.nodes.values())