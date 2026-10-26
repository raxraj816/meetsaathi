# ADR-016 — Implementation extensions to the v1 draft contracts

Status: Accepted (implementation of master v1) · 2026-10-18
Context: `contracts/openapi_v1.yaml`, `schema_v1.sql` and `realtime_events_v1.json` are explicitly *draft* contracts. Implementing the
master spec end to end required additive extensions. None changes an existing field's meaning. Master v1 remains authoritative.

| Area | Extension | Why (master reference) |
|---|---|---|
| `session_state` | `NOTES_ONLY` | 7.1 "PREFLIGHT --denied/unsupported--> NOTES_ONLY"; J1 step 4 |
| `provenance_kind` | `AI_SIMULATION` | 6.2 "preserving mock vs real vs recalled origin" |
| `tenants.org_policy` | `disable_capture`, `disable_live_ai` | 9.2 organisational rules; INT-029 |
| `sessions` | assistance/intensity/output, preset, interview_mode, pause/final watermarks, drain deadline, ASR cursor, transcript/finalization status, recap, mute, retention timestamps, review state | 2.3 independent runtime controls; 7.1–7.2; U09–U10 |
| `session_runtime` | event sequence, ACK watermark, route + private-route verification, user-speaking signal, TTS playback windows | 5.2 temporal gate; 5.4 audio choreography; 10 |
| `session_events` | durable ordered event log per session | 10 "client ACKs reconnect cursor" |
| `capture_gaps` | explicit missing intervals (pause, interruption, upload missing) | 7.1 "UI must communicate missing intervals" |
| `utterance_revisions` | speaker label snapshot, mapping revision, overlap, confidence, correction flag, chunk range, revision reason, FTS vector | 6.1, 6.4 |
| `claims` | owner/due (only if spoken), time range, client_id (offline idempotency), exclude-from-suggestions, version | 6.2; LC-011; C 8.2 |
| `decision_events` | decision lineage with cited source or user attestation | 6.2 |
| `embeddings` | generalised from `memory_embeddings` to claims + utterances, model-tagged | 6.3 |
| `ask_turns` | stored answers + citations so later corrections mark "Corrected since answer" | J11 |
| Context-pack tables | `projects` (courses, interview goals), `interview_mocks`, `mock_turns`, `practice_items`, `practice_attempts`, `review_schedule`, `shares`, `exports` | 2.2, 12.2 Gate 5 |
| Ops tables | `idempotency_keys`, `usage_meters`, `audit_events`, `ingest_tokens`, `devices`, `refresh_tokens`, `user_credentials` | 10, 8.4, UNI-023 |
| RLS | full read/write policies for every scoped table, `ms_worker` role-targeted policies, `session_live()` so tombstoned sessions vanish from all derived tables, controlled `app.tombstoning` visibility for revocation updates | schema_v1 note "production migration must add explicit policies" |
| Events | `session.status`, `insight.expired`, `ask.answered`, `speaker.corrected`; `transcript.partial` carries `utterance_id`+`revision` | 3.3 truthful copy; 3.4 one card |
| REST | consent withdraw, capture-state (device-observed), controls, route, voice route-lost, playback-window, context switch, notes, explain, recap, review, shares, exports, deletion status, learning/interview pack endpoints | 10.1 is an "initial" surface |

Rejected alternative: changing the draft contract's existing shapes. Reverse if: the contract owner freezes a different v1 shape — the
implementation then adapts behind the same behaviour.
