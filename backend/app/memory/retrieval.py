"""Scoped retrieval (master 6.3): authenticated subject -> tenant+space ACL filter BEFORE retrieval ->
structured + lexical (+ optional semantic) search -> rerank -> evidence. Never defaults to all spaces.
Runs on the ms_app role, so Postgres RLS enforces the same boundary a second time."""
from __future__ import annotations

import re
import uuid
from dataclasses import dataclass

import asyncpg

from ..db import vector_literal
from ..errors import ApiError, not_found, space_denied
from ..intelligence.evidence import UTTERANCE_SQL, EvidenceSet, add_utterance_rows
from .embeddings import get_embedder

SCOPES = ("CURRENT_SESSION", "SELECTED_SPACE", "SELECTED_PROJECT", "GENERAL")
STOP = set("""a an and are as at be but by can could did do does for from had has have how i if in into is it its
me my of on or our should so than that the their them then there these they this to us was we were what when where
which who why will with would you your about any all also just like more most much some such tell said say says
decide decided decision""".split()) - {"decide", "decided", "decision"}


@dataclass
class Scope:
    kind: str
    space_id: uuid.UUID | None
    project_id: uuid.UUID | None
    session_id: uuid.UUID | None
    tenant_id: uuid.UUID | None

    def describe(self) -> dict:
        return {"kind": self.kind, "space_id": self.space_id, "project_id": self.project_id, "session_id": self.session_id}


async def resolve_scope(conn: asyncpg.Connection, *, scope: str, scope_id: uuid.UUID | None,
                        session: dict | None) -> Scope:
    if scope not in SCOPES:
        raise ApiError(422, "INVALID_SCOPE", "Choose a retrieval scope.")
    if scope == "CURRENT_SESSION":
        if session is None:
            raise ApiError(422, "SCOPE_REQUIRES_SESSION", "Open a session to ask about it.")
        return Scope(scope, session["space_id"], None, session["session_id"], session["tenant_id"])
    if scope == "GENERAL":
        return Scope(scope, None, None, None, None)
    if scope_id is None:
        raise ApiError(422, "SCOPE_ID_REQUIRED", "Choose which space or project to search.")
    if scope == "SELECTED_SPACE":
        row = await conn.fetchrow("SELECT tenant_id, space_id FROM spaces WHERE space_id=$1 AND deleted_at IS NULL", scope_id)
        if row is None or not await conn.fetchval("SELECT may_read_space($1,$2)", row["tenant_id"], scope_id):
            raise space_denied()
        return Scope(scope, scope_id, None, None, row["tenant_id"])
    row = await conn.fetchrow("SELECT tenant_id, space_id, project_id FROM projects WHERE project_id=$1 AND deleted_at IS NULL", scope_id)
    if row is None or not await conn.fetchval("SELECT may_read_space($1,$2)", row["tenant_id"], row["space_id"]):
        raise space_denied()
    return Scope(scope, row["space_id"], scope_id, None, row["tenant_id"])


def keyword_query(text: str) -> str | None:
    terms = [t for t in re.findall(r"[\w]+", text.lower(), flags=re.UNICODE) if len(t) > 1 and t not in STOP]
    terms = list(dict.fromkeys(terms))[:16]
    if not terms:
        return None
    return " | ".join(re.sub(r"[^\w]", "", t) + ":*" for t in terms if re.sub(r"[^\w]", "", t))


def _scope_filter(scope: Scope, alias: str, first_arg: int) -> tuple[str, list]:
    if scope.kind == "CURRENT_SESSION":
        return f" AND {alias}.session_id = ${first_arg}", [scope.session_id]
    if scope.kind == "SELECTED_PROJECT":
        return (f" AND {alias}.session_id IN (SELECT session_id FROM sessions WHERE project_id = ${first_arg} AND deleted_at IS NULL)",
                [scope.project_id])
    return f" AND {alias}.space_id = ${first_arg}", [scope.space_id]


async def search(conn: asyncpg.Connection, scope: Scope, query: str, *, limit: int = 24, include_recent: int = 0,
                 final_only: bool = False) -> EvidenceSet:
    ev = EvidenceSet()
    if scope.kind == "GENERAL":
        return ev
    seen: set[tuple] = set()
    tsq = keyword_query(query)
    final_clause = " AND r.is_final" if final_only else ""
    rows = []
    if tsq:
        f, a = _scope_filter(scope, "u", 2)
        rows = await conn.fetch(UTTERANCE_SQL + " WHERE r.search @@ to_tsquery('simple', $1)" + f + final_clause +
                                " ORDER BY ts_rank(r.search, to_tsquery('simple', $1)) DESC, r.start_ms LIMIT " + str(limit), tsq, *a)
    if include_recent and scope.session_id:
        recent = await conn.fetch(UTTERANCE_SQL + " WHERE u.session_id=$1" + final_clause + " ORDER BY r.start_ms DESC LIMIT $2",
                                  scope.session_id, include_recent)
        rows = list(rows) + list(reversed(recent))
    emb = get_embedder()
    if emb.available() and query.strip():
        try:
            vec = (await emb.embed([query]))[0]
            f, a = _scope_filter(scope, "e", 3)
            sem = await conn.fetch(
                "SELECT e.owner_id FROM embeddings e WHERE e.owner_kind='UTTERANCE' AND e.embedding_model=$2" + f +
                " ORDER BY e.embedding <=> $1::vector LIMIT 12", vector_literal(vec), emb.model, *a)
            ids = [r["owner_id"] for r in sem]
            if ids:
                rows = list(rows) + list(await conn.fetch(UTTERANCE_SQL + " WHERE u.utterance_id = ANY($1::uuid[])" + final_clause, ids))
        except Exception:  # semantic retrieval is an enhancement; lexical results stand on their own
            pass
    uniq = []
    for r in rows:
        k = (r["utterance_id"], r["revision"])
        if k not in seen:
            seen.add(k)
            uniq.append(r)
    uniq.sort(key=lambda r: (r["created_at"], r["start_ms"]))
    add_utterance_rows(ev, uniq[: limit + include_recent])
    # Notes, recollections and approved memories (claims) in the same scope.
    f, a = _scope_filter(scope, "c", 2 if tsq else 1)
    claim_sql = ("SELECT c.claim_id, c.session_id, c.claim_kind, c.text_value, c.provenance::text AS provenance, c.time_start_ms,"
                 " c.time_end_ms, c.created_at, c.version, s.title FROM claims c LEFT JOIN sessions s ON s.session_id=c.session_id"
                 " WHERE c.memory_state IN ('APPROVED','PENDING_REVIEW') AND c.invalidated_at IS NULL"
                 " AND (s.session_id IS NULL OR s.deleted_at IS NULL)")
    if scope.kind != "CURRENT_SESSION":
        claim_sql += " AND (c.memory_state='APPROVED' OR c.claim_kind IN ('NOTE','RECOLLECTION')) AND NOT c.exclude_from_suggestions"
    if tsq:
        crow = await conn.fetch(claim_sql + " AND c.search @@ to_tsquery('simple', $1)" + f + " ORDER BY c.created_at LIMIT 12", tsq, *a)
    else:
        crow = []
    if scope.kind == "CURRENT_SESSION":
        notes = await conn.fetch(claim_sql + " AND c.claim_kind IN ('NOTE','RECOLLECTION','BOOKMARK')" + _scope_filter(scope, "c", 1)[0] +
                                 " ORDER BY c.created_at LIMIT 20", scope.session_id)
        crow = list(crow) + [n for n in notes if n["claim_id"] not in {c["claim_id"] for c in crow}]
    for r in crow:
        ev.add(kind="CLAIM", ref_id=r["claim_id"], revision=int(r["version"]), session_id=r["session_id"], session_title=r["title"],
               session_date=r["created_at"].date().isoformat(), start_ms=r["time_start_ms"], end_ms=r["time_end_ms"],
               speaker=None, speaker_verified=False, speaker_confidence=None,
               text=f"[{r['claim_kind']}] {r['text_value']}", is_final=True, provenance=r["provenance"])
    return ev


async def load_session_readable(conn, session_id: uuid.UUID) -> dict:
    row = await conn.fetchrow("SELECT * FROM sessions WHERE session_id=$1 AND deleted_at IS NULL", session_id)
    if row is None:
        raise not_found("session")
    return dict(row)
