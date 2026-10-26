"""Identity: accounts, tenants, default spaces, device-bound tokens, per-device revocation (master 8.4)."""
from __future__ import annotations

import datetime as dt
import re
import uuid

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from ..config import get_settings
from ..db import db
from ..domain import ops
from ..errors import ApiError, not_found
from ..security.tokens import (hash_opaque, hash_password, issue_access_token, new_refresh_token, verify_password)
from .deps import CurrentUser, current_user, require_recent_auth

router = APIRouter(prefix="/v1", tags=["identity"])

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
DEFAULT_SPACES = (("Personal", "PERSONAL"), ("Work", "WORK"), ("Learning", "LEARNING"))


class DeviceIn(BaseModel):
    platform: str = Field(pattern="^(IOS|ANDROID|DESKTOP_BRIDGE|TEST)$")
    name: str = Field(min_length=1, max_length=80)
    device_id: uuid.UUID | None = None


class RegisterIn(BaseModel):
    email: str = Field(max_length=254)
    password: str = Field(min_length=10, max_length=256)
    display_name: str | None = Field(default=None, max_length=80)
    device: DeviceIn
    residency_region: str | None = None
    # Launch audience is adults (Learning spec 8.4, LC-041). Under-18 use needs a separate governed track, so the
    # pathway is blocked clearly rather than silently collecting a child's data.
    age_confirmed: bool = False


class LoginIn(BaseModel):
    email: str
    password: str
    device: DeviceIn


class RefreshIn(BaseModel):
    refresh_token: str


class ReauthIn(BaseModel):
    password: str


def _tokens(user_id, device_id, refresh_raw, reauth=False) -> dict:
    s = get_settings()
    return {"access_token": issue_access_token(user_id, device_id, reauth=reauth), "token_type": "Bearer",
            "expires_in": s.access_token_ttl_s, "refresh_token": refresh_raw, "device_id": str(device_id),
            "user_id": str(user_id)}


async def _new_device_and_refresh(conn, user_id, device: DeviceIn):
    s = get_settings()
    device_id = None
    if device.device_id:
        device_id = await conn.fetchval("SELECT device_id FROM devices WHERE device_id=$1 AND user_id=$2 AND revoked_at IS NULL",
                                        device.device_id, user_id)
    if device_id is None:
        device_id = await conn.fetchval("INSERT INTO devices(user_id,platform,name) VALUES ($1,$2,$3) RETURNING device_id",
                                        user_id, device.platform, device.name)
    raw, h = new_refresh_token()
    await conn.execute("INSERT INTO refresh_tokens(token_hash,user_id,device_id,expires_at) VALUES ($1,$2,$3,now()+make_interval(secs=>$4))",
                       h, user_id, device_id, float(s.refresh_token_ttl_s))
    return device_id, raw


@router.post("/auth/register", status_code=201)
async def register(body: RegisterIn):
    s = get_settings()
    if not body.age_confirmed:
        raise ApiError(422, "AGE_REQUIREMENT", "MeetSaathi is currently available only to people aged 18 or older.")
    email = body.email.strip().lower()
    if not EMAIL_RE.match(email):
        raise ApiError(422, "INVALID_EMAIL", "Enter a valid email address.")
    region = body.residency_region or s.processing_region
    async with db.system_tx() as conn:
        if await conn.fetchval("SELECT 1 FROM user_credentials WHERE email=$1", email):
            raise ApiError(409, "ACCOUNT_EXISTS", "An account with this email already exists.")
        user_id = uuid.uuid4()
        await conn.execute("INSERT INTO users(user_id,display_name) VALUES ($1,$2)", user_id, body.display_name)
        await conn.execute("INSERT INTO user_credentials(user_id,email,password_hash) VALUES ($1,$2,$3)",
                           user_id, email, hash_password(body.password))
        tenant_id = await conn.fetchval("INSERT INTO tenants(name,residency_region) VALUES ($1,$2) RETURNING tenant_id",
                                        (body.display_name or email.split("@")[0]) + " (personal)", region)
        await conn.execute("INSERT INTO tenant_memberships(tenant_id,user_id,role) VALUES ($1,$2,'OWNER')", tenant_id, user_id)
        for name, kind in DEFAULT_SPACES:
            sid = await conn.fetchval("INSERT INTO spaces(tenant_id,name,kind,created_by) VALUES ($1,$2,$3,$4) RETURNING space_id",
                                      tenant_id, name, kind, user_id)
            await conn.execute("INSERT INTO space_memberships(tenant_id,space_id,user_id,role) VALUES ($1,$2,$3,'OWNER')",
                               tenant_id, sid, user_id)
        await conn.execute("INSERT INTO user_preferences(user_id,prefs) VALUES ($1,$2)", user_id, {})
        device_id, raw = await _new_device_and_refresh(conn, user_id, body.device)
        await ops.audit(conn, tenant_id=tenant_id, user_id=user_id, action="account.registered")
    return _tokens(user_id, device_id, raw)


@router.post("/auth/login")
async def login(body: LoginIn):
    email = body.email.strip().lower()
    async with db.system_tx() as conn:
        row = await conn.fetchrow("SELECT c.user_id, c.password_hash, u.deleted_at FROM user_credentials c JOIN users u USING (user_id)"
                                  " WHERE c.email=$1", email)
        if row is None or row["deleted_at"] is not None or not verify_password(body.password, row["password_hash"]):
            raise ApiError(401, "INVALID_CREDENTIALS", "Email or password is incorrect.")
        device_id, raw = await _new_device_and_refresh(conn, row["user_id"], body.device)
    return _tokens(row["user_id"], device_id, raw)


@router.post("/auth/refresh")
async def refresh(body: RefreshIn):
    s = get_settings()
    h = hash_opaque(body.refresh_token)
    reused = False
    async with db.system_tx() as conn:
        row = await conn.fetchrow("SELECT r.*, d.revoked_at AS device_revoked FROM refresh_tokens r JOIN devices d USING (device_id)"
                                  " WHERE r.token_hash=$1 FOR UPDATE OF r", h)
        if row is not None and row["revoked_at"] is not None:
            # Replay of a rotated token: assume theft, revoke the whole device (master 9.1 token replay).
            # Committed before the error is returned.
            await conn.execute("UPDATE devices SET revoked_at=now() WHERE device_id=$1 AND revoked_at IS NULL", row["device_id"])
            await conn.execute("UPDATE refresh_tokens SET revoked_at=now() WHERE device_id=$1 AND revoked_at IS NULL", row["device_id"])
            await conn.execute("UPDATE ingest_tokens SET revoked_at=now() WHERE device_id=$1 AND revoked_at IS NULL", row["device_id"])
            await conn.execute("SELECT pg_notify($1, '')", "msd_" + row["device_id"].hex)
            reused = True
    if reused:
        raise ApiError(401, "TOKEN_REUSED", "This device was signed out for your security.")
    async with db.system_tx() as conn:
        row = await conn.fetchrow("SELECT r.*, d.revoked_at AS device_revoked FROM refresh_tokens r JOIN devices d USING (device_id)"
                                  " WHERE r.token_hash=$1 FOR UPDATE OF r", h)
        if row is None or row["revoked_at"] is not None:
            raise ApiError(401, "UNAUTHENTICATED", "Sign in to continue.")
        if row["device_revoked"] is not None or row["expires_at"] < dt.datetime.now(dt.timezone.utc):
            raise ApiError(401, "UNAUTHENTICATED", "Sign in to continue.")
        raw, new_h = new_refresh_token()
        await conn.execute("UPDATE refresh_tokens SET revoked_at=now(), replaced_by=$2 WHERE token_hash=$1", h, new_h)
        await conn.execute("INSERT INTO refresh_tokens(token_hash,user_id,device_id,expires_at) VALUES ($1,$2,$3,now()+make_interval(secs=>$4))",
                           new_h, row["user_id"], row["device_id"], float(s.refresh_token_ttl_s))
    return _tokens(row["user_id"], row["device_id"], raw)


@router.post("/auth/reauth")
async def reauth(body: ReauthIn, user: CurrentUser = Depends(current_user)):
    async with db.system_tx() as conn:
        stored = await conn.fetchval("SELECT password_hash FROM user_credentials WHERE user_id=$1", user.user_id)
    if not stored or not verify_password(body.password, stored):
        raise ApiError(401, "INVALID_CREDENTIALS", "Password is incorrect.")
    s = get_settings()
    return {"access_token": issue_access_token(user.user_id, user.device_id, reauth=True), "token_type": "Bearer",
            "expires_in": s.access_token_ttl_s, "reauth_valid_for_s": s.reauth_window_s}


@router.post("/auth/logout", status_code=204)
async def logout(user: CurrentUser = Depends(current_user)):
    await _revoke_device(user.user_id, user.device_id)


async def _revoke_device(user_id, device_id) -> None:
    async with db.system_tx() as conn:
        n = await conn.execute("UPDATE devices SET revoked_at=now() WHERE device_id=$1 AND user_id=$2 AND revoked_at IS NULL",
                               device_id, user_id)
        await conn.execute("UPDATE refresh_tokens SET revoked_at=now() WHERE device_id=$1 AND revoked_at IS NULL", device_id)
        # UNI-025: revoked device cannot stream; ingress credentials invalidated.
        await conn.execute("UPDATE ingest_tokens SET revoked_at=now() WHERE device_id=$1 AND revoked_at IS NULL", device_id)
        await conn.execute("SELECT pg_notify($1, '')", "msd_" + device_id.hex)
        if n == "UPDATE 0":
            exists = await conn.fetchval("SELECT 1 FROM devices WHERE device_id=$1 AND user_id=$2", device_id, user_id)
            if not exists:
                raise not_found("device")


@router.get("/devices")
async def list_devices(user: CurrentUser = Depends(current_user)):
    async with db.user_tx(user.user_id) as conn:
        rows = await conn.fetch("SELECT device_id, platform, name, created_at, last_seen_at, revoked_at FROM devices ORDER BY created_at")
    return {"items": [dict(r) | {"current": r["device_id"] == user.device_id} for r in rows]}


@router.delete("/devices/{device_id}", status_code=204)
async def revoke_device(device_id: uuid.UUID, user: CurrentUser = Depends(current_user)):
    await _revoke_device(user.user_id, device_id)


@router.get("/me")
async def me(user: CurrentUser = Depends(current_user)):
    async with db.user_tx(user.user_id) as conn:
        u = await conn.fetchrow("SELECT user_id, display_name, created_at FROM users WHERE user_id=$1", user.user_id)
        t = await conn.fetchrow("SELECT tenant_id, name, residency_region, plan, org_policy FROM tenants WHERE tenant_id=$1", user.tenant_id)
        spaces = await conn.fetch("SELECT s.space_id, s.name, s.kind, m.role FROM spaces s JOIN space_memberships m"
                                  " ON m.space_id=s.space_id AND m.user_id=$1 WHERE s.deleted_at IS NULL ORDER BY s.created_at", user.user_id)
        prefs = await conn.fetchval("SELECT prefs FROM user_preferences WHERE user_id=$1", user.user_id)
        quota = await ops.quota_status(conn, user.tenant_id)
    s = get_settings()
    return {"user": dict(u), "tenant": dict(t), "spaces": [dict(r) for r in spaces], "preferences": prefs or {},
            "quota": quota, "processing_disclosure_version": s.processing_disclosure_version,
            "policy_version": s.policy_version}


class PrefsIn(BaseModel):
    prefs: dict
    expected_version: int | None = None


ALLOWED_PREF_KEYS = {"last_context", "default_output", "default_assistance", "default_intensity_by_context",
                     "default_retention_by_context", "language", "captions_large", "reduced_motion_override",
                     "haptics", "lock_screen_details", "suggestions_mute_default", "theme", "voice_rate"}


@router.put("/me/preferences")
async def put_preferences(body: PrefsIn, user: CurrentUser = Depends(current_user)):
    unknown = set(body.prefs) - ALLOWED_PREF_KEYS
    if unknown:
        raise ApiError(422, "UNKNOWN_PREFERENCE", "Some preferences aren't supported.", details={"keys": sorted(unknown)})
    if body.prefs.get("lock_screen_details") is True:
        pass  # explicit user opt-in only (CON-016); default remains neutral notifications
    async with db.user_tx(user.user_id) as conn:
        row = await conn.fetchrow("SELECT prefs, version FROM user_preferences WHERE user_id=$1 FOR UPDATE", user.user_id)
        if body.expected_version is not None and row["version"] != body.expected_version:
            raise ApiError(409, "VERSION_CONFLICT", "Preferences changed on another device. Review and try again.",
                           details={"current_version": row["version"]})
        merged = (row["prefs"] or {}) | body.prefs
        version = await conn.fetchval("UPDATE user_preferences SET prefs=$2, version=version+1, updated_at=now() WHERE user_id=$1 RETURNING version",
                                      user.user_id, merged)
    return {"prefs": merged, "version": version}


@router.get("/me/usage")
async def my_usage(user: CurrentUser = Depends(current_user)):
    async with db.user_tx(user.user_id) as conn:
        return await ops.quota_status(conn, user.tenant_id)


@router.delete("/account", status_code=202)
async def delete_account(user: CurrentUser = Depends(current_user)):
    require_recent_auth(user, get_settings().reauth_window_s)
    from ..memory.deletion import request_account_deletion

    return await request_account_deletion(user)
