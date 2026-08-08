"""Typed models for durable Versioned import operations and import packages."""

from __future__ import annotations

import re
import struct
import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import Annotated, Self
from uuid import UUID

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StrictBool,
    StrictInt,
    field_validator,
    model_validator,
)

from gateway_repository_contracts import (
    OperationStatus,
    RepositoryArtifactRef,
    SimpleError,
    UnknownTypePolicy,
    VerificationPolicy,
    VersionedImportResult,
)
from gateway_repository_contracts.types import BoundedOpaqueString
from gateway_repository_service.arrow_mapping import (
    TemporalSqlTypeKind,
    UnknownSqlTypeError,
    arrow_type,
    classify_temporal_sql_type,
)
from gateway_repository_service.mutation_store import IdempotencyKeyHash

MANIFEST_ENTRY_NAME = "manifest.json"
REPLAY_SQL_ENTRY_NAME = "replay.sql"
STAGED_MANIFEST_FILENAME = "manifest.json"
STAGED_REPLAY_SQL_FILENAME = "replay.sql"

_MAX_IDENTIFIER_CODE_POINTS = 64
_MAX_MANIFEST_SQL_TYPE_LENGTH = 1024
_BOUNDED_UNKNOWN_SQL_TYPE = re.compile(r"^[A-Za-z0-9_(),.' +\\-]+$")

VERSIONED_IMPORT_FINGERPRINT_PREFIX_V1 = b"versioned_import/v1\x00"
MANUAL_RECOVERY_REQUIRED_CODE = "MANUAL_RECOVERY_REQUIRED"
ORDINARY_TERMINAL_ERROR_CODES = frozenset({
    "IMPORT_REJECTED",
    "EXPECTED_COMMIT_MISMATCH",
    "VERIFICATION_FAILED_NOT_PUBLISHED",
})
IMPORT_ADMISSION_PENDING_STATUS = "ADMISSION_PENDING"


class ImportOperationStoreError(RuntimeError):
    """Base error for import operation store failures."""


class ImportStoreInvariantError(ImportOperationStoreError):
    """Raised when a readable durable row violates import operation invariants."""


class ImportFingerprintConflict(ImportOperationStoreError):
    """Raised when the same idempotency scope is reused with a different fingerprint."""

    def __init__(self, *, repository_id: UUID) -> None:
        self.repository_id = repository_id
        super().__init__(f"idempotency fingerprint conflict for repository {repository_id}")


class ImportQueueFull(ImportOperationStoreError):
    """Raised when the global QUEUED import limit has been reached."""


class ImportManualBarrierRequired(ImportOperationStoreError):
    """Raised when a repository has an unresolved manual recovery barrier."""


class ImportArtifactBindingRejected(ImportOperationStoreError):
    """Raised when artifact lifecycle binding does not match the import request."""


class ImportOperationTransitionRejected(ImportOperationStoreError):
    """Raised when an operation transition is not allowed."""


class ImportReplayCountRejected(ImportOperationStoreError):
    """Raised when automatic replay count cannot be incremented."""


class ImportPackageError(RuntimeError):
    """Base error for import package validation failures."""


class ImportPackageRejected(ImportPackageError):
    """Raised when an import package fails structural or manifest validation."""


class _ClosedManifestModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


def validate_manifest_identifier(value: str) -> str:
    if not value:
        raise ValueError("identifier must not be empty")
    code_points = 0
    for char in value:
        code_points += 1
        if code_points > _MAX_IDENTIFIER_CODE_POINTS:
            raise ValueError("identifier exceeds maximum length")
        ordinal = ord(char)
        if char == "\x00" or ordinal < 32 or ordinal == 127 or char in {"/", "\\"}:
            raise ValueError("identifier contains forbidden characters")
    return value


def validate_manifest_table_name(value: str) -> str:
    value = validate_manifest_identifier(value)
    if value != value.strip():
        raise ValueError("table name must not have leading or trailing whitespace")
    return value


def validate_manifest_sql_type(value: str) -> str:
    if not value or len(value) > _MAX_MANIFEST_SQL_TYPE_LENGTH:
        raise ValueError("sql_type length is out of bounds")
    if value != value.strip():
        raise ValueError("sql_type must not have leading or trailing whitespace")
    if any(ord(char) < 32 or ord(char) == 127 for char in value):
        raise ValueError("sql_type contains control characters")
    classification, _ = classify_temporal_sql_type(value)
    if classification == TemporalSqlTypeKind.MALFORMED:
        raise ValueError("sql_type is not a bounded normalized physical spelling") from None
    try:
        arrow_type(value, UnknownTypePolicy.REJECT)
    except UnknownSqlTypeError:
        if classification != TemporalSqlTypeKind.NOT_TEMPORAL:
            raise ValueError("sql_type is not a bounded normalized physical spelling") from None
        if _BOUNDED_UNKNOWN_SQL_TYPE.fullmatch(value) is None:
            raise ValueError("sql_type is not a bounded normalized physical spelling") from None
    return value


class ImportManifestColumn(_ClosedManifestModel):
    name: str
    sql_type: str
    nullable: StrictBool

    @field_validator("name")
    @classmethod
    def _validate_name(cls, value: str) -> str:
        return validate_manifest_identifier(value)

    @field_validator("sql_type")
    @classmethod
    def _validate_sql_type(cls, value: str) -> str:
        return validate_manifest_sql_type(value)


class ImportManifestSchema(_ClosedManifestModel):
    columns: tuple[ImportManifestColumn, ...]
    primary_key: tuple[str, ...]

    @field_validator("primary_key")
    @classmethod
    def _validate_primary_key_names(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        seen: set[str] = set()
        for item in value:
            validate_manifest_identifier(item)
            if item in seen:
                raise ValueError("primary key column names must be unique")
            seen.add(item)
        return value


class ImportManifestTable(_ClosedManifestModel):
    name: str
    table_schema: ImportManifestSchema = Field(alias="schema")
    row_count: Annotated[StrictInt, Field(ge=0)]

    model_config = ConfigDict(extra="forbid", populate_by_name=False)

    @field_validator("row_count", mode="before")
    @classmethod
    def _reject_bool_row_count(cls, value: object) -> object:
        if isinstance(value, bool):
            raise ValueError("row_count must be an integer")
        return value

    @field_validator("name")
    @classmethod
    def _validate_name(cls, value: str) -> str:
        return validate_manifest_table_name(value)


class ImportManifest(_ClosedManifestModel):
    package_version: Annotated[StrictInt, Field(ge=1, le=1)]
    canonicalization_manifest_digest: BoundedOpaqueString
    tables: tuple[ImportManifestTable, ...]

    @field_validator("package_version", mode="before")
    @classmethod
    def _reject_bool_package_version(cls, value: object) -> object:
        if isinstance(value, bool):
            raise ValueError("package_version must be an integer")
        return value

    @model_validator(mode="after")
    def _validate_table_order_and_references(self) -> Self:
        table_names: list[str] = []
        previous_name_bytes: bytes | None = None
        for table in self.tables:
            if table.name in table_names:
                raise ValueError("table names must be unique")
            table_names.append(table.name)
            current_name_bytes = table.name.encode("utf-8")
            if previous_name_bytes is not None and current_name_bytes <= previous_name_bytes:
                raise ValueError("tables must be sorted by canonical UTF-8 name bytes")
            previous_name_bytes = current_name_bytes

            column_names: set[str] = set()
            for column in table.table_schema.columns:
                if column.name in column_names:
                    raise ValueError("column names must be unique within a table")
                column_names.add(column.name)
            for key_name in table.table_schema.primary_key:
                if key_name not in column_names:
                    raise ValueError("primary key references unknown column")
        return self


@dataclass(frozen=True, slots=True)
class ValidatedImportPackage:
    manifest: ImportManifest
    manifest_path: Path
    replay_sql_path: Path
    observed_raw_size_bytes: int
    observed_raw_sha256: str


class RecoveryAuditAction(StrEnum):
    INSPECT_APPLY_SUCCESS = "INSPECT_APPLY_SUCCESS"
    INSPECT_APPLY_NOT_PUBLISHED = "INSPECT_APPLY_NOT_PUBLISHED"


class ManualCorrectionDecision(StrEnum):
    SUCCEEDED = "SUCCEEDED"
    NOT_PUBLISHED = "NOT_PUBLISHED"


@dataclass(frozen=True, slots=True)
class ImportRequestBinding:
    repository_id: UUID
    artifact_ref: RepositoryArtifactRef
    target_ref: str
    expected_commit_id: str
    verification_policy: VerificationPolicy
    unknown_type_policy: UnknownTypePolicy


@dataclass(frozen=True, slots=True)
class StoredImportOperation:
    operation_id: UUID
    repository_id: UUID
    durable_status: str
    status: OperationStatus | None
    artifact_id: UUID
    private_ref_name: str
    operation_marker: str
    automatic_replay_count: int
    result: VersionedImportResult | None
    error: SimpleError | None
    created_at: str
    started_at: str | None
    updated_at: str
    completed_at: str | None
    canonicalization_manifest_digest: str | None


@dataclass(frozen=True, slots=True)
class ImportOperationExecutionContext:
    operation_id: UUID
    repository_id: UUID
    artifact_id: UUID
    artifact_media_type: str
    artifact_size_bytes: int
    artifact_raw_sha256: str
    target_ref: str
    expected_commit_id: str
    verification_policy: VerificationPolicy
    unknown_type_policy: UnknownTypePolicy
    private_ref_name: str
    operation_marker: str


@dataclass(frozen=True, slots=True)
class ClaimOrEnqueueResult:
    operation_id: UUID
    is_new: bool
    operation: StoredImportOperation


@dataclass(frozen=True, slots=True)
class ReplayLookup:
    operation: StoredImportOperation
    stored_fingerprint: bytes
    durable_status: str


@dataclass(frozen=True, slots=True)
class ArtifactOperationReference:
    operation_id: UUID
    durable_status: str
    status: OperationStatus | None
    is_protected: bool


def derive_private_ref_name(operation_id: UUID) -> str:
    return f"gateway-import-{operation_id.hex}"


def derive_operation_marker(operation_id: UUID) -> str:
    return f"gateway-versioned-import operation_id={operation_id}"


def versioned_import_fingerprint_v1(
    *,
    binding: ImportRequestBinding,
    key_hash: IdempotencyKeyHash,
) -> bytes:
    if binding.target_ref != "main":
        raise ValueError("target_ref must be main")
    raw_sha256 = bytes.fromhex(binding.artifact_ref.raw_sha256)
    if len(raw_sha256) != 32:
        raise ValueError("artifact raw_sha256 must be 64 lowercase hex characters")
    return (
        VERSIONED_IMPORT_FINGERPRINT_PREFIX_V1
        + binding.repository_id.bytes
        + binding.artifact_ref.artifact_id.bytes
        + binding.artifact_ref.media_type.encode("utf-8")
        + b"\x00"
        + struct.pack(">Q", binding.artifact_ref.size_bytes)
        + raw_sha256
        + binding.target_ref.encode("utf-8")
        + b"\x00"
        + binding.expected_commit_id.encode("utf-8")
        + b"\x00"
        + binding.verification_policy.value.encode("utf-8")
        + b"\x00"
        + binding.unknown_type_policy.value.encode("utf-8")
        + b"\x00"
        + key_hash.digest
    )


def is_manual_recovery_error(error: SimpleError | None) -> bool:
    return error is not None and error.code == MANUAL_RECOVERY_REQUIRED_CODE


def is_protected_operation_status(status: OperationStatus, error: SimpleError | None) -> bool:
    if status in {OperationStatus.QUEUED, OperationStatus.RUNNING}:
        return True
    return status == OperationStatus.FAILED and is_manual_recovery_error(error)


def is_protected_durable_status(
    durable_status: str,
    wire_status: OperationStatus | None,
    error: SimpleError | None,
) -> bool:
    if durable_status == IMPORT_ADMISSION_PENDING_STATUS:
        return True
    if wire_status is None:
        return False
    return is_protected_operation_status(wire_status, error)


def validate_pending_operation_row(
    row: sqlite3.Row,
    *,
    result: VersionedImportResult | None,
    error: SimpleError | None,
) -> None:
    if result is not None:
        raise ImportStoreInvariantError("pending import operation row has result payload")
    if error is not None:
        raise ImportStoreInvariantError("pending import operation row has error payload")
    if row["started_at"] is not None:
        raise ImportStoreInvariantError("pending import operation row has started_at")
    if row["completed_at"] is not None:
        raise ImportStoreInvariantError("pending import operation row has completed_at")
    if row["canonicalization_manifest_digest"] is not None:
        raise ImportStoreInvariantError(
            "pending import operation row has canonicalization_manifest_digest"
        )


def validate_result_matches_operation_row(
    row: sqlite3.Row,
    result: VersionedImportResult,
) -> None:
    if str(row["artifact_id"]) != str(result.artifact_id):
        raise ImportOperationTransitionRejected("result artifact_id does not match operation request")
    if str(row["target_ref"]) != result.target_ref:
        raise ImportOperationTransitionRejected("result target_ref does not match operation request")
    if str(row["expected_commit_id"]) != result.expected_commit_id:
        raise ImportOperationTransitionRejected(
            "result expected_commit_id does not match operation request"
        )
    if str(row["requested_verification_policy"]) != result.completed_verification_policy.value:
        raise ImportOperationTransitionRejected(
            "result completed_verification_policy does not match operation request"
        )
    if str(row["unknown_type_policy"]) != result.unknown_type_policy.value:
        raise ImportOperationTransitionRejected(
            "result unknown_type_policy does not match operation request"
        )


def utc_now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat()
