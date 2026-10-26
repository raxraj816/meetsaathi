"""Post-session structured extraction (master 6.1-6.2). Produces PENDING_REVIEW claims linked to exact
utterance revisions, and a source-constrained recap. Nothing becomes durable memory without user review.

Typed statuses: a decision starts PROPOSED/DISCUSSED/UNRESOLVED; ACCEPTED/REJECTED/DEFERRED only with a
cited source for that transition. Owners and due dates are kept only if explicitly spoken (cited)."""
from __future__ import annotations

import uuid

from ..domain.policy import policy_for
from .evidence import EvidenceSet
from .reasoner import get_reasoner

EXTRACTION_SCHEMA = {
    "type": "object",
    "properties": {
        "items": {"type": "array", "items": {
            "type": "object",
            "properties": {
                "kind": {"type": "string", "enum": ["DECISION", "ACTION", "QUESTION", "RISK", "CONCEPT", "LESSON", "COMMITMENT", "IDEA"]},
                "text": {"type": "string"},
                "detail": {"type": "string"},
                "evidence_ids": {"type": "array", "items": {"type": "string"}},
                "decision_status": {"type": "string", "enum": ["PROPOSED", "DISCUSSED", "ACCEPTED", "REJECTED", "DEFERRED", "UNRESOLVED", "NONE"]},
                "status_evidence_ids": {"type": "array", "items": {"type": "string"}},
                "owner_spoken": {"type": "string"},
                "owner_evidence_ids": {"type": "array", "items": {"type": "string"}},
                "due_spoken": {"type": "string"},
            },
            "required": ["kind", "text", "detail", "evidence_ids", "decision_status", "status_evidence_ids", "owner_spoken",
                         "owner_evidence_ids", "due_spoken"],
            "additionalProperties": False}},
        "recap": {"type": "array", "items": {
            "type": "object",
            "properties": {"text": {"type": "string"}, "evidence_ids": {"type": "array", "items": {"type": "string"}}},
            "required": ["text", "evidence_ids"], "additionalProperties": False}},
        "topics": {"type": "array", "items": {
            "type": "object",
            "properties": {"title": {"type": "string"}, "evidence_ids": {"type": "array", "items": {"type": "string"}}},
            "required": ["title", "evidence_ids"], "additionalProperties": False}},
        "suggested_next_steps": {"type": "array", "items": {"type": "string"}},
        "visual_content_missing": {"type": "boolean"},
    },
    "required": ["items", "recap", "topics", "suggested_next_steps", "visual_content_missing"],
    "additionalProperties": False,
}

PACK_INSTRUCTIONS = {
    "MEETING": "Extract decisions (with status), actions/commitments (owner only if explicitly spoken), open questions and risks.",
    "LEARNING": "Extract the concepts taught (definitions, worked examples), questions raised, and lessons. Distinguish what the "
                "lecturer said from general knowledge. Set visual_content_missing=true if the speaker referenced a board, slide or "
                "diagram that audio cannot capture.",
    "INTERVIEW": "Extract the questions actually asked (only if captured) and lessons for the candidate. Do not score the candidate.",
    "CONVERSATION": "Extract only clear commitments, open questions and ideas worth keeping. Never infer emotions or motives. "
                    "Most conversations produce few items.",
}


async def extract(session: dict, ev: EvidenceSet) -> dict | None:
    reasoner = get_reasoner()
    if not session["ai_assistance_permitted"] or not reasoner.available() or not ev.items:
        return None
    pol = policy_for(session["context"])
    res = await reasoner.structured(
        task="extract", system_extra=f"Context pack: {session['context']}. {pol.live_guidance}",
        data_blocks={"session": {"title": session["title"], "context": session["context"], "preset": session["preset"]},
                     "untrusted_conversation_data": ev.model_view()},
        instruction=PACK_INSTRUCTIONS[session["context"]] + " recap: 2-4 short sentences, each citing evidence. "
                    "suggested_next_steps are labelled AI suggestions. Return JSON.",
        schema=EXTRACTION_SCHEMA, effort="medium", max_tokens=12000)
    return {"data": res.data, "model": res.model}


async def persist_extraction(conn, session: dict, ev: EvidenceSet, out: dict, policy_version: str) -> dict:
    data, model = out["data"], out["model"]
    pol = policy_for(session["context"])
    created: list[uuid.UUID] = []
    for item in data.get("items", []):
        kind = item["kind"]
        if kind not in pol.extraction_kinds and not (kind in ("ACTION", "COMMITMENT") and session["context"] == "MEETING"):
            continue
        sources = ev.resolve(item.get("evidence_ids"))
        sources = [s for s in sources if s.kind == "UTTERANCE"]
        if not sources or not item["text"].strip():
            continue  # never store an unsourced claim from a recording
        status = None
        if kind == "DECISION":
            requested = item.get("decision_status") or "PROPOSED"
            status_src = [s for s in ev.resolve(item.get("status_evidence_ids")) if s.kind == "UTTERANCE"]
            if requested in ("ACCEPTED", "REJECTED", "DEFERRED") and not status_src:
                requested = "UNRESOLVED"  # no explicit agreement in the source => keep UNRESOLVED (master 6.2)
            status = requested if requested != "NONE" else "PROPOSED"
        owner = None
        if kind in ("ACTION", "COMMITMENT") and item.get("owner_spoken", "").strip():
            if [s for s in ev.resolve(item.get("owner_evidence_ids")) if s.kind == "UTTERANCE"]:
                owner = item["owner_spoken"].strip()[:120]
        cid = await conn.fetchval(
            "INSERT INTO claims(tenant_id,space_id,session_id,project_id,claim_kind,text_value,long_text,provenance,decision_status,"
            " memory_state,model_version,policy_version,owner_label,owner_confirmed,due_text,time_start_ms,time_end_ms,metadata)"
            " VALUES ($1,$2,$3,$4,$5,$6,$7,'RECORDED',$8::decision_state,'PENDING_REVIEW',$9,$10,$11,false,$12,$13,$14,$15) RETURNING claim_id",
            session["tenant_id"], session["space_id"], session["session_id"], session["project_id"], kind, item["text"].strip()[:1000],
            item.get("detail") or None, status, model, policy_version, owner,
            (item.get("due_spoken") or "").strip()[:120] or None if owner else None,
            min(s.start_ms or 0 for s in sources), max(s.end_ms or 0 for s in sources), {"extracted": True})
        for s in sources:
            await conn.execute("INSERT INTO claim_sources(claim_id,tenant_id,space_id,utterance_id,utterance_revision) VALUES ($1,$2,$3,$4,$5)"
                               " ON CONFLICT DO NOTHING", cid, session["tenant_id"], session["space_id"], s.ref_id, s.revision)
        if status:
            first = (ev.resolve(item.get("status_evidence_ids")) or sources)[0]
            await conn.execute("INSERT INTO decision_events(claim_id,tenant_id,space_id,from_state,to_state,utterance_id,utterance_revision,actor)"
                               " VALUES ($1,$2,$3,NULL,$4::decision_state,$5,$6,'MODEL')",
                               cid, session["tenant_id"], session["space_id"], status, first.ref_id, first.revision)
        created.append(cid)
    recap = []
    for st in data.get("recap", []):
        items = [i for i in ev.resolve(st.get("evidence_ids")) if i.kind == "UTTERANCE"]
        if items and st["text"].strip():
            recap.append({"text": st["text"].strip(), "citations": [i.citation() for i in items]})
    topics = []
    for t in data.get("topics", []):
        items = ev.resolve(t.get("evidence_ids"))
        if items:
            topics.append({"title": t["title"], "start_ms": items[0].start_ms, "citations": [i.citation() for i in items[:3]]})
    return {"status": "READY", "summary": recap, "topics": topics, "claim_ids": [str(c) for c in created],
            "suggested_next_steps": [{"text": x, "label": "MeetSaathi suggests"} for x in data.get("suggested_next_steps", [])][:5],
            "visual_content_missing": bool(data.get("visual_content_missing")), "model_version": model}
