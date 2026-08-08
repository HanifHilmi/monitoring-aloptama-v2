-- =====================================================================
-- Monitoring Aloptama V2 - Migration 005
-- Rework telemetry for multi-metric, mixed-type WIDN data.
--
-- The WIDN 1-minute report contains, per station (04 / M / 22):
--   WS WD WGS WGD | TEMP DEWP RH | QNH | DA | ALS D/N VIS RVR RLS
--   | LR1 SKY | RA | PW | SOL | LTX
-- Some values are numeric, others strings (D/N, SKY, PW, LTX).
-- We store one row per (time, sensor_id, metric). `value` holds the
-- float when parseable; `text_value` holds the raw string otherwise.
--
-- SLA/OLA semantics:
--   - SLA = availability of the CDP oneminute file for the minute
--     (file present + parseable => UP, otherwise DOWN).
--   - OLA = availability % = valid samples / expected samples.
-- =====================================================================

-- Existing telemetry PK is (time, sensor_id). Rework to include metric.
ALTER TABLE telemetry ADD COLUMN IF NOT EXISTS metric TEXT NOT NULL DEFAULT 'value';
ALTER TABLE telemetry ADD COLUMN IF NOT EXISTS text_value TEXT;
ALTER TABLE telemetry ADD COLUMN IF NOT EXISTS is_valid BOOLEAN NOT NULL DEFAULT TRUE;

DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'telemetry_pkey') THEN
        ALTER TABLE telemetry DROP CONSTRAINT telemetry_pkey;
    END IF;
END $$;

-- TimescaleDB requires the partitioning column be part of every unique
-- index; (time, sensor_id, metric) satisfies that.
ALTER TABLE telemetry ADD PRIMARY KEY (time, sensor_id, metric);