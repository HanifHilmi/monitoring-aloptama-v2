#!/bin/sh
set -e

# Read env flags. Coolify / compose may inject these as "true"/"false".
ENABLE_MIGRATIONS_ON_BOOT="${ENABLE_MIGRATIONS_ON_BOOT:-false}"
ENABLE_BACKFILL_ON_BOOT="${ENABLE_BACKFILL_ON_BOOT:-false}"

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

# Historical backfill is gated by ENABLE_BACKFILL_ON_BOOT. In the normal
# Coolify deployment this flag is "false" because backfill already ran on
# first boot; keeping it opt-in avoids re-running a multi-hour backfill on
# every worker restart.
if [ "$ENABLE_BACKFILL_ON_BOOT" = "true" ]; then
    echo "[worker] Checking initial backfill..."
    python - <<'PY'
import asyncio
from app.db.session import AsyncSessionLocal
from app.db.migrate import is_database_initialized
from app.services.backfill import run_initial_backfill_if_needed

async def main():
    async with AsyncSessionLocal() as session:
        if not await is_database_initialized(session):
            print("[worker] Database empty - starting historical backfill from 2026-01-01...")
            ran = await run_initial_backfill_if_needed(session)
            print(f"[worker] Backfill {'completed' if ran else 'skipped'}.")
        else:
            print("[worker] Database already initialized - skipping backfill.")

asyncio.run(main())
PY
else
    echo "[worker] ENABLE_BACKFILL_ON_BOOT=false -> skipping backfill."
fi

echo "[worker] Starting ingestion worker..."
exec python -m app.ingestion.worker