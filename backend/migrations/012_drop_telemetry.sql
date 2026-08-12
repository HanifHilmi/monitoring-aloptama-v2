-- =====================================================================
-- Monitoring Aloptama V2 - Migration 012
-- Step-2: DROP the legacy EAV `telemetry` table. All reads/writes now
-- use the wide awos_metrics table (migrations 009-011 + step-1 codes).
-- =====================================================================

DROP TABLE IF EXISTS telemetry;