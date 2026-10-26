"""Exports (data portability) and audience-specific shares with redaction preview, expiry and revocation
(MTG-052/053, UNI-024). Shares are frozen snapshots of user-approved content - never raw audio, never
source URLs, never unverified identities."""
from __future__ import annotations

import asyncio
import datetime as dt
import json
import secrets
import uuid

from ..config import get_settings
from ..db import db
from ..errors import ApiError, not_found
from ..security.tokens import hash_opaque
from ..storage import get_store

SHARE_SECTIONS = ("summary", "decisions", "actions", "questions", "notes")


async def build_recap_snapshot(conn, session: dict, *, sections: list[str], redact_identities: bool,
                               claim_ids: list[uuid.UUID] | None) -> dict:
    bad = set(sections) - set(SHARE_SECTIONS)
    if bad:
        raise ApiError(422, "INVALID_SECTIONS", "Unsupported share sections.", details={"sections": sorted(bad)})
    labels = {}
    for r in await conn.fetch("SELECT alias, user_verified_label FROM session_speakers WHERE session_id=$1", session["session_id"]):
        labels[r["alias"]] = r["user_verified_label"]

    def scrub(text: str) -> str:
        if not redact_identities:
            return text
        for alias, label in labels.items():
            if label:
                text = text.replace(label, alias)
        return text

    rows = await conn.fetch("SELECT claim_id, claim_kind, text_value, decision_status::text AS decision_status, owner_label, owner_confirmed,"
                            " memory_state, provenance::text AS provenance FROM claims WHERE session_id=$1 AND memory_state IN ('APPROVED','PENDING_REVIEW')"
                            " AND invalidated_at IS NULL ORDER BY time_start_ms NULLS LAST", session["session_id"])
    chosen = set(claim_ids or [])
    items = [r for r in rows if (not chosen or r["claim_id"] in chosen) and r["provenance"] != "AI_SIMULATION"]
    snap: dict = {"title": scrub(session["title"]), "date": session["created_at"].date().isoformat(), "context": session["context"],
                  "notice": "Shared by the session owner. Contains only the reviewed items below; no audio or source recordings."}
    recap = session["recap"] or {}
    if "summary" in sections and recap.get("summary"):
        snap["summary"] = [scrub(s["text"]) for s in recap["summary"]]
    for sec, kinds in (("decisions", ("DECISION",)), ("actions", ("ACTION", "COMMITMENT")), ("questions", ("QUESTION", "RISK")),
                       ("notes", ("NOTE", "BOOKMARK"))):
        if sec in sections:
            snap[sec] = [{"text": scrub(r["text_value"]), "status": r["decision_status"],
                          "owner": (scrub(r["owner_label"]) if r["owner_confirmed"] and r["owner_label"] else "Owner unconfirmed")
                          if r["claim_kind"] in ("ACTION", "COMMITMENT") else None,
                          "label": "AI suggestion" if r["provenance"] == "AI_ANALYSIS" else None}
                         for r in items if r["claim_kind"] in kinds]
    return snap


async def create_share(conn, user, session: dict, *, sections, redact_identities, claim_ids, expires_in_hours: int,
                       confirm: bool) -> dict:
    if session["state"] not in ("COMPLETED", "COMPLETED_PARTIAL"):
        raise ApiError(409, "SESSION_NOT_READY", "Share after the recap is ready.")
    if not (1 <= expires_in_hours <= 24 * 30):
        raise ApiError(422, "INVALID_EXPIRY", "Links can last from 1 hour to 30 days.")
    snap = await build_recap_snapshot(conn, session, sections=sections, redact_identities=redact_identities, claim_ids=claim_ids)
    if not confirm:
        return {"preview": snap, "confirm_required": True}
    raw = secrets.token_urlsafe(32)
    expires = dt.datetime.now(dt.timezone.utc) + dt.timedelta(hours=expires_in_hours)
    sid = await conn.fetchval("INSERT INTO shares(tenant_id,space_id,session_id,token_hash,snapshot,options,expires_at,created_by)"
                              " VALUES ($1,$2,$3,$4,$5,$6,$7,$8) RETURNING share_id", session["tenant_id"], session["space_id"],
                              session["session_id"], hash_opaque(raw), snap,
                              {"sections": sections, "redact_identities": redact_identities}, expires, user.user_id)
    return {"share_id": sid, "token": raw, "path": f"/s/{raw}", "expires_at": expires, "preview": snap}


async def read_share(token: str) -> dict:
    async with db.system_tx() as conn:
        row = await conn.fetchrow("SELECT sh.snapshot, sh.expires_at, sh.revoked_at, sh.stale, s.deleted_at FROM shares sh"
                                  " JOIN sessions s ON s.session_id=sh.session_id WHERE sh.token_hash=$1", hash_opaque(token))
    if row is None or row["revoked_at"] is not None or row["deleted_at"] is not None or row["expires_at"] < dt.datetime.now(dt.timezone.utc):
        raise not_found("shared recap")
    return {"snapshot": row["snapshot"], "expires_at": row["expires_at"],
            "notice": "The owner corrected the source after sharing; some items may be outdated." if row["stale"] else None}


async def build_export(export_id: uuid.UUID) -> None:
    """User-reviewed export job. Includes user data with source metadata; other participants are referred to
    by session aliases unless the user verified a label and chose to include names."""
    s = get_settings()
    async with db.system_tx() as conn:
        ex = await conn.fetchrow("SELECT * FROM exports WHERE export_id=$1 FOR UPDATE", export_id)
        if ex is None or ex["status"] not in ("REQUESTED", "IN_PROGRESS"):
            return
        await conn.execute("UPDATE exports SET status='IN_PROGRESS' WHERE export_id=$1", export_id)
        scope = ex["scope"]
        include_names = bool(scope.get("include_verified_names"))
        where, args = "s.created_by=$1 AND s.deleted_at IS NULL", [ex["user_id"]]
        if scope.get("session_id"):
            where += " AND s.session_id=$2"
            args.append(uuid.UUID(scope["session_id"]))
        elif scope.get("space_id"):
            where += " AND s.space_id=$2"
            args.append(uuid.UUID(scope["space_id"]))
        sessions = await conn.fetch(f"SELECT s.* FROM sessions s WHERE {where} ORDER BY s.created_at", *args)
        doc = {"format": "meetsaathi-export", "version": 1, "exported_at": dt.datetime.now(dt.timezone.utc).isoformat(),
               "notice": "Your MeetSaathi data. Participant names appear only where you verified them and chose to include names.",
               "sessions": []}
        for sess in sessions:
            utt = await conn.fetch(
                "SELECT u.utterance_id, r.revision, r.start_ms, r.end_ms, r.transcript, r.is_final, r.provenance::text AS provenance,"
                " r.speaker_label_snapshot, sp.alias FROM utterances u JOIN utterance_revisions r ON r.utterance_id=u.utterance_id"
                " AND r.revision=u.current_revision LEFT JOIN session_speakers sp ON sp.speaker_alias_id=r.speaker_alias_id"
                " WHERE u.session_id=$1 ORDER BY r.start_ms", sess["session_id"])
            claims = await conn.fetch("SELECT claim_id, claim_kind, text_value, long_text, provenance::text AS provenance,"
                                      " decision_status::text AS decision_status, memory_state::text AS memory_state, owner_label, owner_confirmed,"
                                      " time_start_ms, time_end_ms, created_at FROM claims WHERE session_id=$1 AND memory_state<>'DELETED'",
                                      sess["session_id"])
            gaps = await conn.fetch("SELECT start_ms,end_ms,reason,missing_sequence_from,missing_sequence_to,time_bounds_estimated"
                                    " FROM capture_gaps WHERE session_id=$1", sess["session_id"])
            doc["sessions"].append({
                "session_id": str(sess["session_id"]), "title": sess["title"], "context": sess["context"],
                "created_at": sess["created_at"].isoformat(), "state": sess["state"], "capture_source": sess["capture_source"],
                "recap": sess["recap"], "gaps": [dict(g) for g in gaps], "capture_end_ms": sess["capture_end_ms"],
                "transcript": [{"utterance_id": str(u["utterance_id"]), "revision": u["revision"], "start_ms": u["start_ms"],
                                "end_ms": u["end_ms"], "text": u["transcript"], "is_final": u["is_final"], "provenance": u["provenance"],
                                "speaker": (u["speaker_label_snapshot"] if include_names else u["alias"]) or u["alias"]} for u in utt],
                "memories": [dict(c) | {"claim_id": str(c["claim_id"]), "created_at": c["created_at"].isoformat()} for c in claims],
                "audio_included": False})
        key = f"t/{ex['tenant_id']}/exports/{export_id}.json"
        await asyncio.to_thread(get_store().put, ex["tenant_id"], key, json.dumps(doc, default=str, ensure_ascii=False).encode())
        await conn.execute("UPDATE exports SET status='COMPLETE', object_key=$2, completed_at=now(),"
                           " expires_at=now()+make_interval(secs=>$3) WHERE export_id=$1", export_id, key, float(s.export_ttl_s))


async def invalidate_exports(conn, tenant_id) -> None:
    # A portable archive is a frozen derivative that may contain deleted content. Conservatively
    # revoke existing archives for the tenant; owners can request a fresh export of current data.
    await conn.execute("UPDATE exports SET status='EXPIRED', expires_at=now() WHERE tenant_id=$1"
                       " AND status IN ('REQUESTED','IN_PROGRESS','COMPLETE')", tenant_id)


async def purge_expired_exports(conn, tenant_id=None) -> int:
    rows = await conn.fetch("SELECT export_id,tenant_id,object_key FROM exports WHERE purged_at IS NULL"
                            " AND (status='EXPIRED' OR (status='COMPLETE' AND expires_at<=now())"
                            " OR (status='FAILED' AND created_at<now()-interval '1 hour'))"
                            " AND ($1::uuid IS NULL OR tenant_id=$1) FOR UPDATE", tenant_id)
    for row in rows:
        key = row["object_key"] or f"t/{row['tenant_id']}/exports/{row['export_id']}.json"
        await asyncio.to_thread(get_store().delete, key)
        await conn.execute("UPDATE exports SET status='EXPIRED', object_key=NULL, purged_at=now() WHERE export_id=$1", row["export_id"])
    return len(rows)
