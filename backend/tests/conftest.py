"""Shared pytest fixtures."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest


@pytest.fixture
def one_minute_file(tmp_path: Path) -> Path:
    """Sample 1-minute aggregated log file (space-separated columns).

    Layout: <TIMESTAMP> <TEMP> <PRESSURE> ... extra columns
    """
    path = tmp_path / "DCPA202601010000.OneMinute.dat"
    path.write_text(
        "2026-01-01 00:00:00 25.4 1013.25 12.3\n"
        "2026-01-01 00:01:00 25.5 1013.30 12.4\n",
        encoding="utf-8",
    )
    return path


@pytest.fixture
def raw_dcp_file(tmp_path: Path) -> Path:
    """Sample raw DCP telemetry file (fixed character positions).

    Layout (1-based):
      1-19 : timestamp "20260101000000"
      20-29: temperature   (10 chars)
      30-39: pressure      (10 chars)
      40-49: wind speed    (10 chars)
    """
    def line(ts: str, temp: str, pres: str, wind: str) -> str:
        return f"{ts:<19}{temp:>10}{pres:>10}{wind:>10}\n"

    path = tmp_path / "DCPA20260101.dat"
    path.write_text(
        line("20260101000000", "25.4", "1013.25", "12.3")
        + line("20260101010000", "25.5", "1013.30", "12.4"),
        encoding="utf-8",
    )
    return path


@pytest.fixture
def ts() -> datetime:
    return datetime(2026, 1, 1, tzinfo=timezone.utc)