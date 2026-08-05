"""Tests for create/upload HTTP header boundaries."""

from __future__ import annotations

import importlib
import inspect

import pytest
from pydantic import ValidationError

from gateway_repository_contracts import (
    REPOSITORY_IMPORT_MEDIA_TYPE,
    UploadRequestHeaders,
    validate_upload_content_length,
)
from gateway_repository_contracts.versioned import CreateRepositoryResponse, UploadArtifactResponse

SHA256 = "a" * 64
THREE_HUNDRED_MIB = 300 * 1024 * 1024
FIVE_HUNDRED_TWELVE_MIB = 512 * 1024 * 1024


def test_create_repository_has_no_json_request_model() -> None:
    import gateway_repository_contracts.versioned as versioned

    assert not hasattr(versioned, "CreateRepositoryRequest")


def test_upload_artifact_has_no_json_request_model() -> None:
    import gateway_repository_contracts.versioned as versioned

    assert not hasattr(versioned, "UploadArtifactRequest")


def test_repository_import_media_type_is_fixed_tar_zstd() -> None:
    assert REPOSITORY_IMPORT_MEDIA_TYPE == "application/vnd.gateway.repository-import.v1+tar+zstd"


def test_upload_request_headers_accept_large_content_length_shape_only() -> None:
    headers = UploadRequestHeaders(
        content_type=REPOSITORY_IMPORT_MEDIA_TYPE,
        content_length=THREE_HUNDRED_MIB,
        idempotency_key="x" * 255,
        artifact_sha256=SHA256,
    )

    assert headers.content_length == THREE_HUNDRED_MIB


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("content_type", "application/gzip"),
        ("content_type", "application/vnd.gateway.repository-import.v1+tar+gz"),
        ("content_length", -1),
        ("idempotency_key", ""),
        ("idempotency_key", "x" * 256),
        ("artifact_sha256", "not-a-sha"),
        ("artifact_sha256", "A" * 64),
    ],
)
def test_upload_request_headers_reject_invalid_values(field: str, value: object) -> None:
    payload = {
        "content_type": REPOSITORY_IMPORT_MEDIA_TYPE,
        "content_length": 12,
        "idempotency_key": "upload-1",
        "artifact_sha256": SHA256,
    }
    payload[field] = value
    with pytest.raises(ValidationError):
        UploadRequestHeaders.model_validate(payload)


def test_validate_upload_content_length_uses_deployment_bound() -> None:
    assert validate_upload_content_length(100, max_upload_bytes=256) == 100
    assert validate_upload_content_length(THREE_HUNDRED_MIB, max_upload_bytes=FIVE_HUNDRED_TWELVE_MIB) == THREE_HUNDRED_MIB
    with pytest.raises(ValueError, match="configured upload limit"):
        validate_upload_content_length(THREE_HUNDRED_MIB, max_upload_bytes=256 * 1024 * 1024)


def test_create_and_upload_responses_keep_closed_shapes() -> None:
    create = CreateRepositoryResponse.model_validate(
        {
            "repository_id": "018f0f3e-7b0a-7c15-8a9e-2e4b9f4d2c11",
            "default_ref": "main",
            "initial_commit_id": "commit-1",
        }
    )
    upload = UploadArtifactResponse.model_validate(
        {
            "artifact_ref": {
                "artifact_id": "018f0f3e-7b0a-7c16-8a9e-2e4b9f4d2c11",
                "media_type": REPOSITORY_IMPORT_MEDIA_TYPE,
                "size_bytes": 12,
                "raw_sha256": SHA256,
            }
        }
    )

    assert set(create.model_dump()) == {"repository_id", "default_ref", "initial_commit_id"}
    assert set(upload.model_dump()) == {"artifact_ref"}


def test_public_exports_do_not_include_removed_request_models() -> None:
    import gateway_repository_contracts as contracts

    exported = set(contracts.__all__)
    assert "CreateRepositoryRequest" not in exported
    assert "UploadArtifactRequest" not in exported
    assert "UploadRequestHeaders" in exported
    assert "DEFAULT_MAX_UPLOAD_BYTES" not in exported


def test_versioned_module_has_no_create_or_upload_request_models() -> None:
    versioned = importlib.import_module("gateway_repository_contracts.versioned")
    class_names = {name for name, _ in inspect.getmembers(versioned, inspect.isclass)}
    assert "CreateRepositoryRequest" not in class_names
    assert "UploadArtifactRequest" not in class_names
