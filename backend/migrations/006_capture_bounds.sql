-- Report missing sequences as compact intervals with honest (possibly unknown) time bounds.
ALTER TABLE sessions ADD COLUMN capture_end_ms bigint CHECK (capture_end_ms>=0);
ALTER TABLE sessions ADD CONSTRAINT final_sequence_bound CHECK (final_sequence BETWEEN -1 AND 9223372036854775806);
ALTER TABLE sessions ADD CONSTRAINT pause_sequence_bound CHECK (pause_watermark_sequence BETWEEN -1 AND 9223372036854775806);
ALTER TABLE audio_chunks ADD CONSTRAINT sequence_counter_bound CHECK (sequence_no<=9223372036854775806);
ALTER TABLE audio_chunks ADD CONSTRAINT capture_end_bound CHECK (capture_start_ms<=9223372036854775807-duration_ms);
ALTER TABLE session_runtime ADD CONSTRAINT received_sequence_bound CHECK (received_through_sequence BETWEEN -1 AND 9223372036854775806);
ALTER TABLE session_runtime ADD CONSTRAINT maximum_sequence_bound CHECK (max_sequence BETWEEN -1 AND 9223372036854775806);
ALTER TABLE capture_gaps
  ADD COLUMN missing_sequence_from bigint,
  ADD COLUMN missing_sequence_to bigint,
  ADD COLUMN time_bounds_estimated boolean NOT NULL DEFAULT false,
  ADD CONSTRAINT missing_sequence_bounds CHECK (
    (missing_sequence_from IS NULL AND missing_sequence_to IS NULL) OR
    (missing_sequence_from IS NOT NULL AND missing_sequence_to IS NOT NULL AND
     missing_sequence_from>=0 AND missing_sequence_to>=missing_sequence_from AND missing_sequence_to<=9223372036854775806));
CREATE UNIQUE INDEX capture_upload_hole_idx ON capture_gaps(session_id,missing_sequence_from,missing_sequence_to)
  WHERE reason='UPLOAD_MISSING' AND missing_sequence_from IS NOT NULL;
UPDATE capture_gaps SET time_bounds_estimated=true WHERE reason='UPLOAD_MISSING';
