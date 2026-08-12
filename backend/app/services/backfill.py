"""Initial auto-backfill service (WIDN multi-metric).

On first boot (when telemetry tables are uninitialized/empty), this service
runs a historical backfill starting from ``settings.backfill_start``
(2026-01-01 by default) so dashboards render immediately.

Semantics:
- SLA  = availability of the CDP oneminute file for the minute
         (file present + parseable => UP; missing/unreadable => DOWN).
- OLA  = availability % of valid sensor data (valid metrics / expected
         metrics for the sensor at that minute).
- Telemetry is stored one row per (minute, sensor, metric) with both
  float (value) and string (text_value) payloads.
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
from app.ingestion.components import SITE_COMPONENTS, wide_row_components, row_dcp_online
from app.ingestion.state_machine import (
    DowntimeStateMachine,
    transition_ola_component,
    transition_sla,
)
from app.models import (
    CdpConnectivity,
    CdpNode,
    Sensor,
    Site,
    AwosMetrics,
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
    tel = (await session.execute(select(func.count(AwosMetrics.time)))).scalar_one()
    return tel == 0


async def run_initial_backfill_if_needed(
    session: AsyncSession,
    *,
    force: bool = False,
) -> bool:
    """Run the historical backfill when the database is empty (or forced)."""
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
    """Iterate day-by-day over the range, ingest, and feed state machines."""
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
    """Ingest every minute in [start, end) for all sites."""
    sensors_by_site: dict[int, list[Sensor]] = {}
    for s in sensors:
        sensors_by_site.setdefault(s.site_id, []).append(s)

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
    minute_ts = ts.replace(second=0, microsecond=0)
    for site in sites:
        site_sensors = sensors_by_site.get(site.id, [])
        if not site_sensors:
            continue

        # Build sensor specs with WIDN symbol/station mapping.
        specs: dict[str, dict] = {}
        sensor_nodes: dict[str, Sensor] = {}
        for s in site_sensors:
            if not s.is_enabled:
                continue
            entry: dict = {"sensor_id": s.id}
            if s.fallback_slice:
                entry["fallback_slice"] = s.fallback_slice
            if s.symbol:
                entry["symbol"] = s.symbol
            if s.station:
                entry["station"] = s.station
            specs[s.code] = entry
            sensor_nodes[s.code] = s

        # Try each site file prefix. SLA = file exists and parsed.
        parsed_batch: dict = {}
        for prefix in site.file_prefixes or []:
            one_min_path = reader.resolve_site_file(prefix, minute_ts)
            raw_path = reader.resolve_raw_sensor_file(prefix, minute_ts)
            if one_min_path is None or raw_path is None:
                continue
            default_ts = parse_timestamp_from_filename(one_min_path.name) or minute_ts
            parsed_batch = parse_site_batch(one_min_path, raw_path, specs, default_ts)
            if parsed_batch:
                break

        # SLA: file availability per CDP node. Both nodes share the connect
        # status in the SLA view; use the active reader's reachability plus
        # whether a file was actually read.
        file_up = bool(parsed_batch)
        for node in reader.state.nodes.values():
            await transition_sla(
                session, sm, cdp_id=node.cdp_id, site_id=site.id,
                reachable=file_up, ts=minute_ts,
            )

        if not parsed_batch:
            continue

        # ALSO persist WIDE awos_metrics rows + component OLA (feeds the
        # awos_metrics-based SLA/OLA/status/runway paths). EAV kept for parity.
        for row in [r for r in _group_wide_static(parsed_batch, site.slug)
                    if r["time"] == minute_ts]:
            await session.execute(_wide_upsert(row))
        present: set = set()
        for row in [r for r in _group_wide_static(parsed_batch, site.slug)
                    if r["time"] == minute_ts]:
            present |= set(wide_row_components(row))
            if row_dcp_online(row):
                present.add("DCP")
        for comp in list(SITE_COMPONENTS.get(site.slug, [])) + ["DCP"]:
            await transition_ola_component(
                session, sm, site_id=site.id, component_code=comp,
                is_down=comp not in present, ts=minute_ts,
            )

        # Persist telemetry + OLA availability per sensor.
        for code, metrics in parsed_batch.items():
            sensor = sensor_nodes.get(code)
            if sensor is None or not metrics:
                continue
            valid_count = sum(1 for m in metrics if m.is_valid)
            is_down = valid_count == 0
            await transition_ola(
                session, sm, sensor_id=sensor.id, site_id=site.id,
                is_down=is_down, ts=minute_ts,
                reason="missing" if is_down else "ok",
            )
            for m in metrics:
                await session.execute(
                    insert(AwosMetrics)
                    .values(
                        time=minute_ts, sensor_id=sensor.id,
                        metric=m.metric, value=m.value,
                        text_value=m.text_value,
                        status="ok" if m.is_valid else "invalid",
                        is_valid=m.is_valid,
                        raw_line=m.raw or None,
                    )
                    .on_conflict_do_update(
                        index_elements=["time", "sensor_id", "metric"],
                        set_={
                            "value": m.value,
                            "text_value": m.text_value,
                            "status": "ok" if m.is_valid else "invalid",
                            "is_valid": m.is_valid,
                            "raw_line": m.raw or None,
                        },
                    )
                )


def _wide_upsert(row: dict):
    from sqlalchemy.dialects.postgresql import insert as _ins
    ins = _ins(AwosMetrics)
    return ins.values([row]).on_conflict_do_update(
        index_elements=["time", "site_id"],
        set_={c: getattr(ins.excluded, c) for c in row if c not in ("time", "site_id")},
    )


def _group_wide_static(parsed_by_code: dict, site_id: str) -> list[dict]:
    """Collapse one parsed minute into wide awos_metrics row(s)."""
    from app.ingestion.worker import IngestionWorker
    return IngestionWorker._group_wide(parsed_by_code, site_id)
