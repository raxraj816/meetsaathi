"""Job handlers: live ASR windows, insight evaluation, finalization, re-extraction after corrections,
reindexing, deletion purge, exports and maintenance sweeps."""
from __future__ import annotations

import datetime as dt
import logging
import uuid

from ..config import get_settings
from ..db import db, vector_literal
from ..domain.events import append_event
from ..domain.capture_ranges import HOLES_SQL
from ..domain.sessions import status_event, transition
from ..domain.state_machine import S
from ..intelligence import insights
from ..intelligence.evidence import UTTERANCE_SQL, EvidenceSet, add_utterance_rows
from ..intelligence.extraction import extract, persist_extraction
from ..intelligence.reasoner import ReasonerRefused, ReasonerUnavailable
from ..memory.deletion import mark_action_required, retention_sweep, run_purge
from ..memory.embeddings import get_embedder
from ..memory.service import anchor_bookmark
from ..memory.sharing import build_export
from ..speech.adapters import SpeechUnavailable, get_asr
from ..speech.pipeline import drain_asr, run_asr_window
from .runner import Reschedule

log = logging.getLogger("meetsaathi.jobs")


async def h_asr_window(p, job):
    try:
        more = await run_asr_window(uuid.UUID(p["session_id"]))
    except SpeechUnavailable:
        if job["attempts"] >= 2:
            async with db.system_tx() as conn:
                s = await conn.fetchrow("SELECT * FROM sessions WHERE session_id=$1", uuid.UUID(p["session_id"]))
                if s and s["transcript_status"] != "DELAYED":
                    await conn.execute("UPDATE sessions SET transcript_status='DELAYED' WHERE session_id=$1", s["session_id"])
                    await status_event(conn, dict(s), "CAPTIONS_DELAYED", "Captions delayed. Recording continues.", "warning")
        raise
    if more:
        await run_asr_window(uuid.UUID(p["session_id"]))


async def h_asr_flush(p, job):
    await drain_asr(uuid.UUID(p["session_id"]))


async def h_insight(p, job):
    await insights.evaluate(uuid.UUID(p["session_id"]), triggered_at=p.get("triggered_at") or job["created_at"].isoformat(),
                            deferrals=int(p.get("deferrals", 0)))


async def _missing_gaps(conn, session: dict, upto: int) -> None:
    # Old gap rows had no sequence interval and guessed one second for an unknown tail.
    # Replace those derived rows with the current compact, source-aligned description.
    await conn.execute("DELETE FROM capture_gaps WHERE session_id=$1 AND reason='UPLOAD_MISSING'"
                       " AND missing_sequence_from IS NULL", session["session_id"])
    await conn.execute(
        "INSERT INTO capture_gaps(tenant_id,space_id,session_id,start_ms,end_ms,reason,"
        " missing_sequence_from,missing_sequence_to,time_bounds_estimated)"
        " SELECT $4,$5,$1,start_ms,CASE WHEN next_start_ms IS NOT NULL THEN GREATEST(start_ms,next_start_ms)"
        " WHEN $6::bigint>start_ms THEN $6::bigint ELSE NULL END,'UPLOAD_MISSING',sequence_from,sequence_to,true"
        " FROM (" + HOLES_SQL + ") holes WHERE true"
        " ON CONFLICT (session_id,missing_sequence_from,missing_sequence_to)"
        " WHERE reason='UPLOAD_MISSING' AND missing_sequence_from IS NOT NULL DO UPDATE"
        " SET start_ms=EXCLUDED.start_ms,end_ms=EXCLUDED.end_ms,time_bounds_estimated=true",
        session["session_id"], -1, upto, session["tenant_id"], session["space_id"], session.get("capture_end_ms"))


async def h_finalize(p, job):
    s = get_settings()
    sid = uuid.UUID(p["session_id"])
    async with db.system_tx() as conn:
        session = await conn.fetchrow("SELECT * FROM sessions WHERE session_id=$1 AND deleted_at IS NULL FOR UPDATE", sid)
        if session is None or session["state"] != S.FINALIZING.value:
            return
        session = dict(session)
        rt = await conn.fetchrow("SELECT received_through_sequence, max_sequence FROM session_runtime WHERE session_id=$1", sid)
        now = dt.datetime.now(dt.timezone.utc)
        fs = session["final_sequence"] if session["final_sequence"] is not None else -1
        drained = rt["received_through_sequence"] >= fs
        if not drained and session["drain_deadline"] and session["drain_deadline"] > now:
            if session["finalization_status"] != "WAITING_FOR_UPLOAD":
                await conn.execute("UPDATE sessions SET finalization_status='WAITING_FOR_UPLOAD' WHERE session_id=$1", sid)
            raise Reschedule(15)
        if not drained:
            await _missing_gaps(conn, session, fs)
        await conn.execute("UPDATE sessions SET finalization_status='TRANSCRIBING' WHERE session_id=$1", sid)
        await append_event(conn, session, "session.finalization_progress", {"status": "TRANSCRIBING", "retryable": True, "terminal": False,
                                                                           "message": "Recording stopped. Final notes are being prepared."})
    # 1. Transcribe any remaining audio (contiguous first, then past permanent gaps).
    if get_asr().available() and session["capture_permitted"]:
        await drain_asr(sid)
        await drain_asr(sid, allow_gaps=True)
    async with db.system_tx() as conn:
        session = dict(await conn.fetchrow("SELECT * FROM sessions WHERE session_id=$1 FOR UPDATE", sid))
        # 2. Promote provisional revisions to final (append-only; originals preserved).
        prov = await conn.fetch("SELECT r.* FROM utterances u JOIN utterance_revisions r ON r.utterance_id=u.utterance_id AND r.revision=u.current_revision"
                                " WHERE u.session_id=$1 AND NOT r.is_final", sid)
        for r in prov:
            nr = r["revision"] + 1
            await conn.execute(
                "INSERT INTO utterance_revisions(utterance_id,revision,tenant_id,space_id,session_id,start_ms,end_ms,speaker_alias_id,transcript,is_final,"
                " provenance,asr_model_version,diarizer_model_version,speaker_confidence,speaker_label_snapshot,speaker_mapping_revision,overlap,"
                " asr_confidence,language,corrected_by_user,source_chunk_from,source_chunk_to,revision_reason)"
                " VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,true,$10,$11,$12,$13,$14,$15,$16,$17,$18,$19,$20,$21,'FINALIZED')",
                r["utterance_id"], nr, r["tenant_id"], r["space_id"], r["session_id"], r["start_ms"], r["end_ms"], r["speaker_alias_id"],
                r["transcript"], r["provenance"], r["asr_model_version"], r["diarizer_model_version"], r["speaker_confidence"],
                r["speaker_label_snapshot"], r["speaker_mapping_revision"], r["overlap"], r["asr_confidence"], r["language"],
                r["corrected_by_user"], r["source_chunk_from"], r["source_chunk_to"])
            await conn.execute("UPDATE utterances SET current_revision=$2 WHERE utterance_id=$1", r["utterance_id"], nr)
            await append_event(conn, session, "transcript.final", {
                "utterance_id": str(r["utterance_id"]), "revision": nr, "start_ms": r["start_ms"], "end_ms": r["end_ms"], "text": r["transcript"],
                "is_final": True, "speaker_alias": r["speaker_label_snapshot"], "speaker_confidence": r["speaker_confidence"],
                "source_chunk_range": [r["source_chunk_from"], r["source_chunk_to"]]})
        # Bookmarks saved live are anchored to the final revisions overlapping their (uncertain) range.
        bms = await conn.fetch("SELECT claim_id, time_start_ms, time_end_ms FROM claims WHERE session_id=$1 AND claim_kind='BOOKMARK'"
                               " AND time_start_ms IS NOT NULL", sid)
        for b in bms:
            await conn.execute("DELETE FROM claim_sources WHERE claim_id=$1", b["claim_id"])
            await anchor_bookmark(conn, session, b["claim_id"], b["time_start_ms"], b["time_end_ms"])
        has_utt = await conn.fetchval("SELECT count(*) FROM utterances WHERE session_id=$1", sid)
        transcript_status = ("FINAL" if has_utt else ("UNAVAILABLE" if session["capture_source"] != "NONE" else "NONE"))
        await conn.execute("UPDATE sessions SET transcript_status=$2, finalization_status='EXTRACTING' WHERE session_id=$1", sid, transcript_status)
        ev = EvidenceSet()
        add_utterance_rows(ev, await conn.fetch(UTTERANCE_SQL + " WHERE u.session_id=$1 ORDER BY r.start_ms LIMIT 1500", sid))
    # 3. Structured extraction + recap (AI optional; capture/transcript never depend on it).
    recap = {"status": "AI_UNAVAILABLE", "message": "AI recap is unavailable. Your transcript and notes are saved."}
    if not session["ai_assistance_permitted"]:
        recap = {"status": "AI_DISABLED", "message": "AI analysis was not enabled for this session. Your transcript and notes are saved."}
    try:
        out = await extract(session, ev)
    except ReasonerRefused:
        out, recap = None, {"status": "DECLINED", "message": "An AI recap isn't available for this session."}
    except ReasonerUnavailable:
        if job["attempts"] < 3:
            raise
        out = None
    if not ev.items and session["capture_source"] != "NONE":
        recap = {"status": "NO_TRANSCRIPT", "message": "No transcript was produced, so there is no AI recap. Audio and notes are saved."}
    elif session["capture_source"] == "NONE":
        recap = {"status": "NOTES_ONLY", "message": "Notes-only session: your notes are below. Nothing was recorded."}
    async with db.system_tx() as conn:
        session = dict(await conn.fetchrow("SELECT * FROM sessions WHERE session_id=$1 FOR UPDATE", sid))
        if session["state"] != S.FINALIZING.value:
            return
        if out is not None:
            from ..intelligence.evidence import evidence_current

            if not await evidence_current(conn, ev):
                raise Reschedule(1)  # recapture corrected evidence instead of storing stale claims
            await conn.execute("DELETE FROM claims WHERE session_id=$1 AND (metadata->>'extracted')='true' AND memory_state='PENDING_REVIEW'", sid)
            recap = await persist_extraction(conn, session, ev, out, s.policy_version)
            from ..domain import ops as _ops
            await _ops.meter(conn, session["tenant_id"], "reasoner_calls", 1)
        gaps = await conn.fetch("SELECT reason FROM capture_gaps WHERE session_id=$1 AND reason <> 'PAUSED_BY_USER'", sid)
        partial = bool(gaps)
        retention_days = 1 if session["retention_policy_id"] == "EPHEMERAL" else s.raw_audio_retention_days
        new = await transition(conn, session, S.COMPLETED_PARTIAL if partial else S.COMPLETED, reason="FINALIZED", actor="SYSTEM",
                               updates={"recap": recap, "finalization_status": "COMPLETE",
                                        "audio_retention_until": dt.datetime.now(dt.timezone.utc) + dt.timedelta(days=retention_days)})
        await append_event(conn, new, "session.finalization_progress", {
            "status": "COMPLETE", "retryable": False, "terminal": True, "partial": partial,
            "message": "Final notes ready. Some audio was unavailable; gaps are shown." if partial else "Final notes ready."})
        from ..domain import ops as _ops
        await _ops.enqueue(conn, tenant_id=new["tenant_id"], space_id=new["space_id"], session_id=sid, kind="memory.reindex",
                           payload={"session_id": str(sid)}, key=f"reindex:{sid}:final")


async def h_reextract(p, job):
    s = get_settings()
    sid = uuid.UUID(p["session_id"])
    async with db.system_tx() as conn:
        session = await conn.fetchrow("SELECT * FROM sessions WHERE session_id=$1 AND deleted_at IS NULL", sid)
        if session is None or session["state"] not in ("COMPLETED", "COMPLETED_PARTIAL"):
            return
        session = dict(session)
        ev = EvidenceSet()
        add_utterance_rows(ev, await conn.fetch(UTTERANCE_SQL + " WHERE u.session_id=$1 ORDER BY r.start_ms LIMIT 1500", sid))
    try:
        out = await extract(session, ev)
    except (ReasonerUnavailable, ReasonerRefused):
        out = None
    if out is None:
        return  # invalidated claims stay flagged; nothing stale is shown as current
    async with db.system_tx() as conn:
        current = await conn.fetchrow("SELECT * FROM sessions WHERE session_id=$1 AND deleted_at IS NULL FOR UPDATE", sid)
        if current is None or current["state"] not in ("COMPLETED", "COMPLETED_PARTIAL") or not current["ai_assistance_permitted"]:
            return
        from ..intelligence.evidence import evidence_current

        if not await evidence_current(conn, ev):
            return
        session = dict(current)
        await conn.execute("DELETE FROM claims WHERE session_id=$1 AND (metadata->>'extracted')='true' AND memory_state='PENDING_REVIEW'", sid)
        recap = await persist_extraction(conn, session, ev, out, s.policy_version)
        await conn.execute("UPDATE sessions SET recap=$2 WHERE session_id=$1", sid, recap | {"regenerated_after_correction": True})
        await status_event(conn, session, "RECAP_REFRESHED", "Recap refreshed after your correction. Review the new items.")


async def _embed_rows(conn, rows, kind: str) -> None:
    emb = get_embedder()
    if not emb.available() or not rows:
        return
    vecs = await emb.embed([r["text"] for r in rows])
    for r, v in zip(rows, vecs):
        if r["session_id"] is not None:
            live = await conn.fetchval("SELECT session_id FROM sessions WHERE session_id=$1 AND deleted_at IS NULL FOR UPDATE", r["session_id"])
            if live is None:
                continue
        if kind == "UTTERANCE":
            current = await conn.fetchval("SELECT current_revision FROM utterances WHERE utterance_id=$1 FOR UPDATE", r["id"])
        else:
            current = await conn.fetchval("SELECT version::int FROM claims WHERE claim_id=$1 AND memory_state='APPROVED' FOR UPDATE", r["id"])
        if current != r["rev"]:
            continue
        await conn.execute(
            "INSERT INTO embeddings(owner_kind,owner_id,owner_revision,tenant_id,space_id,session_id,embedding_model,embedding)"
            " VALUES ($1,$2,$3,$4,$5,$6,$7,$8::vector) ON CONFLICT (owner_kind,owner_id) DO UPDATE SET owner_revision=EXCLUDED.owner_revision,"
            " embedding=EXCLUDED.embedding, embedding_model=EXCLUDED.embedding_model, updated_at=now()",
            kind, r["id"], r["rev"], r["tenant_id"], r["space_id"], r["session_id"], emb.model, vector_literal(v))


async def h_reindex(p, job):
    sid = uuid.UUID(p["session_id"])
    async with db.system_tx() as conn:
        rows = await conn.fetch("SELECT u.utterance_id AS id, u.current_revision AS rev, u.tenant_id, u.space_id, u.session_id, r.transcript AS text"
                                " FROM utterances u JOIN utterance_revisions r ON r.utterance_id=u.utterance_id AND r.revision=u.current_revision"
                                " JOIN sessions s ON s.session_id=u.session_id AND s.deleted_at IS NULL"
                                " WHERE u.session_id=$1 AND NOT EXISTS (SELECT 1 FROM embeddings e WHERE e.owner_kind='UTTERANCE'"
                                " AND e.owner_id=u.utterance_id AND e.owner_revision=u.current_revision) LIMIT 500", sid)
        await _embed_rows(conn, rows, "UTTERANCE")


async def h_reindex_claims(p, job):
    ids = [uuid.UUID(x) for x in p["claim_ids"]]
    async with db.system_tx() as conn:
        rows = await conn.fetch("SELECT claim_id AS id, version::int AS rev, tenant_id, space_id, session_id, text_value AS text FROM claims"
                                " WHERE claim_id = ANY($1::uuid[]) AND memory_state='APPROVED'", ids)
        await _embed_rows(conn, rows, "CLAIM")


async def h_purge(p, job):
    await run_purge(uuid.UUID(p["request_id"]))


async def h_export(p, job):
    await build_export(uuid.UUID(p["export_id"]))


async def h_sweep(p, job):
    await retention_sweep()
    async with db.system_tx() as conn:
        # STARTING without audio for too long => truthful ERROR rather than a phantom "Live" (master 7.1 timeout).
        stale = await conn.fetch("SELECT * FROM sessions WHERE state='STARTING' AND deleted_at IS NULL AND version > 0"
                                 " AND session_id IN (SELECT session_id FROM session_state_log WHERE current='STARTING'"
                                 " GROUP BY session_id HAVING max(created_at) < now() - interval '90 seconds')")
        for st in stale:
            await transition(conn, dict(st), S.ERROR, reason="START_TIMEOUT", actor="SYSTEM")
        await conn.execute("UPDATE insights SET status='EXPIRED' WHERE status='DELIVERED' AND expires_at < now()")
        await conn.execute("UPDATE exports SET status='EXPIRED' WHERE status='COMPLETE' AND expires_at < now()")
        await conn.execute("DELETE FROM idempotency_keys WHERE created_at < now() - interval '7 days'")


HANDLERS = {
    "asr.window": h_asr_window, "asr.flush": h_asr_flush, "insight.evaluate": h_insight, "session.finalize": h_finalize,
    "memory.reextract": h_reextract, "memory.reindex": h_reindex, "memory.reindex_claims": h_reindex_claims,
    "deletion.purge": h_purge, "export.build": h_export, "maintenance.sweep": h_sweep,
}


async def on_dead(job: dict, msg: str) -> None:
    kind, p = job["kind"], job["payload"]
    if kind == "session.finalize":
        async with db.system_tx() as conn:
            s = await conn.fetchrow("SELECT * FROM sessions WHERE session_id=$1 FOR UPDATE", uuid.UUID(p["session_id"]))
            if s and s["state"] == S.FINALIZING.value:
                new = await transition(conn, dict(s), S.FINALIZATION_RETRYABLE, reason="FINALIZATION_FAILED", actor="SYSTEM",
                                       updates={"finalization_status": "FAILED", "finalization_error": "processing_failed"})
                saved = await conn.fetchval("SELECT count(*) FROM audio_chunks WHERE session_id=$1 AND ingest_status='ACKED'", new["session_id"])
                await append_event(conn, new, "session.finalization_progress", {
                    "status": "FAILED", "retryable": True, "terminal": False,
                    "message": "Recording saved; recap is being retried." if saved else "Notes are saved; the recap couldn't be prepared. Try again."})
    elif kind == "deletion.purge":
        await mark_action_required(uuid.UUID(p["request_id"]), msg)
    elif kind == "export.build":
        async with db.system_tx() as conn:
            await conn.execute("UPDATE exports SET status='FAILED', error='export_failed' WHERE export_id=$1", uuid.UUID(p["export_id"]))
