"""WIDN 1-minute oneminute parser using FIXED CHARACTER POSITIONS.

The real 091OneMinute.<date>.dat uses fixed-width columns (see the AWOS
reference parser). Each data line is padded to 350 chars; fields are
extracted by [start:end] character slices. The first 4 lines are the
header. TEMP/DEWP/QNH are stored without a decimal point and divided by 10.

Sensor -> (station, list of (metric, slice)):
  RWY04 (station 04): ATRH TEMP/DEWP/RH, BARO QNH, ANEM WS/WD,
                      RVR RVR/VIS/ALS/D-N, CEL LR1/SKY, PWX PW
  RWYMID (station M): ATRH TEMP/DEWP/RH, BARO QNH, ANEM WS/WD,
                      RAIN RA, SOLR SOL, LIGH LTX
  RWY22 (station 22): ATRH TEMP/DEWP/RH, BARO QNH, ANEM WS/WD,
                      RVR RVR/VIS, CEL LR1/SKY, PWX PW
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

# Explicit missing tokens => sensor OFFLINE => SQL NULL at write time.
MISSING = {"///", "//", "MM", "M", "N/A", "---"}

LINE_PAD = 350


@dataclass
class ParsedMetric:
    sensor_code: str
    metric: str
    value: Optional[float]
    text_value: Optional[str]
    is_valid: bool
    raw: str = ""
    ts: Optional[datetime] = None    # the record's minute (for wide rows)


@dataclass
class ParsedRecord:
    ts: datetime
    metrics: list[ParsedMetric] = field(default_factory=list)


def coerce_value(raw: str) -> Optional[float]:
    token = raw.strip()
    # Empty/whitespace = sensor ONLINE and healthy but no value to show:
    # numeric 0 (text handled by the caller via text_value '').
    if not token:
        return 0.0
    if token in MISSING:
        return None
    clean = token.replace(",", ".")
    try:
        return float(clean)
    except ValueError:
        return None


def parse_timestamp_from_filename(filename: str) -> Optional[datetime]:
    m = re.search(r"(\d{8})", filename)
    if m:
        try:
            return datetime.strptime(m.group(1), "%Y%m%d").replace(tzinfo=timezone.utc)
        except ValueError:
            pass
    return None


# Fixed character slices per (sensor_code, station). start:end are indexes
# into the padded line. Event/text fields have scale=None (kept as text).
_SLICES: dict[tuple[str, str], list[tuple[str, int, int, Optional[float]]]] = {
    # RWY 04  (offsets measured from the fixed-width WIDN 041 sample line)
    ("ATRH", "04"): [("TEMP", 79, 84, 0.1), ("DEWP", 84, 89, 0.1), ("RH", 89, 93, None)],
    ("BARO", "04"): [("QNH", 124, 130, 0.1), ("DA", 142, 148, None)],
    ("ANEM", "04"): [("WS", 19, 24, None), ("WD", 24, 29, None),
                        ("WGS", 29, 34, None), ("WGD", 34, 39, None)],
    ("RVR", "04"): [("RVR", 176, 182, None), ("VIS", 170, 176, None),
                       ("ALS", 160, 166, None), ("D/N", 166, 168, None),
                       ("RLS", 182, 184, None)],
    ("CEL", "04"): [("LR1", 218, 222, None), ("SKY", 228, 258, None)],
    ("PWX", "04"): [("PW", 306, 312, None), ("RA", 288, 294, None)],
    # MIDDLE (station M)
    ("ATRH", "M"): [("TEMP", 94, 99, 0.1), ("DEWP", 99, 104, 0.1), ("RH", 104, 108, None)],
    ("BARO", "M"): [("QNH", 130, 136, 0.1), ("DA", 148, 154, None)],
    ("ANEM", "M"): [("WS", 39, 44, None), ("WD", 44, 49, None),
                       ("WGS", 49, 54, None), ("WGD", 54, 59, None)],
    ("RAIN", "M"): [("RA", 294, 300, None)],
    ("SOLR", "M"): [("SOL", 326, 331, None)],
    ("LIGH", "M"): [("LTX", 332, 364, None)],
    # RWY 22
    ("ATRH", "22"): [("TEMP", 109, 114, 0.1), ("DEWP", 114, 119, 0.1), ("RH", 119, 123, None)],
    ("BARO", "22"): [("QNH", 136, 142, 0.1), ("DA", 154, 160, None)],
    ("ANEM", "22"): [("WS", 59, 64, None), ("WD", 64, 69, None),
                        ("WGS", 69, 74, None), ("WGD", 74, 79, None)],
    ("RVR", "22"): [("RVR", 200, 206, None), ("VIS", 194, 200, None),
                       ("RLS", 206, 208, None)],
    ("CEL", "22"): [("LR1", 223, 227, None), ("SKY", 258, 288, None)],
    ("PWX", "22"): [("PW", 316, 322, None), ("RA", 300, 306, None)],
}


def parse_one_minute_file(path, sensor_specs, default_ts=None) -> list[ParsedRecord]:
    """Parse a daily 091OneMinute.<date>.dat by fixed char positions."""
    try:
        content = path.read_text(encoding="utf-8", errors="replace")
    except (OSError, UnicodeError):
        return []
    lines = content.splitlines()
    # Skip the 4 header lines (title, STN names, station map, units).
    data_lines = lines[4:]

    # sensor_specs: {code: {station, ...}}
    station_of = {code: spec.get("station", "04") for code, spec in sensor_specs.items()}

    records: list[ParsedRecord] = []
    for raw in data_lines:
        line = raw.rstrip("\n")
        if not line.strip():
            continue
        padded = line.ljust(LINE_PAD, " ")
        # Timestamp: Date cols[4:12] + Hour[13:15] + Minute[16:18]
        date_s = padded[4:12].strip()
        hour_s = padded[13:15].strip()
        min_s = padded[16:18].strip()
        if not (date_s and hour_s and min_s):
            continue
        try:
            ts = datetime.strptime(f"{date_s} {hour_s} {min_s}", "%Y%m%d %H %M").replace(tzinfo=timezone.utc)
        except ValueError:
            continue

        rec = ParsedRecord(ts=ts)
        for code, station in station_of.items():
            spec = _SLICES.get((code, station))
            if not spec:
                continue
            for metric, start, end, scale in spec:
                token = padded[start:end].strip()
                is_text = scale is None
                val = coerce_value(token)  # None for explicit missing/'', else numeric (0 for empty)
                if scale is not None and val is not None:
                    val = round(val * scale, 6)
                # Numeric: valid when not explicit-missing (empty -> 0 healthy).
                # Text: valid when a non-missing token exists; empty stays ''.
                if is_text:
                    valid = token not in MISSING
                else:
                    valid = val is not None
                rec.metrics.append(
                    ParsedMetric(
                        code, metric, val,
                        token if is_text else None, valid, line, ts,
                    )
                )
        records.append(rec)
    return records


def parse_raw_dcp_file(path, sensor_specs, default_ts=None):
    # /sensor/ folder is not used as a data source anymore.
    return []


def parse_site_batch(one_minute_path, raw_sensor_path, sensor_specs, default_ts=None):
    result: dict[str, list[ParsedMetric]] = {}
    if not one_minute_path.exists():
        return result
    for rec in parse_one_minute_file(one_minute_path, sensor_specs, default_ts):
        for metric in rec.metrics:
            result.setdefault(metric.sensor_code, []).append(metric)
    return result