"""Operation runtime public contract tests."""

from __future__ import annotations

import dataclasses
import importlib
from datetime import UTC, datetime

import pytest
from gateway_shared_kernel import DigestRef
from gateway_shared_kernel.jcs import canonicalize_json_value

import gateway_backend.operations as operations
from gateway_backend.artifacts import ArtifactRef
from gateway_backend.operations import (
    OPERATION_RUNTIME_CONTRACT_VERSION,
    BusinessReference,
    JobStepKey,
    OperationDiagnostic,
    OperationRecord,
    OperationStatus,
    StepRecord,
    StepStatus,
    operation_record_from_document,
    step_record_from_document,
)

pytestmark = pytest.mark.unit

EXAMPLE_ARTIFACT_ID = "operation-artifact-0001"
EXAMPLE_MEDIA_TYPE = "application/octet-stream"
EXAMPLE_RAW_SHA256 = "sha256:" + "a" * 64
TIMESTAMP = "2024-01-02T03:04:05Z"
LATER_TIMESTAMP = "2024-01-02T03:05:00Z"
LEASE_EXPIRES = "2024-01-02T03:10:00Z"
DIAGNOSTIC = {"code": "FAILED", "message": "owner reason"}

EXPECTED_OPERATION_STATUSES = (
    "QUEUED",
    "RUNNING",
    "SUCCEEDED",
    "FAILED",
    "CANCELLED",
    "SUPERSEDED",
    "MANUAL_RECOVERY_REQUIRED",
)

EXPECTED_STEP_STATUSES = (
    "PENDING",
    "RUNNING",
    "RETRY_WAIT",
    "SUCCEEDED",
    "FAILED",
    "CANCELLED",
    "MANUAL_RECOVERY_REQUIRED",
)

S1B_PUBLIC_EXPORTS = frozenset(
    {
        "OPERATION_RUNTIME_CONTRACT_VERSION",
        "BusinessReference",
        "JobStepKey",
        "OperationDiagnostic",
        "OperationRecord",
        "OperationStatus",
        "StepRecord",
        "StepStatus",
        "operation_record_from_document",
        "step_record_from_document",
    }
)


def _example_artifact_ref_dict(**changes: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "artifact_id": EXAMPLE_ARTIFACT_ID,
        "media_type": EXAMPLE_MEDIA_TYPE,
        "size_bytes": 3,
        "raw_sha256": EXAMPLE_RAW_SHA256,
    }
    payload.update(changes)
    return payload


def _example_artifact_ref() -> ArtifactRef:
    return ArtifactRef(
        artifact_id=EXAMPLE_ARTIFACT_ID,
        media_type=EXAMPLE_MEDIA_TYPE,
        size_bytes=3,
        raw_sha256=DigestRef(EXAMPLE_RAW_SHA256),
    )


def _minimal_operation_document(**changes: object) -> dict[str, object]:
    document: dict[str, object] = {
        "artifact_refs": [],
        "business_refs": [],
        "cancel_requested": False,
        "checkpoint_ref": None,
        "completed_at": None,
        "contract_version": OPERATION_RUNTIME_CONTRACT_VERSION,
        "created_at": TIMESTAMP,
        "diagnostic": None,
        "document_type": "operation",
        "job_contract_version": "backend-vnext/import-package/v1",
        "job_kind": "import.package",
        "job_payload": {},
        "job_payload_ref": None,
        "operation_id": "op-0001",
        "optimistic_version": 0,
        "ready_closure_ref": None,
        "repository_operation_id": None,
        "status": OperationStatus.QUEUED.value,
        "updated_at": TIMESTAMP,
    }
    document.update(changes)
    return document


def _minimal_step_document(**changes: object) -> dict[str, object]:
    document: dict[str, object] = {
        "attempt_count": 0,
        "cancel_requested": False,
        "checkpoint_ref": None,
        "completed_at": None,
        "contract_version": OPERATION_RUNTIME_CONTRACT_VERSION,
        "created_at": TIMESTAMP,
        "diagnostic": None,
        "document_type": "step",
        "lease_expires_at": None,
        "lease_token": None,
        "operation_id": "op-0001",
        "optimistic_version": 0,
        "prior_output_refs": [],
        "retry_not_before": None,
        "started_at": None,
        "status": StepStatus.PENDING.value,
        "step_id": "step-0001",
        "step_name": "validate",
        "updated_at": TIMESTAMP,
        "worker_id": None,
    }
    document.update(changes)
    return document


def _full_operation_document() -> dict[str, object]:
    return _minimal_operation_document(
        business_refs=[{"kind": "workspace", "value": "ws-1"}],
        artifact_refs=[_example_artifact_ref_dict(artifact_id="artifact-list-1")],
        checkpoint_ref=_example_artifact_ref_dict(artifact_id="artifact-checkpoint-1"),
        ready_closure_ref=_example_artifact_ref_dict(artifact_id="artifact-closure-1"),
        repository_operation_id="repo-op-1",
        status=OperationStatus.FAILED.value,
        diagnostic=DIAGNOSTIC,
        completed_at=TIMESTAMP,
    )


def _full_step_document() -> dict[str, object]:
    return _minimal_step_document(
        status=StepStatus.FAILED.value,
        attempt_count=1,
        diagnostic=DIAGNOSTIC,
        prior_output_refs=[_example_artifact_ref_dict(artifact_id="artifact-output-1")],
        checkpoint_ref=_example_artifact_ref_dict(artifact_id="artifact-step-checkpoint-1"),
        started_at=TIMESTAMP,
        completed_at=TIMESTAMP,
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
        "created_at": datetime(2024, 1, 2, 3, 4, 5, tzinfo=UTC),
        "updated_at": datetime(2024, 1, 2, 3, 4, 5, tzinfo=UTC),
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
        "created_at": datetime(2024, 1, 2, 3, 4, 5, tzinfo=UTC),
        "updated_at": datetime(2024, 1, 2, 3, 4, 5, tzinfo=UTC),
        "started_at": None,
        "completed_at": None,
        "optimistic_version": 0,
    }
    defaults.update(changes)
    return StepRecord(**defaults)  # type: ignore[arg-type]


MALFORMED_OPERATION_DOCUMENT_SHAPES: tuple[tuple[str, dict[str, object] | object, str], ...] = (
    ("non-object-root", [], "must be an object"),
    (
        "unknown-field",
        {**_minimal_operation_document(), "unexpected": True},
        "unknown fields",
    ),
    (
        "missing-operation-id",
        {key: value for key, value in _minimal_operation_document().items() if key != "operation_id"},
        "missing fields",
    ),
    (
        "wrong-contract-version",
        _minimal_operation_document(contract_version="backend-vnext/operation-runtime/v2"),
        "contract_version mismatch",
    ),
    (
        "wrong-document-type",
        _minimal_operation_document(document_type="step"),
        "document_type mismatch",
    ),
    (
        "payload-and-ref-both-null",
        _minimal_operation_document(job_payload=None, job_payload_ref=None),
        "mutually exclusive",
    ),
    (
        "payload-and-ref-both-set",
        _minimal_operation_document(
            job_payload={"x": 1},
            job_payload_ref=_example_artifact_ref_dict(),
        ),
        "mutually exclusive",
    ),
    (
        "host-path-operation-id",
        _minimal_operation_document(operation_id="/tmp/op"),
        "host path",
    ),
    (
        "non-utc-created-at",
        _minimal_operation_document(created_at="2024-01-02T03:04:05+00:00"),
        "canonical UTC timestamp",
    ),
    (
        "non-canonical-fraction",
        _minimal_operation_document(created_at="2024-01-02T03:04:05.000000Z"),
        "canonical UTC timestamp",
    ),
    (
        "optimistic-version-float",
        _minimal_operation_document(optimistic_version=1.5),
        "must be an integer",
    ),
    (
        "optimistic-version-ijson-overflow",
        _minimal_operation_document(optimistic_version=2**53),
        "I-JSON safe integer",
    ),
    (
        "duplicate-artifact-id",
        _minimal_operation_document(
            artifact_refs=[_example_artifact_ref_dict()],
            checkpoint_ref=_example_artifact_ref_dict(),
        ),
        "duplicate artifact_id",
    ),
    (
        "invalid-diagnostic-code",
        _minimal_operation_document(diagnostic={"code": "bad", "message": "reason"}),
        "diagnostic.code",
    ),
)

MALFORMED_STEP_DOCUMENT_SHAPES: tuple[tuple[str, dict[str, object] | object, str], ...] = (
    ("non-object-root", "step", "must be an object"),
    (
        "unknown-field",
        {**_minimal_step_document(), "unexpected": True},
        "unknown fields",
    ),
    (
        "wrong-document-type",
        _minimal_step_document(document_type="operation"),
        "document_type mismatch",
    ),
    (
        "host-path-step-id",
        _minimal_step_document(step_id="C:\\step"),
        "host path",
    ),
    (
        "attempt-count-bool",
        _minimal_step_document(attempt_count=True),
        "must be an integer",
    ),
)

MINIMAL_OPERATION_STATUS_DOCUMENTS: tuple[tuple[str, dict[str, object]], ...] = (
    ("queued", _minimal_operation_document()),
    ("running", _minimal_operation_document(status=OperationStatus.RUNNING.value)),
    (
        "succeeded",
        _minimal_operation_document(
            status=OperationStatus.SUCCEEDED.value,
            completed_at=TIMESTAMP,
        ),
    ),
    (
        "failed",
        _minimal_operation_document(
            status=OperationStatus.FAILED.value,
            diagnostic=DIAGNOSTIC,
            completed_at=TIMESTAMP,
        ),
    ),
    (
        "cancelled",
        _minimal_operation_document(
            status=OperationStatus.CANCELLED.value,
            completed_at=TIMESTAMP,
        ),
    ),
    (
        "superseded",
        _minimal_operation_document(
            status=OperationStatus.SUPERSEDED.value,
            completed_at=TIMESTAMP,
        ),
    ),
    (
        "manual-recovery",
        _minimal_operation_document(
            status=OperationStatus.MANUAL_RECOVERY_REQUIRED.value,
            diagnostic=DIAGNOSTIC,
        ),
    ),
)

MINIMAL_STEP_STATUS_DOCUMENTS: tuple[tuple[str, dict[str, object]], ...] = (
    ("pending", _minimal_step_document()),
    (
        "running",
        _minimal_step_document(
            status=StepStatus.RUNNING.value,
            attempt_count=1,
            started_at=TIMESTAMP,
            worker_id="worker-1",
            lease_token="lease-1",
            lease_expires_at=LEASE_EXPIRES,
        ),
    ),
    (
        "retry-wait",
        _minimal_step_document(
            status=StepStatus.RETRY_WAIT.value,
            attempt_count=1,
            started_at=TIMESTAMP,
            diagnostic=DIAGNOSTIC,
            retry_not_before=LATER_TIMESTAMP,
        ),
    ),
    (
        "succeeded",
        _minimal_step_document(
            status=StepStatus.SUCCEEDED.value,
            attempt_count=1,
            started_at=TIMESTAMP,
            completed_at=LATER_TIMESTAMP,
            updated_at=LATER_TIMESTAMP,
        ),
    ),
    (
        "failed",
        _minimal_step_document(
            status=StepStatus.FAILED.value,
            attempt_count=1,
            started_at=TIMESTAMP,
            diagnostic=DIAGNOSTIC,
            completed_at=LATER_TIMESTAMP,
            updated_at=LATER_TIMESTAMP,
        ),
    ),
    (
        "cancelled-pre-claim",
        _minimal_step_document(
            status=StepStatus.CANCELLED.value,
            completed_at=TIMESTAMP,
        ),
    ),
    (
        "cancelled-post-start",
        _minimal_step_document(
            status=StepStatus.CANCELLED.value,
            attempt_count=1,
            started_at=TIMESTAMP,
            completed_at=LATER_TIMESTAMP,
            updated_at=LATER_TIMESTAMP,
        ),
    ),
    (
        "manual-recovery",
        _minimal_step_document(
            status=StepStatus.MANUAL_RECOVERY_REQUIRED.value,
            attempt_count=1,
            started_at=TIMESTAMP,
            diagnostic=DIAGNOSTIC,
        ),
    ),
)

INVALID_OPERATION_STATUS_FIELD_COMBINATIONS: tuple[tuple[str, dict[str, object], str], ...] = (
    (
        "queued-with-diagnostic",
        _minimal_operation_document(diagnostic=DIAGNOSTIC),
        "diagnostic is forbidden",
    ),
    (
        "failed-without-diagnostic",
        _minimal_operation_document(
            status=OperationStatus.FAILED.value,
            completed_at=TIMESTAMP,
        ),
        "diagnostic is required",
    ),
    (
        "succeeded-without-completed-at",
        _minimal_operation_document(status=OperationStatus.SUCCEEDED.value),
        "completed_at is required",
    ),
    (
        "running-with-completed-at",
        _minimal_operation_document(
            status=OperationStatus.RUNNING.value,
            completed_at=TIMESTAMP,
        ),
        "completed_at is forbidden",
    ),
    (
        "manual-with-completed-at",
        _minimal_operation_document(
            status=OperationStatus.MANUAL_RECOVERY_REQUIRED.value,
            diagnostic=DIAGNOSTIC,
            completed_at=TIMESTAMP,
        ),
        "completed_at is forbidden",
    ),
    (
        "updated-before-created",
        _minimal_operation_document(
            created_at=LATER_TIMESTAMP,
            updated_at=TIMESTAMP,
        ),
        "created_at must be <=",
    ),
)

INVALID_STEP_STATUS_FIELD_COMBINATIONS: tuple[tuple[str, dict[str, object], str], ...] = (
    (
        "pending-with-started-at",
        _minimal_step_document(started_at=TIMESTAMP),
        "PENDING step requires started_at=null",
    ),
    (
        "running-without-lease",
        _minimal_step_document(
            status=StepStatus.RUNNING.value,
            attempt_count=1,
            started_at=TIMESTAMP,
        ),
        "RUNNING step requires worker_id",
    ),
    (
        "running-lease-expired",
        _minimal_step_document(
            status=StepStatus.RUNNING.value,
            attempt_count=1,
            started_at=TIMESTAMP,
            worker_id="worker-1",
            lease_token="lease-1",
            lease_expires_at=TIMESTAMP,
        ),
        "lease_expires_at must be later",
    ),
    (
        "pending-with-lease",
        _minimal_step_document(
            worker_id="worker-1",
            lease_token="lease-1",
            lease_expires_at=LEASE_EXPIRES,
        ),
        "lease identity fields are forbidden",
    ),
    (
        "retry-wait-without-diagnostic",
        _minimal_step_document(
            status=StepStatus.RETRY_WAIT.value,
            attempt_count=1,
            started_at=TIMESTAMP,
            retry_not_before=LATER_TIMESTAMP,
        ),
        "diagnostic is required",
    ),
    (
        "retry-wait-retry-before-updated",
        _minimal_step_document(
            status=StepStatus.RETRY_WAIT.value,
            attempt_count=1,
            started_at=TIMESTAMP,
            diagnostic=DIAGNOSTIC,
            retry_not_before=TIMESTAMP,
            updated_at=LATER_TIMESTAMP,
        ),
        "retry_not_before must be >=",
    ),
    (
        "pending-with-retry-not-before",
        _minimal_step_document(retry_not_before=LATER_TIMESTAMP),
        "retry_not_before is forbidden",
    ),
    (
        "succeeded-without-completed-at",
        _minimal_step_document(
            status=StepStatus.SUCCEEDED.value,
            attempt_count=1,
            started_at=TIMESTAMP,
        ),
        "completed_at is required",
    ),
    (
        "running-with-completed-at",
        _minimal_step_document(
            status=StepStatus.RUNNING.value,
            attempt_count=1,
            started_at=TIMESTAMP,
            worker_id="worker-1",
            lease_token="lease-1",
            lease_expires_at=LEASE_EXPIRES,
            completed_at=LATER_TIMESTAMP,
        ),
        "completed_at is forbidden",
    ),
    (
        "cancelled-mixed-attempt-started",
        _minimal_step_document(
            status=StepStatus.CANCELLED.value,
            attempt_count=1,
            completed_at=TIMESTAMP,
        ),
        "attempt_count>=1 requires started_at",
    ),
    (
        "completed-before-started",
        _minimal_step_document(
            status=StepStatus.SUCCEEDED.value,
            attempt_count=1,
            started_at=LATER_TIMESTAMP,
            completed_at=TIMESTAMP,
            updated_at=LATER_TIMESTAMP,
        ),
        "started_at must be <=",
    ),
)


def test_operations_package_importable() -> None:
    importlib.import_module("gateway_backend.operations")
    importlib.import_module("gateway_backend.operations.contracts")


def test_contract_version_exact() -> None:
    assert OPERATION_RUNTIME_CONTRACT_VERSION == "backend-vnext/operation-runtime/v1"


def test_operation_status_values_exact() -> None:
    assert tuple(status.value for status in OperationStatus) == EXPECTED_OPERATION_STATUSES


def test_step_status_values_exact() -> None:
    assert tuple(status.value for status in StepStatus) == EXPECTED_STEP_STATUSES


def test_job_step_key_registry_identity() -> None:
    first = JobStepKey(job_kind="import.package", step_name="validate")
    second = JobStepKey(job_kind="import.package", step_name="validate")
    different = JobStepKey(job_kind="import.package", step_name="publish")

    assert dataclasses.is_dataclass(first)
    assert first.__slots__ == ("job_kind", "step_name")
    assert (first.job_kind, first.step_name) == ("import.package", "validate")
    assert first == second
    assert first != different
    assert hash(first) == hash(second)
    assert {first: "handler"}[second] == "handler"


def test_public_exports_match_s1b_subset() -> None:
    assert frozenset(operations.__all__) == S1B_PUBLIC_EXPORTS
    for symbol in S1B_PUBLIC_EXPORTS:
        assert hasattr(operations, symbol)


def test_no_operation_kind_in_public_surface() -> None:
    assert not hasattr(operations, "operation_kind")
    assert "operation_kind" not in dir(operations)


def test_minimal_operation_document_round_trips() -> None:
    record = operation_record_from_document(_minimal_operation_document())
    round_tripped = operation_record_from_document(record.to_document())
    assert round_tripped == record


def test_full_operation_document_round_trips() -> None:
    record = operation_record_from_document(_full_operation_document())
    round_tripped = operation_record_from_document(record.to_document())
    assert round_tripped == record


def test_operation_record_with_payload_ref_round_trips() -> None:
    document = _minimal_operation_document(
        job_payload=None,
        job_payload_ref=_example_artifact_ref_dict(),
    )
    record = operation_record_from_document(document)
    assert record.job_payload is None
    assert record.job_payload_ref is not None
    round_tripped = operation_record_from_document(record.to_document())
    assert round_tripped == record


def test_operation_document_emits_closed_key_set() -> None:
    record = operation_record_from_document(_minimal_operation_document())
    assert set(record.to_document()) == set(_minimal_operation_document())


def test_operation_payload_key_reorder_preserves_canonical_bytes() -> None:
    first = operation_record_from_document(_minimal_operation_document(job_payload={"b": 1, "a": 2}))
    second = operation_record_from_document(_minimal_operation_document(job_payload={"a": 2, "b": 1}))
    assert first.job_payload == second.job_payload


def test_minimal_step_document_round_trips() -> None:
    record = step_record_from_document(_minimal_step_document())
    round_tripped = step_record_from_document(record.to_document())
    assert round_tripped == record


def test_full_step_document_round_trips() -> None:
    record = step_record_from_document(_full_step_document())
    round_tripped = step_record_from_document(record.to_document())
    assert round_tripped == record


def test_step_document_emits_closed_key_set() -> None:
    record = step_record_from_document(_minimal_step_document())
    assert set(record.to_document()) == set(_minimal_step_document())


def test_operation_record_constructor_uses_shared_validators() -> None:
    with pytest.raises(ValueError, match="mutually exclusive"):
        _operation_record(job_payload=canonicalize_json_value({}), job_payload_ref=_example_artifact_ref())


def test_business_reference_round_trips_document_shape() -> None:
    ref = BusinessReference(kind="workspace", value="ws-1")
    assert ref.to_document() == {"kind": "workspace", "value": "ws-1"}


def test_operation_diagnostic_round_trips_document_shape() -> None:
    diagnostic = OperationDiagnostic(code="FAILED", message="owner reason")
    assert diagnostic.to_document() == {"code": "FAILED", "message": "owner reason"}


@pytest.mark.parametrize(
    ("name", "document", "match"),
    MALFORMED_OPERATION_DOCUMENT_SHAPES,
)
def test_operation_record_from_document_rejects_malformed_shapes(
    name: str,
    document: dict[str, object] | object,
    match: str,
) -> None:
    del name
    with pytest.raises(ValueError, match=match):
        operation_record_from_document(document)


@pytest.mark.parametrize(
    ("name", "document", "match"),
    MALFORMED_STEP_DOCUMENT_SHAPES,
)
def test_step_record_from_document_rejects_malformed_shapes(
    name: str,
    document: dict[str, object] | object,
    match: str,
) -> None:
    del name
    with pytest.raises(ValueError, match=match):
        step_record_from_document(document)


@pytest.mark.parametrize(("name", "document"), MINIMAL_OPERATION_STATUS_DOCUMENTS)
def test_minimal_operation_status_documents_are_valid(name: str, document: dict[str, object]) -> None:
    del name
    record = operation_record_from_document(document)
    round_tripped = operation_record_from_document(record.to_document())
    assert round_tripped == record


@pytest.mark.parametrize(("name", "document"), MINIMAL_STEP_STATUS_DOCUMENTS)
def test_minimal_step_status_documents_are_valid(name: str, document: dict[str, object]) -> None:
    del name
    record = step_record_from_document(document)
    round_tripped = step_record_from_document(record.to_document())
    assert round_tripped == record


@pytest.mark.parametrize(
    ("name", "document", "match"),
    INVALID_OPERATION_STATUS_FIELD_COMBINATIONS,
)
def test_operation_record_rejects_invalid_status_field_combinations(
    name: str,
    document: dict[str, object],
    match: str,
) -> None:
    del name
    with pytest.raises(ValueError, match=match):
        operation_record_from_document(document)


@pytest.mark.parametrize(
    ("name", "document", "match"),
    INVALID_STEP_STATUS_FIELD_COMBINATIONS,
)
def test_step_record_rejects_invalid_status_field_combinations(
    name: str,
    document: dict[str, object],
    match: str,
) -> None:
    del name
    with pytest.raises(ValueError, match=match):
        step_record_from_document(document)


def test_operation_status_predicates() -> None:
    final_terminal = {
        OperationStatus.SUCCEEDED,
        OperationStatus.FAILED,
        OperationStatus.CANCELLED,
        OperationStatus.SUPERSEDED,
    }
    for status in OperationStatus:
        assert status.is_final_terminal() is (status in final_terminal)
        assert status.requires_manual_recovery() is (
            status is OperationStatus.MANUAL_RECOVERY_REQUIRED
        )
    assert not OperationStatus.MANUAL_RECOVERY_REQUIRED.is_final_terminal()


def test_step_status_predicates() -> None:
    final_terminal = {StepStatus.SUCCEEDED, StepStatus.FAILED, StepStatus.CANCELLED}
    for status in StepStatus:
        assert status.is_final_terminal() is (status in final_terminal)
        assert status.requires_manual_recovery() is (
            status is StepStatus.MANUAL_RECOVERY_REQUIRED
        )
    assert not StepStatus.MANUAL_RECOVERY_REQUIRED.is_final_terminal()


def test_operation_record_is_frozen_and_owns_tuple_refs() -> None:
    business_refs = [{"kind": "workspace", "value": "ws-1"}]
    artifact_refs = [_example_artifact_ref_dict(artifact_id="artifact-owned-1")]
    document = _minimal_operation_document(
        business_refs=business_refs,
        artifact_refs=artifact_refs,
    )
    record = operation_record_from_document(document)
    assert dataclasses.is_dataclass(record)
    with pytest.raises(dataclasses.FrozenInstanceError):
        record.status = OperationStatus.RUNNING  # type: ignore[misc]
    assert isinstance(record.business_refs, tuple)
    assert isinstance(record.artifact_refs, tuple)
    business_refs.append({"kind": "other", "value": "x"})
    artifact_refs.append(_example_artifact_ref_dict(artifact_id="artifact-owned-2"))
    assert len(record.business_refs) == 1
    assert len(record.artifact_refs) == 1


def test_step_record_is_frozen_and_owns_tuple_refs() -> None:
    prior_output_refs = [_example_artifact_ref_dict(artifact_id="artifact-output-owned-1")]
    document = _minimal_step_document(prior_output_refs=prior_output_refs)
    record = step_record_from_document(document)
    assert dataclasses.is_dataclass(record)
    with pytest.raises(dataclasses.FrozenInstanceError):
        record.status = StepStatus.RUNNING  # type: ignore[misc]
    assert isinstance(record.prior_output_refs, tuple)
    prior_output_refs.append(_example_artifact_ref_dict(artifact_id="artifact-output-owned-2"))
    assert len(record.prior_output_refs) == 1


def test_operation_record_constructor_rejects_invalid_status_fields() -> None:
    with pytest.raises(ValueError, match="diagnostic is forbidden"):
        _operation_record(diagnostic=OperationDiagnostic(code="FAILED", message="reason"))
