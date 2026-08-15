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
        # asyncpg does not support multiple statements in a single execute().
        # Split the file into individual statements and run each separately.
        for stmt in _split_sql_statements(sql):
            if not stmt.strip():
                continue
            await session.execute(text(stmt))
        await _mark_applied(session, path.name)
        await session.commit()
        ran.append(path.name)

    if ran:
        logger.info("Applied migrations: %s", ", ".join(ran))
    else:
        logger.info("No pending migrations")
    return ran


def _split_sql_statements(sql: str) -> list[str]:
    """Split a SQL script into individual statements on top-level semicolons.

    Handles dollar-quoted bodies (e.g. PL/pgSQL functions) and single-line
    comments so semicolons inside them are not treated as statement breaks.
    """
    statements: list[str] = []
    current: list[str] = []
    in_dollar = False
    dollar_tag: str | None = None
    in_line_comment = False

    for line in sql.splitlines():
        stripped = line.strip()
        if in_line_comment:
            in_line_comment = False
        if stripped.startswith("--"):
            continue
        if not in_dollar:
            # Detect dollar-quote start (e.g. $$ or $func$)
            import re
            m = re.search(r"\$[A-Za-z_0-9]*\$", line)
            if m:
                in_dollar = True
                dollar_tag = m.group(0)
        else:
            if dollar_tag and dollar_tag in line:
                in_dollar = False
                dollar_tag = None
        current.append(line)
        if not in_dollar and line.rstrip().endswith(";"):
            statements.append("\n".join(current))
            current = []
    if current and "\n".join(current).strip():
        statements.append("\n".join(current))
    return statements


async def reset_database(session: AsyncSession) -> None:
    """Drop all objects so a fresh deploy starts from an empty database.

    TimescaleDB registers the ``timescaledb`` extension in the public
    schema; dropping the schema removes that registration, and migration
    001 re-creates it (``CREATE EXTENSION IF NOT EXISTS timescaledb``).
    Call before running migrations when ``RESET_DB_ON_BOOT=true``.
    """
    await session.execute(text("DROP SCHEMA IF EXISTS public CASCADE"))
    await session.execute(text("CREATE SCHEMA public"))
    await session.commit()
    logger.info("Database reset (public schema recreated)")
