# ADR-018 — Persistent live speech and durable recovery

Status: Implemented and locally tested; real AWS speech acceptance pending. Date: 19 October 2026.

The initial AWS adapter opened a stream for each six-chunk audio window. Because AWS requires real-time pacing, this doubled
buffering latency and repeatedly broke recognition context. A per-session actor now follows acknowledged audio continuously.
Actors run independently from ordinary jobs/SQS publication, with bounded concurrency and renewable, fenced database leases.
Every write rechecks the lease, session state, capture permission and source deletion under the session lock.

Only provider-final results create utterances. Their evidence and millisecond replay watermark commit together. A partial chunk is
replayed from its uncommitted PCM suffix after failure; silence after the final word advances only on clean provider drain. Clean
rollover, missing-input idle timeout, capture discontinuities and sample-rate changes close/drain the connection. Finalization
reschedules while backlog or a live connection remains. Repeated failures back off to 60 seconds rather than reopening in a hot loop.

Draft captions are separate durable events with stream/result IDs. They have no utterance IDs/citations and are unavailable to
retrieval, claims and extraction. Matching clear events cannot retract another connection's draft. Android and iOS show a draft
label, expire stale text after 15 seconds, clear on transport loss and reject other-session events. A recovered lease retracts the
abandoned connection's draft. Session content deletion covers these events through the existing purge path.

Finals are processed in order through a bounded queue, allowing subsequent hypotheses to arrive during diarization. Without an
available diarizer, attribution stays explicitly unassigned. Initial silence is consumed without a cloud connection; a bounded six-second source-quality buffer preserves sustained-silence warnings. In-stream
silence preserves clock continuity; silence hallucinations and app TTS are suppressed. Finite compatible ASR providers retain their
existing window path. There is no automatic provider fallback.

Verification uses real PostgreSQL with explicit provider/SDK doubles: hypotheses before input closes, exact replay suffix, lease
takeover, deletion during recognition, discontinuities, silent input, concurrency/shutdown, finalization/drain, early provider EOF,
drain timeout and duplicate finals. Native tests cover draft expiry and matching clear semantics. This does not establish actual
AWS latency, speech accuracy, mixed-language support, attribution quality, quotas or physical-device behavior.

Operational defaults: two actors per worker, 4-second input idle timeout, 15-minute clean rollover, existing 120-second lease.
Sizing worker tasks/service quotas, streaming-specific alarms and long-session/load/soak acceptance remain release gates.

Provider contracts: [AWS streaming recommendations](https://docs.aws.amazon.com/transcribe/latest/dg/streaming.html),
[AWS partial results](https://docs.aws.amazon.com/transcribe/latest/dg/streaming-partial-results.html).

Repeated failures without committed progress reach the finalization retry action (default budget 3, `MS_ASR_STREAM_RETRY_BUDGET`).
The recording stays saved; user retry resets the stream failure budget and resumes from the same committed watermark.
