# AWS deployment and operations

Prepared configuration is not a deployed environment. Region: **ap-south-1**. The user intends to use their own AWS account.
On 19 October 2026, registry RDAP queries returned HTTP 404 for `polyameet.com`, `polyameet.in` and `polyameet.app`; they appear
unregistered. Registration must be confirmed by the registrar. No domain was bought. `api.polyameet.com` is provisional.

## Prerequisites and bootstrap

Use separate staging/production AWS accounts or strongly isolated roles/state. Configure an approved AWS CLI/SDK login locally;
this workspace currently has no AWS profile/credentials. Never paste access keys into chat or commit them.

Before applying: create an encrypted, versioned, private Terraform state bucket with state locking, a validated regional ACM API
certificate, an SNS alert topic with confirmed subscribers, a reviewed ADOT collector image and an initial backend image. Configure
GitHub environment protection and an OIDC deploy role restricted to the repository and environment. The deploy role needs only the
resource families defined by this stack and `iam:PassRole` for its three task/execution roles. No static GitHub AWS keys are needed.
The initial ECR/collector repositories may be bootstrapped separately; Terraform manages the backend repository after import.

```bash
terraform -chdir=infra/terraform init -backend-config=bucket=YOUR_STATE_BUCKET \
  -backend-config=key=staging/terraform.tfstate -backend-config=region=ap-south-1 \
  -backend-config=encrypt=true -backend-config=use_lockfile=true
cp infra/terraform/staging.tfvars.example infra/terraform/staging.tfvars
# Fill exact account/certificate/alert ARNs and immutable image digests.
terraform -chdir=infra/terraform plan -var-file=staging.tfvars -out=staging.tfplan
terraform -chdir=infra/terraform apply staging.tfplan
terraform -chdir=infra/terraform output -json > infra/deployment-outputs.json
backend/.venv/bin/python infra/bootstrap_secrets.py infra/deployment-outputs.json
backend/.venv/bin/python infra/deploy.py infra/deployment-outputs.json
```

Bootstrap starts services at zero desired tasks. Secret values are generated in memory and written directly to Secrets Manager,
not Terraform state or stdout. The migration task alone receives the owner connection string. Runtime tasks receive the app and
worker-role URLs plus signing/encryption material; custom auth currently requires trusted worker-role access from the API.
RDS connections validate TLS certificates and hostname using the bundled AWS RDS CA bundle (refresh deliberately on CA rotation).

The helper runs the one-shot migration first, verifies its exit status, promotes API and workers, waits for service stability, and
restores prior revisions/counts on failure. Terraform ignores service task-definition/count drift because promotion belongs to this
helper. Keep migrations compatible with the prior app version. A schema rollback is a reviewed operation, not an automatic step.

Create DNS `api` as an ALIAS/CNAME to the output ALB name, matching the ACM certificate. Configure both native Release API base URLs
with the resulting HTTPS origin before signing. The placeholder `.example` release URLs are not deployable endpoints.

## GitHub deployment

`.github/workflows/deploy.yml` is manual and runs the full reusable CI workflow first. It builds/scans an immutable ARM64 backend,
applies infrastructure, initializes secrets and promotes through the migration helper. Configure these environment variables:

`AWS_DEPLOY_ROLE_ARN`, `AWS_REGION`, `ECR_REPOSITORY_URL`, `TERRAFORM_STATE_BUCKET`, `TERRAFORM_STATE_KEY`,
`API_CERTIFICATE_ARN`, `ALARM_TOPIC_ARN`, `COLLECTOR_IMAGE`; optionally `BEDROCK_MODEL_ID`, `BEDROCK_MODEL_ARN`,
`TRANSCRIBE_ENABLED`, `DIARIZER_URL`. Model/service permissions and processing disclosures must match the chosen region.
The collector image must include `infra/otel/collector.yaml`; its base image must be reviewed and pinned to a digest.

A local Git repository is now initialized; no commit or remote exists yet. Workflows are implemented but have not run in GitHub.
Provision/signing workflows for TestFlight and Play internal testing remain to be completed after account/identity configuration.

## Validation before promotion to production

Execute actual AWS smoke tests: register/login, create/consent/start, stream consenting audio, inspect transcript source times,
Ask/citations, stop/finalize/review, export, delete, and verify all S3 versions disappear. Validate the actual bucket/KMS/model region,
not just a configured region label. Test denied IAM actions, provider outage, SQS duplicate delivery, worker death, and key rotation.
Run a staging load/90-minute soak and physical-device matrix; emulator silence is not speech-quality evidence.

`/v1/health` reports configuration; `/v1/ready` checks database reachability. CloudWatch includes API errors/latency, queue age/DLQ,
RDS storage/CPU and healthy API targets. The ADOT sidecar exports deliberate metadata-only OTLP metrics/traces to CloudWatch/X-Ray.
Verify collector health/permissions, alarm delivery and absence of content before relying on telemetry. The collector is nonessential
so its failure cannot stop capture; collector-loss alerts remain to be added and exercised.

## Incident and recovery procedures

- **Queue/provider outage:** committed outbox jobs stay durable. Restore broker/provider access; READY jobs re-publish. Investigate
  `DEAD` rows by kind and opaque ID, with no conversation text in logs. Retry only after correcting the cause; keep idempotency keys.
  Finalization retry is also user-visible. Never mark a purge complete by editing its status.
- **Deletion failure:** inspect the request's `ACTION_REQUIRED` state and S3/KMS permissions/version deletion failures. Requeue the
  existing purge job with its existing payload, `status=READY`, `attempts=0`, `lease_token=NULL`, `dispatched_at=NULL` after repair.
  Confirm all object versions and derivatives are absent before closing the incident.
- **App rollback:** select the previous immutable image/task definitions and use the promotion helper after validating schema
  compatibility. ECS circuit breakers are a second line of defense. Validate old mobile API compatibility before traffic resumes.
- **Database restore drill:** restore an RDS snapshot/PITR to an isolated instance with no application traffic or worker execution.
  Reapply current deletion tombstones/revocation ledger from the authoritative post-backup records before exposing any restored
  content. Verify cross-space RLS and sampled deletions; then perform controlled connection-secret cutover. No restore drill or
  external immutable deletion ledger is implemented/tested yet, so the promise never to resurrect deleted content is a release gate.
- **Secret rotation:** preserve application master keys until a versioned decrypt/re-encrypt migration exists. Current HKDF object
  encryption does not maintain a historical keyring: replacing the master key would make old objects unreadable. Rotate DB runtime
  passwords in both migration/runtime secrets, run migration, then replace services. Managed RDS owner rotation requires refreshing
  the migration secret with the bootstrap helper. JWT rotation currently signs out devices; overlapping signing keys remain pending.
- **Disaster assumptions:** RDS backup retention is 35 days; no measured RPO/RTO or cross-region recovery claim. Cross-region replication
  is intentionally absent until residency and deletion propagation are designed and approved.

Physical route safety, backups/deletion replay, KMS/key rotation, account recovery, abuse controls, store disclosures and legal,
security and accessibility sign-off remain production gates.

## Current container scan gate

Available OS upgrades fixed the flagged PCRE2 issue. Trivy still reports 44 HIGH package findings across eight unique CVEs with no
fixed Debian versions in the scan. See `qa/container-vulnerability-findings-2026-10-19.json`. Do not deploy while the configured
HIGH/CRITICAL gate fails. Some util-linux advisories require privileged operator behavior; the task runs as UID 10001 with all Linux
capabilities dropped and a read-only root filesystem, but reachability/mitigation acceptance still requires security review. No
scanner exceptions or ignores were added. [Debian's util-linux advisory](https://security-tracker.debian.org/tracker/CVE-2026-78408).
