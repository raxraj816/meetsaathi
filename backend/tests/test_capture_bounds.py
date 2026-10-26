"""Sparse counter abuse and honest gap metadata, with real PostgreSQL and API transactions."""
import asyncio
import uuid

import pytest

from app.db import db
from app.domain.capture_ranges import MAX_CAPTURE_MS, MAX_SEQUENCE
from app.workers.jobs import _missing_gaps, h_finalize
from .conftest import put_chunk, recording_session, signup


async def expired_finalize(api, sid):
    async with db.system_tx() as conn:
        await conn.execute("UPDATE sessions SET drain_deadline=now()-interval '1 second' WHERE session_id=$1", uuid.UUID(str(sid)))
    # Guard against regressions that expand the counter span rather than the stored rows.
    await asyncio.wait_for(h_finalize({"session_id": str(sid)}, {"attempts": 3}), 3)
    return (await api.get(f"/v1/sessions/{sid}")).json()


async def test_sparse_bigint_ingest_and_finalization_are_bounded(client):
    """UNI-003, MTG-024: large missing spans cannot monopolize ingest or finalization."""
    api = await signup(client)
    s, ing = await recording_session(api)
    sid, tok = s["session_id"], ing["token"]
    async with asyncio.timeout(3):
        r = await put_chunk(client, sid, tok, MAX_SEQUENCE, start_ms=5000)
        assert r.status_code == 200, r.text
        assert r.json()["gap_sequences"] == list(range(1000))
        assert r.json()["gap_sequences_truncated"] is True
        assert (await put_chunk(client, sid, tok, 0)).json()["received_through_sequence"] == 0
        assert (await put_chunk(client, sid, tok, 2)).json()["received_through_sequence"] == 0
        filled = await put_chunk(client, sid, tok, 1)
        assert filled.json()["received_through_sequence"] == 2
        assert filled.json()["gap_sequences"][0] == 3
    stop = await api.post(f"/v1/sessions/{sid}/stop", {"final_sequence": MAX_SEQUENCE, "at_ms": 6000})
    assert stop.status_code == 202
    view = await expired_finalize(api, sid)
    assert view["state"] == "COMPLETED_PARTIAL"
    holes = [g for g in view["gaps"] if g["reason"] == "UPLOAD_MISSING"]
    assert len(holes) == 1
    assert (holes[0]["missing_sequence_from"], holes[0]["missing_sequence_to"]) == (3, MAX_SEQUENCE-1)
    assert (holes[0]["start_ms"], holes[0]["end_ms"]) == (3000, 5000)
    assert holes[0]["time_bounds_estimated"] is True


@pytest.mark.parametrize("first_sequence,truncated", [(1000, False), (1001, True)])
async def test_gap_summary_reports_whether_1000_ids_are_complete(client, first_sequence, truncated):
    api = await signup(client)
    s, ing = await recording_session(api)
    r = await put_chunk(client, s["session_id"], ing["token"], first_sequence, start_ms=2000)
    assert r.status_code == 200 and r.json()["gap_sequences"] == list(range(1000))
    assert r.json()["gap_sequences_truncated"] is truncated


@pytest.mark.parametrize("end_ms", [None, 5000])
async def test_missing_tail_has_estimated_or_unknown_end_not_invented_duration(client, end_ms):
    api = await signup(client)
    s, ing = await recording_session(api)
    sid = s["session_id"]
    assert (await put_chunk(client, sid, ing["token"], 0)).status_code == 200
    body = {"final_sequence": MAX_SEQUENCE}
    if end_ms is not None:
        body["at_ms"] = end_ms
    await api.post(f"/v1/sessions/{sid}/stop", body)
    view = await expired_finalize(api, sid)
    gap = next(g for g in view["gaps"] if g["reason"] == "UPLOAD_MISSING")
    assert gap["start_ms"] == 1000 and gap["end_ms"] == end_ms
    assert gap["missing_sequence_from"] == 1 and gap["missing_sequence_to"] == MAX_SEQUENCE
    assert gap["time_bounds_estimated"] is True
    # Recomputing the derived range is idempotent, including its stable row identity.
    async with db.system_tx() as conn:
        session = dict(await conn.fetchrow("SELECT * FROM sessions WHERE session_id=$1 FOR UPDATE", uuid.UUID(sid)))
        before = await conn.fetchval("SELECT gap_id FROM capture_gaps WHERE session_id=$1 AND reason='UPLOAD_MISSING'", uuid.UUID(sid))
        await _missing_gaps(conn, session, MAX_SEQUENCE)
        after = await conn.fetchval("SELECT gap_id FROM capture_gaps WHERE session_id=$1 AND reason='UPLOAD_MISSING'", uuid.UUID(sid))
        assert before == after


async def test_all_audio_missing_creates_one_range_and_partial_completion(client):
    api = await signup(client)
    s, _ = await recording_session(api)
    sid = s["session_id"]
    await api.post(f"/v1/sessions/{sid}/stop", {"final_sequence": MAX_SEQUENCE, "at_ms": 5_400_000})
    view = await expired_finalize(api, sid)
    assert view["state"] == "COMPLETED_PARTIAL"
    gap = next(g for g in view["gaps"] if g["reason"] == "UPLOAD_MISSING")
    assert (gap["start_ms"], gap["end_ms"], gap["missing_sequence_from"], gap["missing_sequence_to"]) == (0, 5_400_000, 0, MAX_SEQUENCE)


@pytest.mark.parametrize("final_sequence", [None, -1, 0])
async def test_stale_or_omitted_end_watermark_preserves_all_acked_audio(client, final_sequence):
    api = await signup(client)
    s, ing = await recording_session(api)
    sid = s["session_id"]
    await put_chunk(client, sid, ing["token"], 0)
    await put_chunk(client, sid, ing["token"], 2)
    body = {"at_ms": 100}
    if final_sequence is not None:
        body["final_sequence"] = final_sequence
    stopped = await api.post(f"/v1/sessions/{sid}/stop", body)
    assert stopped.status_code == 202
    assert stopped.json()["ingest"]["max_sequence"] == 2
    assert (await api.get(f"/v1/sessions/{sid}")).json()["ingest"]["final_sequence"] == 2
    assert stopped.json()["capture_end_ms"] == 3000
    assert stopped.json()["ingest"]["drain_only"] is True
    assert (await put_chunk(client, sid, stopped.json()["ingest"]["token"], 1)).status_code == 200
    view = await expired_finalize(api, sid)
    assert view["state"] == "COMPLETED" and view["gaps"] == []


@pytest.mark.parametrize("control", ["pause", "capture-state"])
async def test_pause_and_interruption_cannot_move_watermark_behind_stored_source(client, control):
    api = await signup(client)
    s, ing = await recording_session(api)
    sid = s["session_id"]
    await put_chunk(client, sid, ing["token"], 2)
    body = {"stop_watermark_sequence": -1, "at_ms": 100} if control == "pause" else {"state": "INTERRUPTED", "reason": "PROCESS_RESTORED", "last_sequence": -1, "at_ms": 100}
    paused = await api.post(f"/v1/sessions/{sid}/{control}", body, idem=control != "capture-state")
    assert paused.status_code == 200
    tok = paused.json()["ingest"]["token"]
    assert (await put_chunk(client, sid, tok, 0)).status_code == 200
    assert (await put_chunk(client, sid, tok, 1)).status_code == 200
    assert (await put_chunk(client, sid, tok, 3)).status_code == 409
    assert paused.json()["gaps"][0]["start_ms"] == 3000


@pytest.mark.parametrize("route,body", [
    ("stop", {"final_sequence": MAX_SEQUENCE+1}),
    ("pause", {"stop_watermark_sequence": 10**100}),
    ("capture-state", {"state": "INTERRUPTED", "reason": "PROCESS_RESTORED", "last_sequence": 10**100}),
    ("stop", {"final_sequence": 0, "at_ms": MAX_CAPTURE_MS+1}),
])
async def test_invalid_control_counters_are_validation_errors_not_database_failures(client, route, body):
    api = await signup(client)
    s, _ = await recording_session(api)
    r = await api.post(f"/v1/sessions/{s['session_id']}/{route}", body, idem=route != "capture-state")
    assert r.status_code == 422, r.text
    assert (await api.get(f"/v1/sessions/{s['session_id']}")).json()["state"] == "STARTING"


async def test_ingest_rejects_counter_and_clock_overflow_before_storage(client):
    api = await signup(client)
    s, ing = await recording_session(api)
    sid, tok = s["session_id"], ing["token"]
    for seq, start in [(MAX_SEQUENCE+1, 0), (10**100, 0), (0, MAX_CAPTURE_MS), (0, 10**100)]:
        assert (await put_chunk(client, sid, tok, seq, start_ms=start)).status_code == 422
    view = (await api.get(f"/v1/sessions/{sid}")).json()
    assert view["ingest"]["max_sequence"] == -1
    async with db.system_tx() as conn:
        assert await conn.fetchval("SELECT count(*) FROM audio_chunks WHERE session_id=$1", uuid.UUID(sid)) == 0


async def test_ninety_minute_counter_replay_can_finish_after_end(client):
    """90-minute ACK metadata fixture only, not a microphone/device/quality acceptance claim."""
    api = await signup(client)
    s, _ = await recording_session(api)
    sid = uuid.UUID(s["session_id"])
    async with db.system_tx() as conn:
        owner = await conn.fetchrow("SELECT tenant_id,space_id FROM sessions WHERE session_id=$1", sid)
        await conn.execute("INSERT INTO audio_chunks(tenant_id,space_id,session_id,sequence_no,sample_rate_hz,capture_start_ms,duration_ms,"
                           "sha256_hex,encrypted_object_key,ingest_status) SELECT $1,$2,$3,g,16000,g*1000,1000,$4,'explicit-test-metadata','ACKED'"
                           " FROM generate_series(1,5399) g", owner["tenant_id"], owner["space_id"], sid, "0"*64)
        await conn.execute("UPDATE session_runtime SET max_sequence=5399 WHERE session_id=$1", sid)
        await conn.execute("UPDATE sessions SET source_watermark_ms=5400000 WHERE session_id=$1", sid)
    stopped = await api.post(f"/v1/sessions/{sid}/stop", {"final_sequence": 5399, "at_ms": 5_400_000})
    drain = stopped.json()["ingest"]["token"]
    r = await asyncio.wait_for(put_chunk(client, sid, drain, 0), 3)
    assert r.status_code == 200 and r.json()["received_through_sequence"] == 5399
    assert r.json()["gap_sequences"] == [] and r.json()["gap_sequences_truncated"] is False
    assert (await expired_finalize(api, sid))["state"] == "COMPLETED"

async def test_finite_asr_also_processes_stored_audio_beyond_a_large_permanent_gap(client):
    from app.speech.adapters import set_speech_providers
    from .conftest import ScriptedAsr

    api = await signup(client)
    s, ing = await recording_session(api)
    sid = s["session_id"]
    await put_chunk(client, sid, ing["token"], 0)
    await put_chunk(client, sid, ing["token"], 100)
    await api.post(f"/v1/sessions/{sid}/stop", {"final_sequence": 100, "at_ms": 101000})
    set_speech_providers(ScriptedAsr(["First recorded words", "Words after the gap"]))
    try:
        assert (await expired_finalize(api, sid))["state"] == "COMPLETED_PARTIAL"
        async with db.system_tx() as conn:
            rows = await conn.fetch("SELECT transcript,start_ms FROM utterance_revisions r JOIN utterances u USING(utterance_id)"
                                    " WHERE u.session_id=$1 AND r.revision=u.current_revision ORDER BY start_ms", uuid.UUID(sid))
        assert [r["transcript"] for r in rows] == ["First recorded words", "Words after the gap"]
        assert [r["start_ms"] for r in rows] == [100, 100100]
    finally:
        set_speech_providers()

async def test_finite_provider_cannot_cite_audio_outside_the_supplied_window(client):
    from app.speech.adapters import AsrEngine, AsrSegment, SpeechUnavailable, set_speech_providers
    from app.speech.pipeline import run_asr_window

    class InvalidProvider(AsrEngine):
        def available(self):
            return True

        async def transcribe(self, wav, *, offset_ms, language):
            return [AsrSegment(offset_ms, offset_ms+9000, "Outside recorded source", .9)]

    api = await signup(client)
    s, ing = await recording_session(api)
    sid = uuid.UUID(s["session_id"])
    await put_chunk(client, sid, ing["token"], 0)
    set_speech_providers(InvalidProvider())
    try:
        with pytest.raises(SpeechUnavailable, match="outside supplied audio"):
            await run_asr_window(sid, flush=True)
        async with db.system_tx() as conn:
            assert await conn.fetchval("SELECT count(*) FROM utterances WHERE session_id=$1", sid) == 0
            assert await conn.fetchval("SELECT asr_cursor_sequence FROM sessions WHERE session_id=$1", sid) == -1
    finally:
        set_speech_providers()

async def test_consent_withdrawal_does_not_wait_for_uploads_it_forbids(client):
    api = await signup(client)
    s, ing = await recording_session(api)
    sid = s["session_id"]
    await put_chunk(client, sid, ing["token"], 2)
    withdrawn = await api.post(f"/v1/sessions/{sid}/consent/withdraw", {"reason": "PARTICIPANT_WITHDREW"})
    assert withdrawn.status_code == 200 and withdrawn.json()["capture_permitted"] is False
    assert "token" not in withdrawn.json()["ingest"]
    assert (await put_chunk(client, sid, ing["token"], 1)).status_code == 401
    # No clock manipulation: withdrawal makes the drain deadline immediate, because no further
    # upload is authorized. Available source remains accounted for in the partial result.
    await h_finalize({"session_id": sid}, {"attempts": 3})
    assert (await api.get(f"/v1/sessions/{sid}")).json()["state"] == "COMPLETED_PARTIAL"
    async with db.system_tx() as conn:
        assert await conn.fetchval("SELECT count(*) FROM ingest_tokens WHERE session_id=$1", uuid.UUID(sid)) == 1

async def test_late_source_that_outgrows_declared_end_does_not_invent_a_tail_duration(client):
    api = await signup(client)
    s, ing = await recording_session(api)
    sid = s["session_id"]
    await put_chunk(client, sid, ing["token"], 0)
    stopped = await api.post(f"/v1/sessions/{sid}/stop", {"final_sequence": 3, "at_ms": 1000})
    assert (await put_chunk(client, sid, stopped.json()["ingest"]["token"], 2)).status_code == 200
    view = await expired_finalize(api, sid)
    tail = next(g for g in view["gaps"] if g["missing_sequence_from"] == 3)
    assert tail["start_ms"] == 3000 and tail["end_ms"] is None

async def test_logically_deleted_audio_never_reaches_finite_provider(client):
    from app.speech.adapters import AsrEngine, set_speech_providers
    from app.speech.pipeline import run_asr_window

    class ForbiddenProvider(AsrEngine):
        def available(self):
            return True

        async def transcribe(self, *a, **kw):
            pytest.fail("Logically deleted source must not be sent to a provider")

    api = await signup(client)
    s, ing = await recording_session(api)
    sid = uuid.UUID(s["session_id"])
    await put_chunk(client, sid, ing["token"], 0)
    async with db.system_tx() as conn:
        await conn.execute("UPDATE sessions SET audio_deleted_at=now() WHERE session_id=$1", sid)
    set_speech_providers(ForbiddenProvider())
    try:
        assert await run_asr_window(sid, flush=True) is False
    finally:
        set_speech_providers()

async def test_published_openapi_keeps_exact_64_bit_capture_limits(client):
    schema = (await client.get('/openapi.json')).json()
    stop = schema['components']['schemas']['StopIn']['properties']
    assert stop['final_sequence']['anyOf'][0]['maximum'] == MAX_SEQUENCE
    assert stop['at_ms']['anyOf'][0]['maximum'] == MAX_CAPTURE_MS
    params = {p['name']: p['schema'] for p in schema['paths']['/v1/ingest/sessions/{session_id}/chunks/{sequence}']['put']['parameters']}
    assert params['sequence']['maximum'] == MAX_SEQUENCE
    assert params['X-Capture-Start-Ms']['maximum'] == MAX_CAPTURE_MS
    # Both are integers in the actual JSON, not a rounded floating-point maximum above bigint.
    assert type(params['sequence']['maximum']) is int
    assert params['sequence']['format'] == 'int64'
