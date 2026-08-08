-- =====================================================================
-- Monitoring Aloptama V2 - Migration 004
-- Add WIDN symbol/station mapping columns to sensors.
--
-- The 1-minute WIDN report (`091OneMinute.<date>.dat`) has per-column
-- airport stations (04 / 22 / M) and measurement symbols in its header.
-- The parser auto-maps sensor columns using `symbol` + `station` instead
-- of brittle hardcoded positions.
-- =====================================================================

ALTER TABLE sensors ADD COLUMN IF NOT EXISTS symbol   TEXT;
ALTER TABLE sensors ADD COLUMN IF NOT EXISTS station   TEXT;

-- Runway 04 uses WIDN station "04"
UPDATE sensors SET symbol = 'TEMP', station = '04' WHERE code = 'ATRH' AND site_id = (SELECT id FROM sites WHERE slug = '04');
UPDATE sensors SET symbol = 'QNH',  station = '04' WHERE code = 'BARO' AND site_id = (SELECT id FROM sites WHERE slug = '04');
UPDATE sensors SET symbol = 'WS',   station = '04' WHERE code = 'ANEM' AND site_id = (SELECT id FROM sites WHERE slug = '04');
UPDATE sensors SET symbol = 'VIS',  station = '04' WHERE code = 'PWX'  AND site_id = (SELECT id FROM sites WHERE slug = '04');
UPDATE sensors SET symbol = 'SKY',  station = '04' WHERE code = 'CEL'  AND site_id = (SELECT id FROM sites WHERE slug = '04');
UPDATE sensors SET symbol = 'RVR',  station = '04' WHERE code = 'RVR'  AND site_id = (SELECT id FROM sites WHERE slug = '04');
UPDATE sensors SET symbol = 'ALS',  station = '04' WHERE code = 'ALS'  AND site_id = (SELECT id FROM sites WHERE slug = '04');

-- Runway 22 uses WIDN station "22"
UPDATE sensors SET symbol = 'TEMP', station = '22' WHERE code = 'ATRH' AND site_id = (SELECT id FROM sites WHERE slug = '22');
UPDATE sensors SET symbol = 'QNH',  station = '22' WHERE code = 'BARO' AND site_id = (SELECT id FROM sites WHERE slug = '22');
UPDATE sensors SET symbol = 'WS',   station = '22' WHERE code = 'ANEM' AND site_id = (SELECT id FROM sites WHERE slug = '22');
UPDATE sensors SET symbol = 'VIS',  station = '22' WHERE code = 'PWX'  AND site_id = (SELECT id FROM sites WHERE slug = '22');
UPDATE sensors SET symbol = 'SKY',  station = '22' WHERE code = 'CEL'  AND site_id = (SELECT id FROM sites WHERE slug = '22');
UPDATE sensors SET symbol = 'RVR',  station = '22' WHERE code = 'RVR'  AND site_id = (SELECT id FROM sites WHERE slug = '22');

-- Runway Middle uses WIDN station "M"
UPDATE sensors SET symbol = 'TEMP', station = 'M' WHERE code = 'ATRH' AND site_id = (SELECT id FROM sites WHERE slug = 'middle');
UPDATE sensors SET symbol = 'QNH',  station = 'M' WHERE code = 'BARO' AND site_id = (SELECT id FROM sites WHERE slug = 'middle');
UPDATE sensors SET symbol = 'WS',   station = 'M' WHERE code = 'ANEM' AND site_id = (SELECT id FROM sites WHERE slug = 'middle');
UPDATE sensors SET symbol = 'RA',   station = 'M' WHERE code = 'RAIN' AND site_id = (SELECT id FROM sites WHERE slug = 'middle');
UPDATE sensors SET symbol = 'SOL',  station = 'M' WHERE code = 'SOLR' AND site_id = (SELECT id FROM sites WHERE slug = 'middle');
UPDATE sensors SET symbol = 'LTX',  station = 'M' WHERE code = 'LIGH' AND site_id = (SELECT id FROM sites WHERE slug = 'middle');