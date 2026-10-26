---
title: "MeetSaathi | Product Experience and Interaction Specification"
subtitle: "Mobile-first UX, real-time companion behavior, voice, memory, states, implementation contracts and release acceptance criteria"
date: "14 October 2026"
status: "Product experience specification | Version 1.0 | Build-ready design intent, not an implemented application"
---

# Product charter

**Mission.** Make important conversations easier to understand, navigate and remember by giving people an intelligent, permission-aware mobile companion that knows when to help and when to stay quiet.

**Product promise.** *Stay present. MeetSaathi remembers what matters and helps you think in the moment.*

**One-action foundation.** The dominant action in the product is **Start Companion**. The user should not have to understand ASR, diarization, retrieval, or model orchestration. They choose whether assistance is silent text, earbud voice, or both, and the product responsibly manages the rest.

**What this document does.** It defines the complete intended mobile user experience, visual language, interaction contracts, AI behaviors, trust mechanisms, test cases and engineering acceptance gates. It complements the previously prepared Global Product & Company Blueprint; it does **not** falsely represent a completed production app. Production readiness requires implementation, legal review, platform verification and field testing.

**Why this focus.** Existing products, notably Hedy, already advertise live suggestions, on-demand chat and configurable suggestion frequency. MeetSaathi cannot win on a checkbox. It must be demonstrably better at suggestion timing and precision, screen-off continuity, evidence-linked memory, user trust and glanceable mobile design. [R1]

## The experience people should remember

A user places their phone beside a laptop, taps **Start Companion** after meeting disclosures/permissions, and returns attention to the humans on the call. A few minutes later, a single small card appears: **"Decision isn't final — ask who owns failover testing."** The user understands it in one glance, without scrolling. If they tap, MeetSaathi shows a reason and the underlying transcript timestamp. They later lock the phone, put it in a pocket and, where the device supports the selected audio route, hear a short earbud suggestion only at an appropriate moment. After the meeting, they ask: "What did we commit to, what remains uncertain, and what should I prepare before next week?" MeetSaathi answers with linked, replayable evidence and visibly separates its analysis from statements actually spoken.

# 1. Product principles and choices

| Principle | Product requirement | Reason and trade-off |
|---|---|---|
| Human conversation comes first | The live dashboard has one primary suggestion and a quiet status line; no infinite feed taking over the screen | The user should look at people, not babysit AI; sacrifices information density for focus |
| One tap to enter | From Home, Start Companion with remembered safe settings; preflight only on permission/source/device changes | Reduces friction without silently bypassing consent |
| Voice optional | Text is the default in face-up mode; earbud playback requires explicit opt-in and route check | Avoids public playback surprises and audio collision |
| Evidence by design | Any statement attributed to a participant links to source segment(s) and speaker confidence | Prevents unearned authority and false attribution |
| AI humility | Clearly label **From conversation**, **MeetSaathi suggests**, **Outside explanation**, and **Unclear** | Generated reasoning must not masquerade as recorded facts |
| Deliberately quiet | The algorithm has a “do nothing” outcome and user-configurable interruption limits | A companion that always talks is a distraction |
| Device-aware truth | Capability badges reflect actual mic/earbud route and network status, not aspirational support | Bluetooth and background behavior differ by OS/device [R2-R4] |
| No surprise capture | Clear recording status and relevant participant notice/consent before capture; Stop always reachable | Trust and platform compliance come before convenience |
| Accessible globally | Responsive type, large targets, RTL, translated UI and multilingual ASR evaluation | Worldwide ambition demands native-quality usability |
| Production-intended delivery | Every publicly shipped workflow meets its own reliability, safety and observability gates | Release small areas well instead of a giant fragile feature list |

## Product boundaries

- **Supported:** business meetings, engineering discussions, classes, conferences, interviews **when AI use is explicitly permitted**, and other lawful/consented interactions.
- **Not supported:** covert recording, bypassing workplace or assessment restrictions, identity guessing from voice, mental-health/emotion labeling of bystanders, or undisclosed third-party transcription.
- **Not assumed:** a phone in a pocket can hear a whole conference room well; laptop headphone audio can magically be heard by a separate phone; all earbuds provide hardware-button controls; iOS allows simultaneous phone-mic input and Bluetooth-earbud playback on every headset.

# 2. Information architecture and navigation

Five destinations, with the **session** presented as an immersive surface rather than a permanent tab:

1. **Home** — Start Companion, upcoming/contextual conversation, recent memories, microphone/earbud readiness.
2. **Memories** — session timeline, search, collections/projects, cross-conversation answers.
3. **Ask** — general thinking companion, scoped to "This meeting", "Project", "All permitted memories", or "General".
4. **Activity** — decisions, unresolved questions, actions awaiting confirmation, preparation briefs. Can live inside Memories at initial release to keep navigation simpler.
5. **You** — devices, assistance preferences, languages, permissions, privacy, storage, accessibility.

**Primary bottom navigation:** **Home · Memories · Ask · You**. Activity is embedded in Memories until usability testing demonstrates a need for a fifth tab. Why: fewer top-level choices improve discoverability and return-to-session speed.

**Universal gesture / placement:** A persistent session mini-bar appears when a session is active and the user leaves Live; tap returns to Live. `Stop` remains visible on the Live screen and in the platform status controls where supported.

## Assistance is separate from delivery

| Independent dimension | Choices | Default | User mental model |
|---|---|---|---|
| Assistance | Listener / Ask / Companion | Companion Balanced **only after user opts in**; otherwise Listener | How proactive should AI be? |
| Delivery | Silent text / Earbud voice / Text + voice | Silent text | How should I receive help? |
| Capture | Phone microphone / permitted desktop audio bridge / imported audio | Phone mic, if audible and consented | What can MeetSaathi hear? |
| Placement | Face-up / face-down / pocket / stand | Auto-adapt display; don't pretend to detect a reliable acoustic placement | Where is my phone? |
| Retrieval scope | Current session / selected project / permitted history / general | Current session | What information may AI use? |
| Processing | Cloud / supported local mode | Explicitly disclosed cloud path where needed | Where is content processed? |

**First-run default rationale:** Users should enter with predictable, discreet behavior. No proactive earbud speech, automatic hidden recording, or assumptions about remote call audio. Once users choose preferences, safe settings can be remembered per context.

# 3. End-to-end user journeys

## J1 — First launch: honest 60-second orientation

**Trigger:** App installed; first open.

1. Welcome screen: single sentence, illustrated phone-and-earbud positioning; primary **Get started**.
2. Choose primary use (Technical meeting / Business meeting / Lecture or conference / Other). This influences suggestion templates, not access rights.
3. Explain recording: "MeetSaathi processes conversations you choose to start. Make sure recording and AI assistance are permitted and participants are informed when required." Separate check before beginning each session as appropriate to context and law.
4. Ask for microphone permission *at the moment Start needs it*, not during a generic welcome carousel.
5. Ask for notifications only when user enables lock-screen continuity; ask for Bluetooth/audio controls only when a voice device is connected.
6. Offer a brief interactive walkthrough of the live dashboard using **illustrative content**; no attempt to activate real recording.
7. Enter Home with clear Start Companion action.

**Success:** User understands what it listens to, how it communicates, and how to stop; no unexplained permission prompts. **Failure:** If mic permission denied, show **Enable microphone** and **Explore without recording**, never a dead screen.

## J2 — Phone face-up next to laptop: the flagship

1. Tap **Start Companion**.
2. Session sheet shows title (optional), type, mic source, output (default Silent text), assist level and participant disclosure confirmation.
3. 3-second acoustic preflight checks mic is producing plausible speech levels; caution if blocked/muffled; do **not** delay session when a safe route is known.
4. Enter **Live**: top bar with capture state and elapsed time, central **One Insight** card, short transcript preview beneath, persistent **Ask** affordance, unobtrusive control row.
5. If high-value insight arrives, card updates with small visual entrance; do not move surrounding controls unexpectedly or autoplay voice.
6. Tap card → **Why this matters** with source context and optional **Ask about this**.
7. Swipe or tap dismiss → no repeated equivalent observation; the card can be revisited in Insight history.
8. Tap **End** → confirmation if user is still capturing; stop capture immediately, then summarize asynchronously.

**Success:** User can read the top insight in ~2 seconds, distinguish facts from suggestions, and never needs to scroll to Stop.

## J3 — Phone down / screen locked

1. Start while app is visibly active. Lock screen or turn phone over.
2. Recording continues only through approved platform background mechanisms and visible OS indicators. For Android, microphone foreground service start generally needs to occur while the app is foreground. [R3]
3. On temporary network loss, encrypted bounded local buffering operates; clear status is available on reopen.
4. When capture ends unexpectedly, state changes to **Capture interrupted**, rather than implying listening continued.
5. A system control/notification offers **Return to session** and **Stop** where platform permits; do not leak transcript in notifications by default.

**Success:** No silent loss and no invented coverage. Face-down is a physical posture, not a privacy bypass.

## J4 — Pocket + earbuds

1. Start the session and select **Earbud voice**. Complete route check.
2. App identifies the real active input and output. If the Bluetooth HFP path forces input to the headset, explain the consequence and require validation of room pickup. On iOS, route behavior can couple selected HFP input and output. [R2]
3. Offer a 5-second private sample and volume level check.
4. A suggestion becomes eligible only if sufficiently important, conversation isn't in a critical speech turn, and no voice is already being played.
5. Spoken hint is short; detailed answer remains in the app. Immediate **Mute voice** action available through device-supported controls and Live screen.
6. If earbuds disconnect, stop private speech immediately; never suddenly play personal advice on the phone loudspeaker. Continue text-only unless explicitly authorized otherwise.

**Success:** No unanticipated audible disclosure; user's ability to hear others remains primary.

## J5 — Laptop call with headphones (the often-missed constraint)

1. User sees **Remote voices might not reach your phone** when laptop headphones are detected by user-selected setup.
2. Offer **Use laptop speakers** (if permitted and audible), **Connect desktop bridge** (when available), or **Continue with limited pickup** with a warning.
3. Desktop bridge requires explicit OS permissions and a visible pairing handshake; clearly label the audio source and consent obligations.
4. Session evidence marks source/channel provenance and synchronized timestamps.

**Success:** No false completeness of meeting transcript.

## J6 — Live question without changing screens

1. Tap **Ask** bottom sheet; its header indicates scope **Current conversation**.
2. Quick prompts: **What was decided? / What's unclear? / Explain this / What should I ask?**
3. Type or invoke voice query. If voice query competes with ambient meeting audio, show **Hold to ask** or another tested mechanism rather than continuously leaking the user's private question into the shared meeting.
4. Answer returns as a readable 2-4 sentence summary with source chips or analysis label; details behind **Expand**.
5. Answer preserves live context while user continues reading; transcript recording doesn't freeze.
6. Close sheet to return to exactly the prior Live scroll/insight position.

**Success:** Useful response without losing place or duplicating audio capture.

## J7 — Appropriate proactive guidance

1. Topic changes to disaster recovery. Context builder detects that an architecture decision is proposed with no target RPO/RTO or recovery owner.
2. Intervention model constructs a **candidate**, not an immediate user-visible notification.
3. Candidate passes relevance, evidence, repetition, interruption and current-timing checks.
4. **Text:** card shows "Recovery objectives aren't agreed yet" and "Consider asking who defines RTO/RPO." **Voice:** short version only if user enabled voice and conversation pause is detected.
5. If decision later appears in the transcript, invalidate or update the insight with revision source; don't continue warning about a resolved issue.

**Success:** Suggestion is actionable while the conversation can still change. No guessed participant attribution.

## J8 — Meeting ends and a usable memory appears

1. End session. UI immediately confirms **Recording stopped**; processing may continue separately.
2. Show usable immediate notes (if available) labeled **Preliminary**. Final transcript/diarization refines it without fabricating speaker names.
3. Display **Decisions / Actions / Open questions / Highlights / Full transcript**. Actions are **Proposed** until user verifies owner/deadline.
4. Every attributable item links to time segments; users can correct transcripts and speaker labels.
5. Follow-up question persists in the session memory but its retrieval permissions follow the session's access policy.

**Success:** User leaves with a clear next step and can audit where it came from.

## J9 — Ask across weeks or months

1. Open **Memories**, choose project or search all permitted sessions.
2. Ask: "How did our Aurora failover decision evolve?"
3. Response presents a brief timeline with distinct **Proposed → Revised → Agreed** decisions and timestamped evidence.
4. If evidence conflicts or spans two people with anonymous identities, display the ambiguity prominently.
5. AI can separately offer its own architectural opinion under **MeetSaathi analysis**.

**Success:** User can verify the timeline; no hidden mixing of other workspace's data.

## J10 — Interview and assessment context

**Only support AI assistance when recording and AI use are permitted by the organizer and participants.** Offer a clear session-type choice: **Interview practice**, **Interviewer notes** (with permissions), and **AI-permitted live interview**. The app must not advertise covert or policy-violating assistance. The same great UX applies to authorized settings; do not promote hidden screen or hidden audio cheating.

## J11 — User corrects the system

User says "Speaker 2 is Mira, not Rahul" or corrects a misheard word. The correction must create an audit record, update relevant derived facts and future retrieval, and show whether identity confirmation is user-supplied. Older AI answers may be invalidated or marked **Corrected since answer**; they must not silently remain authoritative.

## J12 — Complete deletion

User chooses **Delete this session** or **Delete all memories**. Explain scope (audio, transcripts, derived summaries, embeddings, caches and backups subject to published retention), show implications for linked actions, then fulfill the deletion workflow with verifiable completion status. Delete should not be a cosmetic hide from UI.

# 4. Screen-by-screen interaction contracts

Notation: **P0** means essential to a successful core product. **P1** means a valuable expansion that can ship after the core quality bar is met. All screens have explicit loading, empty, retry, offline and permission-denied states.

| ID | Screen/surface | Content hierarchy and core actions | P |
|---|---|---|---|
| S01 | Welcome | Clear promise → 3 contextual usage illustrations → Get started | P0 |
| S02 | First-run disclosure | Permissions explanation, processing location, explicit agreement to recording obligations | P0 |
| S03 | Home | Start Companion CTA; device readiness; recent sessions; resume memory | P0 |
| S04 | Session setup sheet | Title optional; type; assistance; output; capture source; consent check; Start | P0 |
| S05 | Audio preflight | Live mic level, current input/output devices, sample playback, routing warning | P0 |
| S06 | Live focus dashboard | Status; One Insight; 2-3 line live transcript; Ask; controls | P0 |
| S07 | Full live transcript | Speaker chips, provisional text, time markers, search, source status | P0 |
| S08 | Ask bottom sheet | Scope; quick prompts; input; succinct response; linked evidence; return | P0 |
| S09 | Insight detail | Recommendation, why, evidence/inference label, dismiss/save/ask, timestamp | P0 |
| S10 | Pocket/voice controls | Output routing, mic status, voice level, mute, interruption level | P0 |
| S11 | Session recovery | Capture/network/audio route status; affected interval; retry/end | P0 |
| S12 | End/processing | Recording stopped; preliminary vs finalized; navigation to memory | P0 |
| S13 | Memory detail | Headline, key outcomes, actions, decisions, open questions, timeline, Ask | P0 |
| S14 | Evidence player | Audio segment with timestamp, source words, confidence, speaker correction | P0 |
| S15 | Memories library | Search, filter by people/project/time, list, empty state, deletion | P0 |
| S16 | Global Ask | Scopes, response provenance, cite/replay, follow-up, memory permission | P0 |
| S17 | Speaker review | Anonymous labels, evidence clips, user mapping, confidence and revision | P0 |
| S18 | Preferences | Assistance, output, languages, accessibility, devices, storage | P0 |
| S19 | Data & privacy center | Consent records, retention, processing modes, exports, deletion | P0 |
| S20 | Desktop bridge pairing | Supported platforms, visible pairing, capture disclosure and disconnect | P1 |
| S21 | Brief before next meeting | Relevant prior notes, active issues, people, goals, Ask | P1 |
| S22 | Activity/action inbox | Proposed actions, ownership verification, status, integrations | P1 |
| S23 | Landscape companion | High-visibility one-card live layout for phone stands/tablet | P1 |
| S24 | Feedback/evaluation | Was this useful? Why? Dismissal, trust and timing micro-feedback | P0 |

## S03 Home: content contract

**Above the fold:** wordmark, device status pill, large **Start Companion** button, single-line explanation of currently selected assistance/output. A light card may say **"Mic: phone · Output: silent text"**. Recent session preview only if it doesn't crowd the primary CTA.

**Avoid:** busy analytics, gamification streaks, prominent subscription ads or long AI marketing copy. Why: the user's top job is starting a reliable session within seconds.

**Tap Start behavior:** if microphone/notice/routing needs action, show setup; otherwise enter safe remembered settings with a short optional confirmation. The app must not start recording merely because Home opened.

## S06 Live Focus: pixel hierarchy by conceptual regions

- **Top 12%:** [Live indicator] [elapsed] [real input quality] [speaker count if reliable]. **End** is always findable. Status text is never only a colored dot.
- **Next 45%:** single primary insight, with category, one bold claim and one sentence of action; tapping reveals evidence and reasoning. When no insight, show **"Listening. I'll surface something useful when it matters."** Do not fill silence with generic platitudes.
- **Next 18%:** most recent meaningful speaker turn(s), limited lines; user can open full transcript.
- **Bottom 25%:** Ask bar and thumb-accessible controls: Mute AI, Insights history, Transcript, End. Keep input keyboard from obscuring End; when sheet opens, separate fixed session controls.

**Cards:** default at most one pinned top insight and two archived in a collapsible view. No persistent toast spam. A card can expire when topic changes; expired cards remain in history marked **Not current**.

## S08 Ask sheet: answer design

- **Question:** "Why did they reject DynamoDB?"
- **Header:** `From this meeting` or `MeetSaathi analysis`.
- **Answer:** "They prioritized relational queries and transactional updates. The discussion did not rule out DynamoDB for other workloads."
- **Evidence:** `18:42` and `32:15` (tap for transcript/audio). Only display such chips when real aligned source segments exist.
- **Follow-up:** **"Should I challenge that choice?"** moves to analysis mode and clearly labels independent reasoning.
- **Unknown state:** "I didn't hear a clear decision. Would you like me to show the relevant part of the discussion?" Never infer one silently.

## S13 Memory detail: information architecture

**Above fold:** meeting title, date/time, duration, completeness/processing status, main conclusion (with source), **Ask about this**.

Then sections in order: **Decisions**, **Your next steps**, **Open questions**, **Highlights**, **Participants** (only confirmed names), **Transcript & audio**, **Related conversations**. The order places outcomes before text walls. Any source citation opens Evidence player. User can correct items and control retention.

## S16 Speaker correction: important nuance

Diarization might only return Speaker A and Speaker B. UI should say **"Speaker A (unconfirmed)"** until matched by supported metadata or user correction, not confidently infer that the voice is a named individual. If two people overlap, show **overlapping speech**; don't force a false single speaker. Identity map may be session-local unless user consents to persistent cross-session linking.

# 5. Visual design system (implementation tokens)

**Brand stance:** sophisticated but warm, technical but welcoming. Avoid a robotic cyberpunk look, glowing gradients everywhere, or distracting “AI is thinking” animations. Use a restrained teal accent only for live/primary companion actions. The logo should visually work at 20 px; icon motif: two conversational arcs becoming a subtle sound wave. Avoid claiming logo/trademark clearance.

| Token | Light | Dark | Usage / why |
|---|---|---|---|
| Background | `#F7F9FC` | `#0B1220` | Calm base; dark suits dim conference rooms |
| Surface | `#FFFFFF` | `#111D2F` | Content layers; clear separation |
| Elevated | `#EAF0F6` | `#1A2A40` | Focused insight cards |
| Primary text | `#172338` | `#F3F7FC` | Readability |
| Secondary text | `#51627A` | `#AFBCD0` | Supporting details |
| Accent | `#007E82` | `#5CE0CC` | Primary CTA and listening state |
| Caution | `#9A5C00` | `#F4C56A` | Mic quality, uncertain speaker |
| Destructive | `#B73242` | `#FF7585` | Stop destructive actions, deletion |
| Borders | `#DBE4EE` | `#2A3A51` | Quiet hierarchy |

**Type:** iOS San Francisco and Android Roboto/system font. No external font dependency. Suggested mobile scale: display 28-32 sp/pt, heading 21-24, section 16-18, body 15-17, secondary 12-14; adapt to Dynamic Type/font scaling and layout wrapping. Do not use 11 px tiny transcript text to cram content.

**Spacing:** base 4-unit grid, common paddings 12/16/20/24, 16-20 corner radius for major panels, 10-12 for small controls. Max line width for paragraph answers around 60-72 characters in wide views.

**Touch:** at least 48dp target for Android controls; use comparable large target area on iOS, test with accessibility sizes. Android guidance recommends 48dp minimum. [R5]

**Motion:** 120-180ms subtle transitions; one card at a time; no jumping transcript focus; respect Reduce Motion, low power and battery constraints. Sound waves are ambient status indicators, not evidence that speech recognition is accurate.

**Layout:** Live mode portrait optimized first; landscape support for desktop-side usage. Keep strong contrast, VoiceOver/TalkBack labels, safe area insets, notches, folding displays, and split-screen behavior.

**Haptics:** single gentle tap for an important eligible insight when user opts in; never repeat buzzes. Respect DND and accessibility settings; no haptic for low-priority generic insights.

# 6. Proactive intelligence: exact behavioral specification

## 6.1 The intervention loop

The AI runs a **candidate generation → evidence binding → policy evaluation → timing evaluation → delivery** pipeline. Generation never implies delivery.

1. **Understand:** recognize current topic, speaker-agnostic proposals, open questions, constraints, decisions, risks and whether a question has been answered.
2. **Propose:** create candidate with type, source span(s), explicit action, target time window, relevance features, expected impact, uncertainty and expiry.
3. **Ground:** if claim references the meeting, require time-aligned source. If general advice, label it as independent suggestion.
4. **Score:** outcome improvement, novelty, contextual relevance, confidence, conversational urgency, disruption risk and overlap with shown suggestions.
5. **Gate:** check user assistance setting, conversation/assessment permissions, cooldown, quiet hours, private delivery availability, network/audio state and user dismissals.
6. **Time:** wait for turn-taking pause or other delivery-appropriate interval, except safety-critical user-approved alerts.
7. **Render:** 1 short title + 1 actionable sentence for Live; optional detailed follow-up; voice <= ~8 seconds as a design target, with text fallback.
8. **Learn:** collect explicit useful/not useful feedback and opt-in aggregated product quality metrics, not indiscriminate private-content training.

## 6.2 Example insight categories

| Category | Eligible situation | Suggested text | Reason / confidence boundary |
|---|---|---|---|
| Open decision | Two alternatives discussed, no final choice | "Decision still open — confirm which approach you'll take." | No invented consensus |
| Missing constraint | Architecture proposal without stated latency objective | "Worth asking: what's the latency target?" | Domain heuristic; label suggestion |
| Conflicting evidence | Current statement contradicts sourced prior commitment | "This differs from the prior plan. Want to compare?" | Exact linked sources required |
| Owner ambiguity | Action agreed without owner | "Who will own the rollout checklist?" | Must not fabricate owner |
| Risk | Design lacks failure/retry discussion | "Consider how retries and duplication will be handled." | Hypothesis, not known flaw |
| Opportunity | User's stated goal connects to opening in discussion | "This is a good moment to clarify the success metric." | Requires context; avoid generic advice |
| Learning | Unfamiliar term appears and user opted into learning mode | "Want a quick explanation of change-data capture?" | Don't presume comprehension deficits |
| Follow-up | User's explicit question hasn't been answered | "Your question about disaster recovery is still unanswered." | Only if tracked clearly |

**Forbidden:** fabricated quoted speech, psychological/emotional diagnosis, secret commentary about private traits, ungrounded named-speaker claims, instructions to evade interview restrictions, generic "great point" filler, unnecessary fear-inducing alarms.

## 6.3 Controls, cooldown and anti-spam

- **Off:** no unsolicited insights, manual Ask available.
- **Selective:** only highest-value timely interventions.
- **Balanced:** useful and actionable suggestions with a larger quiet budget.
- **Active:** more frequent guidance but still novelty/timing gated.
- **Hard user override:** Mute suggestions for 5/15/60 minutes or remainder of session, available in one tap.
- **Deduplication:** compare proposed insights to recent shown/dismissed candidates and current topic; do not repeat without material new evidence.
- **Expiry:** retire a candidate when the topic or underlying decision changes.
- **Voice restraint:** at most one voice suggestion at a time; end spoken guidance if route becomes non-private or user taps interrupt.

**Tunable starting hypotheses, not promises:** Balanced target <= 1 delivered suggestion / 4 minutes on average, more sparingly for content-poor meetings; Selective <= 1 / 8 minutes; Active <= 1 / 2 minutes. These are upper-frequency design constraints, not periodic schedules. Never manufacture a suggestion merely because a timer elapsed.

## 6.4 Grounding and response types

Every AI output includes `kind`: `conversation_fact`, `suggestion`, `external_explanation`, or `insufficient_evidence`. A `conversation_fact` with attributable content must contain ≥1 valid citation reference to the user's authorized source. A suggestion may draw on context but must not be disguised as a fact. External explanations cannot claim "the team said" absent source. If facts and suggestions co-occur, render in separate clearly labeled paragraphs/cards.

**Retrieval freshness:** Live Ask uses the current provisional transcript with clear provisional status; long-term memory queries use the latest approved evidence revision and honor deletion/access policy. Conflicting evidence is shown as a contradiction, not averaged into a fake consensus.

# 7. Earbud voice experience and audio choreography

## 7.1 User-facing voice behavior

- Voice is **off by default** and must be opted into separately from recording.
- Require headset route confirmation and a preview: **"This advice will be spoken privately through [device name]."**
- Show **Input source** and **Output destination** separately; UI reflects what the OS actually selected.
- Spoken proactive suggestions follow: **"One thing: confirm the database recovery target."** No intros like "As a large language model...".
- Long answers never auto-read in full. Speak a short summary, and offer **Continue** using a deliberate user action.
- Speaking stops immediately when earbuds disconnect or user mutes. Never fall back to handset loudspeaker without permission.
- Voice must not echo into the meeting's microphone where possible; acoustic echo cancellation and self-output suppression need real-device testing.
- If microphone routing means the meeting is poorly captured, show **"Voice is connected, but I may miss other speakers."** and provide an alternative.

## 7.2 Turn taking and barge-in

States: `listening`, `answer_requested`, `thinking`, `waiting_for_turn`, `speaking`, `paused`, `muted`, `route_unavailable`.

- User-issued queries have priority over unsolicited advice.
- If user begins talking during AI speech, pause/stop TTS according to configured behavior; do not keep reading over the user.
- For proactive speech, wait for pause detected by VAD plus semantic end-of-turn; false positives must be measured.
- Use short pre-announcement only when necessary, never a loud chime in formal meetings.
- Hardware earbud gestures vary, so provide a tested compatibility table and phone-based fallback; don't claim a universal double-tap command.

## 7.3 Platform constraints must affect design

- iOS Bluetooth HFP may couple microphone selection with headphone output. A2DP supports output-only routing in relevant configurations; actual supported combinations must be validated per device and audio session [R2].
- Android's `setCommunicationDevice` can select a communication output, with matching input selected by the OS; don't expose unsupported independent routing as a universal switch [R4].
- Android microphone foreground services need appropriate permissions and foreground initiation constraints [R3].
- Some advanced Bluetooth recording modes have device/region caveats; never build core promises exclusively around them [R2].

# 8. Conversation memory and thinking experience

## 8.1 Canonical evidence stack

Persist authorized source artifacts distinctly:

`Audio chunks / transcripts (versioned) → speaker turns (uncertain until confirmed) → topic segments → decisions/actions/open questions (proposed) → verified user corrections → derived summaries and vector index → answer citations`.

**Separation of truth:** Transcript is evidence, not always factually true; a participant's claim remains *what they said*. MeetSaathi's advice remains labeled AI analysis. Named identities require explicit map sources and confidence.

**What to remember:** user-chosen durable project facts, decisions with status and evidence, unanswered questions, agreed follow-ups, meeting metadata, language and opt-in personalization preferences. Don't convert every sentence into permanent behavioral profiling.

## 8.2 Memory screen behaviors

- Search natural language, speaker, topic, project or date.
- Every summary item expands to transcript and optional audio clip with timestamp.
- Surface gaps honestly: **"Audio was unavailable between 14:05 and 14:33."**
- Show contradictory decisions with context and source timing.
- Users can **Correct**, **Remove from memory**, **Export** and **Delete session**.
- Speaker names: `Unknown Speaker 2` until verified; overlap not forcibly assigned.
- Allow **Do not use this session for future suggestions** while keeping it locally accessible if the user chooses.

## 8.3 Ask: three user-visible lenses

1. **Remember** — strictly sourced answers from selected conversations.
2. **Think** — independent reasoning informed by clearly separated cited conversation context.
3. **Learn** — teach concepts using general knowledge, with references where appropriate; never attribute explanations to a participant unless actually stated.

Default to Remember for memory questions; offer one-tap **Think further** or **Teach me**. Why: it avoids the subtle but serious confusion between transcript facts and new AI advice.

# 9. Session state machines and edge cases

## 9.1 Recording lifecycle

`NOT_STARTED → PREFLIGHT → CAPTURING ↔ DEGRADED → CAPTURE_INTERRUPTED → RESUMING → CAPTURING → STOPPING → STOPPED → PROCESSING → READY`.

`PREFLIGHT` can also lead to `BLOCKED_PERMISSION`, `BLOCKED_CONSENT`, `UNSUPPORTED_ROUTE`, or `CANCELLED`.

**Strong invariants:**

- No microphone use before user initiates and required conditions hold.
- Status **Capturing** means audio samples are actually arriving at the recorder, not merely that Start was tapped.
- On local network loss but working local recording, status must say **Recording locally · AI paused**; no fictitious live reasoning.
- Stop ends capture even if network request fails; server control eventually reconciles.
- Reconnect resumes from sequence checkpoints and does not duplicate audio or an entire session.
- Any gap produces time-bounded evidence of missing audio; never interpolate fabricated quotes.

## 9.2 Error-state copy and appropriate fallback

| Trigger | Exact message | What user can do |
|---|---|---|
| Mic permission denied | "Microphone access is off. Enable it to start listening." | Open settings / Explore memories |
| Earbuds disconnected | "Earbuds disconnected. Voice suggestions are muted." | Reconnect / Keep text only |
| Input too quiet | "I'm having trouble hearing the conversation." | Test microphone / Move phone |
| Device route changed | "Audio route changed. Checking your microphone." | Continue after auto-test / Choose device |
| Network down, local recording healthy | "Recording locally. Live AI will resume when you're online." | Continue / Stop |
| Capture interrupted | "Recording paused unexpectedly. Some speech may be missing." | Resume / End |
| ASR uncertain | "I may have misheard this part." | Play or correct |
| Speaker unknown | "Speaker identity isn't confirmed." | Label speaker / Keep unknown |
| AI answer unsupported | "I couldn't verify an answer from the conversation." | Show relevant transcript / Ask general analysis |
| Processing ongoing | "Recording stopped. Final notes are being prepared." | Leave screen safely / View preliminary notes |
| Storage insufficient | "Storage is low. The session may stop recording." | Free space / End safely |
| Session deletion pending | "Deletion is in progress. Some copies may take additional time to expire." | View deletion status |

# 10. Microcopy and interaction examples

**Home:** "Ready when you are." Subline: "Listen, think and remember—with your permission." Button: **Start Companion**.

**Setup:** "How should MeetSaathi help?" Options: **Listen quietly**, **Show useful suggestions**, **Speak through earbuds**. Consent line: "Start only when recording and AI assistance are allowed and participants are appropriately informed."

**Live idle:** "Listening. I'll speak up only when there's something worth your attention." If Listener mode: "Listening quietly. Ask me anytime."

**Insight:** Category `DECISION`; title "Owner still unclear"; action "Ask who is responsible for rollback testing." Footnote `MeetSaathi suggests · Based on 18:32–20:10`.

**Fact:** "The team agreed to test failover before launch." Footnote `From conversation · 34:12`. **Do not show** without source segment.

**Voice control:** "Voice suggestions are off." When enabled: "Private audio: Pixel Buds" (actual detected name).

**Ask answer:** "Here's what I heard..." for sourced summaries; "My suggestion..." for inference; "I'm not certain..." for insufficient evidence.

**End:** "Recording stopped. You can leave—I'll finish preparing your notes." Never claim notes completed before they are.

**Delete:** "Delete this session and its saved memories? This cannot be undone once completed." Show actual retention/backups policy nearby.

## Tone guide

Confident but not overconfident; warm and succinct; fewer adjectives. Avoid sycophancy ("brilliant!"), speculation about people, alarming phrases ("critical danger!" absent evidence), and self-referential model language. Favor useful verbs: **Ask, Confirm, Compare, Clarify, Revisit, Check, Prepare.**

# 11. Accessibility, internationalization and privacy UX

- Dynamic Type / Android font-scale 200% tested with buttons visible and no clipped names, including landscape.
- VoiceOver/TalkBack labels use action and state, e.g. "Live recording, 24 minutes. Double tap for details."
- Contrast target at least WCAG AA where applicable; avoid encoding confidence/status only through color.
- Android tap targets ≥ 48dp; provide comparable generous hit regions in iOS. [R5]
- Transcript captions can be viewed without audio; user can disable voice and vibrations independently.
- Right-to-left layouts, bidirectional transcripts, per-session spoken language and code-switching; avoid hardcoding English-centric splitting or monolingual diarization expectations.
- Correct handling of India-region accented English, Hindi-English code-switching, other target languages and accessible spoken output requires real evaluators, not slogans.
- Privacy disclosures in plain language: **What is captured, who can see it, where it is processed, how long it lasts, and how to delete it**.
- Incoming private suggestion text and speaker content should be redacted from lock-screen notifications by default. No auto-sharing summaries.

# 12. Data contracts and event-driven interactions

## 12.1 Domain entities (logical)

`User`, `Workspace`, `Session`, `SessionConsent`, `DeviceRoute`, `AudioChunk`, `TranscriptRevision`, `Utterance`, `SpeakerSlot`, `SpeakerIdentityMapping`, `EvidenceSpan`, `InsightCandidate`, `InsightDelivery`, `AskTurn`, `Decision`, `ActionItem`, `Topic`, `MemoryFact`, `RetentionPolicy`, `DeletionRequest`.

Every session-owned entity carries `tenant_id`, `session_id`, authorization scope and timestamps. AI-generated objects carry model version, prompt/policy version, evidence revision, source refs, confidence calibration metadata and processing mode. No raw model-generated text may bypass authorization or source verification.

## 12.2 Live transport sample

```json
{
  "type": "insight.delivered",
  "event_id": "evt_01JEXAMPLE",
  "session_id": "ses_01JEXAMPLE",
  "sequence": 187,
  "created_at": "2026-10-14T09:15:06Z",
  "payload": {
    "insight_id": "ins_482",
    "kind": "suggestion",
    "category": "unresolved_decision",
    "title": "Recovery owner unclear",
    "action": "Ask who will validate the rollback plan.",
    "evidence": [{"utterance_id":"utt_91","start_ms":2035000,"end_ms":2049000}],
    "priority": "medium",
    "expires_at": "2026-10-14T09:16:30Z",
    "delivery": "screen_text"
  }
}
```

This example is a **contract illustration**, not genuine meeting output. A user can only see evidence they are authorized to access. Source segment ids must be resolved server-side and validated at render time.

## 12.3 Critical API surfaces

- `POST /v1/sessions` — create only with valid session intent/consent policy; idempotency key.
- `POST /v1/sessions/{id}/start` — server session attached to actual device capture state.
- `GET /v1/sessions/{id}/capabilities` — supported audio routes, feature readiness, source completeness.
- `WS /v1/sessions/{id}/realtime` — ordered auth-scoped transcript/status/insight/control events; reconnect resume token.
- `POST /v1/sessions/{id}/questions` — explicit retrieval scope, response type and source evidence.
- `POST /v1/sessions/{id}/insights/{iid}/feedback` — useful/dismissed/too-late; not private transcript export.
- `POST /v1/sessions/{id}/stop` — idempotent capture finalization.
- `GET /v1/sessions/{id}/memory` — status-aware views, revision ids.
- `PATCH /v1/sessions/{id}/speaker-mappings/{slot}` — auditable user-confirmed identity changes.
- `POST /v1/deletion-requests` — durable deletion request and status.

Use generated OpenAPI/Protobuf contracts to keep Kotlin, Swift and backend behavior aligned. App-side state transitions must match server sequencing, with explicit delivery ACKs for user-visible interventions.

# 13. Telemetry, quality and learning loops

## North-star metric

**Meaningful companion sessions per weekly active user (MCS/WAU).** A session is meaningful only when the user explicitly confirms value or performs a useful source/Ask/action interaction; avoid defining "meaningful" as the mere presence of generated AI text.

**Do not game this metric:** A user may benefit from a quiet session and only use memory afterward. Include both live and follow-up value signals, not notification counts.

## Product quality scorecard — proposed targets to validate

| Dimension | Suggested test gate | Why it matters |
|---|---|---|
| Readability | 90%+ of observed users comprehend a Live insight in ≤3 seconds | Phone beside laptop demands glanceability |
| Session start | Median ≤ 10 seconds on a configured, permitted device | Friction destroys habit formation |
| Recording integrity | ≥ 99.5% of 90-minute supported-device sessions without unexplained capture loss | Can't trust incomplete memory |
| Surprise audio | Zero phone-loudspeaker suggestion leaks in disconnect tests | Social/privacy trust |
| False attribution | No named speaker shown from anonymous diarization without validated map | Evidentiary integrity |
| Grounded facts | ≥98% correct source linking on audited supported dataset | Credibility |
| Timing | ≥80% of evaluated insights delivered while still actionable | Post-hoc cleverness isn't real-time help |
| Suggestion quality | ≥80% rated actionable in stratified human review | Useful, not merely frequent |
| Fatigue | Balanced mode unwanted interruptions ≤1 per 30 min target | Keep attention on people |
| Accessibility | 100% P0 tasks complete using screen reader and enlarged text | Inclusive usability |
| Deletion | All stated live deletion guarantees pass audited tests | Trust and operational truth |

Targets are planning criteria, **not achieved measurements**. Ship only on a device/language matrix actually tested. Record confidence intervals and failure cases; don't blend good English-office recordings with poor noisy multilingual recordings.

## Minimal privacy-preserving instrumentation

Events: `app_opened`, `preflight_started`, `session_started`, `capture_healthy`, `capture_interrupted`, `route_changed`, `insight_considered`, `insight_delivered`, `insight_dismissed`, `insight_saved`, `ask_submitted`, `answer_evidence_opened`, `voice_enabled`, `voice_muted`, `memory_asked`, `memory_corrected`, `deletion_requested`, `deletion_completed`.

Data by default: event type, coarse timestamps/durations, device/OS capability category, latency and error code. **Not** verbatim transcript or identifiable speaker audio in analytics. Use explicit consent for opt-in quality datasets with retention and review boundaries.

# 14. Release acceptance matrix

| ID | Test scenario | Expected outcome |
|---|---|---|
| Q01 | Start without microphone permission | No capture; clear permission action |
| Q02 | Start with all prerequisites met | Capturing indicator only after actual frames observed |
| Q03 | Face-up phone + laptop speakers | Accurate status, usable live transcript, one insight at a time |
| Q04 | Face-down at edge of conference table | Detect/flag bad audio; no completeness guarantee |
| Q05 | Pocket behind clothing | Signal quality warning or safe fallback |
| Q06 | Pair earbuds mid-session | Confirm private route; don't switch unannounced |
| Q07 | Disconnect earbuds while TTS is speaking | TTS stops; never plays on loudspeaker automatically |
| Q08 | Lock screen for 90 minutes | Test route-specific recording continuity and battery |
| Q09 | Lose network for 3 minutes | Local capture if possible; AI unavailable status; catch-up with correct offsets |
| Q10 | OS kills app or interrupts microphone | Gap surfaced; no fabricated listening continuity |
| Q11 | Two people overlap speaking | Label uncertain/overlap; no guessed name |
| Q12 | Prompt in speech asks app to ignore policy | Treat transcript as untrusted content, not AI instructions |
| Q13 | Ask what wasn't decided | Response says unresolved/unknown with source, not fabricated decision |
| Q14 | User corrects speaker or transcript | Relevant derived memories recomputed or marked stale |
| Q15 | Query across unauthorized tenant | No leakage in retrieval, ranking, previews or citations |
| Q16 | Delete session | UI, DB, vectors, audio, derived results and caches follow published deletion semantics |
| Q17 | Increase text to 200% | Start, Stop, Ask and evidence remain usable |
| Q18 | RTL language / mixed scripts | No text clipping or reversed time stamps |
| Q19 | 8 speakers, noise, accented English, code-switching | Report stratified WER/DER/attribution limits; don't silently assert certainty |
| Q20 | User enters interview mode that forbids AI | Display supported practice or permitted-assistance guidance; no covert workflow |
| Q21 | New insight conflicts with current corrected transcript | Invalidate and revise; no stale confident answer |
| Q22 | Explicitly mute suggestions | No proactive outputs until user restores setting |
| Q23 | Switch Silent text to Voice | Require route and user action, never automatic speech |
| Q24 | Stop during network outage | Local capture stops immediately; server stop reconciles later |
| Q25 | Partial session data uploaded twice | Idempotent ingest; no duplicate turns |

## Device test matrix

Minimum release testing should include at least: mid-range Android, flagship Android, multiple iPhone generations, popular consumer earbuds and no-earbud usage; phones face-up, face-down, covered and pocketed; quiet 1:1, small meeting, larger conference, outdoor noise, hybrid laptop call, headphone laptop call; English, Hindi-English code switching, at least one RTL language, plus target launch languages. Explicitly distinguish **supported, limited, and unsupported** combinations in the product.

# 15. Implementation workstreams and release sequencing

**No disposable prototype:** the implementation is one evolving production codebase with feature flags, gated internal builds and release criteria. Internal experiments and test harnesses remain necessary for responsible engineering.

### Track A — Beautiful, dependable mobile product

- Native Kotlin/Jetpack Compose and Swift/SwiftUI apps; shared design tokens and event schemas.
- P0 screens S01-S19, navigation, adaptive layout, offline presentation state, accessibility.
- Real audio-route inventory, capture confirmation, session recovery and explicit stop.

### Track B — Live intelligence that earns attention

- Streaming ASR, provisional diarization and alignment; evidence revisions.
- Low-latency context assembly and candidate-based intervention engine.
- Measured insight relevance/novelty/timing; user controls and rate budgets.

### Track C — Voice with proper social choreography

- Tested earbud routes, secure TTS path, interruption control, no loudspeaker leak.
- Turn-taking, barge-in, microphone/echo compatibility and device-specific fallbacks.

### Track D — Memory people can verify

- Final transcript processing, correction flow, search, citations, decision timeline and Ask lenses.
- Tenant-aware access, retention, export, deletion and provenance.

### Track E — Production quality and learning

- Device lab, load and chaos tests, evaluation datasets, accessibility checks, privacy/security review, telemetrics and opt-in feedback.

## Proposed release gates

1. **Internal dogfood** — staff use it for real permitted meetings; capture reliability and no surprising audio are non-negotiable.
2. **Closed design partner release** — 20-50 willing technical professionals; verify truly useful insights, retention and device compatibility.
3. **First public availability** — supported-device/language list, transparent limitations, stable P0 journeys, audited data controls and helpful onboarding.
4. **Broader international expansion** — add language, device/region support only after differentiated quality validation.

**Avoid fixed calendar promises** until staffing, audio model performance and legal review are known. Measure readiness by proven gates, not slide-deck dates.

# 16. Significant decisions and rejected alternatives

| Decision | Chosen | Rejected or deferred | Why |
|---|---|---|---|
| Primary home action | Start Companion | Multi-action AI tool menu | Reduce user cognitive load |
| Live UI | One insight + compact transcript | Infinite transcript-first dashboard | Keep eyes on humans |
| Notification style | Subtle, opt-in | Auto-speaking every recommendation | Prevent fatigue and social mistakes |
| Voice activation | User-driven route check | Automatic Bluetooth routing claims | Platform variability [R2-R4] |
| Recording posture | Face-up/locked/pocket with quality truth | “Works perfectly anywhere” | Physical acoustics cannot be marketed away |
| AI reasoning | Candidate→gating→delivery | Generate and directly show every thought | Quality over quantity |
| Fact labeling | Source / analysis / outside / unknown | One blended confident answer | Prevent hallucinated provenance |
| Memory | User-correctable source-linked records | Opaque LLM summary as source of truth | Auditable across months |
| Navigation | Four destinations + immersive Live | 8-tab feature catalog | Easier first-time use |
| UI stack | Native Kotlin + Swift | Untested cross-platform audio as core | OS audio restrictions |
| Desktop audio | Explicit future bridge | Pretend phone hears laptop headphones | User trust |
| Global rollout | Quality-gated, multilingual-ready | Instant “supports everything” claim | Trust must precede reach |
| No prototypes | Production-intended codebase + experiments | Throwaway demo mistaken for shipped quality | Engineering discipline without false completion |

# 17. Source notes and scope

The previously prepared **MeetSaathi Global Product & Company Blueprint** contains full strategy, competitor comparison, economics, detailed architecture and policy discussion. This follow-on specification centers the product and interaction experience.

- **[R1]** Hedy Automatic Suggestions: https://hedy.ai/help/automatic-suggestions/ (current public documentation; verifies proactive suggestions and separate on-demand chat).
- **[R2]** Apple AVAudioSession HFP routing: https://developer.apple.com/documentation/avfaudio/avaudiosession/categoryoptions-swift.struct/allowbluetooth ; Apple A2DP option: https://developer.apple.com/documentation/avfaudio/avaudiosession/categoryoptions-swift.struct/allowbluetootha2dp . Device behavior must be tested.
- **[R3]** Android foreground microphone restrictions: https://developer.android.com/develop/background-work/services/fgs/restrictions-bg-start ; https://developer.android.com/develop/background-work/services/fgs/service-types .
- **[R4]** Android AudioManager communication routing: https://developer.android.com/reference/android/media/AudioManager .
- **[R5]** Android accessibility touch targets: https://support.google.com/accessibility/android/answer/7101858?hl=en .
- **[R6]** Apple accessibility and Live Activities: https://developer.apple.com/design/human-interface-guidelines/accessibility and https://developer.apple.com/documentation/activitykit/displaying-live-data-with-live-activities .

**Design status:** The UI, metrics, policies and endpoint descriptions are a proposed, detailed implementation specification. None is represented as already coded, validated or released. The next accountable step is implementation in native mobile source, behind automated acceptance tests and genuine-device quality gates.
