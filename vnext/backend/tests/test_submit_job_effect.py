"""Repository upload/import wire-mapping integration tests for submit_import."""

from __future__ import annotations

import json
from pathlib import Path
from uuid import UUID

import pytest
from gateway_repository_contracts import (
    REPOSITORY_IMPORT_MEDIA_TYPE,
    UnknownTypePolicy,
    VerificationPolicy,
)
from gateway_backend.domain.submission.models import RepositoryArtifactRef
from gateway_backend.infrastructure.repository_write.http import HttpRepositoryWriteClient
from tests.support.submit_job_harness import (
    RecordingTransport,
    dolt_available,
    repository_service_session,
)

pytestmark = pytest.mark.integration

REPOSITORY_ID = "018f0f3e-7b0a-7c15-8a9e-2e4b9f4d2c11"
ARTIFACT_ID = "018f0f3e-7b0a-7c16-8a9e-2e4b9f4d2c11"
UPLOAD_KEY = "upload-idem-submit-effect"
IMPORT_KEY = "import-idem-submit-effect"
PACKAGE_BYTES = b"submit-package-bytes"
PACKAGE_SHA256 = "b" * 64
EXPECTED_COMMIT_ID = "commit-c0"


def _import_request_body(repository_artifact_ref: RepositoryArtifactRef) -> dict[str, object]:
    return {
        "repository_id": REPOSITORY_ID,
        "artifact_ref": {
            "artifact_id": repository_artifact_ref.artifact_id,
            "media_type": REPOSITORY_IMPORT_MEDIA_TYPE,
            "size_bytes": repository_artifact_ref.size_bytes,
            "raw_sha256": repository_artifact_ref.raw_sha256,
        },
        "target_ref": "main",
        "expected_commit_id": EXPECTED_COMMIT_ID,
        "verification_policy": VerificationPolicy.STRUCTURAL.value,
        "unknown_type_policy": UnknownTypePolicy.REJECT.value,
    }


def test_submit_upload_and_import_wire_mapping_uses_recording_transport() -> None:
    transport = RecordingTransport()
    client = HttpRepositoryWriteClient(
        base_url="http://repository.test",
        bearer_token="test-bearer-token",
        transport=transport,
    )
    repository_artifact_ref = client.upload_artifact(
        repository_id=REPOSITORY_ID,
        idempotency_key=UPLOAD_KEY,
        media_type=REPOSITORY_IMPORT_MEDIA_TYPE,
        raw_sha256=PACKAGE_SHA256,
        body=PACKAGE_BYTES,
    )
    operation_id = client.submit_versioned_import(
        repository_id=REPOSITORY_ID,
        idempotency_key=IMPORT_KEY,
        artifact_ref=repository_artifact_ref,
        expected_commit_id=EXPECTED_COMMIT_ID,
    )

    assert len(transport.requests) == 2
    upload = transport.requests[0]
    import_request = transport.requests[1]

    assert upload.method == "POST"
    assert upload.url == f"http://repository.test/v1/repositories/{REPOSITORY_ID}/artifacts"
    assert upload.headers["authorization"] == "Bearer test-bearer-token"
    assert upload.headers["idempotency-key"] == UPLOAD_KEY
    assert upload.headers["content-type"] == REPOSITORY_IMPORT_MEDIA_TYPE
    assert upload.headers["content-length"] == str(len(PACKAGE_BYTES))
    assert upload.headers["x-artifact-sha256"] == PACKAGE_SHA256
    assert upload.body == PACKAGE_BYTES

    assert import_request.method == "POST"
    assert (
        import_request.url
        == f"http://repository.test/v1/repositories/{REPOSITORY_ID}/versioned/imports"
    )
    assert import_request.headers["authorization"] == "Bearer test-bearer-token"
    assert import_request.headers["idempotency-key"] == IMPORT_KEY
    assert import_request.headers["content-type"] == "application/json"
    assert json.loads(import_request.body) == _import_request_body(repository_artifact_ref)
    assert set(json.loads(import_request.body)) == {
        "repository_id",
        "artifact_ref",
        "target_ref",
        "expected_commit_id",
        "verification_policy",
        "unknown_type_policy",
    }
    assert operation_id == "018f0f3e-7b0a-7c17-8a9e-2e4b9f4d2c11"


@pytest.mark.skipif(not dolt_available(), reason="dolt is not available")
def test_submit_upload_and_import_wire_mapping_against_live_repository(tmp_path: Path) -> None:
    with repository_service_session(tmp_path) as service:
        seeded = service.repository_id_factory(idempotency_key="create-submit-effect-live")
        transport = RecordingTransport()
        client = service.write_client(transport=transport)
        repository_artifact_ref = client.upload_artifact(
            repository_id=seeded.repository_id,
            idempotency_key=UPLOAD_KEY,
            media_type=REPOSITORY_IMPORT_MEDIA_TYPE,
            raw_sha256=PACKAGE_SHA256,
            body=PACKAGE_BYTES,
        )
        operation_id = client.submit_versioned_import(
            repository_id=seeded.repository_id,
            idempotency_key=IMPORT_KEY,
            artifact_ref=repository_artifact_ref,
            expected_commit_id=seeded.initial_commit_id,
        )

    upload = transport.requests[0]
    import_request = transport.requests[1]
    assert upload.url.endswith(f"/v1/repositories/{seeded.repository_id}/artifacts")
    assert upload.headers["idempotency-key"] == UPLOAD_KEY
    assert import_request.url.endswith(f"/v1/repositories/{seeded.repository_id}/versioned/imports")
    assert import_request.headers["idempotency-key"] == IMPORT_KEY
    body = json.loads(import_request.body)
    assert body["repository_id"] == seeded.repository_id
    assert body["expected_commit_id"] == seeded.initial_commit_id
    assert body["target_ref"] == "main"
    assert body["verification_policy"] == VerificationPolicy.STRUCTURAL.value
    assert body["unknown_type_policy"] == UnknownTypePolicy.REJECT.value
    assert set(body) == {
        "repository_id",
        "artifact_ref",
        "target_ref",
        "expected_commit_id",
        "verification_policy",
        "unknown_type_policy",
    }
    UUID(operation_id)
