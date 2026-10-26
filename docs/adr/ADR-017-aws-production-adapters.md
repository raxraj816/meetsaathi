# ADR-017 — AWS adapters and production delivery continuation

Status: Implemented with local contract tests; live AWS acceptance pending. Date: 19 October 2026.

The v1.1 addendum specifies Amazon Transcribe, Bedrock, S3, SQS, ECS Fargate and Terraform. The inherited implementation had direct
Anthropic/compatible ASR adapters, local storage, a PostgreSQL queue, and no cloud infrastructure. These substitutes were not
sufficient evidence of the addendum's production baseline.

AWS is now the explicit speech/reasoning selection; it remains unavailable until explicitly configured. The existing alternate
providers remain opt-in for development/evaluation. AWS credentials come from the standard chain and ECS task roles, never mobile
clients. The deployment region is `ap-south-1` per the user. Earlier `in-south-1` defaults were invalid AWS region identifiers.

S3 retains application AES-GCM encryption and adds SSE-KMS. Purge handles all versions/delete markers and checks partial failures.
Exports are revoked on source deletion, expire at download time, and are physically purged by durable deletion/retention work.

SQS carries opaque job IDs after outbox commit. PostgreSQL remains authoritative for retry/dead state and fenced renewable leases.
Periodic republication recovers missed notifications. Publication runs independently of long handlers. The broker DLQ complements
application dead jobs; these are separate operational signals, not interchangeable delivery guarantees.

Terraform provides private Fargate tasks and RDS, encrypted objects/queues/secrets, HTTPS ALB, WAF rate limits, scoped task identities,
CloudWatch alarms and an ADOT sidecar configuration. No secret values are Terraform resources. Bootstrap preserves generated
credentials across retries and updates the migration owner credential after RDS rotation. The deployment helper verifies migration
success before promotion and restores both service revisions if promotion fails. Database schema changes must remain backward
compatible; application rollback does not roll back a migration.

OpenTelemetry emits only bounded route/method/status/job-kind metadata. Generic HTTP/model auto-instrumentation is deliberately
absent. Transcript text, prompts, query strings, authorization values and provider exception bodies must not enter telemetry.

Remaining deviations/gates:

- Persistent Transcribe is implemented in ADR-018; actual AWS latency/word-boundary benchmarks remain pending.
- Nemotron's server and measured GPU deployment are absent; unknown speakers remain explicit.
- Native device TTS is retained pending language/latency and private-route evaluations.
- Custom scrypt/JWT/device auth is retained as the current equivalent identity implementation. Managed OIDC, email verification and
  account recovery remain unresolved production identity gates.
- Full Xcode/iOS SDK, signing identities, physical devices, AWS login, actual model/service access, DNS registration and operational
  acceptance are not available evidence. No resource has been deployed and no domain purchased.

The product remains in implementation, not release-ready. See `docs/BUILD_STATUS.md` and `docs/deployment.md`.
