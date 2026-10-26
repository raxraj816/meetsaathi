"""Database access. Two pools with distinct Postgres roles:

* app pool (ms_app): request path; each transaction binds app.user_id to the authenticated user so RLS applies.
* worker pool (ms_worker): trusted service code (auth bootstrap, durable jobs) with explicit worker policies.

The client can never set session variables: app.user_id is only set here, from a verified token subject.
"""
from __future__ import annotations

import json
import ssl
import uuid
from contextlib import asynccontextmanager
from typing import AsyncIterator

import asyncpg

from .config import get_settings


def connection_options() -> dict:
    s = get_settings()
    if s.env in ("dev", "test"):
        return {}
    return {"ssl": ssl.create_default_context(cafile=s.database_ca_file)}


async def _init_conn(conn: asyncpg.Connection) -> None:
    await conn.set_type_codec("jsonb", encoder=json.dumps, decoder=json.loads, schema="pg_catalog")
    await conn.set_type_codec("json", encoder=json.dumps, decoder=json.loads, schema="pg_catalog")


class Database:
    def __init__(self) -> None:
        self.app_pool: asyncpg.Pool | None = None
        self.worker_pool: asyncpg.Pool | None = None

    async def connect(self) -> None:
        s = get_settings()
        if self.app_pool is None:
            self.app_pool = await asyncpg.create_pool(s.database_app_url, min_size=1, max_size=20, init=_init_conn, **connection_options())
        if self.worker_pool is None:
            self.worker_pool = await asyncpg.create_pool(s.database_worker_url, min_size=1, max_size=10, init=_init_conn, **connection_options())

    async def close(self) -> None:
        for pool in (self.app_pool, self.worker_pool):
            if pool is not None:
                await pool.close()
        self.app_pool = None
        self.worker_pool = None

    @asynccontextmanager
    async def user_tx(self, user_id: uuid.UUID) -> AsyncIterator[asyncpg.Connection]:
        assert self.app_pool is not None, "database not connected"
        async with self.app_pool.acquire() as conn:
            async with conn.transaction():
                await conn.execute("SELECT set_config('app.user_id', $1, true)", str(user_id))
                yield conn

    @asynccontextmanager
    async def system_tx(self) -> AsyncIterator[asyncpg.Connection]:
        assert self.worker_pool is not None, "database not connected"
        async with self.worker_pool.acquire() as conn:
            async with conn.transaction():
                yield conn

    @asynccontextmanager
    async def listen_conn(self) -> AsyncIterator[asyncpg.Connection]:
        s = get_settings()
        conn = await asyncpg.connect(s.database_worker_url, **connection_options())
        try:
            yield conn
        finally:
            await conn.close()


db = Database()


def vector_literal(values: list[float]) -> str:
    return "[" + ",".join(f"{v:.7f}" for v in values) + "]"


def session_channel(session_id: uuid.UUID | str) -> str:
    return "mse_" + uuid.UUID(str(session_id)).hex
