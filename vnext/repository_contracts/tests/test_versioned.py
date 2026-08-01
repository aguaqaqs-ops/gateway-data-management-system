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
    VersionedImportResult,
)

REPOSITORY_ID = UUID("018f0f3e-7b0a-7c15-8a9e-2e4b9f4d2c11")
ARTIFACT_ID = UUID("018f0f3e-7b0a-7c16-8a9e-2e4b9f4d2c11")
SHA256 = "a" * 64


def artifact_ref() -> RepositoryArtifactRef:
    return RepositoryArtifactRef(
        artifact_id=ARTIFACT_ID,
        media_type="application/vnd.gateway.repository-import.v1+tar+zstd",
        size_bytes=12,
        raw_sha256=SHA256,
    )


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


def test_import_request_keeps_repository_and_artifact_scopes_distinct() -> None:
    request = SubmitVersionedImportRequest(
        repository_id=REPOSITORY_ID,
        artifact_ref=artifact_ref(),
        target_ref="main",
        expected_commit_id="commit-0",
        idempotency_key="import-1",
    )

    assert request.repository_id == REPOSITORY_ID
    assert request.artifact_ref.artifact_id == ARTIFACT_ID


def test_import_result_echoes_opaque_manifest_binding() -> None:
    result = VersionedImportResult(
        commit_id="commit-1",
        target_ref="main",
        artifact_id=ARTIFACT_ID,
        canonicalization_manifest_digest="manifest-digest-1",
    )

    assert result.canonicalization_manifest_digest == "manifest-digest-1"


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("media_type", ""),
        ("raw_sha256", "not-a-sha"),
        ("size_bytes", -1),
        ("idempotency_key", ""),
    ],
)
def test_bounded_and_integrity_fields_reject_invalid_values(
    field: str, value: object
) -> None:
    values = artifact_ref().model_dump()
    values[field] = value
    with pytest.raises(ValidationError):
        RepositoryArtifactRef(**values)
