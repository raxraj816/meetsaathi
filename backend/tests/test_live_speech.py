"""Live provider doubles + real PostgreSQL: drafts, fenced replay and end-of-input recovery."""
import asyncio
import uuid

import pytest

from app.config import get_settings
from app.db import db
from app.speech.adapters import AsrEngine, AsrSegment, SpeechUnavailable, StreamResult, set_speech_providers
from app.speech.pipeline import drain_asr
from app.speech.streaming import LeaseLost, StreamActor, claim, pending, run_session, supervise
from app.workers.runner import Reschedule
from .conftest import put_chunk, recording_session, signup, silence_pcm, tone_pcm


@pytest.fixture
def streaming_settings(monkeypatch):
    monkeypatch.setattr(get_settings(), "asr_stream_idle_s", 0.1)
    monkeypatch.setattr(get_settings(), "worker_poll_interval_s", 0.02)
    yield
    set_speech_providers()


class LiveAsr(AsrEngine):
    supports_streaming = True
    version = "explicit-live-test-double"

    def __init__(self, handler):
        self.handler = handler

    def available(self):
        return True

    async def stream(self, packets, **kw):
        await self.handler(packets, **kw)


def result(rid, start, end, text="Recorded words", partial=False):
    return StreamResult(rid, AsrSegment(start, end, text, .9, "en-IN"), partial)


async def until(predicate):
    async with asyncio.timeout(3):
        while not await predicate():
            await asyncio.sleep(.01)


async def count(sid):
    async with db.system_tx() as conn:
        return await conn.fetchval("SELECT count(*) FROM utterances WHERE session_id=$1", sid)


async def setup_audio(client, starts=(0,), pcms=None):
    api = await signup(client)
    s, ing = await recording_session(api)
    sid = uuid.UUID(s["session_id"])
    for seq, start in enumerate(starts):
        r = await put_chunk(client, sid, ing["token"], seq, pcm=pcms[seq] if pcms else None, start_ms=start)
        assert r.status_code == 200, r.text
    return api, sid


async def test_live_draft_is_visible_before_input_closes_and_never_evidence(client, streaming_settings):
    _, sid = await setup_audio(client)
    drafted, finish = asyncio.Event(), asyncio.Event()

    async def handler(packets, *, on_result, **kw):
        await anext(packets)
        await on_result(result("one", 0, 500, "Unfinished", partial=True))
        drafted.set()
        await finish.wait()
        await on_result(result("one", 0, 700, "Final words"))
        async for _ in packets:
            pass

    set_speech_providers(LiveAsr(handler))
    task = asyncio.create_task(run_session(sid))
    try:
        await asyncio.wait_for(drafted.wait(), 3)
        assert await count(sid) == 0
        async with db.system_tx() as conn:
            draft = await conn.fetchrow("SELECT payload FROM session_events WHERE session_id=$1 AND type='transcript.preview'", sid)
            assert draft["payload"]["text"] == "Unfinished" and draft["payload"]["evidence"] is False
        assert await pending(sid)
        with pytest.raises(Reschedule):
            await drain_asr(sid)
        finish.set()
        await asyncio.wait_for(task, 3)
        assert await count(sid) == 1
        async with db.system_tx() as conn:
            assert await conn.fetchval("SELECT transcript FROM utterance_revisions WHERE session_id=$1", sid) == "Final words"
            assert await conn.fetchval("SELECT asr_cursor_sequence FROM sessions WHERE session_id=$1", sid) == 0
        assert not await pending(sid)
    finally:
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)


async def test_disconnect_replays_only_exact_uncommitted_pcm_suffix(client, streaming_settings):
    _, sid = await setup_audio(client)
    offsets, seen = [], []

    async def broken(packets, *, on_result, offset_ms, **kw):
        offsets.append(offset_ms)
        seen.append(await anext(packets))
        await on_result(result("first", 0, 400))
        await until(lambda: count(sid))
        raise SpeechUnavailable("explicit transport failure")

    set_speech_providers(LiveAsr(broken))
    await run_session(sid)
    async with db.system_tx() as conn:
        r = await conn.fetchrow("SELECT s.asr_cursor_sequence,r.* FROM sessions s JOIN session_runtime r USING(session_id) WHERE session_id=$1", sid)
        assert r["asr_committed_ms"] == 400 and r["asr_cursor_sequence"] == -1
        await conn.execute("UPDATE session_runtime SET asr_retry_at=NULL WHERE session_id=$1", sid)

    async def recovered(packets, *, on_result, offset_ms, **kw):
        offsets.append(offset_ms)
        seen.append(await anext(packets))
        await on_result(result("second", 400, 1000, "Recovered suffix"))
        async for _ in packets:
            pass

    set_speech_providers(LiveAsr(recovered))
    await run_session(sid)
    assert offsets == [0, 400] and seen == [tone_pcm(), tone_pcm()[12800:]]
    async with db.system_tx() as conn:
        rows = await conn.fetch("SELECT start_ms,end_ms FROM utterance_revisions WHERE session_id=$1 ORDER BY start_ms", sid)
        assert [(r["start_ms"], r["end_ms"]) for r in rows] == [(0, 400), (400, 1000)]
    assert not await pending(sid)


async def test_expired_owner_cannot_write_after_takeover(client, streaming_settings):
    _, sid = await setup_audio(client)
    set_speech_providers(LiveAsr(None))
    old = await claim(sid)
    actor = StreamActor(sid, old)
    packets = actor.packets()
    await anext(packets)
    await actor.result(result("draft", 0, 500, partial=True))
    assert await claim(sid) is None
    async with db.system_tx() as conn:
        await conn.execute("UPDATE session_runtime SET asr_stream_lease_until=now()-interval '1 second' WHERE session_id=$1", sid)
    new = await claim(sid)
    assert new and old != new
    with pytest.raises(LeaseLost):
        await actor.result(result("late", 0, 700))
    assert await count(sid) == 0
    async with db.system_tx() as conn:
        clear = await conn.fetchval("SELECT payload FROM session_events WHERE session_id=$1 AND type='transcript.preview_clear' ORDER BY sequence DESC LIMIT 1", sid)
        assert clear["run_id"] == str(old)
    await packets.aclose()


async def test_audio_deletion_during_stream_cannot_resurrect_evidence(client, streaming_settings):
    _, sid = await setup_audio(client)
    set_speech_providers(LiveAsr(None))
    actor = StreamActor(sid, await claim(sid))
    packets = actor.packets()
    await anext(packets)
    async with db.system_tx() as conn:
        await conn.execute("UPDATE sessions SET audio_deleted_at=now() WHERE session_id=$1", sid)
    with pytest.raises(LeaseLost):
        await actor.result(result("late", 0, 700))
    assert await count(sid) == 0 and not await pending(sid)
    await packets.aclose()


async def test_capture_discontinuities_are_separate_clean_connections(client, streaming_settings):
    _, sid = await setup_audio(client, starts=(0, 5000, 6000))
    offsets = []

    async def handler(packets, *, offset_ms, **kw):
        offsets.append(offset_ms)
        async for _ in packets:
            pass

    set_speech_providers(LiveAsr(handler))
    await run_session(sid)
    assert offsets == [0] and await pending(sid)
    await run_session(sid)
    assert offsets == [0, 5000] and not await pending(sid)


async def test_silence_never_creates_words_and_preserves_stream_clock(client, streaming_settings):
    _, sid = await setup_audio(client, starts=(0, 1000, 2000), pcms=[silence_pcm(), tone_pcm(), silence_pcm()])
    seen = []

    async def handler(packets, *, on_result, offset_ms, **kw):
        assert offset_ms == 1000
        async for pcm in packets:
            seen.append(pcm)
        await on_result(result("hallucinated", 2000, 2900, "Silence hallucination"))

    set_speech_providers(LiveAsr(handler))
    await run_session(sid)
    assert seen == [tone_pcm(), silence_pcm()]
    assert await count(sid) == 0 and not await pending(sid)


async def test_all_silence_opens_no_cloud_stream(client, streaming_settings):
    _, sid = await setup_audio(client, pcms=[silence_pcm()])

    async def forbidden(*a, **kw):
        pytest.fail("No cloud connection should open for initial silence")

    set_speech_providers(LiveAsr(forbidden))
    await run_session(sid)
    assert not await pending(sid)


async def test_supervisor_bounds_connections_and_releases_on_shutdown(client, streaming_settings, monkeypatch):
    _, sid1 = await setup_audio(client)
    _, sid2 = await setup_audio(client)
    active, peak = 0, 0
    started = asyncio.Event()
    monkeypatch.setattr(get_settings(), "asr_stream_concurrency", 1)

    async def handler(packets, **kw):
        nonlocal active, peak
        await anext(packets)
        active += 1
        peak = max(peak, active)
        started.set()
        try:
            await asyncio.Event().wait()
        finally:
            active -= 1

    set_speech_providers(LiveAsr(handler))
    async with db.system_tx() as conn:
        parked = await conn.fetch("SELECT session_id,asr_retry_at FROM session_runtime WHERE session_id<>ALL($1::uuid[])", [sid1,sid2])
        await conn.execute("UPDATE session_runtime SET asr_retry_at=now()+interval '1 day' WHERE session_id<>ALL($1::uuid[])", [sid1,sid2])
    task = asyncio.create_task(supervise())
    try:
        await asyncio.wait_for(started.wait(), 3)
        # An ordinary durable job remains runnable while a provider connection is held open.
        from app.domain import ops
        from app.workers.jobs import HANDLERS
        from app.workers.runner import run_one
        completed = asyncio.Event()

        async def ordinary(payload, job):
            completed.set()

        monkeypatch.setitem(HANDLERS, "test.ordinary", ordinary)
        async with db.system_tx() as conn:
            owner = await conn.fetchrow("SELECT tenant_id,space_id FROM sessions WHERE session_id=$1", sid1)
            await ops.enqueue(conn, tenant_id=owner["tenant_id"], space_id=owner["space_id"], session_id=sid1,
                              kind="test.ordinary", payload={}, key=f"ordinary:{sid1}")
            job_id = await conn.fetchval("SELECT job_id FROM job_outbox WHERE idempotency_key=$1", f"ordinary:{sid1}")
        assert await run_one(job_id)
        assert completed.is_set() and active == 1
        async with db.system_tx() as conn:
            assert await conn.fetchval("SELECT count(*) FROM session_runtime WHERE session_id=ANY($1::uuid[]) AND asr_stream_lease_until>now()", [sid1,sid2]) == 1
    finally:
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)
        async with db.system_tx() as conn:
            await conn.executemany("UPDATE session_runtime SET asr_retry_at=$2 WHERE session_id=$1",
                                   [(r["session_id"],r["asr_retry_at"]) for r in parked])
    assert peak == 1 and active == 0
    async with db.system_tx() as conn:
        assert await conn.fetchval("SELECT count(*) FROM session_runtime WHERE session_id=ANY($1::uuid[]) AND asr_stream_lease_until>now()", [sid1,sid2]) == 0


async def test_ingest_preserves_pcm_duration_and_monotonic_capture_clock(client, streaming_settings):
    api = await signup(client)
    s, ing = await recording_session(api)
    sid = s["session_id"]
    # Arrival order may differ from capture order; metadata must still fit both neighbours.
    assert (await put_chunk(client, sid, ing["token"], 1, start_ms=1000)).status_code == 200
    bad_clock = await put_chunk(client, sid, ing["token"], 0, start_ms=500)
    assert bad_clock.status_code == 422 and bad_clock.json()["code"] == "CHUNK_CLOCK_CONFLICT"
    assert (await put_chunk(client, sid, ing["token"], 0, start_ms=0)).status_code == 200
    changed = await put_chunk(client, sid, ing["token"], 0, start_ms=1)
    assert changed.status_code == 409
    odd = await put_chunk(client, sid, ing["token"], 2, pcm=tone_pcm()+b'\0')
    assert odd.status_code == 422
    mismatch = await client.put(f"/v1/ingest/sessions/{sid}/chunks/2", content=tone_pcm(950), headers={
        "Authorization": f"Bearer {ing['token']}", "X-Sample-Rate": "16000", "X-Capture-Start-Ms": "2000",
        "X-Duration-Ms": "1000", "X-Sha256": "0"*64, "X-Encoding": "pcm_s16le"})
    assert mismatch.status_code == 422 and mismatch.json()["code"] == "CHUNK_LENGTH_MISMATCH"

async def test_finalization_waits_for_provider_drain_even_when_cursor_caught_up(client, streaming_settings):
    _, sid = await setup_audio(client)
    release = asyncio.Event()

    async def handler(packets, *, on_result, **kw):
        await anext(packets)
        await on_result(result("whole-chunk", 0, 1000))
        await release.wait()
        async for _ in packets:
            pass

    set_speech_providers(LiveAsr(handler))
    task = asyncio.create_task(run_session(sid))
    try:
        await until(lambda: count(sid))
        async with db.system_tx() as conn:
            assert await conn.fetchval("SELECT asr_cursor_sequence FROM sessions WHERE session_id=$1", sid) == 0
        with pytest.raises(Reschedule):
            await drain_asr(sid)
        release.set()
        await asyncio.wait_for(task, 3)
        assert not await pending(sid)
    finally:
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)

async def test_persistent_provider_failure_can_be_retried_without_rerecording(client, streaming_settings):
    from app.intelligence import reasoner as reasoner_mod
    from .conftest import FakeReasoner, default_responder, run_jobs

    api, sid = await setup_audio(client)

    async def broken(packets, **kw):
        await anext(packets)
        raise SpeechUnavailable("Explicit provider outage")

    set_speech_providers(LiveAsr(broken))
    for _ in range(get_settings().asr_stream_retry_budget):
        async with db.system_tx() as conn:
            await conn.execute("UPDATE session_runtime SET asr_retry_at=NULL WHERE session_id=$1", sid)
        await run_session(sid)
    stopped = await api.post(f"/v1/sessions/{sid}/stop", {"final_sequence": 0})
    assert stopped.status_code == 202
    async with db.system_tx() as conn:
        await conn.execute("UPDATE job_outbox SET max_attempts=1 WHERE session_id=$1 AND kind='session.finalize'", sid)
    await run_jobs()
    view = (await api.get(f"/v1/sessions/{sid}")).json()
    assert view["state"] == "FINALIZATION_RETRYABLE"
    assert await count(sid) == 0
    retry = await api.post(f"/v1/sessions/{sid}/finalization/retry")
    assert retry.status_code == 202
    async with db.system_tx() as conn:
        assert await conn.fetchval("SELECT asr_failures FROM session_runtime WHERE session_id=$1", sid) == 0

    async def recovered(packets, *, on_result, **kw):
        await anext(packets)
        await on_result(result("recovered", 0, 900, "Recorded words survived the outage"))
        async for _ in packets:
            pass

    set_speech_providers(LiveAsr(recovered))
    reasoner_mod.set_reasoner(FakeReasoner(default_responder))
    await run_session(sid)
    await run_jobs()
    assert (await api.get(f"/v1/sessions/{sid}")).json()["state"] == "COMPLETED"
    assert await count(sid) == 1

async def test_sustained_silence_still_warns_without_opening_a_provider(client, streaming_settings):
    _, sid = await setup_audio(client, starts=tuple(i*1000 for i in range(12)), pcms=[silence_pcm() for _ in range(12)])

    async def forbidden(*a, **kw):
        pytest.fail("Silence must not open a provider connection")

    set_speech_providers(LiveAsr(forbidden))
    await run_session(sid)
    async with db.system_tx() as conn:
        assert await conn.fetchval("SELECT audio_quality FROM session_runtime WHERE session_id=$1", sid) == "SILENT_OR_BLOCKED"
        assert await conn.fetchval("SELECT count(*) FROM session_events WHERE session_id=$1 AND type='session.status'"
                                   " AND payload->>'code'='AUDIO_POOR'", sid) == 1
    assert not await pending(sid)
