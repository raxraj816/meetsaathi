# MeetSaathi — Production Build Addendum v1.1

**Date:** 18 October 2026  
**Applies to:** `MeetSaathi_Unified_Master_Product_Engineering_v1.zip` and the Meeting, Learning, Interview, and Conversation companion specifications.  
**Status:** Implementation directive. Not evidence of an implemented or production-ready application.

## Purpose and priority

The v1.0 Master Product & Engineering Specification is authoritative for the product experience, privacy rules, session state machine, source-grounding, four contextual experiences, and acceptance principles. This v1.1 document records the technology-stack decisions made **after** v1.0 was generated and clarifies what an end-to-end, production-intended build must actually deliver. If a service choice conflicts with a generic v1.0 option, this addendum governs the first implementation, subject to measured benchmarks and documented architecture decisions.

**The product is not a POC.** Develop one maintainable, real native iOS application and one real native Android application, using shared server-side capabilities. Incremental delivery is allowed, but fake capabilities must never appear as shipped, and a functional design preview must not be equated with a real mobile application.

## Technology decisions — baseline

| Area | Production baseline | Lock/qualification |
|---|---|---|
| Android | Kotlin + Jetpack Compose; AudioRecord/AudioManager; native microphone foreground service | Architecture decision |
| iOS | Swift + SwiftUI; AVAudioEngine/AVAudioSession; native background and route handlers | Architecture decision |
| Backend | Python 3, FastAPI + Pydantic, modular monolith with separated inference/background workers | Architecture decision |
| Realtime | Authenticated bidirectional WebSocket sessions and HTTPS APIs; framed chunks, ACKs, replay/reconnect | Architecture decision |
| Streaming ASR | Amazon Transcribe Streaming as initial integrated adapter | Evaluate quality/latency on real data; keep replaceable |
| Speaker diarization | NVIDIA Nemotron 3 Diarization as leading candidate, with alignment and explicit unknown identities | Benchmark and support fallback, including >8 speakers |
| Reasoning and structured extraction | Amazon Bedrock through provider/model adapters, versioned prompts/policies | Model mix depends on measured usefulness, latency and cost |
| TTS | Streaming speech synthesis with cancellation and verified private-earbud routing | Provider selected via device/language/latency benchmark |
| Database | Amazon RDS for PostgreSQL + pgvector; enforce server-side space isolation and reviewed RLS policies | Architecture decision |
| Object storage | Encrypted S3 for authorized audio/uploads/derived objects; lifecycle/retention | Architecture decision |
| Background queue | Amazon SQS with retries, idempotent workers and dead-letter queues | Architecture decision |
| Container hosting | ECS Fargate for API/ordinary workers; GPU-backed EC2/ECS for self-hosted NVIDIA inference when justified | Benchmark-driven GPU fleet shape |
| Auth | Cognito or equivalent OIDC solution, real token verification, device revocation and account recovery | Confirm exact identity flows before production |
| Secrets/encryption | KMS, Secrets Manager, TLS, platform keystores, least-privilege IAM | Required controls |
| Infrastructure delivery | Terraform and automated GitHub Actions build/test/deploy pipeline; managed signing credentials | Must be implemented, not just diagrammed |
| Observability | OpenTelemetry tracing/metrics, CloudWatch and/or Grafana dashboards, alerting and privacy-safe logging | Required controls |

Avoid Kafka, Neo4j, EKS, standalone vector databases, and multiple backend languages until measured load or feature requirements justify the additional complexity. Explicitly document any substitution and its acceptance evidence in an ADR; do not silently swap providers just to obtain a working demo.

## Required user-facing end-to-end outcomes

1. **Real foreground-started session:** Permission/consent preflight, actual microphone capture, live status, Pause/Resume/End, no fictitious waveform, local encrypted buffering and upload acknowledgment.
2. **Actual screen-on Live Focus:** Clear transcript state, one prioritized context-sensitive insight, on-demand Ask, evidence/Why, safe controls visible at all times.
3. **Actual pocket session:** Phone locked; continued capture only where supported; private earbud audio only with verified route and explicit opt-in; connection loss immediately mutes output with no speakerphone fallback.
4. **Actual speech intelligence:** Streaming ASR, anonymous speaker turns, overlap/unknown handling, alignment with timestamps, provisional/final revisions, speaker correction.
5. **Actual source-grounded memory:** Correct tenant/space filtering; attribution and source timestamps; Remember vs Think vs Learn vs Prepare; cross-session memory only under chosen retention policy.
6. **Four context packs in one app:** Meeting decisions, Learning review, Interview mock/permitted live assistance, Conversation reflection. All reuse a single capture and policy stack.
7. **Actually functioning privacy:** Recording/processing/assistance/voice/retention separately controlled; deletion cascades to objects, indexes, caches, local chunks and derivatives, with honest status.
8. **Truthful failure UX:** Microphone/device/route/network failures, ASR lag, diarization uncertainty, backend/model timeout, storage full, and finalization retry are surfaced without losing or inventing content.

## Non-negotiable engineering and operations deliverables

- Repository with Android/iOS source code, real backend implementation, workers, API/client contracts, SQL migrations, infrastructure-as-code, CI configuration, and deployment runbooks.
- Real development/staging/production separation, secret injection, least-privilege identities and automated security scans. Do not commit production tokens or credentials.
- Authenticated APIs and WebSocket streams with rate/usage limits, replay/idempotency, load and abusive-use protections, versioned events, and backward-compatible mobile releases.
- Database migrations with completed and negative-tested RLS/authorization; **the v1.0 SQL is a draft, not a complete secure production migration**. Verify worker roles, grants and cross-table tenant/space consistency.
- Encryption of audio at rest and in transit, consent event ledger, configurable retention, export/deletion jobs and audit logs without leaking conversation content.
- Operational readiness: SLOs, dashboards, alerts, tracing, exception handling, backup/restore drills, incident response playbooks, key rotation, cost/usage alerts, deploy rollback and disaster-recovery assumptions.
- Model evaluation: multilingual/code-switching and technical vocabulary, overlapping speakers, phone-on-table vs pocket, accent/noise/device cohorts; grounded citations, hallucination/attribution tests, intervention usefulness, interruption frequency and end-to-end latency.
- Accessibility, dynamic type, screen readers, localization, battery/thermal profiling, app-store disclosures and region-appropriate recording/education/interview legal review.
- Real-device validation on an explicitly named Android/iOS OS/device/earbud compatibility matrix. Emulator-only verification is insufficient for background capture and audio routing.
- Human-reviewed release sign-off. Every milestone is **Specified**, **Implemented**, **Tested**, or **Released**, with proof; do not mark 'production ready' without passing gates.

## Build and evidence gates

| Gate | Required proof |
|---|---|
| Foundation | Native apps build/sign; backend deploys to staging; auth/space-isolation tests pass; consent policies executable |
| Live audio | Audited real-device start/pause/end, screen-off capture where supported, gaps logged, encrypted spool and replay tested |
| Speech | Actual streamed transcript and speaker turns from diverse consenting test sessions; failure and uncertainty shown |
| AI | Real contextual Ask and interventions grounded in the proper scope; independent evaluation and no-action behavior tested |
| Earbud | Verified private-route behavior including connect/disconnect, call interruption, background, screen lock, low battery |
| Memory | Source citation and correction lineage, scoped cross-session retrieval, export and deletion verification |
| Production | Pen test, staging soak/load test, backup/restore, monitoring, incident runbooks, costs/quotas, accessibility, stores/legal sign-off |

The existing unified QA file contains **323 written scenarios**. They are not completed tests. The team should import them into the test tracker, assign owners/environments, add measurable pass thresholds, and attach evidence for each executed run.

## Coding-agent working agreement

1. Treat the unified v1 master specification as the UX, intelligence and policy contract; this v1.1 addendum as the concrete technology and production-delivery supplement.
2. First inspect the repository and report what's **actually implemented**, what's stubbed, what's untested, what's blocked by credentials/hardware/accounts, and any deviations from the architecture.
3. Work in cohesive, runnable vertical slices with migrations, tests and telemetry. Each deliverable must be real and integration-tested. Test-only fixtures are allowed; production-mode screens must never show fabricated transcripts, AI insights or connectivity.
4. When cloud accounts, vendor credentials, signing identities or physical devices are unavailable, implement and test everything possible, then accurately mark those particular integration/release gates **Blocked**, not Done. Do not fake a pass.
5. For each milestone produce: changed files, runnable commands, required configuration, local/staging test results, security/UX findings, remaining blockers and real-device evidence.
6. Never declare the product globally available or production ready merely because the repository compiles or a simulator works. Ship only after product, security and operational acceptance gates pass.

## Important caveat

This document augments design intent; it does not prove the coding agent has seen the addendum, or that any production code, cloud deployment, real-time model integration or real-device tests exist. Verify against the actual repository and build pipeline.
