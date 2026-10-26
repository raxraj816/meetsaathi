"""Durable session event log + live fan-out (master 10 / realtime_events_v1.json).

Events are appended inside the producing transaction (transactional outbox semantics): the row, the
monotonic per-session sequence and the NOTIFY all commit together or not at all. WebSocket clients
resume from their acknowledged cursor by replaying session_events (no duplicates, ordered)."""
from __future__ import annotations

import datetime as dt
import uuid
from typing import Any

import asyncpg

from ..db import session_channel

EVENT_TYPES = {
    "session.state_changed", "audio.chunk_ack", "transcript.partial", "transcript.final", "insight.delivered",
    "voice.route_lost", "memory.invalidated", "session.finalization_progress",
    # EXT (documented in packages/contracts/realtime_events_v1.json): status needed by truthful UI copy.
    "session.status", "insight.expired", "ask.answered", "speaker.corrected",
    "transcript.preview", "transcript.preview_clear",
}

REQUIRED = {
    "transcript.preview": ("run_id", "preview_id", "start_ms", "end_ms", "text", "is_final", "evidence"),
    "transcript.preview_clear": ("run_id", "reason"),
    "session.state_changed": ("previous", "current", "reason", "audio_watermark_ms"),
    "audio.chunk_ack": ("received_through_sequence", "gap_sequences", "checksum_confirmed"),
    "transcript.final": ("utterance_id", "revision", "start_ms", "end_ms", "text", "is_final"),
    "insight.delivered": ("insight_id", "short_text", "kind", "source_refs", "expires_at", "policy_version", "output_channel"),
}


async def append_event(conn: asyncpg.Connection, session: dict, type_: str, payload: dict[str, Any]) -> dict:
    if type_ not in EVENT_TYPES:
        raise ValueError(f"unknown event type {type_}")
    missing = [k for k in REQUIRED.get(type_, ()) if k not in payload]
    if missing:
        raise ValueError(f"event {type_} missing {missing}")
    seq = await conn.fetchval(
        "UPDATE session_runtime SET event_seq = event_seq + 1 WHERE session_id=$1 RETURNING event_seq",
        session["session_id"])
    if seq is None:
        raise RuntimeError("session runtime row missing")
    event_id = uuid.uuid4()
    created = dt.datetime.now(dt.timezone.utc)
    await conn.execute(
        "INSERT INTO session_events(tenant_id,space_id,session_id,sequence,event_id,type,payload,created_at)"
        " VALUES ($1,$2,$3,$4,$5,$6,$7,$8)",
        session["tenant_id"], session["space_id"], session["session_id"], seq, event_id, type_, payload, created)
    await conn.execute("SELECT pg_notify($1, $2)", session_channel(session["session_id"]), str(seq))
    return envelope(session["session_id"], seq, event_id, created, type_, payload)


def envelope(session_id, seq, event_id, created_at, type_, payload) -> dict:
    return {
        "event_id": str(event_id),
        "schema_version": "1.0",
        "session_id": str(session_id),
        "sequence": int(seq),
        "created_at": created_at.astimezone(dt.timezone.utc).isoformat().replace("+00:00", "Z"),
        "type": type_,
        "payload": payload,
    }


async def events_after(conn: asyncpg.Connection, session_id: uuid.UUID, cursor: int, limit: int = 500) -> list[dict]:
    rows = await conn.fetch(
        "SELECT sequence,event_id,created_at,type,payload FROM session_events WHERE session_id=$1 AND sequence>$2"
        " ORDER BY sequence LIMIT $3", session_id, cursor, limit)
    return [envelope(session_id, r["sequence"], r["event_id"], r["created_at"], r["type"], r["payload"]) for r in rows]
