"""Log parsers for AWOS CDP telemetry (WIDN format).

Two parsing tiers:

1. **Primary** — 1-minute aggregated logs (``091OneMinute.<YYYYMMDD>.dat``)
   in ``/oneminute/``. The file is *daily*; each data row is:
       STN YYYYMMDD HH MM <columns...>
   Header preamble rows (title, column names, station map, units) are
   skipped. Column positions are derived from the station-map row so the
   correct per-site sub-columns are used.

2. **Fallback** — raw DCP telemetry in ``/sensor/`` (``RWYA.DCP.<YYYYMMDDHH>.dat``).
   Lines look like:  ``[20260101000001] 7A00... 005 174 775 743 ...``
   When a 1-minute field is missing/corrupt, the raw line is parsed with
   exact character slicing configured in ``sensors.fallback_slice``.
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

    Handles both ISO (``2026-01-01 00:00:00``) and compact DCP
    (``20260101000000``) timestamps.
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
    """Extract a timestamp from a filename.

    Handles:
        ``091OneMinute.20260101.dat``        -> 2026-01-01T00:00:00Z
        ``RWYA.DCP.2026010100.dat``          -> 2026-01-01T00:00:00Z
        ``DCPA202601010000.OneMinute.dat``   -> 2026-01-01T00:00:00Z
    """
    m = re.search(r"(\d{12})", filename)
    if m:
        try:
            return datetime.strptime(m.group(1), "%Y%m%d%H%M").replace(tzinfo=timezone.utc)
        except ValueError:
            pass
    m = re.search(r"(\d{8})", filename)
    if m:
        try:
            return datetime.strptime(m.group(1), "%Y%m%d").replace(tzinfo=timezone.utc)
        except ValueError:
            pass
    return None


# ----------------------------------------------------------------------
# Value coercion
# ----------------------------------------------------------------------
def coerce_value(raw: str) -> Optional[float]:
    """Coerce a raw string field to float.

    Returns None for empty / non-numeric tokens (incl. '///', 'MMMM', 'M').
    """
    token = raw.strip()
    if not token:
        return None
    if set(token) <= {"M", "/", "."}:
        return None
    for cand in (token.replace(",", "."), token):
        try:
            return float(cand)
        except ValueError:
            continue
    return None


# ----------------------------------------------------------------------
# WIDN 1-minute log parser (primary)
# ----------------------------------------------------------------------
# Header markers that should be skipped before the first data row.
_HEADER_HINTS = (
    "One Minute Report",
    "STN YYYYMMDD",
    "xxx",
    "kt   deg",
)


def _is_header_line(tokens: list[str]) -> bool:
    """True when the row is part of the file header preamble."""
    if not tokens:
        return True
    first = tokens[0]
    if first in {"STN", "xxx"}:
        return True
    joined = " ".join(tokens)
    for hint in _HEADER_HINTS:
        if hint in joined:
            return True
    return False


def parse_one_minute_file(
    path: Path,
    sensor_specs: dict[str, dict],
    default_ts: Optional[datetime] = None,
) -> list[ParsedRecord]:
    """Parse a daily ``091OneMinute.<YYYYMMDD>.dat`` file.

    Each data row: ``STN YYYYMMDD HH MM <columns...>``.
    Tokens 4.. are data; ``sensor_specs[code]['position']`` is a 1-based
    index into those data tokens. The row timestamp is built from
    ``YYYYMMDD HH MM``.
    """
    records: list[ParsedRecord] = []
    try:
        content = path.read_text(encoding="utf-8", errors="replace")
    except (OSError, UnicodeError):
        return records

    # WIDN header rows: the station-map row (starts with 'xxx') and the
    # symbol row (first token 'STN') mark per-column airport (04/M/22)
    # and measurement symbol. We use them to auto-resolve column indices
    # per sensor so hardcoded positions are not needed.
    station_map: list[str] = []
    symbol_map: list[str] = []

    lines = content.splitlines()
    for raw_line in lines:
        line = raw_line.strip()
        if not line:
            continue
        tokens = line.split()
        if tokens and tokens[0] == "xxx":
            station_map = tokens
        elif tokens and tokens[0] == "STN":
            # STN YYYYMMDD GG MM WS WD WGS WGD ... (symbol header).
            # NOTE: the STN symbol row appears ABOVE the xxx station-map
            # row in this report, so do NOT break here — keep scanning
            # until both rows are captured.
            symbol_map = tokens[4:]
        if station_map and symbol_map:
            break

    resolved_positions: dict[str, int] = {}
    for code, spec in sensor_specs.items():
        pos = spec.get("position", 0)
        station = spec.get("station", "04")
        symbol_var = spec.get("symbol", "ATRH")
        if symbol_map:
            # Symbol row: find ALL occurrences of the symbol (a sensor like
            # RVR/VIS/SKY appears once per station block), then pick the one
            # whose station column matches this site's station.
            for i, sym in enumerate(symbol_map):
                if sym != symbol_var:
                    continue
                stat_col = station_map[i + 4] if (i + 4) < len(station_map) else ""
                if stat_col == station:
                    resolved_positions[code] = i + 1
                    break
        if code not in resolved_positions:
            # Fall back to configured position if auto-map unavailable.
            resolved_positions[code] = pos

    for raw_line in lines:
        line = raw_line.strip()
        if not line:
            continue
        tokens = line.split()
        # Data rows start with a station id then a compact date.
        if len(tokens) < 5 or not re.match(r"^\d{8}$", tokens[1]):
            # Old-style per-minute rows have leading timestamp.
            ts, data_part = _extract_ts_and_data(line)
            if ts is None or _is_header_line(tokens):
                continue
            data_tokens = data_part.split()
        else:
            # WIDN row: STN YYYYMMDD HH MM REST...
            try:
                ts = datetime.strptime(
                    f"{tokens[1]} {tokens[2]} {tokens[3]}", "%Y%m%d %H %M"
                ).replace(tzinfo=timezone.utc)
            except ValueError:
                continue
            data_tokens = tokens[4:]

        rec = ParsedRecord(ts=ts)
        for code, spec in sensor_specs.items():
            pos = resolved_positions.get(code, spec.get("position", 0))
            if pos <= 0 or pos > len(data_tokens):
                rec.samples.append(ParsedSample(ts, code, None, "missing", line))
                continue
            token = data_tokens[pos - 1]
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

    Primary strategy: read the 1-minute file. For any sample with status
    ``missing``/``corrupt`` (unreadable field), fall back to the raw DCP
    file for that timestamp and re-parse that specific sensor using exact
    character slicing. If the 1-minute file is absent, the raw DCP file is
    parsed as the sole source.
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