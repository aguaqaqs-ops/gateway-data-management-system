"""Operation runtime state transition and write-precondition tests."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime

import pytest
from gateway_shared_kernel.jcs import canonicalize_json_value

from gateway_backend.operations import (
    OPERATION_RUNTIME_CONTRACT_VERSION,
    OperationDiagnostic,
    OperationRecord,
    OperationStatus,
    StepRecord,
    StepStatus,
    TransitionDisposition,
    WritePrecondition,
    validate_operation_transition,
    validate_step_transition,
    validate_write_precondition,
)

pytestmark = pytest.mark.unit

TS0 = datetime(2024, 1, 2, 3, 4, 5, tzinfo=UTC)
TS1 = datetime(2024, 1, 2, 3, 5, 0, tzinfo=UTC)
TS2 = datetime(2024, 1, 2, 3, 6, 0, tzinfo=UTC)
TS_LEASE = datetime(2024, 1, 2, 3, 10, 0, tzinfo=UTC)
DIAGNOSTIC = OperationDiagnostic(code="FAILED", message="owner reason")


def _operation_record(**changes: object) -> OperationRecord:
    defaults: dict[str, object] = {
        "contract_version": OPERATION_RUNTIME_CONTRACT_VERSION,
        "operation_id": "op-0001",
        "job_kind": "import.package",
        "job_contract_version": "backend-vnext/import-package/v1",
        "job_payload": canonicalize_json_value({}),
        "job_payload_ref": None,
        "business_refs": (),
        "artifact_refs": (),
        "repository_operation_id": None,
        "checkpoint_ref": None,
        "ready_closure_ref": None,
        "status": OperationStatus.QUEUED,
        "diagnostic": None,
        "cancel_requested": False,
        "created_at": TS0,
        "updated_at": TS0,
        "completed_at": None,
        "optimistic_version": 0,
    }
    defaults.update(changes)
    return OperationRecord(**defaults)  # type: ignore[arg-type]


def _step_record(**changes: object) -> StepRecord:
    defaults: dict[str, object] = {
        "contract_version": OPERATION_RUNTIME_CONTRACT_VERSION,
        "step_id": "step-0001",
        "operation_id": "op-0001",
        "step_name": "validate",
        "status": StepStatus.PENDING,
        "attempt_count": 0,
        "diagnostic": None,
        "cancel_requested": False,
        "retry_not_before": None,
        "worker_id": None,
        "lease_token": None,
        "lease_expires_at": None,
        "checkpoint_ref": None,
        "prior_output_refs": (),
        "created_at": TS0,
        "updated_at": TS0,
        "started_at": None,
        "completed_at": None,
        "optimistic_version": 0,
    }
    defaults.update(changes)
    return StepRecord(**defaults)  # type: ignore[arg-type]


def _running_step(*, version: int = 1) -> StepRecord:
    return _step_record(
        status=StepStatus.RUNNING,
        attempt_count=1,
        started_at=TS0,
        worker_id="worker-1",
        lease_token="lease-1",
        lease_expires_at=TS_LEASE,
        updated_at=TS1,
        optimistic_version=version,
    )


def _retry_wait_step(*, version: int = 2) -> StepRecord:
    return _step_record(
        status=StepStatus.RETRY_WAIT,
        attempt_count=1,
        started_at=TS0,
        diagnostic=DIAGNOSTIC,
        retry_not_before=TS1,
        updated_at=TS1,
        optimistic_version=version,
    )


def _manual_operation(*, version: int = 2) -> OperationRecord:
    return _operation_record(
        status=OperationStatus.MANUAL_RECOVERY_REQUIRED,
        diagnostic=DIAGNOSTIC,
        updated_at=TS1,
        optimistic_version=version,
    )


def _manual_step(*, version: int = 3) -> StepRecord:
    return _step_record(
        status=StepStatus.MANUAL_RECOVERY_REQUIRED,
        attempt_count=1,
        started_at=TS0,
        diagnostic=DIAGNOSTIC,
        updated_at=TS2,
        optimistic_version=version,
    )


def _terminal_operation(status: OperationStatus, *, version: int = 3) -> OperationRecord:
    return _operation_record(
        status=status,
        diagnostic=DIAGNOSTIC if status is OperationStatus.FAILED else None,
        completed_at=TS2,
        updated_at=TS2,
        optimistic_version=version,
    )


OPERATION_ALLOWED_TRANSITION_CASES: tuple[tuple[str, OperationRecord, OperationRecord], ...] = (
    (
        "queued-to-running",
        _operation_record(),
        _operation_record(status=OperationStatus.RUNNING, updated_at=TS1, optimistic_version=1),
    ),
    (
        "queued-to-cancelled",
        _operation_record(),
        _operation_record(
            status=OperationStatus.CANCELLED,
            completed_at=TS1,
            updated_at=TS1,
            optimistic_version=1,
        ),
    ),
    (
        "running-to-succeeded",
        _operation_record(status=OperationStatus.RUNNING, updated_at=TS1, optimistic_version=1),
        _operation_record(
            status=OperationStatus.SUCCEEDED,
            completed_at=TS2,
            updated_at=TS2,
            optimistic_version=2,
        ),
    ),
    (
        "manual-to-running",
        _manual_operation(version=2),
        _operation_record(status=OperationStatus.RUNNING, updated_at=TS2, optimistic_version=3),
    ),
)

STEP_ALLOWED_TRANSITION_CASES: tuple[tuple[str, StepRecord, StepRecord], ...] = (
    (
        "pending-to-running",
        _step_record(),
        _step_record(
            status=StepStatus.RUNNING,
            attempt_count=1,
            started_at=TS1,
            worker_id="worker-1",
            lease_token="lease-1",
            lease_expires_at=TS_LEASE,
            updated_at=TS1,
            optimistic_version=1,
        ),
    ),
    (
        "running-to-succeeded",
        _running_step(),
        _step_record(
            status=StepStatus.SUCCEEDED,
            attempt_count=1,
            started_at=TS0,
            completed_at=TS2,
            updated_at=TS2,
            optimistic_version=2,
        ),
    ),
    (
        "retry-wait-to-running",
        _retry_wait_step(version=2),
        _step_record(
            status=StepStatus.RUNNING,
            attempt_count=2,
            started_at=TS0,
            worker_id="worker-2",
            lease_token="lease-2",
            lease_expires_at=TS_LEASE,
            updated_at=TS2,
            optimistic_version=3,
        ),
    ),
    (
        "manual-to-running",
        _manual_step(version=3),
        _step_record(
            status=StepStatus.RUNNING,
            attempt_count=1,
            started_at=TS0,
            worker_id="worker-3",
            lease_token="lease-3",
            lease_expires_at=TS_LEASE,
            updated_at=TS2,
            optimistic_version=4,
        ),
    ),
)

OPERATION_DENIED_TRANSITION_CASES: tuple[tuple[str, OperationRecord, OperationRecord, str], ...] = (
    (
        "queued-to-succeeded",
        _operation_record(),
        _operation_record(
            status=OperationStatus.SUCCEEDED,
            completed_at=TS1,
            updated_at=TS1,
            optimistic_version=1,
        ),
        "operation status transition is not allowed",
    ),
    (
        "manual-to-cancelled",
        _manual_operation(),
        _operation_record(
            status=OperationStatus.CANCELLED,
            completed_at=TS2,
            updated_at=TS2,
            optimistic_version=3,
        ),
        "operation status transition is not allowed",
    ),
    (
        "manual-without-recovery",
        _manual_operation(),
        _operation_record(
            status=OperationStatus.RUNNING,
            updated_at=TS2,
            optimistic_version=3,
        ),
        "recovery authorization is required",
    ),
    (
        "identity-change",
        _operation_record(),
        _operation_record(
            operation_id="op-0002",
            status=OperationStatus.RUNNING,
            updated_at=TS1,
            optimistic_version=1,
        ),
        "operation_id is immutable",
    ),
    (
        "version-not-incremented",
        _operation_record(),
        _operation_record(status=OperationStatus.RUNNING, updated_at=TS1, optimistic_version=0),
        "optimistic_version must be current",
    ),
)

STEP_DENIED_TRANSITION_CASES: tuple[tuple[str, StepRecord, StepRecord, str], ...] = (
    (
        "pending-to-succeeded",
        _step_record(),
        _step_record(
            status=StepStatus.SUCCEEDED,
            attempt_count=1,
            started_at=TS1,
            completed_at=TS1,
            updated_at=TS1,
            optimistic_version=1,
        ),
        "step status transition is not allowed",
    ),
    (
        "pending-to-running-with-wrong-attempt",
        _step_record(),
        _step_record(
            status=StepStatus.RUNNING,
            attempt_count=2,
            started_at=TS1,
            worker_id="worker-1",
            lease_token="lease-1",
            lease_expires_at=TS_LEASE,
            updated_at=TS1,
            optimistic_version=1,
        ),
        "attempt_count must increment",
    ),
    (
        "manual-without-recovery",
        _manual_step(),
        _step_record(
            status=StepStatus.RUNNING,
            attempt_count=1,
            started_at=TS0,
            worker_id="worker-3",
            lease_token="lease-3",
            lease_expires_at=TS_LEASE,
            updated_at=TS2,
            optimistic_version=4,
        ),
        "recovery authorization is required",
    ),
    (
        "identity-change",
        _step_record(),
        _step_record(
            step_id="step-0002",
            status=StepStatus.RUNNING,
            attempt_count=1,
            started_at=TS1,
            worker_id="worker-1",
            lease_token="lease-1",
            lease_expires_at=TS_LEASE,
            updated_at=TS1,
            optimistic_version=1,
        ),
        "step_id is immutable",
    ),
)

WRITE_PRECONDITION_ACCEPT_CASES: tuple[tuple[str, int, str | None, str | None, WritePrecondition], ...] = (
    ("operation-level", 3, None, None, WritePrecondition(3, None, None)),
    (
        "leased-step",
        2,
        "worker-1",
        "lease-1",
        WritePrecondition(2, "worker-1", "lease-1"),
    ),
)

WRITE_PRECONDITION_DENIED_CASES: tuple[
    tuple[str, int, str | None, str | None, WritePrecondition, str],
    ...,
] = (
    (
        "version-mismatch",
        2,
        None,
        None,
        WritePrecondition(3, None, None),
        "optimistic version mismatch",
    ),
    (
        "partial-lease-worker-only",
        2,
        "worker-1",
        "lease-1",
        WritePrecondition(2, "worker-1", None),
        "worker_id and lease_token must both be set or both null",
    ),
    (
        "lease-mismatch",
        2,
        "worker-1",
        "lease-1",
        WritePrecondition(2, "worker-2", "lease-2"),
        "lease identity mismatch",
    ),
    (
        "null-precondition-with-current-lease",
        2,
        "worker-1",
        "lease-1",
        WritePrecondition(2, None, None),
        "lease identity must be null",
    ),
)


@pytest.mark.parametrize(("name", "current", "candidate"), OPERATION_ALLOWED_TRANSITION_CASES)
def test_operation_allowed_transitions_return_apply(
    name: str,
    current: OperationRecord,
    candidate: OperationRecord,
) -> None:
    del name
    kwargs: dict[str, bool] = {}
    if current.status is OperationStatus.MANUAL_RECOVERY_REQUIRED:
        kwargs["recovery_authorized"] = True
    assert validate_operation_transition(current, candidate, **kwargs) is TransitionDisposition.APPLY


@pytest.mark.parametrize(("name", "current", "candidate"), STEP_ALLOWED_TRANSITION_CASES)
def test_step_allowed_transitions_return_apply(
    name: str,
    current: StepRecord,
    candidate: StepRecord,
) -> None:
    del name
    kwargs: dict[str, bool] = {}
    if current.status is StepStatus.MANUAL_RECOVERY_REQUIRED:
        kwargs["recovery_authorized"] = True
    assert validate_step_transition(current, candidate, **kwargs) is TransitionDisposition.APPLY


@pytest.mark.parametrize(("name", "current", "candidate", "match"), OPERATION_DENIED_TRANSITION_CASES)
def test_operation_denied_transitions_raise(
    name: str,
    current: OperationRecord,
    candidate: OperationRecord,
    match: str,
) -> None:
    del name
    with pytest.raises(ValueError, match=match):
        validate_operation_transition(current, candidate)


@pytest.mark.parametrize(("name", "current", "candidate", "match"), STEP_DENIED_TRANSITION_CASES)
def test_step_denied_transitions_raise(
    name: str,
    current: StepRecord,
    candidate: StepRecord,
    match: str,
) -> None:
    del name
    with pytest.raises(ValueError, match=match):
        validate_step_transition(current, candidate)


def test_operation_terminal_duplicate_idempotent() -> None:
    current = _terminal_operation(OperationStatus.SUCCEEDED)
    assert (
        validate_operation_transition(current, current) is TransitionDisposition.IDEMPOTENT
    )


def test_operation_terminal_conflicting_duplicate_rejected() -> None:
    current = _terminal_operation(OperationStatus.SUCCEEDED, version=3)
    candidate = replace(current, optimistic_version=4, updated_at=TS2)
    with pytest.raises(ValueError, match="conflicting terminal duplicate"):
        validate_operation_transition(current, candidate)


def test_step_terminal_duplicate_idempotent() -> None:
    current = _step_record(
        status=StepStatus.CANCELLED,
        completed_at=TS2,
        updated_at=TS2,
        optimistic_version=3,
    )
    assert validate_step_transition(current, current) is TransitionDisposition.IDEMPOTENT


def test_non_terminal_same_status_publication_rejected() -> None:
    current = _operation_record(status=OperationStatus.RUNNING, updated_at=TS1, optimistic_version=1)
    candidate = replace(current, optimistic_version=2, updated_at=TS2)
    with pytest.raises(ValueError, match="same-state publication only allowed for final terminal"):
        validate_operation_transition(current, candidate)


@pytest.mark.parametrize(
    ("name", "current_version", "current_worker", "current_lease", "precondition"),
    WRITE_PRECONDITION_ACCEPT_CASES,
)
def test_write_precondition_accepts_valid_cases(
    name: str,
    current_version: int,
    current_worker: str | None,
    current_lease: str | None,
    precondition: WritePrecondition,
) -> None:
    del name
    validate_write_precondition(
        current_optimistic_version=current_version,
        current_worker_id=current_worker,
        current_lease_token=current_lease,
        precondition=precondition,
    )


@pytest.mark.parametrize(
    ("name", "current_version", "current_worker", "current_lease", "precondition", "match"),
    WRITE_PRECONDITION_DENIED_CASES,
)
def test_write_precondition_rejects_invalid_cases(
    name: str,
    current_version: int,
    current_worker: str | None,
    current_lease: str | None,
    precondition: WritePrecondition,
    match: str,
) -> None:
    del name
    with pytest.raises(ValueError, match=match):
        validate_write_precondition(
            current_optimistic_version=current_version,
            current_worker_id=current_worker,
            current_lease_token=current_lease,
            precondition=precondition,
        )


def test_transition_guards_are_deterministic() -> None:
    current = _operation_record()
    candidate = _operation_record(
        status=OperationStatus.RUNNING,
        updated_at=TS1,
        optimistic_version=1,
    )
    first = validate_operation_transition(current, candidate)
    second = validate_operation_transition(current, candidate)
    assert first is second is TransitionDisposition.APPLY


def test_manual_recovery_allowed_with_authorization() -> None:
    current = _manual_operation()
    candidate = _operation_record(
        status=OperationStatus.RUNNING,
        updated_at=TS2,
        optimistic_version=3,
    )
    assert (
        validate_operation_transition(current, candidate, recovery_authorized=True)
        is TransitionDisposition.APPLY
    )
