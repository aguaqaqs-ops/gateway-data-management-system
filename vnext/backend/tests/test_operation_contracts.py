"""Operation runtime public contract tests."""

from __future__ import annotations

import dataclasses
import importlib
import json
from datetime import UTC, datetime

import pytest
from gateway_shared_kernel import DigestRef
from gateway_shared_kernel.jcs import canonicalize_json_value
from hypothesis import given, settings, strategies as st

import gateway_backend.operations as operations
from gateway_backend.artifacts import ArtifactRef
from gateway_backend.operations.contracts import (
    _BUSINESS_REFERENCE_KEYS,
    _DIAGNOSTIC_KEYS,
    _OPERATION_DOCUMENT_KEYS,
    _STEP_DOCUMENT_KEYS,
)
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

EXPECTED_OPERATION_DOCUMENT_KEYS = frozenset(
    {
        "artifact_refs",
        "business_refs",
        "cancel_requested",
        "checkpoint_ref",
        "completed_at",
        "contract_version",
        "created_at",
        "diagnostic",
        "document_type",
        "job_contract_version",
        "job_kind",
        "job_payload",
        "job_payload_ref",
        "operation_id",
        "optimistic_version",
        "ready_closure_ref",
        "repository_operation_id",
        "status",
        "updated_at",
    }
)
EXPECTED_STEP_DOCUMENT_KEYS = frozenset(
    {
        "attempt_count",
        "cancel_requested",
        "checkpoint_ref",
        "completed_at",
        "contract_version",
        "created_at",
        "diagnostic",
        "document_type",
        "lease_expires_at",
        "lease_token",
        "operation_id",
        "optimistic_version",
        "prior_output_refs",
        "retry_not_before",
        "started_at",
        "status",
        "step_id",
        "step_name",
        "updated_at",
        "worker_id",
    }
)
EXPECTED_BUSINESS_REFERENCE_KEYS = frozenset({"kind", "value"})
EXPECTED_DIAGNOSTIC_KEYS = frozenset({"code", "message"})

_PROP = settings(max_examples=40, deadline=None, derandomize=True)

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

EXPECTED_PUBLIC_EXPORTS = frozenset(
    {
        "OPERATION_RUNTIME_CONTRACT_VERSION",
        "BusinessReference",
        "JobStepKey",
        "OperationDiagnostic",
        "OperationRecord",
        "OperationStatus",
        "StepRecord",
        "StepStatus",
        "TransitionDisposition",
        "WritePrecondition",
        "operation_record_from_document",
        "step_record_from_document",
        "validate_operation_transition",
        "validate_step_transition",
        "validate_write_precondition",
        "DEFAULT_CLAIM_LIMIT",
        "DEFAULT_PAGE_LIMIT",
        "MAX_CLAIM_LIMIT",
        "MAX_PAGE_LIMIT",
        "ClaimCandidate",
        "IntegrityScanPage",
        "CorruptPersistedRecord",
        "ConflictingDuplicate",
        "LeaseExpired",
        "OperationStore",
        "OperationUnitOfWork",
        "RecordNotFound",
        "StaleWrite",
        "StoreBusy",
        "UnsupportedSchemaVersion",
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


def _nested_json_object(depth: int) -> dict[str, object]:
    if depth <= 1:
        return {"leaf": 1}
    return {"nested": _nested_json_object(depth - 1)}


def _opaque_id_value_faults() -> tuple[tuple[str, str, str], ...]:
    return (
        ("empty", "", "1..255"),
        ("too-long", "a" * 256, "1..255"),
        ("nul-control", "id\x00", "control"),
        ("host-path-slash", "/tmp/id", "host path"),
        ("host-path-backslash", "C:\\id", "host path"),
    )


def _registry_name_value_faults() -> tuple[tuple[str, str, str], ...]:
    return (
        ("empty", "", "registry name pattern"),
        ("too-long", "a" * 129, "registry name pattern"),
        ("illegal-char", "bad kind", "registry name pattern"),
    )


def _timestamp_value_faults() -> tuple[tuple[str, str, str], ...]:
    return (
        ("offset-plus-zero", "2024-01-02T03:04:05+00:00", "canonical UTC timestamp"),
        ("offset-east-eight", "2024-01-02T03:04:05+08:00", "canonical UTC timestamp"),
        ("leap-second", "2024-01-02T03:04:60Z", "canonical UTC timestamp"),
        ("invalid-civil-date", "2024-02-30T03:04:05Z", "civil date"),
        ("non-canonical-fraction", "2024-01-02T03:04:05.000000Z", "canonical UTC timestamp"),
    )


def _operation_opaque_id_faults() -> tuple[tuple[str, dict[str, object], str], ...]:
    rows: list[tuple[str, dict[str, object], str]] = []
    for field in ("operation_id", "repository_operation_id"):
        for name, value, match in _opaque_id_value_faults():
            rows.append(
                (
                    f"operation-{field}-{name}",
                    _minimal_operation_document(**{field: value}),
                    match,
                )
            )
    return tuple(rows)


def _step_opaque_id_faults() -> tuple[tuple[str, dict[str, object], str], ...]:
    rows: list[tuple[str, dict[str, object], str]] = []
    for field in ("step_id", "operation_id", "worker_id", "lease_token"):
        for name, value, match in _opaque_id_value_faults():
            if field in {"worker_id", "lease_token"}:
                changes: dict[str, object] = {
                    "status": StepStatus.RUNNING.value,
                    "attempt_count": 1,
                    "started_at": TIMESTAMP,
                    "worker_id": "worker-1",
                    "lease_token": "lease-1",
                    "lease_expires_at": LEASE_EXPIRES,
                }
                changes[field] = value
                document = _minimal_step_document(**changes)
            else:
                document = _minimal_step_document(**{field: value})
            rows.append((f"step-{field}-{name}", document, match))
    return tuple(rows)


def _operation_registry_name_faults() -> tuple[tuple[str, dict[str, object], str], ...]:
    rows: list[tuple[str, dict[str, object], str]] = []
    for field in ("job_kind",):
        for name, value, match in _registry_name_value_faults():
            rows.append(
                (
                    f"operation-{field}-{name}",
                    _minimal_operation_document(**{field: value}),
                    match,
                )
            )
    for name, value, match in _registry_name_value_faults():
        rows.append(
            (
                f"operation-business-kind-{name}",
                _minimal_operation_document(
                    business_refs=[{"kind": value, "value": "ws-1"}],
                ),
                match,
            )
        )
    return tuple(rows)


def _step_registry_name_faults() -> tuple[tuple[str, dict[str, object], str], ...]:
    return tuple(
        (
            f"step-step_name-{name}",
            _minimal_step_document(step_name=value),
            match,
        )
        for name, value, match in _registry_name_value_faults()
    )


def _operation_timestamp_faults() -> tuple[tuple[str, dict[str, object], str], ...]:
    return tuple(
        (
            f"operation-created_at-{name}",
            _minimal_operation_document(created_at=value),
            match,
        )
        for name, value, match in _timestamp_value_faults()
    )


def _step_timestamp_faults() -> tuple[tuple[str, dict[str, object], str], ...]:
    return tuple(
        (
            f"step-updated_at-{name}",
            _minimal_step_document(updated_at=value),
            match,
        )
        for name, value, match in _timestamp_value_faults()
    )


def _failed_operation_document(**changes: object) -> dict[str, object]:
    defaults: dict[str, object] = {
        "status": OperationStatus.FAILED.value,
        "diagnostic": DIAGNOSTIC,
        "completed_at": TIMESTAMP,
    }
    defaults.update(changes)
    return _minimal_operation_document(**defaults)


def _failed_step_document(**changes: object) -> dict[str, object]:
    defaults: dict[str, object] = {
        "status": StepStatus.FAILED.value,
        "attempt_count": 1,
        "started_at": TIMESTAMP,
        "diagnostic": DIAGNOSTIC,
        "completed_at": LATER_TIMESTAMP,
        "updated_at": LATER_TIMESTAMP,
    }
    defaults.update(changes)
    return _minimal_step_document(**defaults)


ARTIFACT_REF_FAULTS: tuple[tuple[str, dict[str, object], str], ...] = (
    (
        "missing-artifact-id",
        {
            "media_type": EXAMPLE_MEDIA_TYPE,
            "size_bytes": 3,
            "raw_sha256": EXAMPLE_RAW_SHA256,
        },
        "missing fields",
    ),
    (
        "unknown-content-digest",
        _example_artifact_ref_dict(content_digest="sha256:" + "b" * 64),
        "unknown fields",
    ),
    (
        "host-path-artifact-id",
        _example_artifact_ref_dict(artifact_id="/tmp/secret.arrow"),
        "host path",
    ),
    (
        "size-bytes-negative",
        _example_artifact_ref_dict(size_bytes=-1),
        "size_bytes must be a non-negative integer",
    ),
)


def _operation_nested_artifact_ref_faults() -> tuple[tuple[str, dict[str, object], str], ...]:
    rows: list[tuple[str, dict[str, object], str]] = []
    injectors: tuple[tuple[str, str], ...] = (
        ("job_payload_ref", "job_payload_ref"),
        ("checkpoint_ref", "checkpoint_ref"),
        ("ready_closure_ref", "ready_closure_ref"),
        ("artifact_refs-item", "artifact_refs"),
    )
    for injector_name, field in injectors:
        for fault_name, fault_payload, match in ARTIFACT_REF_FAULTS:
            if field == "artifact_refs":
                document = _minimal_operation_document(artifact_refs=[fault_payload])
            elif field == "job_payload_ref":
                document = _minimal_operation_document(
                    job_payload=None,
                    job_payload_ref=fault_payload,
                )
            else:
                document = _minimal_operation_document(**{field: fault_payload})
            rows.append((f"operation-{injector_name}-{fault_name}", document, match))
    return tuple(rows)


def _step_nested_artifact_ref_faults() -> tuple[tuple[str, dict[str, object], str], ...]:
    rows: list[tuple[str, dict[str, object], str]] = []
    for fault_name, fault_payload, match in ARTIFACT_REF_FAULTS:
        rows.append(
            (
                f"step-checkpoint_ref-{fault_name}",
                _failed_step_document(checkpoint_ref=fault_payload),
                match,
            )
        )
        rows.append(
            (
                f"step-prior_output_refs-{fault_name}",
                _failed_step_document(prior_output_refs=[fault_payload]),
                match,
            )
        )
    return tuple(rows)


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
    (
        "unknown-future-contract-version",
        _minimal_operation_document(contract_version="backend-vnext/operation-runtime/v2"),
        "contract_version mismatch",
    ),
    (
        "unknown-operation-status",
        _minimal_operation_document(status="NOT_A_STATUS"),
        "known OperationStatus",
    ),
    (
        "status-not-string",
        _minimal_operation_document(status=1),
        "status must be a string",
    ),
    (
        "cancel-requested-not-bool",
        _minimal_operation_document(cancel_requested="yes"),
        "cancel_requested must be a bool",
    ),
    (
        "created-at-not-string",
        _minimal_operation_document(created_at=1),
        "created_at must be a string",
    ),
    (
        "business-refs-not-list",
        _minimal_operation_document(business_refs={"kind": "workspace", "value": "ws-1"}),
        "business_refs must be a list",
    ),
    (
        "artifact-refs-not-list",
        _minimal_operation_document(artifact_refs=_example_artifact_ref_dict()),
        "artifact_refs must be a list",
    ),
    (
        "business-ref-item-not-object",
        _minimal_operation_document(business_refs=["workspace"]),
        "business_refs items must be objects",
    ),
    (
        "business-ref-unknown-field",
        _minimal_operation_document(
            business_refs=[{"kind": "workspace", "value": "ws-1", "extra": True}],
        ),
        "unknown fields",
    ),
    (
        "business-ref-missing-kind",
        _minimal_operation_document(business_refs=[{"value": "ws-1"}]),
        "missing fields",
    ),
    (
        "business-ref-host-path-value",
        _minimal_operation_document(
            business_refs=[{"kind": "workspace", "value": "/tmp/ws"}],
        ),
        "host path",
    ),
    (
        "diagnostic-unknown-field",
        _failed_operation_document(diagnostic={**DIAGNOSTIC, "extra": True}),
        "unknown fields",
    ),
    (
        "diagnostic-missing-code",
        _failed_operation_document(diagnostic={"message": "reason"}),
        "missing fields",
    ),
    (
        "diagnostic-empty-message",
        _failed_operation_document(diagnostic={"code": "FAILED", "message": ""}),
        "diagnostic.message",
    ),
    (
        "diagnostic-message-too-long",
        _failed_operation_document(
            diagnostic={"code": "FAILED", "message": "x" * (4 * 1024 + 1)},
        ),
        "diagnostic.message",
    ),
    (
        "diagnostic-code-not-string",
        _failed_operation_document(diagnostic={"code": 1, "message": "reason"}),
        "diagnostic.code must be a string",
    ),
    (
        "job-payload-array-root",
        _minimal_operation_document(job_payload=[]),
        "job_payload must be a JSON object",
    ),
    (
        "job-payload-string-root",
        _minimal_operation_document(job_payload="payload"),
        "job_payload must be a JSON object",
    ),
    (
        "job-payload-ijson-int-overflow",
        _minimal_operation_document(job_payload={"value": 2**53}),
        "I-JSON safe range",
    ),
    (
        "job-payload-depth-overflow",
        _minimal_operation_document(job_payload=_nested_json_object(33)),
        "maximum JSON depth",
    ),
    (
        "job-payload-aggregate-overflow",
        _minimal_operation_document(job_payload={"items": [{} for _ in range(4096)]}),
        "maximum JSON aggregate size",
    ),
    (
        "job-payload-key-too-long",
        _minimal_operation_document(job_payload={"k" * 129: 1}),
        "object key exceeds maximum size",
    ),
    (
        "job-payload-string-too-long",
        _minimal_operation_document(job_payload={"s": "x" * (16 * 1024 + 1)}),
        "string exceeds maximum size",
    ),
    (
        "job-payload-size-overflow",
        _minimal_operation_document(
            job_payload={f"key-{index}": "y" * 1000 for index in range(70)},
        ),
        "maximum inline payload size",
    ),
    (
        "business-refs-size-overflow",
        _minimal_operation_document(
            business_refs=[{"kind": "workspace", "value": f"ws-{index}"} for index in range(65)],
        ),
        "business_refs exceeds maximum tuple size",
    ),
    (
        "artifact-refs-size-overflow",
        _minimal_operation_document(
            artifact_refs=[
                _example_artifact_ref_dict(artifact_id=f"artifact-overflow-{index}")
                for index in range(65)
            ],
        ),
        "artifact_refs exceeds maximum tuple size",
    ),
    (
        "combined-artifact-refs-overflow",
        _minimal_operation_document(
            job_payload=None,
            job_payload_ref=_example_artifact_ref_dict(artifact_id="artifact-payload-ref"),
            artifact_refs=[
                _example_artifact_ref_dict(artifact_id=f"artifact-overflow-{index}")
                for index in range(64)
            ],
        ),
        "artifact refs exceed maximum per record",
    ),
    * _operation_opaque_id_faults(),
    * _operation_registry_name_faults(),
    * _operation_timestamp_faults(),
    * _operation_nested_artifact_ref_faults(),
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
    (
        "unknown-future-contract-version",
        _minimal_step_document(contract_version="backend-vnext/operation-runtime/v2"),
        "contract_version mismatch",
    ),
    (
        "unknown-step-status",
        _minimal_step_document(status="NOT_A_STATUS"),
        "known StepStatus",
    ),
    (
        "status-not-string",
        _minimal_step_document(status=1),
        "status must be a string",
    ),
    (
        "cancel-requested-not-bool",
        _minimal_step_document(cancel_requested="yes"),
        "cancel_requested must be a bool",
    ),
    (
        "attempt-count-negative",
        _minimal_step_document(attempt_count=-1),
        "non-negative I-JSON safe integer",
    ),
    (
        "attempt-count-ijson-overflow",
        _minimal_step_document(attempt_count=2**53),
        "I-JSON safe integer",
    ),
    (
        "prior-output-refs-not-list",
        _minimal_step_document(prior_output_refs=_example_artifact_ref_dict()),
        "prior_output_refs must be a list",
    ),
    (
        "duplicate-prior-output-artifact-id",
        _failed_step_document(
            prior_output_refs=[
                _example_artifact_ref_dict(artifact_id="artifact-dup-1"),
                _example_artifact_ref_dict(artifact_id="artifact-dup-1"),
            ],
        ),
        "duplicate artifact_id",
    ),
    (
        "prior-output-refs-size-overflow",
        _minimal_step_document(
            prior_output_refs=[
                _example_artifact_ref_dict(artifact_id=f"artifact-overflow-{index}")
                for index in range(65)
            ],
        ),
        "prior_output_refs exceeds maximum tuple size",
    ),
    (
        "running-worker-host-path",
        _minimal_step_document(
            status=StepStatus.RUNNING.value,
            attempt_count=1,
            started_at=TIMESTAMP,
            worker_id="/tmp/worker",
            lease_token="lease-1",
            lease_expires_at=LEASE_EXPIRES,
        ),
        "host path",
    ),
    (
        "running-lease-token-host-path",
        _minimal_step_document(
            status=StepStatus.RUNNING.value,
            attempt_count=1,
            started_at=TIMESTAMP,
            worker_id="worker-1",
            lease_token="C:\\lease",
            lease_expires_at=LEASE_EXPIRES,
        ),
        "host path",
    ),
    * _step_opaque_id_faults(),
    * _step_registry_name_faults(),
    * _step_timestamp_faults(),
    * _step_nested_artifact_ref_faults(),
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

DIRECT_RECORD_CONSTRUCTOR_FAULTS: tuple[
    tuple[str, str, dict[str, object], str],
    ...,
] = (
    (
        "operation-runtime-version",
        "operation",
        {"contract_version": "backend-vnext/operation-runtime/v2"},
        "contract_version mismatch",
    ),
    (
        "operation-non-canonical-payload",
        "operation",
        {"job_payload": b'{"b":1,"a":2}'},
        "canonical JSON bytes",
    ),
    (
        "operation-business-refs-list",
        "operation",
        {"business_refs": []},
        "business_refs must be a tuple",
    ),
    (
        "operation-artifact-refs-list",
        "operation",
        {"artifact_refs": []},
        "artifact_refs must be a tuple",
    ),
    (
        "operation-created-at-string",
        "operation",
        {"created_at": TIMESTAMP},
        "created_at must be a datetime",
    ),
    (
        "operation-optimistic-version-bool",
        "operation",
        {"optimistic_version": True},
        "optimistic_version must be a non-negative I-JSON safe integer",
    ),
    (
        "step-runtime-version",
        "step",
        {"contract_version": "backend-vnext/operation-runtime/v2"},
        "contract_version mismatch",
    ),
    (
        "step-prior-output-refs-list",
        "step",
        {"prior_output_refs": []},
        "prior_output_refs must be a tuple",
    ),
    (
        "step-updated-at-string",
        "step",
        {"updated_at": TIMESTAMP},
        "updated_at must be a datetime",
    ),
    (
        "step-attempt-count-bool",
        "step",
        {"attempt_count": True},
        "attempt_count must be a non-negative I-JSON safe integer",
    ),
)

INLINE_JSON_AGGREGATE_VALID_CASES: tuple[tuple[str, dict[str, object]], ...] = (
    ("scalar-list-at-aggregate-limit", {"items": [0] * 4095}),
    ("object-members-at-aggregate-limit", {f"key-{index}": 0 for index in range(4096)}),
)

INLINE_JSON_AGGREGATE_INVALID_CASES: tuple[tuple[str, dict[str, object]], ...] = (
    ("scalar-list-over-aggregate-limit", {"items": [0] * 4096}),
    ("object-members-over-aggregate-limit", {f"key-{index}": 0 for index in range(4097)}),
)

FINITE_INLINE_JSON_NUMBER_CASES: tuple[tuple[str, dict[str, object]], ...] = (
    ("binary64-fraction", {"value": 1.5}),
    ("binary64-negative-zero", {"value": -0.0}),
    ("binary64-small-finite", {"value": 1e-300}),
)

NONFINITE_INLINE_JSON_NUMBER_CASES: tuple[tuple[str, dict[str, object], bytes], ...] = (
    ("nan", {"value": float("nan")}, b'{"value":NaN}'),
    ("positive-infinity", {"value": float("inf")}, b'{"value":Infinity}'),
    ("negative-infinity", {"value": float("-inf")}, b'{"value":-Infinity}'),
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


def test_public_exports_match_operations_surface() -> None:
    assert frozenset(operations.__all__) == EXPECTED_PUBLIC_EXPORTS
    for symbol in EXPECTED_PUBLIC_EXPORTS:
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


def test_operation_document_key_inventory_matches_contract_module() -> None:
    assert EXPECTED_OPERATION_DOCUMENT_KEYS == _OPERATION_DOCUMENT_KEYS
    assert EXPECTED_STEP_DOCUMENT_KEYS == _STEP_DOCUMENT_KEYS
    assert EXPECTED_BUSINESS_REFERENCE_KEYS == _BUSINESS_REFERENCE_KEYS
    assert EXPECTED_DIAGNOSTIC_KEYS == _DIAGNOSTIC_KEYS


def test_operation_full_document_emits_exact_closed_key_set() -> None:
    record = operation_record_from_document(_full_operation_document())
    assert set(record.to_document()) == EXPECTED_OPERATION_DOCUMENT_KEYS


def test_step_full_document_emits_exact_closed_key_set() -> None:
    record = step_record_from_document(_full_step_document())
    assert set(record.to_document()) == EXPECTED_STEP_DOCUMENT_KEYS


def test_business_reference_and_diagnostic_emit_closed_nested_keys() -> None:
    business_ref = BusinessReference(kind="workspace", value="ws-1")
    diagnostic = OperationDiagnostic(code="FAILED", message="owner reason")
    assert set(business_ref.to_document()) == EXPECTED_BUSINESS_REFERENCE_KEYS
    assert set(diagnostic.to_document()) == EXPECTED_DIAGNOSTIC_KEYS


def test_operation_document_emits_closed_key_set() -> None:
    record = operation_record_from_document(_minimal_operation_document())
    assert set(record.to_document()) == EXPECTED_OPERATION_DOCUMENT_KEYS


def test_operation_payload_key_reorder_preserves_canonical_bytes() -> None:
    first = operation_record_from_document(_minimal_operation_document(job_payload={"b": 1, "a": 2}))
    second = operation_record_from_document(_minimal_operation_document(job_payload={"a": 2, "b": 1}))
    assert first.job_payload == second.job_payload


def test_operation_payload_allows_opaque_path_string() -> None:
    record = operation_record_from_document(
        _minimal_operation_document(job_payload={"path": "/tmp/secret"})
    )
    assert record.job_payload is not None
    round_tripped = operation_record_from_document(record.to_document())
    assert round_tripped == record


def test_operation_document_jcs_round_trip() -> None:
    record = operation_record_from_document(_full_operation_document())
    canonical = canonicalize_json_value(record.to_document())
    parsed = json.loads(canonical)
    assert operation_record_from_document(parsed) == record


def test_step_document_jcs_round_trip() -> None:
    record = step_record_from_document(_full_step_document())
    canonical = canonicalize_json_value(record.to_document())
    parsed = json.loads(canonical)
    assert step_record_from_document(parsed) == record


def test_job_payload_bytes_are_canonical_jcs() -> None:
    payload = {"nested": {"values": [1, 2], "name": "payload"}}
    record = operation_record_from_document(_minimal_operation_document(job_payload=payload))
    assert record.job_payload == canonicalize_json_value(payload)


@pytest.mark.parametrize(("name", "payload"), FINITE_INLINE_JSON_NUMBER_CASES)
def test_finite_binary64_job_payloads_round_trip(
    name: str,
    payload: dict[str, object],
) -> None:
    del name
    document_record = operation_record_from_document(_minimal_operation_document(job_payload=payload))
    direct_record = _operation_record(job_payload=canonicalize_json_value(payload))
    assert document_record == direct_record
    assert operation_record_from_document(direct_record.to_document()) == direct_record


@pytest.mark.parametrize(("name", "payload", "canonical_bytes"), NONFINITE_INLINE_JSON_NUMBER_CASES)
def test_nonfinite_binary64_job_payloads_are_rejected(
    name: str,
    payload: dict[str, object],
    canonical_bytes: bytes,
) -> None:
    del name
    with pytest.raises(ValueError, match="non-I-JSON numbers"):
        operation_record_from_document(_minimal_operation_document(job_payload=payload))
    with pytest.raises(ValueError, match="JSON number must be finite"):
        _operation_record(job_payload=canonical_bytes)


def test_operation_payload_key_reorder_yields_identical_document_jcs() -> None:
    first = operation_record_from_document(
        _minimal_operation_document(
            job_payload={"b": 1, "a": 2},
            business_refs=[{"kind": "workspace", "value": "ws-1"}],
        )
    )
    second = operation_record_from_document(
        _minimal_operation_document(
            job_payload={"a": 2, "b": 1},
            business_refs=[{"kind": "workspace", "value": "ws-1"}],
        )
    )
    assert canonicalize_json_value(first.to_document()) == canonicalize_json_value(
        second.to_document()
    )


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
    assert set(record.to_document()) == EXPECTED_STEP_DOCUMENT_KEYS


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


@pytest.mark.parametrize(
    ("name", "record_kind", "changes", "match"),
    DIRECT_RECORD_CONSTRUCTOR_FAULTS,
)
def test_direct_record_constructors_use_shared_validators(
    name: str,
    record_kind: str,
    changes: dict[str, object],
    match: str,
) -> None:
    del name
    with pytest.raises(ValueError, match=match):
        if record_kind == "operation":
            _operation_record(**changes)
        else:
            _step_record(**changes)


def test_value_object_constructors_reject_wrong_runtime_types() -> None:
    with pytest.raises(ValueError, match="business_refs.kind must be a string"):
        BusinessReference(kind=1, value="ws-1")  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="diagnostic.code must be a string"):
        OperationDiagnostic(code=1, message="reason")  # type: ignore[arg-type]


@pytest.mark.parametrize(("name", "payload"), INLINE_JSON_AGGREGATE_VALID_CASES)
def test_inline_json_aggregate_boundary_is_accepted(
    name: str,
    payload: dict[str, object],
) -> None:
    del name
    document_record = operation_record_from_document(_minimal_operation_document(job_payload=payload))
    direct_record = _operation_record(job_payload=canonicalize_json_value(payload))
    assert document_record == direct_record


@pytest.mark.parametrize(("name", "payload"), INLINE_JSON_AGGREGATE_INVALID_CASES)
def test_inline_json_aggregate_boundary_is_rejected(
    name: str,
    payload: dict[str, object],
) -> None:
    del name
    with pytest.raises(ValueError, match="maximum JSON aggregate size"):
        operation_record_from_document(_minimal_operation_document(job_payload=payload))
    with pytest.raises(ValueError, match="maximum JSON aggregate size"):
        _operation_record(job_payload=canonicalize_json_value(payload))


@st.composite
def bounded_json_object(draw: st.DrawFn) -> dict[str, object]:
    return draw(
        st.dictionaries(
            st.text(
                min_size=1,
                max_size=16,
                alphabet=st.characters(min_codepoint=97, max_codepoint=122),
            ),
            st.one_of(
                st.none(),
                st.booleans(),
                st.integers(min_value=0, max_value=1000),
                st.text(max_size=64),
                st.lists(st.integers(min_value=0, max_value=100), max_size=4),
            ),
            max_size=8,
        )
    )


@_PROP
@given(bounded_json_object())
def test_inline_job_payload_property_round_trip(payload: dict[str, object]) -> None:
    try:
        record = operation_record_from_document(_minimal_operation_document(job_payload=payload))
    except ValueError:
        return
    round_tripped = operation_record_from_document(record.to_document())
    assert round_tripped == record
    assert record.job_payload == canonicalize_json_value(payload)
