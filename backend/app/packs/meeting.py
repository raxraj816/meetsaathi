"""Recap views (U10/M17/L12/C11), the cross-session decision timeline (M19, J9) and next-meeting / next-time
briefs (M22/C15/S21). Outcomes come before text walls; every item keeps its provenance label."""
from __future__ import annotations

import uuid

from ..domain.sessions import gaps
from ..errors import ApiError
from ..intelligence.reasoner import ReasonerRefused, ReasonerUnavailable, get_reasoner
from ..memory.retrieval import Scope

PROV_LABEL = {"RECORDED": "From conversation", "USER_NOTE": "My note", "USER_RECOLLECTION": "User recollection",
              "AI_ANALYSIS": "MeetSaathi suggests", "AI_SIMULATION": "Practice simulation", "IMPORTED": "Imported material"}


async def recap(conn, session: dict) -> dict:
    claims = await conn.fetch(
        "SELECT c.claim_id, c.claim_kind, c.text_value, c.long_text, c.provenance::text AS provenance, c.decision_status::text AS decision_status,"
        " c.memory_state::text AS memory_state, c.owner_label, c.owner_confirmed, c.due_text, c.time_start_ms, c.time_end_ms, c.version,"
        " c.invalidated_at, c.invalidation_reason,"
        " COALESCE((SELECT jsonb_agg(jsonb_build_object('utterance_id', cs.utterance_id, 'revision', cs.utterance_revision, 'start_ms', r.start_ms,"
        "  'end_ms', r.end_ms, 'speaker', r.speaker_label_snapshot, 'is_current', u.current_revision = cs.utterance_revision) ORDER BY r.start_ms)"
        "  FROM claim_sources cs JOIN utterance_revisions r ON r.utterance_id=cs.utterance_id AND r.revision=cs.utterance_revision"
        "  JOIN utterances u ON u.utterance_id=cs.utterance_id WHERE cs.claim_id=c.claim_id), '[]'::jsonb) AS sources"
        " FROM claims c WHERE c.session_id=$1 AND c.memory_state <> 'DELETED' ORDER BY c.time_start_ms NULLS LAST, c.created_at",
        session["session_id"])
    groups: dict[str, list] = {"decisions": [], "actions": [], "open_questions": [], "risks": [], "concepts": [], "lessons": [],
                               "commitments": [], "ideas": [], "bookmarks": [], "notes": [], "recollections": [], "ai_suggestions": []}
    key = {"DECISION": "decisions", "ACTION": "actions", "QUESTION": "open_questions", "RISK": "risks", "CONCEPT": "concepts",
           "LESSON": "lessons", "COMMITMENT": "commitments", "IDEA": "ideas", "BOOKMARK": "bookmarks", "NOTE": "notes",
           "RECOLLECTION": "recollections", "SUGGESTION": "ai_suggestions", "FACT": "notes", "QUOTE": "notes", "SUMMARY": "notes"}
    for c in claims:
        d = dict(c)
        d["label"] = PROV_LABEL[d["provenance"]]
        d["stale"] = d["memory_state"] == "INVALIDATED"
        if d["claim_kind"] in ("ACTION", "COMMITMENT"):
            d["owner_display"] = d["owner_label"] if (d["owner_label"] and d["owner_confirmed"]) else (
                f"{d['owner_label']} (unconfirmed)" if d["owner_label"] else "Owner unconfirmed")
        groups[key.get(d["claim_kind"], "notes")].append(d)
    speakers = [dict(r) for r in await conn.fetch(
        "SELECT alias, user_verified_label, mapping_revision, confidence FROM session_speakers WHERE session_id=$1 ORDER BY alias", session["session_id"])]
    g = await gaps(conn, session["session_id"])
    missing = [x for x in g if x["reason"] != "PAUSED_BY_USER"]
    utter_count = await conn.fetchval("SELECT count(*) FROM utterances WHERE session_id=$1", session["session_id"])
    return {
        "session_id": session["session_id"], "title": session["title"], "context": session["context"], "state": session["state"],
        "created_at": session["created_at"], "duration_ms": int(session["source_watermark_ms"]),
        "processing": {"finalization_status": session["finalization_status"], "transcript_status": session["transcript_status"],
                       "message": _processing_message(session)},
        "completeness": {"partial": session["state"] == "COMPLETED_PARTIAL" or bool(missing), "gaps": g,
                         "notes_only": session["capture_source"] == "NONE", "audio_deleted": session["audio_deleted_at"] is not None,
                         "utterances": utter_count},
        "recap": session["recap"], "speakers": speakers, "participants_confirmed": [s["user_verified_label"] for s in speakers if s["user_verified_label"]],
        **groups,
        "review_state": session["review_state"], "retention_policy_id": session["retention_policy_id"],
    }


def _processing_message(s: dict) -> str:
    st = s["state"]
    if st in ("STOPPING", "FINALIZING"):
        return "Recording stopped. Final notes are being prepared."
    if st == "FINALIZATION_RETRYABLE":
        return "Recording saved; recap is being retried."
    if st == "COMPLETED_PARTIAL":
        return "Final notes ready. Some audio was unavailable; gaps are shown."
    if st == "COMPLETED":
        return "Final notes ready."
    if st == "NOTES_ONLY":
        return "Notes-only. Nothing was recorded."
    return ""


async def decision_timeline(conn, scope: Scope) -> list[dict]:
    if scope.kind == "SELECTED_PROJECT":
        where, arg = "s.project_id=$1", scope.project_id
    elif scope.kind == "SELECTED_SPACE":
        where, arg = "c.space_id=$1", scope.space_id
    elif scope.kind == "CURRENT_SESSION":
        where, arg = "c.session_id=$1", scope.session_id
    else:
        raise ApiError(422, "SCOPE_REQUIRED", "Choose a project, space or session.")
    rows = await conn.fetch(
        "SELECT c.claim_id, c.text_value, c.decision_status::text AS decision_status, c.memory_state::text AS memory_state, c.session_id,"
        " s.title AS session_title, s.created_at AS session_date, c.time_start_ms, c.provenance::text AS provenance,"
        " (SELECT jsonb_agg(jsonb_build_object('from', d.from_state, 'to', d.to_state, 'actor', d.actor, 'utterance_id', d.utterance_id,"
        "   'revision', d.utterance_revision, 'at', d.created_at) ORDER BY d.created_at) FROM decision_events d WHERE d.claim_id=c.claim_id) AS history"
        f" FROM claims c JOIN sessions s ON s.session_id=c.session_id AND s.deleted_at IS NULL WHERE {where} AND c.claim_kind='DECISION'"
        " AND c.memory_state IN ('APPROVED','PENDING_REVIEW','INVALIDATED') ORDER BY s.created_at, c.time_start_ms NULLS LAST", arg)
    return [dict(r) | {"stale": r["memory_state"] == "INVALIDATED"} for r in rows]


BRIEF_SCHEMA = {"type": "object", "properties": {"questions": {"type": "array", "items": {"type": "string"}}},
                "required": ["questions"], "additionalProperties": False}


async def brief(conn, scope: Scope) -> dict:
    """Scope-controlled preparation across permitted history (IMP-020). Only APPROVED, valid evidence."""
    if scope.kind not in ("SELECTED_PROJECT", "SELECTED_SPACE"):
        raise ApiError(422, "SCOPE_REQUIRED", "Choose a project or space to prepare from.")
    where, arg = ("s.project_id=$1", scope.project_id) if scope.kind == "SELECTED_PROJECT" else ("c.space_id=$1", scope.space_id)
    rows = await conn.fetch(
        "SELECT c.claim_id, c.claim_kind, c.text_value, c.decision_status::text AS decision_status, c.owner_label, c.owner_confirmed,"
        " s.title AS session_title, s.created_at AS session_date, c.provenance::text AS provenance FROM claims c"
        f" JOIN sessions s ON s.session_id=c.session_id AND s.deleted_at IS NULL WHERE {where} AND c.memory_state='APPROVED'"
        " AND c.invalidated_at IS NULL AND NOT c.exclude_from_suggestions ORDER BY s.created_at DESC LIMIT 200", arg)
    last_agreed = [dict(r) for r in rows if r["claim_kind"] == "DECISION" and r["decision_status"] == "ACCEPTED"][:8]
    still_open = [dict(r) for r in rows if (r["claim_kind"] == "DECISION" and r["decision_status"] in ("PROPOSED", "DISCUSSED", "UNRESOLVED", "DEFERRED"))
                  or r["claim_kind"] in ("QUESTION", "RISK") or (r["claim_kind"] in ("ACTION", "COMMITMENT") and not r["owner_confirmed"])][:12]
    out = {"scope": scope.describe(), "last_agreed": last_agreed, "still_open": still_open, "questions_worth_asking": [],
           "questions_label": "MeetSaathi suggests", "empty": not rows}
    if not rows:
        out["message"] = "No reviewed memories in this scope yet."
        return out
    reasoner = get_reasoner()
    if reasoner.available():
        try:
            res = await reasoner.structured(
                task="brief.questions", system_extra="Preparation assistant.",
                data_blocks={"untrusted_conversation_data": [{"kind": r["claim_kind"], "status": r["decision_status"], "text": r["text_value"],
                                                              "session": r["session_title"]} for r in rows[:60]]},
                instruction="Suggest up to 3 concise questions worth asking next time, grounded in the open items. Return JSON.",
                schema=BRIEF_SCHEMA, effort="low", max_tokens=1500)
            out["questions_worth_asking"] = res.data["questions"][:3]
        except (ReasonerUnavailable, ReasonerRefused):
            out["questions_unavailable"] = True
    return out


async def session_ids_in_scope(conn, scope: Scope) -> list[uuid.UUID]:
    if scope.kind == "SELECTED_PROJECT":
        rows = await conn.fetch("SELECT session_id FROM sessions WHERE project_id=$1 AND deleted_at IS NULL", scope.project_id)
    elif scope.kind == "SELECTED_SPACE":
        rows = await conn.fetch("SELECT session_id FROM sessions WHERE space_id=$1 AND deleted_at IS NULL", scope.space_id)
    else:
        return [scope.session_id] if scope.session_id else []
    return [r["session_id"] for r in rows]
