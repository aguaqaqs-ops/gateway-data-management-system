"""Typed models for durable Versioned import operations."""

from __future__ import annotations

import struct
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from uuid import UUID

from gateway_repository_contracts import (
    OperationStatus,
    RepositoryArtifactRef,
    SimpleError,
    UnknownTypePolicy,
    VerificationPolicy,
    VersionedImportResult,
)
from gateway_repository_service.mutation_store import IdempotencyKeyHash

VERSIONED_IMPORT_FINGERPRINT_PREFIX_V1 = b"versioned_import/v1\x00"
MANUAL_RECOVERY_REQUIRED_CODE = "MANUAL_RECOVERY_REQUIRED"


class ImportOperationStoreError(RuntimeError):
    """Base error for import operation store failures."""


class ImportFingerprintConflict(ImportOperationStoreError):
    """Raised when the same idempotency scope is reused with a different fingerprint."""

    def __init__(self, *, repository_id: UUID) -> None:
        self.repository_id = repository_id
        super().__init__(f"idempotency fingerprint conflict for repository {repository_id}")


class ImportOperationTransitionRejected(ImportOperationStoreError):
    """Raised when an operation transition is not allowed."""


class ImportReplayCountRejected(ImportOperationStoreError):
    """Raised when automatic replay count cannot be incremented."""


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
    status: OperationStatus
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
class ClaimOrEnqueueResult:
    operation_id: UUID
    is_new: bool
    operation: StoredImportOperation


@dataclass(frozen=True, slots=True)
class ArtifactOperationReference:
    operation_id: UUID
    status: OperationStatus
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


def utc_now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat()
