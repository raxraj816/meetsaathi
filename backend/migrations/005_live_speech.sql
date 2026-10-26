-- A live ASR connection owns a fenced lease independent of the ordinary job queue.
-- The millisecond watermark commits atomically with provider-final evidence. On restart,
-- replay crops the first uncommitted PCM chunk at this point; drafts never advance it.
ALTER TABLE session_runtime
  ADD COLUMN asr_stream_token uuid,
  ADD COLUMN asr_stream_lease_until timestamptz,
  ADD COLUMN asr_committed_ms bigint NOT NULL DEFAULT 0 CHECK (asr_committed_ms >= 0),
  ADD COLUMN asr_retry_at timestamptz,
  ADD COLUMN asr_failures integer NOT NULL DEFAULT 0;

-- The previous finite-window pipeline may already have consumed silent audio.
UPDATE session_runtime r SET asr_committed_ms=COALESCE((
  SELECT max(c.capture_start_ms+c.duration_ms) FROM audio_chunks c JOIN sessions s USING(session_id)
  WHERE c.session_id=r.session_id AND c.sequence_no<=s.asr_cursor_sequence),0);
