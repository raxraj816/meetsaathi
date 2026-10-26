# MeetSaathi Meeting Companion — Design / Engineering Handoff

**Status: design deliverables only. No microphone capture, real AI backend, production app, or app-store release has been built.**

## Contents

- `MeetSaathi_Meeting_Interactive_UX.html`: self-contained interactive UX reference; fictional data and optional user-initiated sample text-to-speech.
- `MeetSaathi_Meeting_Companion_Product_Spec.pdf` and `.md`: full rationale, user journeys, native architecture, AI delivery policies, memory, privacy, failure modes and phased release gates.
- `MeetSaathi_Meeting_Visual_Screenbook.pdf`: screenshots of the actual HTML experience and screen-specific commentary.
- `MeetSaathi_Meeting_Release_QA.csv`: 61 release and regression scenarios, all NOT_RUN.
- `MeetSaathi_Meeting_UI_Contracts.json`: 24 app screen contracts, event taxonomy and states.
- `MeetSaathi_Meeting_Design_Tokens.json`: product design tokens for native apps.

## Opening the interactive design

Open the HTML locally in a modern browser. It contains no external dependencies or tracking. If local file URL opening is blocked by the platform, save/download the file and open it from your computer. It is a UI simulator only.

## Real production implementation

1. Native audio session foundation (Android Kotlin + Compose; iOS Swift + SwiftUI).
2. Ingest and streaming ASR+speaker diarization+source-alignment service.
3. Grounded Ask and proactive intervention policy.
4. Earbud route validation, private voice delivery and offline resilience.
5. Scoped, versioned, correctable memory and participant consent controls.
6. Device, speech, security, accessibility and reliability verification.

## Quality and ethics

Recording requires applicable authorization and participant awareness/consent; private guidance must not be used in restricted interviews. Any illustrated answer, speaker or meeting reference is fictional.
