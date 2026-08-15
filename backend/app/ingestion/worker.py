"""Background ingestion worker.

Responsibilities:
- Periodically probe CDP nodes (active-passive failover via ``CdpReader``).
- Ingest 1-minute telemetry logs (with raw-DCP fallback).

SLA/OLA is computed by the API layer directly from the raw
``cdp_connectivity`` and ``awos_metrics`` hypertables using SQL
``COUNT(*) FILTER`` aggregates; this worker never materializes downtime
events or rollups.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.session import AsyncSessionLocal
from app.ingestion.cdp_reader import CdpReader
from app.ingestion.components import group_wide
from app.ingestion.parsers import parse_site_batch, parse_timestamp_from_filename
from app.models import AwosMetrics, CdpConnectivity, CdpNode, Sensor, Site

logger = logging.getLogger(__name__)


class IngestionWorker:
    """Long-running async ingestion loop."""

    def __init__(self, reader: CdpReader):
        self.reader = reader
        self._stop = asyncio.Event()
        self._tasks: list[asyncio.Task] = []
        self._watermarks: dict[str, datetime] = {}

    # ------------------------------------------------------------------
    async def start(self) -> None:
        """Launch all background loops."""
        logger.info("Starting ingestion worker")
        self._tasks = [
            asyncio.create_task(self._cdp_loop(), name="cdp-loop"),
            asyncio.create_task(self._telemetry_loop(), name="telemetry-loop"),
        ]

    async def stop(self) -> None:
        self._stop.set()
        for t in self._tasks:
            t.cancel()
        await asyncio.gather(*self._tasks, return_exceptions=True)

    # ------------------------------------------------------------------
    async def _cdp_loop(self) -> None:
        """Probe node connectivity live (fast), persist to DB on a 1-min cadence.

        Probes every ``cdps_check_interval_seconds`` (default 15s so the
        dashboard shows near-instant online/offline), but only upserts a
        ``cdp_connectivity`` row once per minute (aligned with /oneminute
        backfill granularity) so SLA history stays 1-minute synced.
        """
        last_persist: Optional[datetime] = None
        while not self._stop.is_set():
            try:
                async with AsyncSessionLocal() as session:
                    now = datetime.now(timezone.utc)
                    persist = (
                        last_persist is None
                        or (now - last_persist).total_seconds() >= 60
                    )
                    await self._check_cdps(session, persist=persist)
                    if persist:
                        last_persist = now
            except Exception:
                logger.exception("CDP check loop error")
            await asyncio.sleep(settings.cdps_check_interval_seconds)

    async def _check_cdps(self, session: AsyncSession, persist: bool = True) -> None:
        nodes = (await session.execute(select(CdpNode))).scalars().all()
        if not nodes:
            return
        # Probe ALL nodes exactly once (fast, updates live state).
        await self.reader.check_all()
        if not persist:
            return
        ts = datetime.now(timezone.utc)
        for n in nodes:
            await self._persist_cdp_sample(session, n, ts)
        await session.commit()

    async def _persist_cdp_sample(
        self, session: AsyncSession, node: CdpNode, ts: datetime
    ) -> None:
        state = self.reader.state.nodes.get(node.name)
        if state is None:
            return
        reachable = state.reachable

        # Persist connectivity sample (1-minute cadence)
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
        sites = (await session.execute(select(Site))).scalars().all()
        sensors_q = await session.execute(select(Sensor))
        sensors = sensors_q.scalars().all()
        for site in sites:
            site_sensors = [s for s in sensors if s.site_id == site.id]
            if not site_sensors:
                continue
            # WATERMARK: only ingest minutes strictly after the stored MAX.
            watermark = (
                await session.execute(
                    select(func.max(AwosMetrics.time)).where(
                        AwosMetrics.site_id == site.slug
                    )
                )
            ).scalar_one()
            if watermark is None:
                watermark = datetime.combine(now.date(), datetime.min.time(), tzinfo=timezone.utc)
            self._watermarks[site.slug] = watermark
            await self._ingest_site_watermark(session, site, site_sensors, watermark, now)
        await session.commit()

    async def _ingest_site_watermark(
        self,
        session: AsyncSession,
        site: Site,
        sensors: list[Sensor],
        watermark: datetime,
        now: datetime,
    ) -> None:
        # Build unified sensor specs (WIDN symbol/station for column mapping).
        specs: dict[str, dict] = {}
        for s in sensors:
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

        # Resolve the TARGET-DAY oneminute file only (live; no old-day replay).
        one_min_path = None
        for prefix in site.file_prefixes or []:
            p = self.reader.resolve_site_file(prefix, now)
            if p and p.exists():
                one_min_path = p
                break
        if one_min_path is None:
            logger.debug("No oneminute file for site %s at %s", site.code, now)
            return

        default_ts = parse_timestamp_from_filename(one_min_path.name) or now
        parsed = parse_site_batch(one_min_path, None, specs, default_ts)
        if not parsed:
            logger.debug("No parseable file for site %s at %s", site.code, now)
            return

        # WATERMARK: keep minutes strictly > the stored max (grabs delayed
        # minutes naturally) and not in the future.
        rows = [
            r for r in group_wide(parsed, site.slug)
            if r["time"] > watermark and r["time"] <= now
        ]
        if not rows:
            return

        await self._persist_site_wide(session, rows)
        logger.debug(
            "Site %s watermark %s -> uploaded %d wide minutes",
            site.code, watermark.isoformat(), len(rows),
        )

    async def _persist_site_wide(self, session: AsyncSession, rows: list[dict]) -> None:
        """Bulk upsert wide rows (time, site_id PK) in ONE statement."""
        if not rows:
            return
        columns = [c for c in rows[0].keys() if c in ("time", "site_id")] + [
            c for c in rows[0].keys() if c not in ("time", "site_id")
        ]
        values = [{c: r.get(c) for c in columns} for r in rows]
        insert_stmt = insert(AwosMetrics)
        upsert = insert_stmt.values(values).on_conflict_do_update(
            index_elements=["time", "site_id"],
            set_={
                c: getattr(insert_stmt.excluded, c)
                for c in columns if c not in ("time", "site_id")
            },
        )
        await session.execute(upsert)


async def build_worker(session: AsyncSession) -> IngestionWorker:
    """Create a worker wired to the configured CDP nodes."""
    # Wait for the schema to exist — the backend may still be applying a
    # RESET_DB_ON_BOOT (drop public schema) when this container starts.
    for attempt in range(60):
        try:
            nodes = (await session.execute(select(CdpNode))).scalars().all()
            break
        except Exception:
            if attempt == 59:
                raise
            await asyncio.sleep(2)
            await session.rollback()
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
    return IngestionWorker(reader)


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
