-- Fenced leases prevent a stalled worker from committing completion after another worker takes over.
ALTER TABLE job_outbox ADD COLUMN lease_token uuid;
ALTER TABLE job_outbox ADD COLUMN dispatched_at timestamptz;
CREATE INDEX job_outbox_dispatch ON job_outbox (available_at, dispatched_at) WHERE status IN ('READY', 'LEASED');
