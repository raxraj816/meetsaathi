-- MeetSaathi reference migration v1; PostgreSQL 16+ recommended.
-- These are implementation starting contracts: migrations, encryption, roles and performance
-- must be security-reviewed. Runtime app role MUST NOT have BYPASSRLS or table ownership.
CREATE EXTENSION IF NOT EXISTS pgcrypto;
CREATE EXTENSION IF NOT EXISTS vector;

CREATE TYPE session_state AS ENUM ('PREFLIGHT','STARTING','RECORDING','PAUSED','INTERRUPTED','STOPPING','FINALIZING','FINALIZATION_RETRYABLE','COMPLETED','COMPLETED_PARTIAL','ERROR','DELETING','DELETED');
CREATE TYPE context_kind AS ENUM ('MEETING','LEARNING','INTERVIEW','CONVERSATION');
CREATE TYPE provenance_kind AS ENUM ('RECORDED','IMPORTED','USER_NOTE','USER_RECOLLECTION','AI_ANALYSIS');
CREATE TYPE memory_status AS ENUM ('PENDING_REVIEW','APPROVED','INVALIDATED','DELETED');
CREATE TYPE decision_state AS ENUM ('PROPOSED','DISCUSSED','ACCEPTED','REJECTED','DEFERRED','SUPERSEDED','UNRESOLVED');

CREATE TABLE tenants (
  tenant_id uuid PRIMARY KEY DEFAULT gen_random_uuid(), name text NOT NULL,
  residency_region text NOT NULL, created_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE users (
  user_id uuid PRIMARY KEY, display_name text,
  created_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE tenant_memberships (
  tenant_id uuid NOT NULL REFERENCES tenants(tenant_id), user_id uuid NOT NULL REFERENCES users(user_id),
  role text NOT NULL CHECK (role IN ('OWNER','ADMIN','EDITOR','VIEWER')),
  PRIMARY KEY (tenant_id,user_id)
);
CREATE TABLE spaces (
  space_id uuid PRIMARY KEY DEFAULT gen_random_uuid(), tenant_id uuid NOT NULL REFERENCES tenants(tenant_id),
  name text NOT NULL, kind text NOT NULL CHECK(kind IN ('PERSONAL','WORK','LEARNING','CUSTOM')),
  created_by uuid NOT NULL REFERENCES users(user_id), created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (tenant_id,space_id)
);
CREATE TABLE space_memberships (
  tenant_id uuid NOT NULL, space_id uuid NOT NULL, user_id uuid NOT NULL REFERENCES users(user_id),
  role text NOT NULL CHECK(role IN ('OWNER','EDITOR','VIEWER')),
  PRIMARY KEY(space_id,user_id), FOREIGN KEY (tenant_id,space_id) REFERENCES spaces(tenant_id,space_id)
);
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
  FOREIGN KEY(tenant_id,space_id) REFERENCES spaces(tenant_id,space_id),
  UNIQUE(tenant_id,space_id,session_id)
);
CREATE TABLE consent_receipts (
  receipt_id uuid PRIMARY KEY DEFAULT gen_random_uuid(), tenant_id uuid NOT NULL, space_id uuid NOT NULL,
  session_id uuid NOT NULL, attested_by uuid NOT NULL REFERENCES users(user_id),
  capture_basis text NOT NULL, notices_attested boolean NOT NULL,
  ai_assistance_permitted boolean NOT NULL DEFAULT false,
  processing_disclosure_version text NOT NULL, scope_json jsonb NOT NULL DEFAULT '{}'::jsonb,
  recorded_at timestamptz NOT NULL DEFAULT now(),
  FOREIGN KEY(tenant_id,space_id,session_id) REFERENCES sessions(tenant_id,space_id,session_id)
);
CREATE TABLE audio_chunks (
  tenant_id uuid NOT NULL, space_id uuid NOT NULL, session_id uuid NOT NULL,
  sequence_no bigint NOT NULL CHECK(sequence_no>=0),
  sample_rate_hz integer NOT NULL CHECK(sample_rate_hz>0), capture_start_ms bigint NOT NULL CHECK(capture_start_ms>=0),
  duration_ms integer NOT NULL CHECK(duration_ms>0), sha256_hex char(64) NOT NULL,
  encrypted_object_key text NOT NULL, ingest_status text NOT NULL CHECK(ingest_status IN ('ACKED','QUARANTINED','PURGED')),
  created_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY(session_id, sequence_no),
  FOREIGN KEY(tenant_id,space_id,session_id) REFERENCES sessions(tenant_id,space_id,session_id)
);
CREATE TABLE session_speakers (
  speaker_alias_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id uuid NOT NULL, space_id uuid NOT NULL, session_id uuid NOT NULL,
  alias text NOT NULL, user_verified_label text, mapping_revision integer NOT NULL DEFAULT 1,
  confidence real CHECK(confidence IS NULL OR (confidence>=0 AND confidence<=1)),
  UNIQUE(session_id,alias),
  FOREIGN KEY(tenant_id,space_id,session_id) REFERENCES sessions(tenant_id,space_id,session_id)
);
CREATE TABLE utterances (
  utterance_id uuid PRIMARY KEY DEFAULT gen_random_uuid(), tenant_id uuid NOT NULL, space_id uuid NOT NULL,
  session_id uuid NOT NULL, current_revision integer NOT NULL DEFAULT 1,
  created_at timestamptz NOT NULL DEFAULT now(),
  FOREIGN KEY(tenant_id,space_id,session_id) REFERENCES sessions(tenant_id,space_id,session_id)
);
CREATE TABLE utterance_revisions (
  utterance_id uuid NOT NULL REFERENCES utterances(utterance_id), revision integer NOT NULL CHECK(revision>0),
  tenant_id uuid NOT NULL, space_id uuid NOT NULL, session_id uuid NOT NULL,
  start_ms bigint NOT NULL CHECK(start_ms>=0), end_ms bigint NOT NULL CHECK(end_ms>start_ms),
  speaker_alias_id uuid REFERENCES session_speakers(speaker_alias_id),
  transcript text NOT NULL, is_final boolean NOT NULL DEFAULT false,
  provenance provenance_kind NOT NULL DEFAULT 'RECORDED', asr_model_version text,
  diarizer_model_version text, speaker_confidence real CHECK(speaker_confidence IS NULL OR (speaker_confidence>=0 AND speaker_confidence<=1)),
  created_at timestamptz NOT NULL DEFAULT now(), PRIMARY KEY(utterance_id,revision),
  FOREIGN KEY(tenant_id,space_id,session_id) REFERENCES sessions(tenant_id,space_id,session_id)
);
CREATE TABLE claims (
  claim_id uuid PRIMARY KEY DEFAULT gen_random_uuid(), tenant_id uuid NOT NULL, space_id uuid NOT NULL,
  session_id uuid REFERENCES sessions(session_id), claim_kind text NOT NULL,
  text_value text NOT NULL, provenance provenance_kind NOT NULL,
  decision_status decision_state,
  memory_state memory_status NOT NULL DEFAULT 'PENDING_REVIEW',
  sensitivity text NOT NULL DEFAULT 'NORMAL', model_version text, policy_version text,
  created_at timestamptz NOT NULL DEFAULT now(), invalidated_at timestamptz,
  FOREIGN KEY(tenant_id,space_id) REFERENCES spaces(tenant_id,space_id),
  UNIQUE(claim_id,tenant_id,space_id)
);
CREATE TABLE claim_sources (
  claim_id uuid NOT NULL, tenant_id uuid NOT NULL, space_id uuid NOT NULL,
  utterance_id uuid NOT NULL, utterance_revision integer NOT NULL,
  PRIMARY KEY(claim_id, utterance_id, utterance_revision),
  FOREIGN KEY (claim_id,tenant_id,space_id) REFERENCES claims(claim_id,tenant_id,space_id) ON DELETE CASCADE,
  FOREIGN KEY (utterance_id,utterance_revision) REFERENCES utterance_revisions(utterance_id,revision)
);
CREATE TABLE memory_embeddings (
  claim_id uuid PRIMARY KEY REFERENCES claims(claim_id) ON DELETE CASCADE,
  tenant_id uuid NOT NULL, space_id uuid NOT NULL, embedding_model text NOT NULL,
  embedding vector(768), updated_at timestamptz NOT NULL DEFAULT now(),
  FOREIGN KEY(tenant_id,space_id) REFERENCES spaces(tenant_id,space_id)
);
-- vector(768) is illustrative; set real dimensions per embedding provider/version.
CREATE TABLE insights (
  insight_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id uuid NOT NULL, space_id uuid NOT NULL, session_id uuid NOT NULL,
  kind text NOT NULL, short_text text NOT NULL, evidence_refs jsonb NOT NULL DEFAULT '[]'::jsonb,
  status text NOT NULL CHECK(status IN ('SUPPRESSED','DELIVERED','DISMISSED','EXPIRED')),
  output_channel text NOT NULL CHECK(output_channel IN ('TEXT','PRIVATE_VOICE','BOTH','NONE')),
  policy_version text NOT NULL, model_version text,
  expires_at timestamptz, created_at timestamptz NOT NULL DEFAULT now(),
  FOREIGN KEY(tenant_id,space_id,session_id) REFERENCES sessions(tenant_id,space_id,session_id)
);
CREATE TABLE job_outbox (
  job_id uuid PRIMARY KEY DEFAULT gen_random_uuid(), tenant_id uuid NOT NULL, space_id uuid NOT NULL,
  session_id uuid, kind text NOT NULL, payload jsonb NOT NULL,
  idempotency_key text NOT NULL UNIQUE, status text NOT NULL DEFAULT 'READY',
  attempts int NOT NULL DEFAULT 0, available_at timestamptz NOT NULL DEFAULT now(),
  created_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE deletion_requests (
  request_id uuid PRIMARY KEY DEFAULT gen_random_uuid(), tenant_id uuid NOT NULL, space_id uuid NOT NULL,
  session_id uuid, requested_by uuid NOT NULL REFERENCES users(user_id),
  status text NOT NULL CHECK(status IN ('REQUESTED','IN_PROGRESS','COMPLETE','ACTION_REQUIRED')),
  created_at timestamptz NOT NULL DEFAULT now(), completed_at timestamptz
);
CREATE INDEX sessions_scope_idx ON sessions(tenant_id,space_id,created_at DESC) WHERE deleted_at IS NULL;
CREATE INDEX utterances_session_idx ON utterances(tenant_id,space_id,session_id);
CREATE INDEX claims_scope_idx ON claims(tenant_id,space_id,memory_state,created_at DESC);
CREATE INDEX outbox_ready_idx ON job_outbox(status,available_at);

-- Defense in depth: every tenant/space-scoped table gets row-level security.
-- The app sets app.user_id to a VERIFIED authenticated UUID per transaction;
-- it cannot let a client set arbitrary session variables through exposed SQL.
CREATE OR REPLACE FUNCTION current_app_user() RETURNS uuid LANGUAGE sql STABLE AS $$
  SELECT NULLIF(current_setting('app.user_id',true),'')::uuid
$$;
CREATE OR REPLACE FUNCTION may_read_space(t uuid, s uuid) RETURNS boolean LANGUAGE sql STABLE SECURITY DEFINER SET search_path=public AS $$
  SELECT EXISTS (SELECT 1 FROM space_memberships m WHERE m.tenant_id=t AND m.space_id=s AND m.user_id=current_app_user())
$$;
-- SECURITY DEFINER requires locked search_path and a security audit of owner/privileges.
DO $$ DECLARE n text; BEGIN
  FOREACH n IN ARRAY ARRAY['spaces','space_memberships','sessions','consent_receipts','audio_chunks','session_speakers','utterances','utterance_revisions','claims','claim_sources','memory_embeddings','insights','job_outbox','deletion_requests'] LOOP
    EXECUTE format('ALTER TABLE %I ENABLE ROW LEVEL SECURITY',n);
    EXECUTE format('ALTER TABLE %I FORCE ROW LEVEL SECURITY',n);
  END LOOP;
END $$;
-- Read policies for example tables; production migration must add explicit read/write
-- policies for every scoped table and service role, or access will deny by default.
CREATE POLICY session_read ON sessions FOR SELECT USING (may_read_space(tenant_id,space_id) AND deleted_at IS NULL);
CREATE POLICY claims_read ON claims FOR SELECT USING (may_read_space(tenant_id,space_id) AND memory_state<>'DELETED');
CREATE POLICY utterance_read ON utterances FOR SELECT USING (may_read_space(tenant_id,space_id));
CREATE POLICY utterance_revision_read ON utterance_revisions FOR SELECT USING (may_read_space(tenant_id,space_id));
CREATE POLICY space_read ON spaces FOR SELECT USING (may_read_space(tenant_id,space_id));
-- All runtime writes MUST use explicit service APIs with authorization, audit and policy gates.

-- Allow application users to inspect only their own membership records; this is
-- needed by may_read_space() under FORCE ROW LEVEL SECURITY.
CREATE POLICY membership_self_read ON space_memberships FOR SELECT USING (user_id=current_app_user());
CREATE POLICY claims_sources_read ON claim_sources FOR SELECT USING (may_read_space(tenant_id,space_id));
-- A production migration should add composite FOREIGN KEY checks tying source utterance
-- revisions to the exact tenant+space and should explicitly grant/refuse worker roles.
