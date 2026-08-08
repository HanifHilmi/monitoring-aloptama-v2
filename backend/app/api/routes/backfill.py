"""Manual backfill endpoints (triggered from the dashboard gear settings).

- ``POST /backfill/cdp``  : Backfill CDP uptime from the oneminute WIDN
  history (file availability per day).
- ``POST /backfill/dcp``  : Backfill DCP (sensor) data from oneminute files.
Both stream progress lines back so the Settings panel shows a live log.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from sqlalchemy import select

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
            start = _parse(settings.backfill_start)
            now = datetime.now(timezone.utc)
            cursor = start
            processed = 0
            while cursor < now:
                one_min = None
                for site in sites:
                    for prefix in site.file_prefixes or []:
                        one_min = reader.resolve_site_file(prefix, cursor)
                        if one_min:
                            break
                    if one_min:
                        break
                available = False
                if one_min and one_min.exists():
                    try:
                        content = one_min.read_text(encoding="utf-8", errors="replace")
                        available = bool(content.strip())
                    except OSError:
                        available = False
                for node in nodes:
                    await session.execute(
                        CdpConnectivity.__table__.insert()
                        .values(time=cursor, cdp_id=node.id, reachable=available, rtt_ms=None)
                        .on_conflict_do_update(
                            index_elements=["time", "cdp_id"],
                            set_={"reachable": available, "error_message": None},
                        )
                    )
                processed += 1
                if processed % 30 == 0:
                    await session.commit()
                    yield _sse(f"CDP backfill {cursor.date()} ...")
                cursor += timedelta(days=1)
            await session.commit()
            yield _sse("CDP backfill COMPLETE")
    except Exception as exc:  # noqa: BLE001
        logger.exception("CDP backfill failed")
        yield _sse(f"ERROR CDP backfill: {exc}")


@router.post("/cdp")
async def backfill_cdp() -> StreamingResponse:
    """Backfill CDP uptime from oneminute file availability."""
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
            start = _parse(settings.backfill_start)
            now = datetime.now(timezone.utc)

            for site in sites:
                site_sensors = [s for s in sensors if s.site_id == site.id]
                sensor_by_code = {s.code: s for s in site_sensors}
                specs = {}
                for s in site_sensors:
                    entry = {}
                    if s.symbol:
                        entry["symbol"] = s.symbol
                    if s.station:
                        entry["station"] = s.station
                    specs[s.code] = entry
                if not specs:
                    continue

                cursor = start
                while cursor < now:
                    one_min = None
                    for prefix in site.file_prefixes or []:
                        one_min = reader.resolve_site_file(prefix, cursor)
                        if one_min and one_min.exists():
                            break
                    if one_min and one_min.exists():
                        default_ts = parse_timestamp_from_filename(one_min.name) or cursor
                        recs = parse_one_minute_file(one_min, specs, default_ts)
                        for rec in recs:
                            for m in rec.metrics:
                                sensor = sensor_by_code[m.sensor_code]
                                await session.execute(
                                    Telemetry.__table__.insert()
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
                    else:
                        # File missing => mark each site sensor metric invalid.
                        for s in site_sensors:
                            if not s.is_enabled:
                                continue
                            await session.execute(
                                Telemetry.__table__.insert()
                                .values(
                                    time=cursor, sensor_id=s.id, metric="missing",
                                    value=None, text_value=None, status="missing",
                                    is_valid=False,
                                )
                                .on_conflict_do_update(
                                    index_elements=["time", "sensor_id", "metric"],
                                    set_={"status": "missing", "is_valid": False},
                                )
                            )
                    cursor += timedelta(days=1)
                    if cursor.minute % 15 == 0:
                        await session.commit()
                await session.commit()
                yield _sse(f"DCP backfill site {site.slug} complete")
            yield _sse("DCP backfill COMPLETE")
    except Exception as exc:  # noqa: BLE001
        logger.exception("DCP backfill failed")
        yield _sse(f"ERROR DCP backfill: {exc}")


@router.post("/dcp")
async def backfill_dcp() -> StreamingResponse:
    """Backfill DCP (sensor) telemetry from oneminute WIDN files."""
    return StreamingResponse(
        _stream_dcp(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )