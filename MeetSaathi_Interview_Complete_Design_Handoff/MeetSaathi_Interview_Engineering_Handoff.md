# MeetSaathi Interview Companion — Engineering Handoff

## Deliverable status
Production-intended specification plus offline interactive simulation. No native app, audio capture, live AI calls, TTS, or backend integration is implemented in this handoff.

## Build order
1. Reuse universal MeetSaathi design tokens, identity, navigation, accessibility patterns, and memory provenance.
2. Implement InterviewGoal/Practice session state with user-controlled role-specific prompt packs and text-only mock.
3. Add reliable mobile microphone, audio interruption handling, user-initiated recording indicators, and OS permissions.
4. Connect streaming ASR plus context-aware mock interview state, then post-answer evaluation and correction flows.
5. Add sourced interview question/answer timeline, feedback model, semantic scoped memory and retention/deletion.
6. Implement **separate** AI assistance and recording eligibility enforcement at UI and API layers.
7. Add permitted-live glanceable on-screen contextual guidance, then private earbud output only after route-lab tests.
8. Gate releases on mobile compatibility, security review, accuracy evaluation and real user practice outcomes.

## Contracts and guardrails
All APIs and state transitions are in `MeetSaathi_Interview_Companion_Product_Spec.md`. Never allow LIVE mode API actions for restricted authorization states; a client-only switch is insufficient. Differentiate `Mute AI`, `Pause capture` and `End`. All measured accuracy claims require a dated test corpus.

## Acceptance
Use `MeetSaathi_Interview_Release_QA.csv` as a checklist. P0 means release blocker; P1 means required for target feature's release. CSV statuses are `Not run`, not passed.
