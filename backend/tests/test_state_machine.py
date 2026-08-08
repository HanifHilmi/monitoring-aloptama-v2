"""Tests for SLA/OLA state machine transitions and uptime math."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.ingestion.state_machine import (
    DowntimeStateMachine,
    compute_uptime_pct,
    transition_ola,
    transition_sla,
)
from tests.fakes import FakeSession


def test_uptime_pct_100() -> None:
    assert compute_uptime_pct(86400, 0) == 100.0


def test_uptime_pct_zero_downtime_window() -> None:
    assert compute_uptime_pct(0, 0) == 0.0


def test_uptime_pct_50() -> None:
    # 12h down out of 24h
    assert compute_uptime_pct(86400, 43200) == 50.0


def test_uptime_pct_quarter() -> None:
    assert compute_uptime_pct(86400, 21600) == 75.0


@pytest.mark.asyncio
async def test_sla_open_and_close() -> None:
    session = FakeSession()
    sm = DowntimeStateMachine()
    t0 = datetime(2026, 1, 1, 0, 0, tzinfo=timezone.utc)

    ev_open = await transition_sla(session, sm, cdp_id=1, site_id=None, reachable=False, ts=t0)
    assert ev_open is not None
    assert ev_open.start_time == t0
    assert ev_open.end_time is None
    assert ev_open.entity_type == "cdp_node"  # must match DB CHECK constraint
    assert sm.get_open_since("sla", "cdp", 1) == t0

    # No duplicate while already down
    ev2 = await transition_sla(session, sm, cdp_id=1, site_id=None, reachable=False, ts=t0 + timedelta(minutes=5))
    assert ev2 is None

    t_close = t0 + timedelta(minutes=10)
    ev_close = await transition_sla(session, sm, cdp_id=1, site_id=None, reachable=True, ts=t_close)
    assert ev_close is not None
    assert ev_close.id == ev_open.id
    assert ev_close.end_time == t_close
    assert sm.get_open_since("sla", "cdp", 1) is None


@pytest.mark.asyncio
async def test_sla_healthy_no_event() -> None:
    session = FakeSession()
    sm = DowntimeStateMachine()
    ev = await transition_sla(session, sm, cdp_id=2, site_id=None, reachable=True, ts=datetime(2026, 1, 1, tzinfo=timezone.utc))
    assert ev is None


@pytest.mark.asyncio
async def test_ola_open_and_close() -> None:
    session = FakeSession()
    sm = DowntimeStateMachine()
    t0 = datetime(2026, 1, 1, 0, 0, tzinfo=timezone.utc)

    ev_open = await transition_ola(
        session, sm, sensor_id=42, site_id=3, is_down=True, ts=t0, reason="corrupt"
    )
    assert ev_open is not None
    assert ev_open.sensor_id == 42
    assert ev_open.reason_code == "corrupt"

    t_close = t0 + timedelta(minutes=3)
    ev_close = await transition_ola(
        session, sm, sensor_id=42, site_id=3, is_down=False, ts=t_close, reason="ok"
    )
    assert ev_close is not None
    assert ev_close.end_time == t_close
    assert sm.get_open_since("ola", "sensor", 42) is None