"""Gated single-card intervention engine (master 5.2, IMP-013).

Pipeline per trigger: policy gate -> spend gate -> interrupt budget -> temporal gate -> candidate generation ->
evidence validation -> dedupe vs shown/dismissed -> explainable scoring -> output channel -> delivery.
Failing any gate yields SUPPRESS; there is no fallback filler. insight.candidate never leaves the server."""
from __future__ import annotations

import datetime as dt
import logging
import re
import uuid

from ..db import db
from ..domain import ops
from ..domain.events import append_event
from ..domain.policy import policy_for
from .evidence import recent_utterances
from .reasoner import ReasonerRefused, ReasonerUnavailable, get_reasoner, words

log = logging.getLogger("meetsaathi.insights")

CANDIDATE_SCHEMA = {
    "type": "object",
    "properties": {
        "candidates": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "kind": {"type": "string", "enum": ["CLARIFY", "TRADEOFF", "DECISION_UNRESOLVED", "FOLLOWUP", "LEARN",
                                                        "CONNECTION", "REMINDER", "TRANSLATION", "INTERVIEW_PRACTICE", "NO_ACTION"]},
                    "short_text": {"type": "string"},
                    "long_text": {"type": "string"},
                    "rationale": {"type": "string"},
                    "evidence_ids": {"type": "array", "items": {"type": "string"}},
                    "source_kind": {"type": "string", "enum": ["FROM_CONVERSATION", "AI_ANALYSIS", "GENERAL_KNOWLEDGE"]},
                    "relevance": {"type": "number"},
                    "timeliness": {"type": "number"},
                    "actionability": {"type": "number"},
                    "novelty": {"type": "number"},
                    "sensitivity": {"type": "string", "enum": ["NORMAL", "SENSITIVE"]},
                    "risk_level": {"type": "string", "enum": ["LOW", "MEDIUM", "HIGH"]},
                    "voice_text": {"type": "string"},
                },
                "required": ["kind", "short_text", "long_text", "rationale", "evidence_ids", "source_kind", "relevance",
                             "timeliness", "actionability", "novelty", "sensitivity", "risk_level", "voice_text"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["candidates"],
    "additionalProperties": False,
}

INSTRUCTION = """Propose at most 3 candidate interventions for the user RIGHT NOW, or a single NO_ACTION candidate.
Most of the time the correct answer is NO_ACTION: silence is a correct decision. Only propose something that is
actionable, novel (not already said or answered, not similar to recently shown or dismissed items), on-topic,
and still useful in the next minute. short_text: {min_w}-{max_w} words, plain, no greeting, starts with a useful verb
where possible (Ask, Confirm, Clarify, Compare, Check, Save). voice_text: <= 18 words, private-earbud phrasing.
Allowed kinds for this context: {kinds}. Use FROM_CONVERSATION only when the cited evidence directly supports the
claim; AI_ANALYSIS for your own reasoning grounded in cited evidence; GENERAL_KNOWLEDGE for outside facts.
Scores are 0..1 and must be honest. Mark SENSITIVE anything personal, health, financial or about a person."""


def _norm_tokens(text: str) -> set[str]:
    return {t for t in re.findall(r"[a-z0-9]+", text.lower()) if len(t) > 2}


def similarity(a: str, b: str) -> float:
    ta, tb = _norm_tokens(a), _norm_tokens(b)
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / len(ta | tb)


def score(c: dict, grounding: float, penalties: dict[str, float]) -> float:
    usefulness = 0.5 * float(c["relevance"]) + 0.3 * float(c["actionability"]) + 0.2 * float(c["novelty"])
    raw = usefulness * grounding * float(c["timeliness"])
    return round(raw - sum(penalties.values()), 4)


async def _suppress(conn, session, c: dict, reason: str, scores: dict | None = None) -> None:
    await conn.execute(
        "INSERT INTO insights(tenant_id,space_id,session_id,kind,short_text,long_text,rationale,evidence_refs,status,output_channel,"
        " policy_version,model_version,source_kind,scores,suppress_reason) VALUES ($1,$2,$3,$4,$5,$6,$7,$8,'SUPPRESSED','NONE',$9,$10,$11,$12,$13)",
        session["tenant_id"], session["space_id"], session["session_id"], c.get("kind", "NO_ACTION"), (c.get("short_text") or "-")[:500],
        c.get("long_text"), c.get("rationale"), c.get("_refs", []), policy_for(session["context"]).version,
        c.get("_model"), c.get("source_kind"), scores or {}, reason)


async def evaluate(session_id: uuid.UUID, *, triggered_at: str | None = None, deferrals: int = 0) -> dict:
    now = dt.datetime.now(dt.timezone.utc)
    async with db.system_tx() as conn:
        session = await conn.fetchrow("SELECT * FROM sessions WHERE session_id=$1 AND deleted_at IS NULL", session_id)
        if session is None:
            return {"outcome": "SUPPRESS", "reason": "SESSION_GONE"}
        session = dict(session)
        pol = policy_for(session["context"])
        rt = dict(await conn.fetchrow("SELECT * FROM session_runtime WHERE session_id=$1", session_id))
        # 1. Policy gate.
        reason = None
        if session["state"] != "RECORDING":
            reason = "NOT_RECORDING"
        elif not session["capture_permitted"]:
            reason = "CAPTURE_NOT_PERMITTED"
        elif not session["ai_assistance_permitted"]:
            reason = "LIVE_AI_NOT_PERMITTED"
        elif session["assistance_mode"] != "COMPANION":
            reason = "ASSISTANCE_NOT_COMPANION"
        elif session["proactive_intensity"] == "QUIET" or pol.budget(session["proactive_intensity"]) is None:
            reason = "QUIET"
        elif session["mute_until"] and session["mute_until"] > now:
            reason = "MUTED"
        elif not get_reasoner().available():
            reason = "REASONER_UNAVAILABLE"
        elif session["transcript_status"] == "DELAYED":
            reason = "CAPTIONS_DELAYED"  # backpressure: skip nonessential insights (master 7.3)
        elif rt["audio_quality"] is None:
            reason = "AUDIO_QUALITY_UNVERIFIED"  # input route changed; re-measure before advising (master 7.3)
        if reason:
            return {"outcome": "SUPPRESS", "reason": reason}
        budget = pol.budget(session["proactive_intensity"])
        # 2. Spend gate.
        q = await ops.quota_status(conn, session["tenant_id"])
        if q["reasoner_calls_used"] >= q["reasoner_calls_limit"]:
            return {"outcome": "SUPPRESS", "reason": "QUOTA"}
        # 3. Interrupt budget.
        last = await conn.fetchval("SELECT max(delivered_at) FROM insights WHERE session_id=$1 AND delivered_at IS NOT NULL", session_id)
        cooldown = budget.cooldown_s * float(rt["cooldown_multiplier"] or 1.0)
        if last and (now - last).total_seconds() < cooldown:
            return {"outcome": "SUPPRESS", "reason": "COOLDOWN"}
        n15 = await conn.fetchval("SELECT count(*) FROM insights WHERE session_id=$1 AND delivered_at > now() - interval '15 minutes'", session_id)
        if n15 >= budget.max_per_15_min:
            return {"outcome": "SUPPRESS", "reason": "BUDGET_CAP"}
        # User-initiated Ask outranks unsolicited suggestions (MTG-025).
        recent_ask = await conn.fetchval("SELECT 1 FROM ask_turns WHERE session_id=$1 AND created_at > now() - interval '30 seconds'", session_id)
        if recent_ask:
            return {"outcome": "SUPPRESS", "reason": "USER_ASK_PRECEDENCE"}
        # 4. Temporal gate: never interrupt while the user is speaking; defer briefly, then give up.
        if rt["user_speaking"] and rt["user_speaking_at"] and (now - rt["user_speaking_at"]).total_seconds() < 20:
            if deferrals < 3:
                await ops.enqueue(conn, tenant_id=session["tenant_id"], space_id=session["space_id"], session_id=session_id,
                                  kind="insight.evaluate", payload={"session_id": str(session_id), "triggered_at": triggered_at,
                                                                    "deferrals": deferrals + 1},
                                  key=f"insight:{session_id}:defer:{triggered_at}:{deferrals + 1}", delay_s=6, max_attempts=2)
            return {"outcome": "DEFER" if deferrals < 3 else "SUPPRESS", "reason": "USER_SPEAKING"}
        evidence = await recent_utterances(conn, session_id, since_ms=max(0, int(session["source_watermark_ms"]) - 180_000), limit=60)
        if not evidence.items:
            return {"outcome": "SUPPRESS", "reason": "NO_EVIDENCE"}
        shown = await conn.fetch("SELECT short_text, status, feedback FROM insights WHERE session_id=$1 AND status IN ('DELIVERED','DISMISSED','EXPIRED')"
                                 " AND created_at > now() - interval '45 minutes' ORDER BY created_at DESC LIMIT 12", session_id)
        await ops.meter(conn, session["tenant_id"], "reasoner_calls", 1)
        context_meta = {"context": session["context"], "preset": session["preset"], "title": session["title"],
                        "language": session["language"], "guidance": pol.live_guidance}

    reasoner = get_reasoner()
    try:
        res = await reasoner.structured(
            task="insight.candidates", system_extra=f"Context pack policy: {pol.live_guidance}",
            data_blocks={"session_context": context_meta,
                         "recent_items_already_shown_or_dismissed": [dict(r) for r in shown],
                         "untrusted_conversation_data": evidence.model_view()},
            instruction=INSTRUCTION.format(min_w=pol.preferred_words[0], max_w=pol.preferred_words[1],
                                           kinds=", ".join(pol.allowed_kinds)),
            schema=CANDIDATE_SCHEMA, effort="low", max_tokens=3000)
    except (ReasonerUnavailable, ReasonerRefused) as e:
        log.info("insight generation unavailable: %s", type(e).__name__)
        return {"outcome": "SUPPRESS", "reason": "MODEL_UNAVAILABLE"}

    done = dt.datetime.now(dt.timezone.utc)
    async with db.system_tx() as conn:
        session = dict(await conn.fetchrow("SELECT * FROM sessions WHERE session_id=$1 FOR UPDATE", session_id))
        rt = dict(await conn.fetchrow("SELECT * FROM session_runtime WHERE session_id=$1", session_id))
        # Re-check the gates that can change while the model was thinking (pause, mute, route, ask).
        if session["state"] != "RECORDING" or session["assistance_mode"] != "COMPANION" or session["proactive_intensity"] == "QUIET" \
                or (session["mute_until"] and session["mute_until"] > done) or not session["ai_assistance_permitted"]:
            return {"outcome": "SUPPRESS", "reason": "STATE_CHANGED"}
        from .evidence import evidence_current

        if not await evidence_current(conn, evidence):
            return {"outcome": "SUPPRESS", "reason": "EVIDENCE_CHANGED"}
        if triggered_at and (done - dt.datetime.fromisoformat(triggered_at)).total_seconds() > 30:
            for c in res.data.get("candidates", []):
                c["_model"] = res.model
                await _suppress(conn, session, c, "STALE")
            return {"outcome": "SUPPRESS", "reason": "STALE"}  # MTG-028: discard rather than surface late
        shown_texts = [r["short_text"] for r in await conn.fetch(
            "SELECT short_text FROM insights WHERE session_id=$1 AND status IN ('DELIVERED','DISMISSED','EXPIRED','SUPPRESSED')"
            " AND created_at > now() - interval '45 minutes'", session_id)]
        best, best_score, best_scores = None, -1.0, {}
        for c in res.data.get("candidates", []):
            c["_model"] = res.model
            if c["kind"] == "NO_ACTION":
                await _suppress(conn, session, c, "NO_ACTION")
                continue
            if c["kind"] not in pol.allowed_kinds:
                await _suppress(conn, session, c, "KIND_NOT_ALLOWED")
                continue
            n = words(c["short_text"])
            if n == 0 or n > pol.max_live_words:
                await _suppress(conn, session, c, "TOO_LONG")
                continue
            cited = evidence.resolve(c["evidence_ids"])
            c["_refs"] = [e.citation() for e in cited]
            if c["source_kind"] == "FROM_CONVERSATION" and not cited:
                await _suppress(conn, session, c, "MISSING_EVIDENCE")
                continue
            grounding = 1.0 if cited else (0.7 if c["source_kind"] == "GENERAL_KNOWLEDGE" else 0.5)
            penalties: dict[str, float] = {}
            if c["sensitivity"] == "SENSITIVE":
                penalties["sensitivity"] = 0.3
            if c["risk_level"] == "HIGH":
                penalties["risk"] = 0.2
            if cited and all((e.asr_confidence is not None and e.asr_confidence < 0.5) for e in cited):
                penalties["weak_capture"] = 0.3
            if any(e.overlap for e in cited):
                penalties["overlap_attribution"] = 0.1
            if rt["audio_quality"] in ("POOR", "SILENT_OR_BLOCKED"):
                penalties["audio_quality"] = 0.2
            dup = max((similarity(c["short_text"], t) for t in shown_texts), default=0.0)
            if dup >= 0.5:
                await _suppress(conn, session, c, "DUPLICATE")
                continue
            sc = score(c, grounding, penalties)
            scores = {"score": sc, "grounding": grounding, "penalties": penalties, "relevance": c["relevance"],
                      "timeliness": c["timeliness"], "actionability": c["actionability"], "novelty": c["novelty"]}
            if sc < budget_threshold(session):
                await _suppress(conn, session, c, "BELOW_THRESHOLD", scores)
                continue
            if sc > best_score:
                if best is not None:
                    await _suppress(conn, session, best, "OUTRANKED", best_scores)
                best, best_score, best_scores = c, sc, scores
            else:
                await _suppress(conn, session, c, "OUTRANKED", scores)
        if best is None:
            return {"outcome": "SUPPRESS", "reason": "NO_QUALIFYING_CANDIDATE"}
        channel = "TEXT"
        if session["output_mode"] in ("PRIVATE_VOICE", "BOTH") and rt["private_route_verified"] and best["sensitivity"] != "SENSITIVE":
            channel = session["output_mode"]
        expires = done + dt.timedelta(seconds=120)
        # Only one prominent card: anything still showing is retired when a new one arrives.
        retired = await conn.fetch("UPDATE insights SET status='EXPIRED', suppress_reason='REPLACED' WHERE session_id=$1 AND status='DELIVERED'"
                                   " AND expires_at > now() RETURNING insight_id", session_id)
        for r in retired:
            await append_event(conn, session, "insight.expired", {"insight_id": str(r["insight_id"]), "reason": "REPLACED"})
        iid = await conn.fetchval(
            "INSERT INTO insights(tenant_id,space_id,session_id,kind,short_text,long_text,rationale,evidence_refs,status,output_channel,"
            " policy_version,model_version,expires_at,source_kind,scores,delivered_at,voice_text) VALUES"
            " ($1,$2,$3,$4,$5,$6,$7,$8,'DELIVERED',$9,$10,$11,$12,$13,$14,now(),$15) RETURNING insight_id",
            session["tenant_id"], session["space_id"], session_id, best["kind"], best["short_text"], best["long_text"],
            best["rationale"], best["_refs"], channel, policy_for(session["context"]).version, res.model, expires,
            best["source_kind"], best_scores, best["voice_text"] if channel != "TEXT" else None)
        await append_event(conn, session, "insight.delivered", {
            "insight_id": str(iid), "short_text": best["short_text"], "kind": best["kind"], "source_refs": best["_refs"],
            "expires_at": expires.isoformat().replace("+00:00", "Z"), "policy_version": policy_for(session["context"]).version,
            "output_channel": channel, "source_kind": best["source_kind"],
            "label": {"FROM_CONVERSATION": "From conversation", "AI_ANALYSIS": "MeetSaathi suggests",
                      "GENERAL_KNOWLEDGE": "Outside explanation"}[best["source_kind"]],
            "voice_text": best["voice_text"] if channel != "TEXT" else None,
            "voice_max_seconds": policy_for(session["context"]).voice_max_seconds})
        return {"outcome": "DELIVERED", "insight_id": str(iid), "score": best_score}


def budget_threshold(session: dict) -> float:
    b = policy_for(session["context"]).budget(session["proactive_intensity"])
    return b.min_score if b else 2.0


FEEDBACK = {"USEFUL", "NOT_USEFUL", "TOO_FREQUENT", "INCORRECT", "TOO_LATE", "DISMISSED", "SAVED"}


async def feedback(conn, user, session: dict, insight_id: uuid.UUID, value: str) -> dict:
    from ..errors import ApiError, not_found

    if value not in FEEDBACK:
        raise ApiError(422, "INVALID_FEEDBACK", "Unsupported feedback.")
    ins = await conn.fetchrow("SELECT * FROM insights WHERE insight_id=$1 AND session_id=$2 AND status<>'SUPPRESSED'",
                              insight_id, session["session_id"])
    if ins is None:
        raise not_found("suggestion")
    status = ins["status"]
    saved_claim = ins["saved_claim_id"]
    if value == "DISMISSED" and status == "DELIVERED":
        status = "DISMISSED"
    if value == "TOO_FREQUENT":
        await conn.execute("UPDATE session_runtime SET cooldown_multiplier = LEAST(cooldown_multiplier * 1.5, 4.0) WHERE session_id=$1",
                           session["session_id"])
    if value == "SAVED" and saved_claim is None:
        # Saved as AI guidance, never as a participant statement (INT-045).
        saved_claim = await conn.fetchval(
            "INSERT INTO claims(tenant_id,space_id,session_id,claim_kind,text_value,long_text,provenance,memory_state,model_version,"
            " policy_version,created_by,metadata) VALUES ($1,$2,$3,'SUGGESTION',$4,$5,'AI_ANALYSIS','PENDING_REVIEW',$6,$7,$8,$9) RETURNING claim_id",
            session["tenant_id"], session["space_id"], session["session_id"], ins["short_text"], ins["long_text"],
            ins["model_version"], ins["policy_version"], user.user_id, {"insight_id": str(insight_id), "evidence_refs": ins["evidence_refs"]})
        for ref in ins["evidence_refs"] or []:
            if "utterance_id" in ref:
                await conn.execute("INSERT INTO claim_sources(claim_id,tenant_id,space_id,utterance_id,utterance_revision) VALUES ($1,$2,$3,$4,$5)"
                                   " ON CONFLICT DO NOTHING", saved_claim, session["tenant_id"], session["space_id"],
                                   uuid.UUID(ref["utterance_id"]), int(ref["revision"]))
        if status == "DELIVERED":
            status = "DISMISSED"
    await conn.execute("UPDATE insights SET feedback=$2, status=$3, saved_claim_id=$4 WHERE insight_id=$1", insight_id, value, status, saved_claim)
    if status != ins["status"]:
        await append_event(conn, session, "insight.expired", {"insight_id": str(insight_id), "reason": value})
    return {"insight_id": insight_id, "status": status, "feedback": value, "saved_claim_id": saved_claim}


async def why(conn, session: dict, insight_id: uuid.UUID) -> dict:
    from ..errors import not_found

    ins = await conn.fetchrow("SELECT insight_id, kind, short_text, long_text, rationale, evidence_refs, source_kind, output_channel,"
                              " status, expires_at, delivered_at, policy_version, model_version FROM insights"
                              " WHERE insight_id=$1 AND session_id=$2 AND status<>'SUPPRESSED'", insight_id, session["session_id"])
    if ins is None:
        raise not_found("suggestion")
    d = dict(ins)
    d["label"] = "MeetSaathi analysis" if d["source_kind"] != "FROM_CONVERSATION" else "From conversation"
    d["not_current"] = d["status"] != "DELIVERED" or (d["expires_at"] and d["expires_at"] < dt.datetime.now(dt.timezone.utc))
    return d
