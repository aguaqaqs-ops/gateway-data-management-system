"""Application-owned recovery capability, decision/outcome contracts and reconcile port."""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from typing import Protocol, runtime_checkable

from gateway_shared_kernel import raw_blob_digest

from gateway_backend.artifacts.types import ArtifactRef
from gateway_backend.operations.contracts import OperationRecord, StepRecord
from gateway_backend.operations.worker import ExecutionControl, LeaseSession

_NAMESPACED_DIAGNOSTIC_CODE_RE = re.compile(r"^[a-z][a-z0-9_.:-]{0,127}$")
_MAX_DIAGNOSTIC_MESSAGE_BYTES = 4 * 1024

# Mirrors gateway_backend.operations.recovery.RECONCILE_SESSION_BUDGET_SECONDS without importing operations.
RECONCILE_SESSION_BUDGET_SECONDS = 60.0

JOB_STATE_IDEMPOTENCY_KEY = "idempotency_key"
JOB_STATE_REQUEST_FINGERPRINT = "request_fingerprint"
JOB_STATE_OPERATION_IDENTITY = "operation_identity"
JOB_STATE_REQUEST_SENT = "request_sent"
JOB_STATE_RECONCILE_STARTED_AT = "reconcile_started_at"

DIAGNOSTIC_EFFECT_IDENTITY_MISMATCH = "r5.effect_identity_mismatch"
DIAGNOSTIC_MANUAL_RECOVERY_REQUIRED = "r5.manual_recovery_required"
DIAGNOSTIC_RECONCILE_TIMEOUT = "r5.reconcile_timeout"


class RecoveryCapability(StrEnum):
    """Static recovery path for one JobDefinition step; not persisted."""

    PURE_RECOMPUTE = "PURE_RECOMPUTE"
    EXTERNAL_EFFECT = "EXTERNAL_EFFECT"
    NON_RETRYABLE = "NON_RETRYABLE"


class RecoveryDecisionDisposition(StrEnum):
    """Bounded runtime recovery disposition produced by R5 policy."""

    NO_ACTION = "NO_ACTION"
    MOVE_TO_RETRY_WAIT = "MOVE_TO_RETRY_WAIT"
    CLAIM_FOR_RECONCILE = "CLAIM_FOR_RECONCILE"
    MARK_MANUAL_RECOVERY = "MARK_MANUAL_RECOVERY"
    BLOCK_STARTUP_RETRYABLE = "BLOCK_STARTUP_RETRYABLE"
    BLOCK_STARTUP_FATAL = "BLOCK_STARTUP_FATAL"


class ExternalEffectReconcilePhase(StrEnum):
    """Bounded external-effect request phase for identity reconcile routing."""

    PRE_REQUEST = "PRE_REQUEST"
    POST_REQUEST = "POST_REQUEST"


@dataclass(frozen=True, slots=True)
class ExternalEffectRequestIdentity:
    """Immutable external-effect request identity bound to one checkpoint."""

    idempotency_key: str
    request_fingerprint: str
    repository_operation_id: str


class RecoveryOutcomeDisposition(StrEnum):
    """Bounded application handler recovery result consumed by R5."""

    PUBLISHED = "PUBLISHED"
    RETRYABLE_FAILURE = "RETRYABLE_FAILURE"
    PERMANENT_FAILURE = "PERMANENT_FAILURE"
    RECONCILE_PENDING = "RECONCILE_PENDING"
    MANUAL_RECOVERY = "MANUAL_RECOVERY"
    CANCELLED = "CANCELLED"


@dataclass(frozen=True, slots=True)
class RecoveryDecision:
    """Read-only bounded recovery decision without payload, I/O or callables."""

    disposition: RecoveryDecisionDisposition
    diagnostic_code: str
    retry_not_before: datetime | None
    reason: str

    def __post_init__(self) -> None:
        if type(self.disposition) is not RecoveryDecisionDisposition:
            raise ValueError("disposition must be RecoveryDecisionDisposition")
        _validate_namespaced_diagnostic_code(self.diagnostic_code)
        _validate_bounded_diagnostic_message(self.reason)
        if self.disposition is RecoveryDecisionDisposition.MOVE_TO_RETRY_WAIT:
            if self.retry_not_before is None:
                raise ValueError("retry_not_before is required for MOVE_TO_RETRY_WAIT")
            _validate_utc_datetime(self.retry_not_before, "retry_not_before")
        elif self.retry_not_before is not None:
            raise ValueError("retry_not_before must be null unless disposition is MOVE_TO_RETRY_WAIT")


@dataclass(frozen=True, slots=True)
class RecoveryOutcome:
    """Application-to-R5 handler recovery result; not an arbitrary durable record."""

    disposition: RecoveryOutcomeDisposition
    diagnostic_code: str | None
    reason: str | None

    def __post_init__(self) -> None:
        if type(self.disposition) is not RecoveryOutcomeDisposition:
            raise ValueError("disposition must be RecoveryOutcomeDisposition")
        if self.diagnostic_code is not None:
            _validate_namespaced_diagnostic_code(self.diagnostic_code)
        if self.reason is not None:
            _validate_bounded_diagnostic_message(self.reason)


@runtime_checkable
class RecoveryPort(Protocol):
    """In-process composition port for handler recovery; not HTTP, registry or R3 protocol."""

    def recover(
        self,
        operation: OperationRecord,
        step: StepRecord,
        control: ExecutionControl,
        lease_session: LeaseSession,
    ) -> RecoveryOutcome:
        """Execute bounded handler recovery for one claimed step."""


def _validate_namespaced_diagnostic_code(value: str) -> None:
    if type(value) is not str:
        raise ValueError("diagnostic_code must be a string")
    if not _NAMESPACED_DIAGNOSTIC_CODE_RE.fullmatch(value):
        raise ValueError("diagnostic_code must match bounded namespaced pattern")


def _validate_bounded_diagnostic_message(value: str) -> None:
    if type(value) is not str:
        raise ValueError("reason must be a string")
    encoded = value.encode("utf-8")
    if not 1 <= len(encoded) <= _MAX_DIAGNOSTIC_MESSAGE_BYTES:
        raise ValueError("reason exceeds bounded diagnostic size")


def compute_request_fingerprint(request_bytes: bytes) -> str:
    """Return the stable request fingerprint digest for one canonical request body."""

    return raw_blob_digest(request_bytes).value


def classify_external_effect_phase(
    *,
    checkpoint_ref: ArtifactRef | None,
    job_state: Mapping[str, object] | None,
) -> ExternalEffectReconcilePhase:
    if checkpoint_ref is None:
        return ExternalEffectReconcilePhase.PRE_REQUEST
    if not isinstance(job_state, Mapping):
        return ExternalEffectReconcilePhase.PRE_REQUEST
    if job_state.get(JOB_STATE_REQUEST_SENT) is True:
        return ExternalEffectReconcilePhase.POST_REQUEST
    return ExternalEffectReconcilePhase.PRE_REQUEST


def reconcile_session_budget_exhausted(elapsed_seconds: float) -> bool:
    if isinstance(elapsed_seconds, bool) or not isinstance(elapsed_seconds, (int, float)):
        raise ValueError("elapsed_seconds must be a number")
    if elapsed_seconds < 0:
        raise ValueError("elapsed_seconds must be non-negative")
    return float(elapsed_seconds) >= RECONCILE_SESSION_BUDGET_SECONDS


def parse_reconcile_started_at(job_state: Mapping[str, object]) -> datetime:
    """Read the mandatory UTC reconcile start timestamp from a checkpoint."""

    if not isinstance(job_state, Mapping):
        raise ValueError("job_state must be a mapping")
    value = job_state.get(JOB_STATE_RECONCILE_STARTED_AT)
    if type(value) is not str or not value:
        raise ValueError(f"{JOB_STATE_RECONCILE_STARTED_AT} must be a non-empty string")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"{JOB_STATE_RECONCILE_STARTED_AT} is malformed") from exc
    _validate_utc_datetime(parsed, JOB_STATE_RECONCILE_STARTED_AT)
    return parsed


def reconcile_elapsed_seconds(started_at: datetime, now: datetime) -> float:
    _validate_utc_datetime(started_at, "started_at")
    _validate_utc_datetime(now, "now")
    return (now - started_at).total_seconds()


def _manual_recovery_outcome(*, diagnostic_code: str, reason: str) -> RecoveryOutcome:
    return RecoveryOutcome(
        disposition=RecoveryOutcomeDisposition.MANUAL_RECOVERY,
        diagnostic_code=diagnostic_code,
        reason=reason,
    )


def validate_external_effect_identity(
    *,
    idempotency_key: str,
    request_bytes: bytes,
    job_state: Mapping[str, object],
    expected_operation_identity: str,
) -> ExternalEffectRequestIdentity | RecoveryOutcome:
    if not isinstance(job_state, Mapping):
        return _manual_recovery_outcome(
            diagnostic_code=DIAGNOSTIC_EFFECT_IDENTITY_MISMATCH,
            reason="checkpoint job_state must be a mapping",
        )
    stored_key = job_state.get(JOB_STATE_IDEMPOTENCY_KEY)
    if type(stored_key) is not str or stored_key != idempotency_key:
        return _manual_recovery_outcome(
            diagnostic_code=DIAGNOSTIC_EFFECT_IDENTITY_MISMATCH,
            reason="checkpoint idempotency_key does not match payload",
        )
    expected_fingerprint = compute_request_fingerprint(request_bytes)
    stored_fingerprint = job_state.get(JOB_STATE_REQUEST_FINGERPRINT)
    if stored_fingerprint is not None:
        if type(stored_fingerprint) is not str or stored_fingerprint != expected_fingerprint:
            return _manual_recovery_outcome(
                diagnostic_code=DIAGNOSTIC_EFFECT_IDENTITY_MISMATCH,
                reason="checkpoint request_fingerprint does not match payload",
            )
    stored_identity = job_state.get(JOB_STATE_OPERATION_IDENTITY)
    if type(stored_identity) is not str or not stored_identity:
        return _manual_recovery_outcome(
            diagnostic_code=DIAGNOSTIC_EFFECT_IDENTITY_MISMATCH,
            reason="checkpoint operation_identity is invalid",
        )
    if stored_identity != expected_operation_identity:
        return _manual_recovery_outcome(
            diagnostic_code=DIAGNOSTIC_EFFECT_IDENTITY_MISMATCH,
            reason="checkpoint operation_identity does not match payload semantics",
        )
    if job_state.get(JOB_STATE_REQUEST_SENT) is not True:
        return _manual_recovery_outcome(
            diagnostic_code=DIAGNOSTIC_EFFECT_IDENTITY_MISMATCH,
            reason="checkpoint request_sent must be true after request acceptance",
        )
    return ExternalEffectRequestIdentity(
        idempotency_key=idempotency_key,
        request_fingerprint=expected_fingerprint,
        repository_operation_id=stored_identity,
    )


def _validate_utc_datetime(value: datetime, label: str) -> None:
    if type(value) is not datetime:
        raise ValueError(f"{label} must be a datetime")
    if value.tzinfo is None or value.tzinfo.utcoffset(value) is None:
        raise ValueError(f"{label} must be timezone-aware UTC")
    if value.utcoffset() != UTC.utcoffset(value):
        raise ValueError(f"{label} must be timezone-aware UTC")


__all__ = [
    "DIAGNOSTIC_EFFECT_IDENTITY_MISMATCH",
    "DIAGNOSTIC_MANUAL_RECOVERY_REQUIRED",
    "DIAGNOSTIC_RECONCILE_TIMEOUT",
    "ExternalEffectReconcilePhase",
    "ExternalEffectRequestIdentity",
    "JOB_STATE_IDEMPOTENCY_KEY",
    "JOB_STATE_OPERATION_IDENTITY",
    "JOB_STATE_RECONCILE_STARTED_AT",
    "JOB_STATE_REQUEST_FINGERPRINT",
    "JOB_STATE_REQUEST_SENT",
    "RECONCILE_SESSION_BUDGET_SECONDS",
    "RecoveryCapability",
    "RecoveryDecision",
    "RecoveryDecisionDisposition",
    "RecoveryOutcome",
    "RecoveryOutcomeDisposition",
    "RecoveryPort",
    "classify_external_effect_phase",
    "compute_request_fingerprint",
    "parse_reconcile_started_at",
    "reconcile_elapsed_seconds",
    "reconcile_session_budget_exhausted",
    "validate_external_effect_identity",
]
