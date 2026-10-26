MEETSAATHI / LEARNING COMPANION — PRODUCT EXPERIENCE HANDOFF
Version 1.0 · 14 October 2026

START HERE
1. MeetSaathi_Learning_Screenbook.pdf
   Five-page visual review of the actual designed mobile screens and interaction rationale.

2. MeetSaathi_Learning_Interactive_UX.html
   Offline, navigable interaction reference with seven principal screens. Open it in a normal browser.
   It includes sample actions for starting a simulated session, getting an explanation,
   saving a moment, opening a recap and answering a quiz.
   It DOES NOT open your microphone, record audio, run any AI service or call a backend.
   All student/course content is fictional and provided solely to illustrate the experience.

3. MeetSaathi_Learning_Companion_Product_Spec.pdf
   Sixteen-page complete product specification. Covers user journeys, 20 screen contracts,
   AI intervention rules, evidence and course memory, native audio operation, security,
   accessibility, API contract sketches and release gates, with rationale for major decisions.

4. MeetSaathi_Learning_Companion_Product_Spec.md
   Editable source, preferable for review and Codex-assisted engineering planning.

5. MeetSaathi_Learning_Release_QA.csv
   42 test cases spanning onboarding, permission, audio, Live Focus, learning, memory,
   quality, privacy, and academic integrity. Intended as release verification inputs.

6. MeetSaathi_Learning_UI_Contracts.json
   Machine-readable screen IDs, session states, response modes, and invariants.

7. MeetSaathi_Design_Tokens.json
   Reuses the existing MeetSaathi colors, spacing, accessibility and interface contracts.

RECOMMENDED IMPLEMENTATION APPROACH
Build Learning as one MeetSaathi context rather than an independent app.
The canonical product order is: native mobile shell and authorized session flow;
reliable audio and truthful state; contextual Explain; source-linked recap;
long-term course memory; retrieval practice; tested voice routing and multilingual coverage.

QUALITY AND SAFETY
Recording must comply with applicable laws and school/class policies. A non-recording
path is a product requirement, not a loophole. Voice advice cannot unexpectedly use
speaker output. Generated explanations must never be misrepresented as lecturer words.
Measurements/SLOs in the product specification are acceptance targets, not achieved metrics.

Neither the HTML nor the PDFs constitute an installed or released MeetSaathi application.
