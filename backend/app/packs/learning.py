"""Learning context pack (Learning spec 3.5-3.7, 6.4; IMP-017).

Explain this: last 30-90 s of permitted transcript, short answer first, explicit source kind; abstains and
bookmarks when capture is unclear. Practice: free-recall items from course evidence, answer hidden until
attempted, answer-dependent feedback. Review: transparent spaced schedule, editable/snoozable, no streaks.
Lineage HEARD -> EXPLAINED -> PRACTICED -> RETAINED (only with evidence of mastery)."""
from __future__ import annotations

import datetime as dt
import re
import uuid

from ..db import db
from ..domain import ops
from ..domain.policy import require_live_ai
from ..errors import ApiError, not_found
from ..intelligence.evidence import UTTERANCE_SQL, EvidenceSet, add_utterance_rows, recent_utterances
from ..intelligence.reasoner import ReasonerRefused, ReasonerUnavailable, get_reasoner
from ..memory.service import add_user_item

REVIEW_POLICY_VERSION = "review-2026-10-18.1"
INTERVALS = [1, 3, 7, 14, 30, 60]
ABSTAIN = "I didn't capture that clearly. I've marked this point for later."

EXPLAIN_SCHEMA = {
    "type": "object",
    "properties": {
        "concept": {"type": "string"},
        "one_line": {"type": "string"},
        "example": {"type": "string"},
        "why_it_matters": {"type": "string"},
        "lecture_statements": {"type": "array", "items": {"type": "object", "properties": {
            "text": {"type": "string"}, "evidence_ids": {"type": "array", "items": {"type": "string"}}},
            "required": ["text", "evidence_ids"], "additionalProperties": False}},
        "visual_content_missing": {"type": "boolean"},
        "captured_clearly": {"type": "boolean"},
    },
    "required": ["concept", "one_line", "example", "why_it_matters", "lecture_statements", "visual_content_missing", "captured_clearly"],
    "additionalProperties": False,
}

PRACTICE_SCHEMA = {
    "type": "object",
    "properties": {"items": {"type": "array", "items": {"type": "object", "properties": {
        "concept": {"type": "string"}, "prompt": {"type": "string"}, "rubric": {"type": "string"},
        "kind": {"type": "string", "enum": ["FREE_RECALL", "SHORT_ANSWER", "EXPLAIN_BACK"]},
        "evidence_ids": {"type": "array", "items": {"type": "string"}}},
        "required": ["concept", "prompt", "rubric", "kind", "evidence_ids"], "additionalProperties": False}}},
    "required": ["items"], "additionalProperties": False,
}

GRADE_SCHEMA = {
    "type": "object",
    "properties": {"verdict": {"type": "string", "enum": ["CORRECT", "PARTIAL", "INCORRECT"]},
                   "feedback": {"type": "string"}, "missing_points": {"type": "array", "items": {"type": "string"}},
                   "next_step": {"type": "string"}},
    "required": ["verdict", "feedback", "missing_points", "next_step"], "additionalProperties": False,
}


def concept_key(concept: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", concept.lower()).strip("-")[:80] or "concept"


async def touch_review(conn, user, *, tenant_id, space_id, project_id, concept: str, lineage: str, verdict: str | None = None,
                       difficult: bool | None = None) -> None:
    key = concept_key(concept)
    row = await conn.fetchrow("SELECT * FROM review_schedule WHERE user_id=$1 AND space_id=$2 AND concept_key=$3",
                              user.user_id, space_id, key)
    order = ["HEARD", "EXPLAINED", "PRACTICED", "RETAINED"]
    now = dt.datetime.now(dt.timezone.utc)
    if row is None:
        await conn.execute("INSERT INTO review_schedule(tenant_id,space_id,user_id,project_id,concept_key,concept,due_at,interval_days,"
                           " lineage_state,difficult,last_verdict,policy_version) VALUES ($1,$2,$3,$4,$5,$6,$7,1,$8,$9,$10,$11)",
                           tenant_id, space_id, user.user_id, project_id, key, concept[:200], now + dt.timedelta(days=1), lineage,
                           bool(difficult), verdict, REVIEW_POLICY_VERSION)
        return
    interval = row["interval_days"]
    state = row["lineage_state"]
    if order.index(lineage) > order.index(state):
        state = lineage
    if verdict == "CORRECT":
        nxt = next((i for i in INTERVALS if i > interval), INTERVALS[-1])
        # RETAINED only with evidence of mastery: correct recall again after a >=7 day gap.
        if row["last_verdict"] == "CORRECT" and interval >= 7:
            state = "RETAINED"
        interval = nxt
    elif verdict == "PARTIAL":
        interval = max(1, interval)
    elif verdict == "INCORRECT":
        interval = 1
        if state == "RETAINED":
            state = "PRACTICED"
    due = now + dt.timedelta(days=interval) if verdict else row["due_at"]
    await conn.execute("UPDATE review_schedule SET lineage_state=$4, interval_days=$5, due_at=$6, last_verdict=COALESCE($7,last_verdict),"
                       " difficult=COALESCE($8,difficult), updated_at=now(), status=CASE WHEN status='REMOVED' THEN 'ACTIVE' ELSE status END"
                       " WHERE user_id=$1 AND space_id=$2 AND concept_key=$3",
                       user.user_id, space_id, key, state, interval, due, verdict, difficult)


async def explain(user, session: dict, window_s: int) -> dict:
    window_s = max(30, min(int(window_s or 60), 90))
    async with db.user_tx(user.user_id) as conn:
        require_live_ai(session)
        since = max(0, int(session["source_watermark_ms"]) - window_s * 1000)
        ev = await recent_utterances(conn, session["session_id"], since_ms=since, limit=40)
        usable = [i for i in ev.items if not (i.asr_confidence is not None and i.asr_confidence < 0.4)]
        reasoner = get_reasoner()
        if not usable:
            bm = await add_user_item(conn, user, session, kind="BOOKMARK", text="Explain later", client_id=None,
                                     at_ms=int(session["source_watermark_ms"]), window_ms=window_s * 1000)
            return {"status": "ABSTAINED", "message": ABSTAIN, "bookmark_id": bm["claim_id"], "source_kind": "INSUFFICIENT_EVIDENCE"}
        if not reasoner.available():
            bm = await add_user_item(conn, user, session, kind="BOOKMARK", text="Explain later", client_id=None,
                                     at_ms=int(session["source_watermark_ms"]), window_ms=window_s * 1000)
            return {"status": "UNAVAILABLE", "message": "I can save this moment; explanations are temporarily unavailable.",
                    "bookmark_id": bm["claim_id"]}
        await ops.require_reasoner_quota(conn, user.tenant_id)
    try:
        res = await reasoner.structured(
            task="learning.explain", system_extra="Learning companion. Be brief and kind. The learner is in a live class.",
            data_blocks={"untrusted_conversation_data": ev.model_view()},
            instruction="Explain the idea the lecturer is currently discussing. one_line <= 25 words. lecture_statements are what the "
                        "lecturer actually said (cite). If the passage is unclear set captured_clearly=false. If a board/slide/diagram "
                        "was referenced, set visual_content_missing=true. Return JSON.",
            schema=EXPLAIN_SCHEMA, effort="low", max_tokens=3000)
    except (ReasonerUnavailable, ReasonerRefused):
        async with db.user_tx(user.user_id) as conn:
            bm = await add_user_item(conn, user, session, kind="BOOKMARK", text="Explain later", client_id=None,
                                     at_ms=int(session["source_watermark_ms"]), window_ms=window_s * 1000)
        return {"status": "UNAVAILABLE", "message": "I can save this moment; explanations are temporarily unavailable.",
                "bookmark_id": bm["claim_id"]}
    d = res.data
    async with db.user_tx(user.user_id) as conn:
        await ops.meter(conn, user.tenant_id, "reasoner_calls", 1)
        if not d.get("captured_clearly", True):
            bm = await add_user_item(conn, user, session, kind="BOOKMARK", text=f"Unclear: {d.get('concept', '')}"[:200], client_id=None,
                                     at_ms=int(session["source_watermark_ms"]), window_ms=window_s * 1000)
            return {"status": "ABSTAINED", "message": ABSTAIN, "bookmark_id": bm["claim_id"], "source_kind": "INSUFFICIENT_EVIDENCE"}
        lecture = []
        for st in d.get("lecture_statements", []):
            items = ev.resolve(st.get("evidence_ids"))
            if items:
                lecture.append({"label": "From this lecture", "text": st["text"], "citations": [i.citation() for i in items]})
        if d.get("concept"):
            await touch_review(conn, user, tenant_id=session["tenant_id"], space_id=session["space_id"], project_id=session["project_id"],
                               concept=d["concept"], lineage="EXPLAINED")
    return {"status": "OK", "concept": d.get("concept"), "title": "Here's the idea",
            "answer": d.get("one_line"), "label": "AI explanation · not a quote",
            "example": d.get("example"), "why_it_matters": d.get("why_it_matters"), "from_lecture": lecture,
            "visual_content_missing": bool(d.get("visual_content_missing")),
            "visual_notice": "The lecturer referred to something visual that wasn't captured. Add a permitted photo or material to include it."
            if d.get("visual_content_missing") else None, "model_version": res.model}


async def generate_practice(user, *, session_id: uuid.UUID | None, project_id: uuid.UUID | None, count: int) -> dict:
    count = max(1, min(count, 8))
    reasoner = get_reasoner()
    async with db.user_tx(user.user_id) as conn:
        ev = EvidenceSet()
        if session_id:
            s = await conn.fetchrow("SELECT * FROM sessions WHERE session_id=$1 AND deleted_at IS NULL", session_id)
            if s is None:
                raise not_found("session")
            space_id, tenant_id, proj = s["space_id"], s["tenant_id"], s["project_id"]
            rows = await conn.fetch(UTTERANCE_SQL + " WHERE u.session_id=$1 ORDER BY r.start_ms LIMIT 400", session_id)
        elif project_id:
            p = await conn.fetchrow("SELECT * FROM projects WHERE project_id=$1 AND deleted_at IS NULL", project_id)
            if p is None:
                raise not_found("course")
            space_id, tenant_id, proj = p["space_id"], p["tenant_id"], project_id
            rows = await conn.fetch(UTTERANCE_SQL + " WHERE s.project_id=$1 ORDER BY s.created_at, r.start_ms LIMIT 500", project_id)
        else:
            raise ApiError(422, "SCOPE_REQUIRED", "Choose a session or course to practise.")
        add_utterance_rows(ev, rows)
        notes = await conn.fetch("SELECT claim_id, session_id, claim_kind, text_value, provenance::text AS provenance, time_start_ms, time_end_ms,"
                                 " created_at, version FROM claims WHERE (session_id=$1 OR ($2::uuid IS NOT NULL AND project_id=$2))"
                                 " AND claim_kind IN ('NOTE','CONCEPT','LESSON','BOOKMARK') AND memory_state IN ('APPROVED','PENDING_REVIEW')"
                                 " AND invalidated_at IS NULL LIMIT 60", session_id, proj)
        for r in notes:
            ev.add(kind="CLAIM", ref_id=r["claim_id"], revision=r["version"], session_id=r["session_id"], session_title=None,
                   session_date=r["created_at"].date().isoformat(), start_ms=r["time_start_ms"], end_ms=r["time_end_ms"], speaker=None,
                   speaker_verified=False, speaker_confidence=None, text=f"[{r['claim_kind']}] {r['text_value']}", is_final=True,
                   provenance=r["provenance"])
        if not ev.items:
            raise ApiError(422, "NO_MATERIAL", "There's no captured lecture or note to practise from yet. Add notes or materials first.")
        if not reasoner.available():
            raise ApiError(503, "AI_UNAVAILABLE", "Practice questions are temporarily unavailable.", retryable=True)
        await ops.require_reasoner_quota(conn, user.tenant_id)
    try:
        res = await reasoner.structured(
            task="learning.practice", system_extra="Retrieval-practice designer. Prefer free recall and explain-back over multiple choice.",
            data_blocks={"untrusted_conversation_data": ev.model_view()},
            instruction=f"Create {count} practice items about concepts actually covered in the material. rubric = the key points of a good "
                        "answer, citing evidence ids. Do not test content that was not captured. Return JSON.",
            schema=PRACTICE_SCHEMA, effort="medium", max_tokens=6000)
    except (ReasonerUnavailable, ReasonerRefused):
        raise ApiError(503, "AI_UNAVAILABLE", "Practice questions are temporarily unavailable.", retryable=True)
    out = []
    async with db.user_tx(user.user_id) as conn:
        await ops.meter(conn, user.tenant_id, "reasoner_calls", 1)
        for it in res.data.get("items", [])[:count]:
            anchors = ev.resolve(it.get("evidence_ids"))
            if not anchors:
                continue
            source_kind = "FROM_LECTURE" if any(a.kind == "UTTERANCE" for a in anchors) else "FROM_NOTES"
            iid = await conn.fetchval(
                "INSERT INTO practice_items(tenant_id,space_id,project_id,session_id,concept,prompt,rubric,kind,anchors,source_kind,created_by)"
                " VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11) RETURNING item_id", tenant_id, space_id, proj, session_id, it["concept"][:200],
                it["prompt"], it["rubric"], it["kind"], [a.citation() for a in anchors], source_kind, user.user_id)
            out.append({"item_id": iid, "concept": it["concept"], "prompt": it["prompt"], "kind": it["kind"], "source_kind": source_kind})
    return {"items": out, "note": "Answers are hidden until you attempt each item."}


async def attempt(user, item_id: uuid.UUID, response: str) -> dict:
    response = (response or "").strip()
    if not response:
        raise ApiError(422, "EMPTY_RESPONSE", "Write your answer first; the answer is shown after you try.")
    async with db.user_tx(user.user_id) as conn:
        item = await conn.fetchrow("SELECT * FROM practice_items WHERE item_id=$1 AND state<>'REMOVED'", item_id)
        if item is None:
            raise not_found("practice item")
        item = dict(item)
    reasoner = get_reasoner()
    verdict, feedback, missing, next_step, model = "UNGRADED", "Automatic feedback is unavailable right now. Compare your answer with the key points below.", [], "", None
    if reasoner.available():
        try:
            res = await reasoner.structured(
                task="learning.grade", system_extra="Supportive tutor. Grade only against the rubric; never penalise language or accent.",
                data_blocks={"rubric": item["rubric"], "question": item["prompt"], "untrusted_user_material": response},
                instruction="Grade the learner's answer. feedback explains why (2-3 sentences). Return JSON.",
                schema=GRADE_SCHEMA, effort="low", max_tokens=2000)
            verdict, feedback, missing, next_step, model = (res.data["verdict"], res.data["feedback"], res.data["missing_points"],
                                                            res.data["next_step"], res.model)
        except (ReasonerUnavailable, ReasonerRefused):
            pass
    async with db.user_tx(user.user_id) as conn:
        if model:
            await ops.meter(conn, user.tenant_id, "reasoner_calls", 1)
        aid = await conn.fetchval("INSERT INTO practice_attempts(item_id,tenant_id,space_id,user_id,response,verdict,feedback,citations)"
                                  " VALUES ($1,$2,$3,$4,$5,$6,$7,$8) RETURNING attempt_id", item_id, item["tenant_id"], item["space_id"],
                                  user.user_id, response, verdict, feedback, item["anchors"])
        await touch_review(conn, user, tenant_id=item["tenant_id"], space_id=item["space_id"], project_id=item["project_id"],
                           concept=item["concept"], lineage="PRACTICED", verdict=None if verdict == "UNGRADED" else verdict)
    return {"attempt_id": aid, "verdict": verdict, "feedback": feedback, "missing_points": missing, "next_step": next_step,
            "key_points": item["rubric"], "sources": item["anchors"], "source_kind": item["source_kind"],
            "note": "A practice score shows how this attempt went, not lifelong mastery."}


async def due_reviews(conn, user, space_id: uuid.UUID | None) -> list[dict]:
    sql = "SELECT * FROM review_schedule WHERE user_id=$1 AND status='ACTIVE'"
    args: list = [user.user_id]
    if space_id:
        sql += " AND space_id=$2"
        args.append(space_id)
    rows = await conn.fetch(sql + " ORDER BY due_at LIMIT 100", *args)
    now = dt.datetime.now(dt.timezone.utc)
    return [dict(r) | {"due": r["due_at"] <= now} for r in rows]


async def update_review(conn, user, space_id: uuid.UUID, key: str, *, action: str, days: int | None) -> dict:
    row = await conn.fetchrow("SELECT * FROM review_schedule WHERE user_id=$1 AND space_id=$2 AND concept_key=$3", user.user_id, space_id, key)
    if row is None:
        raise not_found("review")
    now = dt.datetime.now(dt.timezone.utc)
    if action == "SNOOZE":
        d = max(1, min(int(days or 1), 30))
        await conn.execute("UPDATE review_schedule SET due_at=$4, updated_at=now() WHERE user_id=$1 AND space_id=$2 AND concept_key=$3",
                           user.user_id, space_id, key, max(row["due_at"], now) + dt.timedelta(days=d))
    elif action == "DIFFICULT":
        await conn.execute("UPDATE review_schedule SET difficult=true, interval_days=1, due_at=$4, updated_at=now()"
                           " WHERE user_id=$1 AND space_id=$2 AND concept_key=$3", user.user_id, space_id, key, now + dt.timedelta(days=1))
    elif action == "RESET":
        await conn.execute("UPDATE review_schedule SET interval_days=1, due_at=$4, lineage_state='HEARD', last_verdict=NULL, updated_at=now()"
                           " WHERE user_id=$1 AND space_id=$2 AND concept_key=$3", user.user_id, space_id, key, now + dt.timedelta(days=1))
    elif action == "REMOVE":
        await conn.execute("UPDATE review_schedule SET status='REMOVED', updated_at=now() WHERE user_id=$1 AND space_id=$2 AND concept_key=$3",
                           user.user_id, space_id, key)
    elif action == "RESCHEDULE":
        d = max(0, min(int(days or 1), 365))
        await conn.execute("UPDATE review_schedule SET due_at=$4, status='ACTIVE', updated_at=now() WHERE user_id=$1 AND space_id=$2 AND concept_key=$3",
                           user.user_id, space_id, key, now + dt.timedelta(days=d))
    else:
        raise ApiError(422, "INVALID_ACTION", "Unsupported review action.")
    return dict(await conn.fetchrow("SELECT * FROM review_schedule WHERE user_id=$1 AND space_id=$2 AND concept_key=$3", user.user_id, space_id, key))
