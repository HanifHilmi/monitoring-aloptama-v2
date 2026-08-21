# Monitoring Aloptama V2 (AWOS CAT. III)

A self-hosted, high-performance monitoring platform for an **AWOS CAT. III** (Automated Weather Observing System) — an open-source alternative to Grafana for this domain. It monitors **2 CDP nodes** (SLA) and **7 sensor components per runway site** (OLA), computing precise uptime/validity percentages and storing 1-minute weather telemetry in **TimescaleDB**.

## Architecture

```
┌───────────────────────────────────────────────────────────────────────┐
│                    Frontend (Vue 3 + Vite + Tailwind)                 │
│               Apache ECharts time-series & downtime heatmaps          │
│     dynamic routes: /cat3/system | /cat3/runway/{04,22,middle}| /metar│
└──────────────────────────┬────────────────────────────────────────────┘
                           │ REST / JSON (FastAPI :8000)
┌──────────────────────────▼────────────────────────────────────────────┐
│                   Backend API (FastAPI) + Async ingestion             │
│   - API: /api/v1/status|telemetry|sla-ola|backfill|system (LTTB)      │
│   - Migrations at boot (idempotent, IF NOT EXISTS)                    │
│   - Backfill All job: CDP + DCP combined, dedupe, resume-on-refresh   │
└───────┬──────────────────────────────┬────────────────────────────────┘
        │                              │
┌───────▼───────────────┐   ┌──────────▼────────────────────────────────┐
│  Ingestion Worker     │   │  PostgreSQL + TimescaleDB (latest-pg16)   │
│  Active-passive CDP   │   │  - cdp_nodes, sites, sensors (master)     │
│  reader (failover)    │──▶│  - awos_metrics (wide hypertable)         │
│  watermark ingestion  │   │  - cdp_connectivity (SLA samples)         │
│  1-min shared 091 file│   │  SLA/OLA computed live (COUNT FILTER)     │
└───────────────────────┘   └───────────────────────────────────────────┘
```

## Data model
- **`awos_metrics`** — the **sole** wide time-series table (the old EAV `telemetry` was dropped, migration 012):
  - one row per `(time, site_id)` with explicit typed columns (`temp_c`, `dewp_c`, `rh_pct`, `qnh_hpa`, `da_ft`, `wind_speed_kt`, `wind_dir_deg`, gust `*`, `rvr_m`, `vis_m`, `als_cd`, `als_dn`, `lr1_100ft`, `sky_condition`, `precip_mm`, `present_weather`, `solar_wm2`, `lightning`, …).
  - PK `(time, site_id)` → idempotent `ON CONFLICT (time, site_id) DO UPDATE`.
  - Timescale hypertable with **columnar compression grouped by `site_id`** (segmentby) + compression/retention policies.
- **`cdp_connectivity`** — per-node reachability for SLA.
- SLA/OLA percentages are **computed live** via `COUNT(*) FILTER` aggregates over `awos_metrics` / `cdp_connectivity`. The former `downtime_events` state machine and `daily_sla_ola` rollups were removed (migration `013_remove_rollup_and_events.sql`).

### Data-saving contract
- Explicit missing tokens (`///`, `//`, `M`, `MM`, `N/A`, `---`) → **SQL NULL** (sensor OFFLINE).
- Empty/whitespace field → **NOT NULL** (sensor ONLINE, healthy, no event): numeric = `0`, text = `''`.
- WGS/WGD are tied to WS/WD: when WS/WD are missing → gust = `NULL`; when WS/WD are valid → missing gust = `0`.

## SLA / OLA
- **SLA** = reachability of each **CDP node**, independent of sensor data.
- **OLA** = average **data validity** across the **21 components** (7 per site × 3 sites): a component is valid for a minute when any of its `awos_metrics` columns is non-NULL. DCP is site-level (online when any non-DCP column is present). Percentages are **capped at 100.00**.

```
Uptime % = ((Total Seconds − Downtime Seconds) / Total Seconds) × 100%
```

## Data sources
| Node  | IP env var | Mount path        |
|-------|------------|-------------------|
| CDP 1 | `CDP1_IP`  | `/mnt/cdp1_logs/` |
| CDP 2 | `CDP2_IP`  | `/mnt/cdp2_logs/` |

Log layout (shared `091` file, read once for both CDP + DCP): `oneminute/*.dat` primary, `sensor/*` raw-DCP fallback (exact character-position slicing). Failover: nodes are probed every cycle (ICMP ping first, TCP-connect fallback); if the active node becomes unreachable, the healthiest passive node is promoted to active.

## Site sensor matrix (7 per site)
| Runway 04       | Runway 22       | Runway Middle    |
|-----------------|-----------------|------------------|
| DCP             | DCP             | DCP              |
| ATRH            | ATRH            | ATRH             |
| Dual Barometer  | Dual Barometer  | Dual Barometer   |
| Anemometer      | Anemometer      | Anemometer       |
| RVR + ALS       | RVR             | Rain Gauge       |
| Ceilometer      | Ceilometer      | Solar Radiation  |
| Present Weather | Present Weather | Lightning Detector |

## Env & roles (single toggle: `ENVIRONMENT`)
- **Backend (API)** — serves endpoints, runs **migrations** at boot, and runs the **Backfill All** job in-process.
- **Worker** — continuous **live ingestion** (watermark/frontier) of the latest minutes. It never migrates or backfills on boot.
- `ENVIRONMENT=dev` → schema is dropped/recreated on boot (fresh). Any other value (default `production`) → **never** resets. Migrations always run (idempotent `IF NOT EXISTS`). No `RESET_DB_ON_BOOT` / `ENABLE_BACKFILL_ON_BOOT` / `ENABLE_MIGRATIONS_ON_BOOT` flags.

## Quick start (Docker)
```bash
docker compose up --build -d
```
- Frontend: `http://localhost` (or `http://localhost:80`)
- API: `http://localhost:8000` → docs `/docs`

Data persists on the host via `PG_DATA_DIR` (**default `/var/lib/monitoring-aloptama-pg`**, overridable). Backfill-on-boot is **off**; run **Backfill All (CDP + DCP)** from Settings once on a fresh DB (combined job, dedupe, survives refresh).

## Local development (no Docker)
```bash
# Backend
cd backend && python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
# ensure DATABASE_URL points at a TimescaleDB instance

# Frontend
cd frontend && npm install && npm run dev
```

## API surface (v1)
| Method | Path                                   | Description                                  |
|--------|----------------------------------------|----------------------------------------------|
| GET    | `/health`                              | Liveness probe (Coolify/Docker healthcheck)  |
| GET    | `/api/v1/status/overview`               | CDP + per-component status                   |
| GET    | `/api/v1/telemetry/{site}`              | Wide awos_metrics window (LTTB optional)     |
| GET    | `/api/v1/sla-ola/summary`               | SLA + OLA (per-site & 21-component)          |
| GET    | `/api/v1/sla-ola/history`               | Daily SLA/OLA history                        |
| GET    | `/api/v1/sla-ola/downtime-map`          | Yearly downtime heatmap                      |
| POST   | `/api/v1/backfill/all/start`            | Start combined CDP+DCP backfill job          |
| GET    | `/api/v1/backfill/job/{id}/stream`      | SSE progress / resume (survives refresh)     |

## Tests
```bash
cd backend && pytest -q
cd frontend && npm run build   # compile check
```

## Persisting data across Coolify redeploys
The DB data lives on a **host bind-mount** (`PG_DATA_DIR`, default `/var/lib/monitoring-aloptama-pg`), not a compose named volume (which Coolify doesn't persist). Keep `ENVIRONMENT` unset/`production` so the schema is never reset. With the host path intact, redeploys preserve `awos_metrics` / SLA / OLA — you only run **Backfill All** once.

## License
Proprietary internal tooling.