-- =====================================================================
-- Monitoring Aloptama V2 - Migration 009
-- Wide-columnar hypertable + compressed archive (TimescaleDB best practice).
--
-- Replaces the EAV model for the WORKER's writes. The legacy `telemetry`
-- EAV table is deliberately KEPT for now so existing SLA/OLA dashboard and
-- backfill stay functional while the wide path is verified; it can be
-- dropped later once the wide tables are authoritative.
--
-- 1. awos_metrics : one row per (time, site), with explicit typed columns.
-- 2. PK (time, site_id) -> ON CONFLICT (time, site_id) idempotent upserts.
-- 3. Compression grouped by site_id (segmentby) so each site's series
--    compresses efficiently; custom retention keeps hot recent chunks.
-- =====================================================================

CREATE TABLE IF NOT EXISTS awos_metrics (
    time            TIMESTAMPTZ       NOT NULL,
    site_id         VARCHAR(16)       NOT NULL,   -- '04' | '22' | 'middle' (WIDN site code)

    -- ATRH
    temp_c          DOUBLE PRECISION,
    dewp_c          DOUBLE PRECISION,
    rh_pct          DOUBLE PRECISION,

    -- BARO
    qnh_hpa         DOUBLE PRECISION,
    da_ft           DOUBLE PRECISION,

    -- ANEM
    wind_speed_kt   DOUBLE PRECISION,
    wind_dir_deg    DOUBLE PRECISION,
    gust_speed_kt   DOUBLE PRECISION,
    gust_dir_deg    DOUBLE PRECISION,

    -- RVR / ALS (04 also carries ALS + D/N)
    rvr_m           DOUBLE PRECISION,
    vis_m           DOUBLE PRECISION,
    als_cd          DOUBLE PRECISION,
    rvr_dn          TEXT,                          -- 'D' / 'N' (/ 'M' missing)
    rls             DOUBLE PRECISION,

    -- CEL
    lr1_100ft       DOUBLE PRECISION,
    sky_code        TEXT,

    -- PWX / RAIN
    precip_mm       DOUBLE PRECISION,
    present_weather TEXT,                          -- PW code e.g. 'RERA'

    -- SOLR / LIGH (Middle)
    solar_wm2       DOUBLE PRECISION,
    lightning       TEXT,

    -- bookkeeping
    raw_line        TEXT,

    PRIMARY KEY (time, site_id)
);

-- TimescaleDB hypertable on time (partitioning column must be in PK).
SELECT create_hypertable('awos_metrics', 'time', if_not_exists => TRUE);

-- Indexes for the windowed queries the dashboard uses.
CREATE INDEX IF NOT EXISTS idx_awos_metrics_site_time
    ON awos_metrics (site_id, time DESC);

-- ---------------------------------------------------------------------
-- Columnar compression grouped by site_id (segmentby). Grouping by site
-- keeps each site's 1-minute series contiguous -> far better compression
-- than the EAV table, and range scans per site stay fast.
-- ---------------------------------------------------------------------
ALTER TABLE awos_metrics SET (
    timescaledb.compress,
    timescaledb.compress_segmentby = 'site_id'
);

-- Compress chunks older than 7 days automatically.
SELECT add_compression_policy('awos_metrics', INTERVAL '7 days', if_not_exists => TRUE);

-- Retention: keep 2 years of high-cardinality 1-minute observations.
SELECT add_retention_policy('awos_metrics', INTERVAL '2 years', if_not_exists => TRUE);