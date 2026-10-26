"""Realtime gateway (resume-from-cursor, live delivery, auth), finalization failure path, start timeout,
space/account deletion and retention expiry."""
from __future__ import annotations

import asyncio
import json
import socket
import uuid

import uvicorn
import websockets

from app.db import db
from app.intelligence import reasoner as reasoner_mod
from app.main import create_app
from app.speech import adapters
from app.workers.jobs import h_sweep

from .conftest import (AlternatingDiarizer, FakeReasoner, ScriptedAsr, consent, default_responder, new_session, put_chunk,
                       recording_session, run_jobs, signup, start)


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


async def test_websocket_replays_from_cursor_then_streams_live(client):
    """Master 10: ordered events, reconnect cursor, no duplicates; token sent in-band (not in the URL)."""
    api = await signup(client)
    s, ing = await recording_session(api)
    sid = s["session_id"]
    await put_chunk(client, sid, ing["token"], 0)
    first = (await api.get(f"/v1/sessions/{sid}/events")).json()["items"]
    assert len(first) >= 2
    port = _free_port()
    server = uvicorn.Server(uvicorn.Config(create_app(), host="127.0.0.1", port=port, lifespan="off", log_level="warning"))
    task = asyncio.create_task(server.serve())
    for _ in range(100):
        if server.started:
            break
        await asyncio.sleep(0.02)
    try:
        url = f"ws://127.0.0.1:{port}/v1/sessions/{sid}/realtime"
        async with websockets.connect(url) as ws:
            await ws.send(json.dumps({"type": "auth", "access_token": api.tokens["access_token"], "cursor": first[0]["sequence"]}))
            replay = [json.loads(await asyncio.wait_for(ws.recv(), 5)) for _ in range(len(first) - 1)]
            assert [e["sequence"] for e in replay] == [e["sequence"] for e in first[1:]]
            await ws.send(json.dumps({"type": "ack", "sequence": replay[-1]["sequence"]}))
            await ws.send(json.dumps({"type": "signal", "user_speaking": True}))
            await put_chunk(client, sid, ing["token"], 1)  # commits a new audio.chunk_ack event -> NOTIFY
            live = json.loads(await asyncio.wait_for(ws.recv(), 5))
            while live.get("type") == "ping":
                live = json.loads(await asyncio.wait_for(ws.recv(), 5))
            assert live["type"] == "audio.chunk_ack" and live["sequence"] == replay[-1]["sequence"] + 1
            assert live["payload"]["received_through_sequence"] == 1
        async with db.system_tx() as conn:
            rt = await conn.fetchrow("SELECT user_speaking, last_client_ack_seq FROM session_runtime WHERE session_id=$1", uuid.UUID(sid))
        assert rt["user_speaking"] is True and rt["last_client_ack_seq"] == replay[-1]["sequence"]
        other = await signup(client)
        async with websockets.connect(url) as ws:
            await ws.send(json.dumps({"type": "auth", "access_token": other.tokens["access_token"], "cursor": 0}))
            msg = json.loads(await asyncio.wait_for(ws.recv(), 5))
            assert msg["type"] == "error" and msg["code"] == "UNAUTHENTICATED"
    finally:
        server.should_exit = True
        await task


async def test_finalization_failure_is_retryable_without_rerecording(client):
    """Master 7.1 FINALIZATION_RETRYABLE, U09: capture stays stopped; retry works."""
    adapters.set_speech_providers(ScriptedAsr(["Partition keys decided."] * 4), AlternatingDiarizer())
    from app.intelligence.reasoner import ReasonerUnavailable

    reasoner_mod.set_reasoner(FakeReasoner(lambda t, b: ReasonerUnavailable("down")))
    api = await signup(client)
    s, ing = await recording_session(api)
    sid = s["session_id"]
    for i in range(6):
        await put_chunk(client, sid, ing["token"], i)
    await api.post(f"/v1/sessions/{sid}/stop", {"final_sequence": 5})
    async with db.system_tx() as conn:
        await conn.execute("UPDATE job_outbox SET max_attempts=1 WHERE session_id=$1 AND kind='session.finalize'", uuid.UUID(sid))
    await run_jobs()
    view = (await api.get(f"/v1/sessions/{sid}")).json()
    assert view["state"] == "FINALIZATION_RETRYABLE"
    ev = (await api.get(f"/v1/sessions/{sid}/events")).json()["items"]
    assert [e for e in ev if e["type"] == "session.finalization_progress"][-1]["payload"]["message"] == "Recording saved; recap is being retried."
    reasoner_mod.set_reasoner(FakeReasoner(default_responder))
    r = await api.post(f"/v1/sessions/{sid}/finalization/retry")
    assert r.status_code == 202 and r.json()["state"] == "FINALIZING"
    await run_jobs()
    assert (await api.get(f"/v1/sessions/{sid}")).json()["state"] == "COMPLETED"


async def test_starting_without_audio_times_out_truthfully(client):
    """No phantom 'Live' state (CON-080, master 7.1 STARTING --timeout--> ERROR)."""
    api = await signup(client)
    s, _ = await recording_session(api)
    sid = uuid.UUID(s["session_id"])
    async with db.system_tx() as conn:
        await conn.execute("UPDATE session_state_log SET created_at = now() - interval '5 minutes' WHERE session_id=$1", sid)
    await h_sweep({}, {})
    assert (await api.get(f"/v1/sessions/{sid}")).json()["state"] == "ERROR"


async def test_space_deletion_requires_reauth_and_hides_everything(client):
    api = await signup(client)
    r = await api.post("/v1/spaces", {"name": "Client X"}, idem=False)
    space = r.json()["space_id"]
    from app.config import get_settings

    s = await api.post("/v1/sessions", {"space_id": space, "context": "MEETING", "capture_source": "NONE",
                                        "processing_region": get_settings().processing_region})
    assert s.status_code == 201
    assert (await api.delete(f"/v1/spaces/{space}", idem=False)).status_code == 403  # REAUTH_REQUIRED
    re = await client.post("/v1/auth/reauth", json={"password": "correct-horse-battery"}, headers=api.h)
    api.tokens["access_token"] = re.json()["access_token"]
    r = await api.delete(f"/v1/spaces/{space}", idem=False)
    assert r.status_code == 202
    assert (await api.get(f"/v1/sessions/{s.json()['session_id']}")).status_code == 404
    assert space not in [x["space_id"] for x in (await api.get("/v1/spaces")).json()["items"]]
    await run_jobs()
    assert (await api.get(f"/v1/deletion-requests/{r.json()['request_id']}")).json()["status"] == "COMPLETE"


async def test_ephemeral_session_expires_unless_kept(client):
    """CON-065, CON-017 (sensitive defaults ephemeral, quiet, voice off)."""
    api = await signup(client)
    s = await new_session(api, "CONVERSATION", preset="Trusted family discussion")
    assert s["sensitive"] and s["retention_policy_id"] == "EPHEMERAL"
    rc = await consent(api, s["session_id"])
    r = await start(api, s["session_id"], rc, assistance_mode="COMPANION", proactive_intensity="BALANCED")
    assert r.json()["proactive_intensity"] == "QUIET" and r.json()["output_mode"] == "TEXT"  # no positive opt-in
    await api.post(f"/v1/sessions/{s['session_id']}/stop", {"final_sequence": -1})
    await run_jobs()
    async with db.system_tx() as conn:
        await conn.execute("UPDATE sessions SET ended_at = now() - interval '2 days' WHERE session_id=$1", uuid.UUID(s["session_id"]))
    await h_sweep({}, {})
    await run_jobs()
    assert (await api.get(f"/v1/sessions/{s['session_id']}")).status_code == 404


async def test_account_deletion_revokes_access(client):
    api = await signup(client)
    await new_session(api, capture="NONE")
    re = await client.post("/v1/auth/reauth", json={"password": "correct-horse-battery"}, headers=api.h)
    api.tokens["access_token"] = re.json()["access_token"]
    r = await api.delete("/v1/account", idem=False)
    assert r.status_code == 202 and r.json()["access_revoked"]
    assert (await api.get("/v1/me")).status_code == 401
    await run_jobs()


async def test_usage_quota_blocks_runaway_spend(client):
    """UNI-023: hard, user-visible limit; capture/notes keep working."""
    api = await signup(client)
    me = await api.me()
    from app.domain.ops import period_now

    async with db.system_tx() as conn:
        await conn.execute("INSERT INTO usage_meters(tenant_id,period,meter,quantity) VALUES ($1,$2,'reasoner_calls',100000)",
                           uuid.UUID(me["tenant"]["tenant_id"]), period_now())
    reasoner_mod.set_reasoner(FakeReasoner(default_responder))
    r = await api.post("/v1/ask", {"question": "x", "mode": "THINK", "scope": "GENERAL"}, idem=False)
    assert r.status_code == 429 and r.json()["code"] == "QUOTA_EXCEEDED"
    s = await new_session(api, capture="NONE")
    assert s["state"] == "NOTES_ONLY"


async def test_open_websocket_is_revoked_without_waiting_for_new_content(client):
    """A revoked device must lose an existing idle stream as well as future HTTP/ingest access."""
    api = await signup(client)
    s, _ = await recording_session(api)
    sid = s["session_id"]
    events = (await api.get(f"/v1/sessions/{sid}/events")).json()["items"]
    cursor = events[-1]["sequence"]
    port = _free_port()
    server = uvicorn.Server(uvicorn.Config(create_app(), host="127.0.0.1", port=port, lifespan="off", log_level="warning"))
    task = asyncio.create_task(server.serve())
    for _ in range(100):
        if server.started:
            break
        await asyncio.sleep(0.02)
    try:
        async with websockets.connect(f"ws://127.0.0.1:{port}/v1/sessions/{sid}/realtime") as ws:
            await ws.send(json.dumps({"type": "auth", "access_token": api.tokens["access_token"], "cursor": cursor}))
            await asyncio.sleep(0.05)  # authenticated listener is idle; no new session events will wake it
            result = await api.delete(f"/v1/devices/{api.tokens['device_id']}", idem=False)
            assert result.status_code == 204
            message = json.loads(await asyncio.wait_for(ws.recv(), 2))
            assert message["type"] == "error" and message["code"] == "DEVICE_REVOKED"
    finally:
        server.should_exit = True
        await task
