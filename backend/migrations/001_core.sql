-- MeetSaathi migration 001: core schema.
-- Derived from contracts/schema_v1.sql (master v1). Extensions over the draft contract are
-- marked "EXT" and recorded in docs/adr/ADR-016-schema-extensions.md.
-- Runtime roles (ms_app, ms_worker) are created by the migration runner before this file runs.
-- Neither runtime role owns tables or has BYPASSRLS.

CREATE EXTENSION IF NOT EXISTS pgcrypto;
CREATE EXTENSION IF NOT EXISTS vector;

CREATE TYPE session_state AS ENUM (
  'PREFLIGHT','STARTING','RECORDING','PAUSED','INTERRUPTED','STOPPING','FINALIZING',
  'FINALIZATION_RETRYABLE','COMPLETED','COMPLETED_PARTIAL','ERROR','DELETING','DELETED',
  'NOTES_ONLY' -- EXT: master 7.1 "PREFLIGHT --denied/unsupported--> NOTES_ONLY"
);
CREATE TYPE context_kind AS ENUM ('MEETING','LEARNING','INTERVIEW','CONVERSATION');
CREATE TYPE provenance_kind AS ENUM ('RECORDED','IMPORTED','USER_NOTE','USER_RECOLLECTION','AI_ANALYSIS',
  'AI_SIMULATION' -- EXT: interview mock content (master 6.2 "mock vs real vs recalled origin")
);
CREATE TYPE memory_status AS ENUM ('PENDING_REVIEW','APPROVED','INVALIDATED','DELETED');
CREATE TYPE decision_state AS ENUM ('PROPOSED','DISCUSSED','ACCEPTED','REJECTED','DEFERRED','SUPERSEDED','UNRESOLVED');

-- ---------------------------------------------------------------- identity / tenancy
CREATE TABLE tenants (
  tenant_id uuid PRIMARY KEY DEFAULT gen_random_uuid(), name text NOT NULL,
  residency_region text NOT NULL, plan text NOT NULL DEFAULT 'FREE',
  org_policy jsonb NOT NULL DEFAULT '{}'::jsonb, -- EXT: organization capture / live-AI rules (INT-029, 9.2)
  created_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE users (
  user_id uuid PRIMARY KEY, display_name text,
  created_at timestamptz NOT NULL DEFAULT now(), deleted_at timestamptz
);
-- EXT: credentials, devices and tokens (master 8.4 device-bound session tokens, per-device revocation)
CREATE TABLE user_credentials (
  user_id uuid PRIMARY KEY REFERENCES users(user_id) ON DELETE CASCADE,
  email text NOT NULL UNIQUE, password_hash text NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE devices (
  device_id uuid PRIMARY KEY DEFAULT gen_random_uuid(), user_id uuid NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
  platform text NOT NULL CHECK (platform IN ('IOS','ANDROID','DESKTOP_BRIDGE','TEST')),
  name text NOT NULL, created_at timestamptz NOT NULL DEFAULT now(),
  last_seen_at timestamptz, revoked_at timestamptz
);
CREATE TABLE refresh_tokens (
  token_hash text PRIMARY KEY, user_id uuid NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
  device_id uuid NOT NULL REFERENCES devices(device_id) ON DELETE CASCADE,
  expires_at timestamptz NOT NULL, revoked_at timestamptz, replaced_by text,
  created_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE tenant_memberships (
  tenant_id uuid NOT NULL REFERENCES tenants(tenant_id), user_id uuid NOT NULL REFERENCES users(user_id),
  role text NOT NULL CHECK (role IN ('OWNER','ADMIN','EDITOR','VIEWER')),
  PRIMARY KEY (tenant_id,user_id)
);
CREATE TABLE user_preferences (
  user_id uuid PRIMARY KEY REFERENCES users(user_id) ON DELETE CASCADE,
  prefs jsonb NOT NULL DEFAULT '{}'::jsonb, version bigint NOT NULL DEFAULT 1,
  updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE spaces (
  space_id uuid PRIMARY KEY DEFAULT gen_random_uuid(), tenant_id uuid NOT NULL REFERENCES tenants(tenant_id),
  name text NOT NULL, kind text NOT NULL CHECK(kind IN ('PERSONAL','WORK','LEARNING','CUSTOM')),
  created_by uuid NOT NULL REFERENCES users(user_id), created_at timestamptz NOT NULL DEFAULT now(),
  deleted_at timestamptz,
  UNIQUE (tenant_id,space_id)
);
CREATE TABLE space_memberships (
  tenant_id uuid NOT NULL, space_id uuid NOT NULL, user_id uuid NOT NULL REFERENCES users(user_id),
  role text NOT NULL CHECK(role IN ('OWNER','EDITOR','VIEWER')),
  PRIMARY KEY(space_id,user_id), FOREIGN KEY (tenant_id,space_id) REFERENCES spaces(tenant_id,space_id)
);
-- EXT: projects (master 2.3 "Selected project" retrieval scope; Learning courses; Interview goals)
CREATE TABLE projects (
  project_id uuid PRIMARY KEY DEFAULT gen_random_uuid(), tenant_id uuid NOT NULL, space_id uuid NOT NULL,
  kind text NOT NULL CHECK (kind IN ('PROJECT','COURSE','INTERVIEW_GOAL')),
  title text NOT NULL, metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_by uuid NOT NULL REFERENCES users(user_id), created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(), version bigint NOT NULL DEFAULT 1, deleted_at timestamptz,
  FOREIGN KEY(tenant_id,space_id) REFERENCES spaces(tenant_id,space_id),
  UNIQUE(tenant_id,space_id,project_id)
);

-- ---------------------------------------------------------------- sessions
CREATE TABLE sessions (
  session_id uuid PRIMARY KEY DEFAULT gen_random_uuid(), tenant_id uuid NOT NULL, space_id uuid NOT NULL,
  created_by uuid NOT NULL REFERENCES users(user_id), title text NOT NULL DEFAULT 'Conversation',
  context context_kind NOT NULL, state session_state NOT NULL DEFAULT 'PREFLIGHT',
  capture_source text NOT NULL CHECK(capture_source IN ('PHONE_MIC','DESKTOP_BRIDGE','IMPORTED','NONE')),
  ai_assistance_permitted boolean NOT NULL DEFAULT false,
  capture_permitted boolean NOT NULL DEFAULT false,
  processing_region text NOT NULL, retention_policy_id text,
  started_at timestamptz, capture_stopped_at timestamptz, ended_at timestamptz,
  source_watermark_ms bigint NOT NULL DEFAULT 0 CHECK(source_watermark_ms>=0),
  version bigint NOT NULL DEFAULT 0 CHECK(version>=0), deleted_at timestamptz,
  created_at timestamptz NOT NULL DEFAULT now(),
  -- EXT columns
  project_id uuid REFERENCES projects(project_id),
  preset text,
  interview_mode text CHECK (interview_mode IS NULL OR interview_mode IN ('LIVE','REFLECTION')),
  assistance_mode text NOT NULL DEFAULT 'LISTENER' CHECK (assistance_mode IN ('LISTENER','ASK','COMPANION')),
  proactive_intensity text NOT NULL DEFAULT 'QUIET' CHECK (proactive_intensity IN ('QUIET','BALANCED','ACTIVE')),
  output_mode text NOT NULL DEFAULT 'TEXT' CHECK (output_mode IN ('TEXT','PRIVATE_VOICE','BOTH')),
  sensitive boolean NOT NULL DEFAULT false,
  language text NOT NULL DEFAULT 'en',
  consent_receipt_id uuid, capabilities_hash text,
  pause_watermark_sequence bigint, final_sequence bigint,
  asr_cursor_sequence bigint NOT NULL DEFAULT -1,
  transcript_status text NOT NULL DEFAULT 'NONE' CHECK (transcript_status IN ('NONE','LIVE','UNAVAILABLE','DELAYED','FINAL','PARTIAL')),
  finalization_status text NOT NULL DEFAULT 'NOT_STARTED',
  finalization_attempts int NOT NULL DEFAULT 0,
  finalization_error text,
  recap jsonb,
  mute_until timestamptz,
  audio_retention_until timestamptz, audio_deleted_at timestamptz,
  drain_deadline timestamptz,
  review_state text NOT NULL DEFAULT 'PENDING' CHECK (review_state IN ('PENDING','KEPT','DISCARDED')),
  FOREIGN KEY(tenant_id,space_id) REFERENCES spaces(tenant_id,space_id),
  UNIQUE(tenant_id,space_id,session_id)
);
-- EXT: hot runtime state kept apart from the durable session row.
CREATE TABLE session_runtime (
  session_id uuid PRIMARY KEY REFERENCES sessions(session_id) ON DELETE CASCADE,
  tenant_id uuid NOT NULL, space_id uuid NOT NULL,
  event_seq bigint NOT NULL DEFAULT 0,
  user_speaking boolean NOT NULL DEFAULT false, user_speaking_at timestamptz,
  input_route text, output_route text, route_device_name text,
  private_route_verified boolean NOT NULL DEFAULT false, route_updated_at timestamptz,
  audio_quality text, cooldown_multiplier real NOT NULL DEFAULT 1.0,
  last_client_ack_seq bigint NOT NULL DEFAULT 0,
  received_through_sequence bigint NOT NULL DEFAULT -1, max_sequence bigint NOT NULL DEFAULT -1,
  tts_windows jsonb NOT NULL DEFAULT '[]'::jsonb, speakers_need_review boolean NOT NULL DEFAULT false,
  FOREIGN KEY(tenant_id,space_id,session_id) REFERENCES sessions(tenant_id,space_id,session_id)
);
CREATE TABLE session_state_log (
  log_id bigserial PRIMARY KEY, tenant_id uuid NOT NULL, space_id uuid NOT NULL, session_id uuid NOT NULL,
  previous session_state, current session_state NOT NULL, reason text NOT NULL, actor text NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  FOREIGN KEY(tenant_id,space_id,session_id) REFERENCES sessions(tenant_id,space_id,session_id)
);
CREATE TABLE session_events (
  tenant_id uuid NOT NULL, space_id uuid NOT NULL, session_id uuid NOT NULL,
  sequence bigint NOT NULL, event_id uuid NOT NULL DEFAULT gen_random_uuid(),
  type text NOT NULL, payload jsonb NOT NULL, created_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY(session_id, sequence),
  FOREIGN KEY(tenant_id,space_id,session_id) REFERENCES sessions(tenant_id,space_id,session_id)
);
CREATE TABLE consent_receipts (
  receipt_id uuid PRIMARY KEY DEFAULT gen_random_uuid(), tenant_id uuid NOT NULL, space_id uuid NOT NULL,
  session_id uuid NOT NULL, attested_by uuid NOT NULL REFERENCES users(user_id),
  capture_basis text NOT NULL, notices_attested boolean NOT NULL,
  ai_assistance_permitted boolean NOT NULL DEFAULT false,
  processing_disclosure_version text NOT NULL, scope_json jsonb NOT NULL DEFAULT '{}'::jsonb,
  recorded_at timestamptz NOT NULL DEFAULT now(),
  capture_permitted boolean NOT NULL DEFAULT false, -- EXT: derived, policy-evaluated
  withdrawn_at timestamptz, withdrawal_reason text, -- EXT: CON-013 / MTG-043
  FOREIGN KEY(tenant_id,space_id,session_id) REFERENCES sessions(tenant_id,space_id,session_id)
);
CREATE TABLE ingest_tokens (
  jti uuid PRIMARY KEY, tenant_id uuid NOT NULL, space_id uuid NOT NULL, session_id uuid NOT NULL,
  user_id uuid NOT NULL, device_id uuid NOT NULL REFERENCES devices(device_id),
  expires_at timestamptz NOT NULL, revoked_at timestamptz, drain_only boolean NOT NULL DEFAULT false,
  created_at timestamptz NOT NULL DEFAULT now(),
  FOREIGN KEY(tenant_id,space_id,session_id) REFERENCES sessions(tenant_id,space_id,session_id)
);
CREATE TABLE audio_chunks (
  tenant_id uuid NOT NULL, space_id uuid NOT NULL, session_id uuid NOT NULL,
  sequence_no bigint NOT NULL CHECK(sequence_no>=0),
  sample_rate_hz integer NOT NULL CHECK(sample_rate_hz>0), capture_start_ms bigint NOT NULL CHECK(capture_start_ms>=0),
  duration_ms integer NOT NULL CHECK(duration_ms>0), sha256_hex char(64) NOT NULL,
  encrypted_object_key text NOT NULL, ingest_status text NOT NULL CHECK(ingest_status IN ('ACKED','QUARANTINED','PURGED')),
  created_at timestamptz NOT NULL DEFAULT now(),
  device_id uuid, byte_length integer, -- EXT
  PRIMARY KEY(session_id, sequence_no),
  FOREIGN KEY(tenant_id,space_id,session_id) REFERENCES sessions(tenant_id,space_id,session_id)
);
CREATE TABLE capture_gaps (
  gap_id uuid PRIMARY KEY DEFAULT gen_random_uuid(), tenant_id uuid NOT NULL, space_id uuid NOT NULL, session_id uuid NOT NULL,
  start_ms bigint NOT NULL, end_ms bigint, reason text NOT NULL, created_at timestamptz NOT NULL DEFAULT now(),
  FOREIGN KEY(tenant_id,space_id,session_id) REFERENCES sessions(tenant_id,space_id,session_id)
);
CREATE TABLE session_speakers (
  speaker_alias_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id uuid NOT NULL, space_id uuid NOT NULL, session_id uuid NOT NULL,
  alias text NOT NULL, user_verified_label text, mapping_revision integer NOT NULL DEFAULT 1,
  provider_speaker_id text, -- EXT: diarizer's anonymous id; never an identity

  confidence real CHECK(confidence IS NULL OR (confidence>=0 AND confidence<=1)),
  UNIQUE(session_id,alias),
  FOREIGN KEY(tenant_id,space_id,session_id) REFERENCES sessions(tenant_id,space_id,session_id)
);
CREATE TABLE speaker_mapping_history (
  speaker_alias_id uuid NOT NULL REFERENCES session_speakers(speaker_alias_id) ON DELETE CASCADE,
  mapping_revision integer NOT NULL, tenant_id uuid NOT NULL, space_id uuid NOT NULL, session_id uuid NOT NULL,
  verified_label text, changed_by uuid NOT NULL, created_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (speaker_alias_id, mapping_revision)
);
CREATE TABLE utterances (
  utterance_id uuid PRIMARY KEY DEFAULT gen_random_uuid(), tenant_id uuid NOT NULL, space_id uuid NOT NULL,
  session_id uuid NOT NULL, current_revision integer NOT NULL DEFAULT 1,
  created_at timestamptz NOT NULL DEFAULT now(),
  FOREIGN KEY(tenant_id,space_id,session_id) REFERENCES sessions(tenant_id,space_id,session_id)
);
CREATE TABLE utterance_revisions (
  utterance_id uuid NOT NULL REFERENCES utterances(utterance_id) ON DELETE CASCADE, revision integer NOT NULL CHECK(revision>0),
  tenant_id uuid NOT NULL, space_id uuid NOT NULL, session_id uuid NOT NULL,
  start_ms bigint NOT NULL CHECK(start_ms>=0), end_ms bigint NOT NULL CHECK(end_ms>start_ms),
  speaker_alias_id uuid REFERENCES session_speakers(speaker_alias_id),
  transcript text NOT NULL, is_final boolean NOT NULL DEFAULT false,
  provenance provenance_kind NOT NULL DEFAULT 'RECORDED', asr_model_version text,
  diarizer_model_version text, speaker_confidence real CHECK(speaker_confidence IS NULL OR (speaker_confidence>=0 AND speaker_confidence<=1)),
  created_at timestamptz NOT NULL DEFAULT now(),
  -- EXT
  speaker_label_snapshot text, speaker_mapping_revision integer, overlap boolean NOT NULL DEFAULT false,
  asr_confidence real, language text, corrected_by_user boolean NOT NULL DEFAULT false,
  source_chunk_from bigint, source_chunk_to bigint, revision_reason text NOT NULL DEFAULT 'LIVE_ASR',
  search tsvector GENERATED ALWAYS AS (to_tsvector('simple', transcript)) STORED,
  PRIMARY KEY(utterance_id,revision),
  FOREIGN KEY(tenant_id,space_id,session_id) REFERENCES sessions(tenant_id,space_id,session_id)
);

-- ---------------------------------------------------------------- claims / memory
CREATE TABLE claims (
  claim_id uuid PRIMARY KEY DEFAULT gen_random_uuid(), tenant_id uuid NOT NULL, space_id uuid NOT NULL,
  session_id uuid REFERENCES sessions(session_id), claim_kind text NOT NULL,
  text_value text NOT NULL, provenance provenance_kind NOT NULL,
  decision_status decision_state,
  memory_state memory_status NOT NULL DEFAULT 'PENDING_REVIEW',
  sensitivity text NOT NULL DEFAULT 'NORMAL', model_version text, policy_version text,
  created_at timestamptz NOT NULL DEFAULT now(), invalidated_at timestamptz,
  -- EXT
  project_id uuid REFERENCES projects(project_id),
  long_text text, owner_label text, owner_confirmed boolean NOT NULL DEFAULT false, due_text text,
  time_start_ms bigint, time_end_ms bigint, client_id text, metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_by uuid REFERENCES users(user_id), updated_at timestamptz NOT NULL DEFAULT now(),
  invalidation_reason text, version bigint NOT NULL DEFAULT 1, exclude_from_suggestions boolean NOT NULL DEFAULT false,
  search tsvector GENERATED ALWAYS AS (to_tsvector('simple', text_value || ' ' || coalesce(long_text,''))) STORED,
  CHECK (claim_kind IN ('DECISION','ACTION','QUESTION','RISK','LESSON','CONCEPT','FACT','QUOTE','SUGGESTION',
                        'BOOKMARK','NOTE','RECOLLECTION','SUMMARY','COMMITMENT','IDEA')),
  FOREIGN KEY(tenant_id,space_id) REFERENCES spaces(tenant_id,space_id),
  UNIQUE(claim_id,tenant_id,space_id)
);
CREATE UNIQUE INDEX claims_client_id_uq ON claims(session_id, client_id) WHERE client_id IS NOT NULL;
CREATE TABLE claim_sources (
  claim_id uuid NOT NULL, tenant_id uuid NOT NULL, space_id uuid NOT NULL,
  utterance_id uuid NOT NULL, utterance_revision integer NOT NULL,
  PRIMARY KEY(claim_id, utterance_id, utterance_revision),
  FOREIGN KEY (claim_id,tenant_id,space_id) REFERENCES claims(claim_id,tenant_id,space_id) ON DELETE CASCADE,
  FOREIGN KEY (utterance_id,utterance_revision) REFERENCES utterance_revisions(utterance_id,revision) ON DELETE CASCADE
);
CREATE TABLE decision_events (
  event_id uuid PRIMARY KEY DEFAULT gen_random_uuid(), claim_id uuid NOT NULL REFERENCES claims(claim_id) ON DELETE CASCADE,
  tenant_id uuid NOT NULL, space_id uuid NOT NULL,
  from_state decision_state, to_state decision_state NOT NULL,
  utterance_id uuid, utterance_revision integer, actor text NOT NULL CHECK (actor IN ('MODEL','USER')),
  note text, created_at timestamptz NOT NULL DEFAULT now(),
  FOREIGN KEY(tenant_id,space_id) REFERENCES spaces(tenant_id,space_id)
);
-- Master memory_embeddings generalised to claims and utterance revisions (EXT).
CREATE TABLE embeddings (
  owner_kind text NOT NULL CHECK (owner_kind IN ('CLAIM','UTTERANCE')), owner_id uuid NOT NULL, owner_revision integer NOT NULL DEFAULT 1,
  tenant_id uuid NOT NULL, space_id uuid NOT NULL, session_id uuid, embedding_model text NOT NULL,
  embedding vector(1024) NOT NULL, updated_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (owner_kind, owner_id),
  FOREIGN KEY(tenant_id,space_id) REFERENCES spaces(tenant_id,space_id)
);
-- vector(1024): dimensions must match MS_EMBEDDING_DIMENSIONS; changing provider requires a migration + reindex.

CREATE TABLE insights (
  insight_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id uuid NOT NULL, space_id uuid NOT NULL, session_id uuid NOT NULL,
  kind text NOT NULL, short_text text NOT NULL, evidence_refs jsonb NOT NULL DEFAULT '[]'::jsonb,
  status text NOT NULL CHECK(status IN ('SUPPRESSED','DELIVERED','DISMISSED','EXPIRED')),
  output_channel text NOT NULL CHECK(output_channel IN ('TEXT','PRIVATE_VOICE','BOTH','NONE')),
  policy_version text NOT NULL, model_version text,
  expires_at timestamptz, created_at timestamptz NOT NULL DEFAULT now(),
  -- EXT
  long_text text, rationale text, source_kind text, scores jsonb NOT NULL DEFAULT '{}'::jsonb,
  suppress_reason text, delivered_at timestamptz, feedback text, voice_text text, saved_claim_id uuid,
  FOREIGN KEY(tenant_id,space_id,session_id) REFERENCES sessions(tenant_id,space_id,session_id)
);
CREATE TABLE ask_turns (
  ask_id uuid PRIMARY KEY DEFAULT gen_random_uuid(), tenant_id uuid NOT NULL, user_id uuid NOT NULL REFERENCES users(user_id),
  space_id uuid, session_id uuid REFERENCES sessions(session_id) ON DELETE CASCADE,
  mode text NOT NULL, scope text NOT NULL, scope_id uuid, question text NOT NULL,
  answer text NOT NULL, provenance_label text NOT NULL, citations jsonb NOT NULL DEFAULT '[]'::jsonb,
  uncertainty text NOT NULL, model_version text, created_at timestamptz NOT NULL DEFAULT now()
);

-- ---------------------------------------------------------------- context packs
CREATE TABLE interview_mocks (
  mock_id uuid PRIMARY KEY DEFAULT gen_random_uuid(), tenant_id uuid NOT NULL, space_id uuid NOT NULL,
  goal_id uuid REFERENCES projects(project_id), topic text NOT NULL, difficulty text NOT NULL,
  state text NOT NULL DEFAULT 'ACTIVE' CHECK (state IN ('ACTIVE','PAUSED','FINISHED')),
  settings jsonb NOT NULL DEFAULT '{}'::jsonb, debrief jsonb,
  created_by uuid NOT NULL REFERENCES users(user_id), created_at timestamptz NOT NULL DEFAULT now(), finished_at timestamptz,
  parent_mock_id uuid REFERENCES interview_mocks(mock_id),
  FOREIGN KEY(tenant_id,space_id) REFERENCES spaces(tenant_id,space_id)
);
CREATE TABLE mock_turns (
  turn_id uuid PRIMARY KEY DEFAULT gen_random_uuid(), mock_id uuid NOT NULL REFERENCES interview_mocks(mock_id) ON DELETE CASCADE,
  tenant_id uuid NOT NULL, space_id uuid NOT NULL, seq integer NOT NULL,
  role text NOT NULL CHECK (role IN ('INTERVIEWER','CANDIDATE','COACH')),
  kind text NOT NULL CHECK (kind IN ('QUESTION','FOLLOWUP','ANSWER','HINT','FEEDBACK','NOTICE')),
  text_value text NOT NULL, provenance provenance_kind NOT NULL, created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (mock_id, seq),
  FOREIGN KEY(tenant_id,space_id) REFERENCES spaces(tenant_id,space_id)
);
CREATE TABLE practice_items (
  item_id uuid PRIMARY KEY DEFAULT gen_random_uuid(), tenant_id uuid NOT NULL, space_id uuid NOT NULL,
  project_id uuid REFERENCES projects(project_id), session_id uuid REFERENCES sessions(session_id),
  concept text NOT NULL, prompt text NOT NULL, rubric text NOT NULL, kind text NOT NULL DEFAULT 'FREE_RECALL',
  anchors jsonb NOT NULL DEFAULT '[]'::jsonb, source_kind text NOT NULL,
  state text NOT NULL DEFAULT 'ACTIVE' CHECK (state IN ('ACTIVE','STALE','REMOVED')),
  created_by uuid NOT NULL REFERENCES users(user_id), created_at timestamptz NOT NULL DEFAULT now(),
  FOREIGN KEY(tenant_id,space_id) REFERENCES spaces(tenant_id,space_id)
);
CREATE TABLE practice_attempts (
  attempt_id uuid PRIMARY KEY DEFAULT gen_random_uuid(), item_id uuid NOT NULL REFERENCES practice_items(item_id) ON DELETE CASCADE,
  tenant_id uuid NOT NULL, space_id uuid NOT NULL, user_id uuid NOT NULL REFERENCES users(user_id),
  response text NOT NULL, verdict text NOT NULL CHECK (verdict IN ('CORRECT','PARTIAL','INCORRECT','UNGRADED')),
  feedback text NOT NULL, citations jsonb NOT NULL DEFAULT '[]'::jsonb, created_at timestamptz NOT NULL DEFAULT now(),
  FOREIGN KEY(tenant_id,space_id) REFERENCES spaces(tenant_id,space_id)
);
CREATE TABLE review_schedule (
  tenant_id uuid NOT NULL, space_id uuid NOT NULL, user_id uuid NOT NULL REFERENCES users(user_id),
  project_id uuid REFERENCES projects(project_id), concept_key text NOT NULL, concept text NOT NULL,
  due_at timestamptz NOT NULL, interval_days integer NOT NULL DEFAULT 1,
  status text NOT NULL DEFAULT 'ACTIVE' CHECK (status IN ('ACTIVE','SNOOZED','REMOVED')),
  lineage_state text NOT NULL DEFAULT 'HEARD' CHECK (lineage_state IN ('HEARD','EXPLAINED','PRACTICED','RETAINED')),
  difficult boolean NOT NULL DEFAULT false, last_verdict text, policy_version text NOT NULL,
  updated_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (user_id, space_id, concept_key),
  FOREIGN KEY(tenant_id,space_id) REFERENCES spaces(tenant_id,space_id)
);
CREATE TABLE shares (
  share_id uuid PRIMARY KEY DEFAULT gen_random_uuid(), tenant_id uuid NOT NULL, space_id uuid NOT NULL,
  session_id uuid NOT NULL REFERENCES sessions(session_id) ON DELETE CASCADE, token_hash text NOT NULL UNIQUE,
  snapshot jsonb NOT NULL, options jsonb NOT NULL, expires_at timestamptz NOT NULL, revoked_at timestamptz,
  stale boolean NOT NULL DEFAULT false, created_by uuid NOT NULL REFERENCES users(user_id),
  created_at timestamptz NOT NULL DEFAULT now(),
  FOREIGN KEY(tenant_id,space_id) REFERENCES spaces(tenant_id,space_id)
);
CREATE TABLE exports (
  export_id uuid PRIMARY KEY DEFAULT gen_random_uuid(), tenant_id uuid NOT NULL, user_id uuid NOT NULL REFERENCES users(user_id),
  scope jsonb NOT NULL, status text NOT NULL CHECK (status IN ('REQUESTED','IN_PROGRESS','COMPLETE','FAILED','EXPIRED')),
  object_key text, error text, created_at timestamptz NOT NULL DEFAULT now(), completed_at timestamptz, expires_at timestamptz
);

-- ---------------------------------------------------------------- jobs / deletion / ops
CREATE TABLE job_outbox (
  job_id uuid PRIMARY KEY DEFAULT gen_random_uuid(), tenant_id uuid NOT NULL, space_id uuid NOT NULL,
  session_id uuid, kind text NOT NULL, payload jsonb NOT NULL,
  idempotency_key text NOT NULL UNIQUE, status text NOT NULL DEFAULT 'READY',
  attempts int NOT NULL DEFAULT 0, available_at timestamptz NOT NULL DEFAULT now(),
  created_at timestamptz NOT NULL DEFAULT now(),
  lease_until timestamptz, last_error text, completed_at timestamptz, max_attempts int NOT NULL DEFAULT 6, -- EXT
  CHECK (status IN ('READY','LEASED','DONE','DEAD'))
);
CREATE TABLE deletion_requests (
  request_id uuid PRIMARY KEY DEFAULT gen_random_uuid(), tenant_id uuid NOT NULL, space_id uuid NOT NULL,
  session_id uuid, requested_by uuid NOT NULL REFERENCES users(user_id),
  status text NOT NULL CHECK(status IN ('REQUESTED','IN_PROGRESS','COMPLETE','ACTION_REQUIRED')),
  created_at timestamptz NOT NULL DEFAULT now(), completed_at timestamptz,
  scope_kind text NOT NULL DEFAULT 'SESSION' CHECK (scope_kind IN ('SESSION','SESSION_AUDIO','SPACE','PROJECT','CLAIM','ACCOUNT')), -- EXT
  target_id uuid, detail jsonb NOT NULL DEFAULT '{}'::jsonb
);
CREATE TABLE idempotency_keys (
  user_id uuid NOT NULL, key text NOT NULL, method text NOT NULL, path text NOT NULL, request_hash text NOT NULL,
  status_code int NOT NULL, response jsonb NOT NULL, created_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (user_id, key)
);
CREATE TABLE usage_meters (
  tenant_id uuid NOT NULL REFERENCES tenants(tenant_id), period text NOT NULL, meter text NOT NULL,
  quantity numeric NOT NULL DEFAULT 0, PRIMARY KEY (tenant_id, period, meter)
);
CREATE TABLE audit_events (
  audit_id bigserial PRIMARY KEY, tenant_id uuid, user_id uuid, action text NOT NULL,
  target_kind text, target_id uuid, detail jsonb NOT NULL DEFAULT '{}'::jsonb, created_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX sessions_scope_idx ON sessions(tenant_id,space_id,created_at DESC) WHERE deleted_at IS NULL;
CREATE INDEX utterances_session_idx ON utterances(tenant_id,space_id,session_id);
CREATE INDEX utterance_rev_session_idx ON utterance_revisions(session_id, start_ms);
CREATE INDEX utterance_rev_search_idx ON utterance_revisions USING gin(search);
CREATE INDEX claims_scope_idx ON claims(tenant_id,space_id,memory_state,created_at DESC);
CREATE INDEX claims_session_idx ON claims(session_id);
CREATE INDEX claims_search_idx ON claims USING gin(search);
CREATE INDEX outbox_ready_idx ON job_outbox(status,available_at);
CREATE INDEX insights_session_idx ON insights(session_id, created_at DESC);
CREATE INDEX events_session_idx ON session_events(session_id, sequence);
CREATE INDEX embeddings_space_idx ON embeddings(tenant_id, space_id);
