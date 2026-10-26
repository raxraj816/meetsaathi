# MeetSaathi

**One mobile companion. Four contexts — Meeting, Learning, Interview, Conversation. One trustworthy intelligence platform.**

This repository implements `MeetSaathi_Unified_Master_Product_Engineering_v1` (authoritative) using the five companion design
handoffs as reference. The monorepo layout follows master §12.1.

```text
backend/            FastAPI API + realtime gateway + durable workers, PostgreSQL 16 + pgvector, RLS
  app/api/          HTTP + WebSocket endpoints           app/domain/   sessions, policy/consent, state machine, ingest, events
  app/speech/       ASR / diarizer adapters, aligner      app/intelligence/  reasoner (Bedrock; explicit Anthropic alternative), insight scheduler, Ask, extraction
  app/memory/       retrieval, corrections, deletion, sharing/export                app/packs/  Meeting, Learning, Interview
  app/workers/      leased job runner (retries, dead-letter), finalization, purge   migrations/ schema, row-level security, fenced worker delivery, export purge
apps/android/       Kotlin + Jetpack Compose app (microphone foreground service, encrypted spool, uploader, routes, private TTS)
apps/ios/           MeetSaathiKit Swift package (core, AVAudioEngine capture, AVAudioSession routes, SwiftUI) + App/ target (XcodeGen)
packages/contracts/ openapi_v1.json (generated from the implementation), realtime_events_v1.json, state_machine_v1.json, master drafts
packages/design/    tokens.json (master v1 tokens + UI copy)
infra/              Docker Compose; AWS Terraform/Fargate/RDS/S3/SQS/KMS; bootstrap/deploy helpers; ADOT
docs/               ADRs (master ADR-001..015 + ADR-016 extensions), providers, threat model, runbook
qa/                 Release_QA_Traceability.csv (all 323 master QA rows, with automated evidence where it exists)
```

Current continuation status and remaining implementation work: [docs/BUILD_STATUS.md](docs/BUILD_STATUS.md).
AWS deployment: [docs/deployment.md](docs/deployment.md). The overall end-to-end goal is still active.

## What is implemented (by master release gate)

| Gate | Implemented |
|---|---|
| 0 Foundations | Accounts, tenants, Personal/Work/Learning spaces, projects; device-bound short-lived JWT + rotating refresh tokens with reuse detection; per-device revocation; Postgres RLS on every scoped table with separate `ms_app` / `ms_worker` roles; standard error contract; Idempotency-Key replay; design tokens; contracts |
| 1 Trusted session | Server-authoritative state machine (master 7.1, mirrored by both clients and pinned by a shared fixture); separate consent receipts (capture basis, notices, AI permission, disclosure version); capture/AI/voice/retention gates; native capture (Android FGS microphone + AudioRecord; iOS AVAudioEngine + background audio); encrypted bounded local spool; resumable idempotent upload with checksum, ACK watermark and gap list; pause stops ingest; stop is immediate and idempotent with offline drain; interruptions and gaps recorded |
| 2 Words & speakers | Provider-neutral ASR + Nemotron diarizer adapters, aligner with overlap/unassigned handling and own-voice suppression; provisional → final revisions; anonymous aliases; speaker and transcript corrections that version evidence and invalidate dependent claims, shares, insights and embeddings |
| 3 Quiet intelligence | Single-card insight scheduler: policy → spend → interrupt budget → temporal (user speaking, Ask precedence, staleness) → evidence → dedupe → explainable score → channel; NO_ACTION is common; Remember/Think/Learn/Prepare with server-verified citations and abstention; extractive Remember when AI is down |
| 4 Pocket voice | Verified private route (device present + user-heard test sample), fail-closed hard mute on route loss, never loudspeaker fallback, barge-in stop, playback windows excluded from ASR |
| 5 Memory & packs | Review-to-keep, retain, scoped search (ACL before retrieval), decision lineage, owner confirmation, deletion with immediate revocation + auditable purge, audio-only deletion, retention expiry, exports (re-auth), redacted revocable shares; Meeting recap/decision timeline/brief; Learning Explain-this, practice + feedback, spaced review; Interview goals, adaptive mock, debrief rubric, answer lab, live AI gate; Conversation notes-only default, recollections, reflection |
| 6 Release | **Not claimed.** Device matrix, 90-minute soak, accessibility audits, pen test, legal review and store approval require real devices and people. See `qa/Release_QA_Traceability.csv` (`status` stays `NOT_RUN` until executed on devices). |

## Run it

```bash
cp infra/.env.example infra/.env
docker compose -f infra/docker-compose.yml --env-file infra/.env up --build
```

Local development without Docker for the API: see `docs/runbook.md`. AI and speech providers are optional; without them the app
reports truthful degraded states (see `docs/integrations/providers.md`).

## UI copy and localization

English only at launch, i18n-ready: every UI string lives in `qa/i18n/strings_en.py` (one source for both apps).
`python3 qa/i18n/gen_strings.py` regenerates Android `res/values/strings.xml`, the iOS String Catalog `apps/ios/App/Localizable.xcstrings`
and the compiled-in English fallback, then checks that every key used in Kotlin (`R.string.*`) and Swift (`L("…")`, `LP("…")`) exists.
Server timestamps are rendered in the device's time zone and locale. Preset names are wire identifiers; only their labels are localized.

## Verification performed in this repository (19 October 2026)

- `backend`: `pytest` — **142 tests** against real PostgreSQL + RLS with explicit provider doubles (no paid cloud calls).
- `apps/android`: `./gradlew :app:testDebugUnitTest :app:assembleDebug :app:lintDebug` — **19 JVM tests**, APK builds, lint 0 errors.
  Emulator walk-through `qa/e2e/android_journeys.py` (API 35, local backend seeded by `qa/e2e/seed_journeys.py` with the test doubles):
  **34/34 steps** — sign-in, recap, memory detail with evidence playback, decision status change, owner confirmation, share preview →
  link → recipient page → revoke, transcript with play controls, keep → Memories, project brief and decision ledger, saved defaults with
  the consent gate intact, and consent withdrawal (server stopped, local spool purged, microphone service gone).
  Evidence: `qa/evidence/android-journeys-2026-10-19.json`. Emulator audio is synthetic; no physical device was used.
- `apps/ios`: `swift test` — **24 tests**; the whole package including all SwiftUI screens compiles on macOS. The iOS app target needs
  Xcode with the iOS SDK (`xcodegen generate`), not available here, so `#if os(iOS)` paths are uncompiled and no simulator/device run exists.
- Not exercised: live Bedrock/Transcribe/diarization (no AWS access), physical devices (plan: `docs/device-test-plan.md`).

**Do not label the product production-ready** (master README): real-device validation, provider evaluations, legal review and
security testing remain release gates.
