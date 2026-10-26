"""Aligner (master 8.3): joins ASR segments with diarizer turns on the shared capture clock.

* A segment's speaker is the turn with the largest overlap if it covers >= 50% of the segment.
* Two speakers each covering >= 30% => overlap=True; attribution stays provisional with reduced confidence.
* No diarizer / weak coverage => UNASSIGNED (anonymous, never a guessed name).
* Segments inside the app's own TTS playback windows are dropped: MeetSaathi's voice is not a participant.
"""
from __future__ import annotations

from dataclasses import dataclass

from .adapters import AsrSegment, DiarizationResult

UNASSIGNED = "UNASSIGNED"


@dataclass
class AlignedUtterance:
    segment: AsrSegment
    speaker: str
    speaker_confidence: float | None
    overlap: bool


def _ov(a0: int, a1: int, b0: int, b1: int) -> int:
    return max(0, min(a1, b1) - max(a0, b0))


def in_playback(seg: AsrSegment, windows: list[dict]) -> bool:
    dur = max(1, seg.end_ms - seg.start_ms)
    covered = sum(_ov(seg.start_ms, seg.end_ms, int(w["start_ms"]), int(w["end_ms"])) for w in windows)
    return covered / dur >= 0.6


def align(segments: list[AsrSegment], diar: DiarizationResult | None, tts_windows: list[dict]) -> list[AlignedUtterance]:
    out: list[AlignedUtterance] = []
    for seg in segments:
        if in_playback(seg, tts_windows):
            continue
        if diar is None or not diar.turns:
            out.append(AlignedUtterance(seg, UNASSIGNED, None, False))
            continue
        dur = max(1, seg.end_ms - seg.start_ms)
        cover: dict[str, int] = {}
        conf: dict[str, list[float]] = {}
        flagged_overlap = False
        for t in diar.turns:
            o = _ov(seg.start_ms, seg.end_ms, t.start_ms, t.end_ms)
            if o:
                cover[t.speaker] = cover.get(t.speaker, 0) + o
                if t.confidence is not None:
                    conf.setdefault(t.speaker, []).append(float(t.confidence))
                flagged_overlap = flagged_overlap or t.overlap
        if not cover:
            out.append(AlignedUtterance(seg, UNASSIGNED, None, False))
            continue
        ranked = sorted(cover.items(), key=lambda kv: kv[1], reverse=True)
        best, best_cov = ranked[0]
        frac = best_cov / dur
        overlap = flagged_overlap or (len(ranked) > 1 and ranked[1][1] / dur >= 0.3)
        if frac < 0.5:
            out.append(AlignedUtterance(seg, UNASSIGNED, None, overlap))
            continue
        c = sum(conf.get(best, [])) / len(conf[best]) if conf.get(best) else frac
        if overlap:
            c *= 0.6
        out.append(AlignedUtterance(seg, best, round(max(0.0, min(1.0, c)), 3), overlap))
    return out


def speaker_alias(raw: str, known: dict[str, str]) -> str:
    """Map provider speaker ids to stable session-local aliases: Speaker A, Speaker B, ..."""
    if raw == UNASSIGNED:
        return "Unassigned"
    if raw not in known:
        idx = len([k for k in known if k != UNASSIGNED])
        letters = ""
        n = idx
        while True:
            letters = chr(ord("A") + n % 26) + letters
            n = n // 26 - 1
            if n < 0:
                break
        known[raw] = f"Speaker {letters}"
    return known[raw]
