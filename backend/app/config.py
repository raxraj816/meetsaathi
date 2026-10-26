"""Runtime configuration. Every value comes from the environment (prefix MS_); nothing secret is defaulted
in production. `MS_ENV=dev|test` allows development defaults so the stack can boot locally."""
from __future__ import annotations

import base64
import os
from functools import lru_cache
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="MS_", env_file=".env", extra="ignore")

    env: str = "dev"
    # Database: owner URL is used only by the migration runner.
    database_owner_url: str = "postgresql://postgres:postgres_dev_only@localhost:55432/meetsaathi"
    database_app_url: str = "postgresql://ms_app:ms_app_dev_only@localhost:55432/meetsaathi"
    database_worker_url: str = "postgresql://ms_worker:ms_worker_dev_only@localhost:55432/meetsaathi"
    app_db_password: str = "ms_app_dev_only"
    worker_db_password: str = "ms_worker_dev_only"
    database_ca_file: str | None = None

    jwt_secret: str = "dev-only-jwt-secret-change-me-0123456789abcdef"
    access_token_ttl_s: int = 900
    refresh_token_ttl_s: int = 60 * 60 * 24 * 30
    ingest_token_ttl_s: int = 600
    reauth_window_s: int = 300

    # Base64 32-byte master key for envelope encryption. Production: supplied by KMS-backed secret store.
    master_key_b64: str = base64.b64encode(b"dev-only-master-key-32-bytes!!!!").decode()
    master_key_version: int = 1

    object_store_dir: str = "./var/objects"
    object_store_backend: Literal["local", "s3"] = "local"
    s3_bucket: str | None = None
    s3_kms_key_id: str | None = None
    aws_region: str = "ap-south-1"
    processing_region: str = "ap-south-1"
    allowed_regions: str = "ap-south-1"  # comma separated; providers outside are never used
    processing_disclosure_version: str = "pd-2026-10-18"
    policy_version: str = "ctx-policy-2026-10-18.1"

    # Reasoner (Claude). Unset key => AI features report "unavailable"; capture keeps working.
    anthropic_api_key: str | None = None
    reasoner_model: str = "claude-opus-5-5"
    reasoner_region: str = "ap-south-1"
    reasoner_timeout_s: float = 45.0
    reasoner_provider: Literal["anthropic", "bedrock"] = "bedrock"
    bedrock_model_id: str | None = None  # Explicit regional model ID; never silently use cross-region inference.

    # ASR: OpenAI-compatible /audio/transcriptions endpoint (hosted or self-hosted Whisper-class server).
    asr_base_url: str | None = None
    asr_api_key: str | None = None
    asr_model: str = "whisper-1"
    asr_region: str = "ap-south-1"
    asr_window_chunks: int = 6  # ~6 s of audio per live window with 1 s chunks
    asr_provider: Literal["amazon-transcribe", "openai-compatible"] = "amazon-transcribe"
    transcribe_enabled: bool = False
    transcribe_language_code: str = "en-IN"
    transcribe_language_options: str = "en-IN,hi-IN"
    speech_timeout_s: float = 60.0
    asr_stream_concurrency: int = Field(default=2, ge=1, le=8)
    asr_stream_idle_s: float = Field(default=4.0, ge=0.1, le=10)
    asr_stream_max_s: float = Field(default=900, ge=1, le=3600)
    asr_stream_retry_budget: int = Field(default=3, ge=1, le=10)

    # Diarizer: HTTP adapter for a self-hosted Nemotron 3 diarization service (contract in docs).
    diarizer_url: str | None = None
    diarizer_region: str = "ap-south-1"
    diarizer_max_speakers: int = 8

    # Embeddings: OpenAI-compatible /embeddings endpoint, optional (lexical retrieval always works).
    embedding_base_url: str | None = None
    embedding_api_key: str | None = None
    embedding_model: str = "text-embedding-3-small"
    embedding_dimensions: int = 1024
    embedding_region: str = "ap-south-1"

    max_chunk_bytes: int = 512 * 1024
    raw_audio_retention_days: int = 30
    ephemeral_retention_hours: int = 24
    export_ttl_s: int = 3600

    # Plan quotas (UNI-023). Hours of capture and reasoner calls per month.
    quota_capture_hours: dict[str, float] = Field(default_factory=lambda: {"FREE": 2, "INDIVIDUAL": 10, "POWER": 25, "TEAM": 200})
    quota_reasoner_calls: dict[str, int] = Field(default_factory=lambda: {"FREE": 200, "INDIVIDUAL": 2000, "POWER": 6000, "TEAM": 50000})

    worker_poll_interval_s: float = 0.5
    run_inline_worker: bool = True  # dev convenience: API process also drains the job queue
    queue_backend: Literal["postgres", "sqs"] = "postgres"
    sqs_queue_url: str | None = None
    worker_lease_s: int = Field(default=120, ge=30, le=43200)
    telemetry_enabled: bool = False
    telemetry_service_name: str = "meetsaathi-api"
    telemetry_otlp_endpoint: str = "http://localhost:4318"

    def validate_integrations(self) -> None:
        if self.object_store_backend == "s3" and not (self.s3_bucket and self.s3_kms_key_id):
            raise ValueError("S3 requires MS_S3_BUCKET and MS_S3_KMS_KEY_ID")
        if self.queue_backend == "sqs" and not self.sqs_queue_url:
            raise ValueError("SQS requires MS_SQS_QUEUE_URL")
        if (self.object_store_backend == "s3" or self.queue_backend == "sqs" or self.transcribe_enabled
                or (self.reasoner_provider == "bedrock" and self.bedrock_model_id)) and self.aws_region not in self.allowed_region_set():
            raise ValueError("MS_AWS_REGION must be explicitly included in MS_ALLOWED_REGIONS")

    def master_key(self) -> bytes:
        key = base64.b64decode(self.master_key_b64, validate=True)
        if len(key) != 32:
            raise ValueError("MS_MASTER_KEY_B64 must decode to 32 bytes")
        return key

    def allowed_region_set(self) -> set[str]:
        return {r.strip() for r in self.allowed_regions.split(",") if r.strip()}

    def validate_for_production(self) -> None:
        if self.env in ("dev", "test"):
            return
        problems = []
        try:
            self.master_key()
        except (ValueError, TypeError):
            problems.append("MS_MASTER_KEY_B64 (must be 32 bytes)")
        if "dev-only" in self.jwt_secret or len(self.jwt_secret) < 32:
            problems.append("MS_JWT_SECRET")
        if self.master_key_b64 == Settings.model_fields["master_key_b64"].default:
            problems.append("MS_MASTER_KEY_B64")
        if "dev_only" in self.database_app_url or "dev_only" in self.database_worker_url:
            problems.append("database credentials")
        if problems:
            raise RuntimeError("Refusing to start with development secrets: " + ", ".join(problems))


@lru_cache
def get_settings() -> Settings:
    s = Settings()
    s.validate_integrations()
    s.validate_for_production()
    return s


def reset_settings_cache() -> None:
    get_settings.cache_clear()
    os.environ.setdefault("MS_ENV", "dev")
