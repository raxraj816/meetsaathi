# Provider integrations

Providers are explicitly selected; there is no silent vendor fallback. `available()` reports configuration and region eligibility,
not successful cloud reachability. Health capability flags therefore do not replace a real-provider smoke test.

| Capability | Baseline adapter | Configuration | When unavailable |
|---|---|---|---|
| Reasoning | Bedrock Converse, structured JSON, no executable tools; original schema validated locally | `MS_REASONER_PROVIDER=bedrock`, `MS_BEDROCK_MODEL_ID`, `MS_AWS_REGION`, `MS_ALLOWED_REGIONS` | Suppress insights; Think/Learn/Prepare unavailable; extractive Remember remains |
| Speech | Amazon Transcribe Streaming over HTTP/2 with concurrent PCM send/result receive | `MS_ASR_PROVIDER=amazon-transcribe`, `MS_TRANSCRIBE_ENABLED=true`, `MS_AWS_REGION`, language settings | Audio/notes preserved; captions marked unavailable |
| Objects | Application AES-GCM encryption plus S3 SSE-KMS | `MS_OBJECT_STORE_BACKEND=s3`, `MS_S3_BUCKET`, `MS_S3_KMS_KEY_ID` | Storage errors prevent ACK; client retains unacknowledged chunks |
| Queue | SQS notifications plus transactional PostgreSQL outbox and fenced worker leases | `MS_QUEUE_BACKEND=sqs`, `MS_SQS_QUEUE_URL` | Committed jobs remain in PostgreSQL for re-publication |
| Diarization | Separate NVIDIA Nemotron HTTP service | `MS_DIARIZER_URL`, `MS_DIARIZER_REGION`, `MS_DIARIZER_MAX_SPEAKERS` | Unassigned speakers; never guessed identities |
| Embeddings | Optional compatible embeddings service | `MS_EMBEDDING_*` | PostgreSQL lexical retrieval |
| Private TTS | Native platform synthesis | User opt-in, observed private route, user-heard sample | Text only |

AWS uses its default credential chain: an approved local profile during development, ECS task roles in deployment. Do not put
static AWS keys into mobile clients. Real AWS calls have **not** been executed in this workspace. SDK Stubber tests validate
request/response contracts; Transcribe's stream is exercised with an explicit test double.

Bedrock only accepts regional foundation model IDs/ARNs. Inference profiles are rejected because a configured endpoint alone does
not prove the processing destination. A model must support Converse structured output in the chosen region; no model is silently
selected. Unsupported provider schema constraints are removed from the generation schema and enforced against the original schema
afterward. AWS rejections and malformed, truncated or refused output become truthful degraded states.

The AWS speech path keeps a per-session connection open as acknowledged audio arrives, rather than waiting for six chunks.
A separately supervised actor starts from the first available speech chunk; it does not occupy the sequential job worker.
`MS_ASR_STREAM_CONCURRENCY` bounds connections **per worker process** (default 2), `MS_ASR_STREAM_IDLE_S` closes an idle connection
(default 4 seconds), and `MS_ASR_STREAM_MAX_S` rolls connections cleanly (default 900 seconds). Account quotas, autoscaling,
real-provider caption latency, word-boundary quality and multilingual accuracy still require AWS acceptance.

A renewable PostgreSQL lease fences each connection. Provider-final evidence and the millisecond capture-clock replay watermark
commit together; restart crops the first uncommitted PCM chunk. Clean input/output drain also commits trailing silence. Capture gaps,
rate changes and permanent upload gaps start separate connections. Provider failures leave audio uncommitted for bounded-backoff
retry; finalization waits for the stream to drain. Initial silence opens no connection; silence inside an active stream preserves
the audio clock, and silent/own-TTS output is suppressed. No GPU/model server is fabricated when diarization is unavailable.

Provider hypotheses emit `transcript.preview` and matching `transcript.preview_clear` events. Both native clients display them as
“Live draft · words may change”, expire stale drafts after 15 seconds and exclude them from transcript evidence. Provider-final
segments become ordinary application-provisional revisions until session finalization. Slow diarization uses a bounded FIFO for
finals so receiving the next draft can continue. See [ADR-018](../adr/ADR-018-persistent-live-speech.md).

S3 purges enumerate and remove all object versions and delete markers, checking per-object failures. A deletion request cannot be
marked complete if cloud purge fails. The bucket must not have an Object Lock/replication policy that silently retains content;
any future replication requires extending the deletion workflow. RDS backups remain subject to the disclosed 35-day policy.

## Explicit alternate providers

`MS_REASONER_PROVIDER=anthropic` selects the original direct Anthropic adapter (`MS_ANTHROPIC_API_KEY`, `MS_REASONER_MODEL`,
`MS_REASONER_REGION`). `MS_ASR_PROVIDER=openai-compatible` selects the original compatible transcription endpoint
(`MS_ASR_BASE_URL`, `MS_ASR_API_KEY`, `MS_ASR_MODEL`, `MS_ASR_REGION`). These are opt-in alternatives, not the v1.1 production baseline.
Local encrypted filesystem storage and the PostgreSQL-only queue remain development options.

## Nemotron HTTP contract

`POST {MS_DIARIZER_URL}/v1/diarize`, multipart fields: `audio` (mono PCM16 WAV), `stream_key` (session UUID),
`stream_offset_ms`, `max_speakers`. The service must maintain stable anonymous speaker IDs across windows.

```json
{"model_version":"nemotron-3-diarization-<rev>","max_speakers_supported":8,"speaker_count_estimate":3,
 "turns":[{"speaker":"spk_0","start_ms":120,"end_ms":2900,"confidence":0.91,"overlap":false}]}
```

Times are window-relative. Excess speaker count triggers “Speakers need review”; diarization does not establish identity.
No Nemotron model server/GPU fleet is included yet.

AWS contracts: [Bedrock structured output](https://docs.aws.amazon.com/bedrock/latest/userguide/structured-output.html),
[Transcribe SDK](https://github.com/awslabs/amazon-transcribe-streaming-sdk),
[S3 version deletion](https://docs.aws.amazon.com/AmazonS3/latest/userguide/DeletingObjectVersions.html).

Repeated failures without committed progress reach the finalization retry action (default budget 3, `MS_ASR_STREAM_RETRY_BUDGET`).
The recording stays saved; user retry resets the stream failure budget and resumes from the same committed watermark.

Short session language tags (the native default is `en`) resolve to an explicitly configured dialect (`en-IN` by default);
`auto` explicitly selects configured multilingual detection. Unmapped/ambiguous short tags fail visibly instead of guessing a locale.
