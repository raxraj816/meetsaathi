from __future__ import annotations

import asyncio
import json
import uuid

from app.config import get_settings
from app.db import db
from app.domain import ops
from app.workers import runner, sqs
from app.workers.jobs import HANDLERS
from .conftest import signup


async def enqueue_test_job(client):
    api = await signup(client)
    me = await api.me()
    async with db.system_tx() as conn:
        key = str(uuid.uuid4())
        await ops.enqueue(conn, tenant_id=uuid.UUID(me["tenant"]["tenant_id"]), space_id=uuid.UUID(me["spaces"][0]["space_id"]),
                          session_id=None, kind="delivery.test", payload={}, key=key)
        return await conn.fetchval("SELECT job_id FROM job_outbox WHERE idempotency_key=$1", key)


async def test_expired_lease_owner_cannot_complete_or_fail_new_owner(client):
    jid = await enqueue_test_job(client)
    first = await runner.lease_one(jid)
    assert first and not await runner.lease_one(jid)
    async with db.system_tx() as conn:
        await conn.execute("UPDATE job_outbox SET lease_until=now()-interval '1 second' WHERE job_id=$1", jid)
    second = await runner.lease_one(jid)
    assert second and first["lease_token"] != second["lease_token"]
    assert not await runner.renew(first)
    await runner.complete(first)
    await runner.fail(first, RuntimeError("must not overwrite new owner"))
    async with db.system_tx() as conn:
        row = await conn.fetchrow("SELECT * FROM job_outbox WHERE job_id=$1", jid)
    assert row["status"] == "LEASED" and row["attempts"] == 2
    await runner.complete(second)


async def test_heartbeat_protects_long_job_and_duplicate_delivery(client, monkeypatch):
    jid = await enqueue_test_job(client)
    monkeypatch.setattr(get_settings(), "worker_lease_s", 0.15)
    started = asyncio.Event()
    calls = []

    async def handler(payload, job):
        calls.append(job["job_id"])
        started.set()
        await asyncio.sleep(0.4)

    monkeypatch.setitem(HANDLERS, "delivery.test", handler)
    task = asyncio.create_task(runner.run_one(jid))
    await started.wait()
    await asyncio.sleep(0.25)
    assert not await runner.run_one(jid)  # original duration exceeded; heartbeat still owns the lease
    assert await task
    assert calls == [jid]
    async with db.system_tx() as conn:
        assert await conn.fetchval("SELECT status FROM job_outbox WHERE job_id=$1", jid) == "DONE"


async def test_retry_does_not_persist_sensitive_exception_content(client):
    jid = await enqueue_test_job(client)
    job = await runner.lease_one(jid)
    await runner.fail(job, RuntimeError("private conversation transcript"))
    async with db.system_tx() as conn:
        row = await conn.fetchrow("SELECT status,last_error,lease_token,dispatched_at FROM job_outbox WHERE job_id=$1", jid)
        await conn.execute("UPDATE job_outbox SET status='DONE' WHERE job_id=$1", jid)
    assert row["last_error"] == "RuntimeError" and row["status"] == "READY"
    assert row["lease_token"] is None and row["dispatched_at"] is None


async def test_sqs_delivery_and_duplicate_message_run_only_once(client, monkeypatch):
    jid = await enqueue_test_job(client)
    calls, deleted = [], []

    async def handler(payload, job):
        calls.append(job["job_id"])

    class Broker:
        def receive_message(self, **kwargs):
            return {"Messages": [{"Body": json.dumps({"v": 1, "job_id": str(jid)}), "ReceiptHandle": "receipt"}]}

        def delete_message(self, **kwargs):
            deleted.append(kwargs["ReceiptHandle"])

    monkeypatch.setattr(sqs, "_client", Broker())
    monkeypatch.setitem(HANDLERS, "delivery.test", handler)
    assert await sqs.receive_one()
    assert await sqs.receive_one()
    assert calls == [jid] and deleted == ["receipt", "receipt"]


async def test_concurrent_first_use_of_idempotency_key_serializes(client):
    api = await signup(client)
    me = await api.me()
    body = {"space_id": me["spaces"][0]["space_id"], "context": "MEETING", "capture_source": "NONE",
            "processing_region": get_settings().processing_region}
    headers = api.h | {"Idempotency-Key": "concurrent-" + uuid.uuid4().hex}
    first, second = await asyncio.gather(*(client.post("/v1/sessions", json=body, headers=headers) for _ in range(2)))
    assert first.status_code == second.status_code == 201
    assert first.json()["session_id"] == second.json()["session_id"]
    assert "true" in (first.headers.get("idempotent-replay"), second.headers.get("idempotent-replay"))
