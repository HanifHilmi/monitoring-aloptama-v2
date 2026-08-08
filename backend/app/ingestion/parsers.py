"""WIDN 1-minute log parser.

The WIDN daily report (``091OneMinute.<YYYYMMDD>.dat``) has per-station
(04/M/22) metric blocks. Each sensor maps to one or more WIDN symbols.
TEMP/DEWP/QNH are transmitted with one extra digit (e.g. 253 => 25.3 C,
10108 => 1010.8 hPa); `scale` divides the raw value accordingly.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

MISSING_TOKENS = {"///", "MMMM", "M", "N/A", ""}


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
    if not token or token in MISSING_TOKENS:
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


# WIDN symbol -> sensor metric descriptor (scale divides raw value).
SENSOR_METRICS = {
    "ATRH": [
        {"metric": "TEMP", "symbol": "TEMP", "scale": 0.1},
        {"metric": "DEWP", "symbol": "DEWP", "scale": 0.1},
        {"metric": "RH", "symbol": "RH"},
    ],
    "BARO": [{"metric": "QNH", "symbol": "QNH", "scale": 0.1}],
    "ANEM": [
        {"metric": "WS", "symbol": "WS"},
        {"metric": "WD", "symbol": "WD"},
        {"metric": "WGS", "symbol": "WGS"},
    ],
    "PWX": [
        {"metric": "PW", "symbol": "PW"},
        {"metric": "VIS", "symbol": "VIS"},
    ],
    "CEL": [
        {"metric": "LR1", "symbol": "LR1"},
        {"metric": "SKY", "symbol": "SKY"},
    ],
    "RVR": [{"metric": "RVR", "symbol": "RVR"}],
    "ALS": [
        {"metric": "ALS_INT", "symbol": "ALS"},
        {"metric": "D/N", "symbol": "D/N"},
    ],
    "RAIN": [{"metric": "RA", "symbol": "RA"}],
    "SOLR": [{"metric": "SOL", "symbol": "SOL"}],
    "LIGH": [{"metric": "LTX", "symbol": "LTX"}],
}


def _load_header(lines: list[str]) -> tuple[list[str], list[str]]:
    symbol_map: list[str] = []
    station_map: list[str] = []
    for raw in lines:
        stripped = raw.strip()
        if not stripped:
            continue
        tokens = stripped.split()
        if tokens[0] == "STN":
            symbol_map = tokens[4:]
        elif tokens[0] == "xxx":
            station_map = tokens[1:]
        if symbol_map and station_map:
            break
    return symbol_map, station_map


def _column_for(symbol, station, symbol_map, station_map) -> Optional[int]:
    if not symbol_map:
        return None
    for i, sym in enumerate(symbol_map):
        if sym != symbol:
            continue
        stat = station_map[i] if i < len(station_map) else ""
        if stat == station:
            return i
    return None


def parse_one_minute_file(path, sensor_specs, default_ts=None) -> list[ParsedRecord]:
    try:
        content = path.read_text(encoding="utf-8", errors="replace")
    except (OSError, UnicodeError):
        return []
    lines = content.splitlines()
    symbol_map, station_map = _load_header(lines)

    station_of: dict[str, str] = {}
    specs_metrics: dict[str, list[dict]] = {}
    for code, spec in sensor_specs.items():
        station = spec.get("station", "04")
        station_of[code] = station
        metrics = SENSOR_METRICS.get(code, [])
        if not metrics:
            metrics = [{"metric": "value", "symbol": spec.get("symbol", "TEMP")}]
        specs_metrics[code] = metrics

    records: list[ParsedRecord] = []
    for raw in lines:
        line = raw.strip()
        if not line:
            continue
        tokens = line.split()
        if len(tokens) < 5 or not re.match(r"^\d{8}$", tokens[1]):
            continue
        try:
            ts = datetime.strptime(
                f"{tokens[1]} {tokens[2]} {tokens[3]}", "%Y%m%d %H %M"
            ).replace(tzinfo=timezone.utc)
        except ValueError:
            continue
        data_tokens = tokens[4:]

        rec = ParsedRecord(ts=ts)
        for code, metrics in specs_metrics.items():
            station = station_of[code]
            for m in metrics:
                idx = _column_for(m["symbol"], station, symbol_map, station_map)
                if idx is None or idx >= len(data_tokens):
                    rec.metrics.append(
                        ParsedMetric(code, m["metric"], None, None, False, line)
                    )
                    continue
                token = data_tokens[idx].strip()
                val = coerce_value(token)
                scale = m.get("scale", 1.0)
                if val is not None and scale != 1.0:
                    val = round(val * scale, 6)
                valid = val is not None
                rec.metrics.append(
                    ParsedMetric(
                        code, m["metric"], val,
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