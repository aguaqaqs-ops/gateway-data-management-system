"""Repository import operation facts for Submit application logic."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class RepositoryImportOperationStatus(StrEnum):
    QUEUED = "QUEUED"
    RUNNING = "RUNNING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"


@dataclass(frozen=True, slots=True)
class RepositoryImportOperationResult:
    commit_id: str
    target_ref: str
    artifact_id: str
    canonicalization_manifest_digest: str
    expected_commit_id: str
    completed_verification_policy: str
    unknown_type_policy: str


@dataclass(frozen=True, slots=True)
class RepositoryImportOperationError:
    code: str
    message: str


@dataclass(frozen=True, slots=True)
class RepositoryImportOperation:
    operation_id: str
    status: RepositoryImportOperationStatus
    result: RepositoryImportOperationResult | None = None
    error: RepositoryImportOperationError | None = None


def repository_import_operation_from_evidence_payload(
    operation_payload: dict[str, object],
) -> RepositoryImportOperation:
    operation_id = operation_payload.get("operation_id")
    if type(operation_id) is not str or not operation_id:
        raise ValueError("operation_id must be a non-empty string")
    status_raw = operation_payload.get("status")
    if type(status_raw) is not str:
        raise ValueError("status must be a string")
    status = RepositoryImportOperationStatus(status_raw)
    result: RepositoryImportOperationResult | None = None
    result_raw = operation_payload.get("result")
    if result_raw is not None:
        if type(result_raw) is not dict:
            raise ValueError("result must be an object")
        mapping = result_raw
        result = RepositoryImportOperationResult(
            commit_id=str(mapping["commit_id"]),
            target_ref=str(mapping["target_ref"]),
            artifact_id=str(mapping["artifact_id"]),
            canonicalization_manifest_digest=str(mapping["canonicalization_manifest_digest"]),
            expected_commit_id=str(mapping["expected_commit_id"]),
            completed_verification_policy=str(mapping["completed_verification_policy"]),
            unknown_type_policy=str(mapping["unknown_type_policy"]),
        )
    error: RepositoryImportOperationError | None = None
    error_raw = operation_payload.get("error")
    if error_raw is not None:
        if type(error_raw) is not dict:
            raise ValueError("error must be an object")
        err = error_raw
        error = RepositoryImportOperationError(
            code=str(err["code"]),
            message=str(err["message"]),
        )
    return RepositoryImportOperation(
        operation_id=operation_id,
        status=status,
        result=result,
        error=error,
    )
