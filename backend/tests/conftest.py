"""Test harness. Uses a real PostgreSQL (pgvector) with the production migrations and RLS roles.
Speech and reasoning providers are replaced ONLY here, by explicit test doubles (master task 5:
"fake explicit test audio source only in unit tests")."""
from __future__ import annotations

import asyncio
import hashlib
import json
import os
import struct
import tempfile
import uuid

import pytest
import pytest_asyncio

os.environ.setdefault("MS_ENV", "test")
os.environ["MS_RUN_INLINE_WORKER"] = "false"
os.environ["MS_OBJECT_STORE_DIR"] = tempfile.mkdtemp(prefix="ms-objects-")
os.environ.pop("MS_ANTHROPIC_API_KEY", None)
os.environ.pop("MS_ASR_BASE_URL", None)

import httpx  # noqa: E402

from app.config import get_settings  # noqa: E402
from app.db import db  # noqa: E402
from app.intelligence import reasoner as reasoner_mod  # noqa: E402
from app.intelligence.reasoner import Reasoner, ReasonerResult  # noqa: E402
from app.main import create_app  # noqa: E402
from app.memory import embeddings  # noqa: E402
from app.migrate import migrate  # noqa: E402
from app.speech import adapters  # noqa: E402
from app.speech.adapters import AsrEngine, AsrSegment, DiarizationResult, Diarizer, SpeakerTurn  # noqa: E402
from app.storage import reset_store  # noqa: E402
from app.workers.runner import drain  # noqa: E402

SAMPLE_RATE = 16000


def tone_pcm(ms: int = 1000, amplitude: int = 6000, freq: float = 220.0) -> bytes:
    import math

    n = SAMPLE_RATE * ms // 1000
    return struct.pack(f"<{n}h", *(int(amplitude * math.sin(2 * math.pi * freq * i / SAMPLE_RATE)) for i in range(n)))


def silence_pcm(ms: int = 1000) -> bytes:
    return b"\x00\x00" * (SAMPLE_RATE * ms // 1000)


class ScriptedAsr(AsrEngine):
    """Test double: returns the next scripted line for each window that contains signal."""
    name = "test-asr"
    version = "test-asr:1"
    region = "ap-south-1"

    def __init__(self, lines: list[str] | None = None, confidence: float = 0.9):
        self.lines = list(lines or [])
        self.confidence = confidence
        self.calls = 0

    def available(self) -> bool:
        return True

    async def transcribe(self, wav: bytes, *, offset_ms: int, language: str | None):
        self.calls += 1
        if not self.lines:
            return []
        text = self.lines.pop(0)
        import io
        import wave
        with wave.open(io.BytesIO(wav), "rb") as audio:
            duration = audio.getnframes() * 1000 // audio.getframerate()
        return [AsrSegment(offset_ms + min(100, duration-1), offset_ms + min(2900, duration), text, self.confidence, "en", [])]


class AlternatingDiarizer(Diarizer):
    version = "test-diarizer:1"
    region = "ap-south-1"
    max_supported = 8

    def __init__(self):
        self.n = 0

    def available(self) -> bool:
        return True

    async def diarize(self, wav: bytes, *, session_key: str, offset_ms: int):
        self.n += 1
        spk = "spk_0" if self.n % 2 else "spk_1"
        return DiarizationResult([SpeakerTurn(spk, offset_ms, offset_ms + 6000, 0.9)], self.version, 2, 8)


class FakeReasoner(Reasoner):
    """Test double. `responder(task, data_blocks) -> dict` produces schema-shaped JSON."""

    def __init__(self, responder):
        self.model = "test-reasoner"
        self.region = "ap-south-1"
        self._client = None
        self.responder = responder
        self.calls: list[tuple[str, dict]] = []

    def available(self) -> bool:
        return True

    async def structured(self, *, task, system_extra, data_blocks, instruction, schema, effort="low", max_tokens=4000):
        self.calls.append((task, data_blocks))
        data = self.responder(task, data_blocks)
        if isinstance(data, Exception):
            raise data
        return ReasonerResult(data, self.model, 10, 10)


def handles(data_blocks) -> list[str]:
    return [e["id"] for e in data_blocks.get("untrusted_conversation_data", []) if isinstance(e, dict) and "id" in e]


def default_responder(task, blocks):
    ids = handles(blocks)
    if task == "insight.candidates":
        return {"candidates": [{"kind": "CLARIFY", "short_text": "Ask whether ordering must be global or per customer before choosing partitions.",
                                "long_text": "The team discussed ordering without stating its scope.", "rationale": "Ordering scope unresolved.",
                                "evidence_ids": ids[-1:], "source_kind": "AI_ANALYSIS", "relevance": 0.9, "timeliness": 0.9,
                                "actionability": 0.9, "novelty": 0.9, "sensitivity": "NORMAL", "risk_level": "LOW",
                                "voice_text": "Clarify ordering scope."}]}
    if task == "ask.remember":
        return {"statements": [{"text": "The team proposed per-customer partition keys.", "evidence_ids": ids[:1]},
                               {"text": "This invented claim cites nothing real.", "evidence_ids": ["E999"]}],
                "insufficient_evidence": False, "uncertainty": ""}
    if task in ("ask.think", "ask.learn", "ask.prepare"):
        return {"context_statements": [{"text": "Partitioning was discussed.", "evidence_ids": ids[:1]}],
                "analysis": "Consider idempotent consumers.", "alternatives": ["Global ordering via single partition"],
                "unknowns": ["Throughput target"], "knowledge_kind": "AI_ANALYSIS", "check_question": "Why does ordering matter?",
                "proposed_actions": [{"kind": "FOLLOW_UP_QUESTION", "text": "Ask who owns recovery testing."}], "uncertainty": ""}
    if task == "extract":
        return {"items": [{"kind": "DECISION", "text": "Use per-customer partition keys", "detail": "", "evidence_ids": ids[:1],
                           "decision_status": "ACCEPTED", "status_evidence_ids": [], "owner_spoken": "", "owner_evidence_ids": [], "due_spoken": ""},
                          {"kind": "ACTION", "text": "Benchmark regional failover", "detail": "", "evidence_ids": ids[1:2] or ids[:1],
                           "decision_status": "NONE", "status_evidence_ids": [], "owner_spoken": "Alex", "owner_evidence_ids": [], "due_spoken": "Friday"},
                          {"kind": "QUESTION", "text": "What is the RPO target?", "detail": "", "evidence_ids": ["E999"],
                           "decision_status": "NONE", "status_evidence_ids": [], "owner_spoken": "", "owner_evidence_ids": [], "due_spoken": ""}],
                "recap": [{"text": "The team discussed partitioning.", "evidence_ids": ids[:1]}, {"text": "Unsourced line.", "evidence_ids": []}],
                "topics": [{"title": "Partitioning", "evidence_ids": ids[:1]}], "suggested_next_steps": ["Confirm owner"],
                "visual_content_missing": False}
    if task == "learning.explain":
        return {"concept": "Memoization", "one_line": "Memoization stores answers to repeated subproblems.", "example": "Cache fib(n).",
                "why_it_matters": "Avoids recomputation.", "lecture_statements": [{"text": "Reuse stored results.", "evidence_ids": ids[:1]}],
                "visual_content_missing": True, "captured_clearly": True}
    if task == "learning.practice":
        return {"items": [{"concept": "Memoization", "prompt": "Why does memoization speed up recursion?", "rubric": "Stores repeated results.",
                           "kind": "FREE_RECALL", "evidence_ids": ids[:1]}, {"concept": "Bogus", "prompt": "Uncited?", "rubric": "x",
                           "kind": "FREE_RECALL", "evidence_ids": []}]}
    if task == "learning.grade":
        return {"verdict": "CORRECT", "feedback": "Right: results are cached.", "missing_points": [], "next_step": "Explain when it doesn't help."}
    if task == "interview.first_question":
        return {"kind": "QUESTION", "text": "Design a payments fraud alerting system. What do you clarify first?", "reason": "opening"}
    if task == "interview.next_turn":
        return {"kind": "FOLLOWUP", "text": "You mentioned Kafka. What happens if a consumer processes an event twice?", "reason": "probe"}
    if task == "interview.hint":
        return {"hint": "Think about idempotency keys."}
    if task == "interview.debrief":
        return {"dimensions": [{"name": "Problem framing", "observation": "Clarified scale first.", "evidence_turn_ids": ["T2"],
                                "repair": "State latency targets.", "drill": "Requirements drill", "level": "STRENGTH"}],
                "strengths": ["Clear structure", "Considered failure"], "improvements": ["Quantify RTO/RPO", "Name trade-offs"],
                "next_drills": ["Kafka idempotency"], "uncertain_claims": []}
    if task == "brief.questions":
        return {"questions": ["Who owns failover testing?"]}
    raise AssertionError(f"unexpected task {task}")


@pytest.fixture(scope="session")
def event_loop_policy():
    return asyncio.DefaultEventLoopPolicy()


@pytest_asyncio.fixture(loop_scope="session", scope="session", autouse=True)
async def database():
    await migrate(reset=True)
    await db.connect()
    yield
    await db.close()


@pytest_asyncio.fixture(loop_scope="session")
async def client(database):
    reset_store()
    adapters.set_speech_providers(AsrEngine(), Diarizer())
    reasoner_mod.set_reasoner(Reasoner())  # unconfigured => AI unavailable
    embeddings.set_embedder(embeddings.Embedder())
    app = create_app()
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


class Api:
    """Small helper representing one signed-in device."""

    def __init__(self, client: httpx.AsyncClient, tokens: dict):
        self.c = client
        self.tokens = tokens

    @property
    def h(self):
        return {"Authorization": f"Bearer {self.tokens['access_token']}"}

    def idem(self):
        return self.h | {"Idempotency-Key": "k-" + uuid.uuid4().hex}

    async def get(self, path, **kw):
        return await self.c.get(path, headers=self.h, **kw)

    async def post(self, path, json=None, idem=True, **kw):
        return await self.c.post(path, json=json, headers=self.idem() if idem else self.h, **kw)

    async def patch(self, path, json=None, idem=True):
        return await self.c.patch(path, json=json, headers=self.idem() if idem else self.h)

    async def delete(self, path, idem=True):
        return await self.c.delete(path, headers=self.idem() if idem else self.h)

    async def me(self):
        return (await self.get("/v1/me")).json()

    async def space(self, kind="WORK"):
        return next(s["space_id"] for s in (await self.me())["spaces"] if s["kind"] == kind)


async def signup(client, email=None, platform="TEST") -> Api:
    email = email or f"user-{uuid.uuid4().hex[:10]}@example.test"
    r = await client.post("/v1/auth/register", json={"email": email, "password": "correct-horse-battery", "display_name": "Test", "age_confirmed": True,
                                                      "device": {"platform": platform, "name": "pytest"}})
    assert r.status_code == 201, r.text
    return Api(client, r.json())


CAPS = {"mic_permission": "granted", "input_route": "phone_mic", "output_route": "phone_speaker", "private_route_verified": False}
CAPS_PRIVATE = CAPS | {"output_route": "bluetooth_a2dp", "output_device_name": "Test Buds", "private_route_verified": True}


async def new_session(api: Api, context="MEETING", capture="PHONE_MIC", space_kind="WORK", **kw) -> dict:
    space = await api.space(space_kind)
    r = await api.post("/v1/sessions", {"space_id": space, "context": context, "capture_source": capture,
                                        "processing_region": get_settings().processing_region, **kw})
    assert r.status_code == 201, r.text
    return r.json()


async def consent(api: Api, sid, basis="PARTICIPANTS_INFORMED", notices=True, ai=True) -> dict:
    r = await api.post(f"/v1/sessions/{sid}/consent-receipts", {"capture_basis": basis, "notices_attested": notices,
                                                                "ai_assistance_permitted": ai,
                                                                "processing_disclosure_version": get_settings().processing_disclosure_version})
    assert r.status_code == 201, r.text
    return r.json()


async def start(api: Api, sid, receipt, caps=None, **controls):
    return await api.post(f"/v1/sessions/{sid}/start", {"consent_receipt_id": receipt["receipt_id"], "capabilities_hash": "caps-" + "0" * 16,
                                                         "capabilities": caps or CAPS, **controls})


async def recording_session(api: Api, context="MEETING", **controls) -> tuple[dict, dict]:
    s = await new_session(api, context)
    rc = await consent(api, s["session_id"])
    r = await start(api, s["session_id"], rc, **controls)
    assert r.status_code == 200, r.text
    return r.json(), r.json()["ingest"]


async def put_chunk(client, sid, ingest_token, seq, pcm=None, start_ms=None, sha=None):
    pcm = pcm if pcm is not None else tone_pcm()
    return await client.put(f"/v1/ingest/sessions/{sid}/chunks/{seq}", content=pcm, headers={
        "Authorization": f"Bearer {ingest_token}", "X-Sample-Rate": str(SAMPLE_RATE),
        "X-Capture-Start-Ms": str(seq * 1000 if start_ms is None else start_ms), "X-Duration-Ms": str(len(pcm) * 1000 // (SAMPLE_RATE * 2)),
        "X-Sha256": sha or hashlib.sha256(pcm).hexdigest(), "X-Encoding": "pcm_s16le"})


async def run_jobs():
    return await drain()


def as_json(r):
    try:
        return r.json()
    except json.JSONDecodeError:
        return r.text
