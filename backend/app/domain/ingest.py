"""Audio ingress (master 7.2, IMP-006): exactly-once authoritative ingest per (session, sequence),
checksum verification, encrypted storage, contiguous ACK watermark + gap list, drain after stop."""
from __future__ import annotations

import asyncio
import datetime as dt
import uuid

from ..config import get_settings
from ..db import db
from ..errors import ApiError, conflict
from ..security.crypto import constant_time_equals, sha256_hex
from ..security.tokens import decode_ingest_token
from ..storage import chunk_key, get_store
from ..speech.adapters import get_asr
from . import ops
from .events import append_event
from .sessions import confirm_recording, load_session
from .state_machine import S
from .capture_ranges import MAX_CAPTURE_MS, MAX_SEQUENCE, contiguous_through, gap_summary

ACCEPTING_LIVE = {S.STARTING.value, S.RECORDING.value}


async def ingest_chunk(*, token: str, session_id: uuid.UUID, sequence: int, body: bytes, sample_rate: int,
                       capture_start_ms: int, duration_ms: int, sha256: str, device_id: str | None,
                       encoding: str) -> dict:
    s = get_settings()
    claims = decode_ingest_token(token)
    if claims["ses"] != str(session_id):
        raise ApiError(403, "INGEST_SCOPE_MISMATCH", "This upload credential is for a different session.")
    if device_id and device_id != claims["did"]:
        raise ApiError(403, "INGEST_SCOPE_MISMATCH", "This upload credential belongs to another device.")
    if encoding != "pcm_s16le":
        raise ApiError(415, "UNSUPPORTED_ENCODING", "Audio must be 16-bit PCM.")
    if (not (8000 <= sample_rate <= 48000) or not 0 < duration_ms <= 10000
            or not 0 <= capture_start_ms <= MAX_CAPTURE_MS-duration_ms or not 0 <= sequence <= MAX_SEQUENCE):
        raise ApiError(422, "INVALID_CHUNK_METADATA", "Audio chunk metadata is invalid.")
    if len(body) == 0 or len(body) > s.max_chunk_bytes:
        raise ApiError(413, "CHUNK_TOO_LARGE", "Audio chunk is too large.")
    # PCM frames and their shared capture clock must agree to within one rounded millisecond.
    # A 5% tolerance silently drifted long streams and made exact crash replay impossible.
    if len(body) % 2 or abs(len(body) * 1000 - sample_rate * 2 * duration_ms) > sample_rate * 2:
        raise ApiError(422, "CHUNK_LENGTH_MISMATCH", "Audio chunk length doesn't match its duration.")
    actual = sha256_hex(body)
    checksum_ok = constant_time_equals(actual, sha256.lower())

    user_id = uuid.UUID(claims["sub"])
    async with db.system_tx() as sconn:
        tok = await sconn.fetchrow(
            "SELECT t.revoked_at, t.expires_at, t.drain_only, d.revoked_at AS device_revoked FROM ingest_tokens t"
            " JOIN devices d ON d.device_id=t.device_id WHERE t.jti=$1 AND t.session_id=$2", uuid.UUID(claims["jti"]), session_id)
    now = dt.datetime.now(dt.timezone.utc)
    if tok is None or tok["device_revoked"] is not None:
        raise ApiError(401, "INGEST_REVOKED", "This device can no longer upload audio.")
    if tok["revoked_at"] is not None or tok["expires_at"] < now:
        raise ApiError(401, "INGEST_TOKEN_EXPIRED", "Upload credential expired. Requesting a new one.", retryable=True)

    async with db.user_tx(user_id) as conn:
        session = await load_session(conn, session_id, for_update=True)
        state = session["state"]
        if not session["capture_permitted"]:
            raise ApiError(403, "CAPTURE_NOT_AUTHORIZED", "Capture isn't authorized for this session.")
        # Ordering rules: live states accept anything; paused/interrupted/ended accept only frames captured before.
        if state in ACCEPTING_LIVE and not tok["drain_only"]:
            pass
        elif state in (S.PAUSED.value, S.INTERRUPTED.value):
            wm = session["pause_watermark_sequence"]
            if wm is None or sequence > wm:
                raise conflict("CAPTURE_PAUSED", "Capture is paused; no new audio is accepted.")
        elif state in (S.STOPPING.value, S.FINALIZING.value):
            fs = session["final_sequence"]
            if fs is None or sequence > fs or (session["drain_deadline"] and session["drain_deadline"] < now):
                raise conflict("SESSION_ENDED", "This session has ended; no new audio is accepted.")
        else:
            raise conflict("SESSION_NOT_CAPTURING", "This session isn't capturing audio.", {"state": state})

        existing = await conn.fetchrow("SELECT * FROM audio_chunks WHERE session_id=$1 AND sequence_no=$2",
                                       session_id, sequence)
        rt = await conn.fetchrow("SELECT received_through_sequence, max_sequence FROM session_runtime WHERE session_id=$1 FOR UPDATE",
                                 session_id)
        through, max_seq = int(rt["received_through_sequence"]), int(rt["max_sequence"])
        duplicate = False
        if not checksum_ok:
            gaps, truncated = await gap_summary(conn, session_id, through, max_seq)
            ack = {"received_through_sequence": through, "gap_sequences": gaps, "checksum_confirmed": False,
                   "gap_sequences_truncated": truncated, "sequence": sequence, "status": "CHECKSUM_MISMATCH"}
            await append_event(conn, session, "audio.chunk_ack", ack)
            return ack | {"_status": 422}
        if existing is not None:
            if (existing["sha256_hex"] != actual or existing["sample_rate_hz"] != sample_rate
                    or existing["capture_start_ms"] != capture_start_ms or existing["duration_ms"] != duration_ms):
                raise conflict("CHUNK_CONFLICT", "A different audio chunk was already stored for this sequence.")
            duplicate = True  # idempotent replay: same bytes, same ACK, no second transcript segment
        else:
            prev = await conn.fetchrow("SELECT capture_start_ms+duration_ms AS end_ms FROM audio_chunks"
                                      " WHERE session_id=$1 AND sequence_no<$2 ORDER BY sequence_no DESC LIMIT 1", session_id, sequence)
            nxt = await conn.fetchrow("SELECT capture_start_ms FROM audio_chunks WHERE session_id=$1"
                                     " AND sequence_no>$2 ORDER BY sequence_no LIMIT 1", session_id, sequence)
            if ((prev and capture_start_ms < prev["end_ms"] - 1)
                    or (nxt and capture_start_ms + duration_ms > nxt["capture_start_ms"] + 1)):
                raise ApiError(422, "CHUNK_CLOCK_CONFLICT", "Audio chunks must follow the capture clock without overlap.")
            key = chunk_key(session["tenant_id"], session_id, sequence)
            await asyncio.to_thread(get_store().put, session["tenant_id"], key, body)
            await conn.execute(
                "INSERT INTO audio_chunks(tenant_id,space_id,session_id,sequence_no,sample_rate_hz,capture_start_ms,duration_ms,"
                " sha256_hex,encrypted_object_key,ingest_status,device_id,byte_length) VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,'ACKED',$10,$11)",
                session["tenant_id"], session["space_id"], session_id, sequence, sample_rate, capture_start_ms, duration_ms,
                actual, key, uuid.UUID(claims["did"]), len(body))
            await ops.meter(conn, session["tenant_id"], "capture_seconds", duration_ms / 1000.0)
            max_seq = max(max_seq, sequence)
            if sequence == through + 1:
                through = await contiguous_through(conn, session_id, sequence, max_seq)
            await conn.execute("UPDATE session_runtime SET received_through_sequence=$2, max_sequence=$3 WHERE session_id=$1",
                               session_id, through, max_seq)
            end_ms = capture_start_ms + duration_ms
            if end_ms > session["source_watermark_ms"]:
                await conn.execute("UPDATE sessions SET source_watermark_ms=$2 WHERE session_id=$1", session_id, end_ms)
                session["source_watermark_ms"] = end_ms
            if state == S.STARTING.value:
                session = await confirm_recording(conn, session, reason="AUDIO_RECEIVED", actor="SYSTEM")
            # The persistent provider is independently supervised from the first ACK. Finite providers
            # keep their durable windows; unavailable providers retain the truthful status job.
            streaming = get_asr().supports_streaming and get_asr().available()
            if not streaming and through - int(session["asr_cursor_sequence"]) >= s.asr_window_chunks:
                await ops.enqueue(conn, tenant_id=session["tenant_id"], space_id=session["space_id"], session_id=session_id,
                                  kind="asr.window", payload={"session_id": str(session_id)}, key=f"asr.window:{session_id}:{through}")
        gaps, truncated = await gap_summary(conn, session_id, through, max_seq)
        ack = {"received_through_sequence": through, "gap_sequences": gaps, "checksum_confirmed": True,
               "gap_sequences_truncated": truncated, "sequence": sequence, "status": "DUPLICATE" if duplicate else "ACKED"}
        if not duplicate:
            await append_event(conn, session, "audio.chunk_ack", ack)
        if state in (S.STOPPING.value, S.FINALIZING.value) and session["final_sequence"] is not None and through >= session["final_sequence"]:
            await ops.enqueue(conn, tenant_id=session["tenant_id"], space_id=session["space_id"], session_id=session_id,
                              kind="session.finalize", payload={"session_id": str(session_id)},
                              key=f"finalize:{session_id}:drained:{through}")
    return ack | {"_status": 200}
