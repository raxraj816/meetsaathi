"""Speech evidence path (master 5.1): contiguous acknowledged audio -> ASR -> diarization -> alignment ->
versioned provisional utterances -> transcript.partial events. Finalization later promotes to final revisions.

Invariant: capture_off -> no ASR from live audio. Windows are built only from ACKED chunks of sessions whose
capture was authorized, and never cross a capture discontinuity (pause / interruption)."""
from __future__ import annotations

import asyncio
import logging
import uuid

from ..config import get_settings
from ..db import db
from ..domain import ops
from ..domain.events import append_event
from ..domain.capture_ranges import MAX_CAPTURE_MS
from ..domain.sessions import status_event
from ..storage import get_store
from .adapters import SpeechUnavailable, get_asr, get_diarizer
from .aligner import UNASSIGNED, align, speaker_alias
from .audio import pcm_to_wav, quality_label, rms_dbfs, speech_likely

log = logging.getLogger("meetsaathi.speech")

LIVE_SESSION_STATES = ("STARTING", "RECORDING", "PAUSED", "INTERRUPTED", "STOPPING", "FINALIZING")


def contiguous_run(chunks: list[dict]) -> list[dict]:
    if not chunks:
        return []
    run = [chunks[0]]
    for c in chunks[1:]:
        prev = run[-1]
        if c["sequence_no"] != prev["sequence_no"] + 1 or c["sample_rate_hz"] != prev["sample_rate_hz"]:
            break
        if abs(c["capture_start_ms"] - (prev["capture_start_ms"] + prev["duration_ms"])) > 1:
            break
        run.append(c)
    return run


async def run_asr_window(session_id: uuid.UUID, *, flush: bool = False, allow_gaps: bool = False) -> bool:
    """Returns True if more contiguous audio remains to be transcribed."""
    s = get_settings()
    asr = get_asr()
    if asr.supports_streaming and asr.available():
        return False  # the independently supervised live actor owns this audio
    async with db.system_tx() as conn:
        session = await conn.fetchrow("SELECT * FROM sessions WHERE session_id=$1 AND deleted_at IS NULL FOR UPDATE", session_id)
        if (session is None or session["audio_deleted_at"] is not None
                or session["state"] not in LIVE_SESSION_STATES or not session["capture_permitted"]):
            return False
        session = dict(session)
        rt = await conn.fetchrow("SELECT received_through_sequence, max_sequence, tts_windows FROM session_runtime WHERE session_id=$1", session_id)
        cursor = int(session["asr_cursor_sequence"])
        # Live windows only ever cover contiguous ACKed audio. After the drain deadline, finalization may
        # transcribe beyond a permanent upload gap (the gap itself stays visible as missing audio).
        through = int(rt["max_sequence"] if allow_gaps else rt["received_through_sequence"])
        if through <= cursor or (not flush and through - cursor < s.asr_window_chunks):
            return False
        if not asr.available():
            if session["transcript_status"] != "UNAVAILABLE":
                await conn.execute("UPDATE sessions SET transcript_status='UNAVAILABLE' WHERE session_id=$1", session_id)
                await status_event(conn, session, "CAPTIONS_UNAVAILABLE",
                                   "Live captions are unavailable. Recording continues and is saved.", "warning")
            return False
        chunks = [dict(r) for r in await conn.fetch(
            "SELECT sequence_no, encrypted_object_key, sample_rate_hz, capture_start_ms, duration_ms FROM audio_chunks"
            " WHERE session_id=$1 AND sequence_no>$2 AND sequence_no<=$3 AND ingest_status='ACKED'"
            " ORDER BY sequence_no LIMIT $4", session_id, cursor, through, s.asr_window_chunks * 2)]
        tts_windows = rt["tts_windows"] or []
    run = contiguous_run(chunks)
    if not run:
        return False
    store = get_store()
    pcm = b"".join([await asyncio.to_thread(store.get, session["tenant_id"], c["encrypted_object_key"]) for c in run])
    level = rms_dbfs(pcm)
    first, last = run[0], run[-1]
    segments = []
    diar = None
    if speech_likely(pcm):
        wav = pcm_to_wav(pcm, first["sample_rate_hz"])
        segments = await asr.transcribe(wav, offset_ms=first["capture_start_ms"], language=session["language"])
        end_ms = min(MAX_CAPTURE_MS, last["capture_start_ms"] + last["duration_ms"] + 1)
        if any(seg.start_ms < first["capture_start_ms"] or seg.end_ms <= seg.start_ms or seg.end_ms > end_ms for seg in segments):
            raise SpeechUnavailable("ASR result outside supplied audio")
        dia = get_diarizer()
        if segments and dia.available():
            try:
                diar = await dia.diarize(wav, session_key=str(session_id), offset_ms=first["capture_start_ms"])
            except SpeechUnavailable:
                diar = None
    aligned = align(segments, diar, tts_windows)

    async with db.system_tx() as conn:
        cur = await conn.fetchrow("SELECT * FROM sessions WHERE session_id=$1 AND deleted_at IS NULL FOR UPDATE", session_id)
        if (cur is None or int(cur["asr_cursor_sequence"]) != cursor or cur["audio_deleted_at"] is not None
                or not cur["capture_permitted"] or cur["state"] not in LIVE_SESSION_STATES):
            return False  # another worker advanced the window; never write duplicate segments
        cur = dict(cur)
        await persist_aligned(conn, cur, aligned, asr.version, diar, first, last, level, last["sequence_no"])
        await conn.execute("UPDATE sessions SET asr_cursor_sequence=$2, transcript_status=CASE WHEN transcript_status IN ('NONE','UNAVAILABLE','DELAYED')"
                           " THEN 'LIVE' ELSE transcript_status END WHERE session_id=$1", session_id, last["sequence_no"])
    return last["sequence_no"] < through


async def drain_asr(session_id: uuid.UUID, *, allow_gaps: bool = False, max_windows: int = 10000) -> None:
    if get_asr().supports_streaming and get_asr().available():
        from .streaming import pending
        from ..workers.runner import Reschedule

        if await pending(session_id, fail_on_exhaustion=True):
            raise Reschedule(5)
        return
    for _ in range(max_windows):
        more = await run_asr_window(session_id, flush=True, allow_gaps=allow_gaps)
        if not more:
            return


async def persist_aligned(conn, cur, aligned, asr_version, diar, first, last, level, evidence_key):
    """Write provider-final evidence inside the caller's fenced source transaction."""
    session_id = cur["session_id"]
    known = {r["provider_speaker_id"]: r["alias"] for r in await conn.fetch(
        "SELECT provider_speaker_id, alias FROM session_speakers WHERE session_id=$1 AND provider_speaker_id IS NOT NULL", session_id)}
    speaker_ids: dict[str, uuid.UUID] = {}
    for a in aligned:
        raw = a.speaker
        alias = speaker_alias(raw, known)
        if alias not in speaker_ids:
            sid = await conn.fetchval(
                "INSERT INTO session_speakers(tenant_id,space_id,session_id,alias,provider_speaker_id,confidence)"
                " VALUES ($1,$2,$3,$4,$5,$6) ON CONFLICT (session_id, alias) DO UPDATE SET alias=EXCLUDED.alias"
                " RETURNING speaker_alias_id",
                cur["tenant_id"], cur["space_id"], session_id, alias, None if raw == UNASSIGNED else raw, a.speaker_confidence)
            speaker_ids[alias] = sid
        spk = await conn.fetchrow("SELECT speaker_alias_id, user_verified_label, mapping_revision FROM session_speakers WHERE speaker_alias_id=$1",
                                  speaker_ids[alias])
        uid = await conn.fetchval("INSERT INTO utterances(tenant_id,space_id,session_id) VALUES ($1,$2,$3) RETURNING utterance_id",
                                  cur["tenant_id"], cur["space_id"], session_id)
        await conn.execute(
            "INSERT INTO utterance_revisions(utterance_id,revision,tenant_id,space_id,session_id,start_ms,end_ms,speaker_alias_id,"
            " transcript,is_final,provenance,asr_model_version,diarizer_model_version,speaker_confidence,speaker_label_snapshot,"
            " speaker_mapping_revision,overlap,asr_confidence,language,source_chunk_from,source_chunk_to,revision_reason)"
            " VALUES ($1,1,$2,$3,$4,$5,$6,$7,$8,false,'RECORDED',$9,$10,$11,$12,$13,$14,$15,$16,$17,$18,'LIVE_ASR')",
            uid, cur["tenant_id"], cur["space_id"], session_id, a.segment.start_ms, a.segment.end_ms, spk["speaker_alias_id"],
            a.segment.text, asr_version, diar.model_version if diar else None, a.speaker_confidence,
            spk["user_verified_label"] or alias, spk["mapping_revision"], a.overlap, a.segment.confidence,
            a.segment.language, first["sequence_no"], last["sequence_no"])
        await append_event(conn, cur, "transcript.partial", {
            "utterance_id": str(uid), "revision": 1, "speaker_alias": spk["user_verified_label"] or alias,
            "speaker_verified": spk["user_verified_label"] is not None, "start_ms": a.segment.start_ms,
            "end_ms": a.segment.end_ms, "text": a.segment.text, "speaker_confidence": a.speaker_confidence,
            "overlap": a.overlap, "is_final": False, "source_chunk_range": [first["sequence_no"], last["sequence_no"]],
            "low_confidence": (a.segment.confidence is not None and a.segment.confidence < 0.5)})
    if diar and diar.speaker_count_estimate and diar.speaker_count_estimate > diar.max_supported:
        await conn.execute("UPDATE session_runtime SET speakers_need_review=true WHERE session_id=$1", session_id)
        await status_event(conn, cur, "SPEAKERS_NEED_REVIEW", "Speakers need review. Speaker labels may be incomplete.", "warning")
    await persist_audio_quality(conn, cur, level)
    if aligned and cur["state"] in ("RECORDING", "STARTING"):
        await ops.enqueue(conn, tenant_id=cur["tenant_id"], space_id=cur["space_id"], session_id=session_id,
                          kind="insight.evaluate", payload={"session_id": str(session_id), "through": last["sequence_no"]},
                          key=f"insight:{session_id}:{evidence_key}", max_attempts=2)


async def persist_audio_quality(conn, cur, level):
    session_id = cur["session_id"]
    previous = await conn.fetchval("SELECT audio_quality FROM session_runtime WHERE session_id=$1", session_id)
    quality = quality_label(level)
    await conn.execute("UPDATE session_runtime SET audio_quality=$2 WHERE session_id=$1", session_id, quality)
    if quality != previous and quality != "GOOD" and cur["state"] == "RECORDING":
        await status_event(conn, cur, "AUDIO_POOR", "Microphone audio is unclear. Some context may be missing.", "warning",
                           level_dbfs=round(level, 1))
