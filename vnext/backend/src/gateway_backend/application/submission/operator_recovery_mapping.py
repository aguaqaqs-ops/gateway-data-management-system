"""Typed classification for P4 operator recovery ValueError surfaces."""

from __future__ import annotations

from gateway_backend.application.submission.errors import (
    OperatorRecoveryCapabilityConflict,
    OperatorRecoveryIdentityConflict,
    OperatorRecoveryStateConflict,
)
from gateway_backend.operations.store import StaleWrite

_RECOVERY_STATE_MESSAGES = frozenset(
    {
        "operator recovery requires MANUAL_RECOVERY_REQUIRED operation",
        "operator recovery requires MANUAL_RECOVERY_REQUIRED step",
        "operator recovery only supports MANUAL_RECOVERY_REQUIRED step source",
        "operator recovery only supports MANUAL_RECOVERY_REQUIRED operation source",
        "unsupported operator recovery command",
        "terminal replay only supports ABORT_CONFIRMED_FAILURE",
    }
)
_RECOVERY_CAPABILITY_MESSAGES = frozenset(
    {
        "RESUME_RECONCILE requires EXTERNAL_EFFECT capability",
        "RETRY_FROM_CHECKPOINT requires PURE_RECOMPUTE capability",
    }
)
_RECOVERY_IDENTITY_MESSAGES = frozenset(
    {
        "step does not belong to the requested operation",
        "step_id mismatch",
    }
)
_OPERATION_STALE_WRITE_MESSAGE = "operation CAS lost its precondition"
_STEP_STALE_WRITE_MESSAGE = "step CAS lost its precondition"
_GENERIC_STALE_WRITE_MESSAGE = "write precondition no longer matches"


def classify_operator_recovery_value_error(exc: ValueError) -> Exception:
    message = str(exc)
    if message in _RECOVERY_IDENTITY_MESSAGES:
        return OperatorRecoveryIdentityConflict(message)
    if message in _RECOVERY_CAPABILITY_MESSAGES:
        return OperatorRecoveryCapabilityConflict(message)
    if message in _RECOVERY_STATE_MESSAGES:
        return OperatorRecoveryStateConflict(message)
    return exc


def classify_operator_recovery_stale_write(exc: StaleWrite) -> tuple[str, str]:
    message = str(exc)
    if message == _OPERATION_STALE_WRITE_MESSAGE:
        return ("OPERATION_VERSION_CONFLICT", "operation optimistic version is stale")
    if message == _STEP_STALE_WRITE_MESSAGE:
        return ("STEP_VERSION_CONFLICT", "step optimistic version is stale")
    if message == _GENERIC_STALE_WRITE_MESSAGE:
        return ("STEP_VERSION_CONFLICT", "step optimistic version is stale")
    return ("STEP_VERSION_CONFLICT", "step optimistic version is stale")
