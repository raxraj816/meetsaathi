"""Authoritative recording/session state machine (master 7.1). Clients implement the same table
(apps/*/SessionStateMachine) and the contract test in tests/test_state_machine.py pins it."""
from __future__ import annotations

from enum import Enum


class S(str, Enum):
    PREFLIGHT = "PREFLIGHT"
    NOTES_ONLY = "NOTES_ONLY"
    STARTING = "STARTING"
    RECORDING = "RECORDING"
    PAUSED = "PAUSED"
    INTERRUPTED = "INTERRUPTED"
    STOPPING = "STOPPING"
    FINALIZING = "FINALIZING"
    FINALIZATION_RETRYABLE = "FINALIZATION_RETRYABLE"
    COMPLETED = "COMPLETED"
    COMPLETED_PARTIAL = "COMPLETED_PARTIAL"
    ERROR = "ERROR"
    DELETING = "DELETING"
    DELETED = "DELETED"


TRANSITIONS: dict[S, set[S]] = {
    S.PREFLIGHT: {S.STARTING, S.NOTES_ONLY, S.STOPPING, S.ERROR, S.DELETING},
    S.NOTES_ONLY: {S.STARTING, S.STOPPING, S.DELETING},           # notes-only may later start authorized capture
    S.STARTING: {S.RECORDING, S.ERROR, S.STOPPING, S.INTERRUPTED, S.DELETING},
    S.RECORDING: {S.PAUSED, S.INTERRUPTED, S.STOPPING, S.DELETING},
    S.PAUSED: {S.STARTING, S.STOPPING, S.DELETING},
    S.INTERRUPTED: {S.STARTING, S.STOPPING, S.DELETING},
    S.STOPPING: {S.FINALIZING, S.DELETING},
    S.FINALIZING: {S.COMPLETED, S.COMPLETED_PARTIAL, S.FINALIZATION_RETRYABLE, S.DELETING},
    S.FINALIZATION_RETRYABLE: {S.FINALIZING, S.DELETING},
    S.COMPLETED: {S.DELETING},
    S.COMPLETED_PARTIAL: {S.DELETING},
    S.ERROR: {S.STARTING, S.STOPPING, S.DELETING},
    S.DELETING: {S.DELETED},
    S.DELETED: set(),
}

LIVE_CAPTURE_STATES = {S.STARTING, S.RECORDING}
ACTIVE_STATES = {S.STARTING, S.RECORDING, S.PAUSED, S.INTERRUPTED, S.NOTES_ONLY}
ENDED_STATES = {S.STOPPING, S.FINALIZING, S.FINALIZATION_RETRYABLE, S.COMPLETED, S.COMPLETED_PARTIAL}
TERMINAL_STATES = {S.COMPLETED, S.COMPLETED_PARTIAL, S.DELETED}


def can_transition(current: str | S, target: str | S) -> bool:
    return S(target) in TRANSITIONS[S(current)]


def assert_transition(current: str | S, target: str | S) -> None:
    from ..errors import conflict

    if not can_transition(current, target):
        raise conflict("INVALID_STATE_TRANSITION",
                       "That action isn't possible in the session's current state.",
                       {"current": S(current).value, "requested": S(target).value})
