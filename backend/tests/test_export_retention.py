from __future__ import annotations

import uuid

from app.db import db
from app.memory.deletion import retention_sweep
from app.storage import get_store
from .conftest import new_session, run_jobs, signup


async def exported_session(client):
    api = await signup(client)
    s = await new_session(api, capture="NONE")
    await api.post(f"/v1/sessions/{s['session_id']}/notes", {"kind": "NOTE", "text": "Private planning note"}, idem=False)
    await api.post(f"/v1/sessions/{s['session_id']}/stop", {"final_sequence": -1})
    await run_jobs()
    reauth = await client.post("/v1/auth/reauth", json={"password": "correct-horse-battery"}, headers=api.h)
    api.tokens["access_token"] = reauth.json()["access_token"]
    result = await api.post("/v1/exports", {}, idem=False)
    eid = result.json()["export_id"]
    await run_jobs()
    assert (await api.get(f"/v1/exports/{eid}/download")).status_code == 200
    async with db.system_tx() as conn:
        key = await conn.fetchval("SELECT object_key FROM exports WHERE export_id=$1", uuid.UUID(eid))
    assert get_store().exists(key)
    return api, s["session_id"], eid, key


async def test_session_deletion_revokes_and_purges_existing_archive(client):
    api, sid, eid, key = await exported_session(client)
    result = await api.delete(f"/v1/sessions/{sid}")
    assert result.status_code == 202
    assert (await api.get(f"/v1/exports/{eid}/download")).status_code == 404
    await run_jobs()
    assert not get_store().exists(key)
    assert (await api.get(f"/v1/deletion-requests/{result.json()['request_id']}")).json()["status"] == "COMPLETE"


async def test_expired_archive_is_denied_before_sweep_and_removed_by_sweep(client):
    api, sid, eid, key = await exported_session(client)
    async with db.system_tx() as conn:
        await conn.execute("UPDATE exports SET expires_at=now()-interval '1 second' WHERE export_id=$1", uuid.UUID(eid))
    assert (await api.get(f"/v1/exports/{eid}/download")).status_code == 404
    await retention_sweep()
    assert not get_store().exists(key)
