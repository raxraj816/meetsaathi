# Threat model → implemented controls (master 9.1)

| Threat | Control in this codebase | Evidence |
|---|---|---|
| Undisclosed capture | Capture only after a session-specific consent receipt (`PARTICIPANTS_INFORMED` etc. + notices attested); OS permission is not consent; no capture at launch/reboot; Android FGS from visible activity only, neutral notification; iOS background audio only continues a started session | `test_no_recording_without_consent…`, `test_consent_never_carries_across_sessions`, `CaptureService`, `AudioRoutes.configureForCapture` |
| Prompt injection spoken in room / in JD | Reasoner has **no tools**; content passed only inside `<untrusted_…>` data blocks; outputs are schema JSON; citations re-verified server-side; no endpoint reachable from model output | `test_prompt_injection_in_speech_is_inert`, `test_reasoner_request_has_no_tools…`, `test_interview_mock_adaptive…` |
| Cross-tenant / cross-space leakage | Scope resolved and ACL-checked **before** retrieval; Postgres RLS (`may_read_space`, `session_live`) on every scoped table; app role cannot read credentials; same 404 for missing and unauthorized | `test_cross_tenant_session_access_is_denied`, `test_rls_denies_at_database_level`, `test_cross_space_retrieval_never_leaks` |
| Fake participant attribution | Anonymous aliases, `Unassigned` when weak, overlap flags; names only via user correction (revisioned, audited); quotes/owners never invented | `test_live_transcript_is_provisional…`, `test_finalization_promotes…`, `test_speaker_correction_cascades` |
| Speakerphone privacy leak | Private voice requires device present + user-heard sample; route loss hard-mutes locally, notifies server, downgrades channel to TEXT; reconnect requires a fresh check | `test_private_voice_fails_closed_on_route_loss`, iOS `RouteTests`, Android `PrivateVoice` |
| Token replay / stolen device | 15-min access tokens bound to device; rotating refresh tokens with reuse → device revocation; ingest tokens are short-lived, session-scoped and revocable; revoked device cannot stream | `test_register_login_refresh_rotation_and_reuse_detection`, `test_revoked_device_cannot_stream` |
| Unauthorized export / share | Export requires re-auth within 5 min; shares need preview + confirm, redact identities by default, exclude audio/source URLs, expire, revocable, marked stale on correction | `test_export_requires_reauth…`, `test_share_requires_preview…` |
| Sensitive retention | Separate audio / transcript / memory lifecycles; sensitive presets default EPHEMERAL + Quiet + text; audio retention window; audio-only deletion | `test_ephemeral_session_expires_unless_kept`, `test_delete_audio_keeps_notes_and_transcript` |
| Interview rule breach | AI permission separate from recording; enforced on start, controls, Ask, Explain and the insight scheduler; enterprise policy can disable | `test_interview_ai_gate_is_independent_of_recording`, `test_org_policy_disables_live_ai` |
| Model hallucination | Typed statuses (ACCEPTED only with cited agreement, else UNRESOLVED); uncited claims dropped; abstention copy; provisional evidence flagged | `test_remember_verifies_citations_and_abstains`, `test_finalization_promotes…` |
| Deletion orphaning | Tombstone hides all derived rows immediately (RLS); purge job removes objects, chunks, revisions, claims, insights, events, embeddings; auditable status | `test_session_deletion_revokes_immediately_and_purges` |
| Unapproved vendor/region | Adapters unavailable outside `MS_ALLOWED_REGIONS`; never auto-failover | `test_provider_outside_allowed_region_is_never_used` |
| Runaway spend | Monthly quotas per plan for capture hours and AI calls with user-visible 429; capture/notes keep working | `test_usage_quota_blocks_runaway_spend` |
| Telemetry leakage | Logs carry metadata only; no transcript/notes in logs | `test_default_logs_never_contain_conversation_content` |

SECURITY DEFINER functions (`may_read_space`, `may_write_space`, `is_tenant_member`, `space_created_by_me`, `space_owned_by_me`,
`session_live`) are owned by the migration owner with a locked `search_path`. `app.user_id` and `app.tombstoning` are set only by
server code; no SQL is exposed to clients. Open items before release: external pen test, KMS integration for the master key,
S3/GCS object store adapter with per-tenant keys, abuse/rate limiting at the edge.
