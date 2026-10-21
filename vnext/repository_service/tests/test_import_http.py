"""HTTP tests for POST /v1/repositories/{repository_id}/versioned/imports."""

from __future__ import annotations

import json
import logging
import sqlite3
import threading
from collections.abc import Iterator
from pathlib import Path
from typing import Any
from unittest.mock import patch
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient

from gateway_repository_contracts import (
    OperationStatus,
    RepositoryArtifactRef,
    SimpleError,
    UnknownTypePolicy,
    VerificationPolicy,
    VersionedImportResult,
)
from gateway_repository_service import artifact_cleanup
from gateway_repository_service.app import create_app
from gateway_repository_service.mutation_store import IdempotencyKeyHash
from gateway_repository_service.upload_artifact.admission_pin import ArtifactAdmissionPin
from gateway_repository_service.upload_artifact.visibility import artifact_ready_path
from gateway_repository_service.versioned_import import ImportRequestBinding, versioned_import_fingerprint_v1
from support.control_db_harness import control_db_transaction
from support.http_harness import (
    PRODUCTION_OPENAPI_PATHS,
    ImportHttpTestEnvironment,
    assert_request_id_header,
    create_import_http_environment,
    import_headers,
    import_request_body,
)
from support.lifecycle_harness import lifecycle_settings
from support.upload_harness import create_repository, upload_headers

INVALID_HEADER_CASES = [
    ("", 422),
    ("x" * 256, 422),
]

REPLAY_TERMINAL_STATUS_CASES = [
    OperationStatus.QUEUED,
    OperationStatus.RUNNING,
    OperationStatus.SUCCEEDED,
    OperationStatus.FAILED,
]


@pytest.fixture
def env(tmp_path: Path) -> Iterator[ImportHttpTestEnvironment]:
    environment = create_import_http_environment(tmp_path)
    yield environment
    environment.close()


def _submit(
    env: ImportHttpTestEnvironment,
    repository_id: UUID,
    artifact_id: UUID,
    size_bytes: int,
    raw_sha256: str,
    *,
    idempotency_key: str = "import-key-1",
    headers: dict[str, str] | None = None,
    body_overrides: dict[str, object] | None = None,
) -> Any:
    body = import_request_body(
        repository_id=repository_id,
        artifact_id=artifact_id,
        size_bytes=size_bytes,
        raw_sha256=raw_sha256,
    )
    if body_overrides:
        body.update(body_overrides)
    request_headers = headers or import_headers(idempotency_key=idempotency_key)
    return env.client.post(
        f"/v1/repositories/{repository_id}/versioned/imports",
        headers=request_headers,
        content=json.dumps(body),
    )


def _seed_operation_for_replay(
    env: ImportHttpTestEnvironment,
    repository_id: UUID,
    *,
    idempotency_key: str,
    terminal_status: OperationStatus,
) -> tuple[UUID, UUID, int, str]:
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
    key_hash = IdempotencyKeyHash.from_raw_key(idempotency_key)
    fingerprint = versioned_import_fingerprint_v1(binding=binding, key_hash=key_hash)
    result = env.runtime.import_store.admit_new_import(
        binding,
        key_hash=key_hash,
        fingerprint=fingerprint,
        max_queued_imports=64,
    )
    operation_id = result.operation_id
    if terminal_status == OperationStatus.QUEUED:
        env.runtime.import_store.publish_queued_import(operation_id)
        return operation_id, artifact_id, size_bytes, raw_sha256
    env.runtime.import_store.publish_queued_import(operation_id)
    env.runtime.import_store.claim_if_queued(operation_id)
    if terminal_status == OperationStatus.RUNNING:
        return operation_id, artifact_id, size_bytes, raw_sha256
    if terminal_status == OperationStatus.SUCCEEDED:
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
        return operation_id, artifact_id, size_bytes, raw_sha256
    env.runtime.import_store.mark_failed(
        operation_id,
        error=SimpleError(code="IMPORT_REJECTED", message="rejected"),
    )
    return operation_id, artifact_id, size_bytes, raw_sha256


def _inject_malformed_result_json(env: ImportHttpTestEnvironment, operation_id: UUID) -> None:
    with control_db_transaction(env.control_store) as connection:
        connection.execute(
            "UPDATE repository_import_operations SET result_json = ? WHERE operation_id = ?",
            ('{"commit_id": 123}', str(operation_id)),
        )


def test_submit_requires_auth(env: ImportHttpTestEnvironment) -> None:
    repository_id = env.seed_repository()
    artifact_id, size_bytes, raw_sha256 = env.seed_artifact(repository_id)
    response = env.client.post(
        f"/v1/repositories/{repository_id}/versioned/imports",
        headers=import_headers(idempotency_key="import-key-1", token="wrong-token"),
        content=json.dumps(
            import_request_body(
                repository_id=repository_id,
                artifact_id=artifact_id,
                size_bytes=size_bytes,
                raw_sha256=raw_sha256,
            )
        ),
    )
    assert response.status_code == 401
    assert response.json()["code"] == "UNAUTHENTICATED"


def test_submit_rejects_caller_request_id_override(env: ImportHttpTestEnvironment) -> None:
    repository_id = env.seed_repository()
    artifact_id, size_bytes, raw_sha256 = env.seed_artifact(repository_id)
    response = _submit(
        env,
        repository_id,
        artifact_id,
        size_bytes,
        raw_sha256,
        headers=import_headers(idempotency_key="import-key-1", request_id="caller-id"),
    )
    assert response.status_code == 202
    assert response.headers["X-Request-ID"] != "caller-id"
    assert_request_id_header(response)


@pytest.mark.parametrize("idempotency_key,expected_status", INVALID_HEADER_CASES)
def test_submit_rejects_invalid_idempotency_header(
    env: ImportHttpTestEnvironment,
    idempotency_key: str,
    expected_status: int,
) -> None:
    repository_id = env.seed_repository()
    artifact_id, size_bytes, raw_sha256 = env.seed_artifact(repository_id)
    response = _submit(
        env,
        repository_id,
        artifact_id,
        size_bytes,
        raw_sha256,
        idempotency_key=idempotency_key,
    )
    assert response.status_code == expected_status
    assert response.json()["code"] == "REQUEST_VALIDATION_FAILED"


def test_submit_rejects_body_extra_field(env: ImportHttpTestEnvironment) -> None:
    repository_id = env.seed_repository()
    artifact_id, size_bytes, raw_sha256 = env.seed_artifact(repository_id)
    body = import_request_body(
        repository_id=repository_id,
        artifact_id=artifact_id,
        size_bytes=size_bytes,
        raw_sha256=raw_sha256,
    )
    body["idempotency_key"] = "body-key"
    response = env.client.post(
        f"/v1/repositories/{repository_id}/versioned/imports",
        headers=import_headers(),
        content=json.dumps(body),
    )
    assert response.status_code == 422


def test_submit_rejects_path_body_repository_mismatch(env: ImportHttpTestEnvironment) -> None:
    repository_id = env.seed_repository()
    other_repository_id = env.seed_repository()
    artifact_id, size_bytes, raw_sha256 = env.seed_artifact(repository_id)
    response = _submit(
        env,
        other_repository_id,
        artifact_id,
        size_bytes,
        raw_sha256,
        body_overrides={"repository_id": str(repository_id)},
    )
    assert response.status_code == 422
    assert response.json()["code"] == "REQUEST_VALIDATION_FAILED"


def test_submit_accepts_default_policies(env: ImportHttpTestEnvironment) -> None:
    repository_id = env.seed_repository()
    artifact_id, size_bytes, raw_sha256 = env.seed_artifact(repository_id)
    response = _submit(env, repository_id, artifact_id, size_bytes, raw_sha256)
    assert response.status_code == 202
    operation_id = UUID(response.json()["operation_id"])
    stored = env.runtime.import_store.get_operation(repository_id, operation_id)
    assert stored is not None
    assert stored.status == OperationStatus.QUEUED


def test_submit_inserts_queued_before_202(env: ImportHttpTestEnvironment) -> None:
    repository_id = env.seed_repository()
    artifact_id, size_bytes, raw_sha256 = env.seed_artifact(repository_id)
    response = _submit(env, repository_id, artifact_id, size_bytes, raw_sha256)
    assert response.status_code == 202
    operation_id = UUID(response.json()["operation_id"])
    stored = env.runtime.import_store.get_operation(repository_id, operation_id)
    assert stored is not None
    assert stored.status == OperationStatus.QUEUED
    assert env.runtime.import_store.count_global_queued() == 1
    assert len(env.notify_calls) >= 1
    assert env.notify_queued_visible == [True]


def test_submit_replays_same_operation_id(env: ImportHttpTestEnvironment) -> None:
    repository_id = env.seed_repository()
    artifact_id, size_bytes, raw_sha256 = env.seed_artifact(repository_id)
    first = _submit(env, repository_id, artifact_id, size_bytes, raw_sha256, idempotency_key="replay-key")
    second = _submit(env, repository_id, artifact_id, size_bytes, raw_sha256, idempotency_key="replay-key")
    assert first.status_code == 202
    assert second.status_code == 202
    assert first.json()["operation_id"] == second.json()["operation_id"]
    assert env.runtime.import_store.count_global_queued() == 1


def test_submit_rejects_different_fingerprint_with_same_key(env: ImportHttpTestEnvironment) -> None:
    repository_id = env.seed_repository()
    artifact_id, size_bytes, raw_sha256 = env.seed_artifact(repository_id)
    first = _submit(env, repository_id, artifact_id, size_bytes, raw_sha256, idempotency_key="conflict-key")
    assert first.status_code == 202
    second = _submit(
        env,
        repository_id,
        artifact_id,
        size_bytes,
        raw_sha256,
        idempotency_key="conflict-key",
        body_overrides={"expected_commit_id": "commit-9"},
    )
    assert second.status_code == 409
    assert second.json()["code"] == "IDEMPOTENCY_CONFLICT"


def test_submit_replay_survives_shutdown(env: ImportHttpTestEnvironment) -> None:
    repository_id = env.seed_repository()
    artifact_id, size_bytes, raw_sha256 = env.seed_artifact(repository_id)
    first = _submit(env, repository_id, artifact_id, size_bytes, raw_sha256, idempotency_key="shutdown-replay")
    assert first.status_code == 202
    env.runtime._stopping.set()
    second = _submit(env, repository_id, artifact_id, size_bytes, raw_sha256, idempotency_key="shutdown-replay")
    assert second.status_code == 202


def test_submit_new_key_rejected_when_shutting_down(env: ImportHttpTestEnvironment) -> None:
    repository_id = env.seed_repository()
    artifact_id, size_bytes, raw_sha256 = env.seed_artifact(repository_id)
    env.runtime._stopping.set()
    response = _submit(env, repository_id, artifact_id, size_bytes, raw_sha256, idempotency_key="new-shutdown")
    assert response.status_code == 503
    assert response.json()["code"] == "SERVICE_NOT_READY"


def test_submit_repository_not_found(env: ImportHttpTestEnvironment) -> None:
    repository_id = uuid4()
    artifact_id = uuid4()
    response = _submit(env, repository_id, artifact_id, 12, "a" * 64)
    assert response.status_code == 404
    assert response.json()["code"] == "REPOSITORY_NOT_FOUND"


def test_submit_artifact_not_found_when_missing(env: ImportHttpTestEnvironment) -> None:
    repository_id = env.seed_repository()
    response = _submit(env, repository_id, uuid4(), 12, "a" * 64)
    assert response.status_code == 404
    assert response.json()["code"] == "ARTIFACT_NOT_FOUND"


def test_submit_manual_barrier_rejects_new_key_only(env: ImportHttpTestEnvironment) -> None:
    from gateway_repository_contracts import RepositoryArtifactRef

    repository_id = env.seed_repository()
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
    key_hash = IdempotencyKeyHash.from_raw_key("manual-key")
    fingerprint = versioned_import_fingerprint_v1(binding=binding, key_hash=key_hash)
    admitted = env.runtime.import_store.admit_new_import(
        binding,
        key_hash=key_hash,
        fingerprint=fingerprint,
        max_queued_imports=64,
    )
    operation = env.runtime.import_store.lookup_by_key(repository_id, key_hash)
    assert operation is not None
    env.runtime.import_store.publish_queued_import(admitted.operation_id)
    env.runtime.import_store.claim_if_queued(operation.operation_id)
    env.runtime.import_store.mark_failed(
        operation.operation_id,
        error=SimpleError(code="MANUAL_RECOVERY_REQUIRED", message="manual"),
    )
    response = _submit(env, repository_id, artifact_id, size_bytes, raw_sha256, idempotency_key="new-manual")
    assert response.status_code == 409
    assert response.json()["code"] == "MANUAL_RECOVERY_REQUIRED"


def test_submit_queue_full_rejects_new_key(env: ImportHttpTestEnvironment, tmp_path: Path) -> None:
    limited = create_import_http_environment(tmp_path, max_queued_imports=1)
    try:
        repository_id = limited.seed_repository()
        artifact_id, size_bytes, raw_sha256 = limited.seed_artifact(repository_id)
        first = _submit(
            limited,
            repository_id,
            artifact_id,
            size_bytes,
            raw_sha256,
            idempotency_key="queued-1",
        )
        assert first.status_code == 202
        second = _submit(
            limited,
            repository_id,
            artifact_id,
            size_bytes,
            raw_sha256,
            idempotency_key="queued-2",
        )
        assert second.status_code == 429
        assert second.json()["code"] == "IMPORT_QUEUE_FULL"
    finally:
        limited.close()


def test_submit_disk_denied(env: ImportHttpTestEnvironment) -> None:
    repository_id = env.seed_repository()
    artifact_id, size_bytes, raw_sha256 = env.seed_artifact(repository_id)
    with patch(
        "gateway_repository_service.capacity.os.statvfs",
        side_effect=OSError("disk measurement failed"),
    ):
        response = _submit(env, repository_id, artifact_id, size_bytes, raw_sha256, idempotency_key="disk-deny")
    assert response.status_code == 503
    assert response.json()["code"] == "DISK_ADMISSION_DENIED"


def test_production_openapi_paths(env: ImportHttpTestEnvironment) -> None:
    paths = env.client.get("/openapi.json").json()["paths"]
    assert set(paths.keys()) == PRODUCTION_OPENAPI_PATHS
    import_path = paths["/v1/repositories/{repository_id}/versioned/imports"]["post"]
    assert "202" in import_path["responses"]
    for status in ("401", "404", "409", "422", "429", "503"):
        assert status in import_path["responses"]


def test_submit_logs_do_not_include_raw_key(
    env: ImportHttpTestEnvironment,
    caplog: pytest.LogCaptureFixture,
) -> None:
    repository_id = env.seed_repository()
    artifact_id, size_bytes, raw_sha256 = env.seed_artifact(repository_id)
    raw_key = "super-secret-import-key"
    with caplog.at_level(logging.INFO):
        response = _submit(
            env,
            repository_id,
            artifact_id,
            size_bytes,
            raw_sha256,
            idempotency_key=raw_key,
        )
    assert response.status_code == 202
    assert raw_key not in caplog.text
    assert "test-bearer-token" not in caplog.text
    stored = env.runtime.import_store.lookup_by_key(
        repository_id,
        IdempotencyKeyHash.from_raw_key(raw_key),
    )
    assert stored is not None
    assert stored.private_ref_name not in caplog.text
    assert stored.operation_marker not in caplog.text
    assert "SELECT" not in caplog.text.upper()
    assert str(env.layout.root) not in caplog.text


def test_submit_writable_probe_failure_returns_disk_denied(env: ImportHttpTestEnvironment) -> None:
    from gateway_repository_service.capacity import CapacityAdmissionError

    repository_id = env.seed_repository()
    artifact_id, size_bytes, raw_sha256 = env.seed_artifact(repository_id)
    with patch(
        "gateway_repository_service.versioned_import.submission.assert_durable_root_writable",
        side_effect=CapacityAdmissionError("writable probe failed"),
    ):
        response = _submit(
            env,
            repository_id,
            artifact_id,
            size_bytes,
            raw_sha256,
            idempotency_key="writable-deny",
        )
    assert response.status_code == 503
    assert response.json()["code"] == "DISK_ADMISSION_DENIED"


def test_submit_rejects_uint64_overflow_size_bytes(env: ImportHttpTestEnvironment) -> None:
    repository_id = env.seed_repository()
    artifact_id, size_bytes, raw_sha256 = env.seed_artifact(repository_id)
    response = _submit(
        env,
        repository_id,
        artifact_id,
        size_bytes,
        raw_sha256,
        body_overrides={"artifact_ref": {
            "artifact_id": str(artifact_id),
            "media_type": "application/vnd.gateway.repository-import.v1+tar+zstd",
            "size_bytes": 2**64,
            "raw_sha256": raw_sha256,
        }},
        idempotency_key="uint64-overflow",
    )
    assert response.status_code == 422
    assert response.json()["code"] == "REQUEST_VALIDATION_FAILED"


CONFLICT_GATE_PRIORITY_CASES = [
    "shutdown",
    "provider",
    "disk",
    "manual",
]


@pytest.mark.parametrize("gate", CONFLICT_GATE_PRIORITY_CASES)
def test_submit_conflict_precedes_admission_gates(
    env: ImportHttpTestEnvironment,
    gate: str,
) -> None:
    repository_id = env.seed_repository()
    artifact_id, size_bytes, raw_sha256 = env.seed_artifact(repository_id)
    idempotency_key = f"conflict-{gate}"
    first = _submit(env, repository_id, artifact_id, size_bytes, raw_sha256, idempotency_key=idempotency_key)
    assert first.status_code == 202
    if gate == "shutdown":
        env.runtime._stopping.set()
    elif gate == "provider":
        env.runtime.provider_gate.executable_path = lambda: Path("/does/not/exist/dolt")  # type: ignore[method-assign]
    elif gate == "manual":
        operation = env.runtime.import_store.lookup_by_key(
            repository_id,
            IdempotencyKeyHash.from_raw_key(idempotency_key),
        )
        assert operation is not None
        env.runtime.import_store.claim_if_queued(operation.operation_id)
        env.runtime.import_store.mark_failed(
            operation.operation_id,
            error=SimpleError(code="MANUAL_RECOVERY_REQUIRED", message="manual"),
        )

    if gate == "disk":
        with patch(
            "gateway_repository_service.capacity.os.statvfs",
            side_effect=OSError("disk measurement failed"),
        ):
            response = _submit(
                env,
                repository_id,
                artifact_id,
                size_bytes,
                raw_sha256,
                idempotency_key=idempotency_key,
                body_overrides={"expected_commit_id": "commit-9"},
            )
    else:
        response = _submit(
            env,
            repository_id,
            artifact_id,
            size_bytes,
            raw_sha256,
            idempotency_key=idempotency_key,
            body_overrides={"expected_commit_id": "commit-9"},
        )
    assert response.status_code == 409
    assert response.json()["code"] == "IDEMPOTENCY_CONFLICT"


def test_submit_conflict_precedes_queue_full(tmp_path: Path) -> None:
    limited = create_import_http_environment(tmp_path, max_queued_imports=1)
    try:
        repository_id = limited.seed_repository()
        artifact_id, size_bytes, raw_sha256 = limited.seed_artifact(repository_id)
        idempotency_key = "conflict-queue"
        first = _submit(
            limited,
            repository_id,
            artifact_id,
            size_bytes,
            raw_sha256,
            idempotency_key=idempotency_key,
        )
        assert first.status_code == 202
        second = _submit(
            limited,
            repository_id,
            artifact_id,
            size_bytes,
            raw_sha256,
            idempotency_key="queue-fill",
        )
        assert second.status_code == 429
        conflict = _submit(
            limited,
            repository_id,
            artifact_id,
            size_bytes,
            raw_sha256,
            idempotency_key=idempotency_key,
            body_overrides={"expected_commit_id": "commit-9"},
        )
        assert conflict.status_code == 409
        assert conflict.json()["code"] == "IDEMPOTENCY_CONFLICT"
    finally:
        limited.close()


ARTIFACT_NOT_FOUND_CASES = [
    ("missing", {}),
    ("cross_scope", {"repository_id_override": True}),
    ("media_mismatch", {"lifecycle_media_type": "application/vnd.gateway.repository-import.v1+tar+gz"}),
    ("size_mismatch", {"size_bytes_delta": 1}),
    ("sha_mismatch", {"raw_sha256": "b" * 64}),
    ("consumed", {"consume": True}),
    ("deleted", {"delete_bytes": True}),
]


@pytest.mark.parametrize("case_name,case_options", ARTIFACT_NOT_FOUND_CASES)
def test_submit_artifact_not_found_variants(
    env: ImportHttpTestEnvironment,
    case_name: str,
    case_options: dict[str, object],
) -> None:
    repository_id = env.seed_repository()
    other_repository_id = env.seed_repository()
    artifact_id, size_bytes, raw_sha256 = env.seed_artifact(repository_id)
    target_repository_id = other_repository_id if case_options.get("repository_id_override") else repository_id
    if case_name == "missing":
        target_artifact_id = uuid4()
        submit_size = 12
        submit_sha = "a" * 64
    else:
        target_artifact_id = artifact_id
        size_delta = case_options.get("size_bytes_delta", 0)
        submit_size = size_bytes + (int(size_delta) if isinstance(size_delta, int) else 0)
        submit_sha = str(case_options.get("raw_sha256", raw_sha256))
        if case_options.get("lifecycle_media_type"):
            with env.runtime.mutation_store._lock:
                env.runtime.mutation_store._connection.execute(
                    "UPDATE artifact_lifecycle SET media_type = ? WHERE artifact_id = ?",
                    (case_options["lifecycle_media_type"], str(artifact_id)),
                )
                env.runtime.mutation_store._connection.commit()
        if case_options.get("consume"):
            operation_id = env.runtime.import_store.admit_new_import(
                ImportRequestBinding(
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
                ),
                key_hash=IdempotencyKeyHash.from_raw_key(f"consume-{case_name}"),
                fingerprint=versioned_import_fingerprint_v1(
                    binding=ImportRequestBinding(
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
                    ),
                    key_hash=IdempotencyKeyHash.from_raw_key(f"consume-{case_name}"),
                ),
                max_queued_imports=64,
            ).operation_id
            env.runtime.import_store.publish_queued_import(operation_id)
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
        if case_options.get("delete_bytes"):
            ready_path = artifact_ready_path(env.layout, repository_id, artifact_id)
            ready_path.unlink(missing_ok=True)
            now = "2026-08-06T00:00:00+00:00"
            with env.runtime.mutation_store._lock:
                env.runtime.mutation_store._connection.execute(
                    "UPDATE artifact_lifecycle SET bytes_deleted_at = ? WHERE artifact_id = ?",
                    (now, str(artifact_id)),
                )
                env.runtime.mutation_store._connection.commit()
    body_overrides: dict[str, object] = {
        "artifact_ref": {
            "artifact_id": str(target_artifact_id),
            "media_type": "application/vnd.gateway.repository-import.v1+tar+zstd",
            "size_bytes": submit_size,
            "raw_sha256": submit_sha,
        }
    }
    response = _submit(
        env,
        target_repository_id,
        target_artifact_id,
        submit_size,
        submit_sha,
        idempotency_key=f"artifact-{case_name}",
        body_overrides=body_overrides,
    )
    assert response.status_code == 404
    assert response.json()["code"] == "ARTIFACT_NOT_FOUND"


def test_artifact_visibility_check_does_not_block_operation_poll(env: ImportHttpTestEnvironment) -> None:
    repository_id = env.seed_repository()
    operation_id, artifact_id, size_bytes, raw_sha256 = _seed_operation_for_replay(
        env,
        repository_id,
        idempotency_key="poll-during-fs",
        terminal_status=OperationStatus.SUCCEEDED,
    )
    calls = {"count": 0}

    def slow_visibility(*args: object, **kwargs: object) -> bool:
        del args, kwargs
        calls["count"] += 1
        if calls["count"] == 1:
            response = env.client.get(
                f"/v1/repositories/{repository_id}/operations/{operation_id}",
                headers={"Authorization": "Bearer test-bearer-token"},
            )
            assert response.status_code == 200
        return calls["count"] < 3

    with patch(
        "gateway_repository_service.versioned_import.submission.is_artifact_visible",
        side_effect=slow_visibility,
    ):
        response = _submit(
            env,
            repository_id,
            artifact_id,
            size_bytes,
            raw_sha256,
            idempotency_key="new-fs-blocked",
        )
    assert response.status_code == 404
    assert response.json()["code"] == "ARTIFACT_NOT_FOUND"


@pytest.mark.parametrize("terminal_status", REPLAY_TERMINAL_STATUS_CASES)
def test_submit_replays_same_key_for_all_terminal_states(
    env: ImportHttpTestEnvironment,
    terminal_status: OperationStatus,
) -> None:
    repository_id = env.seed_repository()
    idempotency_key = f"replay-{terminal_status.value.lower()}"
    operation_id, artifact_id, size_bytes, raw_sha256 = _seed_operation_for_replay(
        env,
        repository_id,
        idempotency_key=idempotency_key,
        terminal_status=terminal_status,
    )
    response = _submit(
        env,
        repository_id,
        artifact_id,
        size_bytes,
        raw_sha256,
        idempotency_key=idempotency_key,
    )
    assert response.status_code == 202
    assert response.json()["operation_id"] == str(operation_id)


def test_submit_replay_precedes_provider_unavailable(env: ImportHttpTestEnvironment) -> None:
    repository_id = env.seed_repository()
    idempotency_key = "replay-provider-down"
    operation_id, artifact_id, size_bytes, raw_sha256 = _seed_operation_for_replay(
        env,
        repository_id,
        idempotency_key=idempotency_key,
        terminal_status=OperationStatus.SUCCEEDED,
    )
    env.runtime.provider_gate.executable_path = lambda: Path("/does/not/exist/dolt")  # type: ignore[method-assign]
    response = _submit(
        env,
        repository_id,
        artifact_id,
        size_bytes,
        raw_sha256,
        idempotency_key=idempotency_key,
    )
    assert response.status_code == 202
    assert response.json()["operation_id"] == str(operation_id)


def test_submit_replay_precedes_disk_denied(env: ImportHttpTestEnvironment) -> None:
    repository_id = env.seed_repository()
    idempotency_key = "replay-disk-deny"
    operation_id, artifact_id, size_bytes, raw_sha256 = _seed_operation_for_replay(
        env,
        repository_id,
        idempotency_key=idempotency_key,
        terminal_status=OperationStatus.SUCCEEDED,
    )
    with patch(
        "gateway_repository_service.capacity.os.statvfs",
        side_effect=OSError("disk measurement failed"),
    ):
        replay = _submit(
            env,
            repository_id,
            artifact_id,
            size_bytes,
            raw_sha256,
            idempotency_key=idempotency_key,
        )
        fresh_artifact_id, fresh_size, fresh_sha = env.seed_artifact(repository_id)
        new_key = _submit(
            env,
            repository_id,
            fresh_artifact_id,
            fresh_size,
            fresh_sha,
            idempotency_key="new-disk-deny",
        )
    assert replay.status_code == 202
    assert replay.json()["operation_id"] == str(operation_id)
    assert new_key.status_code == 503
    assert new_key.json()["code"] == "DISK_ADMISSION_DENIED"


def test_submit_response_loss_replays_same_operation_id(env: ImportHttpTestEnvironment) -> None:
    repository_id = env.seed_repository()
    artifact_id, size_bytes, raw_sha256 = env.seed_artifact(repository_id)
    # Simulate client discarding the 202 response while retaining the idempotency key.
    first = _submit(env, repository_id, artifact_id, size_bytes, raw_sha256, idempotency_key="response-loss")
    assert first.status_code == 202
    operation_id = first.json()["operation_id"]
    del first
    second = _submit(env, repository_id, artifact_id, size_bytes, raw_sha256, idempotency_key="response-loss")
    assert second.status_code == 202
    assert second.json()["operation_id"] == operation_id


def test_submit_concurrent_different_keys_respects_queue_limit(tmp_path: Path) -> None:
    limited = create_import_http_environment(tmp_path, max_queued_imports=2)
    try:
        repository_id = limited.seed_repository()
        artifact_id, size_bytes, raw_sha256 = limited.seed_artifact(repository_id)
        barrier = threading.Barrier(3)
        results: list[int] = []
        errors: list[BaseException] = []

        def worker(key: str) -> None:
            barrier.wait()
            try:
                response = _submit(
                    limited,
                    repository_id,
                    artifact_id,
                    size_bytes,
                    raw_sha256,
                    idempotency_key=key,
                )
                results.append(response.status_code)
            except BaseException as exc:
                errors.append(exc)

        threads = [
            threading.Thread(target=worker, args=("concurrent-1",)),
            threading.Thread(target=worker, args=("concurrent-2",)),
            threading.Thread(target=worker, args=("concurrent-3",)),
        ]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        assert errors == []
        assert sorted(results) == [202, 202, 429]
    finally:
        limited.close()


def test_submit_rejects_invalid_json_body(env: ImportHttpTestEnvironment) -> None:
    repository_id = env.seed_repository()
    response = env.client.post(
        f"/v1/repositories/{repository_id}/versioned/imports",
        headers=import_headers(),
        content="not-json",
    )
    assert response.status_code == 422


def test_submit_rejects_non_main_target_ref(env: ImportHttpTestEnvironment) -> None:
    repository_id = env.seed_repository()
    artifact_id, size_bytes, raw_sha256 = env.seed_artifact(repository_id)
    response = _submit(
        env,
        repository_id,
        artifact_id,
        size_bytes,
        raw_sha256,
        body_overrides={"target_ref": "feature"},
    )
    assert response.status_code == 422
    assert response.json()["code"] == "REQUEST_VALIDATION_FAILED"


def test_submit_malformed_durable_row_replay_returns_internal_error(env: ImportHttpTestEnvironment) -> None:
    repository_id = env.seed_repository()
    idempotency_key = "malformed-replay"
    operation_id, artifact_id, size_bytes, raw_sha256 = _seed_operation_for_replay(
        env,
        repository_id,
        idempotency_key=idempotency_key,
        terminal_status=OperationStatus.SUCCEEDED,
    )
    _inject_malformed_result_json(env, operation_id)
    response = _submit(
        env,
        repository_id,
        artifact_id,
        size_bytes,
        raw_sha256,
        idempotency_key=idempotency_key,
    )
    assert response.status_code == 500
    assert response.json()["code"] == "INTERNAL_ERROR"
    assert "sqlite" not in response.text.lower()
    assert "result_json" not in response.text.lower()


def test_submit_artifact_file_missing_at_admission_returns_404(env: ImportHttpTestEnvironment) -> None:
    repository_id = env.seed_repository()
    artifact_id, size_bytes, raw_sha256 = env.seed_artifact(repository_id)
    ready_path = artifact_ready_path(env.layout, repository_id, artifact_id)
    ready_path.unlink()
    with patch(
        "gateway_repository_service.versioned_import.submission.is_artifact_visible",
        side_effect=[True, False],
    ):
        response = _submit(
            env,
            repository_id,
            artifact_id,
            size_bytes,
            raw_sha256,
            idempotency_key="admit-race",
        )
    assert response.status_code == 404
    assert response.json()["code"] == "ARTIFACT_NOT_FOUND"


@pytest.mark.serial
def test_submit_rejects_queued_when_ready_file_removed_before_insert(
    env: ImportHttpTestEnvironment,
) -> None:
    repository_id = env.seed_repository()
    artifact_id, size_bytes, raw_sha256 = env.seed_artifact(repository_id)
    ready_path = artifact_ready_path(env.layout, repository_id, artifact_id)
    pause_before_admit = threading.Event()
    unlink_done = threading.Event()
    import_store = env.runtime.import_store
    original_admit = import_store.admit_new_import

    def paused_admit(*args: Any, **kwargs: Any) -> Any:
        pause_before_admit.set()
        assert unlink_done.wait(timeout=5)
        return original_admit(*args, **kwargs)

    def unlink_worker() -> None:
        assert pause_before_admit.wait(timeout=5)
        ready_path.unlink()
        unlink_done.set()

    unlink_thread = threading.Thread(target=unlink_worker)
    unlink_thread.start()
    try:
        with patch.object(import_store, "admit_new_import", paused_admit):
            response = _submit(
                env,
                repository_id,
                artifact_id,
                size_bytes,
                raw_sha256,
                idempotency_key="artifact-removed-http",
            )
    finally:
        unlink_thread.join(timeout=5)

    assert not unlink_thread.is_alive()
    assert response.status_code == 404
    assert response.json()["code"] == "ARTIFACT_NOT_FOUND"
    assert env.runtime.import_store.count_global_queued() == 0


@pytest.mark.serial
def test_submit_rejects_queued_when_ready_file_removed_after_finalize(
    env: ImportHttpTestEnvironment,
) -> None:
    repository_id = env.seed_repository()
    artifact_id, size_bytes, raw_sha256 = env.seed_artifact(repository_id)
    ready_path = artifact_ready_path(env.layout, repository_id, artifact_id)
    original_finalize = ArtifactAdmissionPin.finalize_new_admission

    def finalize_then_unlink(self: ArtifactAdmissionPin) -> None:
        original_finalize(self)
        self.ready_path.unlink()

    with patch.object(ArtifactAdmissionPin, "finalize_new_admission", finalize_then_unlink):
        response = _submit(
            env,
            repository_id,
            artifact_id,
            size_bytes,
            raw_sha256,
            idempotency_key="artifact-removed-after-finalize",
        )

    assert response.status_code == 404
    assert response.json()["code"] == "ARTIFACT_NOT_FOUND"
    assert env.runtime.import_store.count_global_queued() == 0
    assert not ready_path.is_file()


def test_submit_malformed_artifact_lifecycle_scope_returns_internal_error(
    env: ImportHttpTestEnvironment,
) -> None:
    repository_id = env.seed_repository()
    artifact_id, size_bytes, raw_sha256 = env.seed_artifact(repository_id)
    with control_db_transaction(env.control_store) as connection:
        connection.execute(
            "UPDATE artifact_lifecycle SET repository_scope = ? WHERE artifact_id = ?",
            ("not-a-uuid", str(artifact_id)),
        )
    response = _submit(
        env,
        repository_id,
        artifact_id,
        size_bytes,
        raw_sha256,
        idempotency_key="malformed-lifecycle-scope",
    )
    assert response.status_code == 500
    assert response.json()["code"] == "INTERNAL_ERROR"
    assert "sqlite" not in response.text.lower()


@pytest.mark.serial
def test_submit_admission_pin_blocks_cooperative_cleanup(env: ImportHttpTestEnvironment) -> None:
    repository_id = env.seed_repository()
    artifact_id, size_bytes, raw_sha256 = env.seed_artifact(repository_id)
    ready_path = artifact_ready_path(env.layout, repository_id, artifact_id)
    pause_before_admit = threading.Event()
    resume_admit = threading.Event()
    import_store = env.runtime.import_store
    original_admit = import_store.admit_new_import

    def paused_admit(*args: Any, **kwargs: Any) -> Any:
        pause_before_admit.set()
        assert resume_admit.wait(timeout=5)
        return original_admit(*args, **kwargs)

    def cleanup_worker() -> None:
        assert pause_before_admit.wait(timeout=5)
        outcome = artifact_cleanup.cleanup_ready_artifact_bytes(
            import_store,
            env.layout,
            repository_id=repository_id,
            artifact_id=artifact_id,
            ttl_seconds=env.settings.artifact_ttl_seconds,
        )
        assert outcome == "busy"
        assert ready_path.is_file()
        resume_admit.set()

    cleanup_thread = threading.Thread(target=cleanup_worker)
    cleanup_thread.start()
    try:
        with patch.object(import_store, "admit_new_import", paused_admit):
            response = _submit(
                env,
                repository_id,
                artifact_id,
                size_bytes,
                raw_sha256,
                idempotency_key="admission-pin-cleanup",
            )
    finally:
        cleanup_thread.join(timeout=5)

    assert response.status_code == 202
    assert env.runtime.import_store.count_global_queued() == 1


@pytest.mark.serial
def test_submit_same_key_during_pending_waits_for_resolution(
    env: ImportHttpTestEnvironment,
) -> None:
    repository_id = env.seed_repository()
    artifact_id, size_bytes, raw_sha256 = env.seed_artifact(repository_id)
    pause_after_admit = threading.Event()
    resume_first = threading.Event()
    second_started = threading.Event()
    results: dict[str, Any] = {}
    import_store = env.runtime.import_store
    original_admit = import_store.admit_new_import

    def paused_admit(*args: Any, **kwargs: Any) -> Any:
        result = original_admit(*args, **kwargs)
        pause_after_admit.set()
        assert resume_first.wait(timeout=5)
        return result

    original_finalize = ArtifactAdmissionPin.finalize_new_admission

    def finalize_then_unlink(self: ArtifactAdmissionPin) -> None:
        original_finalize(self)
        self.ready_path.unlink()

    def first_submit() -> None:
        with patch.object(import_store, "admit_new_import", paused_admit):
            with patch.object(ArtifactAdmissionPin, "finalize_new_admission", finalize_then_unlink):
                results["first"] = _submit(
                    env,
                    repository_id,
                    artifact_id,
                    size_bytes,
                    raw_sha256,
                    idempotency_key="pending-same-key",
                )

    def second_submit() -> None:
        assert pause_after_admit.wait(timeout=5)
        second_started.set()
        results["second"] = _submit(
            env,
            repository_id,
            artifact_id,
            size_bytes,
            raw_sha256,
            idempotency_key="pending-same-key",
        )

    first_thread = threading.Thread(target=first_submit)
    second_thread = threading.Thread(target=second_submit)
    first_thread.start()
    assert pause_after_admit.wait(timeout=5)
    second_thread.start()
    assert second_started.wait(timeout=5)
    assert results.get("second") is None
    resume_first.set()
    first_thread.join(timeout=5)
    second_thread.join(timeout=5)

    assert results["first"].status_code == 404
    assert results["first"].json()["code"] == "ARTIFACT_NOT_FOUND"
    assert results["second"].status_code == 404
    assert results["second"].json()["code"] == "ARTIFACT_NOT_FOUND"
    assert env.runtime.import_store.lookup_by_key(
        repository_id,
        IdempotencyKeyHash.from_raw_key("pending-same-key"),
    ) is None
    assert env.runtime.import_store.count_global_queued() == 0


@pytest.mark.serial
def test_submit_rejects_different_fingerprint_immediately_while_pending(
    env: ImportHttpTestEnvironment,
) -> None:
    repository_id = env.seed_repository()
    artifact_id, size_bytes, raw_sha256 = env.seed_artifact(repository_id)
    pause_after_admit = threading.Event()
    resume_first = threading.Event()
    conflict_done = threading.Event()
    results: dict[str, Any] = {}
    import_store = env.runtime.import_store
    original_admit = import_store.admit_new_import

    def paused_admit(*args: Any, **kwargs: Any) -> Any:
        result = original_admit(*args, **kwargs)
        pause_after_admit.set()
        assert resume_first.wait(timeout=5)
        return result

    original_finalize = ArtifactAdmissionPin.finalize_new_admission

    def finalize_then_unlink(self: ArtifactAdmissionPin) -> None:
        original_finalize(self)
        self.ready_path.unlink()

    def first_submit() -> None:
        with patch.object(import_store, "admit_new_import", paused_admit):
            with patch.object(ArtifactAdmissionPin, "finalize_new_admission", finalize_then_unlink):
                results["first"] = _submit(
                    env,
                    repository_id,
                    artifact_id,
                    size_bytes,
                    raw_sha256,
                    idempotency_key="pending-conflict-key",
                )

    def conflict_submit() -> None:
        assert pause_after_admit.wait(timeout=5)
        results["conflict"] = _submit(
            env,
            repository_id,
            artifact_id,
            size_bytes,
            raw_sha256,
            idempotency_key="pending-conflict-key",
            body_overrides={"expected_commit_id": "commit-9"},
        )
        conflict_done.set()

    first_thread = threading.Thread(target=first_submit)
    conflict_thread = threading.Thread(target=conflict_submit)
    first_thread.start()
    assert pause_after_admit.wait(timeout=5)
    conflict_thread.start()
    assert conflict_done.wait(timeout=2)
    assert results["conflict"].status_code == 409
    assert results["conflict"].json()["code"] == "IDEMPOTENCY_CONFLICT"
    assert results.get("first") is None
    resume_first.set()
    first_thread.join(timeout=5)
    conflict_thread.join(timeout=5)
    assert results["first"].status_code == 404
    assert env.runtime.import_store.count_global_queued() == 0


@pytest.mark.serial
def test_submit_publish_sqlite_fault_returns_service_not_ready_not_404(
    env: ImportHttpTestEnvironment,
) -> None:
    repository_id = env.seed_repository()
    artifact_id, size_bytes, raw_sha256 = env.seed_artifact(repository_id)
    import_store = env.runtime.import_store

    def failing_publish(operation_id: UUID) -> bool:
        del operation_id
        raise sqlite3.OperationalError("database is locked")

    with patch.object(import_store, "publish_queued_import", side_effect=failing_publish):
        response = _submit(
            env,
            repository_id,
            artifact_id,
            size_bytes,
            raw_sha256,
            idempotency_key="publish-sqlite-fault",
        )

    assert response.status_code == 503
    assert response.json()["code"] == "SERVICE_NOT_READY"
    assert env.runtime.import_store.count_global_queued() == 0


@pytest.mark.serial
def test_submit_claim_before_abort_does_not_return_false_404(
    env: ImportHttpTestEnvironment,
) -> None:
    repository_id = env.seed_repository()
    artifact_id, size_bytes, raw_sha256 = env.seed_artifact(repository_id)
    pause_after_admit = threading.Event()
    resume_submit = threading.Event()
    claim_checked = threading.Event()
    import_store = env.runtime.import_store
    original_admit = import_store.admit_new_import
    pending_operation_id: dict[str, UUID] = {}

    def paused_admit(*args: Any, **kwargs: Any) -> Any:
        result = original_admit(*args, **kwargs)
        if result.is_new:
            pending_operation_id["id"] = result.operation_id
        pause_after_admit.set()
        assert resume_submit.wait(timeout=5)
        return result

    def claim_worker() -> None:
        assert pause_after_admit.wait(timeout=5)
        operation_id = pending_operation_id["id"]
        assert import_store.claim_if_queued(operation_id) is None
        claim_checked.set()
        resume_submit.set()

    original_finalize = ArtifactAdmissionPin.finalize_new_admission

    def finalize_then_unlink(self: ArtifactAdmissionPin) -> None:
        assert claim_checked.wait(timeout=5)
        original_finalize(self)
        self.ready_path.unlink()

    claim_thread = threading.Thread(target=claim_worker)
    claim_thread.start()
    try:
        with patch.object(import_store, "admit_new_import", paused_admit):
            with patch.object(ArtifactAdmissionPin, "finalize_new_admission", finalize_then_unlink):
                response = _submit(
                    env,
                    repository_id,
                    artifact_id,
                    size_bytes,
                    raw_sha256,
                    idempotency_key="claim-before-abort",
                )
    finally:
        claim_thread.join(timeout=5)

    assert not claim_thread.is_alive()
    assert response.status_code == 404
    assert response.json()["code"] == "ARTIFACT_NOT_FOUND"
    assert env.runtime.import_store.count_global_queued() == 0


@pytest.mark.serial
def test_submit_abort_failure_replays_when_operation_already_claimed(
    env: ImportHttpTestEnvironment,
) -> None:
    repository_id = env.seed_repository()
    artifact_id, size_bytes, raw_sha256 = env.seed_artifact(repository_id)
    pause_after_admit = threading.Event()
    resume_finalize = threading.Event()
    import_store = env.runtime.import_store
    original_admit = import_store.admit_new_import
    pending_operation_id: dict[str, UUID] = {}

    def paused_admit(*args: Any, **kwargs: Any) -> Any:
        result = original_admit(*args, **kwargs)
        if result.is_new:
            pending_operation_id["id"] = result.operation_id
        pause_after_admit.set()
        assert resume_finalize.wait(timeout=5)
        return result

    def publish_and_claim_worker() -> None:
        assert pause_after_admit.wait(timeout=5)
        operation_id = pending_operation_id["id"]
        assert import_store.claim_if_queued(operation_id) is None
        assert import_store.publish_queued_import(operation_id) is True
        assert import_store.claim_if_queued(operation_id) is not None
        resume_finalize.set()

    original_finalize = ArtifactAdmissionPin.finalize_new_admission

    def finalize_then_unlink(self: ArtifactAdmissionPin) -> None:
        original_finalize(self)
        self.ready_path.unlink()

    worker = threading.Thread(target=publish_and_claim_worker)
    worker.start()
    try:
        with patch.object(import_store, "admit_new_import", paused_admit):
            with patch.object(ArtifactAdmissionPin, "finalize_new_admission", finalize_then_unlink):
                response = _submit(
                    env,
                    repository_id,
                    artifact_id,
                    size_bytes,
                    raw_sha256,
                    idempotency_key="abort-failure-replay",
                )
    finally:
        worker.join(timeout=5)

    assert not worker.is_alive()
    assert response.status_code == 202
    operation = import_store.lookup_by_key(
        repository_id,
        IdempotencyKeyHash.from_raw_key("abort-failure-replay"),
    )
    assert operation is not None
    assert operation.status == OperationStatus.RUNNING


@pytest.mark.integration
def test_submit_integration_happy_path(tmp_path: Path) -> None:
    settings = lifecycle_settings(tmp_path)
    with TestClient(create_app(settings)) as client:
        repository_id = create_repository(client)
        payload = b"artifact-bytes"
        upload = client.post(
            f"/v1/repositories/{repository_id}/artifacts",
            headers=upload_headers(idempotency_key="upload-for-import", payload=payload),
            content=payload,
        )
        assert upload.status_code == 201
        artifact_ref = upload.json()["artifact_ref"]
        body = {
            "repository_id": str(repository_id),
            "artifact_ref": artifact_ref,
            "target_ref": "main",
            "expected_commit_id": "commit-0",
        }
        response = client.post(
            f"/v1/repositories/{repository_id}/versioned/imports",
            headers=import_headers(idempotency_key="import-integration"),
            content=json.dumps(body),
        )
        assert response.status_code == 202
        operation_id = response.json()["operation_id"]
        assert operation_id
        poll = client.get(
            f"/v1/repositories/{repository_id}/operations/{operation_id}",
            headers={"Authorization": "Bearer test-bearer-token"},
        )
        assert poll.status_code == 200
        assert poll.json()["operation"]["operation_id"] == operation_id
