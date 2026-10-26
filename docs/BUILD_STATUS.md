# Build continuation status — 19 October 2026

Goal remains active: continue MeetSaathi end to end from the inherited Claude implementation. This is a working build, not a release.
User configuration: AWS `ap-south-1`, their own AWS account; check `polyameet` domain availability. Provisional API DNS:
`api.polyameet.com`. Registry RDAP returned no registration for `.com`, `.in`, `.app`; no purchase or DNS change has been made.
No AWS profile/credentials are configured locally.

## Inherited baseline verified

Native Kotlin/Compose Android, Swift/SwiftUI package and app target, FastAPI/PostgreSQL/RLS, capture/spool/ingest, consent and session
state machine, source-grounded intelligence, memory, four context packs, durable database workers, 323-row QA traceability.
The original 60 backend tests passed against real PostgreSQL. The inherited folder had no Git history. A local `main` repository is now initialized; no commit or remote exists yet.

## Continuation implemented

- AWS Bedrock schema-constrained reasoning, explicit regional model selection, local validation, refusal/truncation/error handling;
  no executable model tools and no implicit inference-profile routing.
- Persistent Amazon Transcribe sessions from the first ACK, paced PCM, concurrent draft/final handling, bounded background actors,
  fenced renewable leases and exact millisecond replay after disconnect. Both native clients render expiring live drafts separately
  from evidence. Input clock/duration validation prevents replay drift. Real AWS latency/quality acceptance remains pending.
- Application-encrypted S3 SSE-KMS object adapter; full version/delete-marker purges and partial-error handling; safe local object
  paths, symlink escape protection, private atomic temporary writes. Async callers offload blocking object I/O.
- SQS delivery from the transactional outbox, opaque IDs, re-publication, lease fencing and renewal, independently scheduled
  publication, retries/dead state. Provider errors no longer persist their content in job error fields.
- Concurrent HTTP idempotency first-use serialization. Open WebSockets recheck token/device/account validity and receive device
  revocation notifications; reconnecting clients refresh credentials through the ordinary HTTP auth path.
- Export download expiry checks, revocation on source deletion, physical purge including deterministic orphaned object keys.
- Both clients flush final capture before the End watermark; persist exact End bodies for offline/restart replay; preserve spool on
  temporary server failures. iOS uploader replacement stops its predecessor, and tap buffers are copied before asynchronous work.
  Sign-out/account deletion now stop local capture/voice/upload and clear live state.
  AI consent is an explicit independent control, off by default; the server now honors denial outside interviews too.
  Inference persistence rechecks source deletion/revisions, so delayed results cannot recreate purged evidence.
- Terraform: private RDS/Fargate, HTTPS ALB, WAF rate rules, S3/KMS/SQS/secrets, scoped task roles, CloudWatch alarms/dashboard;
  safe secret bootstrap, migration-first promotion/rollback helpers, ADOT config, metadata-only OpenTelemetry and readiness.
- Bounded sparse ingest/finalization, truncated ACK gap hints, preservation of acknowledged audio on stale End/Pause/interruption,
  unknown/estimated gap timing through native views and exports, finite-ASR source bounds, and exact Swift integer decoding (ADR-019).
- CI additions: Terraform validation/mock plans, dependency/secret/container scanning; manual AWS OIDC deployment workflow.

## Product journeys and i18n (this continuation, 19 October 2026)

Identity hardening (email verification, recovery, Cognito) is deferred by the product owner until before launch. This pass completed
the remaining client journeys on both apps against existing backend endpoints:

- **Evidence player (S14/U07):** plays exactly the cited span via `GET /sessions/{id}/utterances/{uid}/audio`; Android writes the clip
  to cache only during playback and deletes it, iOS holds it in memory. Playback is refused while any session may be capturing, so a
  clip can never be re-recorded into a live conversation. Deleted/unavailable audio is stated truthfully.
- **Memory detail (S22/M19):** provenance, exact cited transcript revisions (flagged when corrected since), decision status transitions
  mirroring server `DECISION_FLOW` with history, owner/due confirmation (never inferred), exclude-from-suggestions, edit (non-recorded
  only), delete.
- **Sharing (M23/UNI-024):** section choice, identity redaction, expiry, mandatory preview before a link exists, copy/send, list and
  revoke. New backend recipient page `GET /s/{token}`: static, script-free, strict CSP, `no-referrer`, `noindex`, `no-store`; identical
  404 for unknown/revoked/expired links. Tests cover escaping and headers.
- **Projects, courses and interview goals:** create/edit with kind-specific fields (course term/syllabus; interview company, stage,
  date, job description), session timeline, decision ledger, "prepare for next time" brief from kept items only, delete with an explicit
  count of sessions removed. Preflight can attach a session to one; Ask can scope to one.
- **Session controls:** consent withdrawal from Live (mic and uploads stop first; durable marker survives process death; spool purged
  after server acknowledgement; retried offline without uploading), conversation-type switch (permissions unchanged), assistance and
  frequency changes, delete audio but keep notes, full session history with paging.
- **Preferences (U13):** default assistance, delivery and per-context frequency persisted via `/v1/me/preferences`; last context offered
  on Home. Defaults never bypass per-session AI consent, interview rules or the private-route test (verified on the emulator).
- **Exports:** per-account and per-session after re-authentication, status polling, saved only through the system save dialog.
- **Handoff screen audit (all five design handoffs vs. the build):** added the remaining contracts that need no cloud/device access —
  M08 insight detail (rationale, evidence moments, still-current state, feedback), tappable citations in Ask and insights (open the
  memory, or replay the cited moment; the transcript instead while that session is live), L07/C09 timed notes during recording,
  and an L06 larger-captions preference. Deliberately not built: L20 teacher/institution controls (the Learning spec calls for a
  separate governed rollout), L18 lecture/slide import and board photos (no import pipeline), S20 desktop bridge and S23 landscape
  layout (P1), translated captions (English-only launch), and a live "current topic" strip (no topic event exists yet).
- **Full read of all five handoffs (second pass):** Meeting, Learning, Interview, Conversation and the Complete Product package
  (Experience Spec, Global Blueprint, Engineering Handoff, UI contracts, all release-QA CSVs) were read end to end. Gaps closed
  on both apps: Live "What did I miss?" and recap "Ask this meeting" (Meeting 4.1/7.2); suggestion history with "Not current" (S06);
  mute for 5/15/60 min or the rest of the session (Experience 6.3); "Open settings" when the microphone is denied (S02);
  "Stop recording, keep taking notes" with live controls hidden afterwards (CC-014); recap confirmed participants and
  "don't use for future suggestions" (S13/8.2); transcript search (S07); "needs an owner" filter (S22); interview warmup and an
  explicit missing-JD notice (Interview 5.2); an adults-only signup gate enforced by the server (LC-041). Bug fixed: the session
  project picker offered and created projects outside the session's space (the server rejected them; Personal and Work never mix).
- **Interview:** goals with job description, debrief with evidence excerpts and claims to double-check, focused single-skill retry.
- **Sensitive conversations:** sensitive presets (aligned with server policy) show the ephemeral/quiet notice and the explicit opt-in.
- **i18n-ready, English only:** 606 strings and 9 plurals generated from `qa/i18n/strings_en.py` into Android resources, the iOS
  String Catalog and a compiled English fallback; key coverage checked by `gen_strings.py --check`. Dates render in the reader's zone.
- **Accessibility:** headings marked, selection states announced, decorative tab icons hidden from TalkBack, labelled fields,
  ≥48 dp / 44 pt targets, status never colour-only. No TalkBack/VoiceOver audit has been performed on a device.

## Current evidence

- Backend: **142 tests passed** against real PostgreSQL and explicit provider doubles; never paid cloud services.
- Android: Java 21, **19 JVM tests**, APK, lint 0 errors. Emulator journey run **34/34** (`qa/evidence/android-journeys-2026-10-19.json`)
  plus the earlier offline End/process-death smoke (evidence below). Emulator audio is synthetic.
- Swift: **24 tests passed**; all SwiftUI screens compile on macOS, but `#if os(iOS)` paths, the app target and String Catalog
  compilation need Xcode (not available). No simulator or device run.
- Docker, Terraform, dependency audit: unchanged from the entries below.
- QA traceability: 129/323 master rows have automated evidence (emulator journeys now attached to MTG-043/049/052/053, CON-013,
  UNI-024); every device row remains NOT_RUN. This is not 129 device passes.

## Remaining implementation and acceptance work

| Item | Status |
|---|---|
| Identity: email verification, recovery, production identity provider (Cognito or equivalent) | Deferred by product owner until before launch |
| Live AWS speech/AI acceptance (Transcribe, Bedrock, Nemotron serving), multilingual benchmarks | **Blocked** — no AWS credentials |
| iOS app target build, simulator/device runs, signing, TestFlight | **Blocked** — no Xcode / Apple Developer account |
| Physical-device matrix (`docs/device-test-plan.md`): 90-minute/background/battery, Bluetooth routes, TalkBack/VoiceOver | Pending — phones to be provided |
| Abuse/spend protections beyond quotas, key rotation/keyring | Not started |
| Git history/remote, protected environments, domain/ACM/DNS, staging deploy, IAM-negative tests, cloud E2E | **Blocked** — no remote / AWS / domain |
| Backups and restore drill, load/soak, pen test, legal and store review, human release sign-off | Not started |

Do not mark the overall goal complete or call the product production-ready while these requirements remain.

### Confirmed Android offline recovery

`qa/android-offline-end-2026-10-19.json` records the native API 35 exercise. Confirmed End saved
`final_sequence=41`, `at_ms=42157`, with `next_seq=42` after partial-chunk flush. CaptureService was absent after End and after
an offline process restart. After backend restoration and relaunch, the server reached `COMPLETED`, ACK watermark 41,
`finalization_status=COMPLETE`; the drained spool directory was removed. No speech-quality conclusion follows from emulator silence.

### Container security gate

Trivy 0.76.0 found 45 HIGH package findings across nine unique CVEs in the initial Debian 13.7 image. One PCRE2 issue has a Debian
security fix; the Dockerfile now installs available OS security updates. Rescan confirmed the PCRE2 fix: **44 HIGH package findings across eight unique CVEs remain**, with no fixed Debian package versions reported. A comparison with the older
Bookworm base found more flagged CVEs, so the runtime was not downgraded. Findings are recorded in
`qa/container-vulnerability-findings-2026-10-19.json`; the deployment scan remains fail-closed. Unfixed findings require actual
reachability/mitigation review or a patched base, not silent exclusions. The clean Python audit is a separate result.

### Reproducible runtime and secret scan

`backend/requirements.lock` pins 61 runtime distributions with SHA256 release hashes. The Dockerfile installs with
`--require-hashes` before the application, and CI uses the same lock. `backend/scripts/lock_runtime.py` regenerates hashes from an
explicitly tested runtime image and official PyPI release metadata. The lock's dependency audit reports no known vulnerabilities.
The source secret scan passed without exclusions; its initial hit was a non-secret fixed idempotency key in a test, now generated
uniquely per run. Local Git is initialized on `main`, with no commit or remote.

Latest locked Linux ARM64/Python 3.12 container: **117 tests passed** against real PostgreSQL, including RLS and the cloud SDK contract doubles. No live AWS acceptance is claimed.

Persistent live-speech evidence: `qa/live-speech-evidence-2026-10-19.json`; architecture and limits: `docs/adr/ADR-018-persistent-live-speech.md`.
