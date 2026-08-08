"""State-machine for SLA (CDP reachability) and OLA (sensor health).

Transitions:
    ok -> down   opens a downtime event (start_time set)
    down -> ok   closes the event (end_time set, duration computed)

Uptime % = ((Total Seconds - Downtime Seconds) / Total Seconds) * 100
Downtime is measured strictly from open/closed event boundaries.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import DowntimeEvent

logger = logging.getLogger(__name__)


class DowntimeStateMachine:
    """Tracks open/closed downtime events for a single entity."""

    def __init__(self):
        self._cache: dict[tuple[str, int], Optional[datetime]] = {}

    def get_open_since(
        self,
        scope_type: str,
        entity_type: str,
        entity_id: int,
    ) -> Optional[datetime]:
        key = (scope_type, entity_type, entity_id)
        return self._cache.get(key)

    def set_open_since(
        self,
        scope_type: str,
        entity_type: str,
        entity_id: int,
        ts: datetime,
    ) -> None:
        key = (scope_type, entity_type, entity_id)
        self._cache[key] = ts

    def clear(self, scope_type: str, entity_type: str, entity_id: int) -> None:
        key = (scope_type, entity_type, entity_id)
        self._cache.pop(key, None)


async def load_open_events(session: AsyncSession, sm: DowntimeStateMachine) -> None:
    """Hydrate the state machine from unclosed downtime events on boot."""
    stmt = select(DowntimeEvent).where(DowntimeEvent.end_time.is_(None))
    rows = (await session.execute(stmt)).scalars().all()
    for ev in rows:
        if ev.scope_type == "sla" and ev.cdp_id is not None:
            sm.set_open_since("sla", "cdp", ev.cdp_id, ev.start_time)
        elif ev.scope_type == "ola" and ev.sensor_id is not None:
            sm.set_open_since("ola", "sensor", ev.sensor_id, ev.start_time)


async def transition_sla(
    session: AsyncSession,
    sm: DowntimeStateMachine,
    cdp_id: int,
    site_id: Optional[int],
    reachable: bool,
    ts: datetime,
) -> Optional[DowntimeEvent]:
    """Transition CDP SLA state. Returns the created/closed event if any."""
    open_since = sm.get_open_since("sla", "cdp", cdp_id)
    if reachable:
        if open_since is not None:
            ev = await _close_event(session, cdp_id=cdp_id, end=ts)
            sm.clear("sla", "cdp", cdp_id)
            return ev
        return None
    if open_since is None:
        sm.set_open_since("sla", "cdp", cdp_id, ts)
        ev = DowntimeEvent(
            scope_type="sla",
            entity_type="cdp_node",
            cdp_id=cdp_id,
            site_id=site_id,
            start_time=ts,
            reason_code="cdp_unreachable",
            details={"transitioned_to": "down"},
        )
        session.add(ev)
        await session.flush()
        return ev
    return None


async def transition_ola(
    session: AsyncSession,
    sm: DowntimeStateMachine,
    sensor_id: int,
    site_id: int,
    is_down: bool,
    ts: datetime,
    reason: str,
) -> Optional[DowntimeEvent]:
    """Transition sensor OLA state. Returns the created/closed event if any."""
    open_since = sm.get_open_since("ola", "sensor", sensor_id)
    if not is_down:
        if open_since is not None:
            ev = await _close_event(session, sensor_id=sensor_id, end=ts)
            sm.clear("ola", "sensor", sensor_id)
            return ev
        return None
    if open_since is None:
        sm.set_open_since("ola", "sensor", sensor_id, ts)
        ev = DowntimeEvent(
            scope_type="ola",
            entity_type="sensor",
            sensor_id=sensor_id,
            site_id=site_id,
            start_time=ts,
            reason_code=reason,
            details={"transitioned_to": "down"},
        )
        session.add(ev)
        await session.flush()
        return ev
    return None


async def _close_event(
    session: AsyncSession,
    *,
    cdp_id: Optional[int] = None,
    sensor_id: Optional[int] = None,
    end: datetime,
) -> Optional[DowntimeEvent]:
    """Close the oldest open event for the entity, computing duration."""
    if cdp_id is not None:
        stmt = (
            select(DowntimeEvent)
            .where(DowntimeEvent.cdp_id == cdp_id, DowntimeEvent.end_time.is_(None))
            .order_by(DowntimeEvent.start_time)
            .limit(1)
        )
    elif sensor_id is not None:
        stmt = (
            select(DowntimeEvent)
            .where(DowntimeEvent.sensor_id == sensor_id, DowntimeEvent.end_time.is_(None))
            .order_by(DowntimeEvent.start_time)
            .limit(1)
        )
    else:
        return None

    ev = (await session.execute(stmt)).scalars().first()
    if ev is None:
        return None
    ev.end_time = end
    ev.details = {**(ev.details or {}), "transitioned_to": "ok"}
    await session.flush()
    return ev


def compute_uptime_pct(total_seconds: int, downtime_seconds: int) -> float:
    """Uptime % = ((Total - Downtime) / Total) * 100."""
    if total_seconds <= 0:
        return 0.0
    return round(((total_seconds - downtime_seconds) / total_seconds) * 100.0, 4)


def now_utc() -> datetime:
    return datetime.now(timezone.utc)