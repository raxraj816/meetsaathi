"""Evidence assembly and citation verification.

Evidence handed to the model gets short opaque handles (E1, E2, ...) mapped server-side to
(utterance_id, revision). The model can only cite handles; anything else is discarded. A citation is
returned to clients only if it resolves to an utterance revision the caller was authorized to read."""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field

import asyncpg


async def evidence_current(conn: asyncpg.Connection, evidence: "EvidenceSet") -> bool:
    """Revalidate after inference and lock source sessions against concurrent deletion until commit.

    Model output must not recreate deleted content or treat a corrected revision as current. A caller
    may safely retry inference with freshly authorized evidence when this returns false.
    """
    sessions = sorted({item.session_id for item in evidence.items if item.session_id}, key=str)
    if sessions:
        visible = await conn.fetch("SELECT session_id FROM sessions WHERE session_id=ANY($1::uuid[]) AND deleted_at IS NULL"
                                   " ORDER BY session_id FOR UPDATE", sessions)
        if len(visible) != len(sessions):
            return False
    for item in evidence.items:
        if item.kind == "UTTERANCE":
            revision = await conn.fetchval("SELECT current_revision FROM utterances WHERE utterance_id=$1 FOR UPDATE", item.ref_id)
        elif item.kind in ("NOTE", "CLAIM"):
            revision = await conn.fetchval("SELECT version::int FROM claims WHERE claim_id=$1 AND memory_state<>'DELETED' FOR UPDATE", item.ref_id)
        else:
            continue
        if revision != item.revision:
            return False
    return True


@dataclass
class EvidenceItem:
    handle: str
    kind: str  # UTTERANCE | NOTE | CLAIM | MOCK_TURN
    ref_id: uuid.UUID
    revision: int
    session_id: uuid.UUID | None
    session_title: str | None
    session_date: str | None
    start_ms: int | None
    end_ms: int | None
    speaker: str | None
    speaker_verified: bool
    speaker_confidence: float | None
    text: str
    is_final: bool
    provenance: str
    overlap: bool = False
    asr_confidence: float | None = None

    def for_model(self) -> dict:
        d = {"id": self.handle, "source": self.provenance, "text": self.text}
        if self.kind == "UTTERANCE":
            d |= {"t": f"{(self.start_ms or 0) // 60000:02d}:{((self.start_ms or 0) // 1000) % 60:02d}",
                  "speaker": self.speaker or "Unassigned", "speaker_verified": self.speaker_verified,
                  "provisional": not self.is_final}
            if self.overlap:
                d["overlapping_speech"] = True
            if self.asr_confidence is not None and self.asr_confidence < 0.5:
                d["low_confidence_transcript"] = True
        if self.session_title:
            d["session"] = self.session_title
        if self.session_date:
            d["date"] = self.session_date
        return d

    def citation(self) -> dict:
        if self.kind == "UTTERANCE":
            return {"utterance_id": str(self.ref_id), "revision": self.revision, "start_ms": int(self.start_ms or 0),
                    "end_ms": int(self.end_ms or 0), "speaker_alias": self.speaker, "speaker_verified": self.speaker_verified,
                    "speaker_confidence": self.speaker_confidence, "session_id": str(self.session_id) if self.session_id else None,
                    "session_title": self.session_title, "session_date": self.session_date,
                    "is_final": self.is_final, "source_kind": "RECORDED"}
        return {"claim_id": str(self.ref_id), "source_kind": self.provenance, "session_id": str(self.session_id) if self.session_id else None,
                "session_title": self.session_title, "session_date": self.session_date, "text": self.text[:280]}


@dataclass
class EvidenceSet:
    items: list[EvidenceItem] = field(default_factory=list)

    def add(self, **kw) -> EvidenceItem:
        item = EvidenceItem(handle=f"E{len(self.items) + 1}", **kw)
        self.items.append(item)
        return item

    def by_handle(self) -> dict[str, EvidenceItem]:
        return {i.handle: i for i in self.items}

    def resolve(self, handles: list[str] | None) -> list[EvidenceItem]:
        m = self.by_handle()
        seen, out = set(), []
        for h in handles or []:
            h = str(h).strip()
            if h in m and h not in seen:
                seen.add(h)
                out.append(m[h])
        return out

    def model_view(self) -> list[dict]:
        return [i.for_model() for i in self.items]


UTTERANCE_SQL = """
SELECT u.utterance_id, r.revision, r.session_id, r.start_ms, r.end_ms, r.transcript, r.is_final, r.provenance::text AS provenance,
       r.overlap, r.asr_confidence, r.speaker_confidence, sp.alias, sp.user_verified_label, s.title, s.created_at
FROM utterances u
JOIN utterance_revisions r ON r.utterance_id=u.utterance_id AND r.revision=u.current_revision
JOIN sessions s ON s.session_id=u.session_id AND s.deleted_at IS NULL
LEFT JOIN session_speakers sp ON sp.speaker_alias_id=r.speaker_alias_id
"""


def add_utterance_rows(ev: EvidenceSet, rows) -> None:
    for r in rows:
        verified = r["user_verified_label"] is not None
        ev.add(kind="UTTERANCE", ref_id=r["utterance_id"], revision=r["revision"], session_id=r["session_id"],
               session_title=r["title"], session_date=r["created_at"].date().isoformat(), start_ms=r["start_ms"],
               end_ms=r["end_ms"], speaker=(r["user_verified_label"] or r["alias"]), speaker_verified=verified,
               speaker_confidence=r["speaker_confidence"], text=r["transcript"], is_final=r["is_final"],
               provenance=r["provenance"], overlap=r["overlap"], asr_confidence=r["asr_confidence"])


async def recent_utterances(conn: asyncpg.Connection, session_id: uuid.UUID, *, since_ms: int | None = None,
                            limit: int = 80) -> EvidenceSet:
    ev = EvidenceSet()
    if since_ms is None:
        rows = await conn.fetch(UTTERANCE_SQL + " WHERE u.session_id=$1 ORDER BY r.start_ms DESC LIMIT $2", session_id, limit)
    else:
        rows = await conn.fetch(UTTERANCE_SQL + " WHERE u.session_id=$1 AND r.end_ms >= $2 ORDER BY r.start_ms DESC LIMIT $3",
                                session_id, since_ms, limit)
    add_utterance_rows(ev, list(reversed(rows)))
    return ev


def add_claim_rows(ev: EvidenceSet, rows) -> None:
    for r in rows:
        ev.add(kind="CLAIM", ref_id=r["claim_id"], revision=int(r.get("version", 1) if hasattr(r, "get") else 1),
               session_id=r["session_id"], session_title=r.get("title") if hasattr(r, "get") else None,
               session_date=r["created_at"].date().isoformat(), start_ms=r["time_start_ms"], end_ms=r["time_end_ms"],
               speaker=None, speaker_verified=False, speaker_confidence=None,
               text=f"[{r['claim_kind']}] {r['text_value']}", is_final=True, provenance=r["provenance"])
