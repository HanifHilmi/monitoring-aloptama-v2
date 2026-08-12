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
from app.ingestion.components import row_dcp_online, site_components, wide_row_components
from app.ingestion.parsers import parse_site_batch, parse_timestamp_from_filename
from app.ingestion.state_machine import (
    DowntimeStateMachine,
    load_open_events,
    transition_ola,
    transition_ola_component,
    transition_sla,
)
from app.models import (
    AwosMetrics,
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
        self._watermarks: dict[str, datetime] = {}

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
                    await self._check_cdps(session, persist=(
                        last_persist is None
                        or (datetime.now(timezone.utc) - last_persist).total_seconds() >= 60
                    ))
                    if last_persist is None or (datetime.now(timezone.utc) - last_persist).total_seconds() >= 60:
                        last_persist = datetime.now(timezone.utc)
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

    # Wide-row metric -> awos_metrics column mapping (value vs text).
    _WIDE_COLUMNS = {
        "TEMP": ("temp_c", False), "DEWP": ("dewp_c", False), "RH": ("rh_pct", False),
        "QNH": ("qnh_hpa", False), "DA": ("da_ft", False),
        "WS": ("wind_speed_kt", False), "WD": ("wind_dir_deg", False),
        "WGS": ("gust_speed_kt", False), "WGD": ("gust_dir_deg", False),
        "RVR": ("rvr_m", False), "VIS": ("vis_m", False), "ALS": ("als_cd", False),
        "D/N": ("als_dn", True), "RLS": ("rls", False),
        "LR1": ("lr1_100ft", False), "SKY": ("sky_condition", True),
        "RA": ("precip_mm", False), "PW": ("present_weather", True),
        "SOL": ("solar_wm2", False), "LTX": ("lightning", True),
    }

    @staticmethod
    def _group_wide(parsed_by_code: dict, site_id: str) -> list[dict]:
        """Collapse EAV metrics into one wide row per (minute, site)."""
        rows: dict = {}
        for code, metrics in (parsed_by_code or {}).items():
            for m in metrics or []:
                if not m.is_valid or m.ts is None:
                    continue
                col = IngestionWorker._WIDE_COLUMNS.get(m.metric)
                if not col:
                    continue
                column, is_text = col
                key = m.ts.replace(second=0, microsecond=0)
                row = rows.setdefault(key, {"time": key, "site_id": site_id})
                if is_text:
                    # Empty text field = healthy, no event -> empty string.
                    row[column] = (m.text_value or "")
                else:
                    # Empty numeric field = healthy -> 0. Explicit missing is
                    # skipped above (is_valid False) so the column stays NULL.
                    row[column] = m.value if m.value is not None else 0
        # WGS/WGD are tied to WS/WD: if wind is missing (///) the sensor is
        # OFFLINE -> gust = NULL. If wind is ONLINE/valid, gust is 0 when the
        # WGS/WGD fields are missing or empty (offline WGS/WGD columns parse
        # to None and are skipped above, so default them to 0 here).
        for row in rows.values():
            wind_ok = row.get("wind_speed_kt") is not None and row.get("wind_dir_deg") is not None
            if not wind_ok:
                row["gust_speed_kt"] = None
                row["gust_dir_deg"] = None
            else:
                if row.get("gust_speed_kt") is None:
                    row["gust_speed_kt"] = 0
                if row.get("gust_dir_deg") is None:
                    row["gust_dir_deg"] = 0
        return list(rows.values())

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
        sensor_nodes: dict[str, Sensor] = {}
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
            sensor_nodes[s.code] = s

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
            r for r in self._group_wide(parsed, site.slug)
            if r["time"] > watermark and r["time"] <= now
        ]
        if not rows:
            return

        # NEW OLA source: per-(site, component) validity from wide rows.
        present: set[str] = set()
        for r in rows:
            for comp in wide_row_components(r):
                present.add(comp)
                await transition_ola_component(
                    session, self.sm, site_id=site.id, component_code=comp,
                    is_down=False, ts=r["time"],
                )
            if row_dcp_online(r):
                present.add("DCP")
        # Open OLA downtime only for configured components missing this minute.
        for comp in site_components(site.slug):
            if comp not in present:
                await transition_ola_component(
                    session, self.sm, site_id=site.id, component_code=comp,
                    is_down=True, ts=now,
                )

        await self._persist_site_samples(session, site, sensor_nodes, parsed, now)
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

    async def _ingest_site_minute(
        self,
        session: AsyncSession,
        site: Site,
        sensors: list[Sensor],
        ts: datetime,
    ) -> None:
        # Build unified sensor specs (WIDN symbol/station for column mapping)
        specs: dict[str, dict] = {}
        sensor_nodes: dict[str, Sensor] = {}
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
            sensor_nodes[s.code] = s

        # Resolve the TARGET-DAY oneminute file only (live, no backfill).
        one_min_path = None
        for prefix in site.file_prefixes or []:
            p = self.reader.resolve_site_file(prefix, ts)
            if p and p.exists():
                one_min_path = p
                break
        if one_min_path is None:
            logger.debug("No oneminute file for site %s at %s", site.code, ts)
            return

        default_ts = parse_timestamp_from_filename(one_min_path.name) or ts
        parsed = parse_site_batch(one_min_path, None, specs, default_ts)
        if not parsed:
            logger.debug("No parseable file for site %s at %s", site.code, ts)
            return

        # Persist telemetry + OLA transitions
        await self._persist_site_samples(session, site, sensor_nodes, parsed, ts)
        logger.debug(
            "Site %s minute %s: %d sensors parsed", site.code, ts, len(parsed)
        )

    async def _persist_site_samples(
        self,
        session: AsyncSession,
        site: Site,
        sensor_nodes: dict[str, Sensor],
        parsed_by_code: dict,
        ts: datetime,
    ) -> None:
        for code, metrics in parsed_by_code.items():
            sensor = sensor_nodes.get(code)
            if sensor is None or not metrics:
                continue
            # A sensor is UP (OLA) for the minute if any metric is valid.
            valid_count = sum(1 for m in metrics if m.is_valid)
            total_count = len(metrics)
            is_down = valid_count == 0
            reason = "missing" if is_down else "ok"

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

            # Upsert telemetry — one row per metric (WIDN multi-metric).
            for m in metrics:
                await session.execute(
                    insert(Telemetry)
                    .values(
                        time=ts,
                        sensor_id=sensor.id,
                        metric=m.metric,
                        value=m.value,
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
