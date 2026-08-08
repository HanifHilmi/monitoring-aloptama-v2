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

MISSING = {"///", "//", "MM", "M", "N/A", "---", ""}

LINE_PAD = 350


@dataclass
class ParsedMetric:
    sensor_code: str
    metric: str
    value: Optional[float]
    text_value: Optional[str]
    is_valid: bool
    raw: str = ""


@dataclass
class ParsedRecord:
    ts: datetime
    metrics: list[ParsedMetric] = field(default_factory=list)


def coerce_value(raw: str) -> Optional[float]:
    token = raw.strip()
    if not token or token in MISSING:
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
    # RWY 04
    ("ATRH", "04"): [("TEMP", 79, 83, 0.1), ("DEWP", 84, 88, 0.1), ("RH", 89, 93, None)],
    ("BARO", "04"): [("QNH", 124, 129, 0.1)],
    ("ANEM", "04"): [("WS", 19, 23, None), ("WD", 24, 28, None)],
    ("RVR", "04"): [("RVR", 176, 181, None), ("VIS", 170, 175, None),
                    ("ALS_INT", 160, 165, None), ("D/N", 166, 169, None)],
    ("CEL", "04"): [("LR1", 218, 222, None), ("SKY", 228, 257, None)],
    ("PWX", "04"): [("PW", 306, 315, None)],
    # MIDDLE (station M)
    ("ATRH", "M"): [("TEMP", 94, 98, 0.1), ("DEWP", 99, 103, 0.1), ("RH", 104, 108, None)],
    ("BARO", "M"): [("QNH", 130, 135, 0.1)],
    ("ANEM", "M"): [("WS", 39, 43, None), ("WD", 44, 48, None)],
    ("RAIN", "M"): [("RA", 294, 299, None)],
    ("SOLR", "M"): [("SOL", 326, 331, None)],
    ("LIGH", "M"): [("LTX", 332, 336, None)],
    # RWY 22
    ("ATRH", "22"): [("TEMP", 109, 113, 0.1), ("DEWP", 114, 118, 0.1), ("RH", 119, 123, None)],
    ("BARO", "22"): [("QNH", 136, 141, 0.1)],
    ("ANEM", "22"): [("WS", 59, 63, None), ("WD", 64, 68, None)],
    ("RVR", "22"): [("RVR", 200, 205, None), ("VIS", 194, 199, None)],
    ("CEL", "22"): [("LR1", 223, 227, None), ("SKY", 258, 287, None)],
    ("PWX", "22"): [("PW", 316, 325, None)],
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
                val = coerce_value(token)
                if scale is not None and val is not None:
                    val = round(val * scale, 6)
                valid = val is not None
                rec.metrics.append(
                    ParsedMetric(
                        code, metric, val,
                        token if not valid else None, valid, line,
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