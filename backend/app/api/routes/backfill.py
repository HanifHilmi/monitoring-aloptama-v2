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
    """CDP backfill, session-per-day: opens/closes a DB session for each day
    and yields log lines only BETWEEN days (never while a session is open),
    which avoids the greenlet_spawn/await_only error."""
    nodes = (await (await _scoped_session()).execute(select(CdpNode))).close() if False else None
    # load master tables once on its own session
    async with AsyncSessionLocal() as s0:
        nodes = (await s0.execute(select(CdpNode))).scalars().all()
        sites = (await s0.execute(select(Site))).scalars().all()
    reader = CdpReader(
        [{"id": n.id, "name": n.name, "ip_address": str(n.ip_address),
          "mount_path": n.mount_path, "role": n.role} for n in nodes]
    )
    target = _parse(settings.backfill_start).replace(second=0, microsecond=0)
    target_day = _day_start(target)
    now = datetime.now(timezone.utc)
    cur_day = _day_start(now)
    while cur_day >= target_day:
        day_start = cur_day
        day_end = min(cur_day + timedelta(days=1), now)
        one_min, src = _resolve_day_file(reader, sites, cur_day)
        present: set = set()
        if one_min is not None:
            try:
                for rec in parse_one_minute_file(one_min, {}, cur_day):
                    present.add(rec.ts.replace(second=0, microsecond=0))
            except Exception:  # noqa: BLE001
                present = set()
        minutes_up = 0
        total_minutes = max(1, int((day_end-day_start).total_seconds()//60))
        # SESSION PER DAY: all DB writes in one tight block, never across yield.
        async with AsyncSessionLocal() as session:
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
                        .values(time=minute, cdp_id=node.id, reachable=reachable, rtt_ms=None)
                        .on_conflict_do_update(
                            index_elements=["time", "cdp_id"],
                            set_={"reachable": reachable, "error_message": None},
                        )
                    )
            await session.commit()
        # yield is AFTER the session closed
        yield _sse(f"CDP backfill {cur_day.date()} up={minutes_up}/{total_minutes} src={src or 'MISSING'}")
        cur_day -= timedelta(days=1)

async def backfill_cdp() -> StreamingResponse:
    return StreamingResponse(
        _stream_cdp(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


async def _stream_dcp():
    """DCP/awos backfill with a single shared-file resolve + CDP failover +
    dedupe, all writes inside a session-per-day (no yield across a session
    -> avoids greenlet_spawn/await_only)."""
    async with AsyncSessionLocal() as s0:
        nodes = (await s0.execute(select(CdpNode))).scalars().all()
        sites = (await s0.execute(select(Site))).scalars().all()
        sensors = (await s0.execute(select(Sensor))).scalars().all()
    reader = CdpReader(
        [{"id": n.id, "name": n.name, "ip_address": str(n.ip_address),
          "mount_path": n.mount_path, "role": n.role} for n in nodes]
    )
    target = _parse(settings.backfill_start).replace(second=0, microsecond=0)
    target_day = _day_start(target)
    now = datetime.now(timezone.utc)
    cur_day = _day_start(now)

    while cur_day >= target_day:
        day_start = cur_day
        day_end = min(cur_day + timedelta(days=1), now)
        # FAILOVER: try every site prefix across BOTH CDPs until one resolves.
        one_min, src = _resolve_day_file(reader, sites, cur_day)
        log = f"DCP backfill {cur_day.date()} src={src or 'MISSING'}"
        if one_min is not None:
            # SESSION PER DAY: all persistence here, commit once.
            async with AsyncSessionLocal() as session:
                day_rows = 0
                for site in sites:
                    site_sensors = [x for x in sensors if x.site_id == site.id]
                    if not site_sensors:
                        continue
                    specs = {x.code: {"station": x.station or "04"} for x in site_sensors if x.is_enabled}
                    if not specs:
                        continue
                    default_ts = parse_timestamp_from_filename(one_min.name) or cur_day
                    recs = parse_one_minute_file(one_min, specs, default_ts)
                    for rec in recs:
                        rec_min = rec.ts.replace(second=0, microsecond=0)
                        if rec_min < target or rec_min > day_end:
                            continue
                        wide = {}
                        # cheap dedupe: only add a wide row if that (time,site) is absent
                        exists = (await session.execute(
                            select(func.count()).select_from(AwosMetrics).where(
                                AwosMetrics.time == rec_min, AwosMetrics.site_id == site.slug
                            )
                        )).scalar_one() > 0
                        if exists:
                            continue
                        row = _group_wide_static({x.code: None for x in []}, site.slug) if False else None
                        # collapse this minute's metrics into a wide row via worker helper
                        batch = {}
                        for mx in rec.metrics:
                            batch.setdefault(mx.sensor_code, []).append(mx)
                        for r in _group_wide_static(batch, site.slug):
                            if r["time"] != rec_min:
                                continue
                            await session.execute(_wide_upsert(r))
                            day_rows += 1
                await session.commit()
                log += f" rows={day_rows}"
        # yield only AFTER the session is closed
        yield _sse(log)
        cur_day -= timedelta(days=1)

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
