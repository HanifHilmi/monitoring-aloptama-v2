-- =====================================================================
-- Monitoring Aloptama V2 - Migration 003
-- Fix daily_sla_ola primary key: nullable cdp_id/sensor_id cannot be
-- part of a PostgreSQL PRIMARY KEY (PK columns are implicitly NOT NULL).
-- SLA rows (sensor_id NULL) and OLA rows (cdp_id NULL) previously
-- violated the PK on insert, crashing the rollup rebuild at startup.
--
-- Rebuild the table with a surrogate id PK + a COALESCE-based unique
-- index that tolerates NULL entity ids. Data is repopulated by the
-- rollup rebuild that runs on worker/backend startup.
-- =====================================================================

-- TimescaleDB cleans up hypertable catalog entries on DROP.
-- CASCADE covers any dependent objects (indexes, policies).
DROP TABLE IF EXISTS daily_sla_ola CASCADE;

CREATE TABLE daily_sla_ola (
    id                   BIGSERIAL PRIMARY KEY,
    weo_time             DATE NOT NULL,
    scope_type           TEXT NOT NULL CHECK (scope_type IN ('sla', 'ola')),
    entity_type          TEXT NOT NULL CHECK (entity_type IN ('cdp_node', 'sensor')),
    cdp_id               INTEGER,
    sensor_id            INTEGER,
    site_id              INTEGER,
    total_seconds        BIGINT NOT NULL,
    uptime_seconds       BIGINT NOT NULL,
    downtime_seconds     BIGINT NOT NULL,
    uptime_pct           DOUBLE PRECISION NOT NULL,
    open_events          INTEGER NOT NULL DEFAULT 0,
    closed_events        INTEGER NOT NULL DEFAULT 0
);

-- Uniqueness across SLA (cdp_id set, sensor_id NULL) and OLA
-- (sensor_id set, cdp_id NULL) rows. COALESCE maps NULL -> 0 so the
-- composite key is never NULL.
CREATE UNIQUE INDEX uq_daily_sla_ola_entity
    ON daily_sla_ola (
        weo_time, scope_type, entity_type,
        COALESCE(cdp_id, 0), COALESCE(sensor_id, 0)
    );

-- Re-attach as a TimescaleDB hypertable.
SELECT create_hypertable('daily_sla_ola', 'weo_time', if_not_exists => TRUE);