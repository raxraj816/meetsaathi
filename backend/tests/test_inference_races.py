"""Inference results must not resurrect deleted or corrected evidence after a provider await."""
from __future__ import annotations

import asyncio
import uuid

from app.db import db
from app.intelligence import reasoner as reasoner_mod
from app.intelligence.reasoner import ReasonerResult
from app.workers import jobs
from .conftest import FakeReasoner, consent, default_responder, new_session, put_chunk, run_jobs, signup, start
from .test_intelligence import providers, record


async def test_ai_denial_prevents_post_session_extraction(client):
    _, reasoner = providers()
    api = await signup(client)
    session = await new_session(api)
    sid = session["session_id"]
    receipt = await consent(api, sid, ai=False)
    result = await start(api, sid, receipt)
    token = result.json()["ingest"]["token"]
    for i in range(6):
        await put_chunk(client, sid, token, i)
    await run_jobs()
    await api.post(f"/v1/sessions/{sid}/stop", {"final_sequence": 5})
    await run_jobs()
    assert not [c for c in reasoner.calls if c[0] == "extract"]
    view = (await api.get(f"/v1/sessions/{sid}")).json()
    assert view["state"] in ("COMPLETED", "COMPLETED_PARTIAL")
    async with db.system_tx() as conn:
        assert (await conn.fetchval("SELECT recap FROM sessions WHERE session_id=$1", uuid.UUID(sid)))["status"] == "AI_DISABLED"


async def test_reextraction_cannot_recreate_purged_session(client, monkeypatch):
    providers()
    api = await signup(client)
    session, _ = await record(client, api, chunks=6)
    sid = session["session_id"]
    await api.post(f"/v1/sessions/{sid}/stop", {"final_sequence": 5})
    await run_jobs()
    entered, release = asyncio.Event(), asyncio.Event()
    original = jobs.extract

    async def suspended(session, evidence):
        result = await original(session, evidence)
        entered.set()
        await release.wait()
        return result

    monkeypatch.setattr(jobs, "extract", suspended)
    task = asyncio.create_task(jobs.h_reextract({"session_id": sid}, {}))
    await entered.wait()
    response = await api.delete(f"/v1/sessions/{sid}")
    assert response.status_code == 202
    await run_jobs()
    release.set()
    await task
    async with db.system_tx() as conn:
        assert await conn.fetchval("SELECT count(*) FROM claims WHERE session_id=$1", uuid.UUID(sid)) == 0
        assert await conn.fetchval("SELECT recap IS NULL FROM sessions WHERE session_id=$1", uuid.UUID(sid))


async def test_ask_does_not_return_evidence_deleted_during_inference(client):
    providers()
    api = await signup(client)
    session, _ = await record(client, api, chunks=6)
    sid = session["session_id"]
    entered, release = asyncio.Event(), asyncio.Event()

    class SuspendedReasoner(FakeReasoner):
        async def structured(self, **kw):
            entered.set()
            await release.wait()
            return ReasonerResult(default_responder(kw["task"], kw["data_blocks"]), "test", 1, 1)

    reasoner_mod.set_reasoner(SuspendedReasoner(default_responder))
    task = asyncio.create_task(api.post(f"/v1/sessions/{sid}/ask", {"question": "Ordering", "mode": "THINK", "scope": "CURRENT_SESSION"}, idem=False))
    await entered.wait()
    assert (await api.delete(f"/v1/sessions/{sid}")).status_code == 202
    release.set()
    result = await task
    assert result.status_code == 409 and result.json()["code"] == "EVIDENCE_CHANGED"
    await run_jobs()
