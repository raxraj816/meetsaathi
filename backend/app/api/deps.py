from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any, Awaitable, Callable

import asyncpg
from fastapi import Header, Request
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse

from ..db import db
from ..domain import ops
from ..errors import ApiError
from ..security.tokens import decode_access_token


@dataclass(frozen=True)
class CurrentUser:
    user_id: uuid.UUID
    device_id: uuid.UUID
    tenant_id: uuid.UUID
    reauth_at: int | None


async def current_user(authorization: str | None = Header(default=None)) -> CurrentUser:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise ApiError(401, "UNAUTHENTICATED", "Sign in to continue.")
    claims = decode_access_token(authorization.split(" ", 1)[1].strip())
    async with db.system_tx() as conn:
        row = await conn.fetchrow(
            "SELECT d.revoked_at, u.deleted_at, (SELECT tenant_id FROM tenant_memberships m WHERE m.user_id=u.user_id"
            " ORDER BY (role='OWNER') DESC LIMIT 1) AS tenant_id"
            " FROM devices d JOIN users u ON u.user_id=d.user_id WHERE d.device_id=$1 AND d.user_id=$2",
            claims.device_id, claims.user_id)
        if row is None or row["revoked_at"] is not None or row["deleted_at"] is not None or row["tenant_id"] is None:
            raise ApiError(401, "DEVICE_REVOKED", "This device has been signed out.")
        await conn.execute("UPDATE devices SET last_seen_at=now() WHERE device_id=$1 AND (last_seen_at IS NULL OR last_seen_at < now() - interval '1 minute')",
                           claims.device_id)
    return CurrentUser(claims.user_id, claims.device_id, row["tenant_id"], claims.reauth_at)


def require_recent_auth(user: CurrentUser, window_s: int) -> None:
    import time

    if user.reauth_at is None or time.time() - user.reauth_at > window_s:
        raise ApiError(403, "REAUTH_REQUIRED", "Confirm your password to continue.")


async def idempotent(request: Request, user: CurrentUser, key: str | None, body: Any,
                     fn: Callable[[asyncpg.Connection], Awaitable[tuple[int, Any]]]) -> JSONResponse:
    """Run a mutation exactly once per Idempotency-Key. The handler runs in the same transaction as the
    stored response, so a crash can never record a response for work that did not commit."""
    rh = ops.request_hash(request.method, request.url.path, jsonable_encoder(body))
    async with db.user_tx(user.user_id) as conn:
        hit = await ops.idempotent_lookup(conn, user.user_id, key, rh)
        if hit is not None:
            return JSONResponse(status_code=hit[0], content=hit[1], headers={"Idempotent-Replay": "true"})
        status, payload = await fn(conn)
        encoded = jsonable_encoder(payload)
        await ops.idempotent_store(conn, user.user_id, key, request.method, request.url.path, rh, status, encoded)
    return JSONResponse(status_code=status, content=encoded)
