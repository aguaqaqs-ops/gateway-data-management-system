"""HTTP tests for GET /v1/repositories/{repository_id}/operations/{operation_id}."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

import pytest

from gateway_repository_contracts import (
    OperationStatus,
    RepositoryArtifactRef,
    SimpleError,
    UnknownTypePolicy,
    VerificationPolicy,
    VersionedImportResult,
)
from gateway_repository_service.mutation_store import IdempotencyKeyHash
from gateway_repository_service.versioned_import import ImportRequestBinding, versioned_import_fingerprint_v1
from support.http_harness import (
    PRODUCTION_OPENAPI_PATHS,
    ImportHttpTestEnvironment,
    assert_request_id_header,
    create_import_http_environment,
)


@pytest.fixture
def env(tmp_path: Path) -> Iterator[ImportHttpTestEnvironment]:
    environment = create_import_http_environment(tmp_path)
    yield environment
    environment.close()


def _get(
    env: ImportHttpTestEnvironment,
    repository_id: UUID,
    operation_id: UUID,
    *,
    token: str = "test-bearer-token",
) -> Any:
    return env.client.get(
        f"/v1/repositories/{repository_id}/operations/{operation_id}",
        headers={"Authorization": f"Bearer {token}"},
    )


def _enqueue_operation(env: ImportHttpTestEnvironment, repository_id: UUID, *, key: str = "poll-key") -> tuple[UUID, UUID]:
    artifact_id, size_bytes, raw_sha256 = env.seed_artifact(repository_id)
    binding = ImportRequestBinding(
        repository_id=repository_id,
        artifact_ref=RepositoryArtifactRef(
            artifact_id=artifact_id,
            media_type="application/vnd.gateway.repository-import.v1+tar+zstd",
            size_bytes=size_bytes,
            raw_sha256=raw_sha256,
        ),
        target_ref="main",
        expected_commit_id="commit-0",
        verification_policy=VerificationPolicy.STRUCTURAL,
        unknown_type_policy=UnknownTypePolicy.REJECT,
    )
    key_hash = IdempotencyKeyHash.from_raw_key(key)
    fingerprint = versioned_import_fingerprint_v1(binding=binding, key_hash=key_hash)
    result = env.runtime.import_store.admit_new_import(
        binding,
        key_hash=key_hash,
        fingerprint=fingerprint,
        max_queued_imports=64,
        layout=env.layout,
    )
    return result.operation_id, artifact_id


def test_get_operation_requires_auth(env: ImportHttpTestEnvironment) -> None:
    repository_id = env.seed_repository()
    operation_id = _enqueue_operation(env, repository_id)[0]
    response = _get(env, repository_id, operation_id, token="wrong")
    assert response.status_code == 401


def test_get_operation_returns_wrapped_operation(env: ImportHttpTestEnvironment) -> None:
    repository_id = env.seed_repository()
    operation_id = _enqueue_operation(env, repository_id)[0]
    response = _get(env, repository_id, operation_id)
    assert response.status_code == 200
    payload = response.json()
    assert set(payload.keys()) == {"operation"}
    assert payload["operation"]["operation_id"] == str(operation_id)
    assert payload["operation"]["status"] == OperationStatus.QUEUED.value
    assert payload["operation"]["result"] is None
    assert payload["operation"]["error"] is None
    assert_request_id_header(response)


def test_get_operation_terminal_failed_is_200_with_error(env: ImportHttpTestEnvironment) -> None:
    repository_id = env.seed_repository()
    operation_id = _enqueue_operation(env, repository_id)[0]
    env.runtime.import_store.claim_if_queued(operation_id)
    env.runtime.import_store.mark_failed(
        operation_id,
        error=SimpleError(code="IMPORT_REJECTED", message="rejected"),
    )
    response = _get(env, repository_id, operation_id)
    assert response.status_code == 200
    operation = response.json()["operation"]
    assert operation["status"] == OperationStatus.FAILED.value
    assert operation["error"]["code"] == "IMPORT_REJECTED"
    assert operation["error"]["request_id"] is None


def test_get_operation_succeeded_shape(env: ImportHttpTestEnvironment) -> None:
    repository_id = env.seed_repository()
    operation_id, artifact_id = _enqueue_operation(env, repository_id)
    env.runtime.import_store.claim_if_queued(operation_id)
    env.runtime.import_store.mark_succeeded(
        operation_id,
        result=VersionedImportResult(
            commit_id="commit-1",
            target_ref="main",
            artifact_id=artifact_id,
            canonicalization_manifest_digest="digest",
            expected_commit_id="commit-0",
            completed_verification_policy=VerificationPolicy.STRUCTURAL,
            unknown_type_policy=UnknownTypePolicy.REJECT,
        ),
    )
    response = _get(env, repository_id, operation_id)
    assert response.status_code == 200
    operation = response.json()["operation"]
    assert operation["status"] == OperationStatus.SUCCEEDED.value
    assert operation["result"] is not None
    assert operation["error"] is None


def test_get_operation_wrong_repository_is_not_found(env: ImportHttpTestEnvironment) -> None:
    repository_id = env.seed_repository()
    other_repository_id = env.seed_repository()
    operation_id = _enqueue_operation(env, repository_id)[0]
    response = _get(env, other_repository_id, operation_id)
    assert response.status_code == 404
    assert response.json()["code"] == "OPERATION_NOT_FOUND"


def test_get_operation_missing_is_not_found(env: ImportHttpTestEnvironment) -> None:
    repository_id = env.seed_repository()
    response = _get(env, repository_id, uuid4())
    assert response.status_code == 404
    assert response.json()["code"] == "OPERATION_NOT_FOUND"


def test_get_operation_malformed_durable_row_returns_internal_error(env: ImportHttpTestEnvironment) -> None:
    repository_id = env.seed_repository()
    operation_id, artifact_id = _enqueue_operation(env, repository_id)
    env.runtime.import_store.claim_if_queued(operation_id)
    env.runtime.import_store.mark_succeeded(
        operation_id,
        result=VersionedImportResult(
            commit_id="commit-1",
            target_ref="main",
            artifact_id=artifact_id,
            canonicalization_manifest_digest="digest",
            expected_commit_id="commit-0",
            completed_verification_policy=VerificationPolicy.STRUCTURAL,
            unknown_type_policy=UnknownTypePolicy.REJECT,
        ),
    )
    env.control_store.connection.execute(
        "UPDATE repository_import_operations SET result_json = ? WHERE operation_id = ?",
        ('{"commit_id": 123}', str(operation_id)),
    )
    env.control_store.connection.commit()
    response = _get(env, repository_id, operation_id)
    assert response.status_code == 500
    assert response.json()["code"] == "INTERNAL_ERROR"
    assert "sqlite" not in response.text.lower()
    assert "result_json" not in response.text.lower()


def test_get_operation_readable_during_shutdown(env: ImportHttpTestEnvironment) -> None:
    repository_id = env.seed_repository()
    operation_id = _enqueue_operation(env, repository_id)[0]
    env.runtime._stopping.set()
    response = _get(env, repository_id, operation_id)
    assert response.status_code == 200


def test_production_openapi_operation_paths(env: ImportHttpTestEnvironment) -> None:
    paths = env.client.get("/openapi.json").json()["paths"]
    assert set(paths.keys()) == PRODUCTION_OPENAPI_PATHS
    operation_path = paths["/v1/repositories/{repository_id}/operations/{operation_id}"]["get"]
    for status in ("200", "401", "404", "422", "503"):
        assert status in operation_path["responses"]
