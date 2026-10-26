# MeetSaathi — Engineering and Design Handoff

**Status:** Design and implementation instructions. This package does not contain a working Android/iOS application, speech pipeline or deployed backend. Do not market visual designs or sample AI answers as functional software.

## Deliverable map

| File | Owner / purpose |
|---|---|
| `MeetSaathi_Product_Experience_Spec.pdf` | Founder + designer: complete intended journeys, visual and interaction standards, behavior rules, failure handling and why decisions were made |
| `MeetSaathi_Product_Experience_Spec.md` | Design/engineering source specification, searchable and editable |
| `MeetSaathi_Visual_Screenbook.pdf` | Seven mobile screen design references for reviews and visual consistency |
| `MeetSaathi_Visual_Screenbook.html` | Accessible static source for the visual reference, not a functioning application |
| `MeetSaathi_Design_Tokens.json` | Visual tokens to translate into Compose/SwiftUI theme values |
| `MeetSaathi_UI_Contracts.json` | Structured 24-screen inventory, session states, response types, critical invariants |
| `MeetSaathi_Release_Acceptance_Tests.csv` | Twenty-five end-to-end device/integration acceptance cases; all NOT_IMPLEMENTED until run |
| `MeetSaathi_Global_Product_Blueprint.md/pdf` | Previous higher-level strategy, architecture, competition, privacy, pricing research |

## Product owner decisions frozen for build planning

1. The flagship is **face-up phone beside laptop with silent live contextual suggestions**.
2. **Pocket with earbud audio** is an equal flagship, not an optional marketing claim, but support is route-validated and device-dependent.
3. **One prioritized insight**, not an infinite automatic message feed.
4. The AI can decide not to intervene. User-initiated Ask always takes precedence.
5. Any attributed statement requires evidence. External reasoning is visibly different from meeting memory.
6. Phone start/stop, transparent capture and data control always override personalization convenience.
7. Use native Android Kotlin + Jetpack Compose, iOS Swift + SwiftUI, common versioned contracts, modular realtime/backend and AI inference components; simplify backends when possible without compromising trust.
8. No disposable public demo. Maintain a single production-intended codebase with internal test harnesses and feature flags.

## Delivery order (quality gates, not guaranteed calendar dates)

### Gate A — Live session foundation

Implement native navigation, Home, session setup, consent/permission flow, tested phone-mic recording, lifecycle, local encrypted buffering, real route display, Stop, recovery status, basic session memory storage. Pass Q01-Q10 and Q24-Q25 on a published device set.

**User acceptance:** A permitted 90-minute conversation is captured with no unexplained gap, and a user can always tell whether recording is truly active.

### Gate B — Live screen and intelligence

Streaming ASR, diarization, stable provisional transcript, typed source evidence, Ask bottom sheet, candidate insight engine, policy gating, one-card delivery and feedback. Pass Q11-Q15, Q20-Q22.

**User acceptance:** A specific actionable observation arrives when useful, citations replay the correct segment, and the app does not invent decisions or real speaker names.

### Gate C — Earbud quality

Voice output and route compatibility checks; no-loudspeaker-leak rule; TTS summary length controls, pause and interruption logic. Pass Q06-Q08 and Q23 on multiple actual earbud/phone combinations.

**User acceptance:** A real meeting stays audible to the user; private suggestions are short, optional and never blast from the handset upon disconnect.

### Gate D — Memory, correction, accessibility, privacy

Finalization pipeline, speaker identity correction and version invalidation, permission-scoped history search, source-linked decision timeline, export/deletion with audit, localization/accessibility. Pass Q13-Q19.

**User acceptance:** A user can explain why MeetSaathi claims a decision occurred, correct an error and actually control the stored content.

### Gate E — Release-quality polish

Opt-in human evaluation, latency and battery profiles, accessibility and localization audits, App Store/Play policy review, crash/reconnect chaos tests, competitor-blind preference studies. Publish only supported device/language pairings that pass the gate.

## Suggested repository layout

```text
meetsaathi/
  product/               # copied product spec, decisions, acceptance records
  apps/
    android/             # Kotlin, Jetpack Compose, audio foreground service
    ios/                 # Swift, SwiftUI, audio session/recording coordinator
  packages/
    contracts/           # versioned OpenAPI/Protobuf, event schemas
    design-tokens/       # generated native token maps
  services/
    api/                 # auth, sessions, permissions, retrieval
    realtime/            # audio sequence ingestion, websocket events, resumption
    ai/                  # ASR/diarization adapters, evidence, candidates, policy
    worker/              # finalization, correction, deletion workflows
  infra/                 # config, secrets and repeatable deployment manifests
  tests/
    e2e-mobile/          # mapped to Q01..Q25
    contract/            # producer/consumer version tests
    speech-evals/        # permissioned datasets with known answers
    load-and-chaos/      # network loss, route changes, process terminations
  docs/
    privacy/             # data map, consent, deletion policy, legal review
    device-matrix/       # measured supported/limited/unsupported combinations
```

## Engineering rules when using AI coding agents

- Never silently substitute mocked audio, text, voice or AI answers for real implementations. If a provider or platform integration is missing, fail with a clear unavailable state and keep the rest of the app functional.
- Never hardcode user-visible claims of speaker identity without a verified source.
- Keep recording indicators and Stop visible, with actual device capture as the source of truth.
- Never fabricate evidence timestamps or replay a different segment.
- Store and test idempotent event sequences and revisions.
- Use explicit permission/data residency scope and backend authorization, not client filtering.
- Every Pull Request should identify affected screen IDs and Q acceptance IDs, plus logs/screenshots/device test evidence where appropriate.
- Avoid adding a feature unless it improves **intelligence, naturalness, trust or ease of use**.

## The first real product review

Conduct a review on a physical Android and iPhone with the same consented 30-minute technical discussion. Judge these, in order: (1) Did Start work without confusion? (2) Could the user forget the phone and focus on people? (3) Did the best insight arrive at the right moment? (4) Could the user follow it without reading a wall of text? (5) Did the audio remain safe when earbuds changed? (6) Was the recap verifiable? (7) Would they intentionally use it again tomorrow?

**Working North Star:** meaningful companion sessions per weekly active user, combined with source truth, voice safety and voluntary repeated use. No market-scale claims until supported by live usage evidence.
