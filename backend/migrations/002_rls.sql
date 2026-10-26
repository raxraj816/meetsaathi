-- MeetSaathi migration 002: row-level security (master 8.4, schema_v1 defense-in-depth note).
-- ms_app    : request-path role. Every transaction sets app.user_id to the VERIFIED authenticated user.
-- ms_worker : trusted service role for auth bootstrap and durable jobs. Explicit policies below.
-- Neither role owns tables; the migration owner is the only privileged role.

CREATE OR REPLACE FUNCTION current_app_user() RETURNS uuid LANGUAGE sql STABLE AS $$
  SELECT NULLIF(current_setting('app.user_id',true),'')::uuid
$$;

CREATE OR REPLACE FUNCTION may_read_space(t uuid, s uuid) RETURNS boolean
LANGUAGE sql STABLE SECURITY DEFINER SET search_path=public AS $$
  SELECT EXISTS (
    SELECT 1 FROM space_memberships m JOIN spaces sp ON sp.space_id = m.space_id
    WHERE m.tenant_id=t AND m.space_id=s AND m.user_id=current_app_user() AND sp.deleted_at IS NULL)
$$;

CREATE OR REPLACE FUNCTION may_write_space(t uuid, s uuid) RETURNS boolean
LANGUAGE sql STABLE SECURITY DEFINER SET search_path=public AS $$
  SELECT EXISTS (
    SELECT 1 FROM space_memberships m JOIN spaces sp ON sp.space_id = m.space_id
    WHERE m.tenant_id=t AND m.space_id=s AND m.user_id=current_app_user()
      AND m.role IN ('OWNER','EDITOR') AND sp.deleted_at IS NULL)
$$;

CREATE OR REPLACE FUNCTION is_tenant_member(t uuid, roles text[] DEFAULT ARRAY['OWNER','ADMIN','EDITOR','VIEWER'])
RETURNS boolean LANGUAGE sql STABLE SECURITY DEFINER SET search_path=public AS $$
  SELECT EXISTS (SELECT 1 FROM tenant_memberships m WHERE m.tenant_id=t AND m.user_id=current_app_user() AND m.role = ANY(roles))
$$;

CREATE OR REPLACE FUNCTION space_created_by_me(s uuid) RETURNS boolean
LANGUAGE sql STABLE SECURITY DEFINER SET search_path=public AS $$
  SELECT EXISTS (SELECT 1 FROM spaces WHERE space_id=s AND created_by=current_app_user())
$$;

-- Deleted (tombstoned) sessions become invisible immediately for all derived rows (master 6.3).
CREATE OR REPLACE FUNCTION session_live(sid uuid) RETURNS boolean
LANGUAGE sql STABLE SECURITY DEFINER SET search_path=public AS $$
  SELECT sid IS NULL OR EXISTS (SELECT 1 FROM sessions WHERE session_id=sid AND deleted_at IS NULL)
$$;
-- SECURITY DEFINER functions: owner is the migration owner; search_path is locked; audited in docs/threat-model.md.

REVOKE ALL ON ALL TABLES IN SCHEMA public FROM PUBLIC;
REVOKE EXECUTE ON ALL FUNCTIONS IN SCHEMA public FROM PUBLIC;
GRANT USAGE ON SCHEMA public TO ms_app, ms_worker;
GRANT EXECUTE ON FUNCTION current_app_user(), may_read_space(uuid,uuid), may_write_space(uuid,uuid),
  is_tenant_member(uuid,text[]), space_created_by_me(uuid), session_live(uuid) TO ms_app, ms_worker;

-- Worker / service role: full DML on everything, through explicit role-targeted policies.
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO ms_worker;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO ms_worker, ms_app;

-- Request role: no access to credentials or refresh tokens at all.
GRANT SELECT, INSERT, UPDATE, DELETE ON
  tenants, users, tenant_memberships, user_preferences, spaces, space_memberships, projects,
  sessions, session_runtime, session_state_log, session_events, consent_receipts, ingest_tokens,
  audio_chunks, capture_gaps, session_speakers, speaker_mapping_history, utterances, utterance_revisions,
  claims, claim_sources, decision_events, embeddings, insights, ask_turns, interview_mocks, mock_turns,
  practice_items, practice_attempts, review_schedule, shares, exports, job_outbox, deletion_requests,
  idempotency_keys, usage_meters, audit_events
TO ms_app;
GRANT SELECT, UPDATE ON devices TO ms_app;

DO $$ DECLARE n text; BEGIN
  FOREACH n IN ARRAY ARRAY[
    'tenants','users','user_credentials','devices','refresh_tokens','tenant_memberships','user_preferences',
    'spaces','space_memberships','projects','sessions','session_runtime','session_state_log','session_events',
    'consent_receipts','ingest_tokens','audio_chunks','capture_gaps','session_speakers','speaker_mapping_history',
    'utterances','utterance_revisions','claims','claim_sources','decision_events','embeddings','insights',
    'ask_turns','interview_mocks','mock_turns','practice_items','practice_attempts','review_schedule','shares',
    'exports','job_outbox','deletion_requests','idempotency_keys','usage_meters','audit_events'] LOOP
    EXECUTE format('ALTER TABLE %I ENABLE ROW LEVEL SECURITY', n);
    EXECUTE format('ALTER TABLE %I FORCE ROW LEVEL SECURITY', n);
    EXECUTE format('CREATE POLICY worker_all ON %I TO ms_worker USING (true) WITH CHECK (true)', n);
  END LOOP;
END $$;

-- Space-scoped content tables: read = member, write = OWNER/EDITOR member.
DO $$ DECLARE n text; BEGIN
  FOREACH n IN ARRAY ARRAY[
    'projects','session_runtime','session_state_log','consent_receipts','ingest_tokens','capture_gaps',
    'session_speakers','speaker_mapping_history','claim_sources','decision_events','embeddings',
    'interview_mocks','mock_turns','practice_items','practice_attempts','review_schedule','shares',
    'job_outbox','deletion_requests'] LOOP
    EXECUTE format('CREATE POLICY app_read ON %I FOR SELECT TO ms_app USING (may_read_space(tenant_id,space_id))', n);
    EXECUTE format('CREATE POLICY app_insert ON %I FOR INSERT TO ms_app WITH CHECK (may_write_space(tenant_id,space_id))', n);
    EXECUTE format('CREATE POLICY app_update ON %I FOR UPDATE TO ms_app USING (may_write_space(tenant_id,space_id)) WITH CHECK (may_write_space(tenant_id,space_id))', n);
    EXECUTE format('CREATE POLICY app_delete ON %I FOR DELETE TO ms_app USING (may_write_space(tenant_id,space_id))', n);
  END LOOP;
END $$;

-- Session-derived tables additionally disappear the moment their session is tombstoned.
DO $$ DECLARE n text; BEGIN
  FOREACH n IN ARRAY ARRAY['session_events','audio_chunks','utterances','utterance_revisions','insights'] LOOP
    EXECUTE format('CREATE POLICY app_read ON %I FOR SELECT TO ms_app USING (may_read_space(tenant_id,space_id) AND session_live(session_id))', n);
    EXECUTE format('CREATE POLICY app_insert ON %I FOR INSERT TO ms_app WITH CHECK (may_write_space(tenant_id,space_id) AND session_live(session_id))', n);
    EXECUTE format('CREATE POLICY app_update ON %I FOR UPDATE TO ms_app USING (may_write_space(tenant_id,space_id)) WITH CHECK (may_write_space(tenant_id,space_id))', n);
    EXECUTE format('CREATE POLICY app_delete ON %I FOR DELETE TO ms_app USING (may_write_space(tenant_id,space_id))', n);
  END LOOP;
END $$;

CREATE POLICY app_read ON sessions FOR SELECT TO ms_app USING (may_read_space(tenant_id,space_id) AND deleted_at IS NULL);
CREATE POLICY app_insert ON sessions FOR INSERT TO ms_app WITH CHECK (may_write_space(tenant_id,space_id) AND created_by = current_app_user());
CREATE POLICY app_update ON sessions FOR UPDATE TO ms_app USING (may_write_space(tenant_id,space_id) AND deleted_at IS NULL) WITH CHECK (may_write_space(tenant_id,space_id));

CREATE POLICY app_read ON claims FOR SELECT TO ms_app USING (may_read_space(tenant_id,space_id) AND memory_state <> 'DELETED' AND session_live(session_id));
CREATE POLICY app_insert ON claims FOR INSERT TO ms_app WITH CHECK (may_write_space(tenant_id,space_id) AND session_live(session_id));
CREATE POLICY app_update ON claims FOR UPDATE TO ms_app USING (may_write_space(tenant_id,space_id) AND memory_state <> 'DELETED') WITH CHECK (may_write_space(tenant_id,space_id));

CREATE POLICY app_read ON spaces FOR SELECT TO ms_app USING (may_read_space(tenant_id,space_id) OR (created_by = current_app_user() AND deleted_at IS NULL));
CREATE POLICY app_insert ON spaces FOR INSERT TO ms_app WITH CHECK (created_by = current_app_user() AND is_tenant_member(tenant_id, ARRAY['OWNER','ADMIN','EDITOR']));
CREATE POLICY app_update ON spaces FOR UPDATE TO ms_app USING (may_write_space(tenant_id,space_id)) WITH CHECK (true);

CREATE POLICY membership_self_read ON space_memberships FOR SELECT TO ms_app USING (user_id = current_app_user());
CREATE POLICY membership_creator_insert ON space_memberships FOR INSERT TO ms_app
  WITH CHECK (user_id = current_app_user() AND role = 'OWNER' AND space_created_by_me(space_id));

CREATE POLICY app_read ON tenants FOR SELECT TO ms_app USING (is_tenant_member(tenant_id));
CREATE POLICY app_read ON tenant_memberships FOR SELECT TO ms_app USING (user_id = current_app_user());
CREATE POLICY app_self ON users FOR SELECT TO ms_app USING (user_id = current_app_user());
CREATE POLICY app_self_update ON users FOR UPDATE TO ms_app USING (user_id = current_app_user()) WITH CHECK (user_id = current_app_user());
CREATE POLICY app_self ON devices FOR SELECT TO ms_app USING (user_id = current_app_user());
CREATE POLICY app_self_update ON devices FOR UPDATE TO ms_app USING (user_id = current_app_user()) WITH CHECK (user_id = current_app_user());

DO $$ DECLARE n text; BEGIN
  FOREACH n IN ARRAY ARRAY['user_preferences','ask_turns','exports','idempotency_keys'] LOOP
    EXECUTE format('CREATE POLICY app_self ON %I FOR ALL TO ms_app USING (user_id = current_app_user()) WITH CHECK (user_id = current_app_user())', n);
  END LOOP;
END $$;
CREATE POLICY app_read ON usage_meters FOR SELECT TO ms_app USING (is_tenant_member(tenant_id));
CREATE POLICY app_write ON usage_meters FOR INSERT TO ms_app WITH CHECK (is_tenant_member(tenant_id));
CREATE POLICY app_update ON usage_meters FOR UPDATE TO ms_app USING (is_tenant_member(tenant_id)) WITH CHECK (is_tenant_member(tenant_id));
CREATE POLICY app_self ON audit_events FOR SELECT TO ms_app USING (user_id = current_app_user());
CREATE POLICY app_insert ON audit_events FOR INSERT TO ms_app WITH CHECK (user_id = current_app_user());

-- ask_turns scoped to a space must also be readable only while that space is readable.
CREATE POLICY ask_space_guard ON ask_turns AS RESTRICTIVE FOR SELECT TO ms_app
  USING (space_id IS NULL OR may_read_space(tenant_id, space_id));

-- Tombstoning: an UPDATE that hides a row (deleted_at / memory_state='DELETED') must still satisfy SELECT
-- visibility for the new row. Deletion code - and only deletion code - sets app.tombstoning='on' for the
-- statements that revoke access. Clients cannot set session variables (no SQL is exposed).
CREATE POLICY app_tombstone_visibility ON sessions FOR SELECT TO ms_app
  USING (current_setting('app.tombstoning', true) = 'on' AND may_write_space(tenant_id, space_id));
CREATE POLICY app_tombstone_visibility ON claims FOR SELECT TO ms_app
  USING (current_setting('app.tombstoning', true) = 'on' AND may_write_space(tenant_id, space_id));
CREATE OR REPLACE FUNCTION space_owned_by_me(s uuid) RETURNS boolean
LANGUAGE sql STABLE SECURITY DEFINER SET search_path=public AS $$
  SELECT EXISTS (SELECT 1 FROM space_memberships WHERE space_id=s AND user_id=current_app_user() AND role='OWNER')
$$;
GRANT EXECUTE ON FUNCTION space_owned_by_me(uuid) TO ms_app, ms_worker;
CREATE POLICY app_tombstone_visibility ON spaces FOR SELECT TO ms_app
  USING (current_setting('app.tombstoning', true) = 'on' AND space_owned_by_me(space_id));
