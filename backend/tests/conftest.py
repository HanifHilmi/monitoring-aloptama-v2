"""Shared pytest fixtures (fixed-width WIDN oneminute layout)."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest

# 4 header lines must precede the data rows (skipped by the parser).
WIDN_HEADER = (
    "One Minute Report for WIDN\n"
    "STN YYYYMMDD GG MM WS WD WGS WGD WS WD WGS WGD WS WD WGS WGD TEMP DEWP RH TEMP DEWP RH TEMP DEWP RH QNH QNH QNH DA DA DA ALS D/N VIS RVR RLS VIS RVR RLS LR1 LR1 SKY SKY RA RA RA PW PW SOL LTX\n"
    "xxx 04 04 04 04 M M M M 22 22 22 22 04 04 04 M M M 22 22 22 04 M 22 04 M 22 04 04 04 04 22 22 22 04 22 04 22 04 M 22 04 22 M M\n"
    "kt deg kt deg kt deg kt deg kt deg kt deg degC degC pct degC degC pct degC degC pct hPa hPa hPa ft ft ft cd m m\n"
)


def _padded_row(values: dict[int, str]) -> str:
    """Build a 350-char fixed-width data line with values at char offsets."""
    line = [" "] * 350
    for start, text in values.items():
        for i, ch in enumerate(str(text)):
            if start + i < 350:
                line[start + i] = ch
    return "".join(line) + "\n"


@pytest.fixture
def widn_file(tmp_path: Path) -> Path:
    """Fixed-width WIDN daily sample (station 091) with all three blocks."""
    path = tmp_path / "091OneMinute.20260101.dat"
    # Fixed offsets from the AWOS reference parser.
    row = _padded_row({
        0: "091", 4: "20260101", 13: "00", 16: "00",
        # Wedge (04 / M / 22)
        19: "  5", 24: "165", 29: "  9", 34: "170",   # WS_04=5, WD_04=165, WGS_04=9, WGD_04=170
        39: "  2", 44: "166", 49: " 15", 54: "171",  # WS_M=2, WD_M=166, WGS_M=15, WGD_M=171
        59: "  3", 64: "181", 69: " 21", 74: "180",  # WS_22=3, WD_22=181, WGS_22=21, WGD_22=180
        # TEMP/DEWP/RH per station
        79: "253", 84: "235", 89: " 90",   # 04
        94: "251", 99: "236", 104: " 92",  # M
        109: "249", 114: "233", 119: " 90",  # 22
        # QNH (hPa ÷10)
        124: "10108", 130: "10108", 136: "10108",  # 04 / M / 22
        # DA (density altitude) per station
        142: "   4", 148: "   5", 154: "   6",
        # ALS / Day-Night / VIS / RVR (04)
        160: "1047", 166: "D", 170: "13459", 176: "13459",
        # Ceilometer (04/22) LR1 + SKY
        218: " 23", 228: "OVC024", 223: " 22", 258: "SCT300",
        # Present Weather + precip (RA 04)
        288: "  0", 306: "RERA", 316: "NCD",
        # Middle extras
        294: "  0", 326: " 17", 332: " 17",
    })
    path.write_text(WIDN_HEADER + row + row, encoding="utf-8")
    return path


@pytest.fixture
def ts() -> datetime:
    return datetime(2026, 1, 1, tzinfo=timezone.utc)