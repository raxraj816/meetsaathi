"""Capture counters and sparse sequence holes. Work scales with stored chunks, never a declared gap.

Reserve one signed-bigint value for the exclusive upper sentinel used by the range query. This is
a representation bound, not a session-duration or offline-upload limit.
"""
from __future__ import annotations

from ..errors import preflight_failed

MAX_CAPTURE_MS = (1 << 63) - 1
MAX_SEQUENCE = MAX_CAPTURE_MS - 1
ACK_GAP_LIMIT = 1000

# $1=session, $2=last contiguous sequence, $3=inclusive upper sequence. The sentinel
# exposes trailing holes too. LAG visits only stored ACK rows and that one sentinel.
HOLES_SQL = """
WITH stored AS (
  SELECT sequence_no, capture_start_ms, capture_start_ms+duration_ms AS end_ms
  FROM audio_chunks WHERE session_id=$1 AND ingest_status='ACKED' AND sequence_no>$2 AND sequence_no<=$3
  UNION ALL SELECT $3::bigint+1, NULL::bigint, NULL::bigint
), boundaries AS (
  SELECT lag(sequence_no,1,$2::bigint) OVER (ORDER BY sequence_no)+1 AS sequence_from,
         sequence_no-1 AS sequence_to,
         lag(end_ms,1,0::bigint) OVER (ORDER BY sequence_no) AS start_ms,
         capture_start_ms AS next_start_ms
  FROM stored
)
SELECT sequence_from,sequence_to,start_ms,next_start_ms FROM boundaries WHERE sequence_from<=sequence_to
"""


def validate_capture_counters(sequence: int | None, at_ms: int | None) -> None:
    if sequence is not None and not -1 <= sequence <= MAX_SEQUENCE:
        raise preflight_failed("INVALID_CAPTURE_WATERMARK", "Capture sequence is outside the supported range.")
    if at_ms is not None and not 0 <= at_ms <= MAX_CAPTURE_MS:
        raise preflight_failed("INVALID_CAPTURE_CLOCK", "Capture time is outside the supported range.")


async def gap_summary(conn, session_id, through: int, upto: int) -> tuple[list[int], bool]:
    if upto <= through:
        return [], False
    rows = await conn.fetch(HOLES_SQL + " ORDER BY sequence_from LIMIT $4", session_id, through, upto, ACK_GAP_LIMIT+1)
    gaps = []
    truncated = False
    for r in rows:
        remaining = ACK_GAP_LIMIT - len(gaps)
        count = r["sequence_to"] - r["sequence_from"] + 1
        gaps.extend(range(r["sequence_from"], r["sequence_from"] + min(remaining, count)))
        if count > remaining:
            truncated = True
            break
    return gaps, truncated


async def contiguous_through(conn, session_id, start: int, upto: int) -> int:
    # A single ordered pass avoids both numeric-span expansion and correlated per-row RLS
    # probes. This remains predictable before ANALYZE has seen a large offline upload batch.
    return int(await conn.fetchval(
        "SELECT COALESCE(min(sequence_from)-1,$3::bigint) FROM (" + HOLES_SQL + ") holes",
        session_id, start-1, upto))
