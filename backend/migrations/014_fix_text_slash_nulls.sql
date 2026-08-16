-- =====================================================================
-- Monitoring Aloptama V2 - Migration 014
-- Repair offline TEXT values mis-stored as slash strings.
--
-- The oneminute files mark an OFFLINE sensor by filling the field with a
-- run of '/' (one per character of the slice: '/', '///', '/////', 29
-- slashes...). The old parser only exact-matched a fixed set ('///','//'),
-- so offline text fields were stored as slash strings instead of NULL,
-- which inflated data-availability calculations (e.g. Ceilometer was
-- reported 100% on 2026-01-19 when it was actually offline half the day).
--
-- The fixed parser (parsers.py) treats any slash run as offline. This
-- migration corrects the already-ingested rows so availability is
-- accurate. Idempotent: only pure-slash values are nulled.
-- =====================================================================

UPDATE awos_metrics SET sky_condition   = NULL WHERE sky_condition   ~ '^/+$';
UPDATE awos_metrics SET als_dn          = NULL WHERE als_dn          ~ '^/+$';
UPDATE awos_metrics SET present_weather = NULL WHERE present_weather ~ '^/+$';
UPDATE awos_metrics SET lightning       = NULL WHERE lightning       ~ '^/+$';
