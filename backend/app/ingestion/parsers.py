"""WIDN 1-minute log parser.

The WIDN daily report (``091OneMinute.<YYYYMMDD>.dat``) layout:

    line1 : One Minute Report for WIDN
    line2 : STN YYYYMMDD GG MM WS WD WGS WGD WS WD WGS WGD WS WD WGS WGD
            TEMP DEWP RH TEMP DEWP RH TEMP DEWP RH QNH QNH QNH
            DA DA DA ALS D/N VIS RVR RLS VIS RVR RLS LR1 LR1 SKY SKY
            RA RA RA PW PW SOL LTX
    line3 : xxx 04 04 ... (station column map; 04/M/22 repeat per block)
    line4 : units / notes
    line5+ : 091 20260101 00 00 <columns...>

Each sensor's columns are the token slots where the symbol row equals the
sensor's WIDN symbol AND the station-map row equals the site's station.
We parse ALL metrics for a site (not just one value), carrying both float
and string values, and mark rows valid/invalid based on missing/corrupt.
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
    """One metric value for a sensor at a timestamp."""

    sensor_code: str
    metric: str
    value: Optional[float]
    text_value: Optional[str]
    is_valid: bool
    raw: str = ""


@dataclass
class ParsedRecord:
    """The set of metrics extracted from a single log row."""

    ts: datetime
    metrics: list[ParsedMetric] = field(default_factory=list)


def coerce_value(raw: str) -> Optional[float]:
    """Coerce a token to float if numeric-looking, else None."""
    token = raw.strip()
    if not token or token in MISSING_TOKENS:
        return None
    clean = token.replace(",", ".")
    try:
        return float(clean)
    except ValueError:
        return None


def parse_timestamp_from_filename(filename: str) -> Optional[datetime]:
    import re as _re

    m = _re.search(r"(\d{8})", filename)
    if m:
        try:
            return datetime.strptime(m.group(1), "%Y%m%d").replace(tzinfo=timezone.utc)
        except ValueError:
            pass
    return None


# ----------------------------------------------------------------------
# WIDN symbol/station -> sensor metric descriptor
# ----------------------------------------------------------------------
# metric names are the WIDN symbol tokens from the header (upper-cased).
SENSOR_METRICS = {
    "ATRH": [
        {"metric": "TEMP", "symbol": "TEMP"},
        {"metric": "DEWP", "symbol": "DEWP"},
        {"metric": "RH", "symbol": "RH"},
    ],
    "BARO": [
        {"metric": "QNH", "symbol": "QNH"},
    ],
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
    "RVR": [
        {"metric": "RVR", "symbol": "RVR"},
    ],
    "ALS": [
        {"metric": "ALS_INT", "symbol": "ALS"},
        {"metric": "D/N", "symbol": "D/N"},
    ],
    "RAIN": [
        {"metric": "RA", "symbol": "RA"},
    ],
    "SOLR": [
        {"metric": "SOL", "symbol": "SOL"},
    ],
    "LIGH": [
        {"metric": "LTX", "symbol": "LTX"},
    ],
}


def _load_header(lines: list[str]) -> tuple[list[str], list[str]]:
    """Return (symbol_map, station_map) token lists from the header rows."""
    symbol_map: list[str] = []
    station_map: list[str] = []
    for raw in lines:
        stripped = raw.strip()
        if not stripped:
            continue
        tokens = stripped.split()
        if tokens[0] == "STN":
            # STN YYYYMMDD GG MM WS WD WGS ... -> data columns after 4
            symbol_map = tokens[4:]
        elif tokens[0] == "xxx":
            station_map = tokens[1:]
        if symbol_map and station_map:
            break
    return symbol_map, station_map


def _column_for(symbol: str, station: str, symbol_map: list[str], station_map: list[str]) -> Optional[int]:
    """Return 0-based index in the data tokens for a symbol+station.

    Scans every occurrence of `symbol`; picks the one where the station
    map column equals `station`.
    """
    if not symbol_map:
        return None
    for i, sym in enumerate(symbol_map):
        if sym != symbol:
            continue
        stat = station_map[i] if i < len(station_map) else ""
        if stat == station:
            return i
    return None


def parse_one_minute_file(
    path: Path,
    sensor_specs: dict[str, dict],
    default_ts: Optional[datetime] = None,
) -> list[ParsedRecord]:
    """Parse a daily WIDN file into per-metric records."""
    try:
        content = path.read_text(encoding="utf-8", errors="replace")
    except (OSError, UnicodeError):
        return []
    lines = content.splitlines()

    symbol_map, station_map = _load_header(lines)

    # Determine each sensor's station from spec (fallback 04).
    # sensor_specs: {code: {sensor_id, station, ...}}
    station_of: dict[str, str] = {}
    specs_metrics: dict[str, list[dict]] = {}
    for code, spec in sensor_specs.items():
        station = spec.get("station", "04")
        station_of[code] = station
        metrics = SENSOR_METRICS.get(code, [])
        if not metrics:
            # Fall back to a single 'value' metric using the symbol field.
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
                valid = val is not None
                rec.metrics.append(
                    ParsedMetric(
                        code, m["metric"], val,
                        token if not valid else None,
                        valid, line,
                    )
                )
        records.append(rec)
    return records


# Backward-compatible alias for tests/older imports.
def parse_raw_dcp_file(path, sensor_specs, default_ts=None):
    return []  # raw fallback superseded by WIDN primary parser


def parse_site_batch(
    one_minute_path: Path,
    raw_sensor_path: Path,
    sensor_specs: dict[str, dict],
    default_ts: Optional[datetime] = None,
) -> dict[str, list[ParsedMetric]]:
    """Parse a site's WIDN file, returning metric lists keyed by code."""
    result: dict[str, list[ParsedMetric]] = {}
    if not one_minute_path.exists():
        return result
    for rec in parse_one_minute_file(one_minute_path, sensor_specs, default_ts):
        for metric in rec.metrics:
            result.setdefault(metric.sensor_code, []).append(metric)
    return result