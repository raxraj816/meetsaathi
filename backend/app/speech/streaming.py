"""Fenced, recoverable live speech actors, independent of the ordinary sequential job worker.

Only acknowledged encrypted audio is read. Provider-final evidence and a capture-clock replay
watermark commit in one transaction. A crashed stream replays precisely the uncommitted suffix,
including the remainder of a partly consumed chunk. Draft captions never become utterances.
"""
from __future__ import annotations

import asyncio
import logging
import uuid
from contextlib import suppress

from ..config import get_settings
from ..db import db
from ..domain.events import append_event
from ..domain.capture_ranges import MAX_CAPTURE_MS
from ..domain.sessions import status_event
from ..storage import get_store
from .adapters import SpeechUnavailable, get_asr, get_diarizer
from .aligner import align, in_playback
from .audio import pcm_to_wav, rms_dbfs, speech_likely
from .pipeline import LIVE_SESSION_STATES, persist_aligned, persist_audio_quality

log = logging.getLogger("meetsaathi.speech.stream")


class LeaseLost(SpeechUnavailable):
    pass


async def locked_source(conn, sid, token):
    s = await conn.fetchrow("SELECT * FROM sessions WHERE session_id=$1 FOR UPDATE", sid)
    rt = await conn.fetchrow("SELECT *, asr_stream_lease_until>clock_timestamp() AS lease_live"
                             " FROM session_runtime WHERE session_id=$1", sid)
    if (not s or s["deleted_at"] or s["audio_deleted_at"] or not s["capture_permitted"]
            or s["state"] not in LIVE_SESSION_STATES or not rt or rt["asr_stream_token"] != token or not rt["lease_live"]):
        raise LeaseLost("Speech source or stream lease no longer valid")
    return dict(s), dict(rt)


def through_sequence(session, rt):
    # Permanent upload gaps may be crossed only after finalization's existing drain deadline.
    import datetime as dt
    past_drain = (session["state"] == "FINALIZING" and session["drain_deadline"] is not None
                  and session["drain_deadline"] <= dt.datetime.now(dt.timezone.utc))
    return int(rt["max_sequence"] if past_drain else rt["received_through_sequence"])


async def claim(sid):
    token = uuid.uuid4()
    async with db.system_tx() as conn:
        s = await conn.fetchrow("SELECT * FROM sessions WHERE session_id=$1 FOR UPDATE", sid)
        if (not s or s["deleted_at"] or s["audio_deleted_at"] or not s["capture_permitted"]
                or s["state"] not in LIVE_SESSION_STATES):
            return None
        rt = await conn.fetchrow("SELECT *, asr_stream_lease_until>clock_timestamp() AS lease_live,"
                                 " asr_retry_at>clock_timestamp() AS retry_later FROM session_runtime WHERE session_id=$1", sid)
        if rt["lease_live"] or rt["retry_later"] or through_sequence(s, rt) <= s["asr_cursor_sequence"]:
            return None
        if rt["asr_stream_token"]:
            await append_event(conn, dict(s), "transcript.preview_clear", {
                "run_id": str(rt["asr_stream_token"]), "reason": "STREAM_RECOVERED"})
        await conn.execute("UPDATE session_runtime SET asr_stream_token=$2,"
                           " asr_stream_lease_until=clock_timestamp()+$3*interval '1 second' WHERE session_id=$1",
                           sid, token, get_settings().worker_lease_s)
        return token


async def pending(sid, *, fail_on_exhaustion=False):
    """Finalization must wait for a connection's final responses, even if its chunk cursor is caught up."""
    async with db.system_tx() as conn:
        r = await conn.fetchrow("SELECT s.*, r.received_through_sequence, r.max_sequence, r.asr_failures,"
                                " r.asr_stream_lease_until>clock_timestamp() AS lease_live FROM sessions s"
                                " JOIN session_runtime r USING(session_id) WHERE s.session_id=$1", sid)
        waiting = bool(r and not r["deleted_at"] and not r["audio_deleted_at"] and r["capture_permitted"]
                    and r["state"] in LIVE_SESSION_STATES
                    and (r["lease_live"] or through_sequence(r, r) > r["asr_cursor_sequence"]))
        if (waiting and fail_on_exhaustion and not r["lease_live"]
                and r["asr_failures"] >= get_settings().asr_stream_retry_budget):
            raise SpeechUnavailable("Live speech retry budget exhausted")
        return waiting


async def advance(conn, session, token, end_ms, cursor):
    # Caller holds the source lock and has validated its live fencing token.
    await conn.execute("UPDATE session_runtime SET asr_committed_ms=GREATEST(asr_committed_ms,$3), asr_failures=0"
                       " WHERE session_id=$1 AND asr_stream_token=$2", session["session_id"], token, end_ms)
    await conn.execute("UPDATE sessions SET asr_cursor_sequence=GREATEST(asr_cursor_sequence,$2),"
                       " transcript_status='LIVE' WHERE session_id=$1", session["session_id"], cursor)
    if session["transcript_status"] == "DELAYED":
        await status_event(conn, session, "CAPTIONS_RESUMED", "Captions are updating again.", "info")


class StreamActor:
    def __init__(self, sid, token):
        self.sid, self.token = sid, token
        self.audio = []
        self.last = None
        self.committed = 0
        self.started = asyncio.get_running_loop().time()
        self.rate = None
        self.offset = None
        self.language = None
        self.quality_pcm = bytearray()
        self.quality_rate = None
        self.quality_since_check = 0

    async def packets(self):
        idle_since = asyncio.get_running_loop().time()
        next_seq = None
        while asyncio.get_running_loop().time() - self.started < get_settings().asr_stream_max_s:
            async with db.system_tx() as conn:
                s, rt = await locked_source(conn, self.sid, self.token)
                self.committed = max(self.committed, int(rt["asr_committed_ms"]))
                if next_seq is None:
                    next_seq = int(s["asr_cursor_sequence"]) + 1
                chunks = await conn.fetch("SELECT * FROM audio_chunks WHERE session_id=$1 AND ingest_status='ACKED'"
                                          " AND sequence_no BETWEEN $2 AND $3 ORDER BY sequence_no LIMIT 4",
                                          self.sid, next_seq, through_sequence(s, rt))
            if not chunks:
                if (s["state"] != "RECORDING" or
                        asyncio.get_running_loop().time() - idle_since >= get_settings().asr_stream_idle_s):
                    return
                await asyncio.sleep(min(0.25, get_settings().asr_stream_idle_s))
                continue
            for row in chunks:
                c = dict(row)
                if self.last and (c["sequence_no"] != self.last["sequence_no"] + 1
                                  or c["sample_rate_hz"] != self.rate
                                  or abs(c["capture_start_ms"] - self.last["end_ms"]) > 1):
                    return  # drain this connection before a capture gap, rate change or sequence gap
                pcm = await asyncio.to_thread(get_store().get, s["tenant_id"], c["encrypted_object_key"])
                start = max(c["capture_start_ms"], self.committed)
                skip = max(0, start - c["capture_start_ms"]) * c["sample_rate_hz"] // 1000 * 2
                pcm = pcm[skip:]
                c.update(start_ms=start, end_ms=c["capture_start_ms"] + c["duration_ms"], pcm=pcm)
                next_seq = c["sequence_no"] + 1
                # Preserve source-quality warnings even when silence opens no provider connection,
                # or the recognizer returns no words. Six seconds avoids warnings for short pauses.
                if self.quality_rate != c["sample_rate_hz"]:
                    self.quality_rate = c["sample_rate_hz"]
                    self.quality_pcm.clear()
                    self.quality_since_check = 0
                limit = self.quality_rate * 2 * 6
                self.quality_pcm.extend(pcm)
                del self.quality_pcm[:-limit]
                self.quality_since_check += len(pcm)
                if self.quality_since_check >= limit:
                    async with db.system_tx() as conn:
                        current, _ = await locked_source(conn, self.sid, self.token)
                        await persist_audio_quality(conn, current, rms_dbfs(self.quality_pcm))
                    self.quality_since_check = 0
                if self.rate is None and (not pcm or not speech_likely(pcm)):
                    # Initial silence needs no provider connection. Persist its consumption under the lease.
                    async with db.system_tx() as conn:
                        current, _ = await locked_source(conn, self.sid, self.token)
                        await advance(conn, current, self.token, c["end_ms"], c["sequence_no"])
                    continue
                if self.rate is None:
                    self.rate, self.offset, self.language = c["sample_rate_hz"], start, s["language"]
                self.audio.append(c)
                self.last = c
                idle_since = asyncio.get_running_loop().time()
                yield pcm

    def audio_span(self, start, end):
        parts, sources = [], []
        for c in self.audio:
            a, b = max(start, c["start_ms"]), min(end, c["end_ms"])
            if b > a:
                parts.append(c["pcm"][(a-c["start_ms"])*self.rate//1000*2:(b-c["start_ms"])*self.rate//1000*2])
                sources.append(c)
        return b"".join(parts), sources

    async def result(self, result):
        seg = result.segment
        if not self.last or seg.start_ms < self.offset or seg.end_ms > min(MAX_CAPTURE_MS, self.last["end_ms"] + 1):
            raise SpeechUnavailable("Provider result outside submitted audio")
        if seg.end_ms <= self.committed:
            return  # duplicate final ID/interval within this stream
        if seg.start_ms < self.committed:
            raise SpeechUnavailable("Provider final intervals overlap committed evidence")
        pcm, sources = self.audio_span(seg.start_ms, seg.end_ms)
        audible = speech_likely(pcm)
        diar = None
        if not result.is_partial and audible and get_diarizer().available():
            try:
                diar = await get_diarizer().diarize(pcm_to_wav(pcm, self.rate), session_key=str(self.sid), offset_ms=seg.start_ms)
            except SpeechUnavailable:
                pass  # explicitly unassigned; no guessed speaker
        async with db.system_tx() as conn:
            s, rt = await locked_source(conn, self.sid, self.token)
            if result.is_partial:
                if audible and not in_playback(seg, rt["tts_windows"] or []):
                    await conn.execute("UPDATE sessions SET transcript_status='LIVE' WHERE session_id=$1", self.sid)
                    if s["transcript_status"] == "DELAYED":
                        await status_event(conn, s, "CAPTIONS_RESUMED", "Captions are updating again.", "info")
                    await append_event(conn, s, "transcript.preview", {
                        "run_id": str(self.token), "preview_id": result.result_id,
                        "start_ms": seg.start_ms, "end_ms": seg.end_ms, "text": seg.text,
                        "is_final": False, "evidence": False})
                return
            aligned = align([seg] if audible else [], diar, rt["tts_windows"] or [])
            await persist_aligned(conn, s, aligned, get_asr().version, diar, sources[0], sources[-1],
                                  rms_dbfs(pcm), f"{self.token}:{result.result_id}")
            cursor = max([s["asr_cursor_sequence"]] + [c["sequence_no"] for c in self.audio if c["end_ms"] <= seg.end_ms])
            await advance(conn, s, self.token, seg.end_ms, cursor)
            await append_event(conn, s, "transcript.preview_clear", {
                "run_id": str(self.token), "preview_id": result.result_id, "reason": "PROVIDER_FINAL"})
        self.committed = seg.end_ms
        self.audio = [c for c in self.audio if c["end_ms"] > self.committed]

    async def run(self):
        packets = self.packets()
        try:
            # Wait for initial speech before opening a billable connection.
            first = await anext(packets, None)
            if first is None:
                return

            async def source():
                yield first
                async for packet in packets:
                    yield packet

            finals = asyncio.Queue(maxsize=32)

            async def receive(result):
                if result.is_partial:
                    await self.result(result)
                else:
                    await finals.put(result)

            async def persist_finals():
                while (result := await finals.get()) is not None:
                    await self.result(result)

            async def transport():
                await get_asr().stream(source(), sample_rate=self.rate, offset_ms=self.offset,
                                       language=self.language, on_result=receive)
                await finals.put(None)

            # Slow diarization must not block receiving the next draft. The bounded FIFO preserves
            # final-result order and backpressures only when processing falls far behind.
            async with asyncio.TaskGroup() as tasks:
                tasks.create_task(persist_finals())
                tasks.create_task(transport())
            # A clean provider drain also commits trailing silence. Exceptions never advance here.
            async with db.system_tx() as conn:
                s, _ = await locked_source(conn, self.sid, self.token)
                await advance(conn, s, self.token, self.last["end_ms"], self.last["sequence_no"])
        finally:
            await packets.aclose()


async def run_session(sid, token=None):
    token = token or await claim(sid)
    if token is None:
        return False
    task = asyncio.create_task(StreamActor(sid, token).run())

    async def renew():
        while True:
            await asyncio.sleep(get_settings().worker_lease_s / 3)
            async with db.system_tx() as conn:
                await locked_source(conn, sid, token)
                await conn.execute("UPDATE session_runtime SET asr_stream_lease_until=clock_timestamp()+$3*interval '1 second'"
                                   " WHERE session_id=$1 AND asr_stream_token=$2", sid, token, get_settings().worker_lease_s)

    renewal = asyncio.create_task(renew())
    failed = False
    try:
        done, _ = await asyncio.wait((task, renewal), return_when=asyncio.FIRST_COMPLETED)
        for t in done:
            await t
    except asyncio.CancelledError:
        raise
    except Exception as e:
        failed = True
        log.warning("speech stream interrupted type=%s", type(e).__name__)
    finally:
        task.cancel()
        renewal.cancel()
        await asyncio.gather(task, renewal, return_exceptions=True)
        async with db.system_tx() as conn:
            # Do not let an expired owner clear a replacement owner's preview or retry schedule.
            s = await conn.fetchrow("SELECT * FROM sessions WHERE session_id=$1 FOR UPDATE", sid)
            rt = await conn.fetchrow("SELECT * FROM session_runtime WHERE session_id=$1", sid)
            if s and rt and rt["asr_stream_token"] == token:
                if not s["deleted_at"] and not s["audio_deleted_at"] and s["capture_permitted"]:
                    await append_event(conn, dict(s), "transcript.preview_clear", {"run_id": str(token), "reason": "STREAM_CLOSED"})
                    if failed and s["transcript_status"] != "DELAYED":
                        await conn.execute("UPDATE sessions SET transcript_status='DELAYED' WHERE session_id=$1", sid)
                        message = ("Captions delayed. Recording continues." if s["state"] in ("STARTING", "RECORDING")
                                   else "Captions delayed. Saved audio will be retried.")
                        await status_event(conn, dict(s), "CAPTIONS_DELAYED", message, "warning")
                delay = min(60, 2 ** min(int(rt["asr_failures"]) + 1, 6)) if failed else 0
                await conn.execute("UPDATE session_runtime SET asr_stream_token=NULL, asr_stream_lease_until=NULL,"
                                   " asr_retry_at=clock_timestamp()+$3*interval '1 second', asr_failures=$4"
                                   " WHERE session_id=$1 AND asr_stream_token=$2", sid, token, delay,
                                   int(rt["asr_failures"]) + 1 if failed else 0)
    return True


async def supervise(stop=None):
    active = {}
    try:
        while stop is None or not stop.is_set():
            for sid, task in list(active.items()):
                if task.done():
                    with suppress(Exception):
                        task.result()
                    del active[sid]
            try:
                asr = get_asr()
                if asr.supports_streaming and asr.available() and len(active) < get_settings().asr_stream_concurrency:
                    async with db.system_tx() as conn:
                        rows = await conn.fetch("SELECT s.session_id FROM sessions s JOIN session_runtime r USING(session_id)"
                            " WHERE s.deleted_at IS NULL AND s.audio_deleted_at IS NULL AND s.capture_permitted"
                            " AND s.state=ANY($1::session_state[])"
                            " AND (r.asr_stream_lease_until IS NULL OR r.asr_stream_lease_until<clock_timestamp())"
                            " AND (r.asr_retry_at IS NULL OR r.asr_retry_at<=clock_timestamp())"
                            " AND s.asr_cursor_sequence<CASE WHEN s.state='FINALIZING' AND s.drain_deadline<=clock_timestamp()"
                            " THEN r.max_sequence ELSE r.received_through_sequence END"
                            " ORDER BY COALESCE(r.asr_retry_at,s.created_at) LIMIT $2", list(LIVE_SESSION_STATES),
                            get_settings().asr_stream_concurrency * 4)
                    for r in rows:
                        sid = r["session_id"]
                        if sid not in active and (token := await claim(sid)):
                            active[sid] = asyncio.create_task(run_session(sid, token))
                        if len(active) >= get_settings().asr_stream_concurrency:
                            break
            except Exception as e:
                log.warning("speech supervisor error type=%s", type(e).__name__)
            await asyncio.sleep(get_settings().worker_poll_interval_s)
    finally:
        for task in active.values():
            task.cancel()
        await asyncio.gather(*active.values(), return_exceptions=True)
