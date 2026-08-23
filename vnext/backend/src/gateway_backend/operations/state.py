"""Pure structural transition and stale-write guards for operation runtime."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from gateway_backend.operations.contracts import (
    OperationRecord,
    OperationStatus,
    StepRecord,
    StepStatus,
)

_OPERATION_ALLOWED_TRANSITIONS: dict[OperationStatus, frozenset[OperationStatus]] = {
    OperationStatus.QUEUED: frozenset(
        {
            OperationStatus.RUNNING,
            OperationStatus.CANCELLED,
            OperationStatus.SUPERSEDED,
        }
    ),
    OperationStatus.RUNNING: frozenset(
        {
            OperationStatus.SUCCEEDED,
            OperationStatus.FAILED,
            OperationStatus.CANCELLED,
            OperationStatus.SUPERSEDED,
            OperationStatus.MANUAL_RECOVERY_REQUIRED,
        }
    ),
    OperationStatus.MANUAL_RECOVERY_REQUIRED: frozenset(
        {
            OperationStatus.RUNNING,
            OperationStatus.SUCCEEDED,
            OperationStatus.FAILED,
        }
    ),
}

_STEP_ALLOWED_TRANSITIONS: dict[StepStatus, frozenset[StepStatus]] = {
    StepStatus.PENDING: frozenset({StepStatus.RUNNING, StepStatus.CANCELLED}),
    StepStatus.RUNNING: frozenset(
        {
            StepStatus.RETRY_WAIT,
            StepStatus.SUCCEEDED,
            StepStatus.FAILED,
            StepStatus.CANCELLED,
            StepStatus.MANUAL_RECOVERY_REQUIRED,
        }
    ),
    StepStatus.RETRY_WAIT: frozenset({StepStatus.RUNNING, StepStatus.CANCELLED}),
    StepStatus.MANUAL_RECOVERY_REQUIRED: frozenset(
        {
            StepStatus.RUNNING,
            StepStatus.SUCCEEDED,
            StepStatus.FAILED,
        }
    ),
}


class TransitionDisposition(StrEnum):
    APPLY = "APPLY"
    IDEMPOTENT = "IDEMPOTENT"


@dataclass(frozen=True, slots=True)
class WritePrecondition:
    expected_optimistic_version: int
    worker_id: str | None
    lease_token: str | None


def validate_write_precondition(
    *,
    current_optimistic_version: int,
    current_worker_id: str | None,
    current_lease_token: str | None,
    precondition: WritePrecondition,
) -> None:
    if current_optimistic_version != precondition.expected_optimistic_version:
        raise ValueError("optimistic version mismatch")
    pre_worker = precondition.worker_id
    pre_lease = precondition.lease_token
    if (pre_worker is None) != (pre_lease is None):
        raise ValueError("worker_id and lease_token must both be set or both null")
    if pre_worker is not None:
        if pre_worker != current_worker_id or pre_lease != current_lease_token:
            raise ValueError("lease identity mismatch")
    elif current_worker_id is not None or current_lease_token is not None:
        raise ValueError("lease identity must be null")


def validate_operation_transition(
    current: OperationRecord,
    candidate: OperationRecord,
    *,
    recovery_authorized: bool = False,
) -> TransitionDisposition:
    if current.status == candidate.status:
        if not current.status.is_final_terminal():
            raise ValueError("same-state publication only allowed for final terminal")
        if current == candidate:
            return TransitionDisposition.IDEMPOTENT
        raise ValueError("conflicting terminal duplicate")
    _validate_operation_identity_unchanged(current, candidate)
    _validate_cancel_requested_monotonic(current.cancel_requested, candidate.cancel_requested)
    _validate_operation_mutable_fields(current, candidate)
    _require_updated_at_monotonic(current.updated_at, candidate.updated_at)
    _validate_operation_status_edge(
        current.status,
        candidate.status,
        recovery_authorized=recovery_authorized,
    )
    _require_optimistic_version_increment(current.optimistic_version, candidate.optimistic_version)
    return TransitionDisposition.APPLY


def validate_step_transition(
    current: StepRecord,
    candidate: StepRecord,
    *,
    recovery_authorized: bool = False,
) -> TransitionDisposition:
    if current.status == candidate.status:
        if not current.status.is_final_terminal():
            raise ValueError("same-state publication only allowed for final terminal")
        if current == candidate:
            return TransitionDisposition.IDEMPOTENT
        raise ValueError("conflicting terminal duplicate")
    _validate_step_identity_unchanged(current, candidate)
    _validate_cancel_requested_monotonic(current.cancel_requested, candidate.cancel_requested)
    _require_updated_at_monotonic(current.updated_at, candidate.updated_at)
    _validate_step_status_edge(
        current.status,
        candidate.status,
        recovery_authorized=recovery_authorized,
    )
    _validate_step_attempt_and_lease(current, candidate)
    _require_optimistic_version_increment(current.optimistic_version, candidate.optimistic_version)
    return TransitionDisposition.APPLY


def _validate_operation_identity_unchanged(current: OperationRecord, candidate: OperationRecord) -> None:
    if current.contract_version != candidate.contract_version:
        raise ValueError("contract_version is immutable")
    if current.operation_id != candidate.operation_id:
        raise ValueError("operation_id is immutable")
    if current.job_kind != candidate.job_kind:
        raise ValueError("job_kind is immutable")
    if current.job_contract_version != candidate.job_contract_version:
        raise ValueError("job_contract_version is immutable")
    if current.job_payload != candidate.job_payload:
        raise ValueError("job_payload is immutable")
    if current.job_payload_ref != candidate.job_payload_ref:
        raise ValueError("job_payload_ref is immutable")
    if current.business_refs != candidate.business_refs:
        raise ValueError("business_refs are immutable")
    if current.created_at != candidate.created_at:
        raise ValueError("created_at is immutable")


def _validate_step_identity_unchanged(current: StepRecord, candidate: StepRecord) -> None:
    if current.contract_version != candidate.contract_version:
        raise ValueError("contract_version is immutable")
    if current.step_id != candidate.step_id:
        raise ValueError("step_id is immutable")
    if current.operation_id != candidate.operation_id:
        raise ValueError("operation_id is immutable")
    if current.step_name != candidate.step_name:
        raise ValueError("step_name is immutable")
    if current.prior_output_refs != candidate.prior_output_refs:
        raise ValueError("prior_output_refs are immutable")
    if current.created_at != candidate.created_at:
        raise ValueError("created_at is immutable")


def _validate_cancel_requested_monotonic(current: bool, candidate: bool) -> None:
    if current and not candidate:
        raise ValueError("cancel_requested cannot be reset")


def _validate_operation_mutable_fields(current: OperationRecord, candidate: OperationRecord) -> None:
    if current.repository_operation_id is not None:
        if candidate.repository_operation_id != current.repository_operation_id:
            raise ValueError("repository_operation_id can only be set once")
    if current.ready_closure_ref is not None:
        if candidate.ready_closure_ref != current.ready_closure_ref:
            raise ValueError("ready_closure_ref can only be set once")
    current_refs = current.artifact_refs
    candidate_refs = candidate.artifact_refs
    if len(candidate_refs) < len(current_refs):
        raise ValueError("artifact_refs can only append unique refs")
    if candidate_refs[: len(current_refs)] != current_refs:
        raise ValueError("artifact_refs can only append unique refs")
    seen = {ref.artifact_id for ref in current_refs}
    for ref in candidate_refs[len(current_refs) :]:
        if ref.artifact_id in seen:
            raise ValueError("artifact_refs can only append unique refs")
        seen.add(ref.artifact_id)


def _validate_step_attempt_and_lease(current: StepRecord, candidate: StepRecord) -> None:
    from_pending_or_retry = current.status in {StepStatus.PENDING, StepStatus.RETRY_WAIT}
    entering_running = candidate.status is StepStatus.RUNNING
    leaving_running = current.status is StepStatus.RUNNING

    if from_pending_or_retry and entering_running:
        if candidate.attempt_count != current.attempt_count + 1:
            raise ValueError(
                "attempt_count must increment when entering RUNNING from PENDING or RETRY_WAIT"
            )
    elif candidate.attempt_count != current.attempt_count:
        raise ValueError(
            "attempt_count can only change when entering RUNNING from PENDING or RETRY_WAIT"
        )

    if entering_running:
        if (
            candidate.worker_id is None
            or candidate.lease_token is None
            or candidate.lease_expires_at is None
        ):
            raise ValueError("RUNNING step requires lease identity")
    elif leaving_running:
        if (
            candidate.worker_id is not None
            or candidate.lease_token is not None
            or candidate.lease_expires_at is not None
        ):
            raise ValueError("lease identity must be cleared when leaving RUNNING")
    elif (
        candidate.worker_id is not None
        or candidate.lease_token is not None
        or candidate.lease_expires_at is not None
    ):
        raise ValueError("lease identity fields are forbidden outside RUNNING step status")


def _require_updated_at_monotonic(current_updated_at: datetime, candidate_updated_at: datetime) -> None:
    if candidate_updated_at < current_updated_at:
        raise ValueError("updated_at must be >= current updated_at")


def _require_optimistic_version_increment(current_version: int, candidate_version: int) -> None:
    if candidate_version != current_version + 1:
        raise ValueError("optimistic_version must be current + 1")


def _validate_operation_status_edge(
    current_status: OperationStatus,
    candidate_status: OperationStatus,
    *,
    recovery_authorized: bool,
) -> None:
    allowed = _OPERATION_ALLOWED_TRANSITIONS.get(current_status, frozenset())
    if candidate_status not in allowed:
        raise ValueError("operation status transition is not allowed")
    if current_status is OperationStatus.MANUAL_RECOVERY_REQUIRED and not recovery_authorized:
        raise ValueError("recovery authorization is required")


def _validate_step_status_edge(
    current_status: StepStatus,
    candidate_status: StepStatus,
    *,
    recovery_authorized: bool,
) -> None:
    allowed = _STEP_ALLOWED_TRANSITIONS.get(current_status, frozenset())
    if candidate_status not in allowed:
        raise ValueError("step status transition is not allowed")
    if current_status is StepStatus.MANUAL_RECOVERY_REQUIRED and not recovery_authorized:
        raise ValueError("recovery authorization is required")
