-- =====================================================================
-- Monitoring Aloptama V2 - Migration 013
-- Remove the dormant downtime/rollup subsystem.
--
-- 1. daily_sla_ola  : pre-aggregated rollup hypertable. It was rebuilt by
--    the (now-removed) manual rollup worker loop but never READ by any
--    endpoint - SLA/OLA is computed from the raw cdp_connectivity and
--    awos_metrics hypertables via COUNT(*) FILTER aggregates. The table
--    was empty in production (0 rows / 0 chunks), so dropping is safe.
-- 2. downtime_events: state-machine event log. The state machine was
--    removed (no reader; table empty). Dropping the table also removes
--    the conflicting entity_type/scope CHECK constraints created by
--    migrations 001/003/011 (the stale entity_type IN ('cdp_node',
--    'sensor') check and the original 'ola -> sensor_id IS NOT NULL'
--    check, which contradicted component-scoped events).
-- =====================================================================

DROP TABLE IF EXISTS daily_sla_ola;
DROP TABLE IF EXISTS downtime_events;
