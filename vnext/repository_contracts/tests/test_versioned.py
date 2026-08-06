"""Focused tests for the thin Versioned Repository DTOs."""

from __future__ import annotations

from uuid import UUID

import pytest
from pydantic import ValidationError

from gateway_repository_contracts import (
    CreateRepositoryResponse,
    OperationStatus,
    RepositoryArtifactRef,
    SimpleError,
    SubmitVersionedImportRequest,
    UnknownTypePolicy,
    VerificationPolicy,
    VersionedImportResult,
    VersionedOperation,
)

REPOSITORY_ID = UUID("018f0f3e-7b0a-7c15-8a9e-2e4b9f4d2c11")
ARTIFACT_ID = UUID("018f0f3e-7b0a-7c16-8a9e-2e4b9f4d2c11")
OPERATION_ID = UUID("018f0f3e-7b0a-7c17-8a9e-2e4b9f4d2c11")
SHA256 = "a" * 64


def artifact_ref() -> RepositoryArtifactRef:
    return RepositoryArtifactRef(
        artifact_id=ARTIFACT_ID,
        media_type="application/vnd.gateway.repository-import.v1+tar+zstd",
        size_bytes=12,
        raw_sha256=SHA256,
    )


def import_request_payload(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "repository_id": str(REPOSITORY_ID),
        "artifact_ref": artifact_ref().model_dump(),
        "target_ref": "main",
        "expected_commit_id": "commit-0",
    }
    payload.update(overrides)
    return payload


def import_result_payload(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "commit_id": "commit-1",
        "target_ref": "main",
        "artifact_id": str(ARTIFACT_ID),
        "canonicalization_manifest_digest": "manifest-digest-1",
        "expected_commit_id": "commit-0",
        "completed_verification_policy": "STRUCTURAL",
        "unknown_type_policy": "REJECT",
    }
    payload.update(overrides)
    return payload


def test_repository_artifact_ref_has_only_raw_transport_fields() -> None:
    ref = artifact_ref()

    assert ref.artifact_id == ARTIFACT_ID
    assert ref.media_type.startswith("application/")
    assert ref.size_bytes == 12
    assert ref.raw_sha256 == SHA256
    assert set(ref.model_dump()) == {"artifact_id", "media_type", "size_bytes", "raw_sha256"}


def test_repository_artifact_ref_rejects_extra_semantic_fields() -> None:
    with pytest.raises(ValidationError):
        payload = artifact_ref().model_dump()
        payload["content_digest"] = "business-digest"
        RepositoryArtifactRef.model_validate(payload)


def test_pydantic_uses_ordinary_uuid_values() -> None:
    response = CreateRepositoryResponse.model_validate(
        {
            "repository_id": str(REPOSITORY_ID),
            "default_ref": "main",
            "initial_commit_id": "commit-1",
        }
    )

    assert isinstance(response.repository_id, UUID)
    assert response.repository_id == REPOSITORY_ID


def test_simple_error_has_no_legacy_failure_dimensions() -> None:
    error = SimpleError(
        code="IMPORT_REJECTED",
        message="manifest rejected",
        details={"reason": "schema"},
        request_id="request-1",
    )

    assert error.model_dump() == {
        "code": "IMPORT_REJECTED",
        "message": "manifest rejected",
        "details": {"reason": "schema"},
        "request_id": "request-1",
    }


def test_operation_status_is_the_simplified_v1_set() -> None:
    assert {status.value for status in OperationStatus} == {
        "QUEUED",
        "RUNNING",
        "SUCCEEDED",
        "FAILED",
    }


def test_verification_policy_values() -> None:
    assert {policy.value for policy in VerificationPolicy} == {
        "NONE",
        "STRUCTURAL",
        "FULL_SCAN",
    }


def test_unknown_type_policy_values() -> None:
    assert {policy.value for policy in UnknownTypePolicy} == {
        "REJECT",
        "STRINGIFY",
    }


def test_import_request_keeps_repository_and_artifact_scopes_distinct() -> None:
    request = SubmitVersionedImportRequest.model_validate(import_request_payload())

    assert request.repository_id == REPOSITORY_ID
    assert request.artifact_ref.artifact_id == ARTIFACT_ID
    assert "idempotency_key" not in request.model_dump()


def test_import_request_defaults_policies_to_structural_and_reject() -> None:
    request = SubmitVersionedImportRequest.model_validate(import_request_payload())

    assert request.verification_policy == VerificationPolicy.STRUCTURAL
    assert request.unknown_type_policy == UnknownTypePolicy.REJECT


def test_import_request_accepts_explicit_policies() -> None:
    request = SubmitVersionedImportRequest.model_validate(
        import_request_payload(
            verification_policy="FULL_SCAN",
            unknown_type_policy="STRINGIFY",
        )
    )

    assert request.verification_policy == VerificationPolicy.FULL_SCAN
    assert request.unknown_type_policy == UnknownTypePolicy.STRINGIFY


@pytest.mark.parametrize("target_ref", ["feature", ""])
def test_import_request_rejects_non_main_target_ref(target_ref: str) -> None:
    with pytest.raises(ValidationError):
        SubmitVersionedImportRequest.model_validate(
            import_request_payload(target_ref=target_ref)
        )


def test_import_result_echoes_full_binding() -> None:
    result = VersionedImportResult.model_validate(import_result_payload())

    assert result.canonicalization_manifest_digest == "manifest-digest-1"
    assert result.expected_commit_id == "commit-0"
    assert result.completed_verification_policy == VerificationPolicy.STRUCTURAL
    assert result.unknown_type_policy == UnknownTypePolicy.REJECT
    assert set(result.model_dump()) == {
        "commit_id",
        "target_ref",
        "artifact_id",
        "canonicalization_manifest_digest",
        "expected_commit_id",
        "completed_verification_policy",
        "unknown_type_policy",
    }


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("media_type", ""),
        ("raw_sha256", "not-a-sha"),
        ("size_bytes", -1),
    ],
)
def test_bounded_and_integrity_fields_reject_invalid_values(
    field: str, value: object
) -> None:
    values = artifact_ref().model_dump()
    values[field] = value
    with pytest.raises(ValidationError):
        RepositoryArtifactRef(**values)


def test_import_request_rejects_invalid_expected_commit_id() -> None:
    with pytest.raises(ValidationError):
        SubmitVersionedImportRequest.model_validate(
            import_request_payload(expected_commit_id="")
        )


def test_import_request_rejects_body_idempotency_key() -> None:
    with pytest.raises(ValidationError):
        SubmitVersionedImportRequest.model_validate(
            import_request_payload(idempotency_key="import-1")
        )


@pytest.mark.parametrize(
    ("status", "result", "error"),
    [
        (OperationStatus.QUEUED, None, None),
        (OperationStatus.RUNNING, None, None),
        (
            OperationStatus.SUCCEEDED,
            import_result_payload(),
            None,
        ),
        (
            OperationStatus.FAILED,
            None,
            {
                "code": "IMPORT_REJECTED",
                "message": "manifest rejected",
            },
        ),
    ],
)
def test_versioned_operation_accepts_valid_status_result_error_combinations(
    status: OperationStatus,
    result: dict[str, object] | None,
    error: dict[str, object] | None,
) -> None:
    operation = VersionedOperation.model_validate(
        {
            "operation_id": str(OPERATION_ID),
            "status": status.value,
            "result": result,
            "error": error,
        }
    )

    assert operation.status == status
    assert operation.result is None if result is None else operation.result is not None
    assert operation.error is None if error is None else operation.error is not None


@pytest.mark.parametrize(
    ("status", "result", "error"),
    [
        (OperationStatus.QUEUED, import_result_payload(), None),
        (OperationStatus.RUNNING, None, {"code": "IMPORT_REJECTED", "message": "x"}),
        (OperationStatus.SUCCEEDED, None, None),
        (
            OperationStatus.SUCCEEDED,
            import_result_payload(),
            {"code": "IMPORT_REJECTED", "message": "x"},
        ),
        (OperationStatus.FAILED, import_result_payload(), None),
        (
            OperationStatus.FAILED,
            None,
            None,
        ),
    ],
)
def test_versioned_operation_rejects_invalid_status_result_error_combinations(
    status: OperationStatus,
    result: dict[str, object] | None,
    error: dict[str, object] | None,
) -> None:
    with pytest.raises(ValidationError):
        VersionedOperation.model_validate(
            {
                "operation_id": str(OPERATION_ID),
                "status": status.value,
                "result": result,
                "error": error,
            }
        )
