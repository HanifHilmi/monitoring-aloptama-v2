"""Component -> awos_metrics column map + wide-row grouping helpers.

A component is VALID when ANY of its wide columns is non-NULL for that
(time, site). Component availability is computed from awos_metrics with
SQL ``COUNT(*) FILTER`` aggregates by the API layer.
"""
from __future__ import annotations

# component_code -> list of awos_metrics column names that prove it has data
COMPONENT_COLUMNS: dict[str, list[str]] = {
    "ATRH": ["temp_c", "dewp_c", "rh_pct"],
    "BARO": ["qnh_hpa", "da_ft"],
    "ANEM": ["wind_speed_kt", "wind_dir_deg", "gust_speed_kt", "gust_dir_deg"],
    "RVR": ["rvr_m", "vis_m", "als_cd", "als_dn", "rls"],
    "CEL": ["lr1_100ft", "sky_condition"],
    "PWX": ["precip_mm", "present_weather"],
    "RAIN": ["precip_mm"],
    "SOLR": ["solar_wm2"],
    "LIGH": ["lightning"],
}

# Non-DCP component codes per site (7/site => 18 non-DCP + 3 DCP = 21).
SITE_COMPONENTS: dict[str, list[str]] = {
    "04": ["ATRH", "BARO", "ANEM", "RVR", "CEL", "PWX"],
    "22": ["ATRH", "BARO", "ANEM", "RVR", "CEL", "PWX"],
    "middle": ["ATRH", "BARO", "ANEM", "RAIN", "SOLR", "LIGH"],
}

# Wide-row metric alias -> (awos_metrics column, is_text) mapping.
WIDE_COLUMNS: dict[str, tuple[str, bool]] = {
    "TEMP": ("temp_c", False), "DEWP": ("dewp_c", False), "RH": ("rh_pct", False),
    "QNH": ("qnh_hpa", False), "DA": ("da_ft", False),
    "WS": ("wind_speed_kt", False), "WD": ("wind_dir_deg", False),
    "WGS": ("gust_speed_kt", False), "WGD": ("gust_dir_deg", False),
    "RVR": ("rvr_m", False), "VIS": ("vis_m", False), "ALS": ("als_cd", False),
    "D/N": ("als_dn", True), "RLS": ("rls", False),
    "LR1": ("lr1_100ft", False), "SKY": ("sky_condition", True),
    "RA": ("precip_mm", False), "PW": ("present_weather", True),
    "SOL": ("solar_wm2", False), "LTX": ("lightning", True),
}


def group_wide(parsed_by_code: dict, site_id: str) -> list[dict]:
    """Collapse EAV metrics into one wide row per (minute, site)."""
    rows: dict = {}
    for code, metrics in (parsed_by_code or {}).items():
        for m in metrics or []:
            if not m.is_valid or m.ts is None:
                continue
            col = WIDE_COLUMNS.get(m.metric)
            if not col:
                continue
            column, is_text = col
            key = m.ts.replace(second=0, microsecond=0)
            row = rows.setdefault(key, {"time": key, "site_id": site_id})
            if is_text:
                # Empty text field = healthy, no event -> empty string.
                row[column] = (m.text_value or "")
            else:
                # Empty numeric field = healthy -> 0. Explicit missing is
                # skipped above (is_valid False) so the column stays NULL.
                row[column] = m.value if m.value is not None else 0
    # WGS/WGD are tied to WS/WD: if wind is missing (///) the sensor is
    # OFFLINE -> gust = NULL. If wind is ONLINE/valid, gust is 0 when the
    # WGS/WGD fields are missing or empty (offline WGS/WGD columns parse
    # to None and are skipped above, so default them to 0 here).
    for row in rows.values():
        wind_ok = row.get("wind_speed_kt") is not None and row.get("wind_dir_deg") is not None
        if not wind_ok:
            row["gust_speed_kt"] = None
            row["gust_dir_deg"] = None
        else:
            if row.get("gust_speed_kt") is None:
                row["gust_speed_kt"] = 0
            if row.get("gust_dir_deg") is None:
                row["gust_dir_deg"] = 0
    return list(rows.values())
