"""Log parsers for AWOS CDP telemetry.

Two parsing tiers:

1. **Primary** — 1-minute aggregated logs (``*OneMinute*.dat``) in the
   ``/oneminute/`` directory. Each line is a timestamped record where
   sensor values are whitespace-separated columns; column positions are
   configured per-sensor in the ``sensors.position`` master column.

2. **Fallback** — raw DCP telemetry in the ``/sensor/`` directory. When a
   field in the 1-minute log is missing/corrupt/unreadable, the same
   timestamp's raw DCP line is parsed using *exact character position
   slicing* (``sensors.fallback_slice`` = ``"START:END"``, 1-based).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

# ----------------------------------------------------------------------
# Dataclasses
# ----------------------------------------------------------------------
@dataclass
class ParsedSample:
    """One parsed sensor value for a given timestamp."""

    ts: datetime
    sensor_code: str
    value: Optional[float]
    status: str  # ok | corrupt | missing | invalid | out_of_range
    raw: str = ""


@dataclass
class ParsedRecord:
    """All sensor samples extracted from a single log line."""

    ts: datetime
    samples: list[ParsedSample] = field(default_factory=list)


# ----------------------------------------------------------------------
# Timestamp parsing helpers
# ----------------------------------------------------------------------
_TS_ISO_RE = re.compile(
    r"(?P<y>\d{4})[-/](?P<m>\d{1,2})[-/](?P<d>\d{1,2})"
    r"[ T](?P<H>\d{1,2}):(?P<M>\d{1,2})(?::(?P<S>\d{1,2}))?"
)
_TS_DCP_RE = re.compile(
    r"(?P<y>\d{4})(?P<m>\d{2})(?P<d>\d{2})(?P<H>\d{2})(?P<M>\d{2})(?P<S>\d{2})"
)


def _ts_from_iso(match: re.Match) -> Optional[datetime]:
    try:
        return datetime(
            int(match.group("y")),
            int(match.group("m")),
            int(match.group("d")),
            int(match.group("H")),
            int(match.group("M")),
            int(match.group("S") or 0),
            tzinfo=timezone.utc,
        )
    except ValueError:
        return None


def _ts_from_dcp(match: re.Match) -> Optional[datetime]:
    try:
        return datetime(
            int(match.group("y")),
            int(match.group("m")),
            int(match.group("d")),
            int(match.group("H")),
            int(match.group("M")),
            int(match.group("S")),
            tzinfo=timezone.utc,
        )
    except ValueError:
        return None


def _extract_ts_and_data(line: str) -> tuple[Optional[datetime], str]:
    """Extract the UTC timestamp and the remainder of the line after it.

    The 1-minute log format is ``<TIMESTAMP> <COL1> <COL2> ...`` where the
    timestamp may be ISO (``2026-01-01 00:00:00``, split across two
    whitespace tokens) or compact DCP (``20260101000000``, a single token).
    Returning the trailing substring lets the positional parser operate on
    sensor data columns only, so ``position`` is a 1-based index into the
    values *after* the timestamp.
    """
    iso = _TS_ISO_RE.search(line)
    if iso:
        ts = _ts_from_iso(iso)
        if ts is not None:
            return ts, line[iso.end():]

    dcp = _TS_DCP_RE.search(line)
    if dcp:
        ts = _ts_from_dcp(dcp)
        if ts is not None:
            return ts, line[dcp.end():]

    return None, line


def _parse_ts_from_line(line: str) -> Optional[datetime]:
    """Extract UTC timestamp from a log line (ISO or DCP compact format)."""
    ts, _ = _extract_ts_and_data(line)
    return ts


def parse_timestamp_from_filename(filename: str) -> Optional[datetime]:
    """Extract timestamp from a 1-minute log filename, e.g.
    ``DCPA202601010000.OneMinute.dat`` -> 2026-01-01T00:00:00Z.
    """
    m = re.search(r"(\d{12})", filename)
    if not m:
        return None
    try:
        return datetime.strptime(m.group(1), "%Y%m%d%H%M").replace(tzinfo=timezone.utc)
    except ValueError:
        return None


# ----------------------------------------------------------------------
# Value coercion
# ----------------------------------------------------------------------
def coerce_value(raw: str) -> Optional[float]:
    """Coerce a raw string field to float.

    Returns None for empty / non-numeric tokens.
    """
    token = raw.strip()
    if not token:
        return None
    for cand in (token.replace(",", "."), token):
        try:
            return float(cand)
        except ValueError:
            continue
    return None


# ----------------------------------------------------------------------
# 1-minute log parser (primary)
# ----------------------------------------------------------------------
def parse_one_minute_file(
    path: Path,
    sensor_specs: dict[str, dict],
    default_ts: Optional[datetime] = None,
) -> list[ParsedRecord]:
    """Parse a ``*OneMinute*.dat`` aggregated file.

    Expected line layout (space-separated):
        <TIMESTAMP> <COL1> <COL2> ... <COLN>

    ``sensor_specs`` maps a sensor code to its config:
        {"code": {"position": int} }   # 1-based column index
    Sensors without a position are skipped.

    If a line has no timestamp, ``default_ts`` (from the filename) is used.
    """
    records: list[ParsedRecord] = []
    try:
        content = path.read_text(encoding="utf-8", errors="replace")
    except (OSError, UnicodeError):
        return records

    for raw_line in content.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        ts, data_part = _extract_ts_and_data(line)
        ts = ts or default_ts
        if ts is None:
            continue

        rec = ParsedRecord(ts=ts)
        tokens = data_part.split()
        for code, spec in sensor_specs.items():
            pos = spec.get("position", 0)
            if pos <= 0 or pos > len(tokens):
                rec.samples.append(ParsedSample(ts, code, None, "missing", line))
                continue
            token = tokens[pos - 1]
            val = coerce_value(token)
            if val is None:
                rec.samples.append(ParsedSample(ts, code, None, "corrupt", line))
            else:
                rec.samples.append(ParsedSample(ts, code, val, "ok", line))
        records.append(rec)
    return records


# ----------------------------------------------------------------------
# Raw DCP parser (fallback - exact character position slicing)
# ----------------------------------------------------------------------
def parse_raw_dcp_file(
    path: Path,
    sensor_specs: dict[str, dict],
    default_ts: Optional[datetime] = None,
) -> list[ParsedRecord]:
    """Parse raw DCP telemetry using exact character slicing.

    ``sensor_specs`` maps a sensor code to:
        {"fallback_slice": "START:END"}   # 1-based, inclusive END

    For each line, the timestamp is detected from the line itself or the
    ``default_ts`` derived from the file. Each sensor field is pulled via
    ``line[start-1:end]``.
    """
    records: list[ParsedRecord] = []
    try:
        content = path.read_text(encoding="utf-8", errors="replace")
    except (OSError, UnicodeError):
        return records

    for raw_line in content.splitlines():
        line = raw_line.rstrip("\n")
        if not line.strip():
            continue
        ts = _parse_ts_from_line(line) or default_ts
        if ts is None:
            continue

        rec = ParsedRecord(ts=ts)
        for code, spec in sensor_specs.items():
            slice_spec = spec.get("fallback_slice")
            if not slice_spec or ":" not in slice_spec:
                continue
            try:
                start_s, end_s = slice_spec.split(":", 1)
                start = int(start_s) - 1
                end = int(end_s)
            except ValueError:
                continue

            # ``end`` may exceed the line length when a fixed-width field
            # runs to the very end of the record; Python slicing clamps it.
            if start < 0 or start >= len(line) or end <= start:
                rec.samples.append(ParsedSample(ts, code, None, "missing", line))
                continue

            token = line[start:end].strip()
            val = coerce_value(token)
            if val is None:
                rec.samples.append(ParsedSample(ts, code, None, "corrupt", line))
            else:
                rec.samples.append(ParsedSample(ts, code, val, "ok", line))
        records.append(rec)
    return records


# ----------------------------------------------------------------------
# Site-aware dispatch with fallback rules
# ----------------------------------------------------------------------
def parse_site_batch(
    one_minute_path: Path,
    raw_sensor_path: Path,
    sensor_specs: dict[str, dict],
    default_ts: Optional[datetime] = None,
) -> dict[str, list[ParsedSample]]:
    """Parse a site's 1-minute file with automatic raw-DCP fallback per sensor.

    Returns a mapping of ``sensor_code -> list[ParsedSample]``.

    Primary strategy: read the 1-minute file. For any sample with status
    ``missing``/``corrupt`` (unreadable field), fall back to the raw DCP
    file for that timestamp and re-parse that specific sensor using exact
    character slicing.

    If the 1-minute file itself is absent, the raw DCP file is parsed as
    the sole source.
    """
    result: dict[str, list[ParsedSample]] = {}

    if one_minute_path.exists():
        records = parse_one_minute_file(one_minute_path, sensor_specs, default_ts)
        for rec in records:
            for sample in rec.samples:
                result.setdefault(sample.sensor_code, []).append(sample)
    else:
        records = parse_raw_dcp_file(raw_sensor_path, sensor_specs, default_ts)
        for rec in records:
            for sample in rec.samples:
                result.setdefault(sample.sensor_code, []).append(sample)
        return result

    # Fallback pass: fix corrupt/missing samples from raw DCP file
    if raw_sensor_path.exists():
        raw_records = parse_raw_dcp_file(raw_sensor_path, sensor_specs, default_ts)
        raw_by_ts: dict[datetime, dict[str, ParsedSample]] = {}
        for rec in raw_records:
            bucket = raw_by_ts.setdefault(rec.ts, {})
            for sample in rec.samples:
                bucket[sample.sensor_code] = sample

        for code, samples in result.items():
            for sample in samples:
                if sample.status in ("corrupt", "missing"):
                    raw = raw_by_ts.get(sample.ts, {}).get(code)
                    if raw is not None and raw.status == "ok":
                        sample.value = raw.value
                        sample.status = raw.status
                        sample.raw = raw.raw

    return result