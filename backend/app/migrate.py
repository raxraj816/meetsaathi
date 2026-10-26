"""Migration runner. Connects as the migration owner, ensures runtime roles exist (without BYPASSRLS,
without table ownership), then applies migrations/*.sql exactly once each.

Usage: python -m app.migrate            apply pending migrations
       python -m app.migrate --reset    DROP and recreate the public schema (dev/test only)
"""
from __future__ import annotations

import asyncio
import pathlib
import sys

import asyncpg

from .config import get_settings
from .db import connection_options

MIGRATIONS_DIR = pathlib.Path(__file__).resolve().parent.parent / "migrations"


async def _ensure_role(conn: asyncpg.Connection, name: str, password: str) -> None:
    exists = await conn.fetchval("SELECT 1 FROM pg_roles WHERE rolname=$1", name)
    # Password is passed through format(%L) on the server side to avoid client-side quoting bugs.
    if not exists:
        await conn.execute(f"CREATE ROLE {name} LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOBYPASSRLS")
    await conn.execute(f"ALTER ROLE {name} LOGIN NOSUPERUSER NOBYPASSRLS")
    sql = await conn.fetchval("SELECT format('ALTER ROLE %I PASSWORD %L', $1::text, $2::text)", name, password)
    await conn.execute(sql)


async def migrate(reset: bool = False) -> list[str]:
    s = get_settings()
    conn = await asyncpg.connect(s.database_owner_url, **connection_options())
    applied: list[str] = []
    try:
        await conn.execute("SELECT pg_advisory_lock(1870469012)")  # serialize deploy/migration processes
        if reset:
            if s.env not in ("dev", "test"):
                raise RuntimeError("--reset is only allowed in dev/test")
            await conn.execute("DROP SCHEMA IF EXISTS public CASCADE; CREATE SCHEMA public;")
        await _ensure_role(conn, "ms_app", s.app_db_password)
        await _ensure_role(conn, "ms_worker", s.worker_db_password)
        await conn.execute("CREATE TABLE IF NOT EXISTS schema_migrations (name text PRIMARY KEY, applied_at timestamptz NOT NULL DEFAULT now())")
        done = {r["name"] for r in await conn.fetch("SELECT name FROM schema_migrations")}
        for path in sorted(MIGRATIONS_DIR.glob("*.sql")):
            if path.name in done:
                continue
            async with conn.transaction():
                await conn.execute(path.read_text())
                await conn.execute("INSERT INTO schema_migrations(name) VALUES ($1)", path.name)
            applied.append(path.name)
        await conn.execute("REVOKE ALL ON schema_migrations FROM ms_app, ms_worker")
    finally:
        await conn.close()
    return applied


def main() -> None:
    applied = asyncio.run(migrate(reset="--reset" in sys.argv))
    print("applied:", ", ".join(applied) if applied else "nothing (up to date)")


if __name__ == "__main__":
    main()
