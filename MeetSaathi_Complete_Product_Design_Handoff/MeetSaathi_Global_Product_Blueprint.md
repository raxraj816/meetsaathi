---
title: "MeetSaathi | Global Product & Company Blueprint"
subtitle: "Product requirements, competitive benchmarks, production architecture, security, economics, and global go-to-market"
date: "14 October 2026"
status: "Founder strategy and engineering specification | Version 1.0"
---

# Executive decision

**North star.** MeetSaathi is a mobile-native, permission-aware conversational intelligence companion that helps people understand, remember, think through, and act on live human conversations. A user starts a session and puts the phone face-up beside a laptop, face-down on a table, or in a pocket. The same contextual intelligence appears as glanceable text, private earbud audio, or both. Afterward, it remains a cited, searchable memory and reasoning partner.

**The product category is not new.** Hedy already markets proactive real-time coaching and brought NVIDIA Nemotron 3 Diarization to supported iPhones and Macs in September 2026. Granola, Fathom, Circleback, Otter, and Plaud supply overlapping capture, memory, AI chat, and follow-up capabilities. Therefore, "record + transcribe + summarize + ask AI" is not differentiation. MeetSaathi must win on the complete live mobile experience, personalized intervention relevance, trustworthy attributed memory, acoustic/device robustness, and transparent user control. [S1-S8]

**Recommended launch wedge.** Complex, consented technical conversations for software engineers, architects, consultants, technical product managers, and researchers. These users have frequent substantive discussions, measurable information-loss pain, and high value per useful intervention. Build for multilingual worldwide use from the beginning; sequence country support by verified legal, language, reliability, and support readiness rather than releasing everywhere at once.

**Five irreversible-seeming mistakes to avoid:** (1) claiming anonymous diarization identifies people; (2) promising iPhone/Bluetooth/pocket recording combinations without hardware validation; (3) capturing third parties without adequate notices and permissions; (4) fabricating who said what or silently blending meeting facts with AI opinion; (5) selling unlimited expensive live inference before proving unit economics.

**Principle.** No throwaway demo: every released workflow must be production-intended, tested, secure, and valuable. This does not mean "all features on day one"; progressive production releases and real customer validation are required to build a durable company.

# 1. Product thesis, positioning, and boundaries

## 1.1 The job to be done

People want to be present in high-stakes or high-density conversations while still being able to recall the exact discussion, notice omissions, think through trade-offs, prepare questions, and convert decisions into reliable follow-through. Existing tools often reduce note-taking effort. MeetSaathi aims to improve the user's understanding and effectiveness *during* the conversation and build trustworthy context *across* conversations.

**Positioning:** "Your AI companion for conversations that matter." **Functional promise:** "Remember accurately. Think in the moment. Prepare confidently." **Voice and brand:** supportive, concise, unobtrusive, technically credible; not an omniscient 'always listening' surveillance product.

**What it is:** a personal context assistant, live coaching interface, meeting memory, contextual learning assistant, authorized action helper. **What it is not:** a covert recording tool, automated lie detector, employee emotion scorer, interview-cheating device, or a replacement for participants' consent and judgment. Exclude covert-assistance and undisclosed-recording workflows. Interview use is for practice or contexts explicitly permitting AI assistance.

## 1.2 Personas and prioritization

| Persona | Critical job | Willingness to pay hypothesis | Priority |
|---|---|---|---|
| Software engineer / architect | Track design rationale, trade-offs, ownership, and unresolved risks | Medium-high individual; high team | First |
| Technical product manager / consultant | Cross-meeting context, decisions, dependencies, follow-ups | Medium-high | First |
| Researcher / graduate student | Turn seminars/interviews into navigable evidence and learning | Medium; institutional potential | Second |
| Founder / sales consultant | Recall customer needs and prepare next discussions | Medium-high | Second |
| General personal-life recording | Broad memory capture in diverse contexts | Uncertain; privacy complexity | Later |
| Recruitment/interview candidates | Practice, authorized coaching, reflection | Seasonal and often policy-constrained | Practice-specific only |

**Why technical conversations first?** Unlike generic summaries, high-value technical meetings generate inspectable decisions, citations, and trade-offs. The outcome can be tested with experts. A vertical starting point sharpens messaging and dataset coverage without limiting the eventual universal companion vision.

## 1.3 Product invariants

1. Visible session status; capture begins only after deliberate user initiation and necessary disclosures/permissions.
2. The user knows whether AI output is sourced to a recording, an inference, or outside knowledge.
3. Speaker identity remains 'unknown' until reliably mapped or corrected; anonymous speaker labels are not names.
4. Suggestions never claim something was said without supporting evidence.
5. Screen-off and earbud operation have tested device-dependent behavior and graceful fallbacks.
6. Sessions survive transient network loss; unsynced data is encrypted locally.
7. The user can stop capture, mute speech, remove a session, or revoke memory usage promptly.
8. No training on private customer content by default. Explicit separate opt-in would need a rigorous policy.
9. Tenant isolation and consent permissions are enforced server-side at every data access.
10. Reliability, unit cost, latency, accessibility, and language quality are measured in production.

# 2. End-to-end product specification

## 2.1 Modes: independent dimensions

Do not confuse *interaction mode* with *output mode* or *audio source*.

| Dimension | Options | Reason |
|---|---|---|
| Assistance | Listener / Ask / Proactive Companion | User chooses how much AI initiates |
| Output | Text / Earbud voice / Both / Silence | Context and social acceptability vary |
| Placement | Table face-up / Table face-down / Pocket / Uploaded audio | Same product across real situations |
| Capture | Phone mic / Platform-supported external mic / Authorized desktop bridge / Uploaded file | One capture solution cannot handle every laptop-headset situation |
| Privacy | Session-specific consent and sharing / Local-only when supported / Cloud processing with explicit terms | Enterprise and personal use require differentiated trust |

**Default:** Listener with screen-on text suggestions in *Balanced* intervention mode only after appropriate recording permission; private voice **off** until explicitly selected and audio route verified. The user can override per meeting. For very sensitive contexts, default to no capture until explicit consent, with no live suggestions.

## 2.2 Core flows (user acceptance criteria)

**Flow A - phone face-up beside laptop.** User launches app, sees mic/source and privacy status, selects "Meeting", checks participation disclosure, taps Start. The dashboard shows a concise, continuously updating transcript, speaker labels with uncertainty, short prioritized suggestion cards, elapsed time, microphone quality, battery/network state, Ask box, and Stop. Suggestions can be dismissed, expanded, or turned off. A large font landscape mode should be available for phone stands.

**Flow B - phone face-down or locked.** Session begins visibly first. With required OS foreground/background entitlements, capture continues while locked, with system status notification/indicator. If screen is down, no assumption is made that microphone pickup remains adequate; display an audio-quality warning when practical. A reconnection event must not silently end or duplicate a session.

**Flow C - phone in pocket with earbuds.** User starts session and confirms route. App may use the phone mic or earbud mic as platform supports; only advertise tested combinations. Voice suggestions are short, speak at appropriate volume, and do not start during another speaker's sentence unless the user elects urgency. Tap or voice query behavior must be mapped to supported accessories. If the routing combination cannot deliver acceptable room capture, explicitly switch to a supported fallback (screen text or phone table placement) instead of pretending to listen.

**Flow D - laptop users wearing headphones.** The phone mic cannot hear remote participants whose voices play only inside laptop headphones. An optional native desktop bridge (authorized OS audio capture or meeting-platform integration) streams consented audio/transcript to the mobile session. The phone remains the primary surface. No unsupported universal same-device call capture claim.

**Flow E - ask during session.** Input can be typed or spoken through a clearly invoked mode. Questions such as "What did she decide?", "Explain the trade-off", or "What should I ask next?" resolve against a permission-scoped live transcript plus relevant prior context. Response labels: "From conversation", "Suggestion", "External explanation"; transcript-backed claims offer precise segment citations and replay where recording is retained.

**Flow F - proactive Companion Mode.** The system monitors conversational state and selectively proposes high-value interventions: unanswered questions, decisions lacking owners, inconsistent claims, missing failure cases, changed commitments, or technical concepts needing explanation. It waits for good conversational timing. It limits repeats, learns from dismissals, and never talks continuously merely because content is available.

**Flow G - after meeting.** User receives a structured, source-linked digest: overview, participant map, decisions with evidence, action items with responsible speakers and confidence, open questions, disagreements, discussion timeline, personalized learning topics, and "prepare next time." Corrections propagate to all dependent summaries and indexes.

**Flow H - across meetings.** Ask "Why did our architecture decision change since September?" The system retrieves permitted sessions, compares source-backed statements, differentiates revised decisions from unverified speculation, and points to relevant recordings. Users can erase or exclude a meeting from memory and analytics.

## 2.3 Feature priority and reason

| Feature | Priority | Why / launch boundary |
|---|---|---|
| Safe start/stop, status, consent record, session recovery | P0 | Necessary to trust continuous listening |
| Native phone recording with screen-off testing | P0 | Core promise, not a convenience |
| Live ASR, timestamped transcript, correction | P0 | Foundation for both live and post-meeting use |
| Diarization + uncertainty + manual identity mapping | P0 | "Who said what" must not overclaim |
| Text live dashboard and Ask | P0 | Most dependable primary interaction |
| Source citations and replay | P0 | Prevents confident but unverifiable memory |
| Proactive suggestions with policy, throttle, feedback | P0 | Main differentiation hypothesis |
| Short TTS to earbuds with user control | P0 on compatible device matrix | Core vision; release only once routing and timing pass |
| Search across sessions + decision change log | P1 | Retention and compounding memory value |
| Optional desktop bridge | P1 | Required for headset-only laptop audio; different installation burden |
| Multilingual and code-switching adaptation | P1 per tested language | Global value but expensive to QA |
| Authorized integrations and action approvals | P1 | Reduces workflow friction, increases stickiness |
| On-device speech stack for supported handsets | P1/P2 | Privacy, latency and margins; device fragmentation is real |
| Enterprise controls, residency, SSO, DLP | Enterprise gate | Required before selling into regulated teams |
| Dedicated wearable hardware | Not initially | Unnecessary capital risk when phones already exist |

## 2.4 Required screens

Onboarding (what is recorded and what is not), recording consent checklist, Audio Route Test, Home/Library, Session Setup, Live Dashboard, Quick Ask Sheet, Companion Intervention Feed, Speaker Review/Correction, Meeting Digest, Cross-Meeting Search, Conversation Detail, Memory & Deletion Controls, Integrations, Subscription/Usage, Accessibility Settings, Privacy & Regional Settings, Enterprise Admin (web).

**Live dashboard hierarchy:** (1) capture status + Stop; (2) last meaningful utterance; (3) ONE highest-priority suggestion (expand for rationale); (4) Ask; (5) minimized secondary insights. User must never hunt for the Stop control. Use large legible content, high contrast, and screen-aware auto-dimming. Default to text on face-up devices; audio-only should not require a glowing screen.

## 2.5 Example product copy and output contract

**Transcript fact:** "Speaker 2 proposed retrying with exponential backoff at 18:42." [source; confidence; identity unknown]. **Reasoning:** "My assessment: retries need idempotency and a dead-letter handling policy." [not said in meeting]. **External knowledge:** "Kafka preserves order within a partition, not across all partitions." [outside explanation; link if fetched].

The frontend must render these categories separately. If a question cannot be answered from authorized source data, say so and offer to explore it as an independent question. Never use the absence of evidence to assert absence of an event.

# 3. Competitive benchmarks and the switching thesis

## 3.1 Verified competitive landscape (as checked October 2026)

| Product | Relevant capabilities documented publicly | Strategic implication |
|---|---|---|
| Hedy AI | Real-time guidance, conversations in many languages, cross-session intelligence; September 2026 Nemotron on-device diarization on supported Apple devices; Pro ~$8.33/mo annually | Closest direct live-coaching competitor; cannot claim 'first' |
| Granola | Device-audio capture, iOS/Android, speaker tags, cross-meeting chat, briefs, advanced integrations; Business $14/user/mo | Strong meeting-memory and ecosystem substitute |
| Fathom | Live summary, meeting chat, team search, meeting capture; Premium ~$16/mo billed annually, $20 monthly | Strong value in conventional meetings |
| Circleback | Mobile and Apple Watch apps, speaker-labeled sessions, Ask Circleback, team workflow; Pro $15/user/mo listed | Mobile / meeting-history convergence |
| Otter.ai | Live transcription, speaker identification, meeting chat and workflows; paid tiering | Established transcription and collaboration brand |
| Plaud | Wearable recorders, Ask Plaud, transcription and memory | Hardware is a distribution alternative, not only a hardware feature |
| Limitless / Meta | Meta's acquisition of personal conversational-memory startup | Large-platform pressure on persistent memory |

Sources: [S1-S8]. Product pricing and feature availability change; this is a dated snapshot, not a claim of side-by-side verified performance. In particular, competitors' claims should be tested independently before describing MeetSaathi as better.

## 3.2 Benchmarking protocol - test reality, not websites

Recruit 30-50 consented evaluators across three primary cohorts: engineers/architects, PMs/consultants, and researchers. Run the same approved audio/meeting scenarios through MeetSaathi and 3-4 major competitors subject to their product terms. Assess both live and after-session tasks with blind graders. Benchmark by mic placement (table near/far, face-down, pocket), platform (iOS/Android), earbud models, meeting input method, network quality, accents, 2/4/8 speakers, overlap, and noisy rooms.

**Task suite:** (a) capture exact disputed statement; (b) find who owns an action; (c) identify whether a decision was final; (d) ask for a missing failure consideration in real time; (e) replay evidence; (f) distinguish fact vs inference; (g) connect two meetings; (h) experience 90-minute screen-off / audio route changes; (i) delete all artifacts; (j) disclose/notify participants.

**Metrics:** word error rate (WER) by language/noise, diarization error rate (DER) and identity attribution precision, exact citation accuracy, factual consistency, intervention usefulness and false-interruption rate, end-to-end insight latency, 90-minute capture success, route success by device, battery draw, user-reported cognitive burden, post-meeting task completion, and blind preference. Report confidence intervals and disaggregated results; avoid one blended benchmark hiding hard cases.

**Winning gate (hypothesis, not measured):** MeetSaathi must achieve a materially higher blinded "I would use this in my next real meeting" preference score and better actionable suggestion precision than relevant alternatives while matching basic transcription/reliability within an acceptable range. If no measured switching advantage emerges, reposition before scaling spend.

# 4. Architecture - production-intended, modular and mobile first

## 4.1 End-to-end logical architecture

```text
                 ON DEVICE (iOS Swift / Android Kotlin)
User Start + Consent Gate + Session Controls + Audio Route Test
         |                      |                   |
    Phone microphone       Earbud TTS          Live text UI
         |                      ^                   ^
   VAD / AEC / gain / audio chunks              WebSocket events
         |                      |                   |
   Encrypted local spool <---- session transport ----> API Edge
                                                       |
                                               Auth + tenant policy
                                                       |
                                           Realtime Session Gateway
                                                       |
                           +---------------------------+-------------------+
                           |                           |                   |
                  Streaming ASR provider        Diarization path    Context builder
                  partial/final + timing        (Nemotron or API)     rolling state
                           |                           |                   |
                           +--------- merge / align / confidence ----------+
                                                       |
                                       Evidence ledger / session timeline
                                                       |
                                   Retrieval + memory access policy engine
                                                       |
                              Intervention engine (rules + model + scoring)
                                                       |
                               Fact verifier + response formatter + TTS
                                                       |
                                     WebSocket insights / earbud playback

After session: postprocess -> verify speaker map -> decisions/actions ->
 versioned summaries -> embeddings / typed facts -> tenant-scoped retrieval
 Storage: PostgreSQL + pgvector + encrypted object storage + event/outbox
 Observability: OTel traces, error budgets, quality analytics without raw PII
 Optional: permitted desktop bridge, platform integrations, local inference
```

## 4.2 Key architectural decisions and rejected alternatives

**Native Kotlin + Jetpack Compose / Swift + SwiftUI.** Reason: recording, audio focus, OS lifecycle, Bluetooth routing, notifications, and low-latency TTS are platform-centric and critical. Shared domain schema/protocols can be generated from OpenAPI/Protobuf. Rejected as primary: one cross-platform JavaScript audio implementation until the device matrix is proven. A cross-platform presentation layer can be evaluated later, but not at the expense of audio reliability.

**Modular backend with a distinct realtime session service.** Start with Python FastAPI for product APIs and AI orchestration, plus an isolated stateful WebSocket/gRPC realtime gateway for audio and event fan-out. Separate GPU-backed model workers. A large microservices fleet is not necessary before traffic requires it. Reasons: transaction integrity and deployment simplicity, while keeping independently scalable audio workloads.

**WebSocket streaming for low-latency transcript/control events; QUIC/WebRTC only where product tests justify it.** WebSockets are widely supported and easy to instrument for bidirectional low-latency control; server-side packet framing, sequence numbering, backpressure and reconnect logic are essential. Evaluate WebRTC for managed audio jitter/echo complexity only if WebSocket audio transport fails measured quality targets. Do not stream raw unbounded PCM when efficient codecs/secure compression suffice.

**ASR and diarization as replaceable subsystems.** NVIDIA Nemotron 3 is one diarization engine, not the product. It supports up to eight anonymous speakers, not speaker names, and a 0.32-30.4 s *audio buffer* trade-off; actual suggestion latency additionally includes capture, network, ASR, reasoning, and TTS [S9]. Use a provider-neutral ASR interface and a distinct diarization adapter. Benchmark self-hosted Nemotron (license review required) against commercially hosted speaker-aware ASR for accuracy, mobile portability, region and per-hour economics.

**Parallel online path and high-quality finalization path.** Use provisional live text/speakers with revisions; run final ASR/diarization/alignment after the meeting or in the background to improve source quality. Maintain immutable evidence revisions and an auditable correction map so a previously displayed provisional label is never silently treated as a verified fact. Reasons: real-time latency and long-term accuracy demand different operating points.

**PostgreSQL + pgvector initially, not automatic graph database adoption.** Meeting/session/speaker/decision/access-control data is relational; transactions and permission-scoped joins matter more than graph marketing. Vector search augments, not replaces, time-bounded lexical retrieval. Add typed provenance edges inside PostgreSQL first. Introduce an external graph engine only if measured multi-hop performance or advanced relationship analysis warrants it.

**Cloud + selective device intelligence.** A hybrid strategy uses on-device VAD, local encrypted spool, and potentially selected ASR/diarization on supported devices; cloud handles heavier models and complex contextual analysis when authorized. On-device is not automatically private if transcripts or embeddings subsequently leave the phone. Clear processing-mode labels and data-flow enforcement are required. Reason: worldwide phone hardware varies dramatically.

**One primary cloud region with regional isolation options.** Launch with a region chosen for first-customer latency/legal fit, avoid cross-region replication of raw audio, and design region as a first-class data residency attribute. Add a second region when justified by demand or regulatory commitments. No global central memory containing every person's speech.

## 4.3 Pipeline details

1. User starts session while app visible; collect required disclosures/permissions and optional participants' acknowledgement record.
2. Create signed session with tenant, retention, region, features, capture source and consent metadata.
3. Local recorder acquires PCM with OS-specific audio graph, monitors route changes and quality, transforms to transport encoding, writes encrypted bounded spool, sends sequenced chunks.
4. Session gateway acknowledges offsets, reconnects with short-lived tokens, deduplicates chunk IDs, and applies per-session concurrency quotas.
5. Streaming ASR emits partial and final words with timestamps/language probabilities; diarizer emits overlap-capable anonymous activity intervals.
6. Alignment service joins words to activity intervals on the same clock/time base, marks overlaps and uncertainty, and publishes append-only utterance revisions.
7. Context engine builds a rolling conversation state: topic, question, objection, decision candidate, commitment, open issue, and user-specific permitted prior context.
8. Intervention engine generates candidates, evidence-checks them, applies confidence/novelty/urgency/interruption policy, selects the highest-value candidate, or stays silent.
9. Delivery router sends text or short TTS to approved phone route; every generated insight has origin label, age, expiry, evidence pointers, feedback and dismissal state.
10. After session: final diarization, ASR repair, speaker-confirmation flow, summaries and memory extraction, index only allowed facts, preserve correction lineage.

**Precision rule:** a diarizer detects anonymous turns. Actual identity can be linked by user verification or legitimately available, permissioned metadata. Voiceprints are sensitive biometric data in many contexts and must never be added casually. Use explicit speaker correction as the default.

## 4.4 Proactive intervention engine: the differentiating service

**Candidate types:** unanswered direct question, contradiction with a prior accepted decision, commitment without an owner or deadline, risk not yet discussed, missing nonfunctional requirement, requested fact retrieval, concept explanation, and follow-up preparation. Avoid suggestions about inferred inner emotions, protected traits, hiring suitability or deceptive manipulation.

**Scoring:** candidate utility = evidence quality x relevance x actionability x urgency - interruption cost - hallucination risk - redundancy. Use bounded deterministic policy before or after model scoring; models may propose ideas but may not bypass thresholds, consent, muted states or budget caps. Trigger only once the supporting utterance is stable enough.

**Interruption windows:** prefer natural pauses or when a user taps Ask; avoid interrupting ongoing speech. The default Balanced setting sends only meaningful suggestions; Active has bounded frequency, Silent never initiates. Short spoken prompts (e.g., 5-12 seconds) should be skippable, never trigger repeatedly on the same issue, and never mask important real-world speech. A 'do not interrupt' signal has priority over everything except user-visible recording status.

**Feedback flywheel:** user marks Useful, Not relevant, Incorrect, Too late, Too frequent, or Save. Train per-user preference ranking only under appropriate permissions; do not automatically train a general foundation model on private transcript content.

**Anti-pattern:** run a heavyweight LLM inference on every 200-ms audio chunk. Use speech endpointing, event-based triggers, lightweight classifiers and caches to control latency and cost.

## 4.5 Domain/data model and contracts

Core entities: `tenant`, `user`, `membership`, `consent_record`, `session`, `participant`, `audio_source`, `audio_chunk_manifest`, `utterance_revision`, `speaker_cluster`, `speaker_identity_mapping`, `topic`, `evidence_span`, `insight_candidate`, `insight_delivery`, `decision_event`, `action_item`, `meeting_summary_revision`, `memory_fact`, `embedding`, `retention_policy`, `access_grant`, `audit_event`, `billing_meter`.

**Invariants:** every row holds tenant/region provenance; utterances hold source asset + start/end + version; speaker labels may be UNKNOWN; no named person inferred solely from the diarizer; insights reference evidence spans or are labeled independent reasoning; deletions tombstone graph references and trigger index/object purge; retention decisions propagate across all derived artifacts.

**APIs/events (illustrative):** `POST /v1/sessions` (consent + settings, idempotency key), `POST /v1/sessions/{id}/end`, `GET /v1/sessions/{id}/events`, `POST /v1/sessions/{id}/ask`, `PATCH /v1/speakers/{id}` (verified correction), `DELETE /v1/sessions/{id}`, `GET /v1/memory/search`, `POST /v1/insights/{id}/feedback`, `GET /v1/usage`. Realtime events: `audio.chunk`, `audio.ack`, `asr.partial`, `asr.final`, `speaker.provisional`, `utterance.corrected`, `insight.candidate`, `insight.delivered`, `audio.route_changed`, `session.ended`. Message IDs, monotonically increasing sequence, timestamps and idempotency are mandatory.

## 4.6 Failure and operational design

**Offline transition:** continue local encrypted capture only if allowed and capacity remains; mark cloud reasoning unavailable and queue resumable chunks. The app must never imply that real-time AI insights are still being produced without connectivity. **Network flap:** retry with bounded exponential backoff, replay acknowledged offsets, deduplicate. **Mic preemption/phone call:** visibly pause or end; notify user. **Thermal or battery event:** step down model quality, reduce screen refresh, stop optional features before abandoning capture; warn before cutoff. **Bluetooth disconnect:** stop TTS, automatically revert to silent screen guidance only when safe. **Model outage:** preserve capture and transcript if possible; degrade Companion Mode separately. **Speaker >8:** detect out-of-supported-limit situation; use alternative pipeline or mark identity uncertain. **Legal/consent revocation:** immediately stop relevant processing and revoke access.

**Deployment:** managed relational DB with point-in-time restore, encrypted object storage with lifecycle and versioning controls, autoscaling stateless APIs, GPU inference workers behind queues, dead-letter and reconciliation for postprocessing, transactional outbox for event publication, CI/CD progressive rollout, per-platform feature flags, and regional routing tests. Kafka/Kubernetes are options at scale, not day-one obligations.

# 5. Quality, benchmarks, SLOs and validation

## 5.1 Candidate release targets (engineering goals, not observed product performance)

| Objective | Proposed acceptance threshold | Test population |
|---|---|---|
| Session continuity | >=99.5% of supported 90-min sessions without unannounced capture loss | Supported OS/device matrix |
| App stability | >=99.8% crash-free sessions | Production pilot telemetry |
| First usable live transcript | p95 <=2.5 s after a clearly completed phrase | Stable Wi-Fi/4G; defined noise levels |
| Proactive text after qualifying trigger | p95 <=6 s, with hard timeout and silent fallback | Controlled high-confidence triggers |
| Earbud response after deliberate Ask | p95 <=7 s to first intelligible audio | Supported compatible routes |
| Evidence correctness | >=98% of transcript-grounded factual citations resolve to supporting spans | Human audited query set |
| Unfounded concrete speaker/owner attribution | Near-zero critical misattributions; block at uncertainty threshold | Adversarial attribution set |
| Useful suggestion precision | >=80% of delivered prompts rated actionable by blinded evaluators | Consent-based expert study |
| Unwanted interruption rate | <=1 / 30 minutes in Balanced mode | Real-session annotations |
| Deletion completion | Defined purge SLA; no accessible derived artifacts after completion | Data life-cycle integration suite |
| Cost control | SLO-aware unit inference cost within tier budget | Per-feature/region metering |

Targets require a testing plan and instrumented definitions. A p95 from clean audio does not establish pocket/far-field or code-switching performance. Publish segmentations by locale, noisy conditions, speaker count and device. WER and DER should be benchmarked against actual domain ground truth rather than set to an unsupported universal number.

## 5.2 Mandatory physical-device test matrix

Android current/older OS versions, low/mid/high-end handsets; recent and older iPhones; wired headphones, common Bluetooth earbud codecs/models; on-table mic up/down, 0.5m/1.5m/3m distance, pocket clothing types; laptop sound through speaker vs headset; 2/4/8/>8 speakers; overlap; power saver; screen lock; phone call interruptions; Wi-Fi -> LTE -> offline; language changes mid-sentence; live meeting 90-120 min; background app eviction; overheating. Mark combos Supported, Limited, or Unsupported, and expose detection/reporting in product.

**Why:** the go-to-market claim "turn it on, put it away" fails if the device lab tests only a flagship phone in a quiet room.

## 5.3 Evaluation architecture

Use a consented proprietary evaluation corpus with speaker-turn ground truth, timestamps, important facts, expected intervention moments, domain glossary, language/accent labels, and authorized cross-meeting queries. Have experts grade live usefulness without seeing the product identity. Require regression tests on every ASR, diarization, LLM, prompt, or audio engine update. Red-team prompt injection spoken by meeting participants ("ignore previous instructions"), fabricated commitments, bogus speaker names, overlapping voices and adversarial acoustics.

# 6. Security, privacy, legal and trust architecture

## 6.1 Consent and lawful capture design

MeetSaathi handles conversations belonging to multiple people, not only the subscriber. The mobile user granting microphone permission is not automatically authorized to record, process, or share everyone else's words. Build explicit pre-session notice and consent workflow appropriate to use case and jurisdiction, participant notifications where necessary, employer-policy warnings, and one-click Stop. In sensitive scenarios where lawful authorization cannot be established, recording is unavailable. Local processing does not eliminate the need to comply with notice and recording laws.

Apple requires explicit consent and clear indication when recording activity; Android/Play imposes disclosure and permission expectations. EU GDPR requires a suitable legal basis; this is not always consent, but a lawful basis and appropriate transparency are necessary. India's DPDP Act and Rules create additional requirements with staged commencement; country-specific counsel must verify requirements at each launch date. The EU AI Act prohibits many workplace/education biometric emotion-recognition uses; exclude such features. [S10-S16]

## 6.2 Threat model and mitigations

| Threat | Potential damage | Controls |
|---|---|---|
| Covert capture or missing participant notice | Legal harm, trust loss | Consent gate, prominent recording indicator, disclosure tooling, restricted contexts |
| Cross-tenant data leaks | Exposure of proprietary discussions | AuthZ on every query, DB RLS where appropriate, tenant-scoped keys/queries, isolation tests |
| Recorded speech prompt injection | AI leaks data or follows attacker instructions | Transcript always untrusted content; tool-policy sandbox, no instruction execution from speech |
| AI hallucinates commitment / speaker | Bad decisions, reputational harm | Evidence links, unknown speaker state, provenance, correction workflow |
| Stolen unlocked phone / local cache | Private meeting data leak | OS keystore/keychain, encrypted spool, biometric unlock, protected app switcher |
| Vendor data retention/training | Unapproved secondary use | DPA, no-training terms, minimization, routing controls, vetted subprocessors |
| Unauthorized external actions | Calendar, mail or task damage | Explicit per-action approval, narrow tokens, idempotency, audit, revoke |
| Insider access to private audio | Privacy/compliance incident | Least privilege, audited break-glass, encryption keys separated from operators |
| Deletion gaps in embeddings/backup | Retained personal data after request | Cascading deletion manifest, index purge, backup expiration process, verification job |
| Audio replay/device spoofing | Incorrect speaker attribution | No voice-as-identity by default; identity claims verified separately |
| Abuse/DoS and unexpected model spend | Outage or financial loss | Rate limits, per-session budgets, quotas, alarms and circuit breakers |

## 6.3 Trust controls by default

TLS in transit; envelope encryption at rest with cloud KMS; keychain/keystore for local encrypted cache; secret rotation; separate prod/staging; SSO/OIDC for enterprise; OAuth short-lived scopes; tenant-aware retrieval and DB policies; optional region restrictions; time-boxed sharing links; access/deletion audit; privacy-safe observability with redaction; default no third-party model training; external action approval; vulnerability scanning/SBOM/SAST/DAST; pentests before enterprise launch; incident drills and restore testing.

**Data retention:** propose short default raw-audio retention (e.g., 30 days or user-selectable deletion after transcription), longer transcript/memory retention only by affirmative choice; enterprise administrator policies must not silently override the individual's privacy commitments without clear contractual terms. User may delete audio but keep text, or delete all. State plainly that citations requiring audio replay disappear if original audio is deleted.

**Deletion:** mark session revoked at authorization layer immediately; queue index/object/database purge with confirmation; handle shared copies, backups per published schedule, and audit metadata under lawful retention constraints. Ensure the system does not rehydrate erased memory from logs, caches, embeddings, or retraining corpora.

**Global legal plan:** regional legal counsel before each jurisdiction rollout; map GDPR/UK GDPR, US state recording/biometric and consumer privacy laws, India's DPDP framework, data transfer restrictions, minors, medical/education contexts, and employer confidentiality. This document is engineering/business guidance, not a legal opinion.

## 6.4 Accessibility, fairness and anti-manipulation

Support live captions, adjustable text size, high contrast, screen readers, subtitles for AI output, haptic cues, language selection, and no reliance on audio-only interaction. Measure disparities by accent, gender presentation, language and acoustic scenario without storing sensitive demographics by default. Never provide covert interview answer feeds or deceptive invisible assistance in controlled assessments; offer interview practice and explicit approved co-pilot use. Never infer inner emotions or hiring fitness from voice; besides poor reliability, this can create serious legal risk.

# 7. Economics, pricing, cost and business model

## 7.1 Verified input prices and economic assumptions

AssemblyAI lists streaming recognition at approximately $0.15/audio-hour for standard and $0.45/hour for the higher-quality realtime tier, plus a separately priced live diarization add-on at $0.12/hour. These are public vendor list prices, not MeetSaathi's negotiated prices or guarantees. One must not double-count third-party diarization and self-hosted NVIDIA diarization for the same processed stream. Other ASR vendors, self-hosted GPUs, and device inference have different costs and quality trade-offs. [S17]

**Illustrative live cost per fully active recorded hour:** $0.15 speech + $0.12 diarization + $0.18 LLM/retrieval + $0.07 generated voice + $0.10 marginal infrastructure/storage = **$0.62/hour**. These last three numbers are planning assumptions to test, not externally verified prices. Premium speech option substitutes $0.45 ASR for $0.15, producing **$0.92/hour**. Postprocessing, fixed SRE payroll, support, CDN/network egress, payment processing, taxes, app-store commissions, refunds, enterprise support and customer acquisition are not fully included. Some providers bill by connected streaming duration rather than non-silent speech, so idle sessions still cost money.

| Monthly usage per user | Basic $0.62/h | Premium $0.92/h | Gross margin at $19 tier* |
|---|---:|---:|---:|
| 5 hours | $3.10 | $4.60 | 83.7% / 75.8% |
| 10 hours | $6.20 | $9.20 | 67.4% / 51.6% |
| 20 hours | $12.40 | $18.40 | 34.7% / 3.2% |
| 30 hours | $18.60 | $27.60 | 2.1% / negative |

*Gross margins only as (revenue - listed variable model cost)/revenue, not operating margin. This table intentionally shows why an unlimited $19 real-time cloud plan can fail under heavy usage.

## 7.2 Recommended initial monetization experiments

| Plan | Candidate retail price | Included live hours per month | Value |
|---|---:|---:|---|
| Free | $0 | 2 hours | Experience core listener, live text, a small quota of Companion insights and post-meeting chat |
| Individual | $19/mo | 10 hours | More AI coaching, voice output, cross-meeting memory, longer retention |
| Power | $39/mo | 25 hours | Advanced real-time usage, personalized professional memory, extensive search, priority processing |
| Team / Enterprise | Per-seat + usage quote | Contracted pool | Admin, SSO, policy, residency, legal terms, integrations, audit, support |

These are starting hypotheses, not recommended final prices without customer willingness-to-pay tests. Explore annual plans and region-appropriate pricing after confirming revenue, payment tax mechanics, competitive perception, and user value. Charge reasonably for excess hours, with opt-in warnings and hard monthly spend caps. Distinguish recording/transcription hours, advanced coaching minutes, and audio playback if needed, but avoid confusing users with raw token billing.

**Pricing strategy rationale:** the expensive asset is concurrent streaming attention, not storage of a short note. Subscriptions with fair quotas align revenue and inference. Device processing can gradually improve margins without degrading quality. Do not price solely against Hedy's low annual rate: either show superior user value or change the cost/experience architecture.

## 7.3 Cohort/unit economics, not vanity revenue

For an illustrative **1,000 paid users** at $25 blended recognized monthly ARPU, MRR is **$25,000**. At 10,000 paid users, MRR is **$250,000**, equivalent to **$3 million annualized recurring revenue** if steady. This is a scenario, not a forecast. Break-even depends on realized usage, provider contracts, staffing, marketing, churn, and taxes.

Track contribution margin after platform fees, gross margin by persona/feature/region, median and p95 live hours, speech vs reasoning cost, free-to-paid conversion, refund rate, CAC by source, payback months, voluntary churn, net retention for teams, support tickets per 1000 sessions. A high-volume free cohort can destroy economics without converting; instrument feature-level value and cost.

**Pricing sensitivity:** at $19 and 10 active hours, premium speech case leaves $9.80 before additional overhead and selling costs; at 20 hours only $0.60. Growth spending must not be based on the healthy case only. Run Monte Carlo / cohort simulation from real usage before buying traffic.

# 8. Global go-to-market, distribution and defensibility

## 8.1 First market, global design

**Launch cohort:** English-speaking technical professionals and small distributed engineering teams, including India and other reachable markets where recording rules, payment, language, support and data transfer obligations have been validated. India is a useful early founder network and cost-conscious testing ground; worldwide design means localization and policy architecture are extensible from the outset. Do not interpret "global" as every locale enabled without QA.

**Core narrative:** "A live thinking companion for technical conversations - on the phone beside your laptop, or with optional earbuds." Avoid generic "AI meeting notes" advertisements. Demo one surprising product truth: ask about a disputed decision, get exact evidence, then receive a timely missing-risk suggestion during a new discussion.

## 8.2 Distribution sequence

**Wave 1: founder-led design partners.** 25-50 technical professionals and 5-10 small teams. Weekly sessions, consented observation, comparison with incumbent tools, interviews on actual switching behavior. Collect qualitative stories, not merely app-install counts.

**Wave 2: technical community product-led growth.** Short consented demos; architectural decision-review and engineering retro workflows; developer communities, technical newsletters, engineering creators, YouTube walkthroughs, targeted search content. Launch on stores with high-quality listing, privacy transparency and clear headphone compatibility. Ask satisfied users to share a sanitized, permission-cleared insight card - never automatically share transcripts.

**Wave 3: team-led expansion.** Shared topic/decision timeline with distinct private-vs-team contexts, Slack/Calendar/Drive integrations with explicit OAuth scopes, team approvals and admin audit. Pricing model per seat plus usage; team memory requires access separation.

**Wave 4: selective enterprise.** Security documentation, SOC 2 readiness, penetration test evidence, security questionnaires, SSO/SCIM, DPA, data residency, DLP and enterprise procurement. Choose regulated verticals only once legal and operational gates are met.

## 8.3 Differentiation and moat

No single open-weight diarization model is a moat. More credible accumulating advantages are (1) device/audio compatibility and reliable screen-off capture; (2) intervention policy tuned to real human timing; (3) expertly evaluated technical-conversation datasets obtained with permission; (4) multi-session, auditable decision memory under user control; (5) personalization driven by feedback rather than private-model-training shortcuts; (6) integrations and team workflows that become part of work; (7) trust/reputation evidenced by verifiable product behavior. Every candidate moat must be measured rather than asserted.

## 8.4 Brand/name and positioning risks

"MeetSaathi" is emotionally memorable in India and conveys partnership; worldwide, 'Saathi' needs pronunciation/explanation, and 'Meet' can suggest that the tool only works in scheduled meetings. Keep it as a working brand while running professional trademark searches in priority classes and territories, app-store conflict review, domain availability, and multilingual linguistic checks. Do not buy the domain or print materials merely because a quick web result looks clear. Alternative brand exploration can occur before public launch without delaying core engineering.

# 9. Roadmap, staffing, sequencing and release gates

## 9.1 Program framing

The company should have a complete product vision and a deliberately sequenced production delivery. Stage boundaries are **evidence-based release gates**, not throwaway prototypes or promises of a fixed deadline.

**Stage 0 - risk retirement and spec lock (weeks 0-4 target):** confirm legal/consent model; device routing study on Android and iOS; benchmark Nemotron+ASR options; pricing and hosting feasibility; 30-50 user interviews; brand clearance. Deliver ADRs, data model, threat model, contract tests, real audio quality baseline, clickable production UI specification. Gate: basic phone/earbud capture combinations are demonstrably possible or the product promise is revised accurately.

**Stage 1 - production core (months 2-4 target):** native apps, session and consent lifecycle, cloud gateway, live ASR, attributed transcript/correction, text ask, citations, encrypted spool, recovery, analytics, early private paid pilot. Gate: capture SLO and grounded-answer target on supported devices; legal review completed.

**Stage 2 - genuine live companion (months 4-7 target):** trigger engine, feedback, intervention controls, first short TTS route combinations, cross-meeting memory, postprocess repair, eval harness, subscriber billing and quotas, privacy lifecycle. Gate: blind competitor tests show actionably better live coaching, good user control, and viable margin.

**Stage 3 - scale distribution (months 7-12 target):** deepen Android/iOS device matrix, localization in tested languages, authorized desktop bridge, direct integrations, team features, incident and security maturity, expansion marketing. Gate: target retention, paid conversion, support burden, and cost data support expansion.

**Stage 4 - compounding intelligence (year 2+):** selective on-device acceleration, advanced long-term decision memory, privacy-preserving personalization, more sophisticated authorized actions, enterprise/risk-region offerings and optional wearable partners. Gate: demand and unique product advantage, not technology novelty.

## 9.2 Team and ownership

Minimum serious cross-functional ownership: product/founder; native Android; native iOS; backend/realtime; speech/ML; applied LLM/retrieval/evals; product design/UX; security/privacy with outside counsel; QA/release/observability; growth and customer support. People can initially hold multiple roles, but the responsibilities cannot be omitted. Audio QA and security should not be treated as an afterthought delegated to a single full-stack engineer.

**Architecture decision records:** one page for each consequential choice: problem, alternatives, measured evidence, security and cost implications, decision, rollback condition, date, owner. E.g., "We chose WebSocket transport over WebRTC because live audio gateway experiments met latency/jitter targets on target networks; reopen at [X] packet-loss rate." Evidence-backed reversibility is a competitive strength.

## 9.3 Launch gate checklist

- Supported-device matrix with successful 90-min screen-on, screen-off, pocket and table tests.
- Call/headphone audio limitation surfaced accurately to users; no unsupported recording claims.
- Latency distributions and suggestion precision measured; false interrupts acceptable.
- Provenance and corrective attribution workflow tested with overlapping speech.
- User data export, deletion, backup expiry and no-training obligations verified.
- External legal/privacy review, app-store disclosures, incident response contact and DPA where relevant.
- Billing caps, overage disclosures, per-user cost telemetry, failure recovery and rollback.
- Vulnerability scan, threat model, pen test plan, audited access controls, authenticated tenant isolation.
- In-product onboarding and accessibility tests with unfamiliar users.
- Paid users demonstrating recurring use and honest comparative preference over incumbents.

# 10. Product analytics and executive scorecard

**North-star metric:** Weekly *verified value sessions* - consented sessions in which the user receives at least one post-session evidence-backed answer or rates a timely live suggestion useful, with the session successfully completed. This tracks product value, not raw recorded minutes.

**Activation:** percent who successfully complete a meaningful 20+ minute session and ask/receive one useful answer within 7 days. **Engagement:** repeat sessions per activated user, live Companion on-rate, voluntary use after two weeks, ratio of saved vs dismissed suggestions. **Trust:** evidence-replay rate, attribution correction rate, reported hallucinations per 1000 sourced answers, privacy complaints. **Reliability:** SLO, failed sessions, battery/pocket degradation. **Business:** retained paying cohorts, margin/h, conversion, CAC, payback, churn.

**Example ambitious gates (hypotheses):** pilot activation >60%, four-week active usage retention >40% among eligible users, precision on delivered actionable interventions >80%, minimal serious trust incidents, month-one qualitative preference >50% among relevant competitor users. These are decision thresholds, not market research findings and must be reconsidered for measured cohorts.

# 11. Decision log - recommendation, alternatives and rationale

| Decision | Recommended | Alternatives | Why / revisit when |
|---|---|---|---|
| Primary device | Native phone | Browser-only, wearable-first | Closest to natural user behavior; revisit hardware when demand justifies |
| UX | Text-first when screen visible; optional earbuds | Voice-only assistant | Greater social control and accessibility |
| Live AI | Event-triggered proactive with hard caps | Continuous full LLM streaming | Lower intrusion, cost and hallucination risk |
| Default privacy | Explicit capture; opt-in cloud path; visible state | Covert always-on | Legal legitimacy and long-term brand trust |
| Speech engine | Model/provider abstraction | One fixed model forever | Enables quality/cost/region improvements |
| Diarization | Nemotron evaluated, fallback path | Claim it identifies real people | Anonymous speaker tagging must be corrected/verified |
| Memory | Relational + evidence + vector hybrid | Embeddings alone, premature graph | Correctness, access control, structured decision history |
| Backend | Modular core + separate realtime workers | Microservices everywhere | Fewer distributed failure modes early |
| Sales | Technical-professional wedge, then teams | Consumer all-audience launch | Sharper ROI and evaluation, lower marketing waste |
| Pricing | Metered paid live hours | Unlimited low-price cloud compute | Predictable unit economics and premium positioning |
| AI actions | Draft-first, explicit confirmation | Silent autonomous execution | Prevents consequential mistakes and unauthorized changes |
| Launch | Production-ready vertical releases | One giant delayed launch or throwaway demo | Validates demand while preserving quality |

# 12. First 30 days: concrete founder execution program

**Days 1-5: requirements and user evidence.** Write a one-page narrative and 10 ranked JTBD, score 15-20 existing products' claims, recruit ten engineers and five consultants for observation, map permitted meeting scenarios. Finalize supported use-cases and exclusion policies. Start trademark and domain counsel checks.

**Days 6-10: physical platform truth.** Build native audio test harnesses (not a customer product) with recording, background mode, Bluetooth switching, OS interruptions, screen/pocket placements on at least four phone/earbud combinations. Record metrics and failures; document what is actually supportable. This is a research harness, not a throwaway customer demo.

**Days 11-15: speech/reasoning testbed.** Run controlled, consented meeting clips through ASR options and Nemotron 3, measure DER, WER, word/speaker alignment, streaming delay, named speaker error, cost/h. Build a fixed 100+ question source-grounding evaluation set across several meetings and inject misleading spoken instructions to test policy boundaries.

**Days 16-20: system design/security.** Establish repo, schemas, auth/tenancy, data retention diagram, ADRs, wire contracts, encrypted spool, privacy policy draft, session-event sequence diagrams and disaster scenarios. Review with a senior iOS/Android audio engineer and privacy counsel. Lock app navigation and Live Dashboard UX.

**Days 21-25: foundation services.** Implement native session lifecycle and backend realtime gateway, idempotent chunk upload, partial transcript, evidence persistence, observability, usage counters and deletion scaffolding. Test 90-min continuous capture with one supported device class, failures and restarts.

**Days 26-30: commercial validation.** Present specific flows to 20-30 participants, compare incumbent value, collect willingness-to-pay for live suggestions (not just summaries), interview 5 teams for paid-design-partner intent, analyze provider costs and choose the next release gate. Deliver proof of legal, hardware, technical and economic feasibility. Do not market unreleased features as real.

# 13. Key open questions / evidence still needed

The vision is clear, but these are launch-critical empirical unknowns: (1) does a small-screen glance help or distract during actual meetings? (2) do people want proactive spoken interventions or primarily text? (3) can enough current iPhones and Android devices meet battery and voice routing goals? (4) can a reliable microphone capture a pocket conversation without an accessory? (5) how many live prompts per hour feel genuinely valuable? (6) will users grant compliant recording permissions across work settings? (7) which users will pay $19-39 instead of using Hedy/Granola/Fathom? (8) is proprietary intervention ranking a meaningful performance advantage? (9) how much private memory can be safely persisted and deleted? (10) can cloud streaming costs stay low enough under heavy usage? These are testable questions, not reasons to abandon the ambition.

# Sources and research notes

As of 14 October 2026. Pricing pages are mutable. Sources support industry, technical, platform and legal background, not MeetSaathi-specific claims or projected metrics. Regulatory comments are not formal legal advice.

- **[S1]** Hedy official site and real-time coaching: https://hedy.ai/
- **[S2]** Hedy Nemotron announcement, Sep 23 2026: https://hedy.ai/post/nemotron-3-diarization-on-device/
- **[S3]** Hedy pricing: https://hedy.ai/pricing/
- **[S4]** Granola feature and pricing matrix: https://www.granola.ai/pricing
- **[S5]** Fathom pricing/feature matrix: https://www.fathom.ai/pricing?plan=teams
- **[S6]** Circleback pricing/features: https://run.circleback.ai/pricing
- **[S7]** Otter pricing/features: https://otter.ai/pricing
- **[S8]** Plaud and Limitless: https://global.plaud.ai/products/plaud-notepin-ai-annual-unlimited-plan ; https://www.limitless.ai/
- **[S9]** NVIDIA Nemotron 3 Diarization, Sep 23 2026; performance, anonymous speakers, 8-speaker limit, streaming buffer: https://huggingface.co/blog/nvidia/nemotron-diarization ; model/license: https://huggingface.co/nvidia/Nemotron-3-Diarization
- **[S10]** Apple App Store Review Guidelines (recording notice): https://developer.apple.com/app-store/review/guidelines/
- **[S11]** Apple AVAudioSession record/background behavior: https://developer.apple.com/documentation/avfaudio/avaudiosession/category-swift.struct/record
- **[S12]** Apple Bluetooth audio routing: https://developer.apple.com/documentation/avfaudio/avaudiosession/categoryoptions-swift.struct/allowbluetooth
- **[S13]** Android mic foreground-service background restrictions: https://developer.android.com/develop/background-work/services/fgs/restrictions-bg-start
- **[S14]** Android audio playback capture restrictions: https://developer.android.com/media/platform/av-capture
- **[S15]** Google Play prominent disclosure policy: https://support.google.com/googleplay/android-developer/answer/11150561
- **[S16]** GDPR legal grounds: https://commission.europa.eu/law/law-topic/data-protection/information-business-and-organisations/legal-grounds-processing-data_en ; EU AI Act prohibited workplace emotion recognition: https://digital-strategy.ec.europa.eu/en/faqs/navigating-ai-act ; India DPDP government announcement: https://www.pib.gov.in/PressReleasePage.aspx?PRID=2190014&lang=2&reg=3
- **[S17]** AssemblyAI pricing and realtime streaming/diarization benchmarks: https://www.assemblyai.com/pricing/ ; https://www.assemblyai.com/products/streaming-speech-to-text

# Final board-level recommendation

Build MeetSaathi with global ambition and a narrow, evidence-driven first battlefield: the highest-quality live intelligence for consented professional conversations on an ordinary smartphone. Ship a trustworthy, paid, production-intended workflow before attempting a universal AI companion. Protect the brand with unambiguous consent, precise evidence attribution, reliable screen-off behavior, clear device limitations and user-controlled intrusiveness. Validate superiority against Hedy and the conventional meeting assistants in blinded real use; do not assume it. Instrument economics before subsidizing unlimited inference. If MeetSaathi wins this initial workflow and becomes the system of record for a person's important conversations, then broader memory, workplace integrations, wearables and eventually a global conversational intelligence platform become credible expansion paths.
