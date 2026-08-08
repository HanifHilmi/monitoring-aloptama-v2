-- =====================================================================
-- Monitoring Aloptama V2 - Migration 003
-- Fix daily_sla_ola primary key for TimescaleDB compatibility.
--
-- Original schema used a composite PK (weo_time, scope_type, entity_type,
-- cdp_id, sensor_id) with NULLABLE cdp_id/sensor_id. Problems:
--   1. PostgreSQL PK columns are implicitly NOT NULL, so SLA rows
--      (sensor_id NULL) and OLA rows (cdp_id NULL) violated the PK.
--   2. TimescaleDB requires the partition column (weo_time) to be part
--      of every unique index/constraint on a hypertable.
--
-- Fix: composite PK including weo_time + NOT NULL entity columns using
-- 0 as a sentinel for "not applicable" (SLA rows: sensor_id=0; OLA rows:
-- cdp_id=0). Data is repopulated by the rollup rebuild on startup.
-- =====================================================================

-- TimescaleDB cleans up hypertable catalog entries on DROP.
-- CASCADE covers any dependent objects (indexes, policies).
DROP TABLE IF EXISTS daily_sla_ola CASCADE;

CREATE TABLE daily_sla_ola (
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
    -- unique index/constraint for TimescaleDB hypertables.
    PRIMARY KEY (weo_time, scope_type, entity_type, cdp_id, sensor_id)
);

-- Re-attach as a TimescaleDB hypertable.
SELECT create_hypertable('daily_sla_ola', 'weo_time', if_not_exists => TRUE);