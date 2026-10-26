"""LOCAL E2E SEED ONLY. Drives the real API in-process with the explicit test doubles from backend/tests/conftest.py
(scripted ASR, alternating diarizer, fake reasoner) to create a finished, realistic meeting for emulator walk-throughs
of post-session journeys (evidence playback, decisions, owners, sharing, projects, export).

It never runs in a server and never touches cloud providers. The account is written to qa/e2e/.local-account.json
(gitignored) so the emulator can sign in with it. Usage, from backend/:

  MS_ENV=dev MS_OBJECT_STORE_DIR=<same dir as the dev server> .venv/bin/python ../qa/e2e/seed_journeys.py
"""
from __future__ import annotations

import asyncio
import json
import os
import secrets
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))
store_dir = os.environ.get("MS_OBJECT_STORE_DIR")
env = os.environ.get("MS_ENV", "dev")
if env not in ("dev", "test") or not store_dir:
    sys.exit("refusing: set MS_ENV=dev and MS_OBJECT_STORE_DIR to the dev server's object directory")

from tests.conftest import (AlternatingDiarizer, FakeReasoner, ScriptedAsr, default_responder, put_chunk,  # noqa: E402
                            tone_pcm)

# conftest forces test-only settings at import; restore the dev server's view before anything reads settings.
os.environ["MS_OBJECT_STORE_DIR"] = store_dir
os.environ["MS_RUN_INLINE_WORKER"] = "false"

import httpx  # noqa: E402

from app.config import get_settings  # noqa: E402
from app.db import db  # noqa: E402
from app.intelligence import reasoner as reasoner_mod  # noqa: E402
from app.main import create_app  # noqa: E402
from app.speech import adapters  # noqa: E402
from app.storage import reset_store  # noqa: E402
from app.workers.runner import drain  # noqa: E402

LINES = ["We need per-customer partition keys for ordering.", "Alex will benchmark regional failover by Friday.",
         "Should retries use exponential backoff or a fixed delay?", "What is our RPO target for the payments database?"]
OUT = Path(__file__).parent / ".local-account.json"


async def main() -> None:
    get_settings.cache_clear()
    reset_store()
    adapters.set_speech_providers(ScriptedAsr(list(LINES)), AlternatingDiarizer())
    reasoner_mod.set_reasoner(FakeReasoner(default_responder))
    await db.connect()
    app = create_app()
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://seed") as c:
        email = f"e2e-{secrets.token_hex(4)}@example.test"
        password = secrets.token_urlsafe(18)
        r = await c.post("/v1/auth/register", json={"email": email, "password": password, "display_name": "E2E", "age_confirmed": True,
                                                    "device": {"platform": "TEST", "name": "seed"}})
        r.raise_for_status()
        h = {"Authorization": f"Bearer {r.json()['access_token']}"}
        me = (await c.get("/v1/me", headers=h)).json()
        work = next(s["space_id"] for s in me["spaces"] if s["kind"] == "WORK")
        proj = (await c.post("/v1/projects", headers=h, json={"space_id": work, "kind": "PROJECT", "title": "Payments platform",
                                                                  "metadata": {"description": "Event pipeline redesign"}})).json()
        s = (await c.post("/v1/sessions", headers=h | {"Idempotency-Key": secrets.token_hex(8)}, json={
            "space_id": work, "context": "MEETING", "capture_source": "PHONE_MIC", "title": "Architecture review",
            "processing_region": get_settings().processing_region, "preset": "Architecture review", "project_id": proj["project_id"]})).json()
        sid = s["session_id"]
        rc = (await c.post(f"/v1/sessions/{sid}/consent-receipts", headers=h | {"Idempotency-Key": secrets.token_hex(8)}, json={
            "capture_basis": "PARTICIPANTS_INFORMED", "notices_attested": True, "ai_assistance_permitted": True,
            "processing_disclosure_version": get_settings().processing_disclosure_version})).json()
        st = (await c.post(f"/v1/sessions/{sid}/start", headers=h | {"Idempotency-Key": secrets.token_hex(8)}, json={
            "consent_receipt_id": rc["receipt_id"], "capabilities_hash": "seed-" + "0" * 16,
            "capabilities": {"mic_permission": "granted", "input_route": "phone_mic", "output_route": "phone_speaker",
                             "private_route_verified": False}})).json()
        tok = st["ingest"]["token"]
        for i in range(24):
            pr = await put_chunk(c, sid, tok, i, pcm=tone_pcm(freq=180 + 20 * (i % 6)))
            pr.raise_for_status()
            if (i + 1) % 6 == 0:
                await drain()
        await c.post(f"/v1/sessions/{sid}/stop", headers=h | {"Idempotency-Key": secrets.token_hex(8)}, json={"final_sequence": 23})
        for _ in range(4):
            await drain()
        recap = (await c.get(f"/v1/sessions/{sid}/recap", headers=h)).json()
    await db.close()
    OUT.write_text(json.dumps({"email": email, "password": password, "session_id": sid, "project_id": proj["project_id"],
                               "state": recap["state"], "decisions": len(recap["decisions"]), "actions": len(recap["actions"])}, indent=2))
    print(json.dumps({"session_id": sid, "state": recap["state"], "decisions": len(recap["decisions"]), "actions": len(recap["actions"]),
                      "open_questions": len(recap["open_questions"]), "account_file": str(OUT.relative_to(ROOT))}))


if __name__ == "__main__":
    asyncio.run(main())
