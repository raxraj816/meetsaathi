"""Cross-cutting service helpers: audit records (metadata only, never content), job enqueueing,
usage metering / quotas (UNI-023) and idempotent mutation replay (master 10)."""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import uuid
from typing import Any

import asyncpg

from ..config import get_settings
from ..errors import ApiError


async def audit(conn: asyncpg.Connection, *, tenant_id, user_id, action: str, target_kind: str | None = None,
                target_id=None, detail: dict | None = None) -> None:
    await conn.execute(
        "INSERT INTO audit_events(tenant_id,user_id,action,target_kind,target_id,detail) VALUES ($1,$2,$3,$4,$5,$6)",
        tenant_id, user_id, action, target_kind, target_id, detail or {})


async def enqueue(conn: asyncpg.Connection, *, tenant_id, space_id, session_id, kind: str, payload: dict,
                  key: str, delay_s: float = 0.0, max_attempts: int = 6) -> None:
    """Durable job (Postgres job model with leases, retries and dead-letter; master 8.2).
    idempotency_key makes enqueueing safe to repeat."""
    await conn.execute(
        "INSERT INTO job_outbox(tenant_id,space_id,session_id,kind,payload,idempotency_key,available_at,max_attempts)"
        " VALUES ($1,$2,$3,$4,$5,$6, now() + make_interval(secs => $7), $8)"
        " ON CONFLICT (idempotency_key) DO NOTHING",
        tenant_id, space_id, session_id, kind, payload, key, float(delay_s), max_attempts)


def period_now() -> str:
    return dt.datetime.now(dt.timezone.utc).strftime("%Y-%m")


async def meter(conn: asyncpg.Connection, tenant_id, name: str, qty: float) -> None:
    await conn.execute(
        "INSERT INTO usage_meters(tenant_id,period,meter,quantity) VALUES ($1,$2,$3,$4)"
        " ON CONFLICT (tenant_id,period,meter) DO UPDATE SET quantity = usage_meters.quantity + EXCLUDED.quantity",
        tenant_id, period_now(), name, qty)


async def usage(conn: asyncpg.Connection, tenant_id) -> dict[str, float]:
    rows = await conn.fetch("SELECT meter, quantity FROM usage_meters WHERE tenant_id=$1 AND period=$2",
                            tenant_id, period_now())
    return {r["meter"]: float(r["quantity"]) for r in rows}


async def quota_status(conn: asyncpg.Connection, tenant_id) -> dict[str, Any]:
    s = get_settings()
    plan = await conn.fetchval("SELECT plan FROM tenants WHERE tenant_id=$1", tenant_id) or "FREE"
    u = await usage(conn, tenant_id)
    cap_h = s.quota_capture_hours.get(plan, 2)
    calls = s.quota_reasoner_calls.get(plan, 200)
    return {
        "plan": plan, "period": period_now(),
        "capture_hours_used": round(u.get("capture_seconds", 0) / 3600, 3), "capture_hours_limit": cap_h,
        "reasoner_calls_used": int(u.get("reasoner_calls", 0)), "reasoner_calls_limit": calls,
    }


async def require_reasoner_quota(conn: asyncpg.Connection, tenant_id) -> None:
    q = await quota_status(conn, tenant_id)
    if q["reasoner_calls_used"] >= q["reasoner_calls_limit"]:
        raise ApiError(429, "QUOTA_EXCEEDED", "You've reached this month's AI limit for your plan. Capture and notes still work.",
                       details={"meter": "reasoner_calls", "limit": q["reasoner_calls_limit"]})


async def capture_quota_exceeded(conn: asyncpg.Connection, tenant_id) -> bool:
    q = await quota_status(conn, tenant_id)
    return q["capture_hours_used"] >= q["capture_hours_limit"]


def request_hash(method: str, path: str, body: Any) -> str:
    raw = json.dumps({"m": method, "p": path, "b": body}, sort_keys=True, default=str).encode()
    return hashlib.sha256(raw).hexdigest()


async def idempotent_lookup(conn: asyncpg.Connection, user_id: uuid.UUID, key: str | None, rh: str) -> tuple[int, Any] | None:
    if not key:
        raise ApiError(400, "IDEMPOTENCY_KEY_REQUIRED", "This request needs an Idempotency-Key header.")
    if not (12 <= len(key) <= 128):
        raise ApiError(400, "IDEMPOTENCY_KEY_INVALID", "Idempotency-Key must be 12-128 characters.")
    # The lookup and mutation must serialize even when two API replicas receive the first use
    # simultaneously. A uniqueness constraint alone acts too late, after both handlers ran.
    await conn.execute("SELECT pg_advisory_xact_lock(hashtextextended($1, 0))", f"{user_id}:{key}")
    row = await conn.fetchrow("SELECT request_hash,status_code,response FROM idempotency_keys WHERE user_id=$1 AND key=$2",
                              user_id, key)
    if row is None:
        return None
    if row["request_hash"] != rh:
        raise ApiError(422, "IDEMPOTENCY_KEY_REUSED", "This Idempotency-Key was already used for a different request.")
    return row["status_code"], row["response"]


async def idempotent_store(conn: asyncpg.Connection, user_id: uuid.UUID, key: str, method: str, path: str, rh: str,
                           status: int, response: Any) -> None:
    await conn.execute(
        "INSERT INTO idempotency_keys(user_id,key,method,path,request_hash,status_code,response)"
        " VALUES ($1,$2,$3,$4,$5,$6,$7) ON CONFLICT (user_id,key) DO NOTHING",
        user_id, key, method, path, rh, status, response)
