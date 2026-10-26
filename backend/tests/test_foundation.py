"""Gate 0/1 foundations: identity, isolation (negative ACL tests), consent gates, state machine, idempotency,
audio ingest exactly-once semantics. QA ids are noted per test."""
from __future__ import annotations

import uuid

import asyncpg

from app.config import get_settings
from app.domain.state_machine import TRANSITIONS, S, can_transition

from .conftest import (CAPS, consent, new_session, put_chunk, recording_session, run_jobs, signup, silence_pcm, start, tone_pcm)


def test_state_machine_matches_master_7_1():
    assert can_transition(S.PREFLIGHT, S.STARTING)
    assert can_transition(S.PREFLIGHT, S.NOTES_ONLY)
    assert can_transition(S.STARTING, S.RECORDING)
    assert can_transition(S.STARTING, S.ERROR)
    assert can_transition(S.RECORDING, S.PAUSED)
    assert can_transition(S.PAUSED, S.STARTING)          # resume goes through a fresh start gate
    assert not can_transition(S.PAUSED, S.RECORDING)
    assert can_transition(S.RECORDING, S.INTERRUPTED)
    assert can_transition(S.FINALIZING, S.FINALIZATION_RETRYABLE)
    assert can_transition(S.FINALIZATION_RETRYABLE, S.FINALIZING)
    assert not can_transition(S.COMPLETED, S.RECORDING)
    assert TRANSITIONS[S.DELETED] == set()


async def test_register_login_refresh_rotation_and_reuse_detection(client):
    api = await signup(client)
    me = await api.me()
    assert {s["kind"] for s in me["spaces"]} == {"PERSONAL", "WORK", "LEARNING"}
    r = await client.post("/v1/auth/refresh", json={"refresh_token": api.tokens["refresh_token"]})
    assert r.status_code == 200
    # Replaying the rotated token revokes the device (token replay control).
    r2 = await client.post("/v1/auth/refresh", json={"refresh_token": api.tokens["refresh_token"]})
    assert r2.status_code == 401 and r2.json()["code"] == "TOKEN_REUSED"
    assert (await api.get("/v1/me")).status_code == 401


async def test_error_contract_shape(client):
    r = await client.get("/v1/me")
    body = r.json()
    assert r.status_code == 401 and set(body) >= {"code", "user_message", "retryable", "correlation_id"}


async def test_cross_tenant_session_access_is_denied(client):
    """UNI-017 / MTG-041 / Q15: forged ids and direct object lookups never leak."""
    a, b = await signup(client), await signup(client)
    s = await new_session(a)
    for path in (f"/v1/sessions/{s['session_id']}", f"/v1/sessions/{s['session_id']}/utterances",
                 f"/v1/sessions/{s['session_id']}/recap"):
        r = await b.get(path)
        assert r.status_code == 404, path
        assert s["title"] not in r.text
    # B cannot create a session in A's space or search it.
    a_space = await a.space("WORK")
    r = await b.post("/v1/sessions", {"space_id": a_space, "context": "MEETING", "capture_source": "NONE",
                                      "processing_region": get_settings().processing_region})
    assert r.status_code == 403
    r = await b.get("/v1/memories", params={"space_id": a_space, "q": "anything"})
    assert r.status_code == 403 and r.json()["user_message"] == "That memory isn't available in this space."


async def test_rls_denies_at_database_level(client):
    """Defense in depth: even raw SQL on the app role returns nothing for another user's rows."""
    a, b = await signup(client), await signup(client)
    s = await new_session(a)
    bme = await b.me()
    conn = await asyncpg.connect(get_settings().database_app_url)
    try:
        async with conn.transaction():
            await conn.execute("SELECT set_config('app.user_id', $1, true)", bme["user"]["user_id"])
            assert await conn.fetchval("SELECT count(*) FROM sessions WHERE session_id=$1", uuid.UUID(s["session_id"])) == 0
            assert await conn.fetchval("SELECT count(*) FROM spaces WHERE space_id=$1", uuid.UUID(s["space_id"])) == 0
        async with conn.transaction():  # no user bound => nothing visible at all
            assert await conn.fetchval("SELECT count(*) FROM sessions") == 0
        try:
            await conn.fetchval("SELECT count(*) FROM user_credentials")
            raise AssertionError("app role must not read credentials")
        except asyncpg.InsufficientPrivilegeError:
            pass
    finally:
        await conn.close()


async def test_idempotency_replay_and_key_reuse(client):
    api = await signup(client)
    space = await api.space("WORK")
    body = {"space_id": space, "context": "MEETING", "capture_source": "NONE", "processing_region": get_settings().processing_region}
    h = api.h | {"Idempotency-Key": "fixed-key-" + uuid.uuid4().hex}
    r1 = await client.post("/v1/sessions", json=body, headers=h)
    r2 = await client.post("/v1/sessions", json=body, headers=h)
    assert r1.status_code == r2.status_code == 201 and r1.json()["session_id"] == r2.json()["session_id"]
    assert r2.headers.get("Idempotent-Replay") == "true"
    r3 = await client.post("/v1/sessions", json=body | {"title": "different"}, headers=h)
    assert r3.status_code == 422 and r3.json()["code"] == "IDEMPOTENCY_KEY_REUSED"
    r4 = await client.post("/v1/sessions", json=body, headers=api.h)
    assert r4.status_code == 400 and r4.json()["code"] == "IDEMPOTENCY_KEY_REQUIRED"


async def test_no_recording_without_consent_and_os_permission_is_not_consent(client):
    """MTG-004, CON-010, CON-011, Q01."""
    api = await signup(client)
    s = await new_session(api)
    sid = s["session_id"]
    r = await api.post(f"/v1/sessions/{sid}/start", {"consent_receipt_id": str(uuid.uuid4()), "capabilities_hash": "x" * 16,
                                                     "capabilities": CAPS})
    assert r.status_code == 422 and r.json()["code"] == "CONSENT_REQUIRED"
    rc = await consent(api, sid, notices=False)  # mic granted but participants not informed
    assert rc["capture_permitted"] is False
    r = await start(api, sid, rc)
    assert r.status_code == 422 and r.json()["code"] == "CAPTURE_NOT_AUTHORIZED"
    assert "NOTES_ONLY" in r.json()["details"]["alternatives"]
    rc = await consent(api, sid)
    r = await start(api, sid, rc, caps=CAPS | {"mic_permission": "denied"})
    assert r.status_code == 422 and r.json()["code"] == "MICROPHONE_NOT_ENABLED"
    assert (await api.get(f"/v1/sessions/{sid}")).json()["state"] == "PREFLIGHT"


async def test_consent_never_carries_across_sessions(client):
    """CON-021: a receipt from one session can't start another."""
    api = await signup(client)
    s1, s2 = await new_session(api), await new_session(api)
    rc = await consent(api, s1["session_id"])
    r = await start(api, s2["session_id"], rc)
    assert r.status_code == 422 and r.json()["code"] == "CONSENT_REQUIRED"


async def test_defaults_are_listener_and_text(client):
    """ADR-004 / conflict ledger row 1."""
    api = await signup(client)
    s, _ = await recording_session(api)
    assert s["assistance_mode"] == "LISTENER" and s["proactive_intensity"] == "QUIET" and s["output_mode"] == "TEXT"
    assert s["state"] == "STARTING"


async def test_voice_requires_verified_private_route(client):
    """UNI-010, CON-047, MTG-045, Q23."""
    api = await signup(client)
    s = await new_session(api)
    rc = await consent(api, s["session_id"])
    r = await start(api, s["session_id"], rc, output_mode="PRIVATE_VOICE")
    assert r.status_code == 422 and r.json()["code"] == "PRIVATE_ROUTE_REQUIRED"


async def test_interview_ai_gate_is_independent_of_recording(client):
    """UNI-007, INT-022, INT-026, INT-027, INT-030."""
    api = await signup(client)
    s = await new_session(api, "INTERVIEW", interview_mode="LIVE")
    sid = s["session_id"]
    rc = await consent(api, sid, ai=False)  # recording allowed, AI not allowed
    assert rc["capture_permitted"] is True and rc["ai_assistance_permitted"] is False
    r = await start(api, sid, rc, assistance_mode="COMPANION", proactive_intensity="BALANCED")
    assert r.status_code == 403 and r.json()["code"] == "LIVE_AI_NOT_PERMITTED"
    r = await start(api, sid, rc)  # Listener: recording only
    assert r.status_code == 200
    r = await api.post(f"/v1/sessions/{sid}/ask", {"question": "What should I say?", "mode": "THINK", "scope": "CURRENT_SESSION"}, idem=False)
    assert r.status_code == 403 and r.json()["code"] == "LIVE_AI_NOT_PERMITTED"
    r = await api.patch(f"/v1/sessions/{sid}/controls", {"assistance_mode": "COMPANION"}, idem=False)
    assert r.status_code == 403
    r = await api.post(f"/v1/sessions/{sid}/explain", {"window_seconds": 60}, idem=False)
    assert r.status_code == 403


async def test_org_policy_disables_live_ai(client):
    """INT-029: enterprise policy disables live AI consistently."""
    api = await signup(client)
    me = await api.me()
    from app.db import db

    async with db.system_tx() as conn:
        await conn.execute("UPDATE tenants SET org_policy='{\"disable_live_ai\": true}'::jsonb WHERE tenant_id=$1", uuid.UUID(me["tenant"]["tenant_id"]))
    s = await new_session(api)
    rc = await consent(api, s["session_id"])
    assert rc["ai_assistance_permitted"] is False and "ORG_POLICY_DISABLES_LIVE_AI" in rc["reasons"]


async def test_notes_only_never_opens_capture(client):
    """MTG-003, LC-002, CON-005, UNI-008."""
    api = await signup(client)
    s = await new_session(api, "CONVERSATION", capture="NONE")
    assert s["state"] == "NOTES_ONLY"
    r = await api.post(f"/v1/sessions/{s['session_id']}/ingest-token", idem=False)
    assert r.status_code == 403
    r = await api.post(f"/v1/sessions/{s['session_id']}/notes", {"kind": "NOTE", "text": "Mentor suggested one skill focus."}, idem=False)
    assert r.status_code == 201


async def test_ingest_ack_watermark_gaps_and_duplicates(client):
    """UNI-003, MTG-023, MTG-024, Q25, CON-075."""
    api = await signup(client)
    s, ing = await recording_session(api)
    sid, tok = s["session_id"], ing["token"]
    assert ing["resume_cursor"] == 0
    r = await put_chunk(client, sid, tok, 0)
    assert r.status_code == 200 and r.json()["received_through_sequence"] == 0
    assert (await api.get(f"/v1/sessions/{sid}")).json()["state"] == "RECORDING"  # real audio observed
    r = await put_chunk(client, sid, tok, 2)
    assert r.json()["received_through_sequence"] == 0 and r.json()["gap_sequences"] == [1]
    pcm1 = tone_pcm(freq=330)
    r = await put_chunk(client, sid, tok, 1, pcm=pcm1)
    assert r.json()["received_through_sequence"] == 2 and r.json()["gap_sequences"] == []
    r = await put_chunk(client, sid, tok, 1, pcm=pcm1)  # duplicate replay after reconnect
    assert r.status_code == 200 and r.json()["status"] == "DUPLICATE"
    r = await put_chunk(client, sid, tok, 1, pcm=tone_pcm(freq=440))  # different bytes, same sequence
    assert r.status_code == 409 and r.json()["code"] == "CHUNK_CONFLICT"
    r = await put_chunk(client, sid, tok, 3, sha="0" * 64)
    assert r.status_code == 422 and r.json()["checksum_confirmed"] is False
    view = (await api.get(f"/v1/sessions/{sid}")).json()
    assert view["ingest"]["received_through_sequence"] == 2 and view["ingest"]["max_sequence"] == 2


async def test_pause_stops_ingest_but_accepts_earlier_frames(client):
    """CON-071 / INT-048 / MTG-019: no audio enters the backend while paused."""
    api = await signup(client)
    s, ing = await recording_session(api)
    sid, tok = s["session_id"], ing["token"]
    await put_chunk(client, sid, tok, 0)
    r = await api.post(f"/v1/sessions/{sid}/pause", {"stop_watermark_sequence": 1, "at_ms": 2000})
    assert r.status_code == 200 and r.json()["state"] == "PAUSED"
    drain = r.json()["ingest"]
    assert (await put_chunk(client, sid, tok, 1)).status_code == 401  # live token revoked on pause
    assert (await put_chunk(client, sid, drain["token"], 1)).status_code == 200  # captured before the pause
    r = await put_chunk(client, sid, drain["token"], 2)
    assert r.status_code == 409 and r.json()["code"] == "CAPTURE_PAUSED"
    r = await api.post(f"/v1/sessions/{sid}/resume", {"capabilities_hash": "caps-" + "1" * 16, "capabilities": CAPS, "at_ms": 9000})
    assert r.status_code == 200 and r.json()["state"] == "STARTING"
    assert (await put_chunk(client, sid, r.json()["ingest"]["token"], 2, start_ms=9000)).status_code == 200
    gaps = (await api.get(f"/v1/sessions/{sid}")).json()["gaps"]
    assert gaps and gaps[0]["reason"] == "PAUSED_BY_USER" and gaps[0]["end_ms"] == 9000


async def test_stop_is_immediate_idempotent_and_drains_offline_spool(client):
    """UNI-002, Q24, CON-070, MTG-020, ADR-010."""
    api = await signup(client)
    s, ing = await recording_session(api)
    sid, tok = s["session_id"], ing["token"]
    await put_chunk(client, sid, tok, 0)
    r1 = await api.post(f"/v1/sessions/{sid}/stop", {"final_sequence": 2, "at_ms": 3000})
    assert r1.status_code == 202 and r1.json()["state"] == "FINALIZING"
    r2 = await api.post(f"/v1/sessions/{sid}/stop", {"final_sequence": 2})
    assert r2.status_code == 202 and r2.json()["state"] == "FINALIZING"
    assert (await put_chunk(client, sid, tok, 1)).status_code == 401  # live credential ended
    drain = r1.json()["ingest"]
    assert drain["drain_only"] is True
    assert (await put_chunk(client, sid, drain["token"], 1)).status_code == 200
    assert (await put_chunk(client, sid, drain["token"], 3)).status_code == 409  # beyond final_sequence
    await run_jobs()
    assert (await api.get(f"/v1/sessions/{sid}")).json()["state"] == "FINALIZING"  # still waiting for seq 2
    assert (await put_chunk(client, sid, drain["token"], 2)).status_code == 200
    await run_jobs()
    view = (await api.get(f"/v1/sessions/{sid}")).json()
    assert view["state"] == "COMPLETED"
    assert view["transcript_status"] in ("UNAVAILABLE", "NONE")  # no ASR configured: honest, no fake transcript
    recap = (await api.get(f"/v1/sessions/{sid}/recap")).json()
    assert recap["recap"]["status"] in ("NO_TRANSCRIPT", "AI_UNAVAILABLE")


async def test_revoked_device_cannot_stream(client):
    """UNI-025."""
    api = await signup(client)
    s, ing = await recording_session(api)
    await put_chunk(client, s["session_id"], ing["token"], 0)
    me_dev = api.tokens["device_id"]
    assert (await api.delete(f"/v1/devices/{me_dev}", idem=False)).status_code == 204
    r = await put_chunk(client, s["session_id"], ing["token"], 1)
    assert r.status_code == 401


async def test_interrupted_capture_marks_gap_and_truthful_status(client):
    """MTG-016, LC-018, Q10, CON-055."""
    api = await signup(client)
    s, ing = await recording_session(api)
    sid = s["session_id"]
    await put_chunk(client, sid, ing["token"], 0)
    r = await api.post(f"/v1/sessions/{sid}/capture-state", {"state": "INTERRUPTED", "reason": "OS_INTERRUPTION", "at_ms": 1000,
                                                             "last_sequence": 0}, idem=False)
    assert r.status_code == 200 and r.json()["state"] == "INTERRUPTED"
    ev = (await api.get(f"/v1/sessions/{sid}/events")).json()["items"]
    status = [e for e in ev if e["type"] == "session.status" and e["payload"]["code"] == "CAPTURE_INTERRUPTED"]
    assert status and "earlier audio is safe" in status[0]["payload"]["message"]
    await api.post(f"/v1/sessions/{sid}/stop", {"final_sequence": 0})
    await run_jobs()
    assert (await api.get(f"/v1/sessions/{sid}")).json()["state"] == "COMPLETED_PARTIAL"


async def test_consent_withdrawal_stops_capture_and_rejects_uploads(client):
    """CON-013, MTG-043, INT-028."""
    api = await signup(client)
    s, ing = await recording_session(api)
    sid = s["session_id"]
    await put_chunk(client, sid, ing["token"], 0)
    r = await api.post(f"/v1/sessions/{sid}/consent/withdraw", {"reason": "PARTICIPANT_WITHDREW"})
    assert r.status_code == 200 and r.json()["state"] in ("FINALIZING", "STOPPING")
    assert r.json()["capture_permitted"] is False
    assert (await put_chunk(client, sid, ing["token"], 1)).status_code in (401, 403)


async def test_silence_is_never_sent_to_asr(client):
    """Never transcribe silence (no hallucinated speech)."""
    from app.speech import adapters

    from .conftest import ScriptedAsr

    asr = ScriptedAsr(["should never appear"])
    adapters.set_speech_providers(asr, None)
    api = await signup(client)
    s, ing = await recording_session(api)
    for i in range(6):
        await put_chunk(client, s["session_id"], ing["token"], i, pcm=silence_pcm())
    await run_jobs()
    assert asr.calls == 0
    assert (await api.get(f"/v1/sessions/{s['session_id']}/utterances")).json()["items"] == []


async def test_second_capture_on_same_device_requires_ending_first(client):
    api = await signup(client)
    first, _ = await recording_session(api)
    second = await new_session(api)
    receipt = await consent(api, second["session_id"])
    result = await start(api, second["session_id"], receipt)
    assert result.status_code == 409 and result.json()["code"] == "ACTIVE_SESSION_EXISTS"
    await api.post(f"/v1/sessions/{first['session_id']}/stop", {"final_sequence": -1})
    result = await start(api, second["session_id"], receipt)
    assert result.status_code == 200


async def test_explicit_ai_denial_is_honored_in_every_context(client):
    for context in ("MEETING", "LEARNING", "CONVERSATION"):
        api = await signup(client)
        session = await new_session(api, context, capture="PHONE_MIC")
        receipt = await consent(api, session["session_id"], ai=False)
        assert receipt["capture_permitted"] and not receipt["ai_assistance_permitted"]
        result = await start(api, session["session_id"], receipt)
        assert result.status_code == 200
        assert not result.json()["ai_assistance_permitted"]
        rejected = await api.post(f"/v1/sessions/{session['session_id']}/ask", {"question": "Analyze", "mode": "THINK", "scope": "CURRENT_SESSION"}, idem=False)
        assert rejected.status_code == 403


async def test_registration_requires_adult_confirmation(client):
    """LC-041: the under-18 pathway is clearly blocked, never silently accepted."""
    body = {"email": "minor@example.test", "password": "correct-horse-battery", "device": {"platform": "TEST", "name": "t"}}
    r = await client.post("/v1/auth/register", json=body)
    assert r.status_code == 422 and r.json()["code"] == "AGE_REQUIREMENT"
    r = await client.post("/v1/auth/register", json=body | {"age_confirmed": False})
    assert r.status_code == 422 and r.json()["code"] == "AGE_REQUIREMENT"
    assert (await client.post("/v1/auth/register", json=body | {"age_confirmed": True})).status_code == 201
