# Continuation verification log — 19 October 2026

All cloud/provider test doubles are confined to `backend/tests/`. No live cloud calls have been represented as passing.

- Baseline: 60 backend tests passed before changes.
- AWS adapter contracts: 24 passing cases, including real botocore request/response shape validation for Bedrock/S3, final-only
  Transcribe result deduplication/word offsets, region denial, malformed AI output, multipart ASR encoding, filesystem traversal.
- Worker delivery: five passing integration cases against PostgreSQL, including duplicate SQS notifications, lease heartbeat,
  stale-owner completion/failure fencing, error-content redaction and concurrent first-use HTTP idempotency.
- Export retention: two passing integration cases covering immediate archive revocation and physical deletion/expiry.
- Deployment helpers: four passing cases covering secret preservation/password escaping, migration failure, promotion and rollback.
- Terraform validate and two mocked plan tests passed. Actual AWS resources/IAM/collector have not been exercised.
- Android: Java 21; APK, unit tests (15) and lint passed. Emulator: Android 15/API 35, AVD `ms35`, no actual microphone signal.
- iOS shared package: 16 tests passed; no full Xcode/iOS SDK or device build here.
- Python dependency inventory: pip-audit reported no known vulnerabilities. This is not a penetration test.

Native emulator lifecycle passed: confirmed End persisted its exact body through an offline force-stop/relaunch, stopped the
microphone service immediately, replayed after backend restoration, ACKed the final sequence and completed finalization.
See `android-offline-end-2026-10-19.json`. Final backend suite: **102 passed** (including inference deletion races, independent AI
consent and stream revocation); Android 15 JVM tests/build/lint and Swift 16 shared-package tests passed.

Final container smoke: migrations up to date; readiness 200, register 201, authenticated profile 200. OS updates fixed one PCRE2
finding. Trivy remains failing on 44 HIGH package findings / eight unique CVEs (no fixed Debian versions reported); findings are
recorded separately and are not waived.

Source secret scan: gitleaks passed, no exclusions. Runtime SHA256 lock: 61 distributions; locked dependency audit clean.

The final hashed-dependency Docker image also passed all **102 tests** on Linux ARM64 / Python 3.12 against real PostgreSQL.


## Persistent live speech continuation

- Full host backend suite: **117 passed**, using real PostgreSQL and provider doubles.
- Twelve live-stream integration cases: preview before stream close without evidence, cropped PCM replay after disconnect,
  expired-owner fencing, source deletion, capture discontinuities, silence handling, no-cloud silence, bounded concurrency with
  ordinary durable jobs still runnable, strict source-clock validation, finalization awaiting provider drain, and prolonged outage
  followed by the user retry action without re-recording, and sustained-silence quality warnings without cloud calls.
- Transcribe transport cases cover partial/final delivery, short language tags, explicit multilingual selection, duplicate finals,
  provider EOF cancelling input, and missing final-drain timeout. No real AWS speech/latency/quality result is claimed.
- Android: **16 JVM tests**, APK assembly and lint passed. Swift: **17 shared-package tests** passed with macOS compilation.
  Draft expiry/clear matching is covered; these checks do not replace device or full iOS SDK acceptance.
- Source secret scan passed without exclusions. QA traceability remains 129/323 with some automated evidence; device rows NOT_RUN.

Latest locked Linux image passed **117 tests** (Python 3.12/ARM64), including migration 005 and all new speech cases.
Rescan still reports 44 HIGH package findings / eight CVEs, no waivers; source secret scan passes.
Image identity and scope are recorded in `live-speech-evidence-2026-10-19.json`.
