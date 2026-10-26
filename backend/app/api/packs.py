"""Context-pack endpoints: Learning studio and Interview practice. Session-bound features (Explain this,
recap, review-to-keep) live under /v1/sessions."""
from __future__ import annotations

import uuid
from typing import Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from ..db import db
from ..domain.policy import POLICIES
from ..errors import not_found
from ..packs import interview, learning
from .deps import CurrentUser, current_user

router = APIRouter(prefix="/v1", tags=["context-packs"])


@router.get("/context-packs")
async def context_packs():
    return {"items": [{"context": p.context, "presets": list(p.presets), "sensitive_presets": list(p.sensitive_presets),
                       "allowed_insight_kinds": list(p.allowed_kinds), "default_retention": p.default_retention,
                       "max_live_words": p.max_live_words, "policy_version": p.version,
                       "budgets": {k: {"cooldown_s": b.cooldown_s, "max_per_15_min": b.max_per_15_min} for k, b in p.budgets.items()}}
                      for p in POLICIES.values()],
            "defaults": {"assistance_mode": "LISTENER", "proactive_intensity": "QUIET", "output_mode": "TEXT",
                         "retrieval_scope": "CURRENT_SESSION"}}


class PracticeIn(BaseModel):
    session_id: uuid.UUID | None = None
    project_id: uuid.UUID | None = None
    count: int = Field(default=5, ge=1, le=8)


@router.post("/learning/practice", status_code=201)
async def practice(body: PracticeIn, user: CurrentUser = Depends(current_user)):
    return await learning.generate_practice(user, session_id=body.session_id, project_id=body.project_id, count=body.count)


@router.get("/learning/practice")
async def list_practice(user: CurrentUser = Depends(current_user), project_id: uuid.UUID | None = None, session_id: uuid.UUID | None = None):
    async with db.user_tx(user.user_id) as conn:
        rows = await conn.fetch("SELECT item_id, concept, prompt, kind, source_kind, state, created_at,"
                                " (SELECT verdict FROM practice_attempts a WHERE a.item_id=p.item_id ORDER BY created_at DESC LIMIT 1) AS last_verdict"
                                " FROM practice_items p WHERE state<>'REMOVED' AND ($1::uuid IS NULL OR project_id=$1) AND ($2::uuid IS NULL OR session_id=$2)"
                                " ORDER BY created_at DESC LIMIT 100", project_id, session_id)
    return {"items": [dict(r) for r in rows]}


class AttemptIn(BaseModel):
    response: str = Field(min_length=1, max_length=8000)


@router.post("/learning/practice/{item_id}/attempts", status_code=201)
async def attempt(item_id: uuid.UUID, body: AttemptIn, user: CurrentUser = Depends(current_user)):
    return await learning.attempt(user, item_id, body.response)


@router.get("/learning/reviews")
async def reviews(user: CurrentUser = Depends(current_user), space_id: uuid.UUID | None = None):
    async with db.user_tx(user.user_id) as conn:
        return {"items": await learning.due_reviews(conn, user, space_id), "policy_version": learning.REVIEW_POLICY_VERSION,
                "note": "Reviews are suggestions you can snooze, reschedule or remove. There are no streaks."}


class ReviewActionIn(BaseModel):
    space_id: uuid.UUID
    action: Literal["SNOOZE", "DIFFICULT", "RESET", "REMOVE", "RESCHEDULE"]
    days: int | None = Field(default=None, ge=0, le=365)


@router.post("/learning/reviews/{concept_key}")
async def review_action(concept_key: str, body: ReviewActionIn, user: CurrentUser = Depends(current_user)):
    async with db.user_tx(user.user_id) as conn:
        return await learning.update_review(conn, user, body.space_id, concept_key, action=body.action, days=body.days)


class ConceptIn(BaseModel):
    space_id: uuid.UUID
    project_id: uuid.UUID | None = None
    concept: str = Field(min_length=1, max_length=200)
    difficult: bool = True


@router.post("/learning/reviews", status_code=201)
async def mark_concept(body: ConceptIn, user: CurrentUser = Depends(current_user)):
    async with db.user_tx(user.user_id) as conn:
        sp = await conn.fetchrow("SELECT tenant_id FROM spaces WHERE space_id=$1", body.space_id)
        if sp is None or not await conn.fetchval("SELECT may_write_space($1,$2)", sp["tenant_id"], body.space_id):
            raise not_found("space")
        await learning.touch_review(conn, user, tenant_id=sp["tenant_id"], space_id=body.space_id, project_id=body.project_id,
                                    concept=body.concept, lineage="HEARD", difficult=body.difficult)
        return {"concept_key": learning.concept_key(body.concept)}


class MockIn(BaseModel):
    space_id: uuid.UUID
    goal_id: uuid.UUID | None = None
    topic: str
    difficulty: str = "Challenging"
    hints_allowed: bool = True
    feedback_timing: Literal["AFTER_ROUND", "ON_DEMAND"] = "AFTER_ROUND"
    max_questions: int = Field(default=3, ge=1, le=6)


@router.post("/interview/mocks", status_code=201)
async def start_mock(body: MockIn, user: CurrentUser = Depends(current_user)):
    return await interview.start_mock(user, space_id=body.space_id, goal_id=body.goal_id, topic=body.topic, difficulty=body.difficulty,
                                      hints_allowed=body.hints_allowed, feedback_timing=body.feedback_timing, max_questions=body.max_questions)


@router.get("/interview/mocks")
async def list_mocks(user: CurrentUser = Depends(current_user), goal_id: uuid.UUID | None = None):
    async with db.user_tx(user.user_id) as conn:
        rows = await conn.fetch("SELECT mock_id, space_id, goal_id, topic, difficulty, state, created_at, finished_at, parent_mock_id,"
                                " (debrief->>'status') AS debrief_status FROM interview_mocks WHERE ($1::uuid IS NULL OR goal_id=$1)"
                                " ORDER BY created_at DESC LIMIT 100", goal_id)
    return {"items": [dict(r) for r in rows]}


@router.get("/interview/mocks/{mock_id}")
async def get_mock(mock_id: uuid.UUID, user: CurrentUser = Depends(current_user)):
    async with db.user_tx(user.user_id) as conn:
        m = await conn.fetchrow("SELECT * FROM interview_mocks WHERE mock_id=$1", mock_id)
        if m is None:
            raise not_found("practice interview")
        turns = await conn.fetch("SELECT turn_id, seq, role, kind, text_value, provenance::text AS provenance, created_at FROM mock_turns"
                                 " WHERE mock_id=$1 ORDER BY seq", mock_id)
    return {"mock": dict(m), "turns": [dict(t) for t in turns]}


class MockActionIn(BaseModel):
    action: Literal["ANSWER", "NEED_TIME", "REPEAT", "HINT", "FINISH"]
    text: str | None = Field(default=None, max_length=12000)


@router.post("/interview/mocks/{mock_id}/turns")
async def mock_turn(mock_id: uuid.UUID, body: MockActionIn, user: CurrentUser = Depends(current_user)):
    return await interview.mock_action(user, mock_id, body.action, body.text)


@router.get("/interview/mocks/{mock_id}/debrief")
async def mock_debrief(mock_id: uuid.UUID, user: CurrentUser = Depends(current_user)):
    return await interview.debrief(user, mock_id)


class RetryIn(BaseModel):
    focus: str = Field(min_length=1, max_length=300)


@router.post("/interview/mocks/{mock_id}/retry", status_code=201)
async def retry(mock_id: uuid.UUID, body: RetryIn, user: CurrentUser = Depends(current_user)):
    return await interview.retry_skill(user, mock_id, body.focus)
