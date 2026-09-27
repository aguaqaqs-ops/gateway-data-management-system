"""Repository Service wire DTO encoding and decoding for write adapters."""

from __future__ import annotations

from uuid import UUID

from gateway_repository_contracts import (
    RepositoryArtifactRef as WireRepositoryArtifactRef,
    SubmitVersionedImportRequest,
    UnknownTypePolicy,
    UploadArtifactResponse,
    VerificationPolicy,
    VersionedOperation,
)
from gateway_shared_kernel.jcs import canonicalize_json_value

from gateway_backend.application.submission.contracts import (
    RepositoryImportOperation,
    RepositoryImportOperationError,
    RepositoryImportOperationResult,
    RepositoryImportOperationStatus,
)
from gateway_backend.capabilities.storage_projection import REPOSITORY_IMPORT_MEDIA_TYPE
from gateway_backend.domain.submission.models import RepositoryArtifactRef


def repository_artifact_ref_to_wire(ref: RepositoryArtifactRef) -> WireRepositoryArtifactRef:
    return WireRepositoryArtifactRef(
        artifact_id=UUID(ref.artifact_id),
        media_type=ref.media_type,
        size_bytes=ref.size_bytes,
        raw_sha256=_wire_repository_raw_sha256(ref.raw_sha256),
    )


def repository_artifact_ref_from_upload_response(response: UploadArtifactResponse) -> RepositoryArtifactRef:
    wire_ref = response.artifact_ref
    return RepositoryArtifactRef(
        artifact_id=str(wire_ref.artifact_id),
        media_type=str(wire_ref.media_type),
        size_bytes=int(wire_ref.size_bytes),
        raw_sha256=str(wire_ref.raw_sha256),
    )


def build_import_request_bytes(
    *,
    repository_id: str,
    repository_artifact_ref: RepositoryArtifactRef,
    expected_commit_id: str,
) -> bytes:
    request = SubmitVersionedImportRequest(
        repository_id=UUID(repository_id),
        artifact_ref=repository_artifact_ref_to_wire(repository_artifact_ref),
        target_ref="main",
        expected_commit_id=expected_commit_id,
        verification_policy=VerificationPolicy.STRUCTURAL,
        unknown_type_policy=UnknownTypePolicy.REJECT,
    )
    return canonicalize_json_value(request.model_dump(mode="json"))


def import_operation_from_wire(operation: VersionedOperation) -> RepositoryImportOperation:
    result: RepositoryImportOperationResult | None = None
    if operation.result is not None:
        wire_result = operation.result
        result = RepositoryImportOperationResult(
            commit_id=str(wire_result.commit_id),
            target_ref=str(wire_result.target_ref),
            artifact_id=str(wire_result.artifact_id),
            canonicalization_manifest_digest=str(wire_result.canonicalization_manifest_digest),
            expected_commit_id=str(wire_result.expected_commit_id),
            completed_verification_policy=str(wire_result.completed_verification_policy.value),
            unknown_type_policy=str(wire_result.unknown_type_policy.value),
        )
    error: RepositoryImportOperationError | None = None
    if operation.error is not None:
        wire_error = operation.error
        error = RepositoryImportOperationError(
            code=str(wire_error.code),
            message=str(wire_error.message),
            details=(
                None
                if wire_error.details is None
                else dict(wire_error.details)
            ),
            request_id=(
                None
                if wire_error.request_id is None
                else str(wire_error.request_id)
            ),
        )
    status = RepositoryImportOperationStatus(operation.status.value)
    return RepositoryImportOperation(
        operation_id=str(operation.operation_id),
        status=status,
        result=result,
        error=error,
    )


def import_operation_from_evidence_payload(operation_payload: dict[str, object]) -> RepositoryImportOperation:
    operation = VersionedOperation.model_validate(operation_payload)
    return import_operation_from_wire(operation)


def _wire_repository_raw_sha256(value: str) -> str:
    return value.removeprefix("sha256:")
