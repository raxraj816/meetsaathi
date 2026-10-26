-- Exports can leave an object behind if a transaction fails after object upload. The object key is
-- deterministic; track physical purge independently from the nullable committed object_key.
ALTER TABLE exports ADD COLUMN purged_at timestamptz;
CREATE INDEX exports_pending_purge ON exports (expires_at) WHERE purged_at IS NULL;
