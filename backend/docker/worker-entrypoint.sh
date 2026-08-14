#!/bin/sh
set -e

# Read env flags. Coolify / compose may inject these as "true"/"false".
# Worker role: continuous ingestion only. Migrations and the reset are
# owned solely by the backend (API) process.

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

# Migrations are owned by the backend (API) process; the worker never migrates.
echo "[worker] Migrations owned by backend - worker does not run them."

echo "[worker] Auto-backfill disabled — historical data is backfilled manually from the dashboard."

echo "[worker] Starting ingestion worker..."
exec python -m app.ingestion.worker