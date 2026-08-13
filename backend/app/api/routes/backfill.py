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
import asyncio as _asyncio
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert

from app.core.config import settings
from app.services.backfill import _group_wide_static, _wide_upsert
from app.db.session import AsyncSessionLocal
from app.ingestion.cdp_reader import CdpReader
from app.ingestion.parsers import parse_one_minute_file, parse_timestamp_from_filename
from app.models import AwosMetrics, CdpConnectivity, CdpNode, Sensor, Site

router = APIRouter(prefix="/backfill", tags=["backfill"])
logger = logging.getLogger(__name__)
_JOBS: dict[str, dict] = {}
_job_counter = 0



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


async def _stream_all():
    """Combined CDP + DCP backfill. For EACH day it resolves the shared
    091 WIDN file ONCE, then in a SINGLE session writes:
      - cdp_connectivity (per CDP node up/down for that minute),
      - awos_metrics wide rows per site (with dedupe: skips minutes already
        present). Yields a verbose per-day line after commit/close."""
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
        one_min, src = _resolve_day_file(reader, sites, cur_day)

        # SESSION PER DAY: same file -> both CDP and awos writes.
        async with AsyncSessionLocal() as session:
            # timestamps present in the file for this day
            present: set = set()
            if one_min is not None:
                try:
                    for rec in parse_one_minute_file(one_min, {}, cur_day):
                        present.add(rec.ts.replace(second=0, microsecond=0))
                except Exception as exc:  # noqa: BLE001
                    logger.error("DCP backfill parse error %s: %s", src, exc)
            minutes_up = 0
            total_minutes = max(1, int((day_end-day_start).total_seconds()//60))
            minute = day_end.replace(second=0, microsecond=0)
            # CDP: per-node connectivity
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
            # DCP: awos per site, dedupe per minute
            site_rows: dict[str, int] = {}
            site_skip: dict[str, int] = {}
            if one_min is not None:
                default_ts = parse_timestamp_from_filename(one_min.name) or cur_day
                for site in sites:
                    site_sensors = [x for x in sensors if x.site_id == site.id]
                    if not site_sensors:
                        continue
                    specs = {x.code: {"station": x.station or "04"}
                             for x in site_sensors if x.is_enabled}
                    if not specs:
                        continue
                    recs = parse_one_minute_file(one_min, specs, default_ts)
                    for rec in recs:
                        rec_min = rec.ts.replace(second=0, microsecond=0)
                        if rec_min < target or rec_min > day_end:
                            continue
                        exists = (await session.execute(
                            select(func.count()).select_from(AwosMetrics).where(
                                AwosMetrics.time == rec_min, AwosMetrics.site_id == site.slug
                            )
                        )).scalar_one() > 0
                        if exists:
                            site_skip[site.slug] = site_skip.get(site.slug, 0) + 1
                            continue
                        batch = {}
                        for mx in rec.metrics:
                            batch.setdefault(mx.sensor_code, []).append(mx)
                        for r in _group_wide_static(batch, site.slug):
                            if r["time"] != rec_min:
                                continue
                            await session.execute(_wide_upsert(r))
                            site_rows[site.slug] = site_rows.get(site.slug, 0) + 1
            await session.commit()

        per_site = " ".join(f"{k}={v}" for k, v in sorted(site_rows.items())) or "none"
        skip_sum = sum(site_skip.values())
        yield _sse(
            f"BACKFILL {cur_day.date()} src={src or 'MISSING'} "
            f"cdp_up={minutes_up}/{total_minutes} awos_rows=[{per_site}] "
            f"skipped={skip_sum}"
        )
        cur_day -= timedelta(days=1)


async def _run_job(job_id: str, kind: str) -> None:
    _JOBS[job_id]["status"] = "running"
    gen = _stream_all()
    try:
        async for line in gen:
            _JOBS[job_id]["lines"].append(line)
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
    if kind != "all":
        return {"ok": False, "error": "kind must be all"}
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
