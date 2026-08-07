# Monitoring Aloptama V2 (AWOS Cat III)

A high-performance, self-hosted AWOS (Automated Weather Observing System) Category III monitoring platform — a modern, open-source alternative to Grafana for this domain. It monitors CDP nodes and 7 sensors per runway site, computing precise **SLA** (system/CDP reachability) and **OLA** (sensor data validity) percentages.

## Architecture

```
┌────────────────────────────────────────────────────────────────────┐
│                          Frontend (Vue 3)                          │
│   Vite + Tailwind CSS + Apache ECharts  ──  :80/:3000              │
│   Dynamic routes: /runway/04 | /runway/22 | /runway/middle          │
└───────────────┬────────────────────────────────────────────────────┘
                │  REST/JSON (FastAPI)
┌───────────────▼────────────────────────────────────────────────────┐
│                      Backend API (FastAPI)                         │
│   Asyncpg + SQLAlchemy 2 Async  ──  :8000                          │
│   Routes: /api/v1/status, /telemetry, /sla-ola, /downtime          │
│   LTTB downsampling for long-range chart queries                   │
└───────┬──────────────────────────────┬─────────────────────────────┘
        │                              │
┌───────▼───────────────┐   ┌──────────▼──────────────────────────────┐
│   Ingestion Worker     │   │   PostgreSQL + TimescaleDB              │
│   Active-Passive CDP   │   │   - cdp_nodes, sites, sensors           │
│   reader w/ failover   │──▶│   - telemetry (hypertable)              │
│   1-min logs primary   │   │   - downtime_events (state machine)     │
│   raw DCP fallback     │   │   - daily_sla_ola (pre-aggregated)      │
└────────────────────────┘   └─────────────────────────────────────────┘
```

## Key Concepts

### SLA (System – CDP Node Availability)
- Computed from **connectivity log** to each CDP node (`cdp_nodes`), independent of sensor data.
- Any loss of reachability (ping/telnet/read failure) records a `downtime_event` with exact `start_time`, `end_time`, and `duration_seconds`.

### OLA (Hardware – Sensor Data Validity)
- Computed from per-sensor **data validity** at each site.
- If a sensor's 1-minute sample is missing, corrupt, or outside valid physical ranges, a downtime event is opened for that sensor.

```
Uptime % = ((Total Seconds in Period − Total Downtime Seconds) / Total Seconds in Period) × 100%
```

## Data Sources

| Node   | IP               | Mount path       |
|--------|------------------|------------------|
| CDP 1  | `172.70.55.162`  | `/mnt/cdp1_logs/`|
| CDP 2  | `172.70.55.163`  | `/mnt/cdp2_logs/`|

Log layout:
- `oneminute/` — 1-minute aggregated logs (`*OneMinute*.dat`) — **primary reader**
- `sensor/`   — raw DCP telemetry — **fallback reader** (exact character-position slicing)

File prefixes: `DCPA`/`RWYA` → Runway 04 · `DCPB`/`RWYC` → Runway 22 · `DCPC`/`RWYB` → Runway Middle.

## Site Sensor Matrix (7 per site)

| Runway 04        | Runway 22        | Runway Middle    |
|------------------|------------------|------------------|
| DCP              | DCP              | DCP              |
| ATRH             | ATRH             | ATRH             |
| Dual Barometer   | Dual Barometer   | Dual Barometer   |
| Anemometer       | Anemometer       | Anemometer       |
| Present Weather  | Present Weather  | Rain Gauge       |
| Ceilometer       | Ceilometer       | Solar Radiation  |
| RVR + ALS        | RVR              | Lightning Detector |

## Quick Start (Docker)

```bash
docker compose up --build -d
```

- Frontend: `http://localhost`
- API:      `http://localhost:8000`  → docs at `http://localhost:8000/docs`
- On first boot with an empty database, the ingestion service **auto-backfills history from 2026-01-01** (seeded demo telemetry since network mounts are not available in a plain dev environment).

## Local Development (no Docker)

```bash
# Backend
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000

# Frontend
cd frontend
npm install
npm run dev
```

## API Surface (v1)

| Method | Path                       | Description                                   |
|--------|----------------------------|-----------------------------------------------|
| GET    | `/api/v1/health`            | Liveness / DB connectivity                    |
| GET    | `/api/v1/status/live`       | Real-time per-node + per-sensor status        |
| GET    | `/api/v1/status/sites`      | Site + sensor configuration master            |
| GET    | `/api/v1/telemetry`         | Time-series with LTTB downsampling            |
| GET    | `/api/v1/telemetry/current` | Latest sample per site/sensor                 |
| GET    | `/api/v1/sla-ola`           | Pre-aggregated SLA/OLA rollups                |
| GET    | `/api/v1/downtime`          | Downtime events (state-machine records)       |

## Tests

```bash
cd backend && pytest -q
cd frontend && npm run build   # type/compile check
```

## License
Proprietary internal tooling.