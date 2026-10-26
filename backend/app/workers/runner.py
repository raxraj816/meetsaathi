"""Durable job runner: Postgres job model with leases, retries with backoff and a dead-letter state (master 8.2).
Workers are separate from API processes in production (`python -m app.workers.runner`); dev may run inline."""
from __future__ import annotations

import asyncio
import datetime as dt
import logging
import time
import uuid

from ..config import get_settings
from ..db import db
from .. import telemetry

log = logging.getLogger("meetsaathi.worker")


class Reschedule(Exception):
    """Not a failure: try again later without consuming an attempt (e.g. waiting for spooled uploads)."""

    def __init__(self, delay_s: float):
        super().__init__(f"reschedule in {delay_s}s")
        self.delay_s = delay_s


async def lease_one(job_id: uuid.UUID | None = None) -> dict | None:
    async with db.system_tx() as conn:
        row = await conn.fetchrow(
            "SELECT * FROM job_outbox WHERE ((status='READY' AND available_at <= now()) OR (status='LEASED' AND lease_until < now()))"
            " AND ($1::uuid IS NULL OR job_id=$1) ORDER BY available_at LIMIT 1 FOR UPDATE SKIP LOCKED", job_id)
        if row is None:
            return None
        token = uuid.uuid4()
        await conn.execute("UPDATE job_outbox SET status='LEASED', lease_until=now() + make_interval(secs=>$2), attempts=attempts+1, lease_token=$3"
                           " WHERE job_id=$1", row["job_id"], float(get_settings().worker_lease_s), token)
        return dict(row) | {"attempts": row["attempts"] + 1, "lease_token": token}


async def complete(job: dict) -> None:
    async with db.system_tx() as conn:
        await conn.execute("UPDATE job_outbox SET status='DONE', completed_at=now(), lease_until=NULL, lease_token=NULL"
                           " WHERE job_id=$1 AND lease_token=$2 AND status='LEASED'", job["job_id"], job["lease_token"])


async def renew(job: dict) -> bool:
    async with db.system_tx() as conn:
        return bool(await conn.fetchval("UPDATE job_outbox SET lease_until=now()+make_interval(secs=>$3)"
                                       " WHERE job_id=$1 AND lease_token=$2 AND status='LEASED' AND lease_until>now() RETURNING job_id",
                                       job["job_id"], job["lease_token"], float(get_settings().worker_lease_s)))


async def fail(job: dict, err: BaseException) -> None:
    async with db.system_tx() as conn:
        owned = await conn.fetchval("SELECT job_id FROM job_outbox WHERE job_id=$1 AND lease_token=$2 AND status='LEASED' FOR UPDATE",
                                    job["job_id"], job["lease_token"])
        if not owned:
            return
        if isinstance(err, Reschedule):
            await conn.execute("UPDATE job_outbox SET status='READY', attempts=attempts-1, lease_until=NULL, lease_token=NULL, dispatched_at=NULL,"
                               " available_at=now()+make_interval(secs=>$2) WHERE job_id=$1", job["job_id"], float(err.delay_s))
            return
        msg = type(err).__name__  # provider errors may contain conversation content; persist metadata only
        if job["attempts"] >= job["max_attempts"]:
            await conn.execute("UPDATE job_outbox SET status='DEAD', last_error=$2, lease_until=NULL, lease_token=NULL WHERE job_id=$1", job["job_id"], msg)
            dead = True
        else:
            backoff = min(300.0, 2.0 ** job["attempts"])
            await conn.execute("UPDATE job_outbox SET status='READY', last_error=$2, lease_until=NULL, lease_token=NULL, dispatched_at=NULL,"
                               " available_at=now()+make_interval(secs=>$3) WHERE job_id=$1", job["job_id"], msg, backoff)
            dead = False
    if dead:
        from .jobs import on_dead

        await on_dead(job, msg)


async def run_one(job_id: uuid.UUID | None = None) -> bool:
    from .jobs import HANDLERS

    job = await lease_one(job_id)
    if job is None:
        return False
    handler = HANDLERS.get(job["kind"])
    task = None
    heartbeat = None
    started = time.monotonic()
    outcome = "success"
    try:
        if handler is None:
            raise RuntimeError(f"no handler for {job['kind']}")
        task = asyncio.create_task(handler(job["payload"], job))

        async def keep_lease():
            while True:
                await asyncio.sleep(get_settings().worker_lease_s / 3)
                try:
                    owned = await renew(job)
                except Exception:
                    owned = False
                if not owned:
                    task.cancel()
                    return

        heartbeat = asyncio.create_task(keep_lease())
        await task
        await complete(job)
    except asyncio.CancelledError:
        outcome = "lease_lost"
        if asyncio.current_task().cancelling():
            raise
        # A lease heartbeat cancelled only the handler after losing ownership. The new owner is
        # responsible for the job; don't mutate its retry count or terminate the worker process.
        log.warning("job lease lost kind=%s", job["kind"])
    except Exception as e:  # noqa: BLE001 - every failure is recorded and retried or dead-lettered
        outcome = "rescheduled" if isinstance(e, Reschedule) else "failure"
        if not isinstance(e, Reschedule):
            log.warning("job %s %s failed (attempt %s): %s", job["kind"], job["job_id"], job["attempts"], type(e).__name__)
        await fail(job, e)
    finally:
        attrs = {"job.kind": job["kind"], "job.outcome": outcome}
        telemetry.job_duration.record(time.monotonic() - started, attrs)
        telemetry.job_count.add(1, attrs)
        if task and not task.done():
            task.cancel()
        if heartbeat:
            heartbeat.cancel()
            try:
                await heartbeat
            except asyncio.CancelledError:
                pass
    return True


async def drain(max_jobs: int = 1000) -> int:
    """Process jobs until the queue has nothing runnable now. Used by tests and the inline dev worker."""
    n = 0
    while n < max_jobs and await run_one():
        n += 1
    return n


async def schedule_periodic() -> None:
    minute = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%d%H%M")
    from ..domain import ops

    async with db.system_tx() as conn:
        t = await conn.fetchrow("SELECT tenant_id, space_id FROM spaces LIMIT 1")
        if t is None:
            return
        await ops.enqueue(conn, tenant_id=t["tenant_id"], space_id=t["space_id"], session_id=None, kind="maintenance.sweep",
                          payload={}, key=f"sweep:{minute}", max_attempts=1)


async def loop(stop: asyncio.Event | None = None) -> None:
    s = get_settings()

    async def maintenance():
        last_sweep = 0.0
        while stop is None or not stop.is_set():
            try:
                now = asyncio.get_running_loop().time()
                if now - last_sweep > 60:
                    await schedule_periodic()
                    last_sweep = now
                if s.queue_backend == "sqs":
                    from .sqs import dispatch

                    await dispatch()
            except Exception as e:
                log.error("job publication error type=%s", type(e).__name__)
            await asyncio.sleep(s.worker_poll_interval_s)

    publisher = asyncio.create_task(maintenance())
    from ..speech.streaming import supervise

    speech = asyncio.create_task(supervise(stop))
    try:
        while stop is None or not stop.is_set():
            try:
                if s.queue_backend == "sqs":
                    from .sqs import receive_one

                    worked = await receive_one()
                else:
                    worked = await run_one()
            except Exception as e:  # noqa: BLE001
                log.error("worker loop error type=%s", type(e).__name__)
                worked = False
            if not worked:
                await asyncio.sleep(s.worker_poll_interval_s)
    finally:
        publisher.cancel()
        speech.cancel()
        await asyncio.gather(publisher, speech, return_exceptions=True)


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    telemetry.configure()

    async def _run():
        await db.connect()
        try:
            await loop()
        finally:
            await db.close()
            telemetry.shutdown()

    asyncio.run(_run())


if __name__ == "__main__":
    main()

_ = uuid
