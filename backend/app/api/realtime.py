"""Audio ingress endpoint and the realtime WebSocket gateway (master 10, realtime_events_v1.json).

WebSocket protocol (/v1/sessions/{id}/realtime):
  client -> {"type":"auth","access_token":"...","cursor":<last acked sequence>}   (token never in the URL)
  server -> replay of every event with sequence > cursor, then live events as they commit
  client -> {"type":"ack","sequence":n}
  client -> {"type":"signal","user_speaking":true|false}
  client -> {"type":"voice.route_lost"}  (client has ALREADY hard-muted locally; server cancels pending voice)
  client -> {"type":"route", ...RouteIn fields}
Server tolerates duplicate/out-of-order client messages; events are idempotent by (session_id, sequence)."""
from __future__ import annotations

import asyncio
import json
import time
import uuid
from typing import Annotated

from fastapi import Path, APIRouter, Header, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse

from ..db import db, session_channel
from ..config import get_settings
from ..domain.capture_ranges import MAX_CAPTURE_MS, MAX_SEQUENCE
from ..domain.events import events_after
from ..domain.ingest import ingest_chunk
from ..domain.sessions import load_session, update_route, voice_route_lost
from ..errors import ApiError
from ..security.tokens import decode_access_token, decode_ingest_token

router = APIRouter(prefix="/v1", tags=["realtime"])


@router.put("/ingest/sessions/{session_id}/chunks/{sequence}")
async def put_chunk(session_id: uuid.UUID, sequence: Annotated[int, Path(ge=0, le=MAX_SEQUENCE)], request: Request,
                    authorization: str | None = Header(default=None),
                    x_sample_rate: int = Header(alias="X-Sample-Rate", ge=8000, le=48000),
                    x_capture_start_ms: int = Header(alias="X-Capture-Start-Ms", ge=0, le=MAX_CAPTURE_MS),
                    x_duration_ms: int = Header(alias="X-Duration-Ms", ge=1, le=10000),
                    x_sha256: str = Header(alias="X-Sha256", min_length=64, max_length=64, pattern="^[0-9a-fA-F]{64}$"),
                    x_device_id: str | None = Header(default=None, alias="X-Device-Id"),
                    x_encoding: str = Header(default="pcm_s16le", alias="X-Encoding")):
    if not authorization or not authorization.lower().startswith("bearer "):
        raise ApiError(401, "UNAUTHENTICATED", "Upload credential missing.")
    token = authorization.split(" ", 1)[1].strip()
    decode_ingest_token(token)  # reject unauthenticated uploads before buffering any content
    body = bytearray()
    async for piece in request.stream():
        if len(body) + len(piece) > get_settings().max_chunk_bytes:
            raise ApiError(413, "CHUNK_TOO_LARGE", "Audio chunk is too large.")
        body.extend(piece)
    ack = await ingest_chunk(token=token, session_id=session_id, sequence=sequence, body=bytes(body),
                             sample_rate=x_sample_rate, capture_start_ms=x_capture_start_ms, duration_ms=x_duration_ms,
                             sha256=x_sha256, device_id=x_device_id, encoding=x_encoding)
    status = ack.pop("_status")
    return JSONResponse(status_code=status, content=ack)


async def _authenticate(ws: WebSocket, session_id: uuid.UUID):
    try:
        msg = json.loads(await asyncio.wait_for(ws.receive_text(), timeout=10))
    except (asyncio.TimeoutError, json.JSONDecodeError):
        return None, 0
    if not isinstance(msg, dict) or msg.get("type") != "auth":
        return None, 0
    try:
        claims = decode_access_token(str(msg.get("access_token", "")))
    except ApiError:
        return None, 0
    async with db.system_tx() as conn:
        dev = await conn.fetchrow("SELECT revoked_at FROM devices WHERE device_id=$1 AND user_id=$2", claims.device_id, claims.user_id)
    if dev is None or dev["revoked_at"] is not None:
        return None, 0
    try:
        async with db.user_tx(claims.user_id) as conn:
            await load_session(conn, session_id)
    except ApiError:
        return None, 0
    try:
        cursor = int(msg.get("cursor") or 0)
        if not 0 <= cursor < 2**63:
            return None, 0
    except (ValueError, TypeError, OverflowError):
        return None, 0
    return claims, cursor


async def _credential_error(claims) -> str | None:
    if time.time() >= claims.expires_at:
        return "TOKEN_EXPIRED"
    async with db.system_tx() as conn:
        valid = await conn.fetchval("SELECT 1 FROM devices d JOIN users u USING(user_id)"
                                    " WHERE d.device_id=$1 AND d.user_id=$2 AND d.revoked_at IS NULL AND u.deleted_at IS NULL",
                                    claims.device_id, claims.user_id)
    return None if valid else "DEVICE_REVOKED"


@router.websocket("/sessions/{session_id}/realtime")
async def realtime(ws: WebSocket, session_id: uuid.UUID):
    await ws.accept()
    claims, cursor = await _authenticate(ws, session_id)
    if claims is None:
        await ws.send_json({"type": "error", "code": "UNAUTHENTICATED", "user_message": "Sign in to continue."})
        await ws.close(code=4401)
        return
    wake = asyncio.Event()

    def on_notify(*_args):
        wake.set()

    async with db.listen_conn() as lconn:
        await lconn.add_listener(session_channel(session_id), on_notify)
        device_channel = "msd_" + claims.device_id.hex
        await lconn.add_listener(device_channel, on_notify)
        sent = cursor

        async def authorized():
            code = await _credential_error(claims)
            if code:
                await ws.send_json({"type": "error", "code": code, "user_message": "Reconnect to continue this session."})
                return False
            return True

        async def pump():
            nonlocal sent
            while True:
                if not await authorized():
                    return
                async with db.user_tx(claims.user_id) as conn:
                    try:
                        await load_session(conn, session_id)
                    except ApiError:
                        await ws.send_json({"type": "error", "code": "SESSION_UNAVAILABLE", "user_message": "This session isn't available."})
                        return
                    evs = await events_after(conn, session_id, sent)
                for e in evs:
                    await ws.send_json(e)
                    sent = e["sequence"]
                wake.clear()
                try:
                    await asyncio.wait_for(wake.wait(), timeout=max(0.01, min(15, claims.expires_at - time.time())))
                except asyncio.TimeoutError:
                    await ws.send_json({"type": "ping", "server_cursor": sent})

        async def recv():
            while True:
                raw = await ws.receive_text()
                if not await authorized():
                    return
                try:
                    m = json.loads(raw)
                except json.JSONDecodeError:
                    continue
                if not isinstance(m, dict):
                    continue
                t = m.get("type")
                async with db.user_tx(claims.user_id) as conn:
                    try:
                        s = await load_session(conn, session_id)
                    except ApiError:
                        return
                    if t == "ack":
                        await conn.execute("UPDATE session_runtime SET last_client_ack_seq=GREATEST(last_client_ack_seq,$2) WHERE session_id=$1",
                                           session_id, int(m.get("sequence") or 0))
                    elif t == "signal":
                        await conn.execute("UPDATE session_runtime SET user_speaking=$2, user_speaking_at=now() WHERE session_id=$1",
                                           session_id, bool(m.get("user_speaking")))
                    elif t == "voice.route_lost":
                        await voice_route_lost(conn, s, "CLIENT_REPORTED")
                    elif t == "route":
                        await update_route(conn, s, input_route=m.get("input_route"), output_route=m.get("output_route"),
                                           private_route_verified=bool(m.get("private_route_verified")),
                                           device_name=m.get("device_name"), audio_quality=m.get("audio_quality"))

        tasks = [asyncio.create_task(pump()), asyncio.create_task(recv())]
        try:
            done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
            for t in pending:
                t.cancel()
            for t in done:
                exc = t.exception()
                if exc and not isinstance(exc, WebSocketDisconnect):
                    raise exc
        except WebSocketDisconnect:
            pass
        finally:
            for t in tasks:
                t.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
            try:
                await lconn.remove_listener(session_channel(session_id), on_notify)
                await lconn.remove_listener(device_channel, on_notify)
            except Exception:  # noqa: BLE001
                pass
            try:
                await ws.close()
            except (RuntimeError, WebSocketDisconnect):
                pass
