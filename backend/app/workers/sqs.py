"""SQS delivery backed by a transactional PostgreSQL outbox.

Only job IDs leave the database; no transcript, user identifiers, or payloads go to SQS. Publication
is at least once, after the enqueue transaction commits. Database leases fence duplicate deliveries.
Periodic re-publication recovers a lost notification or expired worker lease. A broker outage never
loses a committed job. READY/LEASED/DONE/DEAD and retry budgets remain authoritative in PostgreSQL.
"""
from __future__ import annotations

import asyncio
import json
import uuid

from ..aws import client as aws_client
from ..config import get_settings
from ..db import db

_client = None


def get_client():
    global _client
    if _client is None:
        _client = aws_client("sqs", timeout=15)
    return _client


async def dispatch(limit: int = 10) -> int:
    count = 0
    async with db.system_tx() as conn:
        rows = await conn.fetch(
            "SELECT job_id FROM job_outbox WHERE ((status='READY' AND available_at<=now()) OR (status='LEASED' AND lease_until<now()))"
            " AND (dispatched_at IS NULL OR dispatched_at<now()-interval '120 seconds')"
            " ORDER BY available_at LIMIT $1 FOR UPDATE SKIP LOCKED", limit)
        for row in rows:
            await asyncio.to_thread(get_client().send_message, QueueUrl=get_settings().sqs_queue_url,
                                    MessageBody=json.dumps({"v": 1, "job_id": str(row["job_id"])}))
            await conn.execute("UPDATE job_outbox SET dispatched_at=now() WHERE job_id=$1", row["job_id"])
            count += 1
    return count


async def receive_one() -> bool:
    from .runner import run_one

    s, client = get_settings(), get_client()
    response = await asyncio.to_thread(client.receive_message, QueueUrl=s.sqs_queue_url, MaxNumberOfMessages=1,
                                       WaitTimeSeconds=5, VisibilityTimeout=s.worker_lease_s)
    messages = response.get("Messages", [])
    if not messages:
        return False
    message = messages[0]
    try:
        body = json.loads(message["Body"])
        if body["v"] != 1:
            return True  # invalid messages redrive to the broker DLQ for investigation
        job_id = uuid.UUID(body["job_id"])
    except (ValueError, KeyError, TypeError):
        return True
    worked = await run_one(job_id)
    if worked:
        await asyncio.to_thread(client.delete_message, QueueUrl=s.sqs_queue_url, ReceiptHandle=message["ReceiptHandle"])
    else:
        async with db.system_tx() as conn:
            status = await conn.fetchval("SELECT status FROM job_outbox WHERE job_id=$1", job_id)
        if status is None or status in ("DONE", "DEAD"):
            await asyncio.to_thread(client.delete_message, QueueUrl=s.sqs_queue_url, ReceiptHandle=message["ReceiptHandle"])
    return True
