"""Deletion & retention (master 6.3, J12, MTG-042, CON-062..066).

Step 1 (request path, one transaction): revoke access immediately - tombstone + RLS hides every derived row,
claims marked DELETED, upload credentials and share links revoked.
Step 2 (durable job): purge objects, audio, transcripts, embeddings, insights, caches/derivatives; status
REQUESTED -> IN_PROGRESS -> COMPLETE | ACTION_REQUIRED. Backups expire per the published policy; we never
claim instant physical backup erasure."""
from __future__ import annotations

import asyncio
import logging
import uuid
from contextlib import asynccontextmanager

from ..db import db
from ..config import get_settings
from ..domain import ops
from ..domain.events import append_event
from ..errors import ApiError, not_found
from ..storage import get_store, session_prefix
from .sharing import invalidate_exports, purge_expired_exports


@asynccontextmanager
async def tombstoning(conn):
    """Allow revocation UPDATEs that make rows invisible (see migrations/002_rls.sql)."""
    await conn.execute("SELECT set_config('app.tombstoning', 'on', true)")
    try:
        yield
    finally:
        await conn.execute("SELECT set_config('app.tombstoning', '', true)")

log = logging.getLogger("meetsaathi.deletion")

BACKUP_NOTICE = ("Deleted content is removed from MeetSaathi immediately and purged from storage. Encrypted backups "
                 "expire on their published schedule (up to 35 days) and are never restored into your account.")


async def _new_request(conn, *, tenant_id, space_id, session_id, user_id, scope_kind, target_id, detail=None) -> uuid.UUID:
    rid = await conn.fetchval(
        "INSERT INTO deletion_requests(tenant_id,space_id,session_id,requested_by,status,scope_kind,target_id,detail)"
        " VALUES ($1,$2,$3,$4,'REQUESTED',$5,$6,$7) RETURNING request_id",
        tenant_id, space_id, session_id, user_id, scope_kind, target_id, detail or {})
    await ops.enqueue(conn, tenant_id=tenant_id, space_id=space_id, session_id=session_id, kind="deletion.purge",
                      payload={"request_id": str(rid)}, key=f"purge:{rid}", max_attempts=8)
    return rid


async def _revoke_session(conn, session: dict, user_id) -> None:
    sid = session["session_id"]
    await invalidate_exports(conn, session["tenant_id"])
    await append_event(conn, session, "session.state_changed", {"previous": session["state"], "current": "DELETING",
                                                                "reason": "USER_DELETE", "audio_watermark_ms": int(session["source_watermark_ms"])})
    await conn.execute("UPDATE ingest_tokens SET revoked_at=now() WHERE session_id=$1 AND revoked_at IS NULL", sid)
    await conn.execute("UPDATE shares SET revoked_at=now() WHERE session_id=$1 AND revoked_at IS NULL", sid)
    async with tombstoning(conn):
        await conn.execute("UPDATE claims SET memory_state='DELETED', updated_at=now() WHERE session_id=$1 AND memory_state<>'DELETED'", sid)
        await conn.execute("UPDATE sessions SET deleted_at=now(), state='DELETING', version=version+1 WHERE session_id=$1", sid)
    await conn.execute("INSERT INTO session_state_log(tenant_id,space_id,session_id,previous,current,reason,actor) VALUES ($1,$2,$3,$4,'DELETING','USER_DELETE','USER')",
                       session["tenant_id"], session["space_id"], sid, session["state"])
    await ops.audit(conn, tenant_id=session["tenant_id"], user_id=user_id, action="session.deletion_requested",
                    target_kind="session", target_id=sid)


async def request_session_deletion(conn, user, session: dict) -> dict:
    if not await conn.fetchval("SELECT may_write_space($1,$2)", session["tenant_id"], session["space_id"]):
        raise not_found("session")
    await _revoke_session(conn, session, user.user_id)
    rid = await _new_request(conn, tenant_id=session["tenant_id"], space_id=session["space_id"], session_id=session["session_id"],
                             user_id=user.user_id, scope_kind="SESSION", target_id=session["session_id"])
    return {"request_id": rid, "status": "REQUESTED", "access_revoked": True, "notice": BACKUP_NOTICE}


async def request_audio_deletion(conn, user, session: dict) -> dict:
    await conn.execute("UPDATE sessions SET audio_deleted_at=now(), version=version+1 WHERE session_id=$1", session["session_id"])
    await conn.execute("UPDATE audio_chunks SET ingest_status='PURGED' WHERE session_id=$1", session["session_id"])
    rid = await _new_request(conn, tenant_id=session["tenant_id"], space_id=session["space_id"], session_id=session["session_id"],
                             user_id=user.user_id, scope_kind="SESSION_AUDIO", target_id=session["session_id"])
    await ops.audit(conn, tenant_id=session["tenant_id"], user_id=user.user_id, action="session.audio_deletion_requested",
                    target_kind="session", target_id=session["session_id"])
    return {"request_id": rid, "status": "REQUESTED",
            "notice": "Audio is removed. Transcript and notes remain, but source playback is no longer available."}


async def request_claim_deletion(conn, user, claim: dict) -> dict:
    await invalidate_exports(conn, claim["tenant_id"])
    async with tombstoning(conn):
        await conn.execute("UPDATE claims SET memory_state='DELETED', updated_at=now() WHERE claim_id=$1", claim["claim_id"])
    await conn.execute("DELETE FROM embeddings WHERE owner_kind='CLAIM' AND owner_id=$1", claim["claim_id"])
    rid = await _new_request(conn, tenant_id=claim["tenant_id"], space_id=claim["space_id"], session_id=claim["session_id"],
                             user_id=user.user_id, scope_kind="CLAIM", target_id=claim["claim_id"])
    return {"request_id": rid, "status": "REQUESTED"}


async def request_space_deletion(conn, user, space: dict) -> dict:
    role = await conn.fetchval("SELECT role FROM space_memberships WHERE space_id=$1 AND user_id=$2", space["space_id"], user.user_id)
    if role != "OWNER":
        raise ApiError(403, "SCOPE_DENIED", "Only the space owner can delete it.")
    sessions = await conn.fetch("SELECT * FROM sessions WHERE space_id=$1 AND deleted_at IS NULL", space["space_id"])
    for s in sessions:
        await _revoke_session(conn, dict(s), user.user_id)
    # Record the durable purge request while the space is still writable, then revoke access.
    rid = await _new_request(conn, tenant_id=space["tenant_id"], space_id=space["space_id"], session_id=None, user_id=user.user_id,
                             scope_kind="SPACE", target_id=space["space_id"])
    async with tombstoning(conn):
        await conn.execute("UPDATE claims SET memory_state='DELETED' WHERE space_id=$1 AND memory_state<>'DELETED'", space["space_id"])
        await conn.execute("UPDATE projects SET deleted_at=now() WHERE space_id=$1 AND deleted_at IS NULL", space["space_id"])
        # Tombstoning the space makes may_read_space() false for every row in it: excluded from retrieval immediately.
        await conn.execute("UPDATE spaces SET deleted_at=now() WHERE space_id=$1", space["space_id"])
    return {"request_id": rid, "status": "REQUESTED", "access_revoked": True, "notice": BACKUP_NOTICE}


async def request_account_deletion(user) -> dict:
    async with db.system_tx() as conn:
        await invalidate_exports(conn, user.tenant_id)
        spaces = await conn.fetch("SELECT s.tenant_id, s.space_id FROM spaces s JOIN space_memberships m ON m.space_id=s.space_id"
                                  " WHERE m.user_id=$1 AND m.role='OWNER' AND s.deleted_at IS NULL", user.user_id)
        await conn.execute("UPDATE sessions SET deleted_at=now(), state='DELETING' WHERE created_by=$1 AND deleted_at IS NULL", user.user_id)
        await conn.execute("UPDATE claims SET memory_state='DELETED' WHERE space_id = ANY($1::uuid[])", [s["space_id"] for s in spaces])
        await conn.execute("UPDATE spaces SET deleted_at=now() WHERE space_id = ANY($1::uuid[])", [s["space_id"] for s in spaces])
        await conn.execute("UPDATE devices SET revoked_at=now() WHERE user_id=$1 AND revoked_at IS NULL", user.user_id)
        await conn.execute("SELECT pg_notify('msd_' || replace(device_id::text, '-', ''), '') FROM devices WHERE user_id=$1", user.user_id)
        await conn.execute("UPDATE refresh_tokens SET revoked_at=now() WHERE user_id=$1 AND revoked_at IS NULL", user.user_id)
        await conn.execute("UPDATE ingest_tokens SET revoked_at=now() WHERE user_id=$1 AND revoked_at IS NULL", user.user_id)
        await conn.execute("UPDATE users SET deleted_at=now() WHERE user_id=$1", user.user_id)
        ids = []
        for s in spaces:
            rid = await conn.fetchval(
                "INSERT INTO deletion_requests(tenant_id,space_id,requested_by,status,scope_kind,target_id) VALUES ($1,$2,$3,'REQUESTED','SPACE',$2)"
                " RETURNING request_id", s["tenant_id"], s["space_id"], user.user_id)
            await ops.enqueue(conn, tenant_id=s["tenant_id"], space_id=s["space_id"], session_id=None, kind="deletion.purge",
                              payload={"request_id": str(rid), "account": str(user.user_id)}, key=f"purge:{rid}", max_attempts=8)
            ids.append(str(rid))
        await ops.audit(conn, tenant_id=user.tenant_id, user_id=user.user_id, action="account.deletion_requested")
    return {"status": "REQUESTED", "request_ids": ids, "access_revoked": True, "notice": BACKUP_NOTICE}


async def _purge_session_rows(conn, tenant_id, session_id) -> int:
    store = get_store()
    n = await asyncio.to_thread(store.delete_prefix, session_prefix(tenant_id, session_id))
    await conn.execute("DELETE FROM embeddings WHERE session_id=$1", session_id)
    await conn.execute("DELETE FROM embeddings WHERE owner_kind='CLAIM' AND owner_id IN (SELECT claim_id FROM claims WHERE session_id=$1)", session_id)
    await conn.execute("DELETE FROM claims WHERE session_id=$1", session_id)  # cascades claim_sources, decision_events
    await conn.execute("DELETE FROM practice_items WHERE session_id=$1", session_id)
    await conn.execute("DELETE FROM insights WHERE session_id=$1", session_id)
    await conn.execute("DELETE FROM ask_turns WHERE session_id=$1", session_id)
    await conn.execute("DELETE FROM utterance_revisions WHERE session_id=$1", session_id)
    await conn.execute("DELETE FROM utterances WHERE session_id=$1", session_id)
    await conn.execute("DELETE FROM speaker_mapping_history WHERE session_id=$1", session_id)
    await conn.execute("DELETE FROM session_speakers WHERE session_id=$1", session_id)
    await conn.execute("DELETE FROM audio_chunks WHERE session_id=$1", session_id)
    await conn.execute("DELETE FROM capture_gaps WHERE session_id=$1", session_id)
    await conn.execute("DELETE FROM session_events WHERE session_id=$1", session_id)
    await conn.execute("DELETE FROM shares WHERE session_id=$1", session_id)
    await conn.execute("DELETE FROM job_outbox WHERE session_id=$1 AND kind <> 'deletion.purge' AND status IN ('READY','DEAD')", session_id)
    # Tombstone keeps only non-content metadata needed for audit (consent receipts, state log).
    await conn.execute("UPDATE sessions SET state='DELETED', title='Deleted session', recap=NULL, capabilities_hash=NULL WHERE session_id=$1", session_id)
    return n


async def run_purge(request_id: uuid.UUID) -> None:
    async with db.system_tx() as conn:
        req = await conn.fetchrow("SELECT * FROM deletion_requests WHERE request_id=$1 FOR UPDATE", request_id)
        if req is None or req["status"] == "COMPLETE":
            return
        await conn.execute("UPDATE deletion_requests SET status='IN_PROGRESS' WHERE request_id=$1", request_id)
    async with db.system_tx() as conn:
        kind, tenant_id = req["scope_kind"], req["tenant_id"]
        detail: dict = {}
        detail["exports_purged"] = await purge_expired_exports(conn, tenant_id)
        if kind == "SESSION":
            detail["objects_deleted"] = await _purge_session_rows(conn, tenant_id, req["session_id"])
        elif kind == "SESSION_AUDIO":
            keys = await conn.fetch("SELECT encrypted_object_key FROM audio_chunks WHERE session_id=$1", req["session_id"])
            store = get_store()
            detail["objects_deleted"] = sum([1 for k in keys if await asyncio.to_thread(store.delete, k["encrypted_object_key"])])
            await conn.execute("UPDATE audio_chunks SET ingest_status='PURGED' WHERE session_id=$1", req["session_id"])
        elif kind == "CLAIM":
            await conn.execute("DELETE FROM embeddings WHERE owner_kind='CLAIM' AND owner_id=$1", req["target_id"])
            await conn.execute("DELETE FROM claims WHERE claim_id=$1", req["target_id"])
        elif kind == "SPACE":
            sessions = await conn.fetch("SELECT session_id FROM sessions WHERE space_id=$1", req["space_id"])
            total = 0
            for s in sessions:
                total += await _purge_session_rows(conn, tenant_id, s["session_id"])
            await conn.execute("DELETE FROM embeddings WHERE space_id=$1", req["space_id"])
            await conn.execute("DELETE FROM claims WHERE space_id=$1", req["space_id"])
            await conn.execute("DELETE FROM review_schedule WHERE space_id=$1", req["space_id"])
            await conn.execute("DELETE FROM practice_items WHERE space_id=$1", req["space_id"])
            await conn.execute("DELETE FROM interview_mocks WHERE space_id=$1", req["space_id"])
            await conn.execute("UPDATE projects SET title='Deleted', metadata='{}'::jsonb WHERE space_id=$1", req["space_id"])
            detail["objects_deleted"] = total
            detail["sessions_purged"] = len(sessions)
        await conn.execute("UPDATE deletion_requests SET status='COMPLETE', completed_at=now(), detail=detail || $2 WHERE request_id=$1",
                           request_id, detail)
        await ops.audit(conn, tenant_id=tenant_id, user_id=req["requested_by"], action="deletion.completed",
                        target_kind=kind.lower(), target_id=req["target_id"])


async def mark_action_required(request_id: uuid.UUID, error: str) -> None:
    async with db.system_tx() as conn:
        await conn.execute("UPDATE deletion_requests SET status='ACTION_REQUIRED', detail = detail || $2 WHERE request_id=$1",
                           request_id, {"error": error[:200]})


async def retention_sweep() -> dict:
    """Ephemeral sessions never reviewed expire; raw audio past its retention window is purged (CON-065)."""
    out = {"ephemeral_deleted": 0, "audio_purged": 0}
    async with db.system_tx() as conn:
        await purge_expired_exports(conn)
        expired = await conn.fetch(
            "SELECT * FROM sessions WHERE deleted_at IS NULL AND retention_policy_id='EPHEMERAL' AND review_state='PENDING'"
            " AND state IN ('COMPLETED','COMPLETED_PARTIAL','FINALIZATION_RETRYABLE')"
            " AND ended_at < now() - make_interval(hours => $1)", get_settings().ephemeral_retention_hours)
        for s in expired:
            s = dict(s)
            await _revoke_session(conn, s, s["created_by"])
            await _new_request(conn, tenant_id=s["tenant_id"], space_id=s["space_id"], session_id=s["session_id"],
                               user_id=s["created_by"], scope_kind="SESSION", target_id=s["session_id"], detail={"reason": "RETENTION_EXPIRED"})
            out["ephemeral_deleted"] += 1
        audio = await conn.fetch("SELECT * FROM sessions WHERE deleted_at IS NULL AND audio_deleted_at IS NULL"
                                 " AND audio_retention_until IS NOT NULL AND audio_retention_until < now()")
        for s in audio:
            await conn.execute("UPDATE sessions SET audio_deleted_at=now() WHERE session_id=$1", s["session_id"])
            await conn.execute("UPDATE audio_chunks SET ingest_status='PURGED' WHERE session_id=$1", s["session_id"])
            await _new_request(conn, tenant_id=s["tenant_id"], space_id=s["space_id"], session_id=s["session_id"],
                               user_id=s["created_by"], scope_kind="SESSION_AUDIO", target_id=s["session_id"],
                               detail={"reason": "AUDIO_RETENTION_EXPIRED"})
            out["audio_purged"] += 1
    return out
