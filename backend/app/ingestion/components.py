"""Component -> awos_metrics column map + OLA validity helpers.

OLA = average % of the 21 configured components (7/site x 3 sites) that have
data at a given minute. A component is VALID when ANY of its wide columns is
non-NULL for that (time, site). DCP is site-level: ONLINE when any non-DCP
column on that site is present, OFFLINE only when ALL site columns are NULL.
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

TOTAL_COMPONENTS = (len(SITE_COMPONENTS["04"]) + 1) * len(SITE_COMPONENTS)  # 7*3 = 21


def site_components(site_slug: str) -> list[str]:
    """Return the 7 component codes for a site (6 sensors + DCP)."""
    return list(SITE_COMPONENTS[site_slug]) + ["DCP"]


def wide_row_components(row: dict) -> list[str]:
    """Return the non-DCP component codes that have data in one wide row."""
    out = []
    for code, cols in COMPONENT_COLUMNS.items():
        if any(row.get(c) is not None for c in cols):
            out.append(code)
    return out


def row_dcp_online(row: dict) -> bool:
    """DCP is ONLINE when any non-DCP column on the site is present."""
    for code, cols in COMPONENT_COLUMNS.items():
        if any(row.get(c) is not None for c in cols):
            return True
    return False