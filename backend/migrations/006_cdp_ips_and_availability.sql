-- =====================================================================
-- Monitoring Aloptama V2 - Migration 006
-- Correct CDP node IPs, add component grouping to sensors.
--
-- The correct CDP addresses are 172.22.39.162 (CDP1) and
-- 172.22.39.163 (CDP2). The previous values (172.70.55.x) caused every
-- probe to fail, leaving CDP uptime at 0%.
--
-- Also adds `component` so each RWY site has exactly 7 availability
-- components for Data Availability math. At RWY04 the ALS sensor is part
-- of the RVR component (grouped as RVR_ALS).
-- =====================================================================

ALTER TABLE sensors ADD COLUMN IF NOT EXISTS component TEXT;

UPDATE cdp_nodes
SET ip_address = '172.22.39.162'
WHERE name = 'CDP1';

UPDATE cdp_nodes
SET ip_address = '172.22.39.163'
WHERE name = 'CDP2';

-- RWY04: ALS belongs to the RVR component -> grouped as RVR_ALS.
UPDATE sensors
SET component = 'RVR_ALS'
WHERE code IN ('RVR', 'ALS')
  AND site_id = (SELECT id FROM sites WHERE slug = '04');

-- Every other sensor is its own component.
UPDATE sensors
SET component = code
WHERE component IS NULL OR component = '';