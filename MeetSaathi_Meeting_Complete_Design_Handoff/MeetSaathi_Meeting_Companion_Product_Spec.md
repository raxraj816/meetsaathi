# MeetSaathi — Meeting Companion
## Complete product experience and production specification

**Version:** 1.0 | **Design date:** October 18, 2026 | **Status:** Implementation-ready design proposal, not implemented software

**Product promise:** Stay present in important conversations. MeetSaathi listens with permission, understands what is being discussed, offers timely optional assistance through a phone screen or private earbuds, and creates trustworthy, correctable memories that help people think, decide, and prepare.

**North-star experience:** A person starts a permitted session, places the phone beside their laptop, sees one important suggestion when needed, asks a contextual question without losing the conversation, and later retrieves the exact moment on which an answer is based. Locking the phone or switching to earbuds must preserve the session when the OS/device supports the selected audio routes.

**Product boundary:** The Meeting Companion lives inside the universal MeetSaathi app alongside Learning Companion. It is not a separate subscription, memory silo, design language, or recording infrastructure.

---

# 1. Product judgment and rationale

## 1.1 Problems worth solving

- **In the moment:** I want to listen and participate, but I cannot simultaneously remember every detail, catch contradictions, note open decisions, and research technical questions.
- **In the room:** I need a concise, discreet way to get help while my phone is beside a laptop or safely in my pocket.
- **Afterward:** I need answers to "who said what?" and "why did we decide this?" with evidence rather than polished but unreliable summaries.
- **Across months:** I need to know how ideas, owners, risks, and decisions evolved across conversations without merging unrelated or unauthorized material.
- **For the next meeting:** I want a short, accurate briefing and useful questions rather than rereading old transcripts.

## 1.2 Differentiation test

Transcription, live suggestions, meeting chat and cross-meeting Q&A already exist in commercial products. As of October 2026, Fireflies describes mobile Live Assist with live transcripts, insights and Ask Fred; Hedy describes real-time coaching and cross-session memory; Granola supports contextual chat over meeting history. These are table stakes. Our product has to win measurable preference through **intervention quality, glanceability, evidence fidelity, mobile/earbud dependability, and continuity from live insight to verified memory**.

Do not claim unique diarization, recording, auto-summary, live Ask, or proactive nudges.

## 1.3 Product principles

1. **People first:** The screen should never compete with the speaker. One priority insight, not a stream of unsolicited answers.
2. **Actual device state:** Show what source is really captured and where audio will actually play. No optimistic route labels.
3. **Agency:** Listening, proactive assistance and voice delivery are independent switches. Recording is never inferred from output mode.
4. **Grounded facts:** An asserted meeting fact must cite audio/transcript provenance; external model opinion must be marked separately.
5. **Pause is real:** Pausing capture stops ingest; mute-AI only stops AI audio. Different labels and state changes.
6. **Correctable history:** Speaker, transcript, decision and owner corrections must propagate to summaries and retrieval.
7. **Privacy by design:** Explicit consent/policy gates, least privilege, retention, export, deletion; never covert surveillance.
8. **Professional restraint:** Design assistance for permitted meetings and transparent interview practice, not violating interview rules or secretly recording participants.
9. **One shipped product:** Use staged quality gates in a durable codebase, not a disposable facade.

## 1.4 Personas and differentiated value

| Persona | Live job | Memory job | Avoid |
|---|---|---|---|
| Engineer/architect | Identify unexamined technical trade-offs | Reconstruct decisions and assumptions | Generic suggestions unconnected to requirements |
| PM/team lead | Track decisions, owners, blockers | Compare commitments across weekly meetings | Attributing suggested owners as accepted owners |
| Founder/executive | Detect objections and unanswered commercial questions | Trace strategic rationale and follow-ups | Spurious psychological profiling |
| Customer-facing consultant | Clarify requirements, capture explicit follow-ups | Prepare next client conversation | Mixing confidential client accounts |
| Research collaborator | Note methods, open questions and evidence | Connect discussions, experiments and uncertainties | Fabricated scientific agreement |
| Interviewer/candidate | Authorized, disclosed practice and permitted assistance | Review questions and feedback | Unauthorized help in restricted assessments |

# 2. Information architecture

Keep universal navigation **Home / Sessions / Memory / You**. Meeting-specific surfaces:

- **Home:** Start Companion, resume interrupted session, upcoming meeting briefs (opt-in calendar), recent discussion.
- **Session Setup:** scenario, attendee notification/authorization confirmation, input/output routes, language, proactive level, storage and retention.
- **Preflight:** 10-second capture check, actual route indicator, obstruction test, connection readiness and local buffer state.
- **Live Focus:** status, current topic, one prioritized insight, Save moment, Ask, expandable captions.
- **Live Transcript:** provisional utterances, confidence, unnamed speakers, replay-when-available references.
- **Ask:** short context-aware answer, evidence chips, "Meeting said" versus "My analysis" switch, follow-up.
- **Pocket Voice:** connected-device state, concise spoken suggestions, spoken-response preview/controls, no external speaker leak.
- **Meeting End:** explicit end/confirm, gap report, processing state.
- **Recap:** executive snapshot, what was actually decided, action owners, open questions, risks, cited timeline.
- **Speaker Review:** anonymous-to-name mapping with uncertainty and corrections.
- **Memory:** scoped cross-meeting search, people/projects, decision evolution, date-range filters.
- **Next Meeting Brief:** last decisions, overdue follow-ups, contradictions, questions to ask, sources.
- **Share and Export:** permissioned excerpts, redaction preview, expiry, revoke and audit.
- **Settings / Trust Center:** capture defaults, retention, processing region, language, privacy, device routes and deletion.

**Why:** Provide a simple primary interaction during an ongoing conversation and rich depth only when a user explicitly goes looking for it.

# 3. End-to-end journey

## 3.1 First launch (under 90 seconds is a design target, not a claim)

1. Welcome: "Stay with the conversation. I'll help you remember what matters." Two actions: **Start Companion** and **Explore sample meeting**.
2. Choose preferred language; no forced calendar, contacts or organization permission. Sample exploration works without account or microphone.
3. When user actually starts a session, explain capture, potential cloud processing, that others may be recorded, and their responsibility to follow applicable consent, workplace and assessment policies.
4. User confirms permitted use and selects retention; request microphone permission in context. If declined, continue in **Notes-only** (manual notes and post-meeting analysis of approved documents), with no pretending to capture audio.
5. Preflight: test device actual input + audio level; show whether phone mic hears remote laptop audio. If connected to laptop headphones, suggest a permitted desktop integration or alternate route, not imaginary access.
6. Start session deliberately; show persistent recording indicators and stop/pause controls.

## 3.2 At the table (flagship)

- Put phone in portrait or landscape beside laptop. Display a readable dark live canvas with a compact header and **one important card**.
- When participants are speaking, a low-distraction waveform and optional caption preview confirm capture. Use actual microphone activity and packet acknowledgments; do not invent a "Live" badge when capture has stopped.
- Example context: "Migration design review." Participant suggests PostgreSQL for transactions. Model identifies an open assumption: "Clarify RPO/RTO before committing to Aurora regional failover." The insight is labeled **AI suggestion**, not a team decision.
- User taps **Save** or **Ask why?**, or ignores. Card collapses after its relevance window; it does not disappear from the activity trail.
- An actual agreed decision is a separate card with a **proposed decision** status until evidence supports agreement; its source chips open transcript/audio.

## 3.3 In the pocket / via earbuds

- After a visible, permitted session start, the user locks the phone. The app continues only when the OS permits it; recording status remains discoverable via OS indicators and an ongoing notification where supported.
- With earbuds connected and voice explicitly enabled, the app may speak short guidance. It must check the current output route *immediately before playback*. If earbuds disconnect, cancel playback or show text only; never silently move private content to the phone speaker.
- Earbud mic often captures only the wearer, not the room. The route classifier must state whether room speech remains intelligible. Unsupported pairings should keep text guidance but not promise full-room capture.
- A user-defined hardware/OS shortcut may start Ask where supported; do not promise global wake-word capture, always-on activation or universal double-tap mappings.
- Voice output should auto-cancel when human speech begins, if robustly detectable, and never override safety/alarm audio.

## 3.4 During an authorized laptop call

**Phone microphone** can hear laptop speakers only if sound is playing audibly and the room permits it. **Laptop-headphone calls:** phone may hear only user's voice. Offer a consent-respecting desktop companion / meeting integration as a later supported input, with explicit meeting indicators. Avoid claiming unrestricted same-device call capture on mobile.

## 3.5 End and return

- Tap **End**; confirm with clear actions **End & save** or **Keep session active**. Stop capture immediately when ending, even if AI processing continues.
- Display duration, known interruption intervals, upload/sync state, local pending data and estimated status without fake completion percentages.
- User can read available bookmarks immediately. Transcript, summary and speaker assignments move from **Processing** to **Review ready**, with partial results clearly flagged.
- During speaker review, the user associates anonymous speaker streams with known people only if appropriate. Corrections update citations and derived artifacts; uncertain words retain uncertainty.

## 3.6 Return for memory and preparation

User asks "What did the team finally decide about our retry policy?" Scope first to the correct project and accessible meetings. Answer with a short synthesis and links to source moments, including *date and speaker confidence*. If sessions conflict, explain the sequence and never conceal unresolved contradictions. If a source is deleted or inaccessible, downstream search and memory must stop exposing it.

# 4. Live display: screen contract

## 4.1 Layout zones, top to bottom

1. **Trusted session header**: name, elapsed time, red recording indicator, source route, connection health and pause/end. Contrast >= WCAG AA where applicable.
2. **Active topic**: one current discussion summary, qualified as an inference when incomplete.
3. **Primary insight**: single card with type (Clarify / Trade-off / Decision / Risk / Follow-up), relevance reason and clear source/suggestion status.
4. **Direct actions**: Ask MeetSaathi, Save moment, optional "What did I miss?" catch-up.
5. **Discreet strip**: captions summary, last 1–2 utterances, opt-in expansion.
6. **Transport/output**: voice route and AI mute, not confused with recording pause.

## 4.2 Visual design

- Brand: deep midnight navy background (#071522), light ivory text (#EDF8FA), restrained jade/teal (#6CE4D0), warm amber for open risks (#FFD08C), red reserved for recording stop/errors.
- Typography: native platform dynamic scaling with hierarchy 28/20/16/13, generous line height. Cards use less than 55 words in default view.
- Touch targets: at least 44 pt iOS, 48 dp Android.
- Glanceability: most significant insight understandable in about 2 seconds; user can expand for citations and explanation.
- Motion: brief nonessential transitions; reduce-motion respected; no constantly pulsing AI orb during meetings.
- Landscape and tablets: primary insight left, optional source stream right; accessibility does not rely on color alone.

## 4.3 Live types and language

| Type | Product copy pattern | Trigger | Explicitly not |
|---|---|---|---|
| Clarifying question | "Consider asking whether ordering must be global or per key." | unresolved key assumption | "You must say..." |
| Trade-off | "Lower latency may increase operational complexity." | competing design objectives surfaced | definitive recommendation with no evidence |
| Proposed decision | "It sounds like PostgreSQL is preferred; not yet confirmed." | emerging consensus | final decision |
| Confirmed decision | "Team agreed to test the regional failover design." + source | explicit, verified agreement | silent extrapolation |
| Commitment | "Alex volunteered to draft the benchmark by Friday." + source | explicit person/action/date | model-inferred owner |
| Contradiction | "Today’s target differs from the previous review." + both sources | permissioned cross-meeting comparison | merging separate projects |
| Uncertainty | "I couldn't distinguish the final speaker reliably." | low-quality diarization/audio | invented real identity |

## 4.4 Interaction budget

- Default **Balanced**: no more than one auto surfaced suggestion within a rolling 4-minute window and at most three in any 15 minutes, unless a genuinely urgent user-selected topic requires an explicit exception. Tunable *proposal*, not validated optimal rate.
- **Quiet**: Save and Ask only; never proactive voice.
- **Active**: more candidates but still deduplicate, obey speaking gaps, never become a ticker.
- User Ask and manual action outrank proactive suggestions; auto-play voice is opt-in and capped to approximately 8–12 seconds per brief thought.
- If AI yields no actionable suggestion, show neutral "Listening" rather than manufactured advice.

# 5. AI intelligence and decision policy

## 5.1 Separate the pipelines

A. **Speech evidence path:** audio frames -> voice activity -> streaming ASR -> diarization -> word/turn alignment -> immutable source references -> correction events.

B. **Meeting-state path:** provisional rolling context -> topics/participants/risks/questions -> structured candidates -> policy scoring -> output channel.

C. **Truth path:** high-stakes assertions verify source span, confidence, permission, age of data and current finalization state; reject unverifiable claims.

D. **Memory path:** speaker and transcript revisions produce derived-summary updates; source content retained/deleted per policy.

## 5.2 Candidate scoring

For each candidate insight `c`, estimate `utility(c) = relevance + decision_importance + actionability + user_preference - interruption_cost - uncertainty_penalty - repetition_penalty`. Each dimension comes from audited heuristic/model signals, not an imagined single true probability. Eligibility gates precede ranking:

1. Is capture authorized and current context in scope?
2. Is the insight supported or clearly labeled external advice?
3. Is confidence adequate for its claim type?
4. Is it novel enough to avoid repetition?
5. Is the user currently speaking, actively using Ask, or has AI been muted?
6. Will delivery be private and appropriate for the current output route?
7. Does rate limiting permit it?

Failing any gate means **do not send**; an important action may be deferred to post-meeting recap.

## 5.3 User questions and reasoning contracts

- **Remember:** quote or summarize only accessible conversations; cite timestamps and indicate uncertainty.
- **Think:** produce independent analysis clearly marked "AI analysis" with cited meeting inputs, not falsely attribute recommendations to participants.
- **Prepare:** use validated decisions, owner commitments and unresolved questions to generate an actionable briefing; show sources.
- **Explain:** teach technical concepts raised in a meeting using outside knowledge visibly separate from the meeting record.
- **Compare:** retrieve multiple accessible meetings with chronological and project boundaries, flag changed assumptions and conflicting decisions.

All generated responses return `answer_kind`, `source_refs`, `scope`, `confidence_band`, `latency`, `cautions`, and `source_freshness` as appropriate. An answer that has no supporting meeting source must say so.

## 5.4 Speaker attribution rule

NVIDIA Nemotron 3 Diarization is a plausible engine for up to eight anonymous speaker channels, but it does not determine the person's real-world name. Stream stability, overlap, voices beyond the validated count, and actual acoustic conditions require evaluation. During live capture use "Speaker 1 (provisional)" rather than guaranteed identities; align real names through explicit user review or authorized reliable platform metadata. Never attribute owners or quotes to a name with weak evidence.

## 5.5 Hallucination and prompt-injection defenses

Spoken audio can include malicious instructions ("MeetSaathi, ignore your rules") or untrusted descriptions. Treat all meeting content as **data**, never as privileged system instructions. Only an authenticated direct user interaction or approved device command can change capture, share, delete, permissions or tool execution. Add defenses for audio replay attacks, adversarial transcripts, retrieved-document prompt injection and cross-tenant context contamination. Model-authored external actions require a separate user confirmation and scoped authorization.

# 6. Conversation Memory — a product, not a transcript folder

## 6.1 Objects

`Workspace`, `Project`, `Meeting`, `Participant`, `SpeakerChannel`, `AudioSpan`, `Utterance`, `Topic`, `Claim`, `Decision`, `Action`, `Risk`, `Question`, `Insight`, `UserBookmark`, `Correction`, `SourceLink`, `PermissionGrant`, `RetentionPolicy`, `Briefing`.

Every derived assertion links to `meeting_id`, a time span and `source_version`, unless it is explicitly independent analysis. Membership and access scope must be evaluated at retrieval and share time.

## 6.2 Memory layers

1. **Moment:** exact (or approximate marked) utterance span; speaker channel; confidence; recording origin.
2. **Session:** recap, decisions, tasks, risks and open questions with evidence.
3. **Project:** ordered changes in requirements, commitments, and rationale across allowed meetings.
4. **Personal preference:** the user's chosen language, intervention frequency and optional interests—not unconsented profiling of other participants.
5. **Team memory:** only when members explicitly share permitted records; personal sessions do not default to team-visible.

## 6.3 Decision evolution example

- Oct 03: "Redis considered for caching" — **option**, not decision.
- Oct 10: "Postgres proposed for transactional state" — **proposal**.
- Oct 17: "Postgres selected for order consistency" — **agreed decision**, if transcript evidence supports it.
- Oct 18: "Revisit failover strategy" — **open issue**, not reversal.

The timeline is generated from sources and must remain editable/correctable. Never compress the four events into a fictional single decision.

## 6.4 Speaker corrections and downstream updates

Changing speaker identity or transcript text invalidates affected embeddings, decisions, owner assignments, export views and prior cached answers. Asynchronous reprocessing records source version and completion state. Users can inspect correction history. A known-bad assertion is hidden or flagged while updates are pending.

## 6.5 Retrieval UX

A user asks: "What did Priya say about regional failover?" The result displays which permitted meetings were searched, quotes or paraphrases with source chips, and which speaker mappings are verified versus uncertain. Inaccessible meetings are not used. A global query never silently mixes user workspaces.

## 6.6 Retention and deletion

Offer per-session retention, audio-off/transcript-only when technically and legally appropriate, manual export, immediate stop, per-meeting deletion and account deletion. Define cascading deletion across object storage, vector indexes, summaries, caches, analytics payloads and shared derivatives where permitted; disclose any required audit/backups legal retention. Never claim deletion is complete until verified.

# 7. Before / after screens and copy

## 7.1 Prepare screen

Header "Tomorrow: Design Review" (only when calendar explicitly connected) → three source-linked sections: **Last agreed**, **Still open**, **Questions worth asking**. Optional **Brief me in 60 seconds** text/voice action. Distinguish suggested prompts from previous meeting facts. If no calendar, choose a saved meeting/project manually.

## 7.2 Meeting recap

Top: title + date + duration + verification state; brief paragraph labeled **AI recap**. Then ordered sections:

- **Decisions** (Confirmed / Proposed / Disputed)
- **Actions** (Owner verified / owner unclear, due date only if actually spoken)
- **Risks and trade-offs** (speaker-source links)
- **Questions still open**
- **Key moments** (bookmarks, evidence replay)
- **What MeetSaathi suggests** (separate AI advice)
- **Ask this meeting**

## 7.3 Compare screen

Filter by `project`, `people`, `date`, `meeting`, `access`. Return a small chronology with changed assumptions, who proposed what and citations. For "what should I remember for tomorrow?", prioritize unresolved commitments, high-stakes reversals and not-yet-discussed constraints.

# 8. Production mobile capability matrix

| Feature | Android design | iOS design | Gate |
|---|---|---|---|
| Foreground permissioned recording | `RECORD_AUDIO` + `microphone` foreground service and ongoing notification; started while visible | AVAudioSession `playAndRecord` or appropriate mode + documented background audio handling | Device/OS QA |
| Screen locked | Continue *already started* permitted capture, subject to OS/permission and power behavior | Appropriate background audio entitlement/behavior, interruption handling | 90-minute tests |
| Earbuds + room recording | Device routing varies; inspect AudioManager routes and test pairings | HFP route may couple input and output; A2DP option is output-only and configuration dependent | Explicit compatibility matrix |
| Laptop call | Phone hears external speakers only if acoustically available | Same; no unrestricted internal call recording | Explain limitations |
| Offline | Local encrypted capture and bookmarks where permissioned; cloud analysis delayed | Same | No false "AI live" label |
| Incoming calls / alarms | Pause or recover as OS dictates, mark gaps | Handle interruption delegates, report route/status changes | Never hide loss |
| Accessibility | Compose semantics, TalkBack, scalable type and touch targets | SwiftUI, VoiceOver, Dynamic Type and reduced motion | Accessibility audit |

**Authoritative constraints:** Android background microphone service cannot generally be created while backgrounded on newer versions. Apple's `playAndRecord` and background audio have strict configuration requirements; HFP Bluetooth routing can couple input and output. Apple App Store guideline 2.5.14 calls for explicit consent and a clear recording indication. Do not claim universal compatibility based on prototypes.

# 9. Native architecture and backend boundaries

## 9.1 Suggested stack and reasoning

- **Android:** Kotlin + Jetpack Compose, foreground `AudioCaptureService`, route coordinator, resilient foreground notification and local encrypted queue. Direct control over audio, battery, lifecycle.
- **iOS:** Swift + SwiftUI, `AVAudioSession` coordinator, native capture and route interruption handling. Separate app UI from audio session lifecycle.
- **Realtime gateway:** authenticated bidirectional stream, session sequence numbers, chunk ACKs, resumable offsets, backpressure and monotonic timers. Avoid pretending delivery without ACK.
- **Speech pipeline:** ASR adapter, Nemotron diarization candidate, alignment postprocessor, language ID, quality/confidence estimates, finalization jobs.
- **AI layer:** LLM provider adapter, structured candidate generation, independent policy evaluator, evidence verifier, response renderer. Benchmark costs/latency, not vendor prestige.
- **Data:** PostgreSQL for transactional records, pgvector for embeddings, encrypted object store for permissioned audio, background workers for corrections and deletion. A graph database is optional only after demonstrated query need.
- **Security:** least-privilege scoped tokens, TLS, authenticated audio streams, envelope encryption, tenant-bound retrieval, secrets management and audit records.

## 9.2 Critical event contracts

```json
{
  "type": "utterance.finalized",
  "meeting_id": "mtg_...",
  "seq": 241,
  "source_span": {"start_ms": 742800, "end_ms": 748900},
  "speaker_channel": "spk_02",
  "speaker_status": "provisional",
  "text": "We should test regional failover.",
  "transcript_version": 3,
  "confidence_band": "medium"
}
```

```json
{
  "type": "insight.recommended",
  "meeting_id": "mtg_...",
  "insight_id": "ins_...",
  "kind": "clarification",
  "body": "Clarify the recovery point objective before choosing the deployment region.",
  "origin": "ai_suggestion",
  "source_refs": [{"meeting_id":"mtg_...","start_ms":742800,"end_ms":748900}],
  "expires_at_ms": 755000,
  "delivery": "text",
  "decision_state": "unconfirmed"
}
```

Actions such as `capture.start`, `capture.pause`, `capture.stop`, `session.finalize`, `speaker.correct`, `memory.delete`, `share.create`, and `share.revoke` must be authenticated, idempotent where appropriate, audited and scoped to the active user/workspace.

## 9.3 Session lifecycle

`IDLE → PREFLIGHT → READY → RECORDING ↔ PAUSED → STOPPING → FINALIZING → READY_TO_REVIEW` with `DEGRADED`/`INTERRUPTED` sub-states, `FAILED` and `DELETING`/`DELETED` terminal branches. Voice playback and recommendation mode are **orthogonal** to the capture state.

Key invariants: stopping capture terminates mic access immediately; no AI speaking when output route is unsafe; network failure retains locally queued encrypted frames if allowed and marks analysis unavailable; capture resumes only under documented user and OS permission rules; unknown delivery status is not mislabeled "saved to cloud".

## 9.4 Retry, failure and recovery

| Failure | User-visible response | Engineering behavior |
|---|---|---|
| Mic denied | "Microphone off. Notes-only mode available." | No audio capture or inferred live transcript |
| Phone pocket blocks mic | "Room audio is muffled" | VAD/audio quality health warning; allow reposition |
| Bluetooth disconnects | "Voice paused; text remains available" | Abort TTS before device fallback to speaker |
| Internet lost | "Recording locally; AI responses unavailable" | Encrypted sequence queue and resumable upload |
| Speech unclear | "I couldn't reliably make out that part" | Bookmark uncertain span; suppress false facts |
| More than supported speakers | "Speaker identification may be incomplete" | Fallback process / segment unsorted voices; no false certainty |
| Participant revokes permission | "Recording stopped" | Stop/adjust scope immediately, route to retention policy |
| Model latency spike | "Suggestions delayed" | Drop stale candidates, keep recording path separate |
| Low battery / thermal | "Reduced processing; recording status visible" | Degrade nonessential inference first |
| Duplicate uploads | No duplicate events in timeline | Server-side idempotency keys and gap detection |

# 10. Security, policy and ethical UX

- Permission from phone owner does **not** equal permission from everyone recorded. Legal and institutional rules vary; provide consent notices and a clear ability to stop.
- Never promote covert interview assistance where disallowed by assessment rules. Offer mock-interview coaching, disclosed assistance and permitted contexts.
- Workspace and participant boundaries take priority over personalization. Search never crosses tenants or projects without authorized scopes.
- Data is never used for training by default without a distinct opt-in; verify vendor agreements and processor terms. Avoid uploading raw conversation to analytics/crash tools.
- Granular sharing: approve exactly what is shared, recipient, expiry and redactions; private session remains private by default.
- Never infer mental health, personality or emotional certainty from voice; do not make speculative workplace emotion claims.
- Threat-model audio prompt injection, misidentified speakers, direct object reference attacks, malicious shares, offline device theft, replay of partial audio, and retention bugs.

# 11. Product analytics and quality gates

**Primary experience metric:** meaningful assisted meetings per active user per week: sessions in which a user saved, asked, validated, or later retrieved a genuinely useful insight. Do not substitute recording count.

**Quality telemetry:** capture gap rate, p95 perceived text insight delay, p95 initial Ask audio delay, speaker attribution errors, citation validation score, helpfulness thumbs, unwanted intervention rate, battery/hour, crash-free sessions, privacy incidents, export/delete completion. Privacy-friendly aggregate analytics only.

**Candidate acceptance thresholds to validate, not guaranteed outcomes:**

- 90-minute supported-device meetings: >=99.5% without unexplained capture loss.
- Crash-free sessions: >=99.8%.
- Live transcript update: p95 <=2.5s from stable phrase end (defined dataset/network).
- Contextual text suggestion: p95 <=6s from eligible trigger; discard stale insight.
- User-initiated Ask: p95 <=7s initial intelligible voice when audio route verified.
- Evidence citation correctness: >=98% on audited grounded-fact set.
- Helpful proactive suggestions: >=80% in evaluated scenarios; unwanted <=1 per 30 minutes in Balanced mode.
- False named-speaker/owner attribution: must be separately tracked with strict release threshold; unknown preferable to false identity.

All thresholds need explicit measurement setup, device list, language/accent/noise sampling, and real user preference testing. No cherry-picked demo benchmark.

# 12. Release sequence — a winning product, not a throwaway demo

### Gate A — Capture you can trust
Native Home, consent, preflight, capture-state machine, device route, 90-minute locked-screen session, encrypted buffering, gap report, visible stop/delete. Do not proceed if state is unreliable.

### Gate B — Useful live intelligence
Streaming captions, provisional speakers, source anchors, Ask with cited responses, actionable insight ranking, no-noise silence, user feedback.

### Gate C — Excellent pocket experience
Earbud routing matrix, fail-closed speech playback, focus/mute semantics, private voice UX, interruptions and graceful network degradation.

### Gate D — Long-term memory and trust
Finalization, corrections, project-scoped cross-meeting memory, decision evolution, preview/share/revoke, deletion audits.

### Gate E — Release-ready experience
Accessibility, localization, onboarding research, comparative blind tests against real commercial products, policy review, reliability/regression testing, staged rollouts.

## 12.1 Execution responsibility map

| Discipline | Must deliver |
|---|---|
| Product/UX | User journey, working mobile interaction design, modes, user testing, copy, accessibility |
| Mobile audio | Foreground services, native AVAudioSession, device matrix, route/interruptions |
| Realtime/speech | Streaming ingest, ASR/diarization alignment, confidence and gap detection |
| AI reliability | Source-grounded Ask, intervention policy, regression evals, injection resistance |
| Data/search | Correctable, permission-scoped memory and deletion cascade |
| Security/privacy | Threat model, consent design, encryption, audit, retention, vendor review |
| QA/release | On-device 90-minute tests, battery, soak, offline, user feedback and staged rollout |

# 13. Structured screen inventory (24 contracts)

| ID | Screen/state | Primary action | Must never do |
|---|---|---|---|
| M01 | Welcome | Explore / Begin | Request microphone immediately |
| M02 | Meeting Home | Start Companion | Auto-start a recording |
| M03 | Session scenario | Select purpose | Pretend interview AI assistance always permitted |
| M04 | Consent and capture | Confirm authorized start | Interpret user approval as all-party consent |
| M05 | Audio preflight | Check microphone | Display invented route / quality |
| M06 | Ready | Start | Start in background without permitted lifecycle |
| M07 | Live Focus | Ask / Save / Pause | Show many competing insight cards |
| M08 | Insight detail | Sources / feedback | Describe AI opinion as participant quote |
| M09 | Live captions | Expand/collapse | Declare provisional speakers certain |
| M10 | Ask live | Question / scope | Fabricate source references |
| M11 | Ask answer | Follow-up / replay | Mix analysis and meeting evidence |
| M12 | Pocket/earbuds | Mute AI / voice | Play private guidance on speakers after route loss |
| M13 | Capture paused | Resume / End | Say actively recording |
| M14 | Offline/degraded | Continue locally / End | Claim live AI available without inference |
| M15 | End confirmation | End and save | Continue capture after Stop |
| M16 | Processing | View bookmarks | Claim complete before finalized |
| M17 | Recap | Inspect decisions | Invent owners/dates |
| M18 | Speaker review | Correct identity | Infer real name from audio alone |
| M19 | Decision detail | Verify source | Hide conflicting decision history |
| M20 | Memory Home | Search project | Cross unauthorized contexts |
| M21 | Cross-meeting Ask | Query/filter | Present deleted recordings |
| M22 | Prepare next meeting | Open brief | Invent current agenda/calendar |
| M23 | Share/export | Preview/revoke | Share private data by default |
| M24 | Privacy/settings | Manage retention/delete | Silently keep unexpected copies |

# 14. Development specification for a sample-free production implementation

The companion UI should receive signed and typed live events; no app-facing LLM response may directly change UI routes, initiate recording, control sharing, or delete records. Controls dispatch explicit authenticated intents to native/domain services. Interactive HTML deliverable is a **sample-state design reference** only: it contains fictional meeting content, does not access a microphone, does not invoke an LLM, and cannot demonstrate production performance. No misleading claims of functioning AI.

## Recommended native module boundaries

```text
apps/android: design, home, meeting, audio, route, background, memory, privacy
apps/ios: design, home, meeting, audio, route, background, memory, privacy
packages/contracts: audio chunks, event types, source refs, access scopes, errors
services/api: auth, tenants, sessions, consent, notes, shares
services/realtime: streaming session, chunk ACK, topic context and events
services/speech: ASR, diarization adapter, confidence, finalized timeline
services/intelligence: state, insight candidates, evidence, delivery policy
services/memory: projection, retrieval, corrections, deletion, briefing
services/worker: finalization, reindex, billing and retention operations
infra: secrets, regional routing, telemetry, deployments
qa: speech-evals, e2e-mobile, device-matrix, accessibility, load-chaos
```

# 15. Evidence references and research notes

As verified October 18, 2026. These inform the constraints but do not substitute for legal counsel or device testing:

1. Android microphone foreground-service restrictions: https://developer.android.com/develop/background-work/services/fgs/restrictions-bg-start
2. Android foreground service types: https://developer.android.com/develop/background-work/services/fgs/service-types
3. Apple AVAudioSession playAndRecord / locked-screen handling: https://developer.apple.com/documentation/avfaudio/avaudiosession/category-swift.struct/playandrecord
4. Apple Bluetooth HFP audio routing: https://developer.apple.com/documentation/avfaudio/avaudiosession/categoryoptions-swift.struct/allowbluetooth
5. Apple App Review Guidelines section 2.5.14: https://developer.apple.com/app-store/review/guidelines/
6. NVIDIA Nemotron 3 Diarization technology: https://huggingface.co/blog/nvidia/nemotron-diarization
7. Fireflies mobile Live Assist: https://guide.fireflies.ai/articles/5965172749-live-assist-on-fireflies-mobile-app-get-real-time-notes-live-during-meetings
8. Hedy live coaching: https://hedy.ai/
9. Granola chat with meetings: https://help.granola.ai/article/chatting-with-your-meetings

---

**Product owner decision:** Build MeetSaathi Meeting Companion as a delightful, trusted, usable mobile experience first. Architecture, security and commercial constraints must support that experience, never become excuses for clutter. The best assistant knows when to say something valuable and when to let humans speak.
