"""Background ingestion worker.

Responsibilities:
- Periodically probe CDP nodes (active-passive failover via ``CdpReader``).
- Ingest 1-minute telemetry logs (with raw-DCP fallback).
- Feed the SLA/OLA downtime state machine.
- Periodically rebuild the ``daily_sla_ola`` rollup hypertable.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import delete, func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.session import AsyncSessionLocal
from app.ingestion.cdp_reader import CdpReader
from app.ingestion.parsers import parse_site_batch, parse_timestamp_from_filename
from app.ingestion.state_machine import (
    DowntimeStateMachine,
    load_open_events,
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
from app.services.rollup import rebuild_daily_rollups

logger = logging.getLogger(__name__)


class IngestionWorker:
    """Long-running async ingestion loop."""

    def __init__(self, reader: CdpReader, sm: DowntimeStateMachine):
        self.reader = reader
        self.sm = sm
        self._stop = asyncio.Event()
        self._tasks: list[asyncio.Task] = []

    # ------------------------------------------------------------------
    async def start(self) -> None:
        """Launch all background loops."""
        logger.info("Starting ingestion worker")
        self._tasks = [
            asyncio.create_task(self._cdp_loop(), name="cdp-loop"),
            asyncio.create_task(self._telemetry_loop(), name="telemetry-loop"),
            asyncio.create_task(self._rollup_loop(), name="rollup-loop"),
        ]

    async def stop(self) -> None:
        self._stop.set()
        for t in self._tasks:
            t.cancel()
        await asyncio.gather(*self._tasks, return_exceptions=True)

    # ------------------------------------------------------------------
    async def _cdp_loop(self) -> None:
        """Probe node connectivity and feed SLA state machine."""
        while not self._stop.is_set():
            try:
                async with AsyncSessionLocal() as session:
                    await self._check_cdps(session)
            except Exception:
                logger.exception("CDP check loop error")
            await asyncio.sleep(settings.cdps_check_interval_seconds)

    async def _check_cdps(self, session: AsyncSession) -> None:
        nodes = await session.execute(select(CdpNode))
        for n in nodes.scalars():
            await self._check_one_cdp(session, n)
        await session.commit()

    async def _check_one_cdp(self, session: AsyncSession, node: CdpNode) -> None:
        # Refresh runtime state
        state = self.reader.state.nodes.get(node.name)
        if state is None:
            return
        await self.reader.check_all()
        reachable = state.reachable
        ts = datetime.now(timezone.utc)

        # Persist connectivity sample
        await session.execute(
            insert(CdpConnectivity)
            .values(
                time=ts,
                cdp_id=node.id,
                reachable=reachable,
                rtt_ms=state.last_rtt_ms,
                error_message=state.error_message,
            )
            .on_conflict_do_update(
                index_elements=["time", "cdp_id"],
                set_={
                    "reachable": reachable,
                    "rtt_ms": state.last_rtt_ms,
                    "error_message": state.error_message,
                },
            )
        )

        # State machine transition (SLA)
        await transition_sla(
            session,
            self.sm,
            cdp_id=node.id,
            site_id=None,
            reachable=reachable,
            ts=ts,
        )

    # ------------------------------------------------------------------
    async def _telemetry_loop(self) -> None:
        """Ingest the latest 1-minute log window with raw-DCP fallback."""
        while not self._stop.is_set():
            try:
                async with AsyncSessionLocal() as session:
                    await self._ingest_latest(session)
            except Exception:
                logger.exception("Telemetry ingestion error")
            await asyncio.sleep(settings.ingestion_interval_seconds)

    async def _ingest_latest(self, session: AsyncSession) -> None:
        now = datetime.now(timezone.utc)
        # Process the previous full minute (files are written after minute close)
        minute_ts = (now - timedelta(minutes=1)).replace(second=0, microsecond=0)

        sites = (await session.execute(select(Site))).scalars().all()
        sensors_q = await session.execute(select(Sensor))
        sensors = sensors_q.scalars().all()
        for site in sites:
            site_sensors = [s for s in sensors if s.site_id == site.id]
            if not site_sensors:
                continue
            await self._ingest_site_minute(session, site, site_sensors, minute_ts)
        await session.commit()

    async def _ingest_site_minute(
        self,
        session: AsyncSession,
        site: Site,
        sensors: list[Sensor],
        ts: datetime,
    ) -> None:
        # Build unified sensor specs (position for 1-min, fallback_slice for raw)
        specs: dict[str, dict] = {}
        for s in sensors:
            if not s.is_enabled:
                continue
            entry: dict = {"sensor_id": s.id}
            if s.position:
                entry["position"] = s.position
            if s.fallback_slice:
                entry["fallback_slice"] = s.fallback_slice
            specs[s.code] = entry

        # Try each file prefix for the site until one parses
        for prefix in site.file_prefixes or []:
            one_min_path = self.reader.resolve_site_file(prefix, ts)
            raw_path = self.reader.resolve_raw_sensor_file(prefix, ts)
            if one_min_path is None or raw_path is None:
                continue

            default_ts = parse_timestamp_from_filename(one_min_path.name) or ts
            parsed = parse_site_batch(one_min_path, raw_path, specs, default_ts)
            if not parsed:
                continue

            # Persist telemetry + OLA transitions
            await self._persist_site_samples(session, site, sensors, parsed, ts)
            logger.debug(
                "Site %s minute %s: %d sensors parsed", site.code, ts, len(parsed)
            )
            return
        logger.debug("No parseable file for site %s at %s", site.code, ts)

    async def _persist_site_samples(
        self,
        session: AsyncSession,
        site: Site,
        sensors: list[Sensor],
        parsed_by_code: dict,
        ts: datetime,
    ) -> None:
        sensor_by_code = {s.code: s for s in sensors}
        for code, samples in parsed_by_code.items():
            sensor = sensor_by_code.get(code)
            if sensor is None or not samples:
                continue
            sample = samples[-1]  # single latest sample per minute
            is_down = sample.status != "ok"
            reason = sample.status if is_down else "ok"

            # OLA state machine
            await transition_ola(
                session,
                self.sm,
                sensor_id=sensor.id,
                site_id=site.id,
                is_down=is_down,
                ts=ts,
                reason=reason,
            )

            # Upsert telemetry
            await session.execute(
                insert(Telemetry)
                .values(
                    time=ts,
                    sensor_id=sensor.id,
                    value=sample.value,
                    status=sample.status,
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

    # ------------------------------------------------------------------
    async def _rollup_loop(self) -> None:
        """Periodically rebuild daily SLA/OLA rollups."""
        async with AsyncSessionLocal() as session:
            await self._rebuild_rollup(session)
        while not self._stop.is_set():
            try:
                async with AsyncSessionLocal() as session:
                    await self._rebuild_rollup(session)
            except Exception:
                logger.exception("Rollup loop error")
            await asyncio.sleep(settings.rollup_interval_minutes * 60)

    async def _rebuild_rollup(self, session: AsyncSession) -> None:
        days = (datetime.now(timezone.utc) - timedelta(days=45)).date()
        await rebuild_daily_rollups(session, days, datetime.now(timezone.utc).date())


async def build_worker(session: AsyncSession) -> IngestionWorker:
    """Create a worker wired to the configured CDP nodes."""
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
    sm = DowntimeStateMachine()
    await load_open_events(session, sm)
    reader = CdpReader(node_dicts)
    return IngestionWorker(reader, sm)


async def main() -> None:
    """Entry point for ``python -m app.ingestion.worker``."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s - %(message)s",
    )
    async with AsyncSessionLocal() as session:
        worker = await build_worker(session)
    await worker.start()
    logger.info("Ingestion worker running (Ctrl+C to stop)")
    try:
        await asyncio.Event().wait()
    except (KeyboardInterrupt, asyncio.CancelledError):
        pass
    finally:
        await worker.stop()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
