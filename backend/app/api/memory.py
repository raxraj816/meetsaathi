"""Spaces, projects, memories, cross-session Ask, decisions, briefs, exports, shares, deletion status."""
from __future__ import annotations

import asyncio
import datetime as dt
import uuid
from typing import Literal

from fastapi import APIRouter, Depends, Header, Query, Request
from fastapi.responses import Response
from pydantic import BaseModel, Field

from ..config import get_settings
from ..db import db
from ..domain import ops
from ..errors import ApiError, not_found, space_denied
from ..intelligence.ask import ask as run_ask, history_with_staleness
from ..memory import deletion, service as mem, sharing
from ..memory.retrieval import keyword_query, resolve_scope
from ..packs import meeting
from ..storage import get_store
from .deps import CurrentUser, current_user, idempotent, require_recent_auth

router = APIRouter(prefix="/v1", tags=["memory"])


class SpaceIn(BaseModel):
    name: str = Field(min_length=1, max_length=60)


class ProjectIn(BaseModel):
    space_id: uuid.UUID
    kind: Literal["PROJECT", "COURSE", "INTERVIEW_GOAL"]
    title: str = Field(min_length=1, max_length=160)
    metadata: dict = {}


class ProjectPatch(BaseModel):
    title: str | None = Field(default=None, max_length=160)
    metadata: dict | None = None
    expected_version: int


PROJECT_META_KEYS = {"COURSE": {"term", "instructor_label", "language", "syllabus_text", "preset"},
                     "INTERVIEW_GOAL": {"company", "stage", "interview_date", "language", "coding_language", "jd_text", "experience_notes"},
                     "PROJECT": {"description"}}


def _check_meta(kind: str, meta: dict) -> dict:
    unknown = set(meta) - PROJECT_META_KEYS[kind]
    if unknown:
        raise ApiError(422, "UNKNOWN_FIELDS", "Some fields aren't supported.", details={"fields": sorted(unknown)})
    for k, v in meta.items():
        if not isinstance(v, (str, int, float, bool)) or (isinstance(v, str) and len(v) > 20000):
            raise ApiError(422, "INVALID_FIELD", f"{k} is invalid.")
    return meta


@router.get("/spaces")
async def list_spaces(user: CurrentUser = Depends(current_user)):
    async with db.user_tx(user.user_id) as conn:
        rows = await conn.fetch("SELECT s.space_id, s.name, s.kind, m.role, s.created_at FROM spaces s JOIN space_memberships m"
                                " ON m.space_id=s.space_id AND m.user_id=$1 WHERE s.deleted_at IS NULL ORDER BY s.created_at", user.user_id)
    return {"items": [dict(r) for r in rows]}


@router.post("/spaces", status_code=201)
async def create_space(body: SpaceIn, user: CurrentUser = Depends(current_user)):
    async with db.user_tx(user.user_id) as conn:
        sid = await conn.fetchval("INSERT INTO spaces(tenant_id,name,kind,created_by) VALUES ($1,$2,'CUSTOM',$3) RETURNING space_id",
                                  user.tenant_id, body.name, user.user_id)
        await conn.execute("INSERT INTO space_memberships(tenant_id,space_id,user_id,role) VALUES ($1,$2,$3,'OWNER')", user.tenant_id, sid, user.user_id)
    return {"space_id": sid, "name": body.name, "kind": "CUSTOM", "role": "OWNER"}


@router.delete("/spaces/{space_id}", status_code=202)
async def delete_space(space_id: uuid.UUID, user: CurrentUser = Depends(current_user)):
    require_recent_auth(user, get_settings().reauth_window_s)
    async with db.user_tx(user.user_id) as conn:
        sp = await conn.fetchrow("SELECT * FROM spaces WHERE space_id=$1 AND deleted_at IS NULL", space_id)
        if sp is None:
            raise not_found("space")
        return await deletion.request_space_deletion(conn, user, dict(sp))


@router.get("/projects")
async def list_projects(user: CurrentUser = Depends(current_user), space_id: uuid.UUID | None = None,
                        kind: Literal["PROJECT", "COURSE", "INTERVIEW_GOAL"] | None = None):
    async with db.user_tx(user.user_id) as conn:
        sql = ("SELECT p.project_id, p.space_id, p.kind, p.title, p.metadata, p.version, p.created_at, p.updated_at,"
               " (SELECT max(s.created_at) FROM sessions s WHERE s.project_id=p.project_id AND s.deleted_at IS NULL) AS last_session_at"
               " FROM projects p WHERE p.deleted_at IS NULL")
        args: list = []
        if space_id:
            args.append(space_id)
            sql += f" AND p.space_id=${len(args)}"
        if kind:
            args.append(kind)
            sql += f" AND p.kind=${len(args)}"
        rows = await conn.fetch(sql + " ORDER BY COALESCE((SELECT max(s.created_at) FROM sessions s WHERE s.project_id=p.project_id), p.created_at) DESC", *args)
    items = []
    for r in rows:
        d = dict(r)
        if d["kind"] == "INTERVIEW_GOAL" and d["metadata"].get("jd_text"):
            d["metadata"] = d["metadata"] | {"jd_text_chars": len(d["metadata"]["jd_text"])}
        items.append(d)
    return {"items": items}


@router.post("/projects", status_code=201)
async def create_project(body: ProjectIn, user: CurrentUser = Depends(current_user)):
    meta = _check_meta(body.kind, body.metadata)
    async with db.user_tx(user.user_id) as conn:
        sp = await conn.fetchrow("SELECT tenant_id FROM spaces WHERE space_id=$1 AND deleted_at IS NULL", body.space_id)
        if sp is None or not await conn.fetchval("SELECT may_write_space($1,$2)", sp["tenant_id"], body.space_id):
            raise space_denied()
        row = await conn.fetchrow("INSERT INTO projects(tenant_id,space_id,kind,title,metadata,created_by) VALUES ($1,$2,$3,$4,$5,$6) RETURNING *",
                                  sp["tenant_id"], body.space_id, body.kind, body.title, meta, user.user_id)
    return dict(row)


@router.get("/projects/{project_id}")
async def get_project(project_id: uuid.UUID, user: CurrentUser = Depends(current_user)):
    async with db.user_tx(user.user_id) as conn:
        p = await conn.fetchrow("SELECT * FROM projects WHERE project_id=$1 AND deleted_at IS NULL", project_id)
        if p is None:
            raise not_found("project")
        sessions = await conn.fetch("SELECT session_id, title, context, state, created_at, source_watermark_ms FROM sessions"
                                    " WHERE project_id=$1 AND deleted_at IS NULL ORDER BY created_at DESC", project_id)
        mocks = await conn.fetch("SELECT mock_id, topic, difficulty, state, created_at, finished_at FROM interview_mocks WHERE goal_id=$1"
                                 " ORDER BY created_at DESC", project_id)
    return dict(p) | {"sessions": [dict(s) for s in sessions], "mocks": [dict(m) for m in mocks]}


@router.patch("/projects/{project_id}")
async def patch_project(project_id: uuid.UUID, body: ProjectPatch, user: CurrentUser = Depends(current_user)):
    async with db.user_tx(user.user_id) as conn:
        p = await conn.fetchrow("SELECT * FROM projects WHERE project_id=$1 AND deleted_at IS NULL FOR UPDATE", project_id)
        if p is None:
            raise not_found("project")
        if p["version"] != body.expected_version:
            raise ApiError(409, "VERSION_CONFLICT", "This changed on another device. Review and try again.", details={"current_version": p["version"]})
        meta = p["metadata"] | _check_meta(p["kind"], body.metadata or {})
        row = await conn.fetchrow("UPDATE projects SET title=COALESCE($2,title), metadata=$3, version=version+1, updated_at=now()"
                                  " WHERE project_id=$1 RETURNING *", project_id, body.title, meta)
        if body.metadata and "jd_text" in body.metadata:
            # Edited job description: coaching context refreshes from the new text on the next practice turn (INT-008).
            await ops.audit(conn, tenant_id=p["tenant_id"], user_id=user.user_id, action="goal.context_updated", target_kind="project",
                            target_id=project_id)
    return dict(row)


@router.delete("/projects/{project_id}", status_code=202)
async def delete_project(project_id: uuid.UUID, user: CurrentUser = Depends(current_user)):
    async with db.user_tx(user.user_id) as conn:
        p = await conn.fetchrow("SELECT * FROM projects WHERE project_id=$1 AND deleted_at IS NULL", project_id)
        if p is None:
            raise not_found("project")
        sessions = await conn.fetch("SELECT * FROM sessions WHERE project_id=$1 AND deleted_at IS NULL", project_id)
        out = []
        for s in sessions:
            out.append(await deletion.request_session_deletion(conn, user, dict(s)))
        async with deletion.tombstoning(conn):
            await conn.execute("UPDATE claims SET memory_state='DELETED' WHERE project_id=$1 AND memory_state<>'DELETED'", project_id)
        await conn.execute("DELETE FROM review_schedule WHERE project_id=$1", project_id)
        await conn.execute("UPDATE practice_items SET state='REMOVED' WHERE project_id=$1", project_id)
        await conn.execute("UPDATE projects SET deleted_at=now(), metadata='{}'::jsonb WHERE project_id=$1", project_id)
    return {"status": "REQUESTED", "session_deletions": out, "notice": deletion.BACKUP_NOTICE}


@router.get("/memories")
async def search_memories(user: CurrentUser = Depends(current_user), space_id: uuid.UUID = Query(...), q: str | None = None,
                          kind: str | None = None, state: Literal["APPROVED", "PENDING_REVIEW", "INVALIDATED", "ALL"] = "APPROVED",
                          project_id: uuid.UUID | None = None, limit: int = Query(default=50, le=200)):
    async with db.user_tx(user.user_id) as conn:
        sp = await conn.fetchrow("SELECT tenant_id FROM spaces WHERE space_id=$1 AND deleted_at IS NULL", space_id)
        if sp is None or not await conn.fetchval("SELECT may_read_space($1,$2)", sp["tenant_id"], space_id):
            raise space_denied()  # ACL before retrieval; no metadata about other spaces leaks (UNI-005)
        sql = ("SELECT c.claim_id, c.space_id, c.session_id, c.project_id, c.claim_kind, c.text_value, c.provenance::text AS provenance,"
               " c.memory_state::text AS memory_state, c.decision_status::text AS decision_status, c.owner_label, c.owner_confirmed,"
               " c.created_at, c.invalidated_at, c.invalidation_reason, s.title AS session_title, s.created_at AS session_date"
               " FROM claims c LEFT JOIN sessions s ON s.session_id=c.session_id WHERE c.space_id=$1 AND (s.session_id IS NULL OR s.deleted_at IS NULL)")
        args: list = [space_id]
        if state != "ALL":
            args.append(state)
            sql += f" AND c.memory_state=${len(args)}::memory_status"
        else:
            sql += " AND c.memory_state<>'DELETED'"
        if kind:
            args.append(kind)
            sql += f" AND c.claim_kind=${len(args)}"
        if project_id:
            args.append(project_id)
            sql += f" AND c.project_id=${len(args)}"
        tsq = keyword_query(q) if q else None
        if tsq:
            args.append(tsq)
            sql += f" AND c.search @@ to_tsquery('simple', ${len(args)})"
        args.append(limit)
        rows = await conn.fetch(sql + f" ORDER BY c.created_at DESC LIMIT ${len(args)}", *args)
        sessions = []
        if q and tsq:
            sessions = await conn.fetch(
                "SELECT DISTINCT s.session_id, s.title, s.context, s.created_at FROM utterance_revisions r JOIN utterances u ON u.utterance_id=r.utterance_id"
                " AND u.current_revision=r.revision JOIN sessions s ON s.session_id=u.session_id AND s.deleted_at IS NULL"
                " WHERE s.space_id=$1 AND r.search @@ to_tsquery('simple', $2) LIMIT 20", space_id, tsq)
    label = {"RECORDED": "From conversation", "USER_NOTE": "My note", "USER_RECOLLECTION": "User recollection",
             "AI_ANALYSIS": "MeetSaathi analysis", "AI_SIMULATION": "Practice simulation", "IMPORTED": "Imported material"}
    return {"items": [dict(r) | {"provenance_label": label[r["provenance"]]} for r in rows],
            "matching_sessions": [dict(s) for s in sessions], "scope": {"space_id": space_id}}


class RetainIn(BaseModel):
    space_id: uuid.UUID
    claim_ids: list[uuid.UUID] = Field(min_length=1, max_length=200)


@router.post("/memories/retain", status_code=202)
async def retain(body: RetainIn, request: Request, user: CurrentUser = Depends(current_user), idempotency_key: str | None = Header(default=None)):
    async def fn(conn):
        return 202, await mem.retain(conn, user, body.space_id, body.claim_ids)
    return await idempotent(request, user, idempotency_key, body.model_dump(), fn)


@router.get("/memories/{claim_id}")
async def get_memory(claim_id: uuid.UUID, user: CurrentUser = Depends(current_user)):
    async with db.user_tx(user.user_id) as conn:
        return await mem.claim_view(conn, claim_id)


class ClaimPatch(BaseModel):
    text_value: str | None = Field(default=None, max_length=8000)
    expected_version: int
    exclude_from_suggestions: bool | None = None


@router.patch("/memories/{claim_id}")
async def edit_memory(claim_id: uuid.UUID, body: ClaimPatch, user: CurrentUser = Depends(current_user)):
    async with db.user_tx(user.user_id) as conn:
        c = await conn.fetchrow("SELECT * FROM claims WHERE claim_id=$1 FOR UPDATE", claim_id)
        if c is None:
            raise not_found("memory")
        if c["version"] != body.expected_version:
            raise ApiError(409, "VERSION_CONFLICT", "This memory changed on another device. Review both versions.",
                           details={"current_version": c["version"], "current_text": c["text_value"]})
        if body.text_value is not None and c["provenance"] == "RECORDED":
            raise ApiError(422, "EDIT_SOURCE_INSTEAD", "Recorded items are corrected by fixing the transcript or speaker, keeping provenance.")
        await conn.execute("UPDATE claims SET text_value=COALESCE($2,text_value), exclude_from_suggestions=COALESCE($3,exclude_from_suggestions),"
                           " version=version+1, updated_at=now() WHERE claim_id=$1", claim_id, body.text_value, body.exclude_from_suggestions)
        await conn.execute("DELETE FROM embeddings WHERE owner_kind='CLAIM' AND owner_id=$1", claim_id)
        return await mem.claim_view(conn, claim_id)


@router.delete("/memories/{claim_id}", status_code=202)
async def delete_memory(claim_id: uuid.UUID, user: CurrentUser = Depends(current_user)):
    async with db.user_tx(user.user_id) as conn:
        c = await conn.fetchrow("SELECT * FROM claims WHERE claim_id=$1", claim_id)
        if c is None:
            raise not_found("memory")
        return await deletion.request_claim_deletion(conn, user, dict(c))


class DecisionIn(BaseModel):
    to_state: Literal["PROPOSED", "DISCUSSED", "ACCEPTED", "REJECTED", "DEFERRED", "SUPERSEDED", "UNRESOLVED"]
    utterance_id: uuid.UUID | None = None
    note: str | None = Field(default=None, max_length=300)
    expected_version: int


@router.post("/memories/{claim_id}/decision")
async def decision(claim_id: uuid.UUID, body: DecisionIn, user: CurrentUser = Depends(current_user)):
    async with db.user_tx(user.user_id) as conn:
        c = await conn.fetchrow("SELECT * FROM claims WHERE claim_id=$1 FOR UPDATE", claim_id)
        if c is None:
            raise not_found("memory")
        return await mem.update_decision(conn, user, dict(c), to_state=body.to_state, utterance_id=body.utterance_id, note=body.note,
                                         expected_version=body.expected_version)


class OwnerIn(BaseModel):
    owner_label: str | None = Field(default=None, max_length=120)
    due_text: str | None = Field(default=None, max_length=120)
    expected_version: int


@router.post("/memories/{claim_id}/owner")
async def owner(claim_id: uuid.UUID, body: OwnerIn, user: CurrentUser = Depends(current_user)):
    async with db.user_tx(user.user_id) as conn:
        c = await conn.fetchrow("SELECT * FROM claims WHERE claim_id=$1 FOR UPDATE", claim_id)
        if c is None:
            raise not_found("memory")
        return await mem.confirm_owner(conn, user, dict(c), body.owner_label, body.due_text, body.expected_version)


class GlobalAskIn(BaseModel):
    question: str = Field(min_length=1, max_length=4000)
    mode: Literal["REMEMBER", "THINK", "LEARN", "PREPARE"]
    scope: Literal["SELECTED_SPACE", "SELECTED_PROJECT", "GENERAL"]
    scope_id: uuid.UUID | None = None


@router.post("/ask")
async def global_ask(body: GlobalAskIn, user: CurrentUser = Depends(current_user)):
    return await run_ask(user, session=None, question=body.question, mode=body.mode, scope=body.scope, scope_id=body.scope_id)


@router.get("/ask/history")
async def global_ask_history(user: CurrentUser = Depends(current_user)):
    async with db.user_tx(user.user_id) as conn:
        return {"items": await history_with_staleness(conn, user, None)}


@router.get("/decisions")
async def decisions(user: CurrentUser = Depends(current_user), scope: Literal["SELECTED_SPACE", "SELECTED_PROJECT"] = "SELECTED_PROJECT",
                    scope_id: uuid.UUID = Query(...)):
    async with db.user_tx(user.user_id) as conn:
        sc = await resolve_scope(conn, scope=scope, scope_id=scope_id, session=None)
        return {"items": await meeting.decision_timeline(conn, sc), "scope": sc.describe()}


@router.get("/briefs")
async def brief(user: CurrentUser = Depends(current_user), scope: Literal["SELECTED_SPACE", "SELECTED_PROJECT"] = "SELECTED_PROJECT",
                scope_id: uuid.UUID = Query(...)):
    async with db.user_tx(user.user_id) as conn:
        sc = await resolve_scope(conn, scope=scope, scope_id=scope_id, session=None)
        return await meeting.brief(conn, sc)


class ExportIn(BaseModel):
    session_id: uuid.UUID | None = None
    space_id: uuid.UUID | None = None
    include_verified_names: bool = False


@router.post("/exports", status_code=202)
async def create_export(body: ExportIn, user: CurrentUser = Depends(current_user)):
    require_recent_auth(user, get_settings().reauth_window_s)  # sensitive scope needs re-authentication
    async with db.user_tx(user.user_id) as conn:
        if body.session_id:
            s = await conn.fetchrow("SELECT space_id FROM sessions WHERE session_id=$1 AND deleted_at IS NULL", body.session_id)
            if s is None:
                raise not_found("session")
        if body.space_id:
            ok = await conn.fetchval("SELECT may_read_space(tenant_id,$1) FROM spaces WHERE space_id=$1", body.space_id)
            if not ok:
                raise space_denied()
        scope = {k: (str(v) if isinstance(v, uuid.UUID) else v) for k, v in body.model_dump().items() if v is not None}
        eid = await conn.fetchval("INSERT INTO exports(tenant_id,user_id,scope,status) VALUES ($1,$2,$3,'REQUESTED') RETURNING export_id",
                                  user.tenant_id, user.user_id, scope)
        sp = body.space_id or await conn.fetchval("SELECT space_id FROM space_memberships WHERE user_id=$1 LIMIT 1", user.user_id)
        await ops.enqueue(conn, tenant_id=user.tenant_id, space_id=sp, session_id=None, kind="export.build",
                          payload={"export_id": str(eid)}, key=f"export:{eid}")
    return {"export_id": eid, "status": "REQUESTED"}


@router.get("/exports/{export_id}")
async def get_export(export_id: uuid.UUID, user: CurrentUser = Depends(current_user)):
    async with db.user_tx(user.user_id) as conn:
        e = await conn.fetchrow("SELECT export_id, status, created_at, completed_at, expires_at FROM exports WHERE export_id=$1", export_id)
    if e is None:
        raise not_found("export")
    return dict(e)


@router.get("/exports/{export_id}/download")
async def download_export(export_id: uuid.UUID, user: CurrentUser = Depends(current_user)):
    async with db.user_tx(user.user_id) as conn:
        e = await conn.fetchrow("SELECT * FROM exports WHERE export_id=$1", export_id)
    if e is None or e["status"] != "COMPLETE" or e["expires_at"] is None or e["expires_at"] <= dt.datetime.now(dt.timezone.utc):
        raise not_found("export")
    data = await asyncio.to_thread(get_store().get, e["tenant_id"], e["object_key"])
    return Response(content=data, media_type="application/json",
                    headers={"Content-Disposition": f'attachment; filename="meetsaathi-export-{export_id}.json"', "Cache-Control": "no-store"})


class ShareIn(BaseModel):
    sections: list[str] = ["summary", "decisions", "actions", "questions"]
    redact_identities: bool = True
    claim_ids: list[uuid.UUID] | None = None
    expires_in_hours: int = 72
    confirm: bool = False


@router.post("/sessions/{session_id}/shares")
async def create_share(session_id: uuid.UUID, body: ShareIn, user: CurrentUser = Depends(current_user)):
    async with db.user_tx(user.user_id) as conn:
        s = await conn.fetchrow("SELECT * FROM sessions WHERE session_id=$1 AND deleted_at IS NULL", session_id)
        if s is None or not await conn.fetchval("SELECT may_write_space($1,$2)", s["tenant_id"], s["space_id"]):
            raise not_found("session")
        return await sharing.create_share(conn, user, dict(s), sections=body.sections, redact_identities=body.redact_identities,
                                          claim_ids=body.claim_ids, expires_in_hours=body.expires_in_hours, confirm=body.confirm)


@router.get("/sessions/{session_id}/shares")
async def list_shares(session_id: uuid.UUID, user: CurrentUser = Depends(current_user)):
    async with db.user_tx(user.user_id) as conn:
        rows = await conn.fetch("SELECT share_id, options, expires_at, revoked_at, stale, created_at FROM shares WHERE session_id=$1 ORDER BY created_at DESC",
                                session_id)
    return {"items": [dict(r) for r in rows]}


@router.delete("/shares/{share_id}", status_code=204)
async def revoke_share(share_id: uuid.UUID, user: CurrentUser = Depends(current_user)):
    async with db.user_tx(user.user_id) as conn:
        n = await conn.execute("UPDATE shares SET revoked_at=now() WHERE share_id=$1 AND revoked_at IS NULL", share_id)
        if n == "UPDATE 0" and not await conn.fetchval("SELECT 1 FROM shares WHERE share_id=$1", share_id):
            raise not_found("share")


@router.get("/shared/{token}")
async def read_shared(token: str):
    return await sharing.read_share(token)


@router.get("/deletion-requests/{request_id}")
async def deletion_status(request_id: uuid.UUID, user: CurrentUser = Depends(current_user)):
    async with db.system_tx() as conn:
        r = await conn.fetchrow("SELECT request_id, status, scope_kind, created_at, completed_at, detail FROM deletion_requests"
                                " WHERE request_id=$1 AND requested_by=$2", request_id, user.user_id)
    if r is None:
        raise not_found("deletion request")
    d = dict(r)
    d["message"] = {"REQUESTED": "Deletion is in progress. Some copies may take additional time to expire.",
                    "IN_PROGRESS": "Deletion is in progress. Some copies may take additional time to expire.",
                    "COMPLETE": "Deleted. Backups expire on their published schedule.",
                    "ACTION_REQUIRED": "Deletion needs attention; our team has been notified."}[d["status"]]
    d["detail"] = {k: v for k, v in (d["detail"] or {}).items() if k in ("objects_deleted", "sessions_purged", "reason")}
    return d
