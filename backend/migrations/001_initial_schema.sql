-- =====================================================================
-- Monitoring Aloptama V2 - Initial Schema (PostgreSQL + TimescaleDB)
-- CDP SLA / Sensor OLA engine
-- =====================================================================

-- ---------------------------------------------------------------------
-- 1. MASTER TABLES
-- ---------------------------------------------------------------------

-- CDP nodes (system-level connectivity tracking for SLA)
CREATE TABLE IF NOT EXISTS cdp_nodes (
    id            SERIAL PRIMARY KEY,
    name          TEXT NOT NULL UNIQUE,          -- 'CDP1' | 'CDP2'
    ip_address    INET NOT NULL,
    mount_path    TEXT NOT NULL,                 -- /mnt/cdp1_logs/
    is_active     BOOLEAN NOT NULL DEFAULT TRUE,
    role          TEXT NOT NULL DEFAULT 'passive'
                  CHECK (role IN ('active', 'passive')),
    status        TEXT NOT NULL DEFAULT 'unknown'
                  CHECK (status IN ('up', 'down', 'unknown')),
    created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Site master (three runway sites)
CREATE TABLE IF NOT EXISTS sites (
    id            SERIAL PRIMARY KEY,
    code          TEXT NOT NULL UNIQUE,          -- 'RWY04' | 'RWY22' | 'RWYMID'
    name          TEXT NOT NULL,                 -- Runway 04 / 22 / Middle
    slug          TEXT NOT NULL UNIQUE,          -- route slug: '04' | '22' | 'middle'
    file_prefixes TEXT[] NOT NULL DEFAULT '{}',  -- ['DCPA','RWYA'] alias matches
    created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Sensor master (7 per site)
CREATE TABLE IF NOT EXISTS sensors (
    id             SERIAL PRIMARY KEY,
    site_id        INTEGER NOT NULL REFERENCES sites(id) ON DELETE CASCADE,
    code           TEXT NOT NULL,                -- e.g. ATRH, BARO, ANEM, PWX, CEL, RVR, ALS...
    name           TEXT NOT NULL,                -- display name
    category       TEXT NOT NULL,                -- e.g. 'thermohygrometer','barometer',
                                                 --     'anemometer','present_weather',
                                                 --     'ceilometer','rvr','rain_gauge',
                                                 --     'solar_radiation','lightning_detector',
                                                 --     'dcp'
    unit           TEXT,                         -- C, %, hPa, kt, m, m, mm, W/m2, ...
    min_valid      DOUBLE PRECISION,             -- physical validity range (min)
    max_valid      DOUBLE PRECISION,             -- physical validity range (max)
    position       INTEGER NOT NULL DEFAULT 0,   -- column position in 1-min log
    fallback_slice TEXT,                         -- 'START:END' char slice in raw DCP line
    is_enabled     BOOLEAN NOT NULL DEFAULT TRUE,
    created_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (site_id, code)
);

-- ---------------------------------------------------------------------
-- 2. CDP CONNECTIVITY LOG (SLA source) - hypertable
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS cdp_connectivity (
    time          TIMESTAMPTZ NOT NULL,
    cdp_id        INTEGER NOT NULL REFERENCES cdp_nodes(id) ON DELETE CASCADE,
    reachable     BOOLEAN NOT NULL,
    rtt_ms        DOUBLE PRECISION,
    error_message TEXT,
    PRIMARY KEY (time, cdp_id)
);

-- ---------------------------------------------------------------------
-- 3. TELEMETRY HYPERTABLE (OLA source) - 1-minute sensor values
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS telemetry (
    time        TIMESTAMPTZ NOT NULL,
    sensor_id   INTEGER NOT NULL REFERENCES sensors(id) ON DELETE CASCADE,
    value       DOUBLE PRECISION,
    status      TEXT NOT NULL DEFAULT 'ok'
                CHECK (status IN ('ok', 'corrupt', 'missing', 'invalid', 'out_of_range')),
    raw_line    TEXT,
    PRIMARY KEY (time, sensor_id)
);

-- ---------------------------------------------------------------------
-- 4. DOWNTIME EVENTS (state-machine SLA/OLA records)
--    start_time = state OPEN  -> begin downtime
--    end_time   = state CLOSE -> end downtime, duration computed
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS downtime_events (
    id               BIGSERIAL PRIMARY KEY,
    scope_type       TEXT NOT NULL CHECK (scope_type IN ('sla', 'ola')),
    entity_type      TEXT NOT NULL CHECK (entity_type IN ('cdp_node', 'sensor')),
    cdp_id           INTEGER REFERENCES cdp_nodes(id) ON DELETE CASCADE,
    sensor_id        INTEGER REFERENCES sensors(id) ON DELETE CASCADE,
    site_id          INTEGER REFERENCES sites(id) ON DELETE CASCADE,
    start_time       TIMESTAMPTZ NOT NULL,
    end_time         TIMESTAMPTZ,                     -- NULL while open
    duration_seconds BIGINT GENERATED ALWAYS AS (
        CASE WHEN end_time IS NULL THEN NULL
             ELSE EXTRACT(EPOCH FROM (end_time - start_time))::BIGINT
        END
    ) STORED,
    reason_code      TEXT,                            -- e.g. 'connectivity_loss','missing','corrupt'
    details          JSONB DEFAULT '{}',
    created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CHECK (
        (scope_type = 'sla' AND cdp_id  IS NOT NULL AND sensor_id IS NULL) OR
        (scope_type = 'ola' AND sensor_id IS NOT NULL AND cdp_id IS NULL)
    )
);
CREATE INDEX IF NOT EXISTS idx_downtime_events_lookup
    ON downtime_events (scope_type, entity_type, start_time DESC);

-- ---------------------------------------------------------------------
-- 5. DAILY SLA/OLA ROLLUP - pre-aggregated hypertable
--    Guarantees sub-200ms dashboard queries over 30+ day ranges
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS daily_sla_ola (
    weo_time             DATE NOT NULL,
    scope_type           TEXT NOT NULL CHECK (scope_type IN ('sla', 'ola')),
    entity_type          TEXT NOT NULL CHECK (entity_type IN ('cdp_node', 'sensor')),
    cdp_id               INTEGER NOT NULL DEFAULT 0,   -- 0 = not applicable (OLA)
    sensor_id            INTEGER NOT NULL DEFAULT 0,   -- 0 = not applicable (SLA)
    site_id              INTEGER,
    total_seconds        BIGINT NOT NULL,
    uptime_seconds       BIGINT NOT NULL,
    downtime_seconds     BIGINT NOT NULL,
    uptime_pct           DOUBLE PRECISION NOT NULL,
    open_events          INTEGER NOT NULL DEFAULT 0,
    closed_events        INTEGER NOT NULL DEFAULT 0,
    -- Composite PK: partition column (weo_time) must be part of every
    -- unique index/constraint for TimescaleDB hypertables. Sentinel 0
    -- in cdp_id/sensor_id represents "not applicable" so PK columns
    -- are never NULL.
    PRIMARY KEY (weo_time, scope_type, entity_type, cdp_id, sensor_id)
);

-- ---------------------------------------------------------------------
-- TimescaleDB hypertables
-- ---------------------------------------------------------------------
CREATE EXTENSION IF NOT EXISTS timescaledb;

SELECT create_hypertable('telemetry',        'time', if_not_exists => TRUE);
SELECT create_hypertable('cdp_connectivity', 'time', if_not_exists => TRUE);
SELECT create_hypertable('daily_sla_ola',    'weo_time', if_not_exists => TRUE);

-- telemetry chunk retention (keep 6 months of 1-min granularity)
SELECT add_retention_policy('telemetry', INTERVAL '6 months', if_not_exists => TRUE);

-- ---------------------------------------------------------------------
-- Indexes for fast range scans / downsampling queries
-- ---------------------------------------------------------------------
CREATE INDEX IF NOT EXISTS idx_telemetry_sensor_time
    ON telemetry (sensor_id, time DESC);
CREATE INDEX IF NOT EXISTS idx_cdp_conn_cdp_time
    ON cdp_connectivity (cdp_id, time DESC);

-- Rollup refresh policy: keep daily aggregates fresh every 5 minutes.
-- NOTE: manual refresh also invoked by the ingestion worker.
-- =====================================================================