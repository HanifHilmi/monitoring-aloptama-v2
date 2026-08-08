-- =====================================================================
-- Monitoring Aloptama V2 - Master Data Seed
-- CDP nodes + 3 runway sites + 7 sensors per site
-- =====================================================================

-- ---------------------------------------------------------------------
-- CDP nodes (Active-Passive)
-- ---------------------------------------------------------------------
INSERT INTO cdp_nodes (name, ip_address, mount_path, is_active, role, status)
VALUES
    ('CDP1', '172.70.55.162', '/mnt/cdp1_logs/', TRUE,  'active',  'unknown'),
    ('CDP2', '172.70.55.163', '/mnt/cdp2_logs/', TRUE,  'passive', 'unknown')
ON CONFLICT (name) DO NOTHING;

-- ---------------------------------------------------------------------
-- Sites
-- ---------------------------------------------------------------------
INSERT INTO sites (code, name, slug, file_prefixes)
VALUES
    ('RWY04',  'Runway 04',     '04',     ARRAY['DCPA','RWYA']),
    ('RWY22',  'Runway 22',     '22',     ARRAY['DCPB','RWYC']),
    ('RWYMID', 'Runway Middle', 'middle', ARRAY['DCPC','RWYB'])
ON CONFLICT (code) DO NOTHING;

-- ---------------------------------------------------------------------
-- Sensors - 7 per site
--   Runway 04     : DCP, ATRH, Dual Barometer, Anemometer, Present Weather,
--                   Ceilometer, RVR + ALS
--   Runway 22     : DCP, ATRH, Dual Barometer, Anemometer, Present Weather,
--                   Ceilometer, RVR
--   Runway Middle : DCP, ATRH, Dual Barometer, Anemometer, Rain Gauge,
--                   Solar Radiation, Lightning Detector
--
-- Position = column index (1-based) in the 1-minute aggregated file line.
-- fallback_slice = character slice 'START:END' applied to raw DCP lines
--                  in /sensor/ fallback mode (1-based, inclusive END).
-- =====================================================================
INSERT INTO sensors (site_id, code, name, category, unit, min_valid, max_valid, position, fallback_slice)
WITH s AS (SELECT id, code FROM sites)
SELECT
    s.id,
    v.code,
    v.name,
    v.category,
    v.unit,
    v.min_valid,
    v.max_valid,
    v.position,
    v.fallback_slice
FROM s
JOIN (VALUES
    -- ---- Runway 04 (sensor positions 1..8: DCPA header + 7 sensors) ----
    ('RWY04', 'DCP',  'DCP Platform',          'dcp',               NULL,   NULL,        NULL,     2, '1:4'),
    ('RWY04', 'ATRH', 'Air Temp & RH',         'thermohygrometer',   'C/%', -50.0,       60.0,      3, '5:20'),
    ('RWY04', 'BARO', 'Dual Barometer',        'barometer',          'hPa', 850.0,       1100.0,    4, '21:36'),
    ('RWY04', 'ANEM', 'Anemometer',            'anemometer',         'kt',  0.0,         250.0,     5, '37:52'),
    ('RWY04', 'PWX',  'Present Weather',       'present_weather',    NULL,  NULL,        NULL,      6, '53:68'),
    ('RWY04', 'CEL',  'Ceilometer',            'ceilometer',         'ft',  0.0,         25000.0,   7, '69:84'),
    ('RWY04', 'RVR',  'RVR w/ ALS',            'rvr',                'm',   0.0,         8000.0,    8, '85:104'),
    ('RWY04', 'ALS',  'Ambient Light Sensor',  'ambient_light',      'lux', 0.0,         200000.0,  9, '105:120'),

    -- ---- Runway 22 ----
    ('RWY22', 'DCP',  'DCP Platform',          'dcp',               NULL,   NULL,        NULL,     2, '1:4'),
    ('RWY22', 'ATRH', 'Air Temp & RH',         'thermohygrometer',   'C/%', -50.0,       60.0,      3, '5:20'),
    ('RWY22', 'BARO', 'Dual Barometer',        'barometer',          'hPa', 850.0,       1100.0,    4, '21:36'),
    ('RWY22', 'ANEM', 'Anemometer',            'anemometer',         'kt',  0.0,         250.0,     5, '37:52'),
    ('RWY22', 'PWX',  'Present Weather',       'present_weather',    NULL,  NULL,        NULL,      6, '53:68'),
    ('RWY22', 'CEL',  'Ceilometer',            'ceilometer',         'ft',  0.0,         25000.0,   7, '69:84'),
    ('RWY22', 'RVR',  'RVR',                   'rvr',                'm',   0.0,         8000.0,    8, '85:104'),

    -- ---- Runway Middle ----
    ('RWYMID', 'DCP',  'DCP Platform',          'dcp',               NULL,   NULL,        NULL,     2, '1:4'),
    ('RWYMID', 'ATRH', 'Air Temp & RH',         'thermohygrometer',   'C/%', -50.0,       60.0,      3, '5:20'),
    ('RWYMID', 'BARO', 'Dual Barometer',        'barometer',          'hPa', 850.0,       1100.0,    4, '21:36'),
    ('RWYMID', 'ANEM', 'Anemometer',            'anemometer',         'kt',  0.0,         250.0,     5, '37:52'),
    ('RWYMID', 'RAIN', 'Rain Gauge',            'rain_gauge',         'mm',  0.0,         500.0,     6, '53:68'),
    ('RWYMID', 'SOLR', 'Solar Radiation',       'solar_radiation',    'W/m2',0.0,         2000.0,    7, '69:84'),
    ('RWYMID', 'LIGH', 'Lightning Detector',    'lightning_detector', 'strikes', 0.0,     10000.0,   8, '85:104')
) AS v(site_code, code, name, category, unit, min_valid, max_valid, position, fallback_slice)
  ON s.code = v.site_code
ON CONFLICT (site_id, code) DO NOTHING;
