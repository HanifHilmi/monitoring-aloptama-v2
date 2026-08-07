#!/bin/sh
set -e

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

echo "[worker] Running migrations..."
python - <<'PY'
import asyncio
from app.db.migrate import run_migrations

async def main():
    await run_migrations()
    print("[worker] Migrations applied.")

asyncio.run(main())
PY

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

echo "[worker] Starting ingestion worker..."
exec python -m app.ingestion.worker

Also wire the migration runner into the API startup so the API container self-heals too. Updating `main.py`:

<replace_in_file>
<diff>
------- SEARCH
from app.api.router import api_router
from app.core.config import settings
from app.db.session import AsyncSessionLocal
from app.ingestion.worker import build_worker
from app.services.backfill import run_initial_backfill_if_needed
=======
from app.api.router import api_router
from app.core.config import settings
from app.db.migrate import run_migrations
from app.db.session import AsyncSessionLocal
from app.ingestion.worker import build_worker
from app.services.backfill import run_initial_backfill_if_needed
+++++++ REPLACE

------- SEARCH
    worker = None
    try:
        # 1) Auto-backfill on first boot (when DB is uninitialized)
        if settings.enable_backfill_on_boot:
            async with AsyncSessionLocal() as session:
                ran = await run_initial_backfill_if_needed(session)
                if ran:
                    logger.info("Initial historical backfill completed")
=======
    worker = None
    try:
        # 1) Apply pending migrations (idempotent)
        if settings.enable_migrations_on_boot:
            async with AsyncSessionLocal() as session:
                applied = await run_migrations(session)
                if applied:
                    logger.info("Applied migrations: %s", ", ".join(applied))

        # 2) Auto-backfill on first boot (when DB is uninitialized)
        if settings.enable_backfill_on_boot:
            async with AsyncSessionLocal() as session:
                ran = await run_initial_backfill_if_needed(session)
                if ran:
                    logger.info("Initial historical backfill completed")

        # 3) Start the ingestion worker
=======
+++++++ REPLACE

------- SEARCH
        # 2) Start the ingestion worker
        async with AsyncSessionLocal() as session:
            worker = await build_worker(session)
        await worker.start()
        logger.info("Monitoring Aloptama V2 API started")
=======
        # 3) Start the ingestion worker
        async with AsyncSessionLocal() as session:
            worker = await build_worker(session)
        await worker.start()
        logger.info("Monitoring Aloptama V2 API started")
+++++++ REPLACE
