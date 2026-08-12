-- =====================================================================
-- Monitoring Aloptama V2 - Migration 011
-- OLA downtime events keyed by (site_id, component_code) instead of an
-- EAV sensor_id, so OLA validity is computed from awos_metrics (wide).
-- This keeps `telemetry` table intact for parity until wide is verified.
-- =====================================================================

ALTER TABLE downtime_events ADD COLUMN IF NOT EXISTS component_code TEXT;

-- Relax the OLA CHECK: sensor_id no longer required for OLA events;
-- either (ola + sensor_id) or (ola + (site_id, component_code)).
ALTER TABLE downtime_events DROP CONSTRAINT IF EXISTS ck_downtime_scope_entity;
ALTER TABLE downtime_events ADD CONSTRAINT ck_downtime_scope_entity CHECK (
    (scope_type = 'sla' AND cdp_id IS NOT NULL AND sensor_id IS NULL) OR
    (scope_type = 'ola' AND cdp_id IS NULL AND (
        sensor_id IS NOT NULL OR (site_id IS NOT NULL AND component_code IS NOT NULL)
    ))
);

CREATE INDEX IF NOT EXISTS idx_downtime_events_ola_component
    ON downtime_events (scope_type, site_id, component_code, start_time DESC);
