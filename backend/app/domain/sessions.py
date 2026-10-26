"""Session lifecycle service (master 7.1, 10.1). All transitions are server-authoritative, versioned,
audited and published as session.state_changed events in the same transaction."""
from __future__ import annotations

import datetime as dt
import uuid
from typing import Any

import asyncpg

from ..config import get_settings
from ..errors import ApiError, conflict, not_found, policy_denied, preflight_failed
from ..security.tokens import issue_ingest_token
from . import ops
from .events import append_event
from .capture_ranges import validate_capture_counters
from .policy import evaluate_consent, is_sensitive, policy_for, validate_runtime_controls
from .state_machine import ENDED_STATES, LIVE_CAPTURE_STATES, S, assert_transition

SESSION_COLUMNS = "*"


async def load_session(conn: asyncpg.Connection, session_id: uuid.UUID, *, for_update: bool = False) -> dict:
    sql = "SELECT * FROM sessions WHERE session_id=$1 AND deleted_at IS NULL" + (" FOR UPDATE" if for_update else "")
    row = await conn.fetchrow(sql, session_id)
    if row is None:
        raise not_found("session")
    return dict(row)


async def require_space_write(conn: asyncpg.Connection, tenant_id, space_id) -> None:
    ok = await conn.fetchval("SELECT may_write_space($1,$2)", tenant_id, space_id)
    if not ok:
        raise not_found("session")


async def runtime(conn: asyncpg.Connection, session_id: uuid.UUID) -> dict:
    row = await conn.fetchrow("SELECT * FROM session_runtime WHERE session_id=$1", session_id)
    return dict(row) if row else {}


def fmt_clock(ms: int | None) -> str:
    ms = max(0, int(ms or 0))
    h, rem = divmod(ms // 1000, 3600)
    m, s = divmod(rem, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m:02d}:{s:02d}"


async def transition(conn: asyncpg.Connection, session: dict, target: S, *, reason: str, actor: str,
                     updates: dict[str, Any] | None = None) -> dict:
    assert_transition(session["state"], target)
    updates = dict(updates or {})
    cols = ["state = $2::session_state", "version = version + 1"]
    args: list[Any] = [session["session_id"], target.value]
    for k, v in updates.items():
        args.append(v)
        cols.append(f"{k} = ${len(args)}")
    row = await conn.fetchrow(f"UPDATE sessions SET {', '.join(cols)} WHERE session_id=$1 RETURNING *", *args)
    new = dict(row)
    await conn.execute(
        "INSERT INTO session_state_log(tenant_id,space_id,session_id,previous,current,reason,actor) VALUES ($1,$2,$3,$4,$5,$6,$7)",
        new["tenant_id"], new["space_id"], new["session_id"], session["state"], target.value, reason, actor)
    await append_event(conn, new, "session.state_changed", {
        "previous": session["state"], "current": target.value, "reason": reason,
        "audio_watermark_ms": int(new["source_watermark_ms"]), "version": int(new["version"])})
    return new


async def status_event(conn, session: dict, code: str, message: str, severity: str = "info", **extra) -> None:
    """Truthful, user-facing status copy (master 3.3 / 7.3). Notifications name an actual state."""
    await append_event(conn, session, "session.status", {"code": code, "message": message, "severity": severity, **extra})


async def create_session(conn: asyncpg.Connection, user, *, space_id: uuid.UUID, context: str, title: str | None,
                         capture_source: str, processing_region: str, preset: str | None, project_id: uuid.UUID | None,
                         interview_mode: str | None, language: str) -> dict:
    s = get_settings()
    policy_for(context)
    space = await conn.fetchrow("SELECT tenant_id, space_id FROM spaces WHERE space_id=$1 AND deleted_at IS NULL", space_id)
    if space is None or not await conn.fetchval("SELECT may_write_space($1,$2)", space["tenant_id"], space_id):
        raise ApiError(403, "SCOPE_DENIED", "You can't start a session in that space.")
    if processing_region not in s.allowed_region_set():
        raise preflight_failed("REGION_NOT_SUPPORTED", "Processing isn't available in that region.",
                               {"allowed": sorted(s.allowed_region_set())})
    if project_id is not None:
        ok = await conn.fetchval("SELECT 1 FROM projects WHERE project_id=$1 AND space_id=$2 AND deleted_at IS NULL", project_id, space_id)
        if not ok:
            raise ApiError(403, "SCOPE_DENIED", "That project isn't in this space.")
    if context == "INTERVIEW":
        interview_mode = interview_mode or "LIVE"
        if interview_mode not in ("LIVE", "REFLECTION"):
            raise preflight_failed("INVALID_INTERVIEW_MODE", "Choose a live interview or a reflection.")
        if interview_mode == "REFLECTION" and capture_source != "NONE":
            raise preflight_failed("REFLECTION_IS_NOTES_ONLY", "Reflection never uses the microphone.")
    else:
        interview_mode = None
    sensitive = is_sensitive(context, preset)
    pol = policy_for(context)
    state = S.NOTES_ONLY if capture_source == "NONE" else S.PREFLIGHT
    row = await conn.fetchrow(
        "INSERT INTO sessions(tenant_id,space_id,created_by,title,context,state,capture_source,processing_region,"
        " retention_policy_id,project_id,preset,interview_mode,sensitive,language,ai_assistance_permitted)"
        " VALUES ($1,$2,$3,$4,$5::context_kind,$6::session_state,$7,$8,$9,$10,$11,$12,$13,$14,$15) RETURNING *",
        space["tenant_id"], space_id, user.user_id, (title or default_title(context, preset))[:160], context, state.value,
        capture_source, processing_region, "EPHEMERAL" if sensitive else pol.default_retention, project_id, preset,
        interview_mode, sensitive, language, False)
    sess = dict(row)
    await conn.execute("INSERT INTO session_runtime(session_id,tenant_id,space_id) VALUES ($1,$2,$3)",
                       sess["session_id"], sess["tenant_id"], sess["space_id"])
    await conn.execute(
        "INSERT INTO session_state_log(tenant_id,space_id,session_id,previous,current,reason,actor) VALUES ($1,$2,$3,NULL,$4,$5,'USER')",
        sess["tenant_id"], sess["space_id"], sess["session_id"], state.value, "CREATED")
    await ops.audit(conn, tenant_id=sess["tenant_id"], user_id=user.user_id, action="session.created",
                    target_kind="session", target_id=sess["session_id"], detail={"context": context, "capture_source": capture_source})
    return sess


def default_title(context: str, preset: str | None) -> str:
    base = {"MEETING": "Meeting", "LEARNING": "Learning session", "INTERVIEW": "Interview", "CONVERSATION": "Conversation"}[context]
    return f"{base} · {preset}" if preset else base


async def record_consent(conn, user, session: dict, *, capture_basis: str, notices_attested: bool,
                         ai_assistance_permitted: bool, processing_disclosure_version: str, scope: dict) -> dict:
    if session["state"] not in (S.PREFLIGHT.value, S.NOTES_ONLY.value, S.PAUSED.value, S.INTERRUPTED.value, S.ERROR.value):
        raise conflict("INVALID_STATE_TRANSITION", "Consent can be recorded before capture starts or while paused.")
    tenant = await conn.fetchrow("SELECT residency_region, org_policy FROM tenants WHERE tenant_id=$1", session["tenant_id"])
    decision = evaluate_consent(context=session["context"], interview_mode=session["interview_mode"],
                                capture_source=session["capture_source"], capture_basis=capture_basis,
                                notices_attested=notices_attested, ai_assistance_permitted=ai_assistance_permitted,
                                disclosure_version=processing_disclosure_version, org_policy=tenant["org_policy"] or {},
                                tenant_region=tenant["residency_region"])
    # Earlier receipts for this session are superseded; consent never carries across sessions (CON-021).
    await conn.execute("UPDATE consent_receipts SET withdrawn_at=now(), withdrawal_reason='SUPERSEDED'"
                       " WHERE session_id=$1 AND withdrawn_at IS NULL", session["session_id"])
    rid = await conn.fetchval(
        "INSERT INTO consent_receipts(tenant_id,space_id,session_id,attested_by,capture_basis,notices_attested,"
        " ai_assistance_permitted,processing_disclosure_version,scope_json,capture_permitted) VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10)"
        " RETURNING receipt_id",
        session["tenant_id"], session["space_id"], session["session_id"], user.user_id, capture_basis, notices_attested,
        decision.ai_assistance_permitted, processing_disclosure_version,
        scope | {"region": tenant["residency_region"], "capture_source": session["capture_source"],
                 "context": session["context"], "interview_mode": session["interview_mode"]},
        decision.capture_permitted)
    await conn.execute("UPDATE sessions SET consent_receipt_id=$2, capture_permitted=$3, ai_assistance_permitted=$4, version=version+1"
                       " WHERE session_id=$1", session["session_id"], rid, decision.capture_permitted, decision.ai_assistance_permitted)
    await ops.audit(conn, tenant_id=session["tenant_id"], user_id=user.user_id, action="consent.recorded",
                    target_kind="session", target_id=session["session_id"],
                    detail={"capture_basis": capture_basis, "capture_permitted": decision.capture_permitted,
                            "ai_assistance_permitted": decision.ai_assistance_permitted, "reasons": decision.reasons})
    return {"receipt_id": rid, "capture_permitted": decision.capture_permitted,
            "ai_assistance_permitted": decision.ai_assistance_permitted, "reasons": decision.reasons,
            "processing_disclosure_version": processing_disclosure_version}


async def _valid_receipt(conn, session: dict, receipt_id: uuid.UUID | None) -> dict:
    if receipt_id is None:
        raise preflight_failed("CONSENT_REQUIRED", "Confirm recording permission and participant notice before starting.")
    r = await conn.fetchrow("SELECT * FROM consent_receipts WHERE receipt_id=$1 AND session_id=$2", receipt_id, session["session_id"])
    if r is None or r["withdrawn_at"] is not None:
        raise preflight_failed("CONSENT_REQUIRED", "Confirm recording permission and participant notice before starting.")
    if not r["capture_permitted"]:
        raise preflight_failed("CAPTURE_NOT_AUTHORIZED",
                               "Recording isn't authorized for this session. You can continue in Notes-only.",
                               {"alternatives": ["NOTES_ONLY", "MOCK_PRACTICE" if session["context"] == "INTERVIEW" else "REFLECTION"]})
    return dict(r)


def _check_capabilities(capabilities: dict | None, capabilities_hash: str | None) -> dict:
    if not capabilities_hash or len(capabilities_hash) < 8:
        raise preflight_failed("CAPABILITIES_REQUIRED", "Run the audio check before starting.")
    caps = capabilities or {}
    if caps.get("mic_permission") != "granted":
        raise preflight_failed("MICROPHONE_NOT_ENABLED", "Microphone not enabled. Enable it in Settings or continue in Notes-only.",
                               {"alternatives": ["NOTES_ONLY"]})
    if caps.get("input_route") in (None, "", "none"):
        raise preflight_failed("INPUT_ROUTE_UNAVAILABLE", "No microphone input is available right now.")
    return caps


async def _issue_ingest(conn, user, session: dict, *, drain_only: bool) -> dict:
    s = get_settings()
    jti = uuid.uuid4()
    ttl = s.ingest_token_ttl_s if not drain_only else 1800
    token, exp = issue_ingest_token(jti, user.user_id, user.device_id, session["session_id"], ttl)
    await conn.execute(
        "INSERT INTO ingest_tokens(jti,tenant_id,space_id,session_id,user_id,device_id,expires_at,drain_only)"
        " VALUES ($1,$2,$3,$4,$5,$6,to_timestamp($7),$8)",
        jti, session["tenant_id"], session["space_id"], session["session_id"], user.user_id, user.device_id, exp, drain_only)
    rt = await runtime(conn, session["session_id"])
    return {"token": token, "expires_at": dt.datetime.fromtimestamp(exp, dt.timezone.utc).isoformat().replace("+00:00", "Z"),
            "resume_cursor": int(rt.get("received_through_sequence", -1)) + 1, "drain_only": drain_only,
            "max_sequence": session.get("final_sequence") if drain_only else None}


async def _apply_route(conn, session: dict, caps: dict) -> None:
    await conn.execute(
        "UPDATE session_runtime SET input_route=$2, output_route=$3, route_device_name=$4, private_route_verified=$5,"
        " route_updated_at=now() WHERE session_id=$1",
        session["session_id"], caps.get("input_route"), caps.get("output_route"), caps.get("output_device_name"),
        bool(caps.get("private_route_verified")))


def _check_output(output_mode: str, caps: dict) -> None:
    if output_mode in ("PRIVATE_VOICE", "BOTH") and not caps.get("private_route_verified"):
        raise preflight_failed("PRIVATE_ROUTE_REQUIRED",
                               "Private voice needs a verified earbud route. Choose Text, or connect and test earbuds.",
                               {"alternatives": ["TEXT"]})


async def start(conn, user, session: dict, *, consent_receipt_id, capabilities_hash, capabilities, assistance_mode,
                proactive_intensity, output_mode, sensitive_opt_in: bool) -> tuple[dict, dict]:
    await conn.execute("SELECT pg_advisory_xact_lock(hashtextextended($1, 0))", f"capture-device:{user.device_id}")
    other = await conn.fetchval("SELECT s.session_id FROM sessions s JOIN ingest_tokens i USING(session_id)"
                                " WHERE i.device_id=$1 AND s.session_id<>$2 AND s.deleted_at IS NULL"
                                " AND s.state IN ('STARTING','RECORDING','PAUSED','INTERRUPTED') LIMIT 1",
                                user.device_id, session["session_id"])
    if other:
        raise conflict("ACTIVE_SESSION_EXISTS", "End your current session before starting another.")
    if session["state"] not in (S.PREFLIGHT.value, S.NOTES_ONLY.value, S.ERROR.value):
        if session["state"] in (S.PAUSED.value, S.INTERRUPTED.value):
            raise conflict("USE_RESUME", "This session is paused. Resume it instead.")
        raise conflict("INVALID_STATE_TRANSITION", "This session can't be started now.", {"current": session["state"]})
    if session["capture_source"] == "NONE":
        raise preflight_failed("NOTES_ONLY_SESSION", "This is a Notes-only session; the microphone isn't used.")
    receipt = await _valid_receipt(conn, session, consent_receipt_id)
    caps = _check_capabilities(capabilities, capabilities_hash)
    if await ops.capture_quota_exceeded(conn, session["tenant_id"]):
        raise ApiError(429, "QUOTA_EXCEEDED", "You've used this month's recording hours. Notes-only still works.")
    am, pi, om = validate_runtime_controls(context=session["context"], assistance_mode=assistance_mode,
                                           proactive_intensity=proactive_intensity, output_mode=output_mode,
                                           sensitive=session["sensitive"], sensitive_opt_in=sensitive_opt_in)
    if not receipt["ai_assistance_permitted"] and am != "LISTENER":
        raise policy_denied("LIVE_AI_NOT_PERMITTED",
                            "Live AI help isn't permitted for this session. Choose Listener; practice and post-session review stay available.")
    _check_output(om, caps)
    await _apply_route(conn, session, caps)
    new = await transition(conn, session, S.STARTING, reason="USER_START", actor="USER", updates={
        "capabilities_hash": capabilities_hash, "assistance_mode": am, "proactive_intensity": pi, "output_mode": om,
        "started_at": session["started_at"] or dt.datetime.now(dt.timezone.utc), "pause_watermark_sequence": None,
        "ai_assistance_permitted": receipt["ai_assistance_permitted"]})
    ingest = await _issue_ingest(conn, user, new, drain_only=False)
    await ops.audit(conn, tenant_id=new["tenant_id"], user_id=user.user_id, action="capture.started",
                    target_kind="session", target_id=new["session_id"], detail={"receipt_id": str(receipt["receipt_id"])})
    return new, ingest


async def to_notes_only(conn, user, session: dict, reason: str) -> dict:
    return await transition(conn, session, S.NOTES_ONLY, reason=reason, actor="USER")


async def confirm_recording(conn, session: dict, *, reason: str, actor: str) -> dict:
    if session["state"] == S.RECORDING.value:
        return session
    if session["state"] != S.STARTING.value:
        raise conflict("INVALID_STATE_TRANSITION", "Capture isn't starting.", {"current": session["state"]})
    return await transition(conn, session, S.RECORDING, reason=reason, actor=actor)


async def _open_gap(conn, session, at_ms: int | None, reason: str) -> None:
    await conn.execute("INSERT INTO capture_gaps(tenant_id,space_id,session_id,start_ms,reason) VALUES ($1,$2,$3,$4,$5)",
                       session["tenant_id"], session["space_id"], session["session_id"],
                       max(int(at_ms or 0), int(session["source_watermark_ms"])), reason)


async def _close_gaps(conn, session, at_ms: int | None) -> None:
    await conn.execute("UPDATE capture_gaps SET end_ms=GREATEST(start_ms, $2) WHERE session_id=$1 AND end_ms IS NULL",
                       session["session_id"], int(at_ms if at_ms is not None else session["source_watermark_ms"]))


async def pause(conn, user, session: dict, *, stop_watermark_sequence: int | None, at_ms: int | None) -> dict:
    validate_capture_counters(stop_watermark_sequence, at_ms)
    if session["state"] == S.PAUSED.value:
        return session
    if session["state"] not in (S.RECORDING.value, S.STARTING.value):
        raise conflict("INVALID_STATE_TRANSITION", "Only an active recording can be paused.", {"current": session["state"]})
    if session["state"] == S.STARTING.value:
        session = await transition(conn, session, S.RECORDING, reason="PAUSE_DURING_START", actor="SYSTEM")
    rt = await runtime(conn, session["session_id"])
    watermark = max(stop_watermark_sequence if stop_watermark_sequence is not None else -1, rt.get("max_sequence", -1))
    new = await transition(conn, session, S.PAUSED, reason="USER_PAUSE", actor="USER",
                           updates={"pause_watermark_sequence": watermark})
    await conn.execute("UPDATE ingest_tokens SET revoked_at=now() WHERE session_id=$1 AND revoked_at IS NULL AND NOT drain_only", new["session_id"])
    await _open_gap(conn, new, at_ms, "PAUSED_BY_USER")
    # Paused captures must still be able to deliver frames captured BEFORE the pause.
    ingest = await _issue_ingest(conn, user, new, drain_only=True)
    await ops.enqueue(conn, tenant_id=new["tenant_id"], space_id=new["space_id"], session_id=new["session_id"],
                      kind="asr.flush", payload={"session_id": str(new["session_id"])}, key=f"asr.flush:{new['session_id']}:{new['version']}")
    return new | {"_ingest": ingest}


async def resume(conn, user, session: dict, *, capabilities_hash, capabilities, at_ms) -> tuple[dict, dict]:
    validate_capture_counters(None, at_ms)
    if session["state"] not in (S.PAUSED.value, S.INTERRUPTED.value):
        raise conflict("INVALID_STATE_TRANSITION", "Only a paused or interrupted session can resume.", {"current": session["state"]})
    await _valid_receipt(conn, session, session["consent_receipt_id"])
    caps = _check_capabilities(capabilities, capabilities_hash)  # fresh route/permission gate
    _check_output(session["output_mode"], caps)
    await _apply_route(conn, session, caps)
    await _close_gaps(conn, session, at_ms)
    new = await transition(conn, session, S.STARTING, reason="USER_RESUME", actor="USER",
                           updates={"capabilities_hash": capabilities_hash, "pause_watermark_sequence": None})
    await conn.execute("UPDATE ingest_tokens SET revoked_at=now() WHERE session_id=$1 AND revoked_at IS NULL", new["session_id"])
    return new, await _issue_ingest(conn, user, new, drain_only=False)


INTERRUPT_REASONS = {"OS_INTERRUPTION", "INPUT_LOST", "ROUTE_CHANGED", "STORAGE_LOW", "PROCESS_RESTORED",
                     "PERMISSION_REVOKED", "THERMAL", "BATTERY_CRITICAL", "START_TIMEOUT"}


async def interrupt(conn, user, session: dict, *, reason: str, at_ms: int | None, last_sequence: int | None) -> dict:
    validate_capture_counters(last_sequence, at_ms)
    if reason not in INTERRUPT_REASONS:
        raise preflight_failed("INVALID_REASON", "Unknown interruption reason.")
    if session["state"] == S.INTERRUPTED.value:
        return session
    if session["state"] not in (S.RECORDING.value, S.STARTING.value):
        raise conflict("INVALID_STATE_TRANSITION", "Capture isn't active.", {"current": session["state"]})
    rt = await runtime(conn, session["session_id"])
    watermark = max(last_sequence if last_sequence is not None else -1, rt.get("max_sequence", -1))
    new = await transition(conn, session, S.INTERRUPTED, reason=reason, actor="DEVICE",
                           updates={"pause_watermark_sequence": watermark})
    await conn.execute("UPDATE ingest_tokens SET revoked_at=now() WHERE session_id=$1 AND revoked_at IS NULL AND NOT drain_only", new["session_id"])
    await _open_gap(conn, new, at_ms, reason)
    effective_at = max(int(at_ms or 0), int(new["source_watermark_ms"]))
    await status_event(conn, new, "CAPTURE_INTERRUPTED",
                       f"Recording stopped unexpectedly at {fmt_clock(effective_at)}; earlier audio is safe.", "error", at_ms=effective_at)
    return new | {"_ingest": await _issue_ingest(conn, user, new, drain_only=True)}


async def stop(conn, user, session: dict, *, final_sequence: int | None, at_ms: int | None, reason: str = "USER_END") -> dict:
    """End makes the mic stop promptly regardless of cloud finalization (ADR-010). Idempotent (CON-070)."""
    if S(session["state"]) in ENDED_STATES:
        return session
    validate_capture_counters(final_sequence, at_ms)
    now = dt.datetime.now(dt.timezone.utc)
    rt = await runtime(conn, session["session_id"])
    if session["state"] == S.PREFLIGHT.value:
        # Never captured anything: end straight through finalization with nothing to drain.
        final_sequence = -1
    if final_sequence is None:
        final_sequence = session["pause_watermark_sequence"] if session["pause_watermark_sequence"] is not None else -1
    # The client may be stale after recovery or an in-flight upload. End always preserves all
    # committed source audio; a missing/older client watermark cannot silently discard it.
    final_sequence = max(final_sequence, rt.get("max_sequence", -1))
    capture_end_ms = max(int(at_ms or 0), int(session["source_watermark_ms"])) if at_ms is not None else None
    new = await transition(conn, session, S.STOPPING, reason=reason, actor="USER" if reason == "USER_END" else "SYSTEM", updates={
        "capture_stopped_at": now, "final_sequence": final_sequence, "capture_end_ms": capture_end_ms,
        "drain_deadline": now if reason == "CONSENT_WITHDRAWN" else now + dt.timedelta(minutes=30)})
    await conn.execute("UPDATE ingest_tokens SET revoked_at=now() WHERE session_id=$1 AND revoked_at IS NULL", new["session_id"])
    await _close_gaps(conn, new, at_ms)
    new = await transition(conn, new, S.FINALIZING, reason="CAPTURE_STOPPED", actor="SYSTEM",
                           updates={"finalization_status": "WAITING_FOR_UPLOAD", "ended_at": now})
    await append_event(conn, new, "session.finalization_progress",
                       {"status": "WAITING_FOR_UPLOAD", "retryable": True, "terminal": False,
                        "message": "Recording stopped. Final notes are being prepared."})
    await ops.enqueue(conn, tenant_id=new["tenant_id"], space_id=new["space_id"], session_id=new["session_id"],
                      kind="session.finalize", payload={"session_id": str(new["session_id"])},
                      key=f"finalize:{new['session_id']}:{new['finalization_attempts']}")
    if new["capture_permitted"] and final_sequence >= 0 and rt.get("received_through_sequence", -1) < final_sequence:
        new["_ingest"] = await _issue_ingest(conn, user, new, drain_only=True)
    await ops.audit(conn, tenant_id=new["tenant_id"], user_id=user.user_id, action="capture.stopped",
                    target_kind="session", target_id=new["session_id"], detail={"reason": reason})
    return new


async def retry_finalization(conn, user, session: dict) -> dict:
    if session["state"] != S.FINALIZATION_RETRYABLE.value:
        raise conflict("INVALID_STATE_TRANSITION", "Finalization isn't waiting for a retry.", {"current": session["state"]})
    attempts = session["finalization_attempts"] + 1
    new = await transition(conn, session, S.FINALIZING, reason="USER_RETRY", actor="USER",
                           updates={"finalization_status": "QUEUED", "finalization_attempts": attempts})
    await conn.execute("UPDATE session_runtime SET asr_failures=0, asr_retry_at=NULL WHERE session_id=$1", new["session_id"])
    await ops.enqueue(conn, tenant_id=new["tenant_id"], space_id=new["space_id"], session_id=new["session_id"],
                      kind="session.finalize", payload={"session_id": str(new["session_id"])},
                      key=f"finalize:{new['session_id']}:{attempts}")
    return new


async def withdraw_consent(conn, user, session: dict, reason: str) -> dict:
    """Consent withdrawal stops capture promptly, never auto-resumes, rejects further uploads (CON-013, MTG-043)."""
    await conn.execute("UPDATE consent_receipts SET withdrawn_at=now(), withdrawal_reason=$2 WHERE session_id=$1 AND withdrawn_at IS NULL",
                       session["session_id"], reason[:200])
    await conn.execute("UPDATE sessions SET capture_permitted=false, version=version+1 WHERE session_id=$1", session["session_id"])
    await conn.execute("UPDATE ingest_tokens SET revoked_at=now() WHERE session_id=$1 AND revoked_at IS NULL", session["session_id"])
    session = await load_session(conn, session["session_id"], for_update=True)
    if S(session["state"]) in LIVE_CAPTURE_STATES | {S.PAUSED, S.INTERRUPTED}:
        session = await stop(conn, user, session, final_sequence=-1 if session["pause_watermark_sequence"] is None
                             else session["pause_watermark_sequence"], at_ms=None, reason="CONSENT_WITHDRAWN")
        await conn.execute("UPDATE ingest_tokens SET revoked_at=now() WHERE session_id=$1 AND revoked_at IS NULL", session["session_id"])
        session.pop("_ingest", None)
    await status_event(conn, session, "CAPTURE_ENDED", "Capture ended. Consent was withdrawn.", "error")
    await ops.audit(conn, tenant_id=session["tenant_id"], user_id=user.user_id, action="consent.withdrawn",
                    target_kind="session", target_id=session["session_id"])
    return session


async def update_controls(conn, user, session: dict, *, assistance_mode=None, proactive_intensity=None, output_mode=None,
                          mute_minutes: int | None = None, unmute: bool = False, sensitive_opt_in: bool = False) -> dict:
    am = assistance_mode or session["assistance_mode"]
    pi = proactive_intensity or session["proactive_intensity"]
    om = output_mode or session["output_mode"]
    am, pi, om = validate_runtime_controls(context=session["context"], assistance_mode=am, proactive_intensity=pi,
                                           output_mode=om, sensitive=session["sensitive"], sensitive_opt_in=sensitive_opt_in)
    if am != "LISTENER" and not session["ai_assistance_permitted"]:
        raise policy_denied("LIVE_AI_NOT_PERMITTED", "Live AI help isn't permitted for this session.")
    if om in ("PRIVATE_VOICE", "BOTH"):
        rt = await runtime(conn, session["session_id"])
        if not rt.get("private_route_verified"):
            raise preflight_failed("PRIVATE_ROUTE_REQUIRED", "Connect and test private earbuds before turning on voice.",
                                   {"alternatives": ["TEXT"]})
    mute_until = session["mute_until"]
    if unmute:
        mute_until = None
    elif mute_minutes is not None:
        if mute_minutes not in (5, 15, 60, -1):
            raise preflight_failed("INVALID_MUTE", "Mute for 5, 15 or 60 minutes, or the rest of the session.")
        mute_until = dt.datetime.now(dt.timezone.utc) + (dt.timedelta(days=365) if mute_minutes == -1 else dt.timedelta(minutes=mute_minutes))
    row = await conn.fetchrow("UPDATE sessions SET assistance_mode=$2, proactive_intensity=$3, output_mode=$4, mute_until=$5,"
                              " version=version+1 WHERE session_id=$1 RETURNING *", session["session_id"], am, pi, om, mute_until)
    new = dict(row)
    if mute_until is not None or am != "COMPANION" or pi == "QUIET":
        # Muting stops pending suggestions immediately; capture is untouched (MTG-019).
        expired = await conn.fetch("UPDATE insights SET status='EXPIRED', suppress_reason='MUTED' WHERE session_id=$1"
                                   " AND status='DELIVERED' AND expires_at > now() RETURNING insight_id", session["session_id"])
        for r in expired:
            await append_event(conn, new, "insight.expired", {"insight_id": str(r["insight_id"]), "reason": "MUTED"})
    await status_event(conn, new, "CONTROLS_UPDATED", "Assistance settings updated.", assistance_mode=am,
                       proactive_intensity=pi, output_mode=om,
                       muted_until=mute_until.isoformat() if mute_until else None)
    return new


async def update_route(conn, session: dict, *, input_route, output_route, private_route_verified: bool,
                       device_name: str | None, audio_quality: str | None) -> dict:
    rt = await runtime(conn, session["session_id"])
    was_private = bool(rt.get("private_route_verified"))
    input_changed = rt.get("input_route") is not None and input_route != rt.get("input_route")
    # Master 7.3: after an unexpected input change, quality is unverified until measured again (suggestions pause).
    await conn.execute("UPDATE session_runtime SET input_route=$2, output_route=$3, private_route_verified=$4, route_device_name=$5,"
                       " audio_quality=CASE WHEN $7 THEN NULL ELSE COALESCE($6,audio_quality) END, route_updated_at=now() WHERE session_id=$1",
                       session["session_id"], input_route, output_route, private_route_verified, device_name, audio_quality, input_changed)
    lost = was_private and not private_route_verified
    if lost:
        await voice_route_lost(conn, session, "ROUTE_CHANGED")
    if input_changed and session["state"] in (S.RECORDING.value, S.STARTING.value):
        await status_event(conn, session, "AUDIO_SOURCE_CHANGED", "Audio source changed. Checking your microphone.", "warning",
                           input_route=input_route)
    if audio_quality == "POOR":
        await status_event(conn, session, "AUDIO_POOR", "Some voices may be missing.", "warning")
    return {"private_route_verified": private_route_verified, "voice_route_lost": lost}


async def voice_route_lost(conn, session: dict, reason: str) -> None:
    """ADR-014: private voice fails closed. The client hard-mutes on its own; the server cancels pending TTS."""
    await conn.execute("UPDATE session_runtime SET private_route_verified=false, route_updated_at=now() WHERE session_id=$1",
                       session["session_id"])
    await conn.execute("UPDATE insights SET output_channel='TEXT' WHERE session_id=$1 AND status='DELIVERED'"
                       " AND output_channel IN ('PRIVATE_VOICE','BOTH') AND expires_at > now()", session["session_id"])
    await append_event(conn, session, "voice.route_lost", {"reason": reason, "message": "Private voice paused - earbuds disconnected."})


async def switch_context(conn, user, session: dict, *, context: str, preset: str | None) -> dict:
    policy_for(context)
    if S(session["state"]) in ENDED_STATES or session["state"] in (S.DELETING.value, S.DELETED.value):
        raise conflict("INVALID_STATE_TRANSITION", "The context of an ended session can't change.")
    sensitive = is_sensitive(context, preset)
    interview_mode = "LIVE" if context == "INTERVIEW" else None
    # Policy re-evaluation: entering Interview resets AI permission until a new receipt says otherwise.
    ai = session["ai_assistance_permitted"] and context != "INTERVIEW" and session["context"] != "INTERVIEW"
    if session["context"] == "INTERVIEW" and context != "INTERVIEW":
        tenant_pol = await conn.fetchval("SELECT org_policy FROM tenants WHERE tenant_id=$1", session["tenant_id"])
        ai = not (tenant_pol or {}).get("disable_live_ai")
    am = session["assistance_mode"] if ai else "LISTENER"
    pi = session["proactive_intensity"] if (ai and not sensitive) else "QUIET"
    row = await conn.fetchrow("UPDATE sessions SET context=$2::context_kind, preset=$3, sensitive=$4, interview_mode=$5,"
                              " ai_assistance_permitted=$6, assistance_mode=$7, proactive_intensity=$8, version=version+1"
                              " WHERE session_id=$1 RETURNING *", session["session_id"], context, preset, sensitive,
                              interview_mode, ai, am, pi)
    new = dict(row)
    await ops.audit(conn, tenant_id=new["tenant_id"], user_id=user.user_id, action="session.context_switched",
                    target_kind="session", target_id=new["session_id"],
                    detail={"from": session["context"], "to": context, "ai_assistance_permitted": ai})
    await status_event(conn, new, "CONTEXT_SWITCHED", f"Context changed to {context.title()}.", context=context,
                       ai_assistance_permitted=ai)
    return new


async def gaps(conn, session_id) -> list[dict]:
    rows = await conn.fetch("SELECT start_ms,end_ms,reason,missing_sequence_from,missing_sequence_to,time_bounds_estimated"
                            " FROM capture_gaps WHERE session_id=$1 ORDER BY start_ms", session_id)
    return [dict(r) for r in rows]


async def session_view(conn, session: dict) -> dict:
    rt = await runtime(conn, session["session_id"])
    receipt = None
    if session["consent_receipt_id"]:
        r = await conn.fetchrow("SELECT receipt_id, capture_basis, notices_attested, ai_assistance_permitted, capture_permitted,"
                                " recorded_at, withdrawn_at FROM consent_receipts WHERE receipt_id=$1", session["consent_receipt_id"])
        receipt = dict(r) if r else None
    return {
        "session_id": session["session_id"], "space_id": session["space_id"], "project_id": session["project_id"],
        "context": session["context"], "preset": session["preset"], "interview_mode": session["interview_mode"],
        "title": session["title"], "state": session["state"], "capture_source": session["capture_source"],
        "source_watermark_ms": int(session["source_watermark_ms"]), "version": int(session["version"]),
        "capture_end_ms": session["capture_end_ms"],
        "capture_permitted": session["capture_permitted"], "ai_assistance_permitted": session["ai_assistance_permitted"],
        "assistance_mode": session["assistance_mode"], "proactive_intensity": session["proactive_intensity"],
        "output_mode": session["output_mode"], "sensitive": session["sensitive"],
        "retention_policy_id": session["retention_policy_id"], "processing_region": session["processing_region"],
        "language": session["language"], "muted_until": session["mute_until"],
        "started_at": session["started_at"], "capture_stopped_at": session["capture_stopped_at"], "ended_at": session["ended_at"],
        "created_at": session["created_at"], "transcript_status": session["transcript_status"],
        "finalization": {"status": session["finalization_status"], "attempts": session["finalization_attempts"],
                         "error": session["finalization_error"]},
        "review_state": session["review_state"], "audio_deleted": session["audio_deleted_at"] is not None,
        "gaps": await gaps(conn, session["session_id"]),
        "ingest": {"received_through_sequence": int(rt.get("received_through_sequence", -1)),
                   "max_sequence": int(rt.get("max_sequence", -1)), "final_sequence": session["final_sequence"]},
        "route": {"input": rt.get("input_route"), "output": rt.get("output_route"), "device_name": rt.get("route_device_name"),
                  "private_route_verified": rt.get("private_route_verified", False), "audio_quality": rt.get("audio_quality")},
        "speakers_need_review": rt.get("speakers_need_review", False),
        "consent": receipt, "event_cursor": int(rt.get("event_seq", 0)),
    }
