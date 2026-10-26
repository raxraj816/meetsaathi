"""Password hashing (scrypt), short-lived device-bound access tokens, refresh tokens and ingest tokens."""
from __future__ import annotations

import base64
import hashlib
import hmac
import os
import secrets
import time
import uuid
from dataclasses import dataclass

import jwt

from ..config import get_settings
from ..errors import ApiError

_SCRYPT_N, _SCRYPT_R, _SCRYPT_P = 2**14, 8, 1


def hash_password(password: str) -> str:
    salt = os.urandom(16)
    dk = hashlib.scrypt(password.encode(), salt=salt, n=_SCRYPT_N, r=_SCRYPT_R, p=_SCRYPT_P, dklen=32)
    return "scrypt$%d$%d$%d$%s$%s" % (_SCRYPT_N, _SCRYPT_R, _SCRYPT_P,
                                       base64.b64encode(salt).decode(), base64.b64encode(dk).decode())


def verify_password(password: str, stored: str) -> bool:
    try:
        scheme, n, r, p, salt_b64, dk_b64 = stored.split("$")
        if scheme != "scrypt":
            return False
        dk = hashlib.scrypt(password.encode(), salt=base64.b64decode(salt_b64), n=int(n), r=int(r), p=int(p), dklen=32)
        return hmac.compare_digest(dk, base64.b64decode(dk_b64))
    except (ValueError, TypeError):
        return False


def new_refresh_token() -> tuple[str, str]:
    raw = secrets.token_urlsafe(48)
    return raw, hash_opaque(raw)


def hash_opaque(raw: str) -> str:
    return hashlib.sha256(raw.encode()).hexdigest()


@dataclass(frozen=True)
class AccessClaims:
    user_id: uuid.UUID
    device_id: uuid.UUID
    issued_at: int
    reauth_at: int | None
    expires_at: int


def issue_access_token(user_id: uuid.UUID, device_id: uuid.UUID, reauth: bool = False) -> str:
    s = get_settings()
    now = int(time.time())
    claims = {"sub": str(user_id), "did": str(device_id), "iat": now, "exp": now + s.access_token_ttl_s,
              "typ": "access", "jti": uuid.uuid4().hex}
    if reauth:
        claims["reauth_at"] = now
    return jwt.encode(claims, s.jwt_secret, algorithm="HS256")


def decode_access_token(token: str) -> AccessClaims:
    s = get_settings()
    try:
        c = jwt.decode(token, s.jwt_secret, algorithms=["HS256"], options={"require": ["exp", "iat", "sub", "did", "typ"]})
    except jwt.ExpiredSignatureError:
        raise ApiError(401, "TOKEN_EXPIRED", "Your session expired. Sign in again.", retryable=True)
    except jwt.PyJWTError:
        raise ApiError(401, "UNAUTHENTICATED", "Sign in to continue.")
    if c.get("typ") != "access":
        raise ApiError(401, "UNAUTHENTICATED", "Sign in to continue.")
    try:
        return AccessClaims(uuid.UUID(c["sub"]), uuid.UUID(c["did"]), int(c["iat"]), c.get("reauth_at"), int(c["exp"]))
    except (ValueError, TypeError, KeyError):
        raise ApiError(401, "UNAUTHENTICATED", "Sign in to continue.")


def issue_ingest_token(jti: uuid.UUID, user_id: uuid.UUID, device_id: uuid.UUID, session_id: uuid.UUID,
                       ttl_s: int | None = None) -> tuple[str, int]:
    s = get_settings()
    now = int(time.time())
    exp = now + (ttl_s or s.ingest_token_ttl_s)
    claims = {"sub": str(user_id), "did": str(device_id), "ses": str(session_id), "iat": now, "exp": exp,
              "typ": "ingest", "jti": str(jti)}
    return jwt.encode(claims, s.jwt_secret, algorithm="HS256"), exp


def decode_ingest_token(token: str) -> dict:
    s = get_settings()
    try:
        c = jwt.decode(token, s.jwt_secret, algorithms=["HS256"], options={"require": ["exp", "sub", "did", "ses", "jti"]})
    except jwt.ExpiredSignatureError:
        raise ApiError(401, "INGEST_TOKEN_EXPIRED", "Upload credential expired. Requesting a new one.", retryable=True)
    except jwt.PyJWTError:
        raise ApiError(401, "UNAUTHENTICATED", "Upload credential is not valid.")
    if c.get("typ") != "ingest":
        raise ApiError(401, "UNAUTHENTICATED", "Upload credential is not valid.")
    return c
