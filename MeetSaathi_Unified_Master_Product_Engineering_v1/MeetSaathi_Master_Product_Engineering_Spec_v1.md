---
title: "MeetSaathi | Unified Master Product & Engineering Specification"
subtitle: "One mobile companion. Four contextual experiences. One trustworthy intelligence platform."
version: "1.0"
status: "Implementation-ready design baseline; not an implemented application"
date: "18 October 2026"
owner: "Product / Design / Mobile / AI / Platform / Trust"
---

# Executive decision

**Build one product, not four apps.** MeetSaathi is a mobile-first, permission-aware AI companion for important human conversations. It supports **Meeting, Learning, Interview, and Conversation** as contextual experiences, using the same capture engine, session lifecycle, live assistance, private voice, evidence pipeline, and memory foundation. Research/conference support starts as a preset within Learning or Conversation, with a dedicated surface only if usage justifies it.

**North-star user experience:** Start a permitted session while the phone is face-up beside a laptop; receive an occasional helpful, short, glanceable insight; move to a supported screen-off / pocket setup with optional private earbud audio; afterward, ask MeetSaathi what happened, what it means, and what to do next—without mistaking AI conclusions for what people actually said.

**What winning means:** Measurably better *end-to-end* usefulness, timing, privacy and reliability than alternatives on representative customer workflows. Not the most features, not longest summaries, not maximum AI interruptions. This document specifies a production-intended product foundation, release gates, and executable contracts. None of the target metrics below represent achieved results; all require field validation.

## Decision summary

| Question | Final v1 decision | Reason |
|---|---|---|
| One app or independent companions? | One native iOS app, one native Android app, four context packs | Consistent muscle memory and less fragmented intelligence |
| Primary CTA? | **Start Companion**, with explicit start preflight and required disclosures | Low friction without surprise capture |
| Bottom navigation? | **Home / Memories / Ask / You**; Live is an immersive session surface | Four memorable destinations; Activity inside Memories |
| Default live behavior? | **Listener + Silent Text** before user chooses proactive assistance | Avoid accidental interruptions and unearned recording expectations |
| Proactive controls? | Quiet / Balanced / Active, selected explicitly; context can suggest, never silently escalate | User control; sensitive contexts require restraint |
| Delivery options? | Text / Earbud Voice / Both, independently selected | Screen-on and pocket modes are both first-class |
| What gets remembered? | Scoped, source-labeled, editable, retention-governed items; cross-meeting memory only with consent | Avoid building a private dossier by default |
| Recording and AI help in interviews? | Independently permission-gated; mock practice always available | Assessment integrity, lawful recording and honest UX |
| Mobile technology? | Swift/SwiftUI + Kotlin/Jetpack Compose with narrow shared contracts | Direct control of latency-critical OS audio/lifecycle APIs |
| Backend first shape? | Modular FastAPI services + workers + Postgres/pgvector + encrypted object storage | Strong boundaries without premature distributed infrastructure |
| Speech stack? | Streaming ASR plus separately evaluated diarization; Nemotron 3 as candidate | Diarization is not ASR or verified identity; interchangeable providers |
| Cloud vs on-device? | Capability- and privacy-aware hybrid; explicit processing disclosure | Models, hardware and regions impose different constraints |
| Release strategy? | Quality-gated vertical slices on real devices; four contexts on shared foundations | Product-grade iteration, not throwaway prototype |

# 1. Product charter and experience principles

## 1.1 Core user jobs

1. **Follow:** Remain attentive during complicated speech without losing important context.
2. **Clarify:** Ask for concise assistance in the moment, when allowed.
3. **Notice:** Receive timely, accurate, low-distraction suggestions when explicitly enabled.
4. **Remember:** Retrieve who said what, with original source evidence and uncertainties.
5. **Reason:** Explore alternatives, explanations and risks separately from source facts.
6. **Prepare:** Return to a future conversation more informed than before.
7. **Learn:** In educational or practice contexts, build comprehension through retrieval, feedback and spaced review.

## 1.2 User promise and non-negotiables

- **Presence beats screen time:** no constant scrolling or chat-feed treadmill during a session.
- **Truthful state:** never claim “Listening,” “Recorded,” “Speaker identified,” or “Earbud connected” without observing real system state.
- **Evidence before confidence:** quoted claims must link to permitted transcript/audio with time and revision; uncertain attribution is called uncertain.
- **Silence is a correct decision:** no suggestion is preferable to a repetitive or low-value intervention.
- **No public audio surprise:** private spoken output defaults off; loss of private route immediately mutes it.
- **Transparent capture:** platform indicators plus prominent in-app state and applicable participant notice/consent; user starts recording deliberately.
- **No deception:** no prohibited covert interview assistance, impersonation, voice-based demographic inference, personality/emotion diagnosis, or cross-space memory leakage.
- **Graceful degradation:** captions, notes, and local capture remain usable to the extent safely possible when AI/network fails.
- **User control over memory:** selective keep, correct, export and delete, with bounded deletion and provenance invalidation.

## 1.3 Audiences and positioning

First depth target: engineers, technical workers, product leads and serious learners; use permitted meetings and mock interviews for validation. General conversations and lectures use the same core product. Worldwide readiness requires multilingual evaluation, accessible controls, reliable low-end-device behavior, clear privacy, and region-sensitive processing—not an unsupported claim of global coverage at first release.

**Category:** Personal Conversational Intelligence. **Working tagline:** “Be present. Understand more. Remember what matters.” The name remains a working brand pending trademark/domain/store checks.

# 2. Unified information architecture

## 2.1 Navigation graph

```text
Home ─── Start Companion ── Context chooser ── Session preflight ── Live Focus
 │                                   │                                │
 │                                   └── No mic / Notes-only ── Notes  │
 ├── Continue active session (persistent mini-bar)                   ├─ Ask sheet
 ├── Prepare (recent topic/context)                                  ├─ Current detail / Why
 └── Recent memories                                                 ├─ Transcript / Sources
                                                                     ├─ Audio route / Assistance
Memories ── Spaces ── Sessions ── Recap ── Evidence / Correction      └─ End / Keep / Discard
       └── Search / Decisions / Lessons / Interview goals / Review
Ask ── Remember | Think | Learn | Prepare  (with explicit scope chip)
You ── Devices / Assistance / Language / Privacy / Accessibility / Export
```

**Why:** the four contexts must not create four separate home tabs or duplicate storage. The active session gets a focused full-screen surface; it can be recovered from every tab and device notification when available.

## 2.2 Context packs and behavior changes

| Context pack | Live priority | After session | Context-specific requirements |
|---|---|---|---|
| Meeting | Decisions, trade-offs, commitments, risks, ownership | Decision timeline, recap, next agenda | No proposal auto-labeled as agreement; speaker correction propagates |
| Learning | Follow concepts; **Explain this** and **Save moment** | Teach-back, quizzes, course memory, spaced review | Focus default; no false claims about diagrams not captured |
| Interview | Practice challenge; *permitted* live concise coaching | Evidence-backed debrief, gap analysis, next-round prep | AI-use gate distinct from recording; no covert test assistance |
| Conversation | Low-interruption listening, respectful question prompts, personal capture choices | Reflection, selective memory, suggested follow-ups | Default minimal retention; no inference of private motives |

**Research/conference:** initial Learning preset (`Talk/Seminar`) with concepts, questions and references; can become a dedicated experience after validated demand. Sales/customer discovery can start as Meeting preset; healthcare and legal use require domain governance before specialized launch.

## 2.3 Independent runtime controls

| Dimension | Choices | Initial behavior | Can change during session? |
|---|---|---|---|
| Context | Meeting / Learning / Interview / Conversation | User selection; last non-sensitive choice may be suggested | Yes, with audited context switch and policy re-evaluation |
| Capture source | Phone microphone / authorized desktop bridge / imported file / none | Phone microphone requested only at start | Yes only after re-preflight; no invisible switch |
| Capture state | Off / Starting / Live / Paused / Interrupted / Stopping / Finalizing | Off | User action or explicit OS change |
| Assistance | Listener / Ask / Companion | Listener, user opts into proactive | Yes; disable immediately |
| Proactive intensity | Quiet / Balanced / Active | Quiet until chosen; sensitive contexts stay quiet without positive opt-in | Yes; cannot override policy gates |
| Response output | Text / Private voice / Both | Text | Yes; route checks before voice |
| Retrieval | Current / Selected space / Selected project / General knowledge | Current session | Yes; never silently broaden |
| Retention | Ephemeral / Review to keep / Selected automatic retention policy | Review-to-keep in ordinary contexts, ephemeral suggested for sensitive | Yes with explicit effect on existing data |
| Processing | Regional cloud / supported on-device / hybrid | Shown before capture | Requires clear policy and capability explanation |

**Invariants:** `capture_off -> no ASR/transcript derived from live audio`; `private_voice_active -> verified private route`; `remember_answer -> cited user-authorized sources or explicit no-evidence`; `deleted_space -> excluded from retrieval immediately`; `interview_prohibited -> zero live coaching even when mic is permitted`.

# 3. Global visual and interaction system

## 3.1 Brand tokens

| Token | Dark | Light | Usage |
|---|---|---|---|
| Canvas | `#081522` | `#F4F8FA` | Background |
| Surface | `#132839` | `#FFFFFF` | Cards/sheets |
| Surface elevated | `#183B38` | `#EAF6F3` | Primary insight |
| Accent | `#70E6D0` | `#087968` | Active emphasis; not status alone |
| Main text | `#F0F8F8` | `#142630` | Contrast-tested |
| Secondary text | `#A0B8C6` | `#51636F` | Supporting copy |
| Caution | `#FFCF8A` | `#9C6000` | Uncertain/pending |
| Stop/error | `#FF9BA7` | `#A72641` | Capture loss/destructive actions |

Use system fonts with dynamic sizing; iOS target >=44×44pt, Android >=48×48dp for critical controls. Proposed spacing scale 4/8/12/16/24/32 logical units; radius 12/18/24. Use animation sparingly, honor reduced-motion and do not shift the end-session control when cards arrive. Never rely on color alone for recording/permission status.

## 3.2 Screen hierarchy and contracts

**Universal screens (U):**

- **U01 Welcome:** one-sentence promise, demo without permissions, privacy explanation; CTA Get started.
- **U02 Home:** Start Companion dominates; last safe mode shortcut, active-session bar and recent memory. Do not show an analytics dashboard by default.
- **U03 Context chooser:** four cards, optional presets, editable title. Keep a short recent choice instead of forcing selection every time.
- **U04 Preflight:** capture source, measured mic levels, microphone permission, relevant participant disclosure/authorization, permitted AI status for Interview, desired output, local/cloud processing, expected storage and private route. No start on unresolved hard gate.
- **U05 Live Focus:** fixed header (capture state, timer, audio route), topic/last question, one high-value insight or “Listening quietly,” small live transcript drawer, Ask/Save/Pause/End controls.
- **U06 Ask overlay:** three answer styles (Remember, Think, Learn), optional Prepare action; explicit scope chip; compact answer with expandable reasoning and tappable evidence.
- **U07 Transcript/Evidence:** provisional/final labels, per-turn time, speaker aliases, original audio source if retained, correction and report controls.
- **U08 Voice & devices:** observed input/output routes; private-voice test; switch output; route-change warning and mute action.
- **U09 Session end:** capture stops immediately; saving choice and finalizing progress shown separately; retry finalization without re-recording.
- **U10 Recap:** summary grounded in sources, decisions/unknowns/actions, notes/corrections, deliberate keep/discard.
- **U11 Memories:** scoped spaces, search, session timeline, saved concepts/goals and data provenance.
- **U12 Ask across sessions:** retrieval selector with visible boundary, query citations, no cross-space leakage.
- **U13 You/Settings:** assistance cadence, retention, permissions, devices, accessibility, processing region, data export/deletion.

**Context add-ons (C):** Meeting decision ledger/compare/prep; Learning explain sheet/study studio/course graph; Interview goal/mock/debrief/answer lab; Conversation reflection/selective memory. They reuse Universal navigation, voice and source components.

## 3.3 Live Focus layout

```text
┌─────────────────────────────────────────┐
│ Meeting · 00:24:38       ● Recording     │  sticky header; route status
│ System Architecture Review              │  modest topic/intent
│                                         │
│  ☆ Suggested consideration               │  only one prominent card
│  Clarify whether ordering is required   │  12-28 words preferred
│  per customer or across all events.     │
│  Why this?     Save     Dismiss          │
│                                         │
│  [collapsed] Live captions / transcript │  no endless scrolling
│                                         │
│  Ask MeetSaathi ...                      │  on-demand query
│                                         │
│  Save moment     Pause       End         │  persistent safe controls
└─────────────────────────────────────────┘
```

**Empty insight:** `Listening quietly. Ask whenever you need.` **Poor input:** `Microphone audio is unclear. Some context may be missing.` **Disconnected output:** `Private voice paused - earbuds disconnected.` **Capture interrupted:** `Recording stopped unexpectedly at 12:43; earlier audio is safe.` Never animate a fake waveform when permission is denied or audio is absent.

## 3.4 Interaction budget

- Main insight: 12-28 words preferred, maximum 45 before expansion. Avoid stacked insight notifications.
- Answer overlay must not permanently hide Pause/End; users can dismiss with one obvious action.
- Dismissed suggestions cannot immediately recur with superficial rewording.
- Voice output never reads a full paragraph during someone else's speech by default; short <= ~7-second snippets as initial design hypothesis.
- Notifications must name an actual state rather than euphemistic “AI processing.”
- App should preserve one-handed operation and at-a-glance readability from a phone placed beside a laptop.

# 4. Complete user journeys

## J1 First open and first session

1. Preview what the app does using an explicitly labeled sample conversation; no early microphone permission prompt.
2. Choose Meeting / Learning / Interview / Conversation and desired output; explain how to stop.
3. At first real Start, show only permissions relevant to selected source and disclose processing.
4. If recording is prohibited, enter Notes-only / Mock / Private Reflection without pretending to hear others.
5. When compliant, record from a foreground-visible start and reflect OS mic indicator and app status.
6. Start a 10-second monitored audio check; if volume is low, warn and allow correction.
7. Live screen displays quiet listening, not fabricated suggestions; suggestions arrive only from real contextual evidence.

**Acceptance:** first user can begin a truthful, permitted session in a small number of decisions; no onboarding dead-end when permission is declined.

## J2 Phone face-up beside laptop

Select Silent Text; see capture indicator + transcript preview; receive one concise, source-related card. Tap `Why?` to inspect grounding, save or dismiss. Ask a question in text. If using laptop headphones, explain that the phone microphone may not hear remote participants; guide to authorized desktop companion/integration or notes instead of pretending it can.

## J3 Pocket and earbuds

From an already started session, verify actual private output route (and confirm mic source). Allow screen to lock. Capture stays active only within OS-supported/background-approved lifecycle. Deliver one short voice cue during suitable listening gap. When route disconnects, immediately stop voice playback; never fall back to public speaker automatically. Show persistent capture state and recovery when unlocked. Low audio quality in pocket -> warning; do not hallucinate remote voices.

## J4 Learning lecture

Default Focus/Listener. `Explain this` uses current permitted transcript and relevant prior course context. `Save moment` marks uncertain time range; after class, suggest user-reviewed concept list, a short teach-back conversation and retrieval practice. Distinguish what lecturer said vs independent explanation. If lecturer uses a diagram that was not captured, state it plainly. No mic -> notes-only syllabus / uploaded materials / manual questions.

## J5 Interview

Preparation: goal, job description, question styles, role-specific mock; mock interviewer asks adaptive follow-ups and gives feedback. In real interviews, separate `Is AI permitted?` and `May this be recorded?`. If AI prohibited, disable live advice and text/voice prompts, regardless of user's recording permission. If recording prohibited, use private post-interview recollections, not secretly captured evidence. No stealth overlay or covert answer feeding. Post-round debrief lists actual recorded questions only if captured; recollected questions get a `User recollection` tag.

## J6 Everyday conversation

Default retention minimized; user can record with proper consent, or choose private reflection afterward. Suggest respectful clarifying questions, not manipulation or emotion/personality inference. End-of-session screen offers `Keep selected`, `Export my notes`, `Discard`. Never surprise the user by recalling a sensitive personal conversation in a work meeting.

## J7 Full memory loop

User asks “What did we decide last Tuesday?” -> scope Work > Architecture Project -> top sourced answer with speaker confidence and time. User corrects misattribution -> revision saved and dependent summaries/embeddings/jobs invalidated. Next prep includes only revised valid evidence. Deletion removes memory access immediately and triggers downstream purge with displayed completion state.

# 5. Intelligence runtime and proactive intervention

## 5.1 Functional pipeline

`Audio or notes -> permissions gate -> streaming ASR -> speaker activity -> alignment -> provisional transcript -> topic/current intent -> candidate insights -> safety/policy/evidence filters -> timing + ranking -> text or private voice -> feedback -> user-reviewed memory`.

**Important:** Nemotron diarization answers *when anonymous speakers talk*; it does not perform speech recognition or establish who they are by real name. NVIDIA advertises support for up to eight simultaneous anonymous speaker channels and configurable buffering; use an alternative or human review when source conditions exceed tested limits. End-to-end latency must measure ASR, diarization, reasoning, transport, and audio synthesis, not just a model's buffering latency. [S1]

## 5.2 Insight contract and intervention policy

Each generated candidate contains: `id`, `context`, `kind`, `short_text`, `long_text`, `evidence_refs`, `source_kind`, `source_confidence`, `relevance`, `timeliness`, `sensitivity`, `risk_level`, `model_version`, `policy_version`, `expires_at`. Validation is **gated** before scoring. If prohibited by context/permissions, missing evidence for an attributed claim, a weak capture, or no safe output path, return `SUPPRESS` rather than generating fallback filler.

Candidate types: `CLARIFY`, `TRADEOFF`, `DECISION_UNRESOLVED`, `FOLLOWUP`, `LEARN`, `CONNECTION`, `REMINDER`, `TRANSLATION`, `INTERVIEW_PRACTICE`, `NO_ACTION`.

Scheduler steps:

1. **Policy:** is capture, external reasoning, and this kind of live assistance permitted?
2. **Evidence:** does claim cite current authorized content? If not, label outside knowledge or abstain.
3. **Usefulness:** actionable, novel, on-topic, not already answered, meets context-specific relevance threshold.
4. **Temporal:** suppress while user is speaking; do not play over speech; queue briefly, expire stale suggestions.
5. **Deduplicate:** cluster semantically equivalent candidates across recent windows; maintain dismiss history.
6. **Interrupt budget:** proposed Balanced cooldown 3-5 min (tunable via data), Active 1-3 min with upper cap, Quiet 0 proactive.
7. **Output:** text when available; voice only on verified private route and explicit selection; avoid narrating sensitive information unexpectedly.
8. **Feedback:** allow Useful / Not useful / Too frequent, but never require constant ratings.

**Ranking hypothesis:** quality = usefulness * grounding * timeliness minus distraction, false-attribution and sensitivity penalties. These are explainable sub-scores; no opaque single-number threshold for disallowed speech. The system must produce `NO_ACTION` often in natural conversation.

## 5.3 Ask response grammar

- **Remember**: answer from permitted evidence only. Each attributed factual statement has sources (`session`, timestamp, `utterance_version`); if no source, say `I can't verify that from the available conversation.`
- **Think**: independent evaluation, alternatives, counterarguments, unknowns. Mark `MeetSaathi analysis`, not a transcript fact.
- **Learn**: pedagogical explanations; cite source when tying to captured material, label general knowledge, ask one checking question when useful.
- **Prepare**: follow-ups, actions, study plans or agendas; proposed actions require review and explicit approval.

Prohibit retrieval across tenant or space boundary even if semantic vector similarity is high. Meeting text is untrusted content and cannot issue application/system instructions by speech.

## 5.4 Audio choreography

- ASR and diarization should not treat the AI's own speech as an additional participant: tag playback windows, use acoustic echo handling where possible, and suppress attribution to TTS output.
- Voice cues should wait for detected natural pause and favor user's listening periods. If user begins speaking, duck/stop cue promptly.
- If earbud disconnects, `private_voice=false` immediately; do not auto-route to phone speakers. Resume requires a fresh route check.
- Unsupported combination `phone mic + earbud output` must result in an honest choice (headset mic, text only, or supported alternative), not a silent device switch.
- Voice privacy is separate from capture privacy: switching off AI sound does **not** end recording; switching off microphone ends capture but may retain notes-only Ask.

# 6. Persistent memory and source-of-truth design

## 6.1 Evidence model

1. **Raw source (optional, policy-controlled):** encrypted audio, imported file, or user note.
2. **ASR transcript:** provisional then finalized words and timestamps; revisions preserve prior versions.
3. **Speaker diarization:** anonymous channels with model confidence and overlap flags; identity mapping only with user correction and appropriate permission.
4. **Structured claim:** decision, question, action, lesson, memory fact, quote, suggestion; link to source spans and status.
5. **Derived memory:** user-approved facts and topic summaries with provenance, scope, lifespan and version.
6. **Independent analysis:** separate model-generated assessment, never merged into evidence or represented as a quote.

**Key distinction:** `proposal ≠ decision`, `AI idea ≠ participant statement`, `user recollection ≠ verified recording`, `anonymous speaker ≠ identified human`.

## 6.2 Decision and learning lineage

Meeting: `PROPOSED -> DISCUSSED -> ACCEPTED | REJECTED | DEFERRED -> SUPERSEDED`, each transition backed by a source and permitted correction. If no explicit agreement, keep `UNRESOLVED`. Learning: `HEARD -> EXPLAINED -> PRACTICED -> RETAINED (only when evidence of mastery)`, with user-controlled revision cadence; a quiz score does not prove lifelong mastery. Interview: `QUESTION -> RESPONSE -> FEEDBACK -> RETRY -> REVIEW`, preserving mock vs real vs recalled origin.

## 6.3 Multi-scope retrieval and deletion

Spaces `Personal`, `Work`, `Learning`, optional organizations. Search pipeline: authenticated subject -> tenant+space ACL filter **before** retrieval -> structured and semantic search -> rerank with source freshness/version -> evidence assembly -> answer with citations. Do not default to All spaces. Personal conversations never enter an enterprise share surface by inference. On deletion: immediately revoke retrieval and access; enqueue auditable object/audio/vector/cache/derived purge; status `REQUESTED -> IN_PROGRESS -> COMPLETE | ACTION_REQUIRED`; data retention in backups governed by published policy and legal obligations, never promise instant physical backup erasure. Exports include user data and source metadata, redacting other participants when legally necessary.

## 6.4 Speaker corrections

Speaker identity mapping may be session-local, not silently global. Correction creates `speaker_mapping_version` and revisions of utterance attribution, invalidates impacted quote/action/decision references, reindexes search, and alerts the user if a previous share becomes inaccurate. Preserve auditable originals with access restrictions and retention limits. Never infer person's name from timbre alone.

# 7. Session, audio and connectivity state machines

## 7.1 Recording state machine

```text
IDLE --Start pressed--> PREFLIGHT
PREFLIGHT --permissions+capabilities+notices satisfied--> STARTING
PREFLIGHT --denied / unsupported--> NOTES_ONLY or IDLE
STARTING --audio callback confirmed--> RECORDING
STARTING --timeout/OS denial--> ERROR
RECORDING --Pause--> PAUSING --> PAUSED (mic release/frames stopped)
PAUSED --Resume and permission/route check--> STARTING
RECORDING/PAUSED --End--> STOPPING --> FINALIZING --> COMPLETED
RECORDING --OS interruption/input loss--> INTERRUPTED
INTERRUPTED --user resumes safely--> STARTING
INTERRUPTED --user ends / expiry--> STOPPING
FINALIZING --worker failure--> FINALIZATION_RETRYABLE (capture remains stopped)
FINALIZATION_RETRYABLE --retry--> FINALIZING
```

**State invariants:** `Recording` means actual audio buffers arrive and device route verified; no frames sent during Paused; End makes mic stop promptly, regardless of cloud finalization. A session can be `COMPLETED_PARTIAL` if portions were interrupted. UI must communicate missing intervals. Use monotonic local offsets plus server time mapping for timestamp consistency.

## 7.2 Network and uploader state

Audio chunks (e.g., 0.5-2s logical units) receive monotonic `sequence`, `sample_rate`, `capture_start_ms`, `sha256`, `device_id`, `session_id` and encryption metadata. Store temporary encrypted local spool subject to storage policy. Uploader retries with idempotency keys; server stores `(session_id, sequence)` unique, verifies checksum and ACKs watermark. On reconnect, resume from acknowledged cursor, never duplicate segments in transcript. Local spool stops growing at explicit storage cap; show a clear limit rather than risking disk exhaustion. Retention deletion covers spooled chunks as well as server storage.

## 7.3 Failure decision matrix

| Failure | User-visible truth | System action |
|---|---|---|
| Microphone denied | `Microphone not enabled` | Offer settings or Notes-only; no fake waveform |
| Bluetooth disappears | `Earbud voice paused` | Mute private TTS immediately, preserve eligible capture route after check |
| Input route changes unexpectedly | `Audio source changed` | Pause/suppress if quality unverified; run preflight |
| Network unavailable | `Working offline - AI suggestions unavailable` if local spool works | Encrypted spool, resumable upload, no hallucinated live cloud analysis |
| Audio quality poor | `Some voices may be missing` | Lower confidence, avoid speaker-specific claims |
| ASR falls behind | `Captions delayed` | Maintain capture, apply backpressure and skip nonessential insights |
| Diarization > tested speaker support | `Speakers need review` | Anonymous / unassigned; alternate pipeline or manual edit |
| Finalization fails | `Recording saved; recap is being retried` only when saved verified | Retry idempotently; show partial state |
| Privacy permission revoked | `Capture ended` | Stop capture and uploads immediately; invoke retention policy |
| Cross-space query denied | `That memory isn't available in this space` | Deny before retrieval; audit without exposing content |
| AI model timeout | `Suggestions temporarily unavailable` | Recording can continue; no stale late voice |

# 8. Production technology and deployment

## 8.1 Mobile architecture

**Android:** Kotlin, Jetpack Compose, lifecycle-aware foreground capture using declared microphone FGS, AudioRecord/AudioManager, encrypted local spool, explicit OS status. **iOS:** Swift, SwiftUI, AVAudioEngine/AVAudioSession category/play-and-record as needed, supported background audio mode, route/interruption handlers, Keychain and encrypted local spool. Verify Apple's background recording entitlements and store review requirements on target versions. Android 12+ restricts FGS starts from the background; higher versions add microphone service conditions. iOS HFP may route *both* microphone and output to the headset. Do not promise universal routing. [S2-S4]

Both clients implement the same state-machine spec, event schema and design tokens. Share generated protobuf/OpenAPI contracts, not a huge cross-platform audio framework. Native accessibility semantics, localization, RTL, Dynamic Type/font scale, TalkBack/VoiceOver and battery/memory profiling are required.

## 8.2 Backend architecture (logical)

```text
iOS / Android / optional authorized desktop bridge
    │  OAuth/OIDC + device-bound session token; encrypted stream
    ▼
API Gateway / Realtime Gateway ──> Session + Policy + Consent service
    │                                          │
    ├── audio ingress ──> encrypted spool/S3 ─┼──> durable job queue
    │                  └─> ASR adapter         │       ├─ final ASR + diarization
    │                       └─> diarization    │       ├─ structured extraction
    │                           └─> aligner    │       ├─ embeddings / memory
    ├── text events ──> live context engine    │       └─ deletion / reindex
    │                       └─> gated insight service
    │                                  └─> WebSocket/SSE text events
    ├── Ask API ──> ACL-aware retrieval ──> grounded LLM
    └── TTS gateway ──> authenticated private output routing
                     └─> PostgreSQL + pgvector / encrypted object storage
```

Start with deployable modular services in one backend repository: `identity_policy`, `session`, `audio_ingest`, `speech`, `context`, `interventions`, `memory`, `ask`, `billing`, `ops`. Separate compute-intensive inference workers from API processes; don't require Kafka, Neo4j or Kubernetes until load/security measurements justify them. Use Postgres transactional outbox for durable state events; redis cache/broker may be used for nonauthoritative ephemeral work only. For production durability, durable queue/managed message service or Postgres job model with leases, retries, and DLQ is mandatory.

## 8.3 Recommended provider abstractions

- `AsrEngine`: streaming partial/final segments with language, confidence, clock offsets, word timestamps.
- `Diarizer`: speaker turn intervals with overlap, anonymous IDs; Nemotron 3 a tested candidate, not mandatory lock-in.
- `Aligner`: canonical segmentation between ASR and diarizer using stable source offsets.
- `Reasoner`: structured, citation-oriented prompt output, strict tool allowlist, per-space policy.
- `SpeechSynth`: private cue TTS with cancelability, min buffering and observed routing.
- `Embedder/Retriever`: compatible embedding versioning, ACL-filtered queries, quality evaluations.

All adapters expose version, language capability, expected latency, resource/cost metrics, and fallback health. Never automatically send sensitive audio to a different vendor/region without policy approval and disclosure.

## 8.4 Region, tenancy and identity

`tenant_id` and `space_id` are mandatory on all persisted content and authorization paths. Enforce membership on the server, including PostgreSQL row-level security or equivalently verifiable isolation; never trust tenant IDs only from client JWT claims without server validation. Store regional residency preferences and provider location. Encrypt transport (TLS), server objects (per environment/tenant strategy) and local chunks; keys managed in a KMS/HSM-backed platform. Use short-lived upload tokens and least-privilege workers. Support account recovery and per-device revocation.

## 8.5 Model ops and evaluation pipeline

Version everything: ASR model, diarizer, alignment, prompt templates, reasoner, retrieval schema, safety gates. Offline evaluation datasets include overlap, multiple accents/languages, room reverberation, code-switching, pocket fabric noise, quiet/fast speakers, and 1-8 speakers; create a separate >8 speaker fallback benchmark. Use speaker confusion, WER, timestamp alignment, citation correctness, unsupported assertion rate, intervention precision, speech timing and total glass-to-ear latency. Disallow model deployment on aggregate benchmark wins when a critical cohort regresses.

# 9. Security, privacy and integrity model

## 9.1 Threat register

| Threat | Failure mode | Control |
|---|---|---|
| Undisclosed capture | Participant unaware of live recording | User-confirmed eligibility/notices, prominent UI + OS indication, permissions, organization policy |
| Prompt injection spoken in room | Transcript contains “ignore your rules/send notes” | Treat speech as untrusted data; structured tools allowlisted; no privilege elevation |
| Cross-tenant leakage | Vector match returns someone else's text | Tenant+space ACL prefilter, RLS, negative security tests |
| Fake participant attribution | ASR diarization mismatch creates false quote | Speaker labels provisional, user correction, citation versioning |
| Speakerphone privacy leak | Earbud disconnect routes private output publicly | Hard fail-closed mute on disconnect; explicit recovery check |
| Credential/token replay | Device compromised; session stream hijacked | Short-lived tokens, device binding, session revocation, TLS, replay detection |
| Unauthorized memory export | Sharing reveals participant data | Audience-specific share review, least access, link expiry, revocation |
| Sensitive retention | Long-lived audio/biometrics without need | Separate audio/transcript/memory retention, data minimization, deletion queue |
| Reidentification | Linking private conversations to person globally | Session-scoped aliases by default, user+policy-approved mapping only |
| Interview rule breach | Covert real-time answer suggestions | Independent AI-use permission gate; disallowed live assistance remains disabled |
| Model hallucinations | False agreement/actions inferred | Typed statuses, citation audit, abstention, user corrections |
| Deletion orphaning | Embeddings/derivatives persist | Provenance-driven cascading invalidation/purge and verifiable jobs |

## 9.2 Consent and processing UX

Recording permission, processing permission, share permission and memory retention are distinct user choices. Organizational recording rules can disallow all capture regardless of user settings. For minors, education, healthcare or regulated business use, shipping requires region-/institution-specific legal and security review. Do not silently capture during boot, hidden background launch or revoked permissions. In jurisdictions that require all-party consent, app should surface appropriate workflow; this is product architecture, not legal advice. User must be able to stop immediately.

## 9.3 AI actions and data scope

Suggestions may propose a task, email, reminder, or calendar entry but **must not create external actions without explicit review and scoped authorization**. Tools never execute instructions embedded in speech/transcripts. Model logging defaults to redacted metadata, not raw transcripts; production diagnostics use explicit, time-limited privacy controls. Users get data portability and deletion workflow in Settings. Consent receipts record purpose, participants/notice basis as user-attested when relevant, region, time, policy version and capture mode.

# 10. Unified API and realtime contract (normative)

Use REST for durable resources, WebSocket for low-latency events, and optional HTTP event stream for receive-only fallbacks. All mutations use `Idempotency-Key` and server authorization. Every event has `event_id`, `schema_version`, `session_id`, `sequence`, `created_at`, `type`, `payload`. Client ACKs reconnect cursor; server MUST tolerate duplicates and out-of-order arrival where declared.

## 10.1 Initial REST surface

| Method/path | Purpose | Security |
|---|---|---|
| `POST /v1/sessions` | Create preflight session scoped to space/context | Auth, ACL, policy |
| `POST /v1/sessions/{id}/start` | Start authorized capture, issue ingest credential | Consent and capabilities rechecked |
| `POST /v1/sessions/{id}/pause` | Halt capture; acknowledge stop watermark | Owner/editor only |
| `POST /v1/sessions/{id}/resume` | Revalidate and resume | Fresh route/permission gate |
| `POST /v1/sessions/{id}/stop` | Stop capture, schedule finalization | Idempotent; always end live tokens |
| `GET /v1/sessions/{id}` | State, gaps, finalization status | Space ACL |
| `GET /v1/sessions/{id}/utterances` | Timestamped and versioned transcript | Space ACL |
| `PATCH /v1/sessions/{id}/speakers/{alias}` | Correct alias with revision provenance | Explicit editor permission |
| `POST /v1/sessions/{id}/ask` | Grounded query in explicit scope | Retrieval ACL and spend gate |
| `POST /v1/sessions/{id}/insights/{id}/feedback` | Dismiss/useful/too frequent | Owner scope |
| `GET /v1/memories` | Filtered search/pagination | Tenant/space isolation |
| `POST /v1/memories/retain` | Approve selected evidence as memory | User opt-in |
| `POST /v1/exports` | User-reviewed export job | Reauthentication for sensitive scope |
| `DELETE /v1/sessions/{id}` | Tombstone + purge workflow | Auth, legal retention rules |

Companion QA artifact includes OpenAPI sketch and database DDL as a starting implementation contract; API names/version are recommended, not current deployed endpoints.

## 10.2 Canonical event types

- `session.state_changed` includes `previous`, `current`, `reason`, `audio_watermark_ms`.
- `audio.chunk_ack` includes `received_through_sequence`, `gap_sequences[]`, `checksum_confirmed`.
- `transcript.partial` is explicitly replaceable; `transcript.final` has `utterance_id`, `revision`, `speaker_alias`, `start_ms`, `end_ms`, `text`, `speaker_confidence`, `source_chunk_range`.
- `insight.candidate` never leaves server policy layer; `insight.delivered` has short text, source refs, expiry, policy version and delivery route.
- `voice.route_lost` causes client hard mute and server TTS cancellation.
- `memory.invalidated` carries affected claim/revision IDs; client stops displaying cached stale citations.
- `session.finalization_progress` gives status and retryable/terminal failures without claiming completion early.

## 10.3 Performance/error contract

Standard error: `{code, user_message, retryable, correlation_id, details?}`. Avoid leaking raw source text in errors/analytics. `409` state conflict, `403` policy/ACL denial, `422` failed preflight, `429` quota/rate limits, `503` temporary inference unavailable. Client implements backoff, cancellation and concurrency exclusion. `end` and `mute` must remain responsive when external inference is unavailable.

# 11. Observability, SLOs and measurement

**The figures below are candidate acceptance targets to validate with real users, not achieved benchmarks.** Measure by hardware tier, language, accent, route, network and context pack.

| Metric | Initial target / gate | Measurement |
|---|---|---|
| Crash-free capture sessions | >=99.8% of supported sessions | Device telemetry, real field sessions |
| 90-minute capture continuity | >=99.5% with no *unannounced* gap | Audio watermark/gap audit |
| Partial caption freshness | p95 <=2.5 seconds from end-of-phrase on supported network | Instrumented latency traces |
| Proactive text delivery | p95 <=6 seconds after qualified event | Candidate triggered -> rendered card |
| Ask private audio initial response | p95 <=7 seconds where voice route supported | User query -> intelligible audio |
| Citation correctness | >=98% in audited sourced claims | Human annotated evidence audit |
| False speaker attribution | Set cohort-specific target after evaluation | Corrected human diarization labels |
| Balanced suggestion precision | >=80% useful among delivered on target cohort | Audited blinded annotations |
| Balanced interruption rate | <=1 unwanted per 30 minutes | Explicit negative feedback/observer audit |
| Capture stop reaction | mic release shown immediately; bounded device-specific OS latency | OS instrumentation |
| Deletion from active retrieval | Immediate after authorization success | Negative retriever tests |

Also track completed meaningful sessions per active user (north star), one-week return rate, answer trust, intervention dismiss rate, successful recovery, battery/thermal drain, and variable compute cost per processed hour. Avoid optimizing for the number of interruptions or hours recorded.

# 12. Shipping and implementation program

## 12.1 Single monorepo and module ownership

```text
meetsaathi/
  apps/android/                  # Kotlin, Compose, audio foreground service
  apps/ios/                      # SwiftUI, AVAudioEngine, route manager
  apps/desktop-bridge/           # optional; deferred until permissions/integration approved
  backend/app/api/               # FastAPI HTTP + websocket endpoints
  backend/app/domain/            # sessions, policy, consent, speakers, decisions
  backend/app/speech/            # ASR, diarization, alignment adapters
  backend/app/intelligence/      # context, intervention, ask, citations
  backend/app/memory/            # retrieval, review, embeddings, deletion
  backend/app/workers/           # durable jobs, reindex, purge, finalization
  packages/contracts/           # openapi, websocket schemas, generated clients
  packages/design/              # tokens, UI copy, icons, localization keys
  infra/                        # IaC, secrets, deploy, dashboards
  evals/                        # datasets, prompts, regression gates, blind comparison
  docs/                         # ADRs, threat model, release checklist
```

Organize by responsibilities, not the four product modes. Their differences live in versioned `ContextPolicy` configurations and specific UI flows, not copies of capture/memory code.

## 12.2 Engineering vertical slices and acceptance gates

**Gate 0: Foundations.** Repo, auth, workspace/space ACL, UI tokens, event/OpenAPI schemas, CI, code signing, test devices, audio/consent policy. Exit: negative space-leak test and data erasure path in staging.

**Gate 1: Trusted real session.** User can start/stop an authorized recording on both platforms, screen off within supported restrictions, persist encrypted audio with retry, observe route and gap state. Exit: 90-minute device and reconnect tests; stop always works.

**Gate 2: Accurate words and speakers.** Streaming transcript, provisional/final semantics, Nemotron candidate and fallback, anonymous speaker correction, timestamps, source playback. Exit: human annotated quality thresholds for representative audio; correction propagates.

**Gate 3: Useful quiet intelligence.** On-demand Ask plus source-grounded answers, single-card scheduler, abstention, context pack policies, user feedback. Exit: blind user usefulness benchmark and hallucination/citation audit.

**Gate 4: Pocket voice.** Verified private audio output, route-state handling, voice pauses/barge-in, no public fallback, battery profiling. Exit: multi-device earbud matrix including disconnect/unexpected pairing and network loss.

**Gate 5: Memory and context packs.** Approved memories, scoped cross-session retrieval, Meeting decisions, Learning practice, Interview mock/feedback, Conversation reflection, export/delete. Exit: provenance/permission tests and cross-context UX usability validation.

**Gate 6: Public release quality.** Accessibility/localization, legal review, security penetration test, abuse testing, crash fixes, analytics/privacy audit, pricing limits, support workflows and app-store approval. No dates promised before staffing/provider/device validation.

## 12.3 First 20 engineering tasks (in priority order)

1. Freeze this master v1 product contract and publish ADRs; establish change-control.
2. Register app IDs and build Android+iOS shells from same design tokens.
3. Implement account, tenant, spaces, short-lived session tokens and least-privilege roles.
4. Implement separate policy engine for consent, capture, AI help, voice and retention.
5. Implement client session state machine with a fake **explicit test audio source** only in unit tests.
6. Implement real native mic capture with OS indicators and start/pause/end.
7. Add encrypted local spool, sequence ACK and resumable upload.
8. Add secure backend ingress and object checksum verification.
9. Instrument OS route changes and microphone health.
10. Add accessible Live Focus dashboard and truthful status copy.
11. Integrate streaming ASR adapter with word/source timestamps.
12. Integrate candidate diarization; preserve anonymous speaker uncertainty.
13. Add aligner and transcript revision/version schema.
14. Implement Ask Remember with strict citations and abstention.
15. Implement single-card intervention engine and user controls.
16. Implement private TTS cancellation and earbud disconnect fail-closed behavior.
17. Implement memory retention review, corrections and cascading reindex.
18. Add context pack Meeting/Learning/Interview/Conversation policies and specialist after-session views.
19. Create evaluation corpora, negative permission tests and compatibility matrix.
20. Run field pilot and instrument meaningful session value, latency, unwanted interruptions and retention.

## 12.4 Definition of done for every production feature

Working on actual target phone; accessibility and localization supported; auth/policy enforced; offline and interruption paths specified; source/citation correct where relevant; telemetry with privacy budget; tests in CI; rollback path; documented user-facing failure messages; cost limit and data retention specified; product acceptance signed off. Static design preview alone never constitutes done.

# 13. Conflict-resolution ledger (supersedes older experience docs)

| Earlier ambiguity / clash | Unified resolution |
|---|---|
| Some drafts said Companion Balanced by default vs Silent | New sessions begin **Listener + Text**. Balanced only after explicit selection; remembered choices may be suggested, not silently applied in sensitive settings. |
| `Listener / Ask / Companion` mixed with `Quiet / Balanced / Active` | Assistance *mode* decides whether unsolicited suggestions occur; intensity determines rate **only when Companion enabled**. |
| “One tap” implied automatic mic recording | First time or changed policy/source always uses preflight; returning compliant sessions minimize taps without bypassing notices. |
| “Face-down mode” implied phone can detect placement | Device/display state may change the UI, but never infer acoustic position/reliable mic or unlock private voice without explicit selection. |
| Earbud voice assumed phone mic remains source | Runtime route capability decides; may use headset mic, text-only, or verified compatible route. Never silently promise both. |
| Nemotron treated as full speech-to-text and speaker identity | Separate ASR + diarization + alignment. Anonymous aliases unless verified by user. |
| All decisions treated as final | Explicit state `PROPOSED/DEFERRED/ACCEPTED/...`, only source-supported transitions. |
| Cross-session memory always “on” | Space-scoped, opt-in keep policy, clearly differentiated recorded / recollected / AI content. |
| Interview live help assumed generally usable | Real interview AI assistance only when explicitly permitted, independently of recording rights; mock always available. |
| Classroom always assumes microphone capture | Notes-only, imported permitted materials and post-class reflection supported. |
| Every mode needs a bottom-nav tab | Four shared bottom tabs; context packs live in Home/Start and session presentation. |
| Research Companion unspecified | Research/conference is Learning preset initially; only specialize after evaluation. |
| Early architecture suggested graph DB/Kafka/K8s by default | PostgreSQL+pgvector and durable jobs first; add complexity when justified by measured needs. |
| Partial transcripts treated as stable citations | Every turn versioned; only finalized/verified citations used for high-stakes attributable claims. |
| End session and finalization conflated | Stop microphone immediately; finalization is a separate observable state with retry. |

# 14. Implementation verification and source register

## 14.1 Engineering review questions before first sprint

- Which supported iOS/Android device and OS tiers will be included at first release?
- Which exact microphone/earbud combinations work in phone-on-table and pocket scenarios across those devices?
- Which speech stack meets accuracy/latency for Hindi/English code-switching, plus target international languages?
- What regional processing and consent UX is legally approved in initial market(s)?
- What are measured per-hour ASR, diarization, reasoning, TTS, storage and support costs under real concurrency?
- What result from a blinded benchmark would cause us to change intervention strategy or model?

These questions are **delivery validation gates**, not reasons to defer the software architecture or product work indefinitely. Owner/timeline should be set in the actual sprint plan.

## 14.2 External references (verified October 2026)

- **[S1]** NVIDIA, “Know Who Spoke When: Build Real-Time, Multi-Speaker AI with NVIDIA Nemotron 3 Diarization,” September 23, 2026: https://huggingface.co/blog/nvidia/nemotron-diarization
- **[S2]** Android Developers, foreground-service restrictions and changes: https://developer.android.com/develop/background-work/services/fgs/changes and https://developer.android.com/develop/background-work/services/fgs/restrictions-bg-start
- **[S3]** Apple Developer, AVAudioSession allowBluetooth HFP coupling: https://developer.apple.com/documentation/avfaudio/avaudiosession/categoryoptions-swift.struct/allowbluetooth
- **[S4]** Apple Developer, record category and background audio recording: https://developer.apple.com/documentation/avfaudio/avaudiosession/category-swift.struct/record

## Final build directive

**Do not create separate MeetSaathi Meeting, Learning, Interview and Conversation repositories. Build the shared native session and source-grounded intelligence foundation, then plug in context-specific screens and policies.** Optimize for exceptional real-phone UX, verifiable help, and repeat use. This specification is authoritative for v1 design intent; companion artifacts supply executable schemas and a release test baseline. Engineering must validate real-device behavior and update decisions with measured evidence before production launch.
