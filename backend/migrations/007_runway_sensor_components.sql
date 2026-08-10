-- =====================================================================
-- Monitoring Aloptama V2 - Migration 007
-- Runway sensor components rework.
--
-- 1. ALS is part of the RVR component on RWY04 (metrics ALS + D/N are
--    already parsed under the RVR sensor). Disable the SEPARATE ALS
--    sensor row so every runway site has exactly 7 components:
--      RWY04: DCP, ATRH, BARO, ANEM, PWX, CEL, RVR(ALS/D-N)
--      RWY22: DCP, ATRH, BARO, ANEM, PWX, CEL, RVR
--      MID  : DCP, ATRH, BARO, ANEM, RAIN, SOLR, LIGH
-- 2. DCP is a STATE sensor (online/offline like CDP), not a raw value
--    from /oneminute/. `is_state=TRUE` marks it; the backend derives it:
--    online if ANY other component has at least one non-/// value.
-- 3. chart_metrics: declarative list of which telemetry metrics belong
--    on a component's combined chart (the frontend groups them).
-- =====================================================================

-- RWY04: separately-seeded ALS sensor folded into RVR -> disable it.
UPDATE sensors SET is_enabled = FALSE, is_state = TRUE
WHERE code = 'ALS'
  AND site_id = (SELECT id FROM sites WHERE slug = '04');

-- Mark DCP sensors as state-only (RWY04, RWY22, MIDDLE).
UPDATE sensors SET is_state = TRUE
WHERE code = 'DCP';

-- Declarative combined-chart metric sets per sensor code.
ALTER TABLE sensors ADD COLUMN IF NOT EXISTS chart_metrics TEXT;

UPDATE sensors SET chart_metrics = 'TEMP,DEWP,RH'  WHERE code = 'ATRH';
UPDATE sensors SET chart_metrics = 'QNH,DA'        WHERE code = 'BARO';
UPDATE sensors SET chart_metrics = 'WS,WD'         WHERE code = 'ANEM';
UPDATE sensors SET chart_metrics = 'RVR,VIS'       WHERE code = 'RVR';
UPDATE sensors SET chart_metrics = 'PW,RA'         WHERE code = 'PWX';
UPDATE sensors SET chart_metrics = 'LR1,SKY'       WHERE code = 'CEL';
UPDATE sensors SET chart_metrics = 'RA'            WHERE code = 'RAIN';
UPDATE sensors SET chart_metrics = 'SOL'           WHERE code = 'SOLR';
UPDATE sensors SET chart_metrics = 'LTX'           WHERE code = 'LIGH';
-- RWY04 RVR additionally includes ALS + D/N (same component card).
UPDATE sensors SET chart_metrics = 'RVR,VIS,ALS,D/N'
WHERE code = 'RVR' AND site_id = (SELECT id FROM sites WHERE slug = '04');