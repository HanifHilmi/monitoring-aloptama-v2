"""Manual backfill endpoints (Settings -> Backfill).

- ``POST /backfill/cdp``: SLA from the oneminute WIDN files at FULL
  1-minute resolution, filling BACKWARDS from now -> backfill_start so the
  most recent data lands first. Per minute it checks whether the matching
  oneminute file contains that minute's row; writes one CdpConnectivity
  row per minute (reachable = row present). Missing minute => downtime.
  Per-day logs show minutes-up/total and the source file.
- ``POST /backfill/dcp``: DCP/sensor telemetry from the same files, per-day
  try/except + commit so one corrupt file logs an ERROR and the stream
  continues.
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
from app.models import AwosMetrics, CdpConnectivity, CdpNode, Sensor, Site

router = APIRouter(prefix="/backfill", tags=["backfill"])
logger = logging.getLogger(__name__)


def _sse(line: str) -> str:
    return f"data: {line}\n\n"


def _parse(value: str) -> datetime:
    if value.endswith("Z"):
        value = value[:-1] + "+00:00"
    return datetime.fromisoformat(value).astimezone(timezone.utc)


def _day_start(dt: datetime) -> datetime:
    return dt.replace(hour=0, minute=0, second=0, microsecond=0)


def _resolve_day_file(reader, sites, day: datetime):
    """Return (path|None, name|None) of the day's universal oneminute file."""
    for site in sites:
        for prefix in site.file_prefixes or []:
            p = reader.resolve_site_file(prefix, day)
            if p and p.exists():
                return p, p.name
    return None, None


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
            target_day = _day_start(target)
            now = datetime.now(timezone.utc)
            total_rows = 0

            # Fill backwards: today -> target.
            cur_day = _day_start(now)
            while cur_day >= target_day:
                day_start = cur_day
                day_end = min(cur_day + timedelta(days=1), now)

                one_min, src = _resolve_day_file(reader, sites, cur_day)
                present: set[datetime] = set()
                if one_min is not None:
                    try:
                        for rec in parse_one_minute_file(one_min, {}, cur_day):
                            present.add(rec.ts.replace(second=0, microsecond=0))
                    except Exception as exc:  # noqa: BLE001
                        logger.error("CDP backfill parse error %s: %s", src, exc)
                        present = set()

                minutes_up = 0
                total_minutes = max(1, int((day_end - day_start).total_seconds() // 60))
                minute = day_end.replace(second=0, microsecond=0)
                while minute > day_start:
                    minute -= timedelta(minutes=1)
                    if minute < target:
                        continue
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
                logger.info("CDP backfill day=%s up=%d/%d src=%s",
                            cur_day.date(), minutes_up, total_minutes, src)
                yield _sse(
                    f"CDP backfill {cur_day.date()} up={minutes_up}/{total_minutes} src={src or 'MISSING'}"
                )
                cur_day -= timedelta(days=1)

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
            target_day = _day_start(target)
            now = datetime.now(timezone.utc)
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
                cur_day = _day_start(now)
                while cur_day >= target_day:
                    day_start = cur_day
                    day_end = min(cur_day + timedelta(days=1), now)
                    one_min, src = _resolve_day_file(reader, [site], cur_day)
                    try:
                        minutes = 0
                        metric_rows = 0
                        if one_min is not None:
                            default_ts = parse_timestamp_from_filename(one_min.name) or cur_day
                            recs = parse_one_minute_file(one_min, specs, default_ts)
                            minutes = len(recs)
                            for rec in recs:
                                for m in rec.metrics:
                                    sensor = sensor_by_code.get(m.sensor_code)
                                    if sensor is None:
                                        continue
                                    await session.execute(
                                        insert(AwosMetrics)
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
                            while minute > day_start:
                                minute -= timedelta(minutes=1)
                                if minute < target:
                                    break
                                minutes += 1
                                for s in site_sensors:
                                    if not s.is_enabled:
                                        continue
                                    await session.execute(
                                        insert(AwosMetrics)
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
                            site.slug, cur_day.date(), minutes, metric_rows, src,
                        )
                        yield _sse(
                            f"DCP site {site.slug} {cur_day.date()} minutes={minutes} rows={metric_rows} src={src or 'MISSING'}"
                        )
                    except Exception as exc:  # noqa: BLE001
                        await session.rollback()
                        logger.error("DCP backfill error site=%s day=%s: %s", site.slug, cur_day.date(), exc)
                        yield _sse(f"ERROR DCP backfill site={site.slug} day={cur_day.date()} : {exc}")
                    cur_day -= timedelta(days=1)

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

# ----------------------------------------------------------------------
# Background backfill jobs (server-side, independent of the browser).
# POST /backfill/{kind}/start returns a job_id immediately; the work runs
# as an asyncio task in the backend process so a page refresh never stops
# it.  GET /backfill/job/{job_id}/stream replays the log lines (SSE).
# ----------------------------------------------------------------------
import asyncio
import asyncio as _asyncio

_JOBS: dict[str, dict] = {}   # job_id -> {kind, status, lines[]}
_job_counter = 0


async def _run_job(job_id: str, kind: str) -> None:
    _JOBS[job_id]["status"] = "running"
    gens = [_stream_cdp(), _stream_dcp()] if kind == "all" else ([_stream_cdp()] if kind == "cdp" else [_stream_dcp()])

    async def _drain(label: str, gen) -> None:
        try:
            async for line in gen:
                _JOBS[job_id]["lines"].append(line)
            _JOBS[job_id]["lines"].append(f"{label} COMPLETE")
        except Exception as exc:  # noqa: BLE001
            _JOBS[job_id]["lines"].append(f"{label} ERROR: {exc}")

    try:
        # Run all streams CONCURRENTLY (CDP + DCP at the same time) so the
        # combined backfill isn't serial, and to avoid greenlet_spawn issues
        # from chaining async generators in one task.
        if kind == "all":
            await asyncio.gather(
                _drain("CDP backfill", gens[0]),
                _drain("DCP backfill", gens[1]),
            )
        else:
            await _drain("Backfill", gens[0])
        _JOBS[job_id]["status"] = "done"
    except Exception as exc:  # noqa: BLE001
        _JOBS[job_id]["lines"].append(f"ERROR: {exc}")
        _JOBS[job_id]["status"] = "error"


def _new_job(kind: str) -> str:
    global _job_counter
    _job_counter += 1
    job_id = f"{kind}-{_job_counter}"
    _JOBS[job_id] = {"kind": kind, "status": "pending", "lines": []}
    _asyncio.get_running_loop().create_task(_run_job(job_id, kind))
    return job_id


@router.post("/{kind}/start", tags=["backfill"])
async def start_backfill(kind: str) -> dict:
    if kind not in ("cdp", "dcp", "all"):
        return {"ok": False, "error": "kind must be cdp or dcp"}
    job_id = _new_job(kind)
    return {"ok": True, "job_id": job_id}


@router.get("/job/{job_id}", tags=["backfill"])
async def backfill_job_status(job_id: str) -> dict:
    job = _JOBS.get(job_id)
    if job is None:
        return {"ok": False, "error": "job not found"}
    return {"job_id": job_id, "status": job["status"], "lines": job["lines"]}


@router.get("/job/{job_id}/stream", tags=["backfill"])
async def backfill_job_stream(job_id: str) -> StreamingResponse:
    async def gen():
        job = _JOBS.get(job_id)
        if job is None:
            yield _sse("ERROR job not found")
            return
        # Replay what has been captured so far, then tail new lines.
        idx = 0
        while True:
            while idx < len(job["lines"]):
                yield job["lines"][idx]
                idx += 1
            if job["status"] in ("done", "error"):
                yield _sse(f"JOB {job['status'].upper()}")
                return
            await _asyncio.sleep(1)

    return StreamingResponse(gen(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})
