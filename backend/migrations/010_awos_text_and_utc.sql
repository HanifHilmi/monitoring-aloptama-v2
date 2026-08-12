-- =====================================================================
-- Monitoring Aloptama V2 - Migration 010
-- 1. Rename text columns to domain terms: rvr_dn -> als_dn,
--    sky_code -> sky_condition.
-- 2. Force the database connection default TIME ZONE to UTC so all
--    session/wal displays show UTC (stored instants are already UTC).
-- =====================================================================

ALTER TABLE awos_metrics RENAME COLUMN rvr_dn    TO als_dn;
ALTER TABLE awos_metrics RENAME COLUMN sky_code  TO sky_condition;