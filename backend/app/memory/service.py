"""Memory items: notes, bookmarks ("Save moment"), recollections, review-to-keep, retain, decision lineage,
action ownership confirmation. Provenance is explicit on every item: recorded / user note / user recollection /
AI analysis / AI simulation - never blended (master 6.1 key distinctions)."""
from __future__ import annotations

import uuid

from ..domain import ops
from ..domain.events import append_event
from ..errors import ApiError, conflict, not_found
from .deletion import request_session_deletion

NOTE_KINDS = {"NOTE": "USER_NOTE", "RECOLLECTION": "USER_RECOLLECTION", "BOOKMARK": "USER_NOTE", "QUESTION": "USER_NOTE",
              "IDEA": "USER_NOTE", "COMMITMENT": "USER_NOTE"}
DECISION_FLOW = {
    None: {"PROPOSED", "DISCUSSED", "UNRESOLVED"},
    "PROPOSED": {"DISCUSSED", "ACCEPTED", "REJECTED", "DEFERRED", "UNRESOLVED"},
    "DISCUSSED": {"ACCEPTED", "REJECTED", "DEFERRED", "UNRESOLVED"},
    "UNRESOLVED": {"DISCUSSED", "ACCEPTED", "REJECTED", "DEFERRED"},
    "DEFERRED": {"DISCUSSED", "ACCEPTED", "REJECTED", "UNRESOLVED"},
    "ACCEPTED": {"SUPERSEDED"},
    "REJECTED": {"SUPERSEDED", "DISCUSSED"},
    "SUPERSEDED": set(),
}


async def add_user_item(conn, user, session: dict, *, kind: str, text: str, client_id: str | None,
                        at_ms: int | None, window_ms: int | None) -> dict:
    """Notes and bookmarks work offline: the client generates client_id; re-sending is idempotent (LC-011)."""
    if kind not in NOTE_KINDS:
        raise ApiError(422, "INVALID_KIND", "Unsupported note type.")
    text = (text or "").strip()
    if kind != "BOOKMARK" and not text:
        raise ApiError(422, "EMPTY_NOTE", "Write something to save.")
    if len(text) > 8000:
        raise ApiError(422, "NOTE_TOO_LONG", "Notes can be up to 8000 characters.")
    if kind == "RECOLLECTION" and session["capture_source"] != "NONE" and session["context"] != "INTERVIEW":
        pass  # recollections are allowed anywhere; they are always labelled as such
    if client_id:
        existing = await conn.fetchrow("SELECT claim_id, created_at FROM claims WHERE session_id=$1 AND client_id=$2",
                                       session["session_id"], client_id)
        if existing:
            return {"claim_id": existing["claim_id"], "duplicate": True}
    start = end = None
    if kind == "BOOKMARK":
        at = at_ms if at_ms is not None else int(session["source_watermark_ms"])
        w = max(5000, min(int(window_ms or 30000), 90000))
        start, end = max(0, at - w), at
        text = text or "Saved moment"
    cid = await conn.fetchval(
        "INSERT INTO claims(tenant_id,space_id,session_id,project_id,claim_kind,text_value,provenance,memory_state,created_by,"
        " client_id,time_start_ms,time_end_ms,metadata) VALUES ($1,$2,$3,$4,$5,$6,$7::provenance_kind,'PENDING_REVIEW',$8,$9,$10,$11,$12)"
        " RETURNING claim_id",
        session["tenant_id"], session["space_id"], session["session_id"], session["project_id"],
        "BOOKMARK" if kind == "BOOKMARK" else ("NOTE" if kind in ("NOTE", "QUESTION", "IDEA") else kind), text,
        NOTE_KINDS[kind], user.user_id, client_id, start, end, {"user_kind": kind})
    if kind == "BOOKMARK":
        await anchor_bookmark(conn, session, cid, start, end)
    return {"claim_id": cid, "duplicate": False, "time_start_ms": start, "time_end_ms": end,
            "uncertain_range": kind == "BOOKMARK"}


async def anchor_bookmark(conn, session: dict, claim_id, start, end) -> int:
    rows = await conn.fetch(
        "SELECT u.utterance_id, u.current_revision FROM utterances u JOIN utterance_revisions r ON r.utterance_id=u.utterance_id"
        " AND r.revision=u.current_revision WHERE u.session_id=$1 AND r.end_ms >= $2 AND r.start_ms <= $3",
        session["session_id"], start, end)
    for r in rows:
        await conn.execute("INSERT INTO claim_sources(claim_id,tenant_id,space_id,utterance_id,utterance_revision) VALUES ($1,$2,$3,$4,$5)"
                           " ON CONFLICT DO NOTHING", claim_id, session["tenant_id"], session["space_id"], r["utterance_id"],
                           r["current_revision"])
    return len(rows)


async def claim_view(conn, claim_id: uuid.UUID) -> dict:
    c = await conn.fetchrow("SELECT c.*, s.title AS session_title, s.created_at AS session_created_at, s.audio_deleted_at"
                            " FROM claims c LEFT JOIN sessions s ON s.session_id=c.session_id WHERE c.claim_id=$1", claim_id)
    if c is None:
        raise not_found("memory")
    d = dict(c)
    d.pop("search", None)
    src = await conn.fetch(
        "SELECT cs.utterance_id, cs.utterance_revision, r.start_ms, r.end_ms, r.transcript, r.is_final, r.speaker_label_snapshot,"
        " (u.current_revision = cs.utterance_revision) AS is_current FROM claim_sources cs"
        " JOIN utterance_revisions r ON r.utterance_id=cs.utterance_id AND r.revision=cs.utterance_revision"
        " JOIN utterances u ON u.utterance_id=cs.utterance_id WHERE cs.claim_id=$1 ORDER BY r.start_ms", claim_id)
    d["sources"] = [dict(s) | {"replay_available": d["audio_deleted_at"] is None} for s in src]
    if d["claim_kind"] == "DECISION":
        d["decision_history"] = [dict(r) for r in await conn.fetch(
            "SELECT from_state, to_state, actor, utterance_id, utterance_revision, note, created_at FROM decision_events"
            " WHERE claim_id=$1 ORDER BY created_at", claim_id)]
    d["provenance_label"] = {"RECORDED": "From conversation", "USER_NOTE": "My note", "USER_RECOLLECTION": "User recollection",
                             "AI_ANALYSIS": "MeetSaathi analysis", "AI_SIMULATION": "Practice simulation",
                             "IMPORTED": "Imported material"}[d["provenance"]]
    return d


async def update_decision(conn, user, claim: dict, *, to_state: str, utterance_id: uuid.UUID | None, note: str | None,
                          expected_version: int) -> dict:
    if claim["claim_kind"] != "DECISION":
        raise ApiError(422, "NOT_A_DECISION", "Only decisions have a status.")
    if claim["version"] != expected_version:
        raise conflict("VERSION_CONFLICT", "This decision changed. Review the latest version.", {"current_version": claim["version"]})
    cur = claim["decision_status"]
    if to_state not in DECISION_FLOW.get(cur, set()):
        raise conflict("INVALID_DECISION_TRANSITION", "That status change isn't valid for this decision.", {"current": cur})
    rev = None
    if utterance_id is not None:
        rev = await conn.fetchval("SELECT current_revision FROM utterances WHERE utterance_id=$1 AND session_id=$2",
                                  utterance_id, claim["session_id"])
        if rev is None:
            raise ApiError(422, "INVALID_SOURCE", "Pick a moment from this session as the source.")
    elif to_state in ("ACCEPTED", "REJECTED"):
        # A user may confirm from their own knowledge; the history records it as a user attestation.
        note = note or "Confirmed by user"
    await conn.execute("UPDATE claims SET decision_status=$2::decision_state, version=version+1, updated_at=now() WHERE claim_id=$1",
                       claim["claim_id"], to_state)
    await conn.execute("INSERT INTO decision_events(claim_id,tenant_id,space_id,from_state,to_state,utterance_id,utterance_revision,actor,note)"
                       " VALUES ($1,$2,$3,$4::decision_state,$5::decision_state,$6,$7,'USER',$8)",
                       claim["claim_id"], claim["tenant_id"], claim["space_id"], cur, to_state, utterance_id, rev, note)
    return await claim_view(conn, claim["claim_id"])


async def confirm_owner(conn, user, claim: dict, owner_label: str | None, due_text: str | None, expected_version: int) -> dict:
    if claim["claim_kind"] not in ("ACTION", "COMMITMENT"):
        raise ApiError(422, "NOT_AN_ACTION", "Only actions have owners.")
    if claim["version"] != expected_version:
        raise conflict("VERSION_CONFLICT", "This action changed. Review the latest version.", {"current_version": claim["version"]})
    await conn.execute("UPDATE claims SET owner_label=$2, owner_confirmed=$3, due_text=$4, version=version+1, updated_at=now() WHERE claim_id=$1",
                       claim["claim_id"], (owner_label or "").strip() or None, bool((owner_label or "").strip()), (due_text or "").strip() or None)
    return await claim_view(conn, claim["claim_id"])


async def retain(conn, user, space_id: uuid.UUID, claim_ids: list[uuid.UUID]) -> dict:
    """Approve selected evidence as durable memory (user opt-in only; ADR-012)."""
    if not await conn.fetchval("SELECT may_write_space(tenant_id,$1) FROM spaces WHERE space_id=$1", space_id):
        raise ApiError(403, "SCOPE_DENIED", "That memory isn't available in this space.")
    rows = await conn.fetch("SELECT claim_id, memory_state, space_id FROM claims WHERE claim_id = ANY($1::uuid[])", claim_ids)
    found = {r["claim_id"]: r for r in rows}
    approved, rejected = [], []
    for cid in claim_ids:
        r = found.get(cid)
        if r is None or r["space_id"] != space_id:
            rejected.append({"claim_id": cid, "reason": "NOT_IN_SPACE"})
        elif r["memory_state"] == "INVALIDATED":
            rejected.append({"claim_id": cid, "reason": "INVALIDATED_REVIEW_SOURCE"})
        else:
            await conn.execute("UPDATE claims SET memory_state='APPROVED', updated_at=now() WHERE claim_id=$1", cid)
            approved.append(cid)
    if approved:
        await ops.enqueue(conn, tenant_id=user.tenant_id, space_id=space_id, session_id=None, kind="memory.reindex_claims",
                          payload={"claim_ids": [str(c) for c in approved]}, key=f"reindex_claims:{uuid.uuid4()}")
    return {"approved": approved, "rejected": rejected}


async def review_session(conn, user, session: dict, *, keep_claim_ids: list[uuid.UUID], discard_session: bool,
                         exclude_from_suggestions: bool) -> dict:
    """End-of-session choice: Keep selected / Discard (CON-058/059). Status reflects committed storage only."""
    if session["state"] not in ("COMPLETED", "COMPLETED_PARTIAL", "FINALIZING", "FINALIZATION_RETRYABLE", "NOTES_ONLY"):
        raise conflict("SESSION_NOT_ENDED", "End the session before reviewing what to keep.")
    if discard_session:
        out = await request_session_deletion(conn, user, session)
        return {"review_state": "DISCARDED", "deletion": out}
    res = await retain(conn, user, session["space_id"], keep_claim_ids) if keep_claim_ids else {"approved": [], "rejected": []}
    # Items not kept remain reviewable drafts; under EPHEMERAL retention the session expires unless kept.
    await conn.execute("UPDATE sessions SET review_state='KEPT', retention_policy_id=CASE WHEN retention_policy_id='EPHEMERAL'"
                       " THEN 'KEEP_SELECTED' ELSE retention_policy_id END, version=version+1 WHERE session_id=$1", session["session_id"])
    if exclude_from_suggestions:
        await conn.execute("UPDATE claims SET exclude_from_suggestions=true WHERE session_id=$1", session["session_id"])
    await append_event(conn, session, "session.status", {"code": "REVIEW_SAVED", "message": "Your choices were saved.", "severity": "info"})
    return {"review_state": "KEPT", **res}
