"""Manual backfill endpoints (Settings -> Backfill).

- ``POST /backfill/cdp``: SLA from the oneminute WIDN files at FULL
  1-minute resolution, filling BACKWARDS from now -> backfill_start so the
  most recent data lands first. For every minute it checks whether the
  matching oneminute file actually contains that minute's row; writes one
  CdpConnectivity row per minute (reachable = row present). Missing minute
  => downtime. Per-day logs show minutes-up/total and the source file.
- ``POST /backfill/dcp``: DCP/sensor telemetry from the same files. Each
  day runs in its own try/except + commit so one corrupt file logs an
  ERROR line and the stream keeps going instead of dying.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert

from app.core.config import settings
from app.db.session import AsyncSessionLocal
from app.ingestion.cdp_reader import CdpReader
from app.ingestion.parsers import parse_one_minute_file, parse_timestamp_from_filename
from app.models import CdpConnectivity, CdpNode, Sensor, Site, Telemetry

router = APIRouter(prefix="/backfill", tags=["backfill"])
logger = logging.getLogger(__name__)


def _sse(line: str) -> str:
    return f"data: {line}\n\n"


def _parse(value: str) -> datetime:
    if value.endswith("Z"):
        value = value[:-1] + "+00:00"
    return datetime.fromisoformat(value).astimezone(timezone.utc)


def _day_lines(down_to: datetime) -> int:
    """Iterate DAYS backwards from now (inclusive) down to `down_to`."""
    now = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    down = down_to.replace(hour=0, minute=0, second=0, microsecond=0)
    if down > now:
        return 0
    return int((now - down).total_seconds() // 86400) + 1


async def _stream_cdp():
    try:
        async with AsyncSessionLocal() as session:
            nodes = (await session.execute(select(CdpNode))).scalars().all()
            sites = (await session.execute(select(Site))).scalars().all()
            reader = CdpReader(
                [
                    {"id": n.id, "name": n.name, "ip_address": str(n.ip_address),
                     "mount_path": n.mount_path, "role": n.role}
                    for n in nodes
                ]
            )
            target = _parse(settings.backfill_start).replace(second=0, microsecond=0)
            total_rows = 0

            # Iterate backwards from today down to the target date.
            cur = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
            target_day = target.replace(hour=0, minute=0, second=0, microsecond=0)
            while cur >= target_day:
                # For the current day, scan minutes backwards from end-of-day.
                day_end = min(cur + timedelta(days=1), datetime.now(timezone.utc))
                # Resolve the day's oneminute file (universal station file).
                one_min = None
                for site in sites:
                    for prefix in site.file_prefixes or []:
                        one_min = reader.resolve_site_file(prefix, cur)
                        if one_min and one_min.exists():
                            break
                    if one_min and one_min.exists():
                        break
                src = one_min.name if one_min and one_min.exists() else None

                # Minutes actually present in the file.
                present: set[datetime] = set()
                if src:
                    try:
                        for rec in parse_one_minute_file(one_min, {}, cur):
                            present.add(rec.ts.replace(second=0, microsecond=0))
                    except Exception as exc:  # noqa: BLE001
                        logger.error("CDP backfill parse error %s: %s", src, exc)
                        present = set()

                minutes_up = 0
                # Iterate minutes backwards within the day.
                minute = day_end.replace(second=0, microsecond=0)
                first_min = cur
                while minute > first_min:
                    minute -= timedelta(minutes=1)
                    if minute < target:
                        break
                    reachable = minute in present
                    if reachable:
                        minutes_up += 1
                    for node in nodes:
                        await session.execute(
                            insert(CdpConnectivity)
                            .values(time=minute, cdp_id=node.id,
                                    reachable=reachable, rtt_ms=None)
                            .on_conflict_do_update(
                                index_elements=["time", "cdp_id"],
                                set_={"reachable": reachable, "error_message": None},
                            )
                        )
                    total_rows += len(nodes)

                await session.commit()
                day_minutes = int(min(day_end, datetime.now(timezone.utc)) % (24 * 60) // 1) or 0
                total_minutes = max(1, int((min(day_end, datetime.now(timezone.utc)) - cur).total_seconds() // 60))
                logger.info(
                    "CDP backfill day=%s up=%d/%d src=%s",
                    cur.date(), minutes_up, total_minutes, src,
                )
                yield _sse(
                    f"CDP backfill {cur.date()} up={minutes_up}/{total_minutes} src={src or 'MISSING'}"
                )
                cur -= timedelta(days=1)

            logger.info("CDP backfill complete (%d connectivity rows)", total_rows)
            yield _sse(f"CDP backfill COMPLETE rows={total_rows}")
    except Exception as exc:  # noqa: BLE001
        logger.exception("CDP backfill failed")
        yield _sse(f"ERROR CDP backfill: {exc}")


@router.post("/cdp")
async def backfill_cdp() -> StreamingResponse:
    return StreamingResponse(
        _stream_cdp(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


async def _stream_dcp():
    try:
        async with AsyncSessionLocal() as session:
            yield _sse("DCP backfill started")
            nodes = (await session.execute(select(CdpNode))).scalars().all()
            reader = CdpReader(
                [
                    {"id": n.id, "name": n.name, "ip_address": str(n.ip_address),
                     "mount_path": n.mount_path, "role": n.role}
                    for n in nodes
                ]
            )
            sites = (await session.execute(select(Site))).scalars().all()
            sensors = (await session.execute(select(Sensor))).scalars().all()
            target = _parse(settings.backfill_start).replace(second=0, microsecond=0)
            total_metric_rows = 0

            for site in sites:
                site_sensors = [s for s in sensors if s.site_id == site.id]
                sensor_by_code = {s.code: s for s in site_sensors}
                specs = {}
                for s in site_sensors:
                    specs[s.code] = {"station": s.station or "04"}
                if not specs:
                    continue

                # Fill backwards per day, from today down to target.
                cur = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
                target_day = target.replace(hour=0, minute=0, second=0, microsecond=0)
                while cur >= target_day:
                    day_end = min(cur + timedelta(days=1), datetime.now(timezone.utc))
                    one_min = None
                    for prefix in site.file_prefixes or []:
                        one_min = reader.resolve_site_file(prefix, cur)
                        if one_min and one_min.exists():
                            break
                    src = one_min.name if one_min and one_min.exists() else None
                    try:
                        minutes = 0
                        metric_rows = 0
                        if src:
                            default_ts = parse_timestamp_from_filename(one_min.name) or cur
                            recs = parse_one_minute_file(one_min, specs, default_ts)
                            minutes = len(recs)
                            for rec in recs:
                                for m in rec.metrics:
                                    sensor = sensor_by_code.get(m.sensor_code)
                                    if sensor is None:
                                        continue
                                    await session.execute(
                                        insert(Telemetry)
                                        .values(
                                            time=rec.ts, sensor_id=sensor.id,
                                            metric=m.metric, value=m.value,
                                            text_value=m.text_value,
                                            status="ok" if m.is_valid else "invalid",
                                            is_valid=m.is_valid,
                                        )
                                        .on_conflict_do_update(
                                            index_elements=["time", "sensor_id", "metric"],
                                            set_={
                                                "value": m.value,
                                                "text_value": m.text_value,
                                                "status": "ok" if m.is_valid else "invalid",
                                                "is_valid": m.is_valid,
                                            },
                                        )
                                    )
                                    metric_rows += 1
                        else:
                            # No file -> mark each sensor metric missing per minute.
                            minute = day_end.replace(second=0, microsecond=0)
                            first_min = cur
                            while minute > first_min:
                                minute -= timedelta(minutes=1)
                                if minute < target:
                                    break
                                minutes += 1
                                for s in site_sensors:
                                    if not s.is_enabled:
                                        continue
                                    await session.execute(
                                        insert(Telemetry)
                                        .values(time=minute, sensor_id=s.id, metric="missing",
                                                value=None, text_value=None, status="missing",
                                                is_valid=False)
                                        .on_conflict_do_update(
                                            index_elements=["time", "sensor_id", "metric"],
                                            set_={"status": "missing", "is_valid": False},
                                        )
                                    )
                                    metric_rows += 1
                        total_metric_rows += metric_rows
                        await session.commit()
                        logger.info(
                            "DCP backfill site=%s day=%s minutes=%d metric_rows=%d src=%s",
                            site.slug, cur.date(), minutes, metric_rows, src,
                        )
                        yield _sse(
                            f"DCP site {site.slug} {cur.date()} minutes={minutes} rows={metric_rows} src={src or 'MISSING'}"
                        )
                    except Exception as exc:  # noqa: BLE001
                        await session.rollback()
                        logger.error("DCP backfill error site=%s day=%s: %s", site.slug, cur.date(), exc)
                        yield _sse(f"ERROR DCP backfill site={site.slug} day={cur.date()} : {exc}")
                    cur -= timedelta(days=1)

            logger.info("DCP backfill complete (%d metric rows)", total_metric_rows)
            yield _sse(f"DCP backfill COMPLETE rows={total_metric_rows}")
    except Exception as exc:  # noqa: BLE001
        logger.exception("DCP backfill failed")
        yield _sse(f"ERROR DCP backfill: {exc}")


@router.post("/dcp")
async def backfill_dcp() -> StreamingResponse:
    return StreamingResponse(
        _stream_dcp(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )