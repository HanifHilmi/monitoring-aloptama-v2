"""Tests for the WIDN multi-metric parser."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from app.ingestion.parsers import (
    coerce_value,
    parse_one_minute_file,
    parse_site_batch,
    parse_timestamp_from_filename,
)


def specs(station: str = "04") -> dict:
    codes = ["ATRH", "BARO", "ANEM", "PWX", "CEL", "RVR", "ALS", "RAIN", "SOLR", "LIGH"]
    return {
        code: {"sensor_id": i + 1, "station": station}
        for i, code in enumerate(codes)
    }


def test_parse_widn_metrics(widn_file: Path) -> None:
    records = parse_one_minute_file(widn_file, specs())
    assert len(records) == 2
    # 091 20260101 00 00 row: TEMP=253, QNH=10108, WS=5, WGS invalid
    by_code: dict[str, dict] = {}
    for m in records[0].metrics:
        by_code[(m.sensor_code, m.metric)] = m
    # TEMP/DEWP/QNH are transmitted with a trailing digit; `scale` divides.
    assert by_code[("ATRH", "TEMP")].value == 25.3
    assert by_code[("ATRH", "DEWP")].value == 23.5
    assert by_code[("ATRH", "RH")].value == 90.0
    assert by_code[("BARO", "QNH")].value == 1010.8
    assert by_code[("ANEM", "WS")].value == 5.0
    assert by_code[("ANEM", "WD")].value == 165.0
    # Wind gust metrics are now saved against the anemometer.
    assert by_code[("ANEM", "WGS")].value == 9.0
    assert by_code[("ANEM", "WGD")].value == 170.0
    assert by_code[("CEL", "LR1")].value == 23.0
    assert by_code[("CEL", "SKY")].text_value == "OVC024"
    # ALS + D/N belong to the RVR component (RVR_ALS), not a separate ALS.
    assert by_code[("RVR", "ALS")].value == 1047.0
    assert by_code[("RVR", "D/N")].text_value == "D"
    # VIS belongs to RVR, not PWX (product semantics).
    assert by_code[("RVR", "VIS")].value == 13459.0
    assert by_code[("RVR", "RVR")].value == 13459.0
    assert ("PWX", "VIS") not in by_code
    assert by_code[("PWX", "PW")].text_value == "RERA"
    # DA (density altitude) and RA (precip) are now parsed too.
    assert by_code[("BARO", "DA")].value == 4.0
    assert by_code[("PWX", "RA")].value == 0.0


def test_parse_widn_station22(widn_file: Path) -> None:
    records = parse_one_minute_file(widn_file, specs(station="22"))
    by_code: dict[str, dict] = {}
    for m in records[0].metrics:
        by_code[(m.sensor_code, m.metric)] = m
    # Row: 253 235 90 | 251 236 92 | 249 233 90 maps to 04 | M | 22
    assert by_code[("ATRH", "TEMP")].value == 24.9  # station 22 block, ÷10
    assert by_code[("ANEM", "WS")].value == 3.0  # 04=5, M=2, 22=3
    assert by_code[("BARO", "QNH")].value == 1010.8


def test_parse_site_batch(widn_file: Path) -> None:
    result = parse_site_batch(widn_file, widn_file, specs())
    assert "ATRH" in result
    atrh = result["ATRH"]
    by_metric = {m.metric: m for m in atrh}
    assert len(by_metric) == 3  # TEMP / DEWP / RH
    assert by_metric["TEMP"].value == 25.3  # scaled ÷10


def test_parse_timestamp_from_filename() -> None:
    ts = parse_timestamp_from_filename("091OneMinute.20260101.dat")
    assert ts == datetime(2026, 1, 1, tzinfo=timezone.utc)


def test_parse_timestamp_invalid() -> None:
    assert parse_timestamp_from_filename("DCPA.invalid.dat") is None


def test_coerce_value() -> None:
    assert coerce_value("25.4") == 25.4
    # Empty/whitespace = healthy, no value -> 0 (online, no event).
    assert coerce_value("  ") == 0.0
    assert coerce_value("N/A") is None
    assert coerce_value("1,5") == 1.5
    # Explicit missing tokens -> NULL (sensor OFFLINE).
    assert coerce_value("///") is None
    assert coerce_value("MMMM") is None
    assert coerce_value("D") is None  # string day/night flag


def test_coerce_value_variable_slash_runs() -> None:
    # The offline representation is a run of '/' matching the field width:
    # '/', '//', '///', '/////', 29 slashes ... all must be NULL.
    assert coerce_value("/") is None
    assert coerce_value("//") is None
    assert coerce_value("///") is None
    assert coerce_value("/////") is None
    assert coerce_value("/" * 29) is None


def test_offline_text_fields_are_invalid(tmp_path) -> None:
    # Offline text fields (SKY with 29 slashes, D/N with a single slash) must
    # be flagged invalid (stored NULL) while healthy fields stay valid.
    from tests.conftest import WIDN_HEADER, _padded_row

    path = tmp_path / "091OneMinute.20260101.dat"
    row = _padded_row({
        0: "091", 4: "20260101", 13: "00", 16: "00",
        79: "253", 84: "235", 89: " 90",   # ATRH 04 healthy
        166: "/",                            # D/N 04 offline
        228: "/" * 29,                       # SKY 04 offline
    })
    path.write_text(WIDN_HEADER + row, encoding="utf-8")

    recs = parse_one_minute_file(path, specs())
    by = {(m.sensor_code, m.metric): m for m in recs[0].metrics}
    assert by[("CEL", "SKY")].is_valid is False
    assert by[("RVR", "D/N")].is_valid is False
    assert by[("ATRH", "TEMP")].is_valid is True