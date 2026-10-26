"""Session REST surface (master 10.1 + contracts/openapi_v1.yaml). Mutations require Idempotency-Key."""
from __future__ import annotations

import asyncio
import uuid
from typing import Literal

from fastapi import APIRouter, Depends, Header, Query, Request
from pydantic import BaseModel, Field

from ..config import get_settings
from ..db import db
from ..domain import sessions as svc
from ..domain.state_machine import S
from ..domain.capture_ranges import MAX_CAPTURE_MS, MAX_SEQUENCE
from ..errors import ApiError, not_found
from ..intelligence import insights as ins
from ..intelligence.ask import ask as run_ask, history_with_staleness
from ..memory import corrections, deletion, service as mem
from ..packs import learning, meeting
from .deps import CurrentUser, current_user, idempotent

router = APIRouter(prefix="/v1", tags=["sessions"])
Ctx = Literal["MEETING", "LEARNING", "INTERVIEW", "CONVERSATION"]


class CreateSessionIn(BaseModel):
    space_id: uuid.UUID
    context: Ctx
    title: str | None = Field(default=None, max_length=160)
    capture_source: Literal["PHONE_MIC", "DESKTOP_BRIDGE", "IMPORTED", "NONE"]
    processing_region: str
    preset: str | None = Field(default=None, max_length=80)
    project_id: uuid.UUID | None = None
    interview_mode: Literal["LIVE", "REFLECTION"] | None = None
    language: str = Field(default="en", max_length=16)


class ConsentIn(BaseModel):
    capture_basis: str
    notices_attested: bool
    ai_assistance_permitted: bool
    processing_disclosure_version: str
    participants_note: str | None = Field(default=None, max_length=300)


class Capabilities(BaseModel):
    mic_permission: Literal["granted", "denied", "undetermined"]
    input_route: str | None = None
    output_route: str | None = None
    output_device_name: str | None = Field(default=None, max_length=80)
    private_route_verified: bool = False
    measured_level_dbfs: float | None = None
    platform: str | None = None
    background_capture_supported: bool | None = None


class StartIn(BaseModel):
    consent_receipt_id: uuid.UUID
    capabilities_hash: str
    capabilities: Capabilities
    voice_enabled: bool = False
    proactive_enabled: bool = False
    assistance_mode: Literal["LISTENER", "ASK", "COMPANION"] | None = None
    proactive_intensity: Literal["QUIET", "BALANCED", "ACTIVE"] | None = None
    output_mode: Literal["TEXT", "PRIVATE_VOICE", "BOTH"] | None = None
    sensitive_opt_in: bool = False


class PauseIn(BaseModel):
    stop_watermark_sequence: int | None = Field(default=None, ge=-1, le=MAX_SEQUENCE)
    at_ms: int | None = Field(default=None, ge=0, le=MAX_CAPTURE_MS)


class ResumeIn(BaseModel):
    capabilities_hash: str
    capabilities: Capabilities
    at_ms: int | None = Field(default=None, ge=0, le=MAX_CAPTURE_MS)


class StopIn(BaseModel):
    final_sequence: int | None = Field(default=None, ge=-1, le=MAX_SEQUENCE)
    at_ms: int | None = Field(default=None, ge=0, le=MAX_CAPTURE_MS)


class CaptureStateIn(BaseModel):
    state: Literal["RECORDING", "INTERRUPTED"]
    reason: str = "AUDIO_CALLBACK_CONFIRMED"
    at_ms: int | None = Field(default=None, ge=0, le=MAX_CAPTURE_MS)
    last_sequence: int | None = Field(default=None, ge=-1, le=MAX_SEQUENCE)


class ControlsIn(BaseModel):
    assistance_mode: Literal["LISTENER", "ASK", "COMPANION"] | None = None
    proactive_intensity: Literal["QUIET", "BALANCED", "ACTIVE"] | None = None
    output_mode: Literal["TEXT", "PRIVATE_VOICE", "BOTH"] | None = None
    mute_minutes: int | None = None
    unmute: bool = False
    sensitive_opt_in: bool = False


class RouteIn(BaseModel):
    input_route: str | None = None
    output_route: str | None = None
    private_route_verified: bool = False
    device_name: str | None = Field(default=None, max_length=80)
    audio_quality: Literal["GOOD", "POOR", "SILENT_OR_BLOCKED"] | None = None


class ContextIn(BaseModel):
    context: Ctx
    preset: str | None = None


class AskIn(BaseModel):
    question: str = Field(min_length=1, max_length=4000)
    mode: Literal["REMEMBER", "THINK", "LEARN", "PREPARE"]
    scope: Literal["CURRENT_SESSION", "SELECTED_SPACE", "SELECTED_PROJECT", "GENERAL"]
    scope_id: uuid.UUID | None = None


class FeedbackIn(BaseModel):
    value: Literal["USEFUL", "NOT_USEFUL", "TOO_FREQUENT", "INCORRECT", "TOO_LATE", "DISMISSED", "SAVED"]


class SpeakerIn(BaseModel):
    verified_label: str = Field(max_length=80)
    expected_revision: int = Field(ge=1)


class UtteranceFixIn(BaseModel):
    text: str = Field(min_length=1, max_length=5000)
    expected_revision: int = Field(ge=1)


class NoteIn(BaseModel):
    kind: Literal["NOTE", "RECOLLECTION", "BOOKMARK", "QUESTION", "IDEA", "COMMITMENT"]
    text: str = Field(default="", max_length=8000)
    client_id: str | None = Field(default=None, max_length=64)
    at_ms: int | None = Field(default=None, ge=0, le=MAX_CAPTURE_MS)
    window_ms: int | None = Field(default=None, ge=1000, le=90000)


class WithdrawIn(BaseModel):
    reason: str = Field(default="PARTICIPANT_WITHDREW", max_length=200)


class ReviewIn(BaseModel):
    keep_claim_ids: list[uuid.UUID] = []
    discard_session: bool = False
    exclude_from_suggestions: bool = False


class ExplainIn(BaseModel):
    window_seconds: int = Field(default=60, ge=30, le=90)


class TtsWindowIn(BaseModel):
    start_ms: int = Field(ge=0, le=MAX_CAPTURE_MS)
    end_ms: int = Field(ge=0, le=MAX_CAPTURE_MS)


async def _load(conn, session_id, for_update=True):
    return await svc.load_session(conn, session_id, for_update=for_update)


@router.post("/sessions", status_code=201)
async def create_session(body: CreateSessionIn, request: Request, user: CurrentUser = Depends(current_user),
                         idempotency_key: str | None = Header(default=None)):
    async def fn(conn):
        s = await svc.create_session(conn, user, space_id=body.space_id, context=body.context, title=body.title,
                                     capture_source=body.capture_source, processing_region=body.processing_region, preset=body.preset,
                                     project_id=body.project_id, interview_mode=body.interview_mode, language=body.language)
        return 201, await svc.session_view(conn, s)
    return await idempotent(request, user, idempotency_key, body.model_dump(), fn)


@router.get("/sessions")
async def list_sessions(user: CurrentUser = Depends(current_user), space_id: uuid.UUID | None = None,
                        context: Ctx | None = None, active: bool = False, limit: int = Query(default=30, le=100),
                        before: str | None = None):
    async with db.user_tx(user.user_id) as conn:
        sql = ("SELECT session_id, space_id, project_id, title, context, state, capture_source, created_at, started_at, ended_at,"
               " source_watermark_ms, review_state, preset, (recap->>'status') AS recap_status,"
               " (SELECT count(*) FROM claims c WHERE c.session_id=s.session_id AND c.claim_kind='DECISION' AND c.memory_state<>'DELETED') AS decisions,"
               " (SELECT count(*) FROM claims c WHERE c.session_id=s.session_id AND c.claim_kind IN ('QUESTION','RISK') AND c.memory_state<>'DELETED') AS open_items"
               " FROM sessions s WHERE deleted_at IS NULL")
        args: list = []
        if space_id:
            args.append(space_id)
            sql += f" AND space_id=${len(args)}"
        if context:
            args.append(context)
            sql += f" AND context=${len(args)}::context_kind"
        if active:
            sql += " AND state IN ('PREFLIGHT','STARTING','RECORDING','PAUSED','INTERRUPTED','NOTES_ONLY')"
        if before:
            args.append(before)
            sql += f" AND created_at < ${len(args)}::timestamptz"
        args.append(limit)
        rows = await conn.fetch(sql + f" ORDER BY created_at DESC LIMIT ${len(args)}", *args)
    items = [dict(r) for r in rows]
    return {"items": items, "next_cursor": items[-1]["created_at"].isoformat() if len(items) == limit else None}


@router.get("/sessions/{session_id}")
async def get_session(session_id: uuid.UUID, user: CurrentUser = Depends(current_user)):
    async with db.user_tx(user.user_id) as conn:
        return await svc.session_view(conn, await _load(conn, session_id, for_update=False))


@router.post("/sessions/{session_id}/consent-receipts", status_code=201)
async def consent(session_id: uuid.UUID, body: ConsentIn, request: Request, user: CurrentUser = Depends(current_user),
                  idempotency_key: str | None = Header(default=None)):
    async def fn(conn):
        s = await _load(conn, session_id)
        await svc.require_space_write(conn, s["tenant_id"], s["space_id"])
        return 201, await svc.record_consent(conn, user, s, capture_basis=body.capture_basis, notices_attested=body.notices_attested,
                                             ai_assistance_permitted=body.ai_assistance_permitted,
                                             processing_disclosure_version=body.processing_disclosure_version,
                                             scope={"participants_note": body.participants_note} if body.participants_note else {})
    return await idempotent(request, user, idempotency_key, body.model_dump(), fn)


@router.post("/sessions/{session_id}/start")
async def start(session_id: uuid.UUID, body: StartIn, request: Request, user: CurrentUser = Depends(current_user),
                idempotency_key: str | None = Header(default=None)):
    async def fn(conn):
        s = await _load(conn, session_id)
        await svc.require_space_write(conn, s["tenant_id"], s["space_id"])
        am = body.assistance_mode or ("COMPANION" if body.proactive_enabled else "LISTENER")
        pi = body.proactive_intensity or ("BALANCED" if body.proactive_enabled else "QUIET")
        om = body.output_mode or ("PRIVATE_VOICE" if body.voice_enabled else "TEXT")
        new, ingest = await svc.start(conn, user, s, consent_receipt_id=body.consent_receipt_id, capabilities_hash=body.capabilities_hash,
                                      capabilities=body.capabilities.model_dump(), assistance_mode=am, proactive_intensity=pi,
                                      output_mode=om, sensitive_opt_in=body.sensitive_opt_in)
        return 200, await svc.session_view(conn, new) | {"ingest": ingest}
    return await idempotent(request, user, idempotency_key, body.model_dump(), fn)


@router.post("/sessions/{session_id}/notes-only")
async def notes_only(session_id: uuid.UUID, request: Request, user: CurrentUser = Depends(current_user),
                     idempotency_key: str | None = Header(default=None)):
    async def fn(conn):
        s = await _load(conn, session_id)
        if s["state"] == S.NOTES_ONLY.value:
            return 200, await svc.session_view(conn, s)
        if s["state"] not in (S.PREFLIGHT.value, S.ERROR.value):
            raise ApiError(409, "INVALID_STATE_TRANSITION", "Stop capture before switching to Notes-only.")
        return 200, await svc.session_view(conn, await svc.to_notes_only(conn, user, s, "USER_CHOSE_NOTES_ONLY"))
    return await idempotent(request, user, idempotency_key, {}, fn)


@router.post("/sessions/{session_id}/ingest-token")
async def ingest_token(session_id: uuid.UUID, user: CurrentUser = Depends(current_user)):
    async with db.user_tx(user.user_id) as conn:
        s = await _load(conn, session_id)
        await svc.require_space_write(conn, s["tenant_id"], s["space_id"])
        if not s["capture_permitted"]:
            raise ApiError(403, "CAPTURE_NOT_AUTHORIZED", "Capture isn't authorized for this session.")
        if s["state"] in (S.STARTING.value, S.RECORDING.value):
            return await svc._issue_ingest(conn, user, s, drain_only=False)
        if s["state"] in (S.PAUSED.value, S.INTERRUPTED.value, S.STOPPING.value, S.FINALIZING.value):
            return await svc._issue_ingest(conn, user, s, drain_only=True)
        raise ApiError(403, "SESSION_NOT_CAPTURING", "This session isn't accepting audio.")


@router.post("/sessions/{session_id}/capture-state")
async def capture_state(session_id: uuid.UUID, body: CaptureStateIn, user: CurrentUser = Depends(current_user)):
    async with db.user_tx(user.user_id) as conn:
        s = await _load(conn, session_id)
        await svc.require_space_write(conn, s["tenant_id"], s["space_id"])
        if body.state == "RECORDING":
            new = await svc.confirm_recording(conn, s, reason=body.reason[:60], actor="DEVICE")
        else:
            new = await svc.interrupt(conn, user, s, reason=body.reason, at_ms=body.at_ms, last_sequence=body.last_sequence)
        ingest = new.pop("_ingest", None)
        return await svc.session_view(conn, new) | ({"ingest": ingest} if ingest else {})


@router.post("/sessions/{session_id}/pause")
async def pause(session_id: uuid.UUID, body: PauseIn, request: Request, user: CurrentUser = Depends(current_user),
                idempotency_key: str | None = Header(default=None)):
    async def fn(conn):
        s = await _load(conn, session_id)
        await svc.require_space_write(conn, s["tenant_id"], s["space_id"])
        new = await svc.pause(conn, user, s, stop_watermark_sequence=body.stop_watermark_sequence, at_ms=body.at_ms)
        ingest = new.pop("_ingest", None)
        return 200, await svc.session_view(conn, new) | ({"ingest": ingest} if ingest else {})
    return await idempotent(request, user, idempotency_key, body.model_dump(), fn)


@router.post("/sessions/{session_id}/resume")
async def resume(session_id: uuid.UUID, body: ResumeIn, request: Request, user: CurrentUser = Depends(current_user),
                 idempotency_key: str | None = Header(default=None)):
    async def fn(conn):
        s = await _load(conn, session_id)
        await svc.require_space_write(conn, s["tenant_id"], s["space_id"])
        new, ingest = await svc.resume(conn, user, s, capabilities_hash=body.capabilities_hash,
                                       capabilities=body.capabilities.model_dump(), at_ms=body.at_ms)
        return 200, await svc.session_view(conn, new) | {"ingest": ingest}
    return await idempotent(request, user, idempotency_key, body.model_dump(), fn)


@router.post("/sessions/{session_id}/stop", status_code=202)
async def stop(session_id: uuid.UUID, body: StopIn, request: Request, user: CurrentUser = Depends(current_user),
               idempotency_key: str | None = Header(default=None)):
    async def fn(conn):
        s = await _load(conn, session_id)
        await svc.require_space_write(conn, s["tenant_id"], s["space_id"])
        new = await svc.stop(conn, user, s, final_sequence=body.final_sequence, at_ms=body.at_ms)
        ingest = new.pop("_ingest", None)
        return 202, await svc.session_view(conn, new) | ({"ingest": ingest} if ingest else {})
    return await idempotent(request, user, idempotency_key, body.model_dump(), fn)


@router.post("/sessions/{session_id}/finalization/retry", status_code=202)
async def retry_final(session_id: uuid.UUID, request: Request, user: CurrentUser = Depends(current_user),
                      idempotency_key: str | None = Header(default=None)):
    async def fn(conn):
        s = await _load(conn, session_id)
        await svc.require_space_write(conn, s["tenant_id"], s["space_id"])
        return 202, await svc.session_view(conn, await svc.retry_finalization(conn, user, s))
    return await idempotent(request, user, idempotency_key, {}, fn)


@router.post("/sessions/{session_id}/consent/withdraw")
async def withdraw(session_id: uuid.UUID, body: WithdrawIn, request: Request, user: CurrentUser = Depends(current_user),
                   idempotency_key: str | None = Header(default=None)):
    async def fn(conn):
        s = await _load(conn, session_id)
        await svc.require_space_write(conn, s["tenant_id"], s["space_id"])
        return 200, await svc.session_view(conn, await svc.withdraw_consent(conn, user, s, body.reason))
    return await idempotent(request, user, idempotency_key, body.model_dump(), fn)


@router.patch("/sessions/{session_id}/controls")
async def controls(session_id: uuid.UUID, body: ControlsIn, user: CurrentUser = Depends(current_user)):
    async with db.user_tx(user.user_id) as conn:
        s = await _load(conn, session_id)
        await svc.require_space_write(conn, s["tenant_id"], s["space_id"])
        new = await svc.update_controls(conn, user, s, assistance_mode=body.assistance_mode, proactive_intensity=body.proactive_intensity,
                                        output_mode=body.output_mode, mute_minutes=body.mute_minutes, unmute=body.unmute,
                                        sensitive_opt_in=body.sensitive_opt_in)
        return await svc.session_view(conn, new)


@router.post("/sessions/{session_id}/route")
async def route(session_id: uuid.UUID, body: RouteIn, user: CurrentUser = Depends(current_user)):
    async with db.user_tx(user.user_id) as conn:
        s = await _load(conn, session_id)
        await svc.require_space_write(conn, s["tenant_id"], s["space_id"])
        return await svc.update_route(conn, s, input_route=body.input_route, output_route=body.output_route,
                                      private_route_verified=body.private_route_verified, device_name=body.device_name,
                                      audio_quality=body.audio_quality)


@router.post("/sessions/{session_id}/voice/route-lost")
async def route_lost(session_id: uuid.UUID, user: CurrentUser = Depends(current_user)):
    async with db.user_tx(user.user_id) as conn:
        s = await _load(conn, session_id)
        await svc.voice_route_lost(conn, s, "CLIENT_REPORTED")
        return {"private_route_verified": False}


@router.post("/sessions/{session_id}/voice/playback-window")
async def playback_window(session_id: uuid.UUID, body: TtsWindowIn, user: CurrentUser = Depends(current_user)):
    """Client reports when MeetSaathi's own voice played so ASR never attributes it to a participant (master 5.4)."""
    if body.end_ms <= body.start_ms or body.end_ms - body.start_ms > 60000:
        raise ApiError(422, "INVALID_WINDOW", "Invalid playback window.")
    async with db.user_tx(user.user_id) as conn:
        s = await _load(conn, session_id)
        await conn.execute("UPDATE session_runtime SET tts_windows = (tts_windows || $2::jsonb) WHERE session_id=$1",
                           s["session_id"], [{"start_ms": body.start_ms, "end_ms": body.end_ms}])
        return {"ok": True}


@router.post("/sessions/{session_id}/context")
async def switch_context(session_id: uuid.UUID, body: ContextIn, user: CurrentUser = Depends(current_user)):
    async with db.user_tx(user.user_id) as conn:
        s = await _load(conn, session_id)
        await svc.require_space_write(conn, s["tenant_id"], s["space_id"])
        return await svc.session_view(conn, await svc.switch_context(conn, user, s, context=body.context, preset=body.preset))


@router.delete("/sessions/{session_id}", status_code=202)
async def delete_session(session_id: uuid.UUID, request: Request, user: CurrentUser = Depends(current_user),
                         idempotency_key: str | None = Header(default=None)):
    async def fn(conn):
        s = await _load(conn, session_id)
        return 202, await deletion.request_session_deletion(conn, user, s)
    return await idempotent(request, user, idempotency_key, {}, fn)


@router.delete("/sessions/{session_id}/audio", status_code=202)
async def delete_audio(session_id: uuid.UUID, request: Request, user: CurrentUser = Depends(current_user),
                       idempotency_key: str | None = Header(default=None)):
    async def fn(conn):
        s = await _load(conn, session_id)
        await svc.require_space_write(conn, s["tenant_id"], s["space_id"])
        if s["state"] not in ("COMPLETED", "COMPLETED_PARTIAL", "FINALIZATION_RETRYABLE"):
            raise ApiError(409, "SESSION_NOT_ENDED", "End the session before deleting its audio.")
        return 202, await deletion.request_audio_deletion(conn, user, s)
    return await idempotent(request, user, idempotency_key, {}, fn)


@router.get("/sessions/{session_id}/utterances")
async def utterances(session_id: uuid.UUID, user: CurrentUser = Depends(current_user), cursor: str | None = None,
                     limit: int = Query(default=200, le=500)):
    after = int(cursor) if cursor and cursor.isdigit() else -1
    async with db.user_tx(user.user_id) as conn:
        await _load(conn, session_id, for_update=False)
        rows = await conn.fetch(
            "SELECT u.utterance_id, r.revision, r.start_ms, r.end_ms, r.transcript AS text, r.is_final, r.provenance::text AS provenance,"
            " sp.alias AS speaker_alias, sp.user_verified_label, r.speaker_confidence, r.overlap, r.asr_confidence, r.corrected_by_user"
            " FROM utterances u JOIN utterance_revisions r ON r.utterance_id=u.utterance_id AND r.revision=u.current_revision"
            " LEFT JOIN session_speakers sp ON sp.speaker_alias_id=r.speaker_alias_id"
            " WHERE u.session_id=$1 AND r.start_ms > $2 ORDER BY r.start_ms LIMIT $3", session_id, after, limit)
        gaps = await svc.gaps(conn, session_id)
    items = []
    for r in rows:
        d = dict(r)
        d["speaker_display"] = d["user_verified_label"] or (f"{d['speaker_alias']} (unconfirmed)" if d["speaker_alias"] != "Unassigned" else "Unassigned speaker")
        d["speaker_verified"] = d.pop("user_verified_label") is not None
        d["label"] = "Final" if d["is_final"] else "Provisional"
        d["uncertain"] = bool(d["overlap"]) or (d["asr_confidence"] is not None and d["asr_confidence"] < 0.5)
        items.append(d)
    return {"items": items, "gaps": gaps, "next_cursor": str(items[-1]["start_ms"]) if len(items) == limit else None}


@router.get("/sessions/{session_id}/utterances/{utterance_id}/revisions")
async def utterance_revisions(session_id: uuid.UUID, utterance_id: uuid.UUID, user: CurrentUser = Depends(current_user)):
    async with db.user_tx(user.user_id) as conn:
        await _load(conn, session_id, for_update=False)
        rows = await conn.fetch("SELECT revision, transcript AS text, is_final, speaker_label_snapshot, revision_reason, corrected_by_user, created_at"
                                " FROM utterance_revisions WHERE utterance_id=$1 AND session_id=$2 ORDER BY revision", utterance_id, session_id)
        if not rows:
            raise not_found("transcript segment")
    return {"items": [dict(r) for r in rows]}


@router.get("/sessions/{session_id}/utterances/{utterance_id}/audio")
async def utterance_audio(session_id: uuid.UUID, utterance_id: uuid.UUID, user: CurrentUser = Depends(current_user)):
    """Evidence player: returns exactly the permitted audio for the cited span (never a different segment)."""
    from fastapi.responses import Response

    from ..speech.audio import pcm_to_wav
    from ..storage import get_store

    async with db.user_tx(user.user_id) as conn:
        s = await _load(conn, session_id, for_update=False)
        if s["audio_deleted_at"] is not None:
            raise ApiError(410, "AUDIO_DELETED", "The audio for this moment was deleted. The transcript remains.")
        r = await conn.fetchrow("SELECT r.start_ms, r.end_ms FROM utterances u JOIN utterance_revisions r ON r.utterance_id=u.utterance_id"
                                " AND r.revision=u.current_revision WHERE u.utterance_id=$1 AND u.session_id=$2", utterance_id, session_id)
        if r is None:
            raise not_found("transcript segment")
        chunks = await conn.fetch("SELECT encrypted_object_key, sample_rate_hz, capture_start_ms, duration_ms FROM audio_chunks WHERE session_id=$1"
                                  " AND ingest_status='ACKED' AND capture_start_ms + duration_ms > $2 AND capture_start_ms < $3 ORDER BY sequence_no",
                                  session_id, r["start_ms"], r["end_ms"])
    if not chunks:
        raise ApiError(404, "CLIP_UNAVAILABLE", "No audio is available for this moment.")
    store, rate = get_store(), chunks[0]["sample_rate_hz"]
    pcm = bytearray()
    for c in chunks:
        if c["sample_rate_hz"] != rate:
            break
        data = await asyncio.to_thread(store.get, s["tenant_id"], c["encrypted_object_key"])
        lo = max(0, r["start_ms"] - c["capture_start_ms"]) * rate // 1000 * 2
        hi = min(c["duration_ms"], r["end_ms"] - c["capture_start_ms"]) * rate // 1000 * 2
        pcm += data[lo:hi]
    return Response(content=pcm_to_wav(bytes(pcm), rate), media_type="audio/wav", headers={"Cache-Control": "no-store"})


@router.get("/sessions/{session_id}/speakers")
async def speakers(session_id: uuid.UUID, user: CurrentUser = Depends(current_user)):
    async with db.user_tx(user.user_id) as conn:
        await _load(conn, session_id, for_update=False)
        rows = await conn.fetch("SELECT sp.alias, sp.user_verified_label, sp.mapping_revision, sp.confidence,"
                                " (SELECT count(*) FROM utterance_revisions r JOIN utterances u ON u.utterance_id=r.utterance_id AND r.revision=u.current_revision"
                                "  WHERE r.speaker_alias_id=sp.speaker_alias_id) AS utterances,"
                                " (SELECT bool_or(r.overlap) FROM utterance_revisions r WHERE r.speaker_alias_id=sp.speaker_alias_id) AS has_overlap"
                                " FROM session_speakers sp WHERE sp.session_id=$1 ORDER BY sp.alias", session_id)
        rt = await svc.runtime(conn, session_id)
    return {"items": [dict(r) | {"status": "VERIFIED_BY_USER" if r["user_verified_label"] else "ANONYMOUS"} for r in rows],
            "speakers_need_review": rt.get("speakers_need_review", False),
            "notice": "Speaker labels separate voices; they don't identify people. Names appear only when you confirm them."}


@router.patch("/sessions/{session_id}/speakers/{alias}", status_code=202)
async def correct_speaker(session_id: uuid.UUID, alias: str, body: SpeakerIn, request: Request, user: CurrentUser = Depends(current_user),
                          idempotency_key: str | None = Header(default=None)):
    async def fn(conn):
        s = await _load(conn, session_id)
        await svc.require_space_write(conn, s["tenant_id"], s["space_id"])
        return 202, await corrections.correct_speaker(conn, user, s, alias, body.verified_label, body.expected_revision)
    return await idempotent(request, user, idempotency_key, body.model_dump(), fn)


@router.patch("/sessions/{session_id}/utterances/{utterance_id}", status_code=202)
async def correct_utterance(session_id: uuid.UUID, utterance_id: uuid.UUID, body: UtteranceFixIn, request: Request,
                            user: CurrentUser = Depends(current_user), idempotency_key: str | None = Header(default=None)):
    async def fn(conn):
        s = await _load(conn, session_id)
        await svc.require_space_write(conn, s["tenant_id"], s["space_id"])
        return 202, await corrections.correct_transcript(conn, user, s, utterance_id, body.text, body.expected_revision)
    return await idempotent(request, user, idempotency_key, body.model_dump(), fn)


@router.post("/sessions/{session_id}/ask")
async def ask(session_id: uuid.UUID, body: AskIn, user: CurrentUser = Depends(current_user)):
    async with db.user_tx(user.user_id) as conn:
        s = await _load(conn, session_id, for_update=False)
    return await run_ask(user, session=s, question=body.question, mode=body.mode, scope=body.scope, scope_id=body.scope_id)


@router.get("/sessions/{session_id}/asks")
async def ask_history(session_id: uuid.UUID, user: CurrentUser = Depends(current_user)):
    async with db.user_tx(user.user_id) as conn:
        await _load(conn, session_id, for_update=False)
        return {"items": await history_with_staleness(conn, user, session_id)}


@router.post("/sessions/{session_id}/explain")
async def explain(session_id: uuid.UUID, body: ExplainIn, user: CurrentUser = Depends(current_user)):
    async with db.user_tx(user.user_id) as conn:
        s = await _load(conn, session_id, for_update=False)
    return await learning.explain(user, s, body.window_seconds)


@router.get("/sessions/{session_id}/insights")
async def list_insights(session_id: uuid.UUID, user: CurrentUser = Depends(current_user)):
    async with db.user_tx(user.user_id) as conn:
        await _load(conn, session_id, for_update=False)
        rows = await conn.fetch("SELECT insight_id, kind, short_text, long_text, source_kind, status, output_channel, evidence_refs, expires_at,"
                                " delivered_at, feedback FROM insights WHERE session_id=$1 AND status<>'SUPPRESSED' ORDER BY created_at DESC LIMIT 50",
                                session_id)
    return {"items": [dict(r) | {"not_current": r["status"] != "DELIVERED"} for r in rows]}


@router.get("/sessions/{session_id}/insights/{insight_id}")
async def insight_detail(session_id: uuid.UUID, insight_id: uuid.UUID, user: CurrentUser = Depends(current_user)):
    async with db.user_tx(user.user_id) as conn:
        s = await _load(conn, session_id, for_update=False)
        return await ins.why(conn, s, insight_id)


@router.post("/sessions/{session_id}/insights/{insight_id}/feedback")
async def insight_feedback(session_id: uuid.UUID, insight_id: uuid.UUID, body: FeedbackIn, request: Request,
                           user: CurrentUser = Depends(current_user), idempotency_key: str | None = Header(default=None)):
    async def fn(conn):
        s = await _load(conn, session_id, for_update=False)
        return 200, await ins.feedback(conn, user, s, insight_id, body.value)
    return await idempotent(request, user, idempotency_key, body.model_dump(), fn)


@router.post("/sessions/{session_id}/notes", status_code=201)
async def add_note(session_id: uuid.UUID, body: NoteIn, user: CurrentUser = Depends(current_user)):
    async with db.user_tx(user.user_id) as conn:
        s = await _load(conn, session_id, for_update=False)
        await svc.require_space_write(conn, s["tenant_id"], s["space_id"])
        return await mem.add_user_item(conn, user, s, kind=body.kind, text=body.text, client_id=body.client_id, at_ms=body.at_ms,
                                       window_ms=body.window_ms)


@router.get("/sessions/{session_id}/recap")
async def recap(session_id: uuid.UUID, user: CurrentUser = Depends(current_user)):
    async with db.user_tx(user.user_id) as conn:
        s = await _load(conn, session_id, for_update=False)
        return await meeting.recap(conn, s)


@router.post("/sessions/{session_id}/review")
async def review(session_id: uuid.UUID, body: ReviewIn, request: Request, user: CurrentUser = Depends(current_user),
                 idempotency_key: str | None = Header(default=None)):
    async def fn(conn):
        s = await _load(conn, session_id)
        await svc.require_space_write(conn, s["tenant_id"], s["space_id"])
        return 200, await mem.review_session(conn, user, s, keep_claim_ids=body.keep_claim_ids, discard_session=body.discard_session,
                                             exclude_from_suggestions=body.exclude_from_suggestions)
    return await idempotent(request, user, idempotency_key, body.model_dump(), fn)


@router.get("/sessions/{session_id}/events")
async def events(session_id: uuid.UUID, user: CurrentUser = Depends(current_user), after: int = 0, limit: int = Query(default=200, le=500)):
    """Receive-only fallback for the WebSocket stream (master 10)."""
    from ..domain.events import events_after

    async with db.user_tx(user.user_id) as conn:
        await _load(conn, session_id, for_update=False)
        return {"items": await events_after(conn, session_id, after, limit)}


_ = get_settings
