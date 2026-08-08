"""Shared pytest fixtures."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest


_WIDN_HEADER = (
    "One Minute Report for WIDN\n"
    "STN YYYYMMDD GG MM WS WD WGS WGD WS WD WGS WGD WS WD WGS WGD "
    "TEMP DEWP RH TEMP DEWP RH TEMP DEWP RH QNH QNH QNH DA DA DA "
    "ALS D/N VIS RVR RLS VIS RVR RLS LR1 LR1 SKY SKY RA RA RA PW PW SOL LTX \n"
    "xxx 04 04 04 04 M M M M 22 22 22 22 04 04 04 M M M 22 22 22 04 M 22 "
    "04 M 22 04 04 04 04 22 22 22 04 22 04 22 04 M 22 04 22 M M 47 \n"
)


@pytest.fixture
def widn_file(tmp_path: Path) -> Path:
    """Realistic WIDN daily report sample (station 091, three blocks)."""
    path = tmp_path / "091OneMinute.20260101.dat"
    # First data row: 091 20260101 00 00 WS=5 WD=165 ... TEMP=253 DEWP=235 RH=90
    # QNH=10108 DA=1700 ALS=1047 D/N=D VIS=13459 RVR=13459 RLS=5 SKY=Y LR1=5
    row = (
        "091 20260101 00 00   5  165  ///  ///    2  166  ///  ///    3  181  ///  /// "
        "  253  235  90   251  236  92   249  233  90  10108 10108 10108  "
        "1700  1700  1700  1047 D   13459 13459 5   5   Y   11220 11220 5   5   Y   "
        "   023  022  OVC024                        SCT020 OVC026                     0     0     0                       17       \n"
    )
    path.write_text(_WIDN_HEADER + row + row, encoding="utf-8")
    return path


@pytest.fixture
def ts() -> datetime:
    return datetime(2026, 1, 1, tzinfo=timezone.utc)