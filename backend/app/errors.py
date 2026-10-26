"""Standard error contract (master 10.3): {code, user_message, retryable, correlation_id, details?}.
User messages never contain raw source text."""
from __future__ import annotations

import contextvars
import uuid
from typing import Any

correlation_id_var: contextvars.ContextVar[str] = contextvars.ContextVar("correlation_id", default="")


def new_correlation_id() -> str:
    return uuid.uuid4().hex


class ApiError(Exception):
    def __init__(self, status: int, code: str, user_message: str, *, retryable: bool = False,
                 details: dict[str, Any] | None = None):
        super().__init__(code)
        self.status = status
        self.code = code
        self.user_message = user_message
        self.retryable = retryable
        self.details = details

    def body(self) -> dict[str, Any]:
        out: dict[str, Any] = {
            "code": self.code,
            "user_message": self.user_message,
            "retryable": self.retryable,
            "correlation_id": correlation_id_var.get() or new_correlation_id(),
        }
        if self.details:
            out["details"] = self.details
        return out


def not_found(what: str = "resource") -> ApiError:
    # Same response for "does not exist" and "not authorized" to avoid metadata leaks (MTG-041, UNI-017).
    return ApiError(404, "NOT_FOUND", f"That {what} isn't available.")


def space_denied() -> ApiError:
    return ApiError(403, "SCOPE_DENIED", "That memory isn't available in this space.")


def conflict(code: str, msg: str, details: dict[str, Any] | None = None) -> ApiError:
    return ApiError(409, code, msg, details=details)


def policy_denied(code: str, msg: str, details: dict[str, Any] | None = None) -> ApiError:
    return ApiError(403, code, msg, details=details)


def preflight_failed(code: str, msg: str, details: dict[str, Any] | None = None) -> ApiError:
    return ApiError(422, code, msg, details=details)


def unavailable(code: str, msg: str) -> ApiError:
    return ApiError(503, code, msg, retryable=True)
