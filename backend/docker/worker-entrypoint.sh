#!/bin/sh
set -e

# Read env flags. Coolify / compose may inject these as "true"/"false".
ENABLE_MIGRATIONS_ON_BOOT="${ENABLE_MIGRATIONS_ON_BOOT:-false}"

echo "[worker] Waiting for database..."
python - <<'PY'
import asyncio, sys

async def wait():
    from sqlalchemy import text
    from app.db.session import engine
    for attempt in range(60):
        try:
            async with engine.connect() as conn:
                await conn.execute(text("SELECT 1"))
            print("[worker] Database is ready.")
            return
        except Exception as exc:
            print(f"[worker] DB not ready ({attempt + 1}/60): {exc}")
            await asyncio.sleep(2)
    sys.exit(1)

asyncio.run(wait())
PY

# Migrations are owned by the backend (API) process. Running them here too
# causes advisory-lock / deadlock races on boot, so we only apply them when
# explicitly enabled (single-service local setups).
if [ "$ENABLE_MIGRATIONS_ON_BOOT" = "true" ]; then
    echo "[worker] Running migrations..."
    python - <<'PY'
import asyncio
from app.db.migrate import run_migrations

async def main():
    await run_migrations()
    print("[worker] Migrations applied.")

asyncio.run(main())
PY
else
    echo "[worker] ENABLE_MIGRATIONS_ON_BOOT=false -> skipping migrations (backend owns schema)."
fi

# Historical backfill is NEVER run from the worker on boot. It is triggered
# explicitly from the dashboard Settings -> Backfill ("Backfill CDP uptime"
# and "Backfill DCP Data") via POST /api/v1/backfill/cdp and /dcp. This
# guarantees the ingestion worker starts immediately on every deploy.
echo "[worker] Auto-backfill disabled — historical data is backfilled manually from the dashboard."

echo "[worker] Starting ingestion worker..."
exec python -m app.ingestion.worker