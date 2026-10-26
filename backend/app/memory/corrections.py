"""Corrections with provenance invalidation (master 6.4, J7, IMP-015).

A correction never overwrites evidence: it appends a new utterance revision, keeps the original (audited),
invalidates every claim citing a superseded revision, flags shares built on them, queues re-extraction /
reindex, and emits memory.invalidated so clients drop cached stale citations."""
from __future__ import annotations

import uuid

from ..domain import ops
from ..domain.events import append_event
from ..errors import ApiError, conflict, not_found


async def _invalidate_claims_citing(conn, session: dict, superseded: list[tuple[uuid.UUID, int]], reason: str) -> list[str]:
    if not superseded:
        return []
    uids = [u for u, _ in superseded]
    revs = [r for _, r in superseded]
    rows = await conn.fetch(
        "UPDATE claims SET memory_state='INVALIDATED', invalidated_at=now(), invalidation_reason=$2, updated_at=now()"
        " WHERE session_id=$1 AND memory_state IN ('PENDING_REVIEW','APPROVED') AND claim_id IN ("
        "   SELECT cs.claim_id FROM claim_sources cs JOIN unnest($3::uuid[], $4::int[]) AS x(u, r)"
        "   ON cs.utterance_id = x.u AND cs.utterance_revision = x.r)"
        " RETURNING claim_id", session["session_id"], reason, uids, revs)
    ids = [str(r["claim_id"]) for r in rows]
    if ids:
        await conn.execute("DELETE FROM embeddings WHERE owner_kind='CLAIM' AND owner_id = ANY($1::uuid[])", [uuid.UUID(i) for i in ids])
        await conn.execute("UPDATE shares SET stale=true WHERE session_id=$1 AND revoked_at IS NULL", session["session_id"])
        await conn.execute("UPDATE practice_items SET state='STALE' WHERE session_id=$1 AND state='ACTIVE'", session["session_id"])
    # Insights whose evidence was superseded are no longer current.
    await conn.execute(
        "UPDATE insights SET status='EXPIRED', suppress_reason='SOURCE_CORRECTED' WHERE session_id=$1 AND status='DELIVERED'"
        " AND EXISTS (SELECT 1 FROM jsonb_array_elements(evidence_refs) e JOIN unnest($2::uuid[]) x(u) ON (e->>'utterance_id')::uuid = x.u)",
        session["session_id"], uids)
    return ids


async def correct_speaker(conn, user, session: dict, alias: str, verified_label: str, expected_revision: int) -> dict:
    label = verified_label.strip()
    if not label or len(label) > 80:
        raise ApiError(422, "INVALID_LABEL", "Enter a name of up to 80 characters, or keep the speaker anonymous.")
    spk = await conn.fetchrow("SELECT * FROM session_speakers WHERE session_id=$1 AND alias=$2 FOR UPDATE", session["session_id"], alias)
    if spk is None:
        raise not_found("speaker")
    if spk["mapping_revision"] != expected_revision:
        raise conflict("REVISION_CONFLICT", "This speaker label changed. Review the latest version.",
                       {"current_revision": spk["mapping_revision"]})
    new_rev = spk["mapping_revision"] + 1
    clear = label.lower() in ("unknown", "anonymous")  # user may revert to anonymous
    await conn.execute("UPDATE session_speakers SET user_verified_label=$2, mapping_revision=$3 WHERE speaker_alias_id=$1",
                       spk["speaker_alias_id"], None if clear else label, new_rev)
    await conn.execute("INSERT INTO speaker_mapping_history(speaker_alias_id,mapping_revision,tenant_id,space_id,session_id,verified_label,changed_by)"
                       " VALUES ($1,$2,$3,$4,$5,$6,$7)", spk["speaker_alias_id"], new_rev, session["tenant_id"], session["space_id"],
                       session["session_id"], None if clear else label, user.user_id)
    # New attribution revisions for every utterance currently attributed to this alias.
    cur = await conn.fetch(
        "SELECT r.* FROM utterances u JOIN utterance_revisions r ON r.utterance_id=u.utterance_id AND r.revision=u.current_revision"
        " WHERE u.session_id=$1 AND r.speaker_alias_id=$2 FOR UPDATE OF u", session["session_id"], spk["speaker_alias_id"])
    superseded = []
    for r in cur:
        nr = r["revision"] + 1
        await conn.execute(
            "INSERT INTO utterance_revisions(utterance_id,revision,tenant_id,space_id,session_id,start_ms,end_ms,speaker_alias_id,transcript,"
            " is_final,provenance,asr_model_version,diarizer_model_version,speaker_confidence,speaker_label_snapshot,speaker_mapping_revision,"
            " overlap,asr_confidence,language,corrected_by_user,source_chunk_from,source_chunk_to,revision_reason)"
            " VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15,$16,$17,$18,$19,$20,$21,$22,'SPEAKER_CORRECTION')",
            r["utterance_id"], nr, r["tenant_id"], r["space_id"], r["session_id"], r["start_ms"], r["end_ms"], r["speaker_alias_id"],
            r["transcript"], r["is_final"], r["provenance"], r["asr_model_version"], r["diarizer_model_version"], r["speaker_confidence"],
            alias if clear else label, new_rev, r["overlap"], r["asr_confidence"], r["language"], r["corrected_by_user"],
            r["source_chunk_from"], r["source_chunk_to"])
        await conn.execute("UPDATE utterances SET current_revision=$2 WHERE utterance_id=$1", r["utterance_id"], nr)
        await conn.execute("DELETE FROM embeddings WHERE owner_kind='UTTERANCE' AND owner_id=$1", r["utterance_id"])
        superseded.append((r["utterance_id"], r["revision"]))
    invalidated = await _invalidate_claims_citing(conn, session, superseded, "SPEAKER_CORRECTED")
    # Claims whose owner was this alias label must be revalidated too.
    await conn.execute("UPDATE claims SET owner_confirmed=false WHERE session_id=$1 AND owner_label=$2", session["session_id"], alias)
    await _queue_reprocess(conn, session, "speaker", new_rev)
    payload = {"reason": "SPEAKER_CORRECTED", "alias": alias, "mapping_revision": new_rev, "claim_ids": invalidated,
               "superseded_revisions": [{"utterance_id": str(u), "revision": rv} for u, rv in superseded]}
    await append_event(conn, session, "memory.invalidated", payload)
    await append_event(conn, session, "speaker.corrected", {"alias": alias, "verified_label": None if clear else label,
                                                            "mapping_revision": new_rev, "user_supplied": True})
    await ops.audit(conn, tenant_id=session["tenant_id"], user_id=user.user_id, action="speaker.corrected",
                    target_kind="session", target_id=session["session_id"], detail={"alias": alias, "mapping_revision": new_rev})
    return {"alias": alias, "verified_label": None if clear else label, "mapping_revision": new_rev,
            "updated_utterances": len(superseded), "invalidated_claims": invalidated, "reindex": "QUEUED"}


async def correct_transcript(conn, user, session: dict, utterance_id: uuid.UUID, text: str, expected_revision: int) -> dict:
    text = text.strip()
    if not text or len(text) > 5000:
        raise ApiError(422, "INVALID_TEXT", "Corrected text must be 1-5000 characters.")
    u = await conn.fetchrow("SELECT * FROM utterances WHERE utterance_id=$1 AND session_id=$2 FOR UPDATE", utterance_id, session["session_id"])
    if u is None:
        raise not_found("transcript segment")
    if u["current_revision"] != expected_revision:
        raise conflict("REVISION_CONFLICT", "This segment changed. Review the latest version.", {"current_revision": u["current_revision"]})
    r = await conn.fetchrow("SELECT * FROM utterance_revisions WHERE utterance_id=$1 AND revision=$2", utterance_id, u["current_revision"])
    nr = r["revision"] + 1
    await conn.execute(
        "INSERT INTO utterance_revisions(utterance_id,revision,tenant_id,space_id,session_id,start_ms,end_ms,speaker_alias_id,transcript,"
        " is_final,provenance,asr_model_version,diarizer_model_version,speaker_confidence,speaker_label_snapshot,speaker_mapping_revision,"
        " overlap,asr_confidence,language,corrected_by_user,source_chunk_from,source_chunk_to,revision_reason)"
        " VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15,$16,$17,NULL,$18,true,$19,$20,'TRANSCRIPT_CORRECTION')",
        utterance_id, nr, r["tenant_id"], r["space_id"], r["session_id"], r["start_ms"], r["end_ms"], r["speaker_alias_id"], text,
        r["is_final"], r["provenance"], r["asr_model_version"], r["diarizer_model_version"], r["speaker_confidence"],
        r["speaker_label_snapshot"], r["speaker_mapping_revision"], r["overlap"], r["language"], r["source_chunk_from"], r["source_chunk_to"])
    await conn.execute("UPDATE utterances SET current_revision=$2 WHERE utterance_id=$1", utterance_id, nr)
    await conn.execute("DELETE FROM embeddings WHERE owner_kind='UTTERANCE' AND owner_id=$1", utterance_id)
    invalidated = await _invalidate_claims_citing(conn, session, [(utterance_id, r["revision"])], "TRANSCRIPT_CORRECTED")
    await _queue_reprocess(conn, session, f"transcript:{utterance_id}", nr)
    await append_event(conn, session, "memory.invalidated", {"reason": "TRANSCRIPT_CORRECTED", "claim_ids": invalidated,
                                                            "superseded_revisions": [{"utterance_id": str(utterance_id), "revision": r["revision"]}]})
    await append_event(conn, session, "transcript.final", {"utterance_id": str(utterance_id), "revision": nr, "start_ms": r["start_ms"],
                                                          "end_ms": r["end_ms"], "text": text, "is_final": r["is_final"],
                                                          "speaker_alias": r["speaker_label_snapshot"], "corrected_by_user": True,
                                                          "speaker_confidence": r["speaker_confidence"], "source_chunk_range":
                                                          [r["source_chunk_from"], r["source_chunk_to"]]})
    await ops.audit(conn, tenant_id=session["tenant_id"], user_id=user.user_id, action="transcript.corrected",
                    target_kind="utterance", target_id=utterance_id, detail={"revision": nr})
    return {"utterance_id": utterance_id, "revision": nr, "invalidated_claims": invalidated, "reindex": "QUEUED"}


async def _queue_reprocess(conn, session: dict, what: str, rev: int) -> None:
    if session["state"] in ("COMPLETED", "COMPLETED_PARTIAL"):
        await ops.enqueue(conn, tenant_id=session["tenant_id"], space_id=session["space_id"], session_id=session["session_id"],
                          kind="memory.reextract", payload={"session_id": str(session["session_id"])},
                          key=f"reextract:{session['session_id']}:{what}:{rev}", delay_s=2)
    await ops.enqueue(conn, tenant_id=session["tenant_id"], space_id=session["space_id"], session_id=session["session_id"],
                      kind="memory.reindex", payload={"session_id": str(session["session_id"])},
                      key=f"reindex:{session['session_id']}:{what}:{rev}", delay_s=1)
