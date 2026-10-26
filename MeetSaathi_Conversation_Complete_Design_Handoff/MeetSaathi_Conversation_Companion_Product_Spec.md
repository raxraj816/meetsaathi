# MeetSaathi — Conversation Companion
## Complete Product Experience & Engineering Specification

**Version:** 1.0 design baseline  |  **Date:** 18 October 2026  |  **Status:** Product and implementation handoff; not a built mobile app

> **Product promise:** Be more present in everyday conversations. Understand what matters. Remember only what you choose to keep.

## 1. Executive product decision

Conversation Companion is the general-purpose, consent-aware mode within **one unified MeetSaathi mobile application**. It is neither a secret recorder nor a social-manipulation engine. It helps people prepare, listen, clarify, remember, and reflect across permitted everyday conversations. It shares the app's audio, reasoning, voice, memory, and privacy foundation with Meeting, Learning, and Interview Companions; only the experience policies change.

**Design thesis:** The best everyday companion is calm, relationally respectful, personally useful, and often silent. It should feel like a helpful thinking partner, not a second person competing for attention.

**Key difference from Meeting Companion:** A meeting often produces decisions and action items. An everyday conversation may produce an understanding, a personal commitment, emotional nuance, a new idea, or nothing worth saving. Conversation Companion therefore asks *what is worth keeping?* instead of automatically turning every exchange into a business-style recap.

**Success definition:** A user can initiate a permitted session in under three deliberate steps, keep their attention on the other person, retrieve one precise and well-attributed useful fact, and decide exactly what—if anything—is retained afterward.

## 2. Users, environments, and fit

| Situation | Real job to be done | Desired AI intervention | Risk and constraint |
|---|---|---|---|
| Mentor or career conversation | Remember advice, clarify next steps | Highlight an unanswered question; save a follow-up | Respect third-party confidentiality |
| Networking or industry event | Remember permitted introductions and topics | Quiet context recall when requested | Do not covertly profile strangers |
| Collaborative problem-solving | Connect ideas and capture a useful breakthrough | Surface a trade-off or a contradiction with evidence | Don't claim agreement prematurely |
| Trusted family discussion | Remember mutually agreed plans | Optional save on user request | Highest privacy default; no background surveillance |
| Language exchange | Understand difficult phrases | On-demand translations and context | Preserve meaning and indicate uncertainty |
| Personal coaching session | Recall guidance and exercises | Save user-selected tasks | Sensitive topics; avoid unverified therapy/diagnosis |
| Medical / legal / financial consultation | Remember practitioner-provided instructions | Evidence-linked user questions | Stronger domain controls; no substituting for qualified advice |
| After-the-fact private reflection | Think through a conversation from memory | Organize user's notes and brainstorm | Must label recollection as user-supplied, not a transcript |

**Audience priority:** Everyday professional, mentoring, and collaborative conversations first; high-stakes personal and regulated situations later, only with domain-specific safeguards and deployment approval.

**Not supported:** Secretly recording people; detecting someone’s inner feelings or intentions from their voice; creating covert dossiers about others; impersonating an individual; making consequential judgments about people; manipulating another participant. A permitted coaching prompt must help the user communicate clearly, not engineer deceptive persuasion.

## 3. North-star journey

1. **Choose to start.** The person launches MeetSaathi and selects *Conversation*, which defaults to **Notes-only** unless the user deliberately enables microphone capture and meets participant-notice and consent requirements.
2. **Preflight.** The app indicates the intended capture source, voice destination, network status, retention setting, and a concise description of the participant-awareness obligation.
3. **Begin.** The session indicator unambiguously shows `Listening` or `Notes-only`. The user can pause or stop without navigating away.
4. **Face-up live companion.** The dashboard displays the current theme and at most one high-value, ephemeral suggestion. *Ask*, *Save moment*, *Pause*, and *End* remain available.
5. **Pocket companion.** The person locks the screen, if the platform permits an active session to continue. Optional earbud guidance remains short and never falls back to loudspeaker after headset disconnection.
6. **Follow a thread.** When the user deliberately asks or when a validated intervention qualifies, the AI gives a question, clarification, or evidence-backed reminder—not a long unsolicited lecture.
7. **Review and choose.** The user ends the session and sees a private review of potential keeps; nothing becomes durable cross-session memory without the selected retention policy and authorization.
8. **Reflect.** The user can ask `What was the suggested next step?` or `Help me think through this idea`. The system separates **said in recording**, **my note**, and **AI interpretation**.
9. **Prepare next time.** Saved information resurfaces only inside the user's allowed memory spaces and with context.

## 4. Information architecture

Unified app bottom navigation: **Home · Live · Memories · You**. *Conversation* is an experience preset inside Home/Live, not a new app or competing tab. In a live session, bottom navigation is replaced by high-priority session controls to avoid accidental exits.

Conversation screens and requirements:

| ID | Screen | Primary information | Primary action | State / behavior |
|---|---|---|---|---|
| C01 | Companion Home | Continue / start, recent saved topics | Start conversation | No mic on launch |
| C02 | Context chooser | Mentor, personal, networking, open | Choose context | Defaults are preferences, not permissions |
| C03 | Capture & consent | Recording options, notice, retention | Confirm session | Microphone gated |
| C04 | Audio preflight | Input, output, signal, route warning | Begin session | Block on invalid route or missing permission |
| C05 | Live Focus | One insight, current topic, statuses | Ask / Save / Pause | No auto-scroll or endless cards |
| C06 | Live transcript | Provisional speaker segments and time | Inspect / correct | Optional and collapsible |
| C07 | Ask Companion | Current context and question | Ask | Answer may be silent text or private voice |
| C08 | Earbud / pocket | Audio route, privacy voice, interruptions | Adjust or mute | Never loudspeaker fallback for private speech |
| C09 | Saved moments | Bookmarks / notes with provenance | Bookmark / remove | No false certainty |
| C10 | Session pause/end | Capture status and retained draft | Resume / End | Idempotent end |
| C11 | Reflection recap | Themes, keeps, questions, source clips | Review and save | Private by default |
| C12 | Reflection chat | Remember / Think / Prepare | Ask grounded questions | Modes separate evidence from reasoning |
| C13 | Conversation memory | Scoped topics, dates, saved facts | Search | Space and permission aware |
| C14 | People & boundaries | Participant aliases, sharing status | Correct labels | No covert profiles or identity guesses |
| C15 | Next-time prep | Voluntary relevant memory summary | Open prep | Never surface sensitive info on lock screen |
| C16 | Privacy center | Delete, export, retention, audience | Manage | Per-session memory control |
| C17 | Notes-only mode | User-authored notes, no capture | Capture note | No mic icon or fictional transcript |
| C18 | Recovery & limited mode | Interruption / offline / route changes | Retry / save locally / end | Truthful degraded statuses |

## 5. Design language and UX requirements

- **Visual direction:** warm off-white surfaces for reviewing knowledge; deep midnight navy for active conversations; calm jade as a signal of live/ready state; amber only for unresolved or caution states. Respect system appearance, large type, reduced motion, and high contrast.
- **Home:** strong hierarchy: `Start Companion` > `Continue Reflection` > `Memories`. Do not turn the home screen into an analytics dashboard.
- **Live screen:** one active insight max. No animated paragraph streaming. Transcript folded by default; expand only on demand.
- **Tap targets:** minimum 44×44pt iOS / 48dp Android for critical actions. End requires a visible control, not gesture discovery.
- **Information architecture:** label user-authored, captured, inferred, and independently researched content consistently.
- **Live suggestion length:** aim for 12–28 words; hard design cap 45 words before `More`. Never issue multi-paragraph private audio guidance during ongoing speech.
- **User control:** separate `Capture`, `Proactive suggestions`, `Voice playback`, and `Memory retention`. Turning off one must not deceptively imply that all are off.
- **Accessibility:** captions, Dynamic Type, TalkBack/VoiceOver, color-independent status, motion settings, RTL where appropriate, and no audio-only essential action.
- **Sound:** no auto-read aloud, no public-speaker playback by accident, earbud voice intentionally enabled only.

## 6. Live Focus: component contract

**Header:** `Conversation · Live`, elapsed timer, exact session status, active input/output icons. **Current topic:** short provisional heading updated cautiously; no labeling a participant's emotional state. **One insight:** type (`Clarify`, `Connection`, `Remember`, `Question`), body, `Why this?` rationale, `Save`, `Dismiss`. **Quick actions:** `Ask`, `Save moment`, `Pause`, `End`. **Transcript drawer:** collapsed, source audio markers when authorized. **Accessibility:** persistent visible and spoken recording status. **Privacy microcopy:** `Participants have been informed` is a user-confirmed state, not an assertion made by the AI.

When there is no useful insight, show `Listening quietly — ask whenever you need` rather than forced content. When audio quality falls, show `I may have missed part of this conversation` and suppress speaker-specific claims. When notes-only, replace the entire listening dashboard with a note composer; do not claim live awareness.

## 7. Proactive intelligence and intervention policy

**Pipeline:** consent gate → capture / ASR (when permitted) → provisional speaker turns → current conversational context → candidate generation → grounding / safety / usefulness checks → interruption scheduler → text/voice decision → user feedback → memory eligibility.

**Allowed intents**: (a) clarify an ambiguity, (b) recall user-authorized relevant context, (c) propose a respectful open-ended question, (d) flag a missed explicit follow-up, (e) explain an unfamiliar term on request, (f) translate with caveats, (g) highlight a concrete inconsistency backed by source evidence.

**Disallowed intents**: guess emotions or hidden motives; provide manipulative interpersonal tactics; make definitive claims about trustworthiness or character; leak another person's private prior conversation; present AI advice as quoted speech; infer protected characteristics; propose unrelated suggestions purely to boost engagement.

**Intervention rules (initial design hypotheses):**

1. `Silent` default for sensitive contexts, `Balanced` for explicitly opted-in ordinary conversations, `Active` only when selected. No preset overrides consent.
2. Minimum independent-evidence / context-quality checks; if low-confidence, abstain or offer an optional question to clarify.
3. Suppress delivery while the user is speaking; consider pause timing, meeting pace, and whether the new message is better saved for recap.
4. Deduplicate semantically similar suggestions. Default cooldown 5 minutes in Balanced, unless a genuinely critical user-defined reminder is due. Not a fixed limit on all emergency or accessibility behaviors.
5. Text is the default presentation on face-up devices; voice requires explicit authorization and a verified private route.
6. Competing candidate insights ranked by `usefulness × evidence × timeliness − distraction × sensitivity`; qualitative score with separately testable evidence and privacy gates, not unexplainable single-model threshold.
7. Every delivered insight records `kind`, `source refs`, `model/policy version`, `delivered_at`, `user reaction`, and `reason to intervene` without storing more participant data than necessary.
8. Do not continuously surface intervention cards just because they can be generated. The app earns trust through restraint.

**Examples:**

- Mentoring: `You said you want clearer priorities. Consider asking which skill to focus on first.`
- Language exchange: `The phrase may mean “let's revisit it later,” depending on context. Tap to see alternatives.`
- Collaborative idea: `Two timelines were mentioned. Ask which one is the actual commitment.`
- Personal conversation: `You asked to remember the appointment date. Save the date?` (Only if source clear and within capture permissions.)
- No suggestion: `Keep listening`; the most common outcome should often be no interruption.

## 8. Ask Companion: reasoning contracts

Three tabs with separate retrieval and response rules:

- **Remember:** `What was said?` Answer only from authorized transcript or the user's notes, with `Source: recording at 08:24` / `Source: my note, unverified` and `Not enough evidence` when applicable.
- **Think:** `What could it mean?` Analyze alternatives, uncertainties, respectful questions, and user goals; explicitly label AI inference. Never assert another person's hidden motive as fact.
- **Prepare:** `What can I do next?` Suggest follow-up questions, optionally a user-reviewed reminder or private to-do. No autonomous messaging or calendar actions without distinct permission.

**When no recording exists:** allow questions about typed or privately dictated notes. Do not invent direct quotes or timestamps. When a transcript conflicts with a user correction, preserve the original, the correction, and the confidence/provenance relationship.

## 9. Private voice / pocket experience

- User starts from visible app, routes audio deliberately, and confirms participant awareness when live capture is enabled.
- Android: microphone foreground service with proper permission / service type; the session must be initiated under allowed foreground conditions. Persistent system capture indicator/notification.
- iOS: correct `AVAudioSession` category and background audio mode; handle interruptions and route changes. A compatible device may still not simultaneously support the desired phone microphone and Bluetooth voice output; detect and explain actual routing.
- Bluetooth HFP routing may couple the headset microphone and output on iOS, meaning the earbud microphone may replace the table microphone. Never promise remote participants will remain audible when the mic changes.
- Voice uses brief interjections, optional earbud chime/haptic, voice interruptibility, and queuing. If headset disconnects, **mute private spoken content immediately**, show an alert, and do not reroute private speech to speakerphone.
- If a session's input fails or the operating system suspends it, surface `Capture interrupted`; save only authenticated captured chunks and do not silently infer ongoing speech.
- Pocket audio capture is environment dependent, especially fabric noise, distance, and orientation. Offer `Audio quality poor` rather than suggesting a falsely perfect transcript.

## 10. Memory: store meaning without building a dossier

Memory is **opt-in, scoped, editable, portable, and forgettable**. Spaces: `Personal`, `Work`, `Learning`, and optional user-created spaces. The same speaker alias across sessions is *not* automatically the same person. Identity mappings require a transparent user-mediated workflow and relevant participant permission/legitimate basis where applicable.

Memory record kinds: `explicitly saved fact`, `question`, `idea`, `commitment`, `user note`, `possible topic`, `correction`, and `AI reflection`. Every item retains `source_type` = recorded / user_note / model_analysis; `session_id`, time interval when recorded, sensitivity, audience, expiration, provenance, and revision chain. AI analysis is not searchable as a quote from a participant.

**Review-to-save:** at end, offer `Keep these 2 things`, `Review individually`, `Discard session`. Default retention must be visible. Sensitive contexts default to ephemeral/notes-only when possible. Users can delete audio while retaining user-reviewed sanitized notes; clarify implications of doing so, including the loss of source playback.

**Cross-conversation retrieval:** permit only from a space the user has authorized for the current query. No surprise references from personal memory in a shared/work meeting. Search returns provenance, date, and original wording when available. Deletion cascades to embeddings, indexes, summaries, cache, and derived items or marks them inaccessible pending bounded deletion completion.

## 11. Session state machine

`IDLE → CONFIGURING → PREFLIGHT → ACTIVE_CAPTURE | ACTIVE_NOTES_ONLY → PAUSED → (ACTIVE_*) → ENDING → FINALIZING → REVIEW → SAVED | DISCARDED`

Exception sub-states: `INPUT_UNAVAILABLE`, `ROUTE_CHANGED`, `NETWORK_DEGRADED`, `BACKGROUND_RESTRICTED`, `CONSENT_NOT_CONFIRMED`, `STORAGE_UNAVAILABLE`, `PARTICIPANT_WITHDRAWS`, `PROCESSING_FAILED`.

Invariants:

1. No microphone access or streaming outside confirmed authorized capture states.
2. Notes-only never starts ASR or generates live listener-derived insights.
3. All `End` operations idempotent and release active capture resources immediately.
4. Session stop halts new capture before any background finalization begins.
5. Loss of consent stops recording for the affected context; do not resume automatically.
6. Voice output requires an approved destination; route change invalidates approval until re-evaluated.
7. Failure notices must use plain language and preserve the user's ability to end.
8. Saved and discarded statuses must accurately reflect committed storage, not optimistic UI state.

## 12. UI state and event contracts

Representative event stream (`conversation_event_v1`):

```json
{
  "event_id": "evt_123",
  "session_id": "sess_123",
  "sequence": 218,
  "kind": "insight_candidate|insight_delivered|utterance_final|audio_route_changed|capture_interrupted",
  "source_refs": [{"utterance_id":"utt_52","start_ms":120500,"end_ms":128100}],
  "privacy_space_id": "space_personal",
  "created_at": "2026-10-18T15:00:00Z",
  "payload": {"confidence_band":"moderate","text":"Clarify which date is confirmed."}
}
```

Represent consent authorization separately from OS microphone permission:

```json
{
  "audio_capture": "permitted|not_permitted|pending",
  "participant_notice": "confirmed|not_confirmed|unknown",
  "ai_live_assistance": "enabled|disabled",
  "voice_output": "disabled|private_route_confirmed|route_unavailable",
  "retention": "ephemeral|session_review|user_selected_memory",
  "current_input": "phone_mic|headset_mic|external_mic|none",
  "current_output": "screen_text|private_headset|muted"
}
```

Client contract examples:

- `POST /v1/conversations` — create private draft, no recording yet.
- `POST /v1/conversations/{id}/authorize` — verify client disclosures and permissions; server does not assume third-party legal consent from a checkbox alone.
- `POST /v1/conversations/{id}/start` — idempotency key, route / privacy preflight.
- `POST /v1/conversations/{id}/pause` / `/resume` / `/end` — monotonic state transitions.
- `GET /v1/conversations/{id}/events?after_seq=...` — resumable context updates.
- `POST /v1/conversations/{id}/ask` — mode = remember/think/prepare; explicit retrieval scope.
- `POST /v1/conversations/{id}/bookmarks` — note / clip / correction with provenance.
- `POST /v1/conversations/{id}/review` — atomic save selection and retention.
- `DELETE /v1/conversations/{id}` — deletion workflow with status and downstream propagation.
- `GET /v1/memory/search` — scoped, permission-filtered evidence.

### 12.1 Core entities

`Account`, `PrivacySpace`, `Session`, `SessionPermissionSnapshot`, `ParticipantNotice`, `AudioChunk`, `Utterance`, `SpeakerAlias`, `Insight`, `InterventionDecision`, `Bookmark`, `MemoryItem`, `MemorySource`, `MemoryCorrection`, `RetentionPolicy`, `DeletionRequest`, `AuditEvent`.

Use stable IDs, tenant/user ownership on every row, encryption metadata, versioned transcript revisions, and explicit speaker uncertainty. Index consent and privacy scope checks before vector retrieval, not merely after semantic ranking.

## 13. Production implementation architecture

**Native applications:** Kotlin + Jetpack Compose on Android; Swift + SwiftUI on iOS. Shared OpenAPI and event schemas; separate platform audio modules. Why: live microphone, interruptions, Bluetooth, accessibility, and lifecycle control are platform-sensitive.

**Client components:** SessionController, PermissionCenter, AudioCaptureAdapter, AudioRouteDirector, LocalEncryptedBuffer, LiveEventReducer, CompanionDashboard, VoicePlaybackCoordinator, ReflectionUI, MemoryBrowser, RecoveryManager.

**Backend components:** API Gateway, Session Service, Stream Ingest, ASR & diarization workers, Turn Alignment, Context Builder, Evidence Store, Intervention Policy, LLM Router, TTS, Memory Service, Retrieval, Retention/Deletion, Audit and Observability.

**Data:** PostgreSQL for transactions, scoped relationship and correction data; pgvector initially for embedding search; encrypted object storage for permitted audio; Redis only if workload measurements justify it; queue for durable asynchronous finalization. Avoid premature microservice / graph / Kafka expansion.

**Realtime processing:** modest streaming chunks → VAD → streaming ASR → speaker turn alignment → evidence indexed → context engine → relevance/safety judge → delivery decision. Batch reprocessing after recording may improve final speaker labels and transcripts; never silently overwrite originals.

**On-device-first ambition:** privacy-sensitive local transforms and buffering first, selectively use on-device speech inference where latency/battery/quality supports it; cloud processing requires disclosure and a recorded permission decision. Do not imply Nemotron 3’s published buffer latency equals end-to-end assistant latency.

**Failure recovery:** resumable event sequences, bounded encrypted local buffer, explicit capture-incomplete status, signed upload grants, safe replay and deduplication. No fake 'always listening' promise after an OS stop.

## 14. Trust and security threat model

Threats and mitigations:

| Threat | Required control |
|---|---|
| Unauthorized recording | Foreground start, OS permissions, explicit capture opt-in, participant disclosures, visible indicators |
| Listening when paused | Mic stream teardown / verified no bytes sent |
| Voice leaking to phone speaker | Route latch and automatic private TTS mute on route change |
| Mixing personal and work memory | Privacy-space ACLs checked at retrieval and generation |
| AI claims wrong speaker identity | Anonymous ID defaults, correction UX, evidence with confidence |
| Prompt injection spoken by another person | Treat transcripts as untrusted, never as system instructions; tool execution requires policy + approval |
| Transcript containing private secrets | Redaction controls, retention controls, narrow access, encrypted storage |
| Cross-user search leakage | Tenant-scoped authorization before retrieval; negative tests |
| Deletion appears complete but embeddings remain | Deletion jobs with auditable completion and bounded SLA |
| Sensitive notifications on lock screen | Neutral notification content by default |
| Unapproved autonomous actions | Explicit user confirmation before sending, scheduling, or sharing |

**Jurisdiction:** Consent and data-protection bases vary by region and environment. Global rollouts need localized legal review; do not assume one tap solves legal authorization. For minors or sensitive settings, add dedicated safeguards, institutional rules, and stricter retention.

## 15. Quality and experience gates (targets, not achieved metrics)

| Metric | Candidate release gate | How measured |
|---|---|---|
| Task completion: start legitimate session | ≥ 95% without help in usability testing | Moderated tasks |
| Silent mode surprise outputs | 0 | Device automation + field QA |
| Lost audio on supported 60-minute sessions | < 0.5% unannounced | Long-session test matrix |
| False confident speaker attribution | 0 in high-risk evaluation sample | Human-audited clips |
| Source provenance on factual remembered claims | ≥ 98% correct in evaluation corpus | Evidence annotation |
| Proactive insights judged helpful | ≥ 80% in opted-in, non-sensitive study | Blind human rating |
| Unwanted Balanced interruptions | ≤ 1 per 30 minutes | Session feedback + review |
| Private audio leaks after disconnect | 0 | Bluetooth route fault injections |
| User-selected deletion | Complete within published service policy | End-to-end deletion check |
| Crash-free sessions | ≥ 99.8% supported device set | Telemetry |
| Latency to first live text after utterance | P95 ≤ 3 s target | Timestamped end-to-end test |
| Relevant suggestion from trigger | P95 ≤ 6 s target | Session replay tests |

Targets must be revised only with recorded user research, not to conceal a miss. Include accuracy slices for quiet rooms, café noise, phone-in-pocket, headsets, overlap, accents, languages, and network conditions.

## 16. Analytics and user experience evaluation

North Star: **Meaningful companion conversations per weekly active user**—a session is meaningful only if the person confirms help received or returns to valuable saved context, not simply because recording stayed on. Guardrails: permission drop-offs, microphone errors, unnecessary interruptions, battery drain, retention surprise, memory trust, and deletion success.

Respect privacy: telemetry should use event metadata and opt-in aggregated quality measurements; never default to sending raw personal conversation content into product analytics.

## 17. Delivery roadmap / engineering sequence

**R1 — Coherent native journey:** one Start Companion, transparent consent/preflight, Notes-only option, reliable pause/end, local encrypted capture, graceful interruptions. *Exit:* real device begins and finishes a valid session with no silent capture state change.

**R2 — Accurate conversational understanding:** streaming ASR, provisional speaker turns, collapsible transcript, confirmed corrections, source-linked capture, good degraded behavior. *Exit:* user retrieves an exact segment with timestamp and uncertainty.

**R3 — High-utility intelligence:** contextual Ask, one-card live focus, evidence-aware proactive scheduler, feedback, separate Remember/Think/Prepare answers. *Exit:* robust human evaluation and low interruption rate.

**R4 — Memory and reflection:** review-to-save, scoped search, user edits, export and deletion, next-time preparation. *Exit:* correct cross-conversation search without leakage.

**R5 — Private voice and expanded devices:** verified Bluetooth routes, earbud playback, interruption/route recovery, screen-off and pocket performance. *Exit:* supported-device matrix meets audio leak and recovery requirements.

**R6 — Product readiness:** security review, accessibility, localization, country launch policies, store compliance, battery/thermal validation, performance budgets, 90-minute reliability suites. *Exit:* product gates passed and user testing demonstrates willingness to return.

R1–R6 are release increments of one product, not disposable prototypes. Engineering can work on components in parallel once interface contracts stabilize.

## 18. Copywriting examples and behavior tone

- Initial welcome: `A little help when it matters. Space to be present the rest of the time.`
- Permission explanation: `Record only when everyone who needs to know has been informed and the recording is allowed.`
- Quiet live: `Listening quietly. Tap Ask if you need me.`
- Suggestion: `A date was mentioned, but not confirmed. Want to clarify it?`
- Poor capture: `Audio is unclear. I may miss words or speakers.`
- Private route loss: `Earbuds disconnected. Spoken guidance has stopped.`
- No-recording: `Notes-only. I can't hear this conversation; add anything you'd like to remember.`
- After ending: `What would you like to keep from this conversation?`
- Unsourced answer: `I can't confirm that from the material you saved.`

## 19. Product decisions and rejected alternatives

| Choice | Decision | Why | Alternative rejected |
|---|---|---|---|
| Privacy default | Notes-only until explicit recording choice | Everyday setting is sensitive | Auto-listening at app open |
| Default live UI | One insight and clear status | Reduces distraction | Infinite transcript/chat wall |
| Assistance | Optional Balanced / Silent; Active opt-in | Timely value beats quantity | Always-on unsolicited prompts |
| Voice | Private route required | Prevents unintended disclosures | TTS through whatever speaker is available |
| Attribution | Anonymous unless confirmed | Model cannot know person identity from diarization alone | Guess names from voice |
| Memory | Review / scoping / deletion | User agency and trust | Permanent hidden memory of everyone |
| Modes | Remember / Think / Prepare | Separates evidence from inference | One unlabelled chatbot answer |
| Architecture | Native app + shared backend | Correct platform control | All audio in webview |
| Quality | Targeted evaluation gates | Product excellence is measurable | Feature count as quality metric |

## 20. Implementation checklist for a Codex or engineering team

- [ ] Establish monorepo with Android/iOS/backend/contracts/docs/QA; enforce type-safe contracts.
- [ ] Build unified design system tokens and components used by all MeetSaathi companions.
- [ ] Implement session and permission state machine with test-first invariants.
- [ ] Implement native mic capture and device-route reporting without any silent background auto-start.
- [ ] Add UI-visible truthful state, notifications, interruptions and persistent user stop access.
- [ ] Implement mock synthetic event stream for app tests, separated from production stream endpoints.
- [ ] Implement secure stream ingest, ASR, diarization/alignment, and stable evidence IDs.
- [ ] Implement Ask/Reasoning with grounded, source-aware user-permission-scoped retrieval.
- [ ] Implement candidate interventions, scoring, suppress/abstain path and feedback capture.
- [ ] Implement private voice coordinator with route-change mute and verified destination.
- [ ] Implement post-session review, memory opt-in, corrections, search, export and deletion.
- [ ] Implement feature flags and server-driven policy versions without reducing explicit consent requirements.
- [ ] Run reproducible real-device acceptance suites for power, Bluetooth, network and permissions.
- [ ] Complete privacy/security review, penetration test, accessibility audit, regional policy review.

## 21. Source and verification notes

Official technical references consulted 18 October 2026:

- Android microphone foreground-service rules: https://developer.android.com/develop/background-work/services/fgs/service-types and https://developer.android.com/develop/background-work/services/fgs/restrictions-bg-start
- Apple Bluetooth Hands-Free audio routing: https://developer.apple.com/documentation/avfaudio/avaudiosession/categoryoptions-swift.struct/allowbluetooth
- Apple background audio: https://developer.apple.com/documentation/avfaudio/avaudiosession/category-swift.struct/record
- Apple App Review recording consent: https://developer.apple.com/app-store/review/guidelines/
- NVIDIA Nemotron 3 diarization: https://huggingface.co/nvidia/Nemotron-3-Diarization
- European Commission GDPR principles: https://commission.europa.eu/law/law-topic/data-protection/information-business-and-organisations/principles-gdpr_en

**Research boundaries:** This is a prospective design with measurable targets, not proof of real-device support, legal compliance, model quality, or product-market fit. Obtain local legal advice and user evidence before launching in a jurisdiction or claiming performance.

---
**One MeetSaathi. Multiple contextual experiences. One promise: useful help without stealing the user's attention or autonomy.**
