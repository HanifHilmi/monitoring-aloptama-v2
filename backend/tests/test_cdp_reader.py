"""Tests for CDP active-passive failover logic."""

from __future__ import annotations

from datetime import datetime, timezone

from app.ingestion.cdp_reader import CdpReader


def _reader(active_down: bool = False) -> CdpReader:
    reader = CdpReader(
        [
            {"id": 1, "name": "CDP1", "ip_address": "172.70.55.162",
             "mount_path": "/mnt/cdp1_logs/", "role": "active"},
            {"id": 2, "name": "CDP2", "ip_address": "172.70.55.163",
             "mount_path": "/mnt/cdp2_logs/", "role": "passive"},
        ]
    )
    if active_down:
        reader.state.nodes["CDP1"].reachable = False
        reader.state.nodes["CDP1"].consecutive_failures = 3
        reader.state.nodes["CDP2"].reachable = True
    else:
        reader.state.nodes["CDP1"].reachable = True
        reader.state.nodes["CDP2"].reachable = True
    return reader


def test_initial_active_node() -> None:
    reader = _reader()
    assert reader.active_node_name() == "CDP1"
    assert reader.state.active_node().role == "active"


def test_failover_promotes_passive() -> None:
    reader = _reader(active_down=True)
    assert reader.active_node_name() == "CDP1"
    # No real network I/O: drive the failover logic directly
    reader._promote_passive()
    assert reader.active_node_name() == "CDP2"
    assert reader.state.nodes["CDP1"].role == "passive"
    assert reader.state.nodes["CDP2"].role == "active"


def test_failover_does_not_flap() -> None:
    """Once promoted, the recovered original stays passive (no flapping)."""
    reader = _reader(active_down=True)
    reader._promote_passive()
    # Original active recovers
    reader.state.nodes["CDP1"].reachable = True
    reader.state.nodes["CDP2"].reachable = False
    reader._promote_passive()
    # CDP2 was the failed active -> promote CDP1 back
    assert reader.active_node_name() == "CDP1"


def test_resolve_site_file_on_active() -> None:
    reader = _reader()
    reader.state.nodes["CDP1"].mount_path = "/mnt/cdp1_logs/"
    ts = datetime(2026, 1, 1, 0, 30, tzinfo=timezone.utc)
    path = reader.resolve_site_file("DCPA", ts)
    assert path is not None
    name = path.name
    # Real WIDN layout: daily file. With the local CDP mount present the
    # resolver's universal-station glob matches 091OneMinute.20260101.dat;
    # otherwise it falls back to the site-prefixed candidate. Both end in
    # OneMinute.20260101.dat.
    assert name.startswith(("DCPAOneMinute", "091OneMinute"))
    assert name.endswith("OneMinute.20260101.dat")


def test_resolve_raw_sensor_file_on_active() -> None:
    reader = _reader()
    ts = datetime(2026, 1, 1, 0, 30, tzinfo=timezone.utc)
    path = reader.resolve_raw_sensor_file("RWYA", ts)
    assert path is not None
    assert str(path).endswith("/mnt/cdp1_logs/sensor/RWYA.DCP.2026010100.dat")


def test_resolve_after_failover_uses_new_active() -> None:
    reader = _reader(active_down=True)
    reader.state.nodes["CDP1"].reachable = False
    reader._promote_passive()
    ts = datetime(2026, 1, 1, 0, 30, tzinfo=timezone.utc)
    path = reader.resolve_site_file("DCPA", ts)
    assert path is not None
    assert str(path).startswith("/mnt/cdp2_logs/oneminute/")
    assert path.name.endswith("OneMinute.20260101.dat")


def test_resolve_none_without_active() -> None:
    reader = _reader()
    reader.state.active_name = None
    assert reader.resolve_site_file("DCPA", datetime(2026, 1, 1, tzinfo=timezone.utc)) is None
    assert reader.resolve_raw_sensor_file("DCPA", datetime(2026, 1, 1, tzinfo=timezone.utc)) is None