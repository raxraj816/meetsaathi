# MeetSaathi — Interview Companion
## Complete mobile product experience and production specification

**Version:** 1.0  
**Design date:** October 18, 2026  
**Status:** Implementation-ready product design proposal. Interactive reference uses simulated data; no production code or live audio service has been built.  
**Product family:** Universal MeetSaathi (Meeting, Learning, Interview, Research, Conversation)

> **Prepare intelligently. Stay present. Learn from every round.**

## Executive product decision

Build Interview Companion as a context-aware experience **inside MeetSaathi**, not an independent AI interview-answer app. One native mobile foundation, one trust model, one source-linked conversational memory, three distinct interview journeys: **Practice**, **Permitted Live Assistance**, and **Review / Reflection**. Practice must be excellent independently; live assistance is gated by explicit interview rules and recording consent. Device output may be **silent on-screen text**, **private earbud voice**, or **both**, subject to actual hardware routing.

**Why:** An answer generator is easily commoditized and can undermine candidate competence. A product that helps people improve, stay calm, reason clearly, and learn after each round creates defensible long-term value. Meeting and Learning Companion already establish a calmer and more trustworthy interaction model; Interview reuses it instead of fragmenting the app.

---

# 1. User outcomes, audiences and competitive boundary

## 1.1 Jobs to be done

1. "I have an interview next week. Tell me what to study based on the job, my experience, and the round." 
2. "Interrogate my knowledge and ask realistic follow-ups, not easy canned questions."
3. "Help me practice speaking naturally and making defensible technical claims."
4. "When allowed, help me recall a framework or identify missing clarification without distracting me."
5. "After the round, tell me what was asked, what I actually answered, and what I need to improve, citing the recording if one was permitted."
6. "Carry lessons and progress from round one to round five and eventually across jobs."
7. "If recording or AI help is prohibited, let me prepare before and reflect afterward without covert listening."

## 1.2 Personas

| Persona | Context | Highest-value experience | Failure to avoid |
|---|---|---|---|
| Senior software engineer | System design, behavioral, Java DSA, deep dives | Rigorous mock interviewer, assumption prompts, diagrams/checklists, explain-back | Overly long or technically invalid suggestions |
| Early-career candidate | First behavioral and general technical interviews | Rehearse, reduce filler, structured feedback, fundamentals | Discouraging, generic grading |
| Cloud solutions architect | Trade-offs, customer discovery, cost/security/reliability | Scenario simulator with probing follow-ups | Memorized vendor pitches over customer needs |
| Product manager | Product sense, analytical, execution | Clarifying questions, stakeholder trade-offs, prioritization | Treating subjective choices as objectively scored facts |
| Research engineer | ML fundamentals, research critique, coding | Oral defense, experiments and failure analysis | Fabricated paper claims |
| Student / graduate | Campus placements | Low-friction mock interviews and foundational learning | Unsupported confidence scores or cheating support |
| Interviewer / hiring team | Authorized structured interviews | Interview notes, consistent rubrics, evidence and follow-ups | Automated exclusion or protected-trait inference |

**Initial wedge:** Technical professionals and serious job seekers. Role packs can grow later. No separate product infrastructure per role.

## 1.3 Existing competitive bar

As of October 2026, Final Round AI advertises real-time interview answers, mocks and debriefs; Huru emphasizes mock practice and scored feedback. Neither live answer suggestions nor mock interview chat alone establish uniqueness. Our value proposition must be tested against alternatives through realistic follow-ups, learning improvement across sessions, helpfulness of allowed live suggestions, calm interface, speaker/evidence accuracy, and mobile reliability.

## 1.4 Product boundaries and integrity

- No hidden assistant features designed to violate interview conditions, screen-share rules, proctoring, or employer assessment restrictions.
- No silent recording of other participants. Permission to use AI and permission to record are **two independent checks**.
- No fake evidence that an interviewer asked something if the transcript is uncertain or the session was not recorded.
- No unsupported inference about personality, emotions, honesty, health, demographic characteristics, employability or hiring outcome.
- No automatic claim that a high interview score guarantees an offer.
- No access to system audio from other apps without OS-supported, authorized integration.
- No pretending the app can hear through a laptop headset while the phone microphone captures only the room.

---

# 2. Product information architecture

Universal tabs remain **Home / Sessions / Memory / You**, matching Meeting and Learning. Selecting **Interview** changes contextual screens, practice policies, icons and recommendations; it does not create a disconnected data silo.

**Interview surfaces:**
1. Home: upcoming interview, "Practice now", "Start authorized session", last coaching insight.
2. Interview Goal: employer/role/stage, JD, candidate experience, allowed materials, goals and preferred speaking style.
3. Role Preparation: 10-minute warmup, targeted question map, weak areas, previous rounds.
4. Practice Setup: interviewer persona, domain/format, difficulty, time, feedback timing.
5. Mock Live: realistic interviewer turns, voice/text answers, follow-up probes and optional whiteboard/code workspace.
6. Live Eligibility: ask if AI is allowed and recording is allowed separately; explain constraints and require acknowledgment.
7. Device Preflight: actual audio input/output routes, Bluetooth handling, sound test, user-initiated recording.
8. Live Focus: real capture status, question excerpt, one concise suggestion, Ask/Save, no transcript wall.
9. Ask Sheet: short help grounded in current question, optional evidence or model reasoning, user dismissal.
10. Pocket Voice: route indicator, whispered concise guidance where permitted, fast mute and no-speaker-leak behavior.
11. Session Timeline: questions, answers, transitions, source timestamps and recording gaps.
12. Debrief: evidence-grounded observations and user-centered actionable coaching.
13. Answer Lab: replay, explain what to strengthen, compare candidate's revision to their own previous answer.
14. Round Memory: aggregated questions, concepts, employer/stage, lessons and confidence ranges.
15. Next-Round Plan: prioritized preparation, mock drills and reminders.
16. Trust Center: recording consent, AI authorization, retention, deletion, audio route history, exports.
17. Accessibility: captions, text scaling, slow TTS, one-handed controls, screen reader, haptics.
18. Offline Reflection: manual notes and user-supplied approved material; no fake ASR.

---

# 3. Three operating modes: behavior vs delivery

| Behavior mode | Capture | AI during conversation | Afterward |
|---|---|---|---|
| **Practice** | Consensual user practice voice/text | Full AI interviewer and teaching; simulated questions | Evidence-backed skill feedback, adaptive drills |
| **Permitted Live** | Only with independently verified recording permission | Only when live AI is explicitly allowed; compact contextual assistance | Approved recording debrief, next-round plan |
| **Reflect / Notes-only** | None by default; manual notes | No live listening/assistance during restricted interviews | Reflection from manually entered details or approved materials |

**Delivery** is a separate setting: Text / Voice / Both. **Assistance level** is another separate setting: Quiet (only Ask), Balanced (high-value limited nudges), Active (more frequent but still restrained; available only in Practice or authorized Live). **Audio consent and recording state** are separate from AI speaking state.

**Hard gates:** If live AI is prohibited, permitted-live assistance cannot start. If recording is prohibited, microphone capture cannot start. If AI is allowed but recording prohibited, provide a manually initiated, non-recording alternative only where the interview's rules permit it; otherwise direct user to pre/post preparation. In production the app must not assume unchecked self-attestation is independently verified; communicate user responsibility and support organizational policy controls where available.

---

# 4. Complete candidate journeys

## 4.1 First launch: value without permissions

- Choose **Interview** from universal MeetSaathi; see “Practice now” and “Prepare for a real round.”
- No account or microphone request to explore a complete fictional sample mock.
- Optional import: pasted JD, role, interview stage, resume/experience; avoid collecting legal names and employers unless needed. Allow edits and deletion.
- Show how answers will be evaluated: clarity, reasoning, technical accuracy, communication, genuine evidence. Explain ratings as coaching aids, not employer-equivalent scores.
- Only request microphone when starting a spoken session. Show input data handling plainly.

**Why:** Trust and activation. Do not force full professional profiles or permission requests before value appears.

## 4.2 Prepare for a senior engineering round

- Role Goal: “Senior/Staff backend engineer”, stage “System design”, language English, code Java, optional employer profile.
- Screen: “What they may assess” (user- or JD-grounded), “Your strongest evidence”, “Top three gaps”, “10-minute warmup”.
- Candidate chooses **Practice system design**. AI asks for clarifications and follows up on scale, failure modes, storage, consistency, security, observability and cost.
- When candidate pauses, AI waits for a configured silence threshold or asks if more thinking time is needed; never immediately marks a pause as failure.
- Post-round, feedback prioritizes two or three behaviors that will substantially improve outcomes.

## 4.3 Practical mock: question → answer → challenge

1. AI asks: “Design an event-driven fraud alerting system supporting large transaction volume.”
2. Candidate responds verbally. UI shows interviewer avatar, current question, timer, pause, “Repeat”, “Need 30 seconds”, optional captions.
3. AI asks an incisive follow-up based on what the candidate actually said: “What happens when the consumer processes an event twice?”
4. Candidate explains idempotency. Model can challenge unstated assumptions, request a concrete example and explore a fault-injection scenario.
5. Only after the round or when feedback-on-demand is chosen, coaching appears: soundness, clarity, missing assumptions, specific stronger phrasing, source excerpts.
6. Candidate retries the **same skill** with a different scenario. Progress is measured by demonstrated improvement, not repetition count.

**Why:** Practice of reasoning under conversational pressure yields more useful development than memorizing generated answers.

## 4.4 Live permitted session: phone beside laptop

- User opens Interview Goal and taps **Join with Companion**; sees two separate permissions: interview allows AI assistance? interview allows recording? Clear “Not permitted” paths.
- If both allowed, device preflight shows actual phone microphone, whether the laptop speakers are audible, earbud route if any, network/battery and local buffer readiness. They explicitly start recording.
- The Live Focus screen shows **Current question** and just **one priority insight** (“Clarify whether ordering must be global or per partition”). Labels distinguish **AI suggestion** versus **speaker said**.
- The user can tap **Why?**, **Ask**, **Save**, or ignore. Quiet/Balanced defaults: suggestions never cover the question and never exceed a short glanceable card.
- While talking, avoid showing 100-word drafted answers that induce reading rather than engagement.
- If confidence low, show “Couldn't confidently hear that question” and withhold confident suggestions.
- End session → processing → debrief with captured gaps noted honestly.

## 4.5 Live with phone in pocket, optional earbud

- Start and permission gates occur while phone is visible. Lock/pocket afterward. An OS-visible recording status remains available.
- Voice is opt-in and private only when route confirms earbuds. Suggestions must be very short, and speaking is deferred while interviewer/candidate speech is detected when feasible.
- On earbud disconnect, immediately cancel pending playback; **never silently route private interview guidance to the phone speaker**.
- A Bluetooth headset input may stop the phone microphone hearing other participants. Explain which source is currently captured and disable automatic full-conversation claims if only the wearer is intelligible.
- If route changes, ask user to confirm route and resume only after verification.
- Avoid claiming globally available hardware button mappings or always-on wake words; supported shortcuts are capability-detected.

## 4.6 Interview without permission for AI or recording

- **Before:** 10-minute warmup with targeted mock questions.
- **During:** MeetSaathi does not listen, transcribe, or speak. An optional time-agnostic prewritten checklist can be accessed only if interview rules permit reference material; otherwise nothing runs during the interview.
- **After:** User types “They asked about cache invalidation and multi-region DR.” Clearly mark as **user recollection**, never as recorded fact.
- Coach can then teach concepts, help reconstruct discussion, and schedule improvement drills.

**Why:** Product usefulness should not depend on breaking employer or assessment rules.

---

# 5. Visual design system and screen contracts

## 5.1 Universal design language

- Midnight canvas `#071421`, muted panel `#132335`, jade accent `#72E3CE`, off-white `#F2F7FA`, muted slate `#A6B8C8`, amber `#F4CB86` for uncertainties; red reserved for actual interruption/error.
- H1 26–30 pt; card heading 16–18; reading content 15–16; metadata 12–13 with high contrast and supported dynamic type.
- Touch target iOS ≥44 pt / Android ≥48 dp; large pause, exit, repeat, ask, mute functions.
- No high-frequency pulsing orb. Waveform indicates **actual**, not fabricated, capture activity.
- Live Focus has a fixed question header, primary insight card, and bottom Ask action; detailed transcript stays behind a sheet.
- Avoid visual overload: one unsolicited insight, ≤36 words at first glance, progressive disclosure of “Why” or sources.
- Accessibility: voice captions, dyslexia-friendly readable fonts without requiring a custom font, color-independent states, dynamic type, screen reader focus, reduced motion.

## 5.2 Screen contracts

| Screen | Key information | Primary action | Empty/error behavior |
|---|---|---|---|
| Interview Home | Next round, progress, recent mock | Practice now | Sample round without account |
| Goal | Role, stage, date, source documents | Prepare | “Not enough JD context” is explicit |
| Warmup | 3 focused skill prompts | Start practice | Generic fundamentals if no goal |
| Mock Setup | Topic, difficulty, time, feedback policy | Start mock | Microphone denied -> text practice |
| Mock Live | AI question, listen/respond state | Answer / Next | ASR unavailable -> typed answer |
| Eligibility | AI help allowed? recording allowed? | Continue eligible mode | Restriction -> reflection/practice |
| Preflight | Real input/output route, quality meter | Start authorized | Can't hear laptop -> explicit warning |
| Live Focus | Question, one timely insight, route | Ask or Save | No capture -> session gap state |
| Ask sheet | Short, framed response, uncertainty | Follow-up / Save | Insufficient audio -> ask rephrase |
| Pocket Voice | Actual earbud device/route, AI mute | Mute voice | Disconnect -> stop playback |
| Session Timeline | Question turns + candidate answers | Play cited moment | Mark gap instead of reconstruction |
| Debrief | 2 strengths, 2 growth areas, examples | Practice weaknesses | No record -> recollection-tagged |
| Answer Lab | One answer, why it can improve | Retry answer | Missing source -> text-based lesson |
| Round Memory | Interview sequence, concepts, trend | Ask across rounds | Access-scope empty state |
| Next Round | 3 prioritized actions | Start targeted drill | No schedule -> general plan |
| Privacy | Recordings, consent, export/delete | Delete/export | Graceful data status and confirmations |

## 5.3 Live screen hierarchy

1. Header: interview goal, `Live / Paused / Restoring / No capture`, elapsed time.
2. Context strip: “Current question” and captured confidence/source type.
3. Priority insight: short actionable tip, explicitly tagged **AI guidance**, optionally `Why?`, never misrepresented as interviewer words.
4. User controls: **Ask**, **Save**, **Mute AI**, **Pause capture**, **End** with distinct outcomes.
5. Optional bottom drawer: transcript (provisional speakers), details, reference materials where allowed.
6. Route footer: actual input and output; never says “earbuds private” without verification.

---

# 6. Interview intelligence behavior

## 6.1 Question and context tracking

Maintain a versioned state describing goal, round, permitted assistance, active question, interviewer challenges, candidate's claims, uncertain utterances, topic transition, evidence sources, duration, and whether the user is speaking. Detect question type **probabilistically**: system design, coding, behavioral, technical deep-dive, case, product sense, or mixed. Ask neutral clarification when ambiguity materially matters.

## 6.2 Practice interviewer loop

- **Ask:** realistic task, constraints when appropriate, no immediate ideal answer.
- **Listen:** allow thinking time; avoid racing silence detection.
- **Probe:** follow-ups reference candidate's own assertions and realistic interview constraints.
- **Challenge:** focus on assumption, evidence, trade-off or failure handling; refrain from humiliating feedback.
- **Coach:** summarize concrete opportunities after a segment, not every sentence unless the user requests it.
- **Rehearse:** targeted redo with new variant, compare improvement evidence rather than “perfect answer.”

**Role-specific teaching:**
- Behavioral: Context, action, ownership, result, reflection; STAR helps structure, but do not force robotic wording or invent achievements.
- System design: Requirements, scale, design, alternatives, capacity, consistency, reliability, security, cost, observability.
- Coding: Problem interpretation, examples, complexity, edge cases, readable code, testing; support Java and other languages.
- AI/ML: Data, objective, baseline, evaluation, leakage, serving, drift, cost, safety.
- Solutions architecture: Customer constraints, trade-offs, operational excellence, governance, economics.

## 6.3 Proactive permitted-live engine

**Candidate creation → risk scoring → evidence and policy checks → scheduling → output.**

Generate candidate nudges only for identifiable problems (missing essential clarification, user-requested reminder, contradiction to prior user-approved material, overlooked security concern, or time-limit awareness). Require role relevance, confidence, actionable wording, low burden, session authorization, and an appropriate moment.

Rules:
- Never deliver an unsolicited long answer; default ≤36 words on screen / ≤9 seconds voice.
- Show at most one priority nudge simultaneously; deprioritize duplicates; apply configurable cooldowns.
- Be silent when speech recognition is unreliable, when speaking would interfere, or when user muted assistance.
- Interviewer answer versus external suggestion must have distinct labels; model may reason but cannot claim source provenance it lacks.
- In Practice, nudge policy is configurable (coaching on/off). In real Live, more conservative Balanced default.
- No nudges from unapproved uploaded material, unrelated job profiles or another organization's confidential meeting memory.

## 6.4 Ask flow

On demand, user asks for a definition, consideration, conceptual explanation, alternative, or recap. The assistant takes the latest authorized audio-derived context and memory in scope; returns short user-facing text with a confidence label and separate source/AI reasoning tags. On earbud channel, read the answer concisely, not entire transcript/citations; full written answer is available afterward.

## 6.5 Debrief and evaluation rubric

Six human-readable dimensions: **Question comprehension; Problem framing; Reasoning and trade-offs; Technical accuracy; Clear communication; Evidence and specificity.** For each, provide specific behavior, an excerpt/timestamp where available, a suggested repair, and a targeted drill. Scores may be optional, derived from transparent rubrics and uncertainty estimates, and must not be compared with real employer pass bars.

Evidence levels: `Recorded / Verified transcript`, `Candidate-reported recollection`, `AI simulation`, `External general guidance`. Never silently mix levels. No emotional-state profiling, deceptive lie-detection, facial beauty/culture scoring, or protected-characteristic inference.

---

# 7. Interview Memory and learning continuity

## 7.1 Memory object model

- `InterviewGoal`: user ID, role, optional company, stage/round, date, JD documents, topics, consent settings; isolated tenant scope.
- `InterviewSession`: goal ID, mode, capture status timeline, route changes, authorization state, timezone, audio deletion policy, timestamps.
- `Turn`: speaker pseudonym, words, temporal boundaries, provisional confidence, source hash, correction history.
- `Question`: normalized question, exact sourced wording if available, topic, follow-up chain, interviewer/candidate turn refs.
- `Answer`: candidate turn spans, user-edited revision, alternatives, explanation, improvement markers.
- `Evidence`: audio object ID or approved text reference, time range, source classification, model/processing version.
- `Feedback`: rubric, rationale, cited examples, uncertainty, suggested drill.
- `SkillSignal`: concept, session references, demonstrated evidence, weak/strong estimate with confidence, practice suggestions.
- `Action`: user-approved preparation task, reminder, status.
- `Authorization`: legal/organizational basis, user acknowledgment, revocation and policies. Avoid claiming universal compliance from a checkbox.

## 7.2 Memory views

**Round page:** questions asked; candidate's own examples; what was strong; improvement opportunities; unresolved follow-ups; session gaps.  
**Role goal:** how preparation changed from screen to loop; questions recurring; reviewed improvements; planned next round.  
**Personal skills:** technical gaps and proof of improvement, excluding unsupported psychometric judgments.  
**Ask across rounds:** “Which multi-region reliability questions have I struggled with and what improved?” requiring evidence chips and date.

## 7.3 Correction and truthfulness

User can correct a transcript, speaker assignment, mistaken question boundary or inferred company context; resulting summaries, question trees, embeddings and coaching signals are invalidated/recomputed where relevant. Keep auditable edit history visible to the account owner. If user deletes recording, any evidence requiring that recording becomes unavailable or linked derivatives are removed according to the chosen data policy; do not falsely offer replay after deletion.

## 7.4 Job progression loop

`Prepare → Practice → Interview (if permitted) → Reflect → Fix one skill → Retry → Next Round`. 
Progress is based on specific revisable skills, not raw hours or flattering aggregate scores. Suggestions adapt to candidate's explicit goals and the source provenance of past interviews.

---

# 8. Voice, Bluetooth and mobile production behavior

## 8.1 Audio routes

- **Phone near laptop speakers:** Room capture can hear remote interviewer when laptop sound is actually audible; verify preflight.
- **Laptop connected to private headset:** Phone microphone usually will not hear interviewer voice; don't claim capture. Use authorized desktop connection if developed or practice/reflection only.
- **Phone pocket + earbud:** The headset mic may capture wearer only. Full-room diarization cannot be promised; route state should say so.
- **iOS Bluetooth HFP:** Selecting an HFP input/output can couple input and output automatically; the app must query the actual route after configuration, not assume independent split. Apple documents explicit route-change handling and stopping private audio on disconnect.
- **Android:** Microphone foreground-service starts are restricted in the background. Start from visible user action and maintain lawful/OS-valid foreground process and recording indicator. Test all targeted OS versions.

## 8.2 Latency budget (candidate targets, not measured)

| Event | Proposed service-level objective | Measurement boundary |
|---|---|---|
| Live stable transcript | P95 ≤3.0 s after meaningful phrase end | local audio time → rendered stable text |
| Question type/context | P95 ≤3.5 s | question end → context state |
| Short live insight | P95 ≤6.0 s | qualifying trigger → visible card |
| On-demand text first useful response | P95 ≤5.0 s | ask send → meaningful text |
| Private voice first words | P95 ≤7.0 s | ask send → intelligible earbud audio |
| Route change detection | ≤1.5 s under supported conditions | OS notification → UI corrected |
| Stop capture guarantee | immediate local stop (test instrumented), server acknowledgment eventually | user stop → local frames stopped |

Prioritize never showing stale, incorrect, or misrouted guidance over chasing aggressive timing.

## 8.3 Session lifecycle

`IDLE → SETUP → AUTHORIZATION → PREFLIGHT → CONNECTING → LIVE → PAUSED ↔ LIVE → ENDING → FINALIZING → READY`. 
Separate exceptional paths: `MIC_DENIED → TEXT_PRACTICE/REFLECTION`, `RECORDING_PROHIBITED → NO_CAPTURE`, `AI_PROHIBITED → PRE/POST_ONLY`, `ROUTE_LOST → SAFE_PAUSE/RECOVER`, `NETWORK_LOST → LOCAL_BUFFER/DEGRADED`, `LOW_BATTERY → WARNING/SAVE`, `STORAGE_FULL → PAUSE_AND_NOTIFY`, `AUTH_EXPIRED → REAUTH`, `USER_REVOKED → HARD_STOP`, `DELETION_REQUESTED → RETENTION_WORKFLOW`.

Differentiate `Mute AI speech`, `Silence nudges`, `Pause microphone`, and `End session`; none of these actions silently changes the others.

## 8.4 Failure behavior

- Audio feed unavailable: persistent `Not listening` state. No simulated inference.
- Low signal and packet loss: preserve local encrypted segment buffer with bounded retention and sync cursor; mark holes and deliver degraded mode; do not infer missing questions.
- Backend failure: capture locally only if user explicitly agreed and capacity permits; otherwise stop with prominent notice.
- Earbuds disconnect during private guidance: cancel queued TTS; never switch to loudspeaker automatically.
- Incoming call: obey OS interrupt; show accurate pause; reconcile segment ordering afterward.
- Speaker separation poor: use `Speaker A/B` or `Unknown`; no named person without review/grounding.
- Memory source lost: retract citations/replies rather than inventing a source.
- AI provider outage: concise status and resume/alternative-provider policy; do not leak unapproved data by automatic provider switch.

---

# 9. Architecture and implementation boundaries

## 9.1 Clients

Native **Swift / SwiftUI (iOS)** and **Kotlin / Jetpack Compose (Android)** with shared design tokens, API/event contracts and a common evaluation suite. Adopt cross-platform UI only after validating critical background capture, Bluetooth, accessibility and render fidelity. Offline practice content may be supported incrementally; don't promise fully offline real-time AI on every device.

## 9.2 Services

- **API/Auth:** identity, tenant-scoped goals, consent policies, session lifecycle, device registration.
- **Realtime gateway:** session authorization, encrypted transport, audio sequence acknowledgments, backpressure, reconnect and cutover.
- **Speech pipeline:** streaming ASR with token timestamps, diarization where multiple speakers and sufficient audio quality justify it, turn segmentation, stable/provisional transcripts.
- **Context service:** goal and current question state, role-specific constraints, versioned context updates.
- **Interview engine:** question generator, interviewer simulation, feedback rubric, conversation turn orchestrator.
- **Nudge engine:** candidate generation + timing/evidence/policy/rate limit gates.
- **Output router:** text/voice selection, detected earbuds, cancellation policy and OS interruption handling.
- **Memory and retrieval:** structured questions/answers/feedback, PostgreSQL/pgvector, source object storage, strict ACLs, freshness/version invalidation.
- **Task service:** opted-in reminders and study plans.
- **Observability:** privacy-minimized traces, quality metrics, OS/capture diagnostics and redacted error logs.

## 9.3 Decision rationale

- PostgreSQL first for sessions, permissions, corrections and questions; pgvector for scoped retrieval. Avoid premature graph/database fragmentation.
- Streaming ASR and diarization are different model tasks. Nemotron-style diarization may label anonymous speakers but does not resolve actual identity or generate accurate transcript by itself.
- Support direct transcription/meeting integrations only where explicitly authorized and platform-permitted; not silent cross-app capture.
- Isolate personal and enterprise data at every query and downstream derivation; never mix interview sessions with confidential meeting data by default.
- Use feature flags and staged rollouts for fragile audio routing and proactive voice.

## 9.4 Illustrative API contracts

```text
POST /v1/interview-goals                 create or update role goal
GET  /v1/interview-goals/{goalId}        retrieve goal with scoped auth
POST /v1/interview-sessions/preflight    capabilities, policy, routes
POST /v1/interview-sessions              start authorized practice/live session
POST /v1/interview-sessions/{id}/events   transcript/question/route events
POST /v1/interview-sessions/{id}/ask      on-demand answer
POST /v1/interview-sessions/{id}/pause    pause microphone or practice state
POST /v1/interview-sessions/{id}/end      finalize and reconcile
GET  /v1/interview-sessions/{id}/debrief  sourced post-session coaching
GET  /v1/interview-goals/{id}/memory      goal-scoped cross-round search
POST /v1/interview-goals/{id}/drills      generate targeted practice
PATCH /v1/interview-turns/{id}            corrected content/speaker
DELETE /v1/interview-sessions/{id}        deletion and derivative revocation
```

**Illustrative live insight object:**

```json
{
  "kind": "CLARIFY_REQUIREMENT",
  "text": "Consider clarifying the consistency requirement before choosing storage.",
  "source_kind": "AI_REASONING",
  "question_id": "q_042",
  "context_version": 17,
  "priority": "high",
  "valid_until_ms": 175000,
  "delivery": ["TEXT"],
  "confidence": 0.88,
  "authorization_scope": "PERMITTED_LIVE"
}
```

`valid_until_ms` is relative to the live timeline; it is not a security authorization. Server-side policy still controls allowed operations.

---

# 10. Privacy, security and responsible interview use

## 10.1 Threat model

Threats include private audio leakage, accidental loudspeaker playback, unauthorized assistance in restricted assessment, cross-goal/tenant retrieval, consent spoofing, sensitive resume/JD leakage, transcript prompt injection, malicious uploaded JD instructions, stale/misattributed citations, oversized retention, insecure exports, and false claims of employer-specific evaluation.

Controls:
1. Separate explicit flags for `recording_authorized` and `ai_assistance_allowed`, checked on server for relevant endpoints.
2. Maintain OS-visible recording and user-facing pause/end affordances; consent must be legally sufficient for jurisdiction and participants, not merely app permission.
3. Encryption in transit and at rest, device-bound encrypted local buffer, envelope keys and scoped access logs.
4. Strict tenant/user/goal ACL at retrieval **and** embedding/index level; controlled sharing with redaction and revoke.
5. Uploaded JD/resume/transcript treated as untrusted data; instruction hierarchy enforced outside retrieved text.
6. Retention controls, export and deletion with audited derivative/cache purging.
7. Data residency and vendor processing options disclosed; do not automatically transfer sensitive recording to new providers.
8. Private voice fails closed on route disconnect; no surprise speaker fallback.
9. No automated employment prediction, disability/health/emotion profiling, accent-based discrimination or protected-class inference.
10. Allow enterprise disabling of live AI and recording according to policy.

## 10.2 Integrity UX

The app should say: “Does this interview permit AI assistance?” and separately “May you record all participants?” Disallowed choices route to Practice/Reflection. **Practice requires no third-party permission** when it is wholly user-generated or simulator-based; user should still control their own data. Where regulations differ, deployment counsel must review consent and applicable data-protection rules; these specs are not legal advice.

---

# 11. Accessibility and localization

- Voice-to-text, visible caption corrections, optional text-only mock, text size/contrast, VoiceOver/TalkBack, reduced motion and haptic alternative.
- On low bandwidth, downgrade to transcript/answer-only and show progress, never pretend an audio stream is connected.
- Support international accents via proper evaluations, not claims; multilanguage/CodeSwitch ASR quality gates prior to marketing broad coverage.
- Candidate sets answer language and coding language separately; role packs should use natural regional wording, not stereotyped speech judgments.
- No penalty based on accent, speech disability, non-native English or long cognitive pauses; score only task-relevant evidence with visibility into uncertainties.
- Adaptive coaching should be opt-in and never require an “ideal” personality or speaking style.

---

# 12. Quality targets and evaluation

**Proposed targets to validate, not achieved metrics:**

| Product dimension | Candidate gate |
|---|---|
| Successful end-to-end 60-min permitted session, supported test matrix | ≥99.5% without unannounced recording loss |
| Crash-free sessions | ≥99.8% |
| Unauthorized AI/recording path blocked in tests | 100% of policy-gated cases |
| Real private-voice route disconnect | 0 unintended loudspeaker disclosures in test corpus |
| Cited question/answer factual attribution | ≥98% in annotated eligible samples |
| Proactive nudge usefulness | ≥80% rated actionable in matched blind trials |
| Unwanted Balanced nudges | ≤1 per 30 min typical live session |
| Stable live transcript P95 | ≤3 seconds after phrase end in supported audio conditions |
| Proactive text P95 | ≤6 seconds after validated trigger |
| Post-interview debrief completeness | 100% missing-capture gaps labeled |
| Source deletion/authorization revocation | All derivative consumers respect revocation in instrumented tests |
| Accessibility | Critical journeys usable with TalkBack/VoiceOver and dynamic font scaling |

**Evaluation datasets:** diverse devices and earbud profiles; laptop speakers vs headset; multiple languages and accents; overlapping speech and poor acoustics; quiet thoughtful pauses; mock topic drift; incomplete recordings; contradictory interviewer turns; consent prohibitions; prompt-injected JDs; back-to-back interview rounds.

**User experience research:** blind compare mock quality vs Huru, live glanceability vs current solutions, debrief usefulness vs human coaching, retention after 4 sessions, next-round preparedness and user-initiated referrals. Measure real task outcomes, not claimed hiring probabilities.

---

# 13. Release gates and build sequence

**Gate A: Polished skeleton + integrity.** Shared MeetSaathi design system; Interview Home/Goals/Practice/Reflection; robust permission states and sample simulation; no fake recording badges.

**Gate B: Real audio and practice.** Native microphone permissions, streaming ASR, practice interviewer orchestration, turn-taking, realistic follow-ups, answer lab, fallback to typed practice, robust OS interruptions. Must work reliably across diverse speech and devices.

**Gate C: Grounded memory.** Stored sessions, sourced question tree, correction flow, debrief rubric, cross-round practice recommendations, source deletion.

**Gate D: Permitted live assistance.** Verified policy UI, explicit start, tested phone/table/pocket routes, short text nudges, real-time Ask, conservative proactive scheduling, proof of no private audio leak.

**Gate E: Global quality.** Localization, accessibility, security review, red-team tests, privacy legal review by market, device matrix, stress/load/cost evaluations, pilot user outcomes.

No “throwaway prototype” codebase: these are staged production-bound increments with feature flags and acceptance gates. Public shipping only when the specific feature's reliability, safety and experience pass its gate.

## Engineering ownership breakdown

- **Mobile/audio:** iOS/Android session lifecycle, routing, real capture, accessibility.
- **AI/speech:** streaming ASR, diarization, question detection, interview simulation, confidence, evals.
- **Backend/memory:** authorization, data, source corrections, semantic/structured retrieval, event replays.
- **Product/design:** live glanceability, mock conversation pacing, debrief usefulness, content systems.
- **Security/quality:** consent, red-team, reliability, test labs, release controls.

---

# 14. Detailed acceptance checklist

See `MeetSaathi_Interview_Release_QA.csv`. Coverage includes: onboarding; goal creation; user data import; mock session and tough follow-ups; typed alternative; live eligibility; recording gates; actual microphone and earbud routes; lock-screen continuation; route loss; pause/resume; proactive quality; Ask; sourced debrief; transcript/speaker corrections; cross-round memory; consent revocation; deletion; accessibility; localization; offline/degraded path; adversarial input; security isolation; observability; user trust.

---

# 15. The North Star test

A candidate opens MeetSaathi the night before a technical interview, completes a realistic spoken mock, gets two honest improvements, and rehearses them. During the actual interview, the app either respects the interview's no-assistance rules **or**, if explicitly permitted, provides short, relevant help without stealing attention or leaking private audio. After the round, the candidate can accurately review what happened, understand gaps, and enter the next interview better prepared.

**Winning quality = natural interaction + real learning improvement + trustworthy memory + dependable mobile behavior.** Not maximum suggestion volume, maximum AI-generated word count, or impressive-sounding scores.

---

# 16. Sources and verification links (accessed October 18, 2026)

- Final Round AI: https://www.finalroundai.com/ — markets live interview co-pilot, mock practice and debriefs.
- Huru comparison: https://huru.ai/compare/huru-vs-final-round-ai/ — mock-practice positioning, dated September 2026.
- Android foreground microphone restrictions: https://developer.android.com/develop/background-work/services/fgs/restrictions-bg-start
- Android foreground service requirements: https://developer.android.com/develop/background-work/services/fgs/service-types
- Apple App Review Guidelines, recording indications: https://developer.apple.com/app-store/review/guidelines/
- Apple `playAndRecord`: https://developer.apple.com/documentation/avfaudio/avaudiosession/category-swift.struct/playandrecord
- Apple Bluetooth HFP route coupling: https://developer.apple.com/documentation/avfaudio/avaudiosession/categoryoptions-swift.struct/allowbluetooth
- Apple audio route changes and unplug behavior: https://developer.apple.com/documentation/avfaudio/responding-to-audio-route-changes

**Implementation note:** API contracts, metrics and diagrams are specifications / hypotheses, not deployed services or measured product outcomes.
