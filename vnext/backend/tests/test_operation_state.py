"""Operation runtime state transition and write-precondition tests."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime

import pytest
from gateway_shared_kernel import DigestRef
from gateway_shared_kernel.jcs import canonicalize_json_value

from gateway_backend.artifacts import ArtifactRef
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
from gateway_backend.operations.state import (
    _OPERATION_ALLOWED_TRANSITIONS,
    _STEP_ALLOWED_TRANSITIONS,
)

pytestmark = pytest.mark.unit

TS0 = datetime(2024, 1, 2, 3, 4, 5, tzinfo=UTC)
TS1 = datetime(2024, 1, 2, 3, 5, 0, tzinfo=UTC)
TS2 = datetime(2024, 1, 2, 3, 6, 0, tzinfo=UTC)
TS_LEASE = datetime(2024, 1, 2, 3, 10, 0, tzinfo=UTC)
TS_LEASE_LATER = datetime(2024, 1, 2, 3, 11, 0, tzinfo=UTC)
DIAGNOSTIC = OperationDiagnostic(code="FAILED", message="owner reason")

EXPECTED_OPERATION_ALLOWED_TRANSITIONS = {
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

EXPECTED_STEP_ALLOWED_TRANSITIONS = {
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


def _artifact_ref(artifact_id: str) -> ArtifactRef:
    return ArtifactRef(
        artifact_id=artifact_id,
        media_type="application/octet-stream",
        size_bytes=3,
        raw_sha256=DigestRef("sha256:" + "a" * 64),
    )


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


def _operation_for_status(
    status: OperationStatus,
    *,
    version: int,
    updated_at: datetime,
) -> OperationRecord:
    changes: dict[str, object] = {
        "status": status,
        "optimistic_version": version,
        "updated_at": updated_at,
        "completed_at": None,
        "diagnostic": None,
    }
    if status.is_final_terminal():
        changes["completed_at"] = updated_at
    if status in {OperationStatus.FAILED, OperationStatus.MANUAL_RECOVERY_REQUIRED}:
        changes["diagnostic"] = DIAGNOSTIC
    return _operation_record(**changes)


def _step_for_status(
    status: StepStatus,
    *,
    version: int,
    updated_at: datetime,
) -> StepRecord:
    changes: dict[str, object] = {
        "status": status,
        "optimistic_version": version,
        "updated_at": updated_at,
        "attempt_count": 0,
        "started_at": None,
        "completed_at": None,
        "diagnostic": None,
        "retry_not_before": None,
        "worker_id": None,
        "lease_token": None,
        "lease_expires_at": None,
    }
    if status is StepStatus.RUNNING:
        changes.update(
            {
                "attempt_count": 1,
                "started_at": TS0,
                "worker_id": "worker-1",
                "lease_token": "lease-1",
                "lease_expires_at": TS_LEASE,
            }
        )
    elif status is StepStatus.RETRY_WAIT:
        changes.update(
            {
                "attempt_count": 1,
                "started_at": TS0,
                "diagnostic": DIAGNOSTIC,
                "retry_not_before": updated_at,
            }
        )
    elif status is StepStatus.MANUAL_RECOVERY_REQUIRED:
        changes.update(
            {
                "attempt_count": 1,
                "started_at": TS0,
                "diagnostic": DIAGNOSTIC,
            }
        )
    elif status.is_final_terminal():
        changes["completed_at"] = updated_at
        if status is StepStatus.FAILED:
            changes.update(
                {
                    "attempt_count": 1,
                    "started_at": TS0,
                    "diagnostic": DIAGNOSTIC,
                }
            )
        elif status is StepStatus.SUCCEEDED:
            changes.update({"attempt_count": 1, "started_at": TS0})
        elif status is StepStatus.CANCELLED and version > 0:
            changes.update({"attempt_count": 1, "started_at": TS0})
    return _step_record(**changes)


def _operation_candidate(
    current: OperationRecord,
    target: OperationStatus,
    **changes: object,
) -> OperationRecord:
    next_version = current.optimistic_version + 1
    next_updated = TS1 if next_version == 1 else TS2
    payload: dict[str, object] = {
        "status": target,
        "optimistic_version": next_version,
        "updated_at": next_updated,
        "cancel_requested": current.cancel_requested,
        "completed_at": None,
        "diagnostic": None,
    }
    if target.is_final_terminal():
        payload["completed_at"] = next_updated
    if target in {OperationStatus.FAILED, OperationStatus.MANUAL_RECOVERY_REQUIRED}:
        payload["diagnostic"] = DIAGNOSTIC
    payload.update(changes)
    return _operation_record(**payload)


def _step_candidate(
    current: StepRecord,
    target: StepStatus,
    **changes: object,
) -> StepRecord:
    next_version = current.optimistic_version + 1
    next_updated = TS2
    payload: dict[str, object] = {
        "status": target,
        "optimistic_version": next_version,
        "updated_at": next_updated,
        "cancel_requested": current.cancel_requested,
        "attempt_count": current.attempt_count,
        "started_at": current.started_at,
        "completed_at": None,
        "diagnostic": None,
        "retry_not_before": None,
        "worker_id": None,
        "lease_token": None,
        "lease_expires_at": None,
    }
    if target is StepStatus.PENDING:
        payload.update(
            {
                "attempt_count": 0,
                "started_at": None,
                "completed_at": None,
                "diagnostic": None,
                "retry_not_before": None,
                "worker_id": None,
                "lease_token": None,
                "lease_expires_at": None,
            }
        )
    elif target is StepStatus.RUNNING:
        if current.status in {StepStatus.PENDING, StepStatus.RETRY_WAIT}:
            payload["attempt_count"] = current.attempt_count + 1
        payload["started_at"] = current.started_at or TS0
        payload["worker_id"] = changes.pop("worker_id", f"worker-{next_version}")
        payload["lease_token"] = changes.pop("lease_token", f"lease-{next_version}")
        payload["lease_expires_at"] = changes.pop("lease_expires_at", TS_LEASE)
    elif target is StepStatus.RETRY_WAIT:
        payload.update(
            {
                "attempt_count": max(current.attempt_count, 1),
                "started_at": current.started_at or TS0,
                "diagnostic": DIAGNOSTIC,
                "retry_not_before": next_updated,
            }
        )
    elif target is StepStatus.MANUAL_RECOVERY_REQUIRED:
        payload.update(
            {
                "attempt_count": max(current.attempt_count, 1),
                "started_at": current.started_at or TS0,
                "diagnostic": DIAGNOSTIC,
            }
        )
    elif target.is_final_terminal():
        payload["completed_at"] = next_updated
        if target is StepStatus.FAILED:
            payload.update(
                {
                    "attempt_count": max(current.attempt_count, 1),
                    "started_at": current.started_at or TS0,
                    "diagnostic": DIAGNOSTIC,
                }
            )
        elif target is StepStatus.SUCCEEDED:
            payload.update(
                {
                    "attempt_count": max(current.attempt_count, 1),
                    "started_at": current.started_at or TS0,
                }
            )
        elif target is StepStatus.CANCELLED:
            if current.status is StepStatus.PENDING:
                payload.update({"attempt_count": 0, "started_at": None})
            else:
                payload.update(
                    {
                        "attempt_count": max(current.attempt_count, 1),
                        "started_at": current.started_at or TS0,
                    }
                )
    payload.update(changes)
    return _step_record(**payload)


def _operation_current_for_status(status: OperationStatus) -> OperationRecord:
    if status is OperationStatus.QUEUED:
        return _operation_for_status(status, version=0, updated_at=TS0)
    if status is OperationStatus.RUNNING:
        return _operation_for_status(status, version=1, updated_at=TS1)
    if status is OperationStatus.MANUAL_RECOVERY_REQUIRED:
        return _operation_for_status(status, version=2, updated_at=TS1)
    return _operation_for_status(status, version=3, updated_at=TS2)


def _step_current_for_status(status: StepStatus) -> StepRecord:
    if status is StepStatus.PENDING:
        return _step_for_status(status, version=0, updated_at=TS0)
    if status is StepStatus.RUNNING:
        return _step_for_status(status, version=1, updated_at=TS1)
    if status is StepStatus.RETRY_WAIT:
        return _step_for_status(status, version=2, updated_at=TS1)
    if status is StepStatus.MANUAL_RECOVERY_REQUIRED:
        return _step_for_status(status, version=3, updated_at=TS2)
    return _step_for_status(status, version=3, updated_at=TS2)


def _build_operation_allowed_cases() -> tuple[tuple[str, OperationRecord, OperationRecord], ...]:
    cases: list[tuple[str, OperationRecord, OperationRecord]] = []
    for from_status, targets in EXPECTED_OPERATION_ALLOWED_TRANSITIONS.items():
        current = _operation_current_for_status(from_status)
        for target in sorted(targets, key=lambda item: item.value):
            name = f"{from_status.value}-to-{target.value}"
            candidate = _operation_candidate(current, target)
            cases.append((name, current, candidate))
    return tuple(cases)


def _build_step_allowed_cases() -> tuple[tuple[str, StepRecord, StepRecord], ...]:
    cases: list[tuple[str, StepRecord, StepRecord]] = []
    for from_status, targets in EXPECTED_STEP_ALLOWED_TRANSITIONS.items():
        current = _step_current_for_status(from_status)
        for target in sorted(targets, key=lambda item: item.value):
            name = f"{from_status.value}-to-{target.value}"
            candidate = _step_candidate(current, target)
            cases.append((name, current, candidate))
    return tuple(cases)


def _build_operation_denied_cases() -> tuple[tuple[str, OperationRecord, OperationRecord, str], ...]:
    cases: list[tuple[str, OperationRecord, OperationRecord, str]] = []
    for from_status in OperationStatus:
        if from_status.is_final_terminal():
            current = _operation_current_for_status(from_status)
            for target in OperationStatus:
                if target == from_status:
                    continue
                candidate = _operation_candidate(current, target)
                name = f"{from_status.value}-to-{target.value}"
                cases.append(
                    (name, current, candidate, "operation status transition is not allowed")
                )
            continue
        allowed = EXPECTED_OPERATION_ALLOWED_TRANSITIONS.get(from_status, frozenset())
        current = _operation_current_for_status(from_status)
        for target in OperationStatus:
            if target == from_status or target in allowed:
                continue
            candidate = _operation_candidate(current, target)
            name = f"{from_status.value}-to-{target.value}"
            cases.append(
                (name, current, candidate, "operation status transition is not allowed")
            )
    return tuple(cases)


def _build_step_denied_cases() -> tuple[tuple[str, StepRecord, StepRecord, str], ...]:
    cases: list[tuple[str, StepRecord, StepRecord, str]] = []
    for from_status in StepStatus:
        if from_status.is_final_terminal():
            current = _step_current_for_status(from_status)
            for target in StepStatus:
                if target == from_status:
                    continue
                candidate = _step_candidate(current, target)
                name = f"{from_status.value}-to-{target.value}"
                cases.append((name, current, candidate, "step status transition is not allowed"))
            continue
        allowed = EXPECTED_STEP_ALLOWED_TRANSITIONS.get(from_status, frozenset())
        current = _step_current_for_status(from_status)
        for target in StepStatus:
            if target == from_status or target in allowed:
                continue
            candidate = _step_candidate(current, target)
            name = f"{from_status.value}-to-{target.value}"
            cases.append((name, current, candidate, "step status transition is not allowed"))
    return tuple(cases)


OPERATION_ALLOWED_TRANSITION_CASES = _build_operation_allowed_cases()
STEP_ALLOWED_TRANSITION_CASES = _build_step_allowed_cases()
OPERATION_DENIED_TRANSITION_CASES = _build_operation_denied_cases()
STEP_DENIED_TRANSITION_CASES = _build_step_denied_cases()

MANUAL_OPERATION_RECOVERY_DENIED_CASES: tuple[
    tuple[str, OperationStatus, str],
    ...,
] = (
    ("manual-to-running", OperationStatus.RUNNING, "recovery authorization is required"),
    ("manual-to-succeeded", OperationStatus.SUCCEEDED, "recovery authorization is required"),
    ("manual-to-failed", OperationStatus.FAILED, "recovery authorization is required"),
)

MANUAL_STEP_RECOVERY_DENIED_CASES: tuple[tuple[str, StepStatus, str], ...] = (
    ("manual-to-running", StepStatus.RUNNING, "recovery authorization is required"),
    ("manual-to-succeeded", StepStatus.SUCCEEDED, "recovery authorization is required"),
    ("manual-to-failed", StepStatus.FAILED, "recovery authorization is required"),
)

OPERATION_MUTATION_DENIED_CASES: tuple[tuple[str, OperationRecord, OperationRecord, str], ...] = (
    (
        "repository-operation-id-rewrite",
        _operation_record(repository_operation_id="repo-op-1", updated_at=TS1, optimistic_version=1),
        _operation_record(
            repository_operation_id="repo-op-2",
            updated_at=TS2,
            optimistic_version=2,
            status=OperationStatus.RUNNING,
        ),
        "repository_operation_id can only be set once",
    ),
    (
        "ready-closure-ref-rewrite",
        _operation_record(
            ready_closure_ref=_artifact_ref("artifact-closure-1"),
            updated_at=TS1,
            optimistic_version=1,
        ),
        _operation_record(
            ready_closure_ref=_artifact_ref("artifact-closure-2"),
            updated_at=TS2,
            optimistic_version=2,
            status=OperationStatus.RUNNING,
        ),
        "ready_closure_ref can only be set once",
    ),
    (
        "artifact-refs-not-append",
        _operation_record(
            artifact_refs=(_artifact_ref("artifact-a"),),
            updated_at=TS1,
            optimistic_version=1,
        ),
        _operation_record(
            artifact_refs=(_artifact_ref("artifact-b"),),
            updated_at=TS2,
            optimistic_version=2,
            status=OperationStatus.RUNNING,
        ),
        "artifact_refs can only append unique refs",
    ),
    (
        "updated-at-regression",
        _operation_record(
            status=OperationStatus.RUNNING,
            updated_at=TS1,
            optimistic_version=1,
        ),
        _operation_record(
            status=OperationStatus.SUCCEEDED,
            completed_at=TS0,
            updated_at=TS0,
            optimistic_version=2,
        ),
        "updated_at must be >=",
    ),
    (
        "job-payload-change",
        _operation_record(),
        _operation_record(
            job_payload=canonicalize_json_value({"changed": True}),
            status=OperationStatus.RUNNING,
            updated_at=TS1,
            optimistic_version=1,
        ),
        "job_payload is immutable",
    ),
    (
        "cancel-requested-reset",
        _operation_record(cancel_requested=True, updated_at=TS1, optimistic_version=1),
        _operation_record(
            cancel_requested=False,
            status=OperationStatus.RUNNING,
            updated_at=TS2,
            optimistic_version=2,
        ),
        "cancel_requested cannot be reset",
    ),
)

STEP_MUTATION_DENIED_CASES: tuple[tuple[str, StepRecord, StepRecord, str], ...] = (
    (
        "prior-output-refs-change",
        _step_record(prior_output_refs=(_artifact_ref("artifact-out-1"),)),
        _step_record(
            prior_output_refs=(_artifact_ref("artifact-out-2"),),
            status=StepStatus.RUNNING,
            attempt_count=1,
            started_at=TS1,
            worker_id="worker-1",
            lease_token="lease-1",
            lease_expires_at=TS_LEASE,
            updated_at=TS1,
            optimistic_version=1,
        ),
        "prior_output_refs are immutable",
    ),
)

WRITE_PRECONDITION_ACCEPT_CASES: tuple[tuple[str, int, str | None, str | None, WritePrecondition], ...] = (
    ("operation-heartbeat", 5, None, None, WritePrecondition(5, None, None)),
    ("operation-checkpoint", 5, None, None, WritePrecondition(5, None, None)),
    (
        "leased-step-heartbeat",
        2,
        "worker-1",
        "lease-1",
        WritePrecondition(2, "worker-1", "lease-1"),
    ),
    (
        "leased-step-checkpoint",
        2,
        "worker-1",
        "lease-1",
        WritePrecondition(2, "worker-1", "lease-1"),
    ),
    ("claim-unleased-step", 0, None, None, WritePrecondition(0, None, None)),
)

WRITE_PRECONDITION_DENIED_CASES: tuple[
    tuple[str, int, str | None, str | None, WritePrecondition, str],
    ...,
] = (
    (
        "operation-terminal-stale-version",
        5,
        None,
        None,
        WritePrecondition(4, None, None),
        "optimistic version mismatch",
    ),
    (
        "leased-step-checkpoint-stale-version",
        2,
        "worker-1",
        "lease-1",
        WritePrecondition(1, "worker-1", "lease-1"),
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

WRITE_PRECONDITION_CONSTRUCTOR_FAULTS: tuple[tuple[str, dict[str, object], str], ...] = (
    (
        "expected-version-bool",
        {"expected_optimistic_version": True, "worker_id": None, "lease_token": None},
        "expected_optimistic_version must be a non-negative I-JSON safe integer",
    ),
    (
        "expected-version-negative",
        {"expected_optimistic_version": -1, "worker_id": None, "lease_token": None},
        "expected_optimistic_version must be a non-negative I-JSON safe integer",
    ),
    (
        "expected-version-float",
        {"expected_optimistic_version": 1.0, "worker_id": None, "lease_token": None},
        "expected_optimistic_version must be a non-negative I-JSON safe integer",
    ),
    (
        "worker-id-bool",
        {"expected_optimistic_version": 1, "worker_id": True, "lease_token": "lease-1"},
        "worker_id must be a string or None",
    ),
)

WRITE_PRECONDITION_IDENTITY_ACCEPT_CASES: tuple[tuple[str, str, str], ...] = (
    ("one-byte-identities", "w", "l"),
    ("maximum-byte-identities", "w" * 255, "l" * 255),
)

WRITE_PRECONDITION_IDENTITY_FAULTS: tuple[tuple[str, str, str, str], ...] = (
    ("worker-empty", "", "lease-1", "1..255"),
    ("worker-too-long", "w" * 256, "lease-1", "1..255"),
    ("worker-control", "worker\x00", "lease-1", "control"),
    ("worker-unix-path", "/tmp/worker", "lease-1", "host path"),
    ("worker-windows-path", "C:\\worker", "lease-1", "host path"),
    ("lease-empty", "worker-1", "", "1..255"),
    ("lease-too-long", "worker-1", "l" * 256, "1..255"),
    ("lease-control", "worker-1", "lease\x00", "control"),
    ("lease-unix-path", "worker-1", "/tmp/lease", "host path"),
    ("lease-windows-path", "worker-1", "C:\\lease", "host path"),
)

OPERATION_TERMINAL_STATUSES = tuple(
    status for status in OperationStatus if status.is_final_terminal()
)
STEP_TERMINAL_STATUSES = tuple(status for status in StepStatus if status.is_final_terminal())


def test_operation_transition_matrix_inventory_matches_state_module() -> None:
    assert EXPECTED_OPERATION_ALLOWED_TRANSITIONS == _OPERATION_ALLOWED_TRANSITIONS
    assert EXPECTED_STEP_ALLOWED_TRANSITIONS == _STEP_ALLOWED_TRANSITIONS


def test_operation_allowed_cases_cover_complete_matrix() -> None:
    covered = {
        (current.status, candidate.status)
        for _, current, candidate in OPERATION_ALLOWED_TRANSITION_CASES
    }
    expected = {
        (from_status, target)
        for from_status, targets in EXPECTED_OPERATION_ALLOWED_TRANSITIONS.items()
        for target in targets
    }
    assert covered == expected


def test_step_allowed_cases_cover_complete_matrix() -> None:
    covered = {
        (current.status, candidate.status)
        for _, current, candidate in STEP_ALLOWED_TRANSITION_CASES
    }
    expected = {
        (from_status, target)
        for from_status, targets in EXPECTED_STEP_ALLOWED_TRANSITIONS.items()
        for target in targets
    }
    assert covered == expected


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


@pytest.mark.parametrize(("name", "target", "match"), MANUAL_OPERATION_RECOVERY_DENIED_CASES)
def test_manual_operation_recovery_edges_require_authorization(
    name: str,
    target: OperationStatus,
    match: str,
) -> None:
    del name
    current = _operation_current_for_status(OperationStatus.MANUAL_RECOVERY_REQUIRED)
    candidate = _operation_candidate(current, target)
    with pytest.raises(ValueError, match=match):
        validate_operation_transition(current, candidate)


@pytest.mark.parametrize(("name", "target", "match"), MANUAL_STEP_RECOVERY_DENIED_CASES)
def test_manual_step_recovery_edges_require_authorization(
    name: str,
    target: StepStatus,
    match: str,
) -> None:
    del name
    current = _step_current_for_status(StepStatus.MANUAL_RECOVERY_REQUIRED)
    candidate = _step_candidate(current, target)
    with pytest.raises(ValueError, match=match):
        validate_step_transition(current, candidate)


@pytest.mark.parametrize(("name", "current", "candidate", "match"), OPERATION_MUTATION_DENIED_CASES)
def test_operation_mutation_rules_rejected_on_transition(
    name: str,
    current: OperationRecord,
    candidate: OperationRecord,
    match: str,
) -> None:
    del name
    with pytest.raises(ValueError, match=match):
        validate_operation_transition(current, candidate)


@pytest.mark.parametrize(("name", "current", "candidate", "match"), STEP_MUTATION_DENIED_CASES)
def test_step_mutation_rules_rejected_on_transition(
    name: str,
    current: StepRecord,
    candidate: StepRecord,
    match: str,
) -> None:
    del name
    with pytest.raises(ValueError, match=match):
        validate_step_transition(current, candidate)


def test_operation_checkpoint_ref_can_change_on_allowed_transition() -> None:
    current = _operation_current_for_status(OperationStatus.RUNNING)
    candidate = _operation_candidate(
        current,
        OperationStatus.SUCCEEDED,
        checkpoint_ref=_artifact_ref("artifact-checkpoint-new"),
    )
    assert validate_operation_transition(current, candidate) is TransitionDisposition.APPLY


def test_cancel_requested_can_set_during_allowed_transition() -> None:
    current = _operation_current_for_status(OperationStatus.QUEUED)
    candidate = _operation_candidate(
        current,
        OperationStatus.RUNNING,
        cancel_requested=True,
    )
    assert validate_operation_transition(current, candidate) is TransitionDisposition.APPLY
    assert candidate.cancel_requested is True


def test_cancel_requested_cannot_reset() -> None:
    current = _operation_record(
        status=OperationStatus.RUNNING,
        cancel_requested=True,
        updated_at=TS1,
        optimistic_version=1,
    )
    candidate = _operation_candidate(current, OperationStatus.SUCCEEDED, cancel_requested=False)
    with pytest.raises(ValueError, match="cancel_requested cannot be reset"):
        validate_operation_transition(current, candidate)


def test_same_status_operation_heartbeat_uses_mutation_scope_guard() -> None:
    current = _operation_current_for_status(OperationStatus.RUNNING)
    heartbeat = replace(current, optimistic_version=2, updated_at=TS2)
    checkpoint = replace(
        current,
        checkpoint_ref=_artifact_ref("artifact-heartbeat-checkpoint"),
        optimistic_version=2,
        updated_at=TS2,
    )
    cancel_intent = replace(current, cancel_requested=True, optimistic_version=2, updated_at=TS2)

    assert validate_operation_transition(current, heartbeat) is TransitionDisposition.APPLY
    assert validate_operation_transition(current, checkpoint) is TransitionDisposition.APPLY
    assert validate_operation_transition(current, cancel_intent) is TransitionDisposition.APPLY


def test_same_status_operation_mutation_scope_rejects_immutable_and_reset() -> None:
    current = _operation_current_for_status(OperationStatus.RUNNING)
    changed_payload = replace(
        current,
        job_payload=canonicalize_json_value({"changed": True}),
        optimistic_version=2,
        updated_at=TS2,
    )
    with pytest.raises(ValueError, match="job_payload is immutable"):
        validate_operation_transition(current, changed_payload)

    cancelled = replace(current, cancel_requested=True)
    reset = replace(cancelled, cancel_requested=False, optimistic_version=2, updated_at=TS2)
    with pytest.raises(ValueError, match="cancel_requested cannot be reset"):
        validate_operation_transition(cancelled, reset)


def test_same_status_step_heartbeat_checkpoint_and_cancel_use_mutation_scope_guard() -> None:
    current = _step_current_for_status(StepStatus.RUNNING)
    heartbeat = replace(
        current,
        lease_expires_at=TS_LEASE_LATER,
        optimistic_version=2,
        updated_at=TS2,
    )
    checkpoint = replace(
        current,
        checkpoint_ref=_artifact_ref("artifact-step-heartbeat-checkpoint"),
        optimistic_version=2,
        updated_at=TS2,
    )
    cancel_intent = replace(current, cancel_requested=True, optimistic_version=2, updated_at=TS2)

    assert validate_step_transition(current, heartbeat) is TransitionDisposition.APPLY
    assert validate_step_transition(current, checkpoint) is TransitionDisposition.APPLY
    assert validate_step_transition(current, cancel_intent) is TransitionDisposition.APPLY


def test_same_status_step_mutation_scope_rejects_lease_identity_change() -> None:
    current = _step_current_for_status(StepStatus.RUNNING)
    candidate = replace(
        current,
        worker_id="worker-2",
        lease_token="lease-2",
        optimistic_version=2,
        updated_at=TS2,
    )
    with pytest.raises(ValueError, match="immutable during RUNNING heartbeat"):
        validate_step_transition(current, candidate)


def test_manual_attention_rejects_same_status_mutation() -> None:
    operation = _operation_current_for_status(OperationStatus.MANUAL_RECOVERY_REQUIRED)
    operation_candidate = replace(operation, optimistic_version=3, updated_at=TS2)
    with pytest.raises(ValueError, match="same-status mutation is forbidden"):
        validate_operation_transition(operation, operation_candidate)

    step = _step_current_for_status(StepStatus.MANUAL_RECOVERY_REQUIRED)
    step_candidate = replace(step, optimistic_version=4, updated_at=TS2)
    with pytest.raises(ValueError, match="same-status mutation is forbidden"):
        validate_step_transition(step, step_candidate)


def test_retry_transition_preserves_first_started_at() -> None:
    current = _step_current_for_status(StepStatus.RETRY_WAIT)
    candidate = _step_candidate(current, StepStatus.RUNNING, started_at=TS1)
    with pytest.raises(ValueError, match="started_at is immutable"):
        validate_step_transition(current, candidate)


def test_authorized_manual_recovery_preserves_first_started_at() -> None:
    current = _step_current_for_status(StepStatus.MANUAL_RECOVERY_REQUIRED)
    candidate = _step_candidate(current, StepStatus.RUNNING, started_at=TS1)
    with pytest.raises(ValueError, match="started_at is immutable"):
        validate_step_transition(current, candidate, recovery_authorized=True)


def test_cancelled_publication_is_explicit_status_edge() -> None:
    current = _operation_current_for_status(OperationStatus.RUNNING)
    candidate = _operation_candidate(current, OperationStatus.CANCELLED)
    assert validate_operation_transition(current, candidate) is TransitionDisposition.APPLY


def test_running_operation_may_supersede_structurally() -> None:
    current = _operation_current_for_status(OperationStatus.RUNNING)
    candidate = _operation_candidate(current, OperationStatus.SUPERSEDED)
    assert validate_operation_transition(current, candidate) is TransitionDisposition.APPLY


def test_manual_attention_status_not_final_terminal() -> None:
    assert not OperationStatus.MANUAL_RECOVERY_REQUIRED.is_final_terminal()
    assert not StepStatus.MANUAL_RECOVERY_REQUIRED.is_final_terminal()
    assert OperationStatus.MANUAL_RECOVERY_REQUIRED.requires_manual_recovery()
    assert StepStatus.MANUAL_RECOVERY_REQUIRED.requires_manual_recovery()


def test_superseded_is_final_terminal_without_attention_semantics() -> None:
    assert OperationStatus.SUPERSEDED.is_final_terminal()
    assert not OperationStatus.SUPERSEDED.requires_manual_recovery()


@pytest.mark.parametrize("status", OPERATION_TERMINAL_STATUSES)
def test_operation_terminal_duplicate_idempotent(status: OperationStatus) -> None:
    current = _operation_for_status(status, version=3, updated_at=TS2)
    assert validate_operation_transition(current, current) is TransitionDisposition.IDEMPOTENT


@pytest.mark.parametrize("status", OPERATION_TERMINAL_STATUSES)
def test_operation_terminal_conflicting_duplicate_rejected(status: OperationStatus) -> None:
    current = _operation_for_status(status, version=3, updated_at=TS2)
    candidate = replace(current, optimistic_version=4, updated_at=TS2)
    with pytest.raises(ValueError, match="conflicting terminal duplicate"):
        validate_operation_transition(current, candidate)


@pytest.mark.parametrize("status", STEP_TERMINAL_STATUSES)
def test_step_terminal_duplicate_idempotent(status: StepStatus) -> None:
    current = _step_for_status(status, version=3, updated_at=TS2)
    assert validate_step_transition(current, current) is TransitionDisposition.IDEMPOTENT


@pytest.mark.parametrize("status", STEP_TERMINAL_STATUSES)
def test_step_terminal_conflicting_duplicate_rejected(status: StepStatus) -> None:
    current = _step_for_status(status, version=3, updated_at=TS2)
    candidate = replace(current, optimistic_version=4, updated_at=TS2)
    with pytest.raises(ValueError, match="conflicting terminal duplicate"):
        validate_step_transition(current, candidate)


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


@pytest.mark.parametrize(("name", "changes", "match"), WRITE_PRECONDITION_CONSTRUCTOR_FAULTS)
def test_write_precondition_constructor_rejects_invalid_scalar_types(
    name: str,
    changes: dict[str, object],
    match: str,
) -> None:
    del name
    with pytest.raises(ValueError, match=match):
        WritePrecondition(**changes)  # type: ignore[arg-type]


@pytest.mark.parametrize(("name", "worker_id", "lease_token"), WRITE_PRECONDITION_IDENTITY_ACCEPT_CASES)
def test_write_precondition_accepts_opaque_identity_boundaries(
    name: str,
    worker_id: str,
    lease_token: str,
) -> None:
    del name
    precondition = WritePrecondition(1, worker_id, lease_token)
    validate_write_precondition(
        current_optimistic_version=1,
        current_worker_id=worker_id,
        current_lease_token=lease_token,
        precondition=precondition,
    )


@pytest.mark.parametrize(
    ("name", "worker_id", "lease_token", "match"),
    WRITE_PRECONDITION_IDENTITY_FAULTS,
)
def test_write_precondition_rejects_opaque_identity_boundary_faults(
    name: str,
    worker_id: str,
    lease_token: str,
    match: str,
) -> None:
    del name
    with pytest.raises(ValueError, match=match):
        WritePrecondition(1, worker_id, lease_token)

    with pytest.raises(ValueError, match=match):
        validate_write_precondition(
            current_optimistic_version=1,
            current_worker_id=worker_id,
            current_lease_token=lease_token,
            precondition=WritePrecondition(1, "worker-1", "lease-1"),
        )


def test_write_precondition_guard_rejects_bool_current_version() -> None:
    with pytest.raises(ValueError, match="current_optimistic_version must be"):
        validate_write_precondition(
            current_optimistic_version=True,
            current_worker_id=None,
            current_lease_token=None,
            precondition=WritePrecondition(1, None, None),
        )


def test_transition_guard_rejects_non_bool_recovery_authorization() -> None:
    current = _operation_current_for_status(OperationStatus.MANUAL_RECOVERY_REQUIRED)
    candidate = _operation_candidate(current, OperationStatus.RUNNING)
    with pytest.raises(ValueError, match="recovery_authorized must be a bool"):
        validate_operation_transition(current, candidate, recovery_authorized=1)  # type: ignore[arg-type]


def test_transition_guards_are_deterministic() -> None:
    current = _operation_current_for_status(OperationStatus.QUEUED)
    candidate = _operation_candidate(current, OperationStatus.RUNNING)
    first = validate_operation_transition(current, candidate)
    second = validate_operation_transition(current, candidate)
    assert first is second is TransitionDisposition.APPLY

    step_current = _step_current_for_status(StepStatus.PENDING)
    step_candidate = _step_candidate(step_current, StepStatus.RUNNING)
    assert validate_step_transition(step_current, step_candidate) is validate_step_transition(
        step_current, step_candidate
    )

    validate_write_precondition(
        current_optimistic_version=5,
        current_worker_id=None,
        current_lease_token=None,
        precondition=WritePrecondition(5, None, None),
    )
    validate_write_precondition(
        current_optimistic_version=5,
        current_worker_id=None,
        current_lease_token=None,
        precondition=WritePrecondition(5, None, None),
    )


def test_manual_recovery_allowed_with_authorization() -> None:
    current = _operation_current_for_status(OperationStatus.MANUAL_RECOVERY_REQUIRED)
    candidate = _operation_candidate(current, OperationStatus.RUNNING)
    assert (
        validate_operation_transition(current, candidate, recovery_authorized=True)
        is TransitionDisposition.APPLY
    )
