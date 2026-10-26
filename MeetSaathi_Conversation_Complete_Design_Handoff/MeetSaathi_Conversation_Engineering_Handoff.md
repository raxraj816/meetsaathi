# MeetSaathi Conversation Companion — Engineering Handoff

**Status:** Implementation specification; no functional native app built yet.

## What to build
A single unified MeetSaathi product with contextual Conversation Companion policies. The interactive HTML design is a synthetic UX test harness, never a production audio frontend. Treat the full `MeetSaathi_Conversation_Companion_Product_Spec.md` as the product source of truth.

### Recommended repo layout
```text
meetsaathi/
  apps/android/            # Kotlin + Compose, audio route and foreground service
  apps/ios/                # Swift + SwiftUI, AVAudioSession and background behavior
  services/api/            # Authn/z, sessions, permissions, retrieval, user data
  services/realtime/       # Streaming ingest, sequence tracking, ASR/diarization
  services/intelligence/   # Context builder, policy gate, LLM, TTS
  services/memory/         # PostgreSQL, pgvector, source provenance, deletion
  contracts/openapi/
  contracts/events/
  packages/design-tokens/
  qa/device-matrix/
  qa/evaluation-datasets/
  docs/architecture/
  infra/
```

## Implementation milestones and why they matter

**M1 — Truthful native session:** Build and test permission/capture/stop state machine, Notes-only mode, explicit participant disclosure, user-selected retention, and persistent device status. *Why:* Without this foundation, the app cannot be trusted to listen.

**M2 — Source-grounded recording:** Add encrypted buffering, ASR, speaker diarization, correction, time intervals, and verifiable replay. *Why:* Memory accuracy depends on evidence integrity, not just fluent summaries.

**M3 — Useful proactive AI:** Add live context state, candidate insight generation, evidence checks, suppression / interruption scheduler, single-card UI and user feedback. *Why:* More generated suggestions is not better UX.

**M4 — Remember / Think / Prepare:** Implement three separately evaluated response policies, retrieval-scoped evidence references, user-reviewed saves, and no-data abstention. *Why:* AI inference must not become a fake quote.

**M5 — Earbud/private voice:** Add route detection and route-specific tests, TTS queue/cancellation, Bluetooth disconnect kill-switch, screen-off controls. *Why:* Leaking private voice to a speaker is a severe trust failure.

**M6 — Real-world release:** Run all 96 documented test cases, supported-device audio/memory/thermal matrix, user trials, accessibility and localized compliance reviews. *Why:* Production quality is measured in uncontrolled user conditions.

## Engineering non-negotiables

- Authorization must run at client and server, and on every privacy-scoped search.
- Never create ambient auto-listening from app launch, reboot or unrelated background triggers.
- Use immutable evidence ids and transcript revisions; do not silently change who said what.
- A `Stop` response halts capture first; finalization continues only after source is safely sealed.
- On private audio route loss, cancel queued TTS and never use loudspeaker fallback.
- Memory search is strictly filtered by tenant, user, space and per-item access policy before ranking.
- Treat recorded speech as untrusted text, not as instructions to system tools.
- Production UI must communicate actual mic, route, processing and retention state.
- Keep the preview's fictional demo data distinct from live/test production records.

## Release criteria
Run the device, security, quality, accessibility and deletion tests in `MeetSaathi_Conversation_Release_QA.csv`. Each row starts as `Not run`, not `Pass`. Record evidence, device OS and firmware, app version, network conditions, model versions and any exemptions.

## Deliverable order for Codex
Start with architecture decision records, shared API/event contracts, database migrations, and a minimal native session. Build one full consented conversation to verified memory before polishing secondary experiences. No disposable public demo or ungrounded claims of production readiness.
