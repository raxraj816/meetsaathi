# MeetSaathi — Unified Master Product & Engineering v1.0

**Authoritative scope:** One mobile application with Meeting, Learning, Interview and Conversation contextual experiences, a shared live intelligence engine, optional private-earbud voice and permission-controlled memory.

## Start here
1. Read `MeetSaathi_Master_Product_Engineering_Spec_v1.pdf` for UX and architecture decisions and the conflict-resolution ledger.
2. Read the editable `.md` alongside it for code generation and change tracking.
3. View `design/Unified_Experience_Preview.html` for a **fictional local-only interactive design**, not a microphone/AI-enabled app.
4. Review `contracts/openapi_v1.yaml`, `contracts/realtime_events_v1.json` and `contracts/schema_v1.sql`; these are **reviewable draft contracts**, not a running production system.
5. Run `qa/Unified_Release_QA.csv` on actual devices and infrastructure. All rows begin unexecuted, and historical companion QA cases are normalized and retained.
6. Use `qa/Implementation_Backlog.csv` and `contracts/ARCHITECTURE_DECISIONS.md` to begin engineering.

## File authority
Master v1 overrides conflicting behaviors in the individual companion documents. Earlier individual designs remain reference material only, not separate products or definitive API contracts.

## Known implementation prerequisites
- Validate supported device/OS/earbud matrix and recorded consent paths.
- Define legal and app-review policies per initial market.
- Implement real audio, streaming speech and AI services; the preview has **no access** to microphone or user content.
- Run threat models and review example row-level security policies; SQL sample intentionally **denies most access until explicit audited policies are added**.
- Ensure native clients fail closed when the private voice route changes.
- Confirm model costs and end-to-end latency using representative workloads.

**Do not label the product production-ready merely because specs, mocks or backend schemas exist.**
