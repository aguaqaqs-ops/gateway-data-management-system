"""Operation runtime public contracts owned by gateway_backend.operations."""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum

from gateway_shared_kernel.errors import CanonicalEncodingError
from gateway_shared_kernel.jcs import canonicalize_jcs, canonicalize_json_value

from gateway_backend.artifacts.serialize import artifact_ref_from_dict, artifact_ref_to_dict
from gateway_backend.artifacts.types import ArtifactRef, assert_no_host_path_identity

OPERATION_RUNTIME_CONTRACT_VERSION = "backend-vnext/operation-runtime/v1"
OPERATION_DOCUMENT_TYPE = "operation"
STEP_DOCUMENT_TYPE = "step"

_IJSON_MAX_SAFE_INTEGER = (2**53) - 1
_MAX_OPAQUE_ID_BYTES = 255
_MAX_REGISTRY_NAME_LEN = 128
_MAX_CONTRACT_VERSION_LEN = 128
_MAX_DIAGNOSTIC_MESSAGE_BYTES = 4 * 1024
_MAX_INLINE_PAYLOAD_BYTES = 64 * 1024
_MAX_JSON_DEPTH = 32
_MAX_JSON_AGGREGATE = 4096
_MAX_JSON_KEY_BYTES = 128
_MAX_JSON_STRING_BYTES = 16 * 1024
_MAX_REFS_PER_RECORD = 64
_MAX_BUSINESS_REFS = 64

_REGISTRY_NAME_RE = re.compile(r"^[A-Za-z0-9._:-]{1,128}$")
_DIAGNOSTIC_CODE_RE = re.compile(r"^[A-Z][A-Z0-9_.:-]{0,127}$")
_CONTRACT_VERSION_RE = re.compile(r"^[\x20-\x7e]{1,128}$")
_TIMESTAMP_RE = re.compile(
    r"^([0-9]{4})-([0-9]{2})-([0-9]{2})T([0-9]{2}):([0-9]{2}):([0-9]{2})(?:\.([0-9]{1,6}))?Z$"
)
_CONTROL_CHAR_RE = re.compile(r"[\x00-\x1f\x7f]")

_OPERATION_DOCUMENT_KEYS = frozenset(
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
_STEP_DOCUMENT_KEYS = frozenset(
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
_BUSINESS_REFERENCE_KEYS = frozenset({"kind", "value"})
_DIAGNOSTIC_KEYS = frozenset({"code", "message"})


class OperationStatus(StrEnum):
    QUEUED = "QUEUED"
    RUNNING = "RUNNING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"
    SUPERSEDED = "SUPERSEDED"
    MANUAL_RECOVERY_REQUIRED = "MANUAL_RECOVERY_REQUIRED"

    def is_final_terminal(self) -> bool:
        return self in _OPERATION_FINAL_TERMINAL

    def requires_manual_recovery(self) -> bool:
        return self is OperationStatus.MANUAL_RECOVERY_REQUIRED


class StepStatus(StrEnum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    RETRY_WAIT = "RETRY_WAIT"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"
    MANUAL_RECOVERY_REQUIRED = "MANUAL_RECOVERY_REQUIRED"

    def is_final_terminal(self) -> bool:
        return self in _STEP_FINAL_TERMINAL

    def requires_manual_recovery(self) -> bool:
        return self is StepStatus.MANUAL_RECOVERY_REQUIRED


_OPERATION_FINAL_TERMINAL = frozenset(
    {
        OperationStatus.SUCCEEDED,
        OperationStatus.FAILED,
        OperationStatus.CANCELLED,
        OperationStatus.SUPERSEDED,
    }
)
_STEP_FINAL_TERMINAL = frozenset(
    {
        StepStatus.SUCCEEDED,
        StepStatus.FAILED,
        StepStatus.CANCELLED,
    }
)


@dataclass(frozen=True, slots=True)
class JobStepKey:
    """Stable JobDefinition registry identity; does not hold handlers or callables."""

    job_kind: str
    step_name: str

    def __post_init__(self) -> None:
        _validate_registry_name(self.job_kind, "job_kind")
        _validate_registry_name(self.step_name, "step_name")


@dataclass(frozen=True, slots=True)
class BusinessReference:
    kind: str
    value: str

    def __post_init__(self) -> None:
        _validate_registry_name(self.kind, "business_refs.kind")
        _validate_opaque_id(self.value, "business_refs.value")

    def to_document(self) -> dict[str, object]:
        return {"kind": self.kind, "value": self.value}


@dataclass(frozen=True, slots=True)
class OperationDiagnostic:
    code: str
    message: str

    def __post_init__(self) -> None:
        _validate_diagnostic_code(self.code)
        _validate_diagnostic_message(self.message)

    def to_document(self) -> dict[str, object]:
        return {"code": self.code, "message": self.message}


@dataclass(frozen=True, slots=True)
class OperationRecord:
    contract_version: str
    operation_id: str
    job_kind: str
    job_contract_version: str
    job_payload: bytes | None
    job_payload_ref: ArtifactRef | None
    business_refs: tuple[BusinessReference, ...]
    artifact_refs: tuple[ArtifactRef, ...]
    repository_operation_id: str | None
    checkpoint_ref: ArtifactRef | None
    ready_closure_ref: ArtifactRef | None
    status: OperationStatus
    diagnostic: OperationDiagnostic | None
    cancel_requested: bool
    created_at: datetime
    updated_at: datetime
    completed_at: datetime | None
    optimistic_version: int

    def __post_init__(self) -> None:
        _validate_operation_record_fields(self)

    def to_document(self) -> dict[str, object]:
        return {
            "artifact_refs": [artifact_ref_to_dict(item) for item in self.artifact_refs],
            "business_refs": [item.to_document() for item in self.business_refs],
            "cancel_requested": self.cancel_requested,
            "checkpoint_ref": (
                artifact_ref_to_dict(self.checkpoint_ref)
                if self.checkpoint_ref is not None
                else None
            ),
            "completed_at": (
                _format_utc_timestamp(self.completed_at)
                if self.completed_at is not None
                else None
            ),
            "contract_version": self.contract_version,
            "created_at": _format_utc_timestamp(self.created_at),
            "diagnostic": self.diagnostic.to_document() if self.diagnostic is not None else None,
            "document_type": OPERATION_DOCUMENT_TYPE,
            "job_contract_version": self.job_contract_version,
            "job_kind": self.job_kind,
            "job_payload": _decode_job_payload_object(self.job_payload),
            "job_payload_ref": (
                artifact_ref_to_dict(self.job_payload_ref)
                if self.job_payload_ref is not None
                else None
            ),
            "operation_id": self.operation_id,
            "optimistic_version": self.optimistic_version,
            "ready_closure_ref": (
                artifact_ref_to_dict(self.ready_closure_ref)
                if self.ready_closure_ref is not None
                else None
            ),
            "repository_operation_id": self.repository_operation_id,
            "status": self.status.value,
            "updated_at": _format_utc_timestamp(self.updated_at),
        }


@dataclass(frozen=True, slots=True)
class StepRecord:
    contract_version: str
    step_id: str
    operation_id: str
    step_name: str
    status: StepStatus
    attempt_count: int
    diagnostic: OperationDiagnostic | None
    cancel_requested: bool
    retry_not_before: datetime | None
    worker_id: str | None
    lease_token: str | None
    lease_expires_at: datetime | None
    checkpoint_ref: ArtifactRef | None
    prior_output_refs: tuple[ArtifactRef, ...]
    created_at: datetime
    updated_at: datetime
    started_at: datetime | None
    completed_at: datetime | None
    optimistic_version: int

    def __post_init__(self) -> None:
        _validate_step_record_fields(self)

    def to_document(self) -> dict[str, object]:
        return {
            "attempt_count": self.attempt_count,
            "cancel_requested": self.cancel_requested,
            "checkpoint_ref": (
                artifact_ref_to_dict(self.checkpoint_ref)
                if self.checkpoint_ref is not None
                else None
            ),
            "completed_at": (
                _format_utc_timestamp(self.completed_at)
                if self.completed_at is not None
                else None
            ),
            "contract_version": self.contract_version,
            "created_at": _format_utc_timestamp(self.created_at),
            "diagnostic": self.diagnostic.to_document() if self.diagnostic is not None else None,
            "document_type": STEP_DOCUMENT_TYPE,
            "lease_expires_at": (
                _format_utc_timestamp(self.lease_expires_at)
                if self.lease_expires_at is not None
                else None
            ),
            "lease_token": self.lease_token,
            "operation_id": self.operation_id,
            "optimistic_version": self.optimistic_version,
            "prior_output_refs": [artifact_ref_to_dict(item) for item in self.prior_output_refs],
            "retry_not_before": (
                _format_utc_timestamp(self.retry_not_before)
                if self.retry_not_before is not None
                else None
            ),
            "started_at": (
                _format_utc_timestamp(self.started_at) if self.started_at is not None else None
            ),
            "status": self.status.value,
            "step_id": self.step_id,
            "step_name": self.step_name,
            "updated_at": _format_utc_timestamp(self.updated_at),
            "worker_id": self.worker_id,
        }


def operation_record_from_document(document: object) -> OperationRecord:
    document_mapping = _require_closed_document(document, _OPERATION_DOCUMENT_KEYS, "operation document")
    _require_contract_version(document_mapping["contract_version"])
    _require_document_type(document_mapping["document_type"], OPERATION_DOCUMENT_TYPE)
    job_payload_object = document_mapping["job_payload"]
    job_payload_ref_payload = document_mapping["job_payload_ref"]
    job_payload, job_payload_ref = _parse_job_payload_binding(
        job_payload_object,
        job_payload_ref_payload,
    )
    business_refs = _parse_business_refs(document_mapping["business_refs"])
    artifact_refs = _parse_artifact_ref_list(document_mapping["artifact_refs"], label="artifact_refs")
    checkpoint_ref = _parse_optional_artifact_ref(document_mapping["checkpoint_ref"])
    ready_closure_ref = _parse_optional_artifact_ref(document_mapping["ready_closure_ref"])
    _reject_duplicate_artifact_ids(
        _collect_artifact_refs(job_payload_ref, artifact_refs, checkpoint_ref, ready_closure_ref)
    )
    return OperationRecord(
        contract_version=_require_contract_version_string(document_mapping["contract_version"]),
        operation_id=_parse_opaque_id(document_mapping["operation_id"], "operation_id"),
        job_kind=_parse_registry_name(document_mapping["job_kind"], "job_kind"),
        job_contract_version=_parse_job_contract_version(document_mapping["job_contract_version"]),
        job_payload=job_payload,
        job_payload_ref=job_payload_ref,
        business_refs=business_refs,
        artifact_refs=artifact_refs,
        repository_operation_id=_parse_optional_opaque_id(
            document_mapping["repository_operation_id"],
            "repository_operation_id",
        ),
        checkpoint_ref=checkpoint_ref,
        ready_closure_ref=ready_closure_ref,
        status=_parse_operation_status(document_mapping["status"]),
        diagnostic=_parse_optional_diagnostic(document_mapping["diagnostic"]),
        cancel_requested=_require_bool(document_mapping["cancel_requested"], "cancel_requested"),
        created_at=_parse_utc_timestamp(document_mapping["created_at"], "created_at"),
        updated_at=_parse_utc_timestamp(document_mapping["updated_at"], "updated_at"),
        completed_at=_parse_optional_utc_timestamp(document_mapping["completed_at"], "completed_at"),
        optimistic_version=_parse_ijson_int(
            document_mapping["optimistic_version"],
            "optimistic_version",
        ),
    )


def step_record_from_document(document: object) -> StepRecord:
    document_mapping = _require_closed_document(document, _STEP_DOCUMENT_KEYS, "step document")
    _require_contract_version(document_mapping["contract_version"])
    _require_document_type(document_mapping["document_type"], STEP_DOCUMENT_TYPE)
    prior_output_refs = _parse_artifact_ref_list(
        document_mapping["prior_output_refs"],
        label="prior_output_refs",
    )
    checkpoint_ref = _parse_optional_artifact_ref(document_mapping["checkpoint_ref"])
    _reject_duplicate_artifact_ids(_collect_artifact_refs(None, prior_output_refs, checkpoint_ref))
    return StepRecord(
        contract_version=_require_contract_version_string(document_mapping["contract_version"]),
        step_id=_parse_opaque_id(document_mapping["step_id"], "step_id"),
        operation_id=_parse_opaque_id(document_mapping["operation_id"], "operation_id"),
        step_name=_parse_registry_name(document_mapping["step_name"], "step_name"),
        status=_parse_step_status(document_mapping["status"]),
        attempt_count=_parse_ijson_int(document_mapping["attempt_count"], "attempt_count"),
        diagnostic=_parse_optional_diagnostic(document_mapping["diagnostic"]),
        cancel_requested=_require_bool(document_mapping["cancel_requested"], "cancel_requested"),
        retry_not_before=_parse_optional_utc_timestamp(
            document_mapping["retry_not_before"],
            "retry_not_before",
        ),
        worker_id=_parse_optional_opaque_id(document_mapping["worker_id"], "worker_id"),
        lease_token=_parse_optional_opaque_id(document_mapping["lease_token"], "lease_token"),
        lease_expires_at=_parse_optional_utc_timestamp(
            document_mapping["lease_expires_at"],
            "lease_expires_at",
        ),
        checkpoint_ref=checkpoint_ref,
        prior_output_refs=prior_output_refs,
        created_at=_parse_utc_timestamp(document_mapping["created_at"], "created_at"),
        updated_at=_parse_utc_timestamp(document_mapping["updated_at"], "updated_at"),
        started_at=_parse_optional_utc_timestamp(document_mapping["started_at"], "started_at"),
        completed_at=_parse_optional_utc_timestamp(document_mapping["completed_at"], "completed_at"),
        optimistic_version=_parse_ijson_int(
            document_mapping["optimistic_version"],
            "optimistic_version",
        ),
    )


def _validate_operation_record_fields(record: OperationRecord) -> None:
    _validate_contract_version_string(record.contract_version)
    _validate_opaque_id(record.operation_id, "operation_id")
    _validate_registry_name(record.job_kind, "job_kind")
    _validate_contract_version_string(record.job_contract_version)
    _validate_job_payload_binding(record.job_payload, record.job_payload_ref)
    if len(record.business_refs) > _MAX_BUSINESS_REFS:
        raise ValueError("business_refs exceeds maximum tuple size")
    for business_ref in record.business_refs:
        if type(business_ref) is not BusinessReference:
            raise ValueError("business_refs must contain BusinessReference")
    for artifact_ref in record.artifact_refs:
        if type(artifact_ref) is not ArtifactRef:
            raise ValueError("artifact_refs must contain ArtifactRef")
    if record.repository_operation_id is not None:
        _validate_opaque_id(record.repository_operation_id, "repository_operation_id")
    if record.checkpoint_ref is not None and type(record.checkpoint_ref) is not ArtifactRef:
        raise ValueError("checkpoint_ref must be ArtifactRef or None")
    if record.ready_closure_ref is not None and type(record.ready_closure_ref) is not ArtifactRef:
        raise ValueError("ready_closure_ref must be ArtifactRef or None")
    if type(record.status) is not OperationStatus:
        raise ValueError("status must be OperationStatus")
    if record.diagnostic is not None and type(record.diagnostic) is not OperationDiagnostic:
        raise ValueError("diagnostic must be OperationDiagnostic or None")
    if type(record.cancel_requested) is not bool:
        raise ValueError("cancel_requested must be a bool")
    _validate_datetime_field(record.created_at, "created_at")
    _validate_datetime_field(record.updated_at, "updated_at")
    if record.completed_at is not None:
        _validate_datetime_field(record.completed_at, "completed_at")
    _validate_ijson_int_value(record.optimistic_version, "optimistic_version")
    _reject_duplicate_artifact_ids(
        _collect_artifact_refs(
            record.job_payload_ref,
            record.artifact_refs,
            record.checkpoint_ref,
            record.ready_closure_ref,
        )
    )
    _validate_operation_status_fields(record)


def _validate_step_record_fields(record: StepRecord) -> None:
    _validate_contract_version_string(record.contract_version)
    _validate_opaque_id(record.step_id, "step_id")
    _validate_opaque_id(record.operation_id, "operation_id")
    _validate_registry_name(record.step_name, "step_name")
    if type(record.status) is not StepStatus:
        raise ValueError("status must be StepStatus")
    _validate_ijson_int_value(record.attempt_count, "attempt_count")
    if record.diagnostic is not None and type(record.diagnostic) is not OperationDiagnostic:
        raise ValueError("diagnostic must be OperationDiagnostic or None")
    if type(record.cancel_requested) is not bool:
        raise ValueError("cancel_requested must be a bool")
    if record.retry_not_before is not None:
        _validate_datetime_field(record.retry_not_before, "retry_not_before")
    if record.worker_id is not None:
        _validate_opaque_id(record.worker_id, "worker_id")
    if record.lease_token is not None:
        _validate_opaque_id(record.lease_token, "lease_token")
    if record.lease_expires_at is not None:
        _validate_datetime_field(record.lease_expires_at, "lease_expires_at")
    if record.checkpoint_ref is not None and type(record.checkpoint_ref) is not ArtifactRef:
        raise ValueError("checkpoint_ref must be ArtifactRef or None")
    for item in record.prior_output_refs:
        if type(item) is not ArtifactRef:
            raise ValueError("prior_output_refs must contain ArtifactRef")
    _validate_datetime_field(record.created_at, "created_at")
    _validate_datetime_field(record.updated_at, "updated_at")
    if record.started_at is not None:
        _validate_datetime_field(record.started_at, "started_at")
    if record.completed_at is not None:
        _validate_datetime_field(record.completed_at, "completed_at")
    _validate_ijson_int_value(record.optimistic_version, "optimistic_version")
    _reject_duplicate_artifact_ids(
        _collect_artifact_refs(None, record.prior_output_refs, record.checkpoint_ref)
    )
    _validate_step_status_fields(record)


def _validate_operation_status_fields(record: OperationRecord) -> None:
    status = record.status
    if status in {OperationStatus.FAILED, OperationStatus.MANUAL_RECOVERY_REQUIRED}:
        if record.diagnostic is None:
            raise ValueError("diagnostic is required for this operation status")
    elif status not in {OperationStatus.CANCELLED, OperationStatus.SUPERSEDED}:
        if record.diagnostic is not None:
            raise ValueError("diagnostic is forbidden for this operation status")
    if status.is_final_terminal():
        if record.completed_at is None:
            raise ValueError("completed_at is required for final terminal operation status")
    elif record.completed_at is not None:
        raise ValueError("completed_at is forbidden for non-final operation status")
    _require_timestamp_order(record.created_at, record.updated_at, "created_at", "updated_at")
    if record.completed_at is not None:
        _require_timestamp_order(
            record.created_at,
            record.completed_at,
            "created_at",
            "completed_at",
        )
        _require_timestamp_order(
            record.completed_at,
            record.updated_at,
            "completed_at",
            "updated_at",
        )


def _validate_step_status_fields(record: StepRecord) -> None:
    status = record.status
    lease_fields = (record.worker_id, record.lease_token, record.lease_expires_at)
    if status is StepStatus.RUNNING:
        if any(field is None for field in lease_fields):
            raise ValueError("RUNNING step requires worker_id, lease_token, and lease_expires_at")
        assert record.lease_expires_at is not None
        if record.lease_expires_at <= record.updated_at:
            raise ValueError("lease_expires_at must be later than updated_at for RUNNING step")
    elif any(field is not None for field in lease_fields):
        raise ValueError("lease identity fields are forbidden outside RUNNING step status")
    if status in {StepStatus.RETRY_WAIT, StepStatus.FAILED, StepStatus.MANUAL_RECOVERY_REQUIRED}:
        if record.diagnostic is None:
            raise ValueError("diagnostic is required for this step status")
    elif status is not StepStatus.CANCELLED:
        if record.diagnostic is not None:
            raise ValueError("diagnostic is forbidden for this step status")
    if status.is_final_terminal():
        if record.completed_at is None:
            raise ValueError("completed_at is required for final terminal step status")
    elif record.completed_at is not None:
        raise ValueError("completed_at is forbidden for non-final step status")
    if status is StepStatus.PENDING:
        if record.attempt_count != 0:
            raise ValueError("PENDING step requires attempt_count=0")
        if record.started_at is not None:
            raise ValueError("PENDING step requires started_at=null")
    elif status is StepStatus.CANCELLED:
        if record.attempt_count == 0:
            if record.started_at is not None:
                raise ValueError("CANCELLED step with attempt_count=0 requires started_at=null")
        elif record.started_at is None:
            raise ValueError("CANCELLED step with attempt_count>=1 requires started_at")
    else:
        if record.attempt_count < 1:
            raise ValueError("step status requires attempt_count>=1")
        if record.started_at is None:
            raise ValueError("step status requires started_at")
    if status is StepStatus.RETRY_WAIT:
        if record.retry_not_before is None:
            raise ValueError("RETRY_WAIT step requires retry_not_before")
        if record.retry_not_before < record.updated_at:
            raise ValueError("retry_not_before must be >= updated_at for RETRY_WAIT step")
    elif record.retry_not_before is not None:
        raise ValueError("retry_not_before is forbidden outside RETRY_WAIT step status")
    _require_timestamp_order(record.created_at, record.updated_at, "created_at", "updated_at")
    if record.started_at is not None:
        _require_timestamp_order(record.created_at, record.started_at, "created_at", "started_at")
        _require_timestamp_order(record.started_at, record.updated_at, "started_at", "updated_at")
    if record.completed_at is not None:
        _require_timestamp_order(
            record.created_at,
            record.completed_at,
            "created_at",
            "completed_at",
        )
        _require_timestamp_order(
            record.completed_at,
            record.updated_at,
            "completed_at",
            "updated_at",
        )
        if record.started_at is not None:
            _require_timestamp_order(
                record.started_at,
                record.completed_at,
                "started_at",
                "completed_at",
            )


def _require_timestamp_order(
    before: datetime,
    after: datetime,
    before_label: str,
    after_label: str,
) -> None:
    if before > after:
        raise ValueError(f"{before_label} must be <= {after_label}")


def _require_closed_document(
    document: object,
    allowed_keys: frozenset[str],
    label: str,
) -> dict[str, object]:
    if type(document) is not dict:
        raise ValueError(f"{label} must be an object")
    _reject_unknown_keys(document, allowed_keys, label)
    return document


def _reject_unknown_keys(payload: Mapping[str, object], allowed: frozenset[str], label: str) -> None:
    unknown = set(payload) - allowed
    if unknown:
        raise ValueError(f"{label} contains unknown fields")
    missing = allowed - set(payload)
    if missing:
        raise ValueError(f"{label} missing fields")


def _require_contract_version(value: object) -> None:
    if value != OPERATION_RUNTIME_CONTRACT_VERSION:
        raise ValueError("contract_version mismatch")


def _require_document_type(value: object, expected: str) -> None:
    if value != expected:
        raise ValueError("document_type mismatch")


def _require_contract_version_string(value: object) -> str:
    if type(value) is not str:
        raise ValueError("contract_version must be a string")
    _validate_contract_version_string(value)
    return value


def _parse_runtime_contract_version(value: object) -> str:
    version = _require_contract_version_string(value)
    _require_contract_version(version)
    return version


def _parse_job_contract_version(value: object) -> str:
    if type(value) is not str:
        raise ValueError("job_contract_version must be a string")
    _validate_contract_version_string(value)
    return value


def _validate_contract_version_string(value: str) -> None:
    if not _CONTRACT_VERSION_RE.fullmatch(value):
        raise ValueError("contract_version must be bounded ASCII printable")


def _parse_registry_name(value: object, label: str) -> str:
    if type(value) is not str:
        raise ValueError(f"{label} must be a string")
    _validate_registry_name(value, label)
    return value


def _validate_registry_name(value: str, label: str) -> None:
    if not _REGISTRY_NAME_RE.fullmatch(value):
        raise ValueError(f"{label} must match registry name pattern")


def _parse_opaque_id(value: object, label: str) -> str:
    if type(value) is not str:
        raise ValueError(f"{label} must be a string")
    _validate_opaque_id(value, label)
    return value


def _parse_optional_opaque_id(value: object, label: str) -> str | None:
    if value is None:
        return None
    return _parse_opaque_id(value, label)


def _validate_opaque_id(value: str, label: str) -> None:
    encoded = value.encode("utf-8")
    if not 1 <= len(encoded) <= _MAX_OPAQUE_ID_BYTES:
        raise ValueError(f"{label} must be 1..255 UTF-8 bytes")
    if _CONTROL_CHAR_RE.search(value):
        raise ValueError(f"{label} must not contain control characters")
    assert_no_host_path_identity(value, label=label)


def _parse_ijson_int(value: object, label: str) -> int:
    if type(value) is not int or isinstance(value, bool):
        raise ValueError(f"{label} must be an integer")
    _validate_ijson_int_value(value, label)
    return value


def _validate_ijson_int_value(value: int, label: str) -> None:
    if value < 0 or value > _IJSON_MAX_SAFE_INTEGER:
        raise ValueError(f"{label} must be a non-negative I-JSON safe integer")


def _require_bool(value: object, label: str) -> bool:
    if type(value) is not bool:
        raise ValueError(f"{label} must be a bool")
    return value


def _validate_diagnostic_code(value: str) -> None:
    if not _DIAGNOSTIC_CODE_RE.fullmatch(value):
        raise ValueError("diagnostic.code must match bounded opaque code pattern")


def _validate_diagnostic_message(value: str) -> None:
    encoded = value.encode("utf-8")
    if not 1 <= len(encoded) <= _MAX_DIAGNOSTIC_MESSAGE_BYTES:
        raise ValueError("diagnostic.message must be 1..4 KiB UTF-8")


def _parse_optional_diagnostic(value: object) -> OperationDiagnostic | None:
    if value is None:
        return None
    if type(value) is not dict:
        raise ValueError("diagnostic must be an object or null")
    _reject_unknown_keys(value, _DIAGNOSTIC_KEYS, "diagnostic")
    return OperationDiagnostic(
        code=_parse_diagnostic_code(value["code"]),
        message=_parse_diagnostic_message(value["message"]),
    )


def _parse_diagnostic_code(value: object) -> str:
    if type(value) is not str:
        raise ValueError("diagnostic.code must be a string")
    _validate_diagnostic_code(value)
    return value


def _parse_diagnostic_message(value: object) -> str:
    if type(value) is not str:
        raise ValueError("diagnostic.message must be a string")
    _validate_diagnostic_message(value)
    return value


def _parse_business_refs(value: object) -> tuple[BusinessReference, ...]:
    if type(value) is not list:
        raise ValueError("business_refs must be a list")
    if len(value) > _MAX_BUSINESS_REFS:
        raise ValueError("business_refs exceeds maximum tuple size")
    refs: list[BusinessReference] = []
    for index, item in enumerate(value):
        if type(item) is not dict:
            raise ValueError("business_refs items must be objects")
        _reject_unknown_keys(item, _BUSINESS_REFERENCE_KEYS, f"business_refs[{index}]")
        refs.append(
            BusinessReference(
                kind=_parse_registry_name(item["kind"], f"business_refs[{index}].kind"),
                value=_parse_opaque_id(item["value"], f"business_refs[{index}].value"),
            )
        )
    return tuple(refs)


def _parse_artifact_ref_list(value: object, *, label: str) -> tuple[ArtifactRef, ...]:
    if type(value) is not list:
        raise ValueError(f"{label} must be a list")
    refs: list[ArtifactRef] = []
    for index, item in enumerate(value):
        if type(item) is not dict:
            raise ValueError(f"{label}[{index}] must be an object")
        refs.append(artifact_ref_from_dict(item))
    if len(refs) > _MAX_REFS_PER_RECORD:
        raise ValueError(f"{label} exceeds maximum tuple size")
    return tuple(refs)


def _parse_optional_artifact_ref(value: object) -> ArtifactRef | None:
    if value is None:
        return None
    if type(value) is not dict:
        raise ValueError("artifact ref must be an object or null")
    return artifact_ref_from_dict(value)


def _parse_job_payload_binding(
    job_payload: object,
    job_payload_ref: object,
) -> tuple[bytes | None, ArtifactRef | None]:
    inline_present = job_payload is not None
    ref_present = job_payload_ref is not None
    if inline_present == ref_present:
        raise ValueError("job_payload and job_payload_ref must be mutually exclusive")
    if inline_present:
        if type(job_payload) is not dict:
            raise ValueError("job_payload must be a JSON object")
        return _canonicalize_job_payload_object(job_payload), None
    if type(job_payload_ref) is not dict:
        raise ValueError("job_payload_ref must be an object or null")
    return None, artifact_ref_from_dict(job_payload_ref)


def _validate_job_payload_binding(
    job_payload: bytes | None,
    job_payload_ref: ArtifactRef | None,
) -> None:
    inline_present = job_payload is not None
    ref_present = job_payload_ref is not None
    if inline_present == ref_present:
        raise ValueError("job_payload and job_payload_ref must be mutually exclusive")
    if job_payload is not None:
        if type(job_payload) is not bytes:
            raise ValueError("job_payload must be canonical JSON bytes or None")
        if len(job_payload) > _MAX_INLINE_PAYLOAD_BYTES:
            raise ValueError("job_payload exceeds maximum inline payload size")
    if job_payload_ref is not None and type(job_payload_ref) is not ArtifactRef:
        raise ValueError("job_payload_ref must be ArtifactRef or None")


def _canonicalize_job_payload_object(payload: dict[str, object]) -> bytes:
    _validate_json_structure(payload)
    try:
        canonical = canonicalize_json_value(payload)
    except CanonicalEncodingError as exc:
        raise ValueError(str(exc)) from exc
    if len(canonical) > _MAX_INLINE_PAYLOAD_BYTES:
        raise ValueError("job_payload exceeds maximum inline payload size")
    return canonical


def _decode_job_payload_object(job_payload: bytes | None) -> dict[str, object] | None:
    if job_payload is None:
        return None
    try:
        canonical = canonicalize_jcs(job_payload)
    except CanonicalEncodingError as exc:
        raise ValueError(str(exc)) from exc
    value = json.loads(canonical)
    if type(value) is not dict:
        raise ValueError("job_payload must be a JSON object")
    return value


def _validate_json_structure(value: object, *, depth: int = 1, aggregate: int = 0) -> int:
    if depth > _MAX_JSON_DEPTH:
        raise ValueError("job_payload exceeds maximum JSON depth")
    if isinstance(value, dict):
        next_aggregate = aggregate + 1
        if next_aggregate > _MAX_JSON_AGGREGATE:
            raise ValueError("job_payload exceeds maximum JSON aggregate size")
        for key, item in value.items():
            if type(key) is not str:
                raise ValueError("job_payload object keys must be strings")
            if len(key.encode("utf-8")) > _MAX_JSON_KEY_BYTES:
                raise ValueError("job_payload object key exceeds maximum size")
            next_aggregate = _validate_json_structure(item, depth=depth + 1, aggregate=next_aggregate)
        return next_aggregate
    if isinstance(value, list):
        next_aggregate = aggregate + 1
        if next_aggregate > _MAX_JSON_AGGREGATE:
            raise ValueError("job_payload exceeds maximum JSON aggregate size")
        for item in value:
            next_aggregate = _validate_json_structure(item, depth=depth + 1, aggregate=next_aggregate)
        return next_aggregate
    if type(value) is str:
        if len(value.encode("utf-8")) > _MAX_JSON_STRING_BYTES:
            raise ValueError("job_payload string exceeds maximum size")
        return aggregate
    if value is None or type(value) is bool:
        return aggregate
    if type(value) is int:
        if isinstance(value, bool) or value < _IJSON_MIN_SAFE_INTEGER or value > _IJSON_MAX_SAFE_INTEGER:
            raise ValueError("job_payload integer outside I-JSON safe range")
        return aggregate
    if type(value) is float:
        raise ValueError("job_payload must not contain non-I-JSON numbers")
    raise ValueError("job_payload must contain only JSON values")


_IJSON_MIN_SAFE_INTEGER = -((2**53) - 1)


def _parse_utc_timestamp(value: object, label: str) -> datetime:
    if type(value) is not str:
        raise ValueError(f"{label} must be a string")
    return _parse_utc_timestamp_text(value, label)


def _parse_optional_utc_timestamp(value: object, label: str) -> datetime | None:
    if value is None:
        return None
    return _parse_utc_timestamp(value, label)


def _parse_utc_timestamp_text(text: str, label: str) -> datetime:
    match = _TIMESTAMP_RE.fullmatch(text)
    if match is None:
        raise ValueError(f"{label} must be canonical UTC timestamp")
    year, month, day, hour, minute, second = (int(match.group(i)) for i in range(1, 7))
    fraction = match.group(7)
    if fraction is not None and len(fraction) > 6:
        raise ValueError(f"{label} must be canonical UTC timestamp")
    _validate_civil_date(year, month, day)
    if hour > 23 or minute > 59 or second > 59:
        raise ValueError(f"{label} must be canonical UTC timestamp")
    canonical = _format_utc_timestamp_parts(year, month, day, hour, minute, second, fraction)
    if canonical != text:
        raise ValueError(f"{label} must be canonical UTC timestamp")
    microsecond = int(fraction.ljust(6, "0")) if fraction is not None else 0
    return datetime(year, month, day, hour, minute, second, microsecond, tzinfo=UTC)


def _format_utc_timestamp(value: datetime) -> str:
    if value.tzinfo is None or value.utcoffset() != UTC.utcoffset(value):
        raise ValueError("timestamp must use UTC")
    return _format_utc_timestamp_parts(
        value.year,
        value.month,
        value.day,
        value.hour,
        value.minute,
        value.second,
        f"{value.microsecond:06d}".rstrip("0") or None,
    )


def _format_utc_timestamp_parts(
    year: int,
    month: int,
    day: int,
    hour: int,
    minute: int,
    second: int,
    fraction: str | None,
) -> str:
    fraction_text = ""
    if fraction:
        trimmed = fraction.rstrip("0")
        if trimmed:
            fraction_text = f".{trimmed}"
    return f"{year:04d}-{month:02d}-{day:02d}T{hour:02d}:{minute:02d}:{second:02d}{fraction_text}Z"


def _validate_datetime_field(value: datetime, label: str) -> None:
    if value.tzinfo is None or value.utcoffset() != UTC.utcoffset(value):
        raise ValueError(f"{label} must use UTC")


def _validate_civil_date(year: int, month: int, day: int) -> None:
    if year < 1 or month < 1 or month > 12 or day < 1:
        raise ValueError("timestamp civil date out of range")
    if day > _days_in_month(year, month):
        raise ValueError("timestamp civil date out of range")


def _days_in_month(year: int, month: int) -> int:
    if month in {1, 3, 5, 7, 8, 10, 12}:
        return 31
    if month in {4, 6, 9, 11}:
        return 30
    return 29 if _is_leap_year(year) else 28


def _is_leap_year(year: int) -> bool:
    return year % 4 == 0 and (year % 100 != 0 or year % 400 == 0)


def _collect_artifact_refs(
    job_payload_ref: ArtifactRef | None,
    artifact_refs: tuple[ArtifactRef, ...],
    checkpoint_ref: ArtifactRef | None,
    ready_closure_ref: ArtifactRef | None = None,
) -> tuple[ArtifactRef, ...]:
    refs: list[ArtifactRef] = []
    if job_payload_ref is not None:
        refs.append(job_payload_ref)
    refs.extend(artifact_refs)
    if checkpoint_ref is not None:
        refs.append(checkpoint_ref)
    if ready_closure_ref is not None:
        refs.append(ready_closure_ref)
    if len(refs) > _MAX_REFS_PER_RECORD:
        raise ValueError("artifact refs exceed maximum per record")
    return tuple(refs)


def _reject_duplicate_artifact_ids(refs: tuple[ArtifactRef, ...]) -> None:
    seen: set[str] = set()
    for ref in refs:
        if ref.artifact_id in seen:
            raise ValueError("duplicate artifact_id in record")
        seen.add(ref.artifact_id)


def _parse_operation_status(value: object) -> OperationStatus:
    if type(value) is not str:
        raise ValueError("status must be a string")
    try:
        return OperationStatus(value)
    except ValueError as exc:
        raise ValueError("status must be a known OperationStatus") from exc


def _parse_step_status(value: object) -> StepStatus:
    if type(value) is not str:
        raise ValueError("status must be a string")
    try:
        return StepStatus(value)
    except ValueError as exc:
        raise ValueError("status must be a known StepStatus") from exc
