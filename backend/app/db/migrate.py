"""Minimal migration runner for the ordered SQL migration scripts.

Reads ``migrations/*.sql`` in filename order and executes each against the
configured database. Idempotent via a ``schema_migrations`` bookkeeping table.
"""

from __future__ import annotations

import logging
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import AsyncSessionLocal

logger = logging.getLogger(__name__)

MIGRATIONS_DIR = Path(__file__).resolve().parents[2] / "migrations"


async def _ensure_bookkeeping(session: AsyncSession) -> None:
    await session.execute(
        text(
            """
            CREATE TABLE IF NOT EXISTS schema_migrations (
                filename VARCHAR(255) PRIMARY KEY,
                applied_at TIMESTAMPTZ NOT NULL DEFAULT now()
            )
            """
        )
    )
    await session.commit()


async def _applied_files(session: AsyncSession) -> set[str]:
    rows = await session.execute(text("SELECT filename FROM schema_migrations"))
    return {row[0] for row in rows}


async def _mark_applied(session: AsyncSession, filename: str) -> None:
    await session.execute(
        text(
            "INSERT INTO schema_migrations (filename) VALUES (:fname)"
            " ON CONFLICT (filename) DO NOTHING"
        ),
        {"fname": filename},
    )


async def run_migrations(session: AsyncSession | None = None) -> list[str]:
    """Apply all pending SQL migrations, returning applied filenames."""
    if session is None:
        async with AsyncSessionLocal() as s:
            return await run_migrations(s)

    await _ensure_bookkeeping(session)
    applied = await _applied_files(session)

    files = sorted(MIGRATIONS_DIR.glob("*.sql"))
    if not files:
        logger.warning("No migration files found in %s", MIGRATIONS_DIR)
        return []

    ran: list[str] = []
    for path in files:
        if path.name in applied:
            continue
        sql = path.read_text(encoding="utf-8")
        logger.info("Applying migration %s", path.name)
        # TimescaleDB DDL is not transactional-safe in all versions; run per file.
        await session.execute(text(sql))
        await _mark_applied(session, path.name)
        await session.commit()
        ran.append(path.name)

    if ran:
        logger.info("Applied migrations: %s", ", ".join(ran))
    else:
        logger.info("No pending migrations")
    return ran


async def is_database_initialized(session: AsyncSession) -> bool:
    """True when telemetry/connectivity data already exists (skip backfill)."""
    from app.services.backfill import is_database_uninitialized

    return not await is_database_uninitialized(session)
