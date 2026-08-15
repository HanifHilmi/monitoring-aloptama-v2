"""Manual backfill endpoints (Settings -> Backfill).

- ``POST /backfill/all/start``: SLA from the oneminute WIDN files at FULL
  1-minute resolution, filling BACKWARDS from now -> backfill_start so the
  most recent data lands first. Per day it resolves the shared 091 file
  once, writes CDP connectivity + wide awos_metrics rows with BULK upserts
  (a handful of statements per day instead of one per minute), and skips
  minutes already present.
- Progress is streamed back to the client as SSE lines.
"""

from __future__ import annotations

import logging
import asyncio as _asyncio
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert

from app.core.config import settings
from app.db.session import AsyncSessionLocal
from app.ingestion.cdp_reader import CdpReader
from app.ingestion.components import group_wide
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


def _bulk_cdp_upsert(rows: list[dict]):
    ins = insert(CdpConnectivity)
    return ins.values(rows).on_conflict_do_update(
        index_elements=["time", "cdp_id"],
        set_={"reachable": ins.excluded.reachable, "error_message": None},
    )


def _bulk_awos_upsert(rows: list[dict]):
    """Multi-row wide upsert; normalizes each row to the union of keys."""
    cols = ["time", "site_id"] + [
        c for r in rows for c in r if c not in ("time", "site_id")
    ]
    cols = list(dict.fromkeys(cols))  # dedupe, preserve order
    values = [{c: r.get(c) for c in cols} for r in rows]
    ins = insert(AwosMetrics)
    return ins.values(values).on_conflict_do_update(
        index_elements=["time", "site_id"],
        set_={c: getattr(ins.excluded, c) for c in cols if c not in ("time", "site_id")},
    )


async def _stream_all():
    """Combined CDP + DCP backfill, one bulk pass per day."""
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

        async with AsyncSessionLocal() as session:
            # Parse the shared file ONCE per site into per-site metric groups;
            # also collect every minute timestamp present (CDP reachability).
            present: set = set()
            parsed_by_site: dict[str, dict] = {}
            if one_min is not None:
                try:
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
                            present.add(rec.ts.replace(second=0, microsecond=0))
                        by_code: dict[str, list] = {}
                        for rec in recs:
                            for m in rec.metrics:
                                by_code.setdefault(m.sensor_code, []).append(m)
                        parsed_by_site[site.slug] = by_code
                except Exception as exc:  # noqa: BLE001
                    logger.error("DCP backfill parse error %s: %s", src, exc)

            # Minutes already present per site (one DISTINCT query each).
            existing: dict[str, set] = {}
            for slug in parsed_by_site:
                ts_rows = (
                    await session.execute(
                        select(AwosMetrics.time).where(
                            AwosMetrics.site_id == slug,
                            AwosMetrics.time >= day_start,
                            AwosMetrics.time < day_end,
                        )
                    )
                ).scalars().all()
                existing[slug] = {t.replace(second=0, microsecond=0) for t in ts_rows}

            # CDP: bulk connectivity upsert for every minute in the window.
            cdp_batch: list[dict] = []
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
                    cdp_batch.append({"time": minute, "cdp_id": node.id, "reachable": reachable})
            if cdp_batch:
                await session.execute(_bulk_cdp_upsert(cdp_batch))

            # DCP: wide awos_metrics per site, skip already-present minutes.
            site_rows: dict[str, int] = {}
            site_skip: dict[str, int] = {}
            for slug, by_code in parsed_by_site.items():
                batch = []
                for r in group_wide(by_code, slug):
                    rec_min = r["time"]
                    if rec_min < target or rec_min > day_end:
                        continue
                    if rec_min in existing.get(slug, set()):
                        site_skip[slug] = site_skip.get(slug, 0) + 1
                        continue
                    batch.append(r)
                    site_rows[slug] = site_rows.get(slug, 0) + 1
                if batch:
                    await session.execute(_bulk_awos_upsert(batch))
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
