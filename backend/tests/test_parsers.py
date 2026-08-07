"""Tests for the 1-minute + raw-DCP log parsers (with fallback)."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest

from app.ingestion.parsers import (
    coerce_value,
    parse_one_minute_file,
    parse_raw_dcp_file,
    parse_site_batch,
    parse_timestamp_from_filename,
)


def test_parse_one_minute_ok(one_minute_file: Path) -> None:
    specs = {
        "ATRH": {"position": 1},
        "BARO": {"position": 2},
        "WIND": {"position": 3},
    }
    records = parse_one_minute_file(one_minute_file, specs)
    assert len(records) == 2
    r = records[0]
    by_code = {s.sensor_code: s for s in r.samples}
    assert by_code["ATRH"].value == 25.4
    assert by_code["ATRH"].status == "ok"
    assert by_code["BARO"].value == 1013.25
    assert by_code["WIND"].value == 12.3


def test_parse_one_minute_missing_position(one_minute_file: Path) -> None:
    specs = {"CEIL": {"position": 99}}
    records = parse_one_minute_file(one_minute_file, specs)
    assert records
    assert records[0].samples[0].status == "missing"
    assert records[0].samples[0].value is None


def test_parse_one_minute_corrupt(tmp_path: Path) -> None:
    path = tmp_path / "RWYA202601010000.OneMinute.dat"
    path.write_text("2026-01-01 00:00:00 bad 1013.25\n", encoding="utf-8")
    records = parse_one_minute_file(path, {"ATRH": {"position": 1}})
    assert records[0].samples[0].status == "corrupt"
    assert records[0].samples[0].value is None


def test_parse_raw_dcp_slicing(raw_dcp_file: Path) -> None:
    specs = {
        "ATRH": {"fallback_slice": "20:30"},
        "BARO": {"fallback_slice": "30:40"},
        "WIND": {"fallback_slice": "40:50"},
    }
    records = parse_raw_dcp_file(raw_dcp_file, specs)
    assert len(records) == 2
    r = records[0]
    by_code = {s.sensor_code: s for s in r.samples}
    assert by_code["ATRH"].value == 25.4
    assert by_code["BARO"].value == 1013.25
    assert by_code["WIND"].value == 12.3
    assert by_code["ATRH"].status == "ok"


def test_parse_site_batch_fallback(
    tmp_path: Path, one_minute_file: Path, raw_dcp_file: Path
) -> None:
    # Corrupt the 1-minute field, raw DCP has the valid value
    one_minute_file.write_text(
        "2026-01-01 00:00:00 BAD 1013.25 12.3\n", encoding="utf-8"
    )
    specs = {"ATRH": {"position": 1, "fallback_slice": "20:30"}}
    result = parse_site_batch(one_minute_file, raw_dcp_file, specs)
    samples = result["ATRH"]
    assert samples[0].value == 25.4  # recovered from raw DCP
    assert samples[0].status == "ok"


def test_parse_site_batch_no_one_minute_file(
    tmp_path: Path, raw_dcp_file: Path
) -> None:
    missing = tmp_path / "DOESNOTEXIST.OneMinute.dat"
    specs = {"ATRH": {"position": 1, "fallback_slice": "20:30"}}
    result = parse_site_batch(missing, raw_dcp_file, specs)
    samples = result.get("ATRH", [])
    assert len(samples) == 2
    assert samples[0].value == 25.4
    assert samples[0].status == "ok"


def test_parse_timestamp_from_filename() -> None:
    ts = parse_timestamp_from_filename("DCPA202601010030.OneMinute.dat")
    assert ts == datetime(2026, 1, 1, 0, 30, tzinfo=timezone.utc)


def test_parse_timestamp_invalid() -> None:
    assert parse_timestamp_from_filename("DCPA.invalid.dat") is None


def test_coerce_value() -> None:
    assert coerce_value("25.4") == 25.4
    assert coerce_value("  ") is None
    assert coerce_value("N/A") is None
    assert coerce_value("1,5") == 1.5  # comma decimal