"""Ask response grammar (master 5.3): Remember / Think / Learn / Prepare with explicit scope.

* Remember: permitted evidence only; every statement carries verified citations, else
  "I can't verify that from the available conversation."  Works without a reasoner (extractive).
* Think: independent analysis labelled "MeetSaathi analysis", never a transcript fact.
* Learn: pedagogical explanation; general knowledge labelled; optional checking question.
* Prepare: follow-ups / actions as PROPOSALS needing explicit approval; nothing is executed.
"""
from __future__ import annotations

import uuid

from ..db import db
from ..domain import ops
from ..domain.events import append_event
from ..domain.state_machine import ACTIVE_STATES, S
from ..errors import ApiError, policy_denied, unavailable
from ..memory.retrieval import Scope, resolve_scope, search
from .evidence import EvidenceSet
from .reasoner import ReasonerRefused, ReasonerUnavailable, get_reasoner

NO_EVIDENCE = "I can't verify that from the available conversation."
MODES = ("REMEMBER", "THINK", "LEARN", "PREPARE")

STATEMENTS_SCHEMA = {
    "type": "object",
    "properties": {
        "statements": {"type": "array", "items": {
            "type": "object",
            "properties": {"text": {"type": "string"}, "evidence_ids": {"type": "array", "items": {"type": "string"}}},
            "required": ["text", "evidence_ids"], "additionalProperties": False}},
        "insufficient_evidence": {"type": "boolean"},
        "uncertainty": {"type": "string"},
    },
    "required": ["statements", "insufficient_evidence", "uncertainty"],
    "additionalProperties": False,
}

ANALYSIS_SCHEMA = {
    "type": "object",
    "properties": {
        "context_statements": {"type": "array", "items": {
            "type": "object",
            "properties": {"text": {"type": "string"}, "evidence_ids": {"type": "array", "items": {"type": "string"}}},
            "required": ["text", "evidence_ids"], "additionalProperties": False}},
        "analysis": {"type": "string"},
        "alternatives": {"type": "array", "items": {"type": "string"}},
        "unknowns": {"type": "array", "items": {"type": "string"}},
        "knowledge_kind": {"type": "string", "enum": ["AI_ANALYSIS", "GENERAL_KNOWLEDGE"]},
        "check_question": {"type": "string"},
        "proposed_actions": {"type": "array", "items": {
            "type": "object",
            "properties": {"kind": {"type": "string", "enum": ["FOLLOW_UP_QUESTION", "TASK", "REMINDER", "AGENDA_ITEM", "STUDY_STEP",
                                                                "MESSAGE_DRAFT"]},
                           "text": {"type": "string"}},
            "required": ["kind", "text"], "additionalProperties": False}},
        "uncertainty": {"type": "string"},
    },
    "required": ["context_statements", "analysis", "alternatives", "unknowns", "knowledge_kind", "check_question",
                 "proposed_actions", "uncertainty"],
    "additionalProperties": False,
}

MODE_GUIDANCE = {
    "REMEMBER": "Answer ONLY from the evidence. Each statement must cite the evidence ids that support it. "
                "Paraphrase faithfully; quote only exact words. If the evidence does not establish the answer, set "
                "insufficient_evidence=true and return no unsupported statements. Absence of evidence is not evidence of absence. "
                "If speakers are unverified, refer to them by alias. If evidence is provisional or overlapping, say so in uncertainty.",
    "THINK": "Give independent reasoning: evaluation, alternatives, counterarguments and unknowns. Context statements (what was "
             "actually said) must cite evidence; analysis is your own view and must not claim anyone said it. Never assert another "
             "person's hidden motive or emotion; offer hypotheses with uncertainty. proposed_actions may be empty.",
    "LEARN": "Teach the concept: short explanation, then a simple example. Tie to captured material only with citations; label "
             "outside knowledge as GENERAL_KNOWLEDGE. If a visual (board, slide, diagram) was referenced but not captured, say it "
             "was not captured. Provide one short check_question when useful.",
    "PREPARE": "Suggest concrete follow-ups, questions, agenda items or study steps grounded in the evidence. These are proposals "
               "for the user to review; nothing will be sent or scheduled. Do not invent owners or deadlines.",
}


def _label_for(items) -> str:
    kinds = {i.provenance for i in items}
    if any(i.kind == "UTTERANCE" for i in items):
        return "FROM_CONVERSATION"
    if kinds & {"USER_NOTE", "USER_RECOLLECTION"}:
        return "FROM_USER_NOTE"
    return "FROM_CONVERSATION" if items else "INSUFFICIENT_EVIDENCE"


def _uncertainty_notes(items) -> list[str]:
    notes = []
    if any(i.kind == "UTTERANCE" and not i.is_final for i in items):
        notes.append("Based on the provisional live transcript.")
    if any(i.kind == "UTTERANCE" and not i.speaker_verified for i in items):
        notes.append("Speaker identities are not confirmed.")
    if any(i.overlap for i in items):
        notes.append("Some speech overlapped; attribution is uncertain.")
    if any(i.provenance == "USER_RECOLLECTION" for i in items):
        notes.append("Includes your own recollection, not a verified recording.")
    if any(i.provenance == "USER_NOTE" for i in items) and not any(i.kind == "UTTERANCE" for i in items):
        notes.append("Source is your note only; no recording supports it.")
    return notes


def _extractive(ev: EvidenceSet) -> dict:
    recorded = [i for i in ev.items if i.kind == "UTTERANCE"][:3]
    top = recorded or ev.items[:3]
    lines = []
    for i in top:
        if i.kind == "UTTERANCE":
            lines.append(f"{i.speaker or 'Unassigned'} at {(i.start_ms or 0) // 60000:02d}:{((i.start_ms or 0) // 1000) % 60:02d}: “{i.text}”")
        else:
            label = "Your recollection" if i.provenance == "USER_RECOLLECTION" else "Your note"
            lines.append(f"{label}: {i.text.split('] ', 1)[-1]}")
    head = "Here's what I found in the conversation:" if recorded else "Here's what you noted:"
    note = "AI summary unavailable; showing matching moments as recorded." if recorded else "AI summary unavailable; showing your matching notes."
    return {"answer": head + "\n" + "\n".join(lines), "cited": top, "section_label": "From conversation" if recorded else "From your notes",
            "uncertainty": " ".join([note] + _uncertainty_notes(top))}


async def ask(user, *, session: dict | None, question: str, mode: str, scope: str, scope_id: uuid.UUID | None) -> dict:
    if mode not in MODES:
        raise ApiError(422, "INVALID_MODE", "Choose Remember, Think, Learn or Prepare.")
    question = question.strip()
    if not (1 <= len(question) <= 4000):
        raise ApiError(422, "INVALID_QUESTION", "Ask a question of up to 4000 characters.")
    reasoner = get_reasoner()
    async with db.user_tx(user.user_id) as conn:
        if session is not None:
            # INT-022/UNI-007: in a live session where AI help is prohibited, Ask is refused server-side.
            if S(session["state"]) in ACTIVE_STATES and session["state"] != S.NOTES_ONLY.value and not session["ai_assistance_permitted"]:
                raise policy_denied("LIVE_AI_NOT_PERMITTED", "Live AI help isn't permitted in this session. You can review it afterwards.")
        sc: Scope = await resolve_scope(conn, scope=scope, scope_id=scope_id, session=session)
        if mode != "REMEMBER" or reasoner.available():
            await ops.require_reasoner_quota(conn, user.tenant_id)
        ev = await search(conn, sc, question, include_recent=40 if (sc.kind == "CURRENT_SESSION" and session and
                                                                     session["state"] in ("RECORDING", "PAUSED", "STARTING")) else 0)
        searched = len({i.session_id for i in ev.items if i.session_id})

    result: dict
    if mode == "REMEMBER":
        if not ev.items:
            result = {"answer": NO_EVIDENCE, "provenance_label": "INSUFFICIENT_EVIDENCE", "citations": [],
                      "uncertainty": "No permitted source in this scope supports an answer.", "sections": []}
        elif not reasoner.available():
            ex = _extractive(ev)
            result = {"answer": ex["answer"], "provenance_label": _label_for(ex["cited"]),
                      "citations": [c.citation() for c in ex["cited"]], "uncertainty": ex["uncertainty"],
                      "sections": [{"label": ex["section_label"], "text": ex["answer"], "citations": [c.citation() for c in ex["cited"]]}]}
        else:
            try:
                res = await reasoner.structured(task="ask.remember", system_extra=MODE_GUIDANCE["REMEMBER"],
                                                data_blocks={"question": question, "untrusted_conversation_data": ev.model_view()},
                                                instruction="Answer the question per the rules. Return JSON.",
                                                schema=STATEMENTS_SCHEMA, effort="medium", max_tokens=4000)
            except ReasonerRefused:
                raise ApiError(422, "REQUEST_DECLINED", "MeetSaathi can't help with that request.")
            except ReasonerUnavailable:
                ex = _extractive(ev)
                res = None
                result = {"answer": ex["answer"], "provenance_label": _label_for(ex["cited"]),
                          "citations": [c.citation() for c in ex["cited"]], "uncertainty": ex["uncertainty"],
                          "sections": [{"label": ex["section_label"], "text": ex["answer"],
                                        "citations": [c.citation() for c in ex["cited"]]}]}
            if res is not None:
                kept, cited_all = [], []
                for st in res.data.get("statements", []):
                    items = ev.resolve(st.get("evidence_ids"))
                    if items and st.get("text", "").strip():
                        kept.append((st["text"].strip(), items))
                        cited_all.extend(i for i in items if i not in cited_all)
                if not kept or res.data.get("insufficient_evidence") and not kept:
                    result = {"answer": NO_EVIDENCE, "provenance_label": "INSUFFICIENT_EVIDENCE", "citations": [],
                              "uncertainty": res.data.get("uncertainty") or "The conversation doesn't establish this.", "sections": []}
                else:
                    answer = " ".join(t for t, _ in kept)
                    notes = _uncertainty_notes(cited_all)
                    result = {"answer": answer, "provenance_label": _label_for(cited_all),
                              "citations": [i.citation() for i in cited_all],
                              "uncertainty": " ".join([res.data.get("uncertainty", "")] + notes).strip(),
                              "sections": [{"label": "From conversation" if _label_for(items) == "FROM_CONVERSATION" else "From your notes",
                                            "text": t, "citations": [i.citation() for i in items]} for t, items in kept]}
                result["model_version"] = res.model
    else:
        if not reasoner.available():
            raise unavailable("AI_UNAVAILABLE", "Suggestions temporarily unavailable. Remember answers from your sources still work.")
        try:
            res = await reasoner.structured(task=f"ask.{mode.lower()}", system_extra=MODE_GUIDANCE[mode],
                                            data_blocks={"question": question, "untrusted_conversation_data": ev.model_view()},
                                            instruction="Respond per the mode rules. Return JSON.", schema=ANALYSIS_SCHEMA,
                                            effort="medium", max_tokens=6000)
        except ReasonerRefused:
            raise ApiError(422, "REQUEST_DECLINED", "MeetSaathi can't help with that request.")
        except ReasonerUnavailable:
            raise unavailable("AI_UNAVAILABLE", "Suggestions temporarily unavailable.")
        d = res.data
        ctx_sections, cited_all = [], []
        for st in d.get("context_statements", []):
            items = ev.resolve(st.get("evidence_ids"))
            if items and st.get("text", "").strip():  # uncited "context" is dropped, never shown as fact
                ctx_sections.append({"label": "From conversation", "text": st["text"].strip(), "citations": [i.citation() for i in items]})
                cited_all.extend(i for i in items if i not in cited_all)
        label = "GENERAL_KNOWLEDGE" if (mode == "LEARN" and d.get("knowledge_kind") == "GENERAL_KNOWLEDGE") else "AI_ANALYSIS"
        analysis_label = {"THINK": "MeetSaathi analysis", "LEARN": "Learning explanation" if label == "AI_ANALYSIS" else "Outside explanation",
                          "PREPARE": "MeetSaathi suggests"}[mode]
        sections = ctx_sections + [{"label": analysis_label, "text": d.get("analysis", ""), "citations": []}]
        if d.get("alternatives"):
            sections.append({"label": "Alternatives", "text": "\n".join(d["alternatives"]), "citations": []})
        if d.get("unknowns"):
            sections.append({"label": "Unknowns", "text": "\n".join(d["unknowns"]), "citations": []})
        result = {"answer": d.get("analysis", ""), "provenance_label": label, "citations": [i.citation() for i in cited_all],
                  "uncertainty": " ".join([d.get("uncertainty", "")] + _uncertainty_notes(cited_all)).strip(),
                  "sections": sections, "model_version": res.model,
                  "check_question": d.get("check_question") or None if mode == "LEARN" else None,
                  "proposed_actions": [a | {"requires_approval": True, "status": "PROPOSED"} for a in d.get("proposed_actions", [])]
                  if mode == "PREPARE" else []}

    result.update({"mode": mode, "scope": sc.describe(), "searched_sessions": searched})
    async with db.user_tx(user.user_id) as conn:
        from .evidence import evidence_current

        if not await evidence_current(conn, ev):
            raise ApiError(409, "EVIDENCE_CHANGED", "The source changed while preparing your answer. Ask again to use the latest permitted content.")
        ask_id = await conn.fetchval(
            "INSERT INTO ask_turns(tenant_id,user_id,space_id,session_id,mode,scope,scope_id,question,answer,provenance_label,citations,"
            " uncertainty,model_version) VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13) RETURNING ask_id",
            user.tenant_id, user.user_id, sc.space_id, session["session_id"] if session else None, mode, scope, scope_id, question,
            result["answer"], result["provenance_label"], result["citations"], result["uncertainty"] or "", result.get("model_version"))
        if result.get("model_version"):
            await ops.meter(conn, user.tenant_id, "reasoner_calls", 1)
        if session is not None:
            await append_event(conn, session, "ask.answered", {"ask_id": str(ask_id), "mode": mode,
                                                               "provenance_label": result["provenance_label"]})
    result["ask_id"] = ask_id
    return result


async def history_with_staleness(conn, user, session_id: uuid.UUID | None, limit: int = 30) -> list[dict]:
    """Older answers whose cited revisions were corrected are marked "Corrected since answer" (J11)."""
    if session_id:
        rows = await conn.fetch("SELECT * FROM ask_turns WHERE session_id=$1 ORDER BY created_at DESC LIMIT $2", session_id, limit)
    else:
        rows = await conn.fetch("SELECT * FROM ask_turns WHERE user_id=$1 ORDER BY created_at DESC LIMIT $2", user.user_id, limit)
    out = []
    for r in rows:
        d = dict(r)
        stale = False
        for c in d["citations"] or []:
            if "utterance_id" in c:
                # Finalization (provisional -> final) is not a correction; only user corrections or deletion make it stale.
                changed = await conn.fetchval(
                    "SELECT NOT EXISTS (SELECT 1 FROM utterances WHERE utterance_id=$1) OR EXISTS (SELECT 1 FROM utterance_revisions"
                    " WHERE utterance_id=$1 AND revision > $2 AND revision_reason IN ('SPEAKER_CORRECTION','TRANSCRIPT_CORRECTION'))",
                    uuid.UUID(c["utterance_id"]), int(c["revision"]))
                if changed:
                    stale = True
                    break
        d["corrected_since_answer"] = stale
        out.append(d)
    return out
