# ADR-019 — Bounded upload counters and honest missing-source intervals

Status: Implemented; local integration/native verification. Date: 19 October 2026.

The original ACK and finalization queries expanded every integer up to a client-supplied sequence. A sparse or very large counter
could consume database time and memory despite a small upload body. End also accepted an older watermark than the server's stored
source, and a missing tail was described as an invented one-second gap.

Gap queries now inspect ordered stored ACK rows plus one upper sentinel. ACK responses enumerate at most 1,000 missing IDs and add
`gap_sequences_truncated` when that hint is incomplete. The contiguous watermark is computed in one ordered pass; it does not use a
correlated lookup for each row, which was slow under RLS before statistics reflected a large offline batch. Missing-source records
are compact inclusive sequence intervals rather than one operation per absent number. These changes preserve sparse/out-of-order
and long offline replay; they introduce no duration cap or arbitrary maximum upload lead.

Capture sequence values are bounded to -1 (empty) through 9223372036854775806, reserving the final signed-bigint value for the upper
sentinel. Capture milliseconds fit a nonnegative signed bigint, and each chunk's duration must fit its end timestamp. HTTP/domain
checks reject overflow before storage/SQL; migration 006 enforces the persisted bounds too. PCM length/sample validation remains
within one rounded millisecond. FastAPI's intermediate schema model rounds these large bounds through float. The public/generated OpenAPI contract restores exact
integer limits from the Pydantic model/parameter metadata and declares `int64`, matching actual request validation.

Pause, interruption and End cannot move their watermark behind the highest stored sequence. An older or omitted client End value
therefore preserves all acknowledged audio and permits missing earlier chunks to drain. A separately stored `capture_end_ms` records
the client-declared clock bound without promoting it to recorded evidence. Consent withdrawal has an immediate drain deadline and
issues no new upload credential, because further uploads are forbidden.

`UPLOAD_MISSING` exposes `missing_sequence_from/to` and `time_bounds_estimated`. Adjacent recorded timestamps bound missing audio
approximately. A tail without a usable declared end keeps `end_ms=null`; no duration is invented, including when late source grows
past an older declared end. Gap ranges are idempotent. Native transcript/recap views label approximate timing and unknown ends;
exports preserve the same metadata. Existing pause/interruption gap fields remain compatible.

Finite ASR now selects actual stored chunks past a permanent gap, rather than inspecting only the next few numeric sequence IDs.
Windows split on capture-clock discontinuities (one millisecond rounding tolerance); provider segments outside supplied audio are
rejected, and logically deleted audio is skipped before provider access. The persistent AWS path retains the same bounds.
Swift generic JSON preserves signed 64-bit integers; timestamp conversions no longer round through Double or trap on overflow.

Verification covers the largest accepted sparse counter, truncation boundaries, integer/time overflow, stale/omitted control
watermarks, delayed End uploads, known/unknown/stale tail clocks, consent withdrawal, source-boundary rejection and source deletion.
A 5,400-chunk ACK metadata fixture verifies 90-minute counter replay only; it is not a physical capture, background, battery,
speech-quality or cloud-load acceptance result. Actual AWS/device/production release gates remain in BUILD_STATUS.md.
