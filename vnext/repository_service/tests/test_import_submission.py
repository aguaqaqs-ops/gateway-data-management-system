"""Unit tests for import submission admission ordering."""

from __future__ import annotations

import sqlite3
import threading
from collections.abc import Iterator
from pathlib import Path
from typing import Any
from unittest.mock import patch
from uuid import UUID

import pytest

from gateway_repository_contracts import ImportRequestHeaders, SubmitVersionedImportRequest
from gateway_repository_service.http.errors import ServiceError
from gateway_repository_service.versioned_import.submission import ImportSubmissionService
from support.http_harness import ImportHttpTestEnvironment, create_import_http_environment, import_request_body

STORE_ERROR_CASES = [
    ("invalid_json", "UPDATE repository_import_operations SET result_json = ? WHERE operation_id = ?", ("{",)),
    (
        "invalid_artifact_id",
        "UPDATE repository_import_operations SET artifact_id = ? WHERE operation_id = ?",
        ("not-a-uuid",),
    ),
    (
        "fingerprint_text",
        "UPDATE repository_import_operations SET request_fingerprint = ? WHERE operation_id = ?",
        ("not-bytes",),
    ),
    (
        "fingerprint_integer",
        "UPDATE repository_import_operations SET request_fingerprint = ? WHERE operation_id = ?",
        (42,),
    ),
]

PREFLIGHT_SQLITE_FAULT_CASES = [
    (
        "repository_visible",
        "gateway_repository_service.versioned_import.submission.is_repository_visible",
    ),
    (
        "artifact_lifecycle",
        "gateway_repository_service.versioned_import.submission.ImportSubmissionService._artifact_acceptable",
    ),
    (
        "artifact_visible",
        "gateway_repository_service.versioned_import.submission.is_artifact_visible",
    ),
]


@pytest.fixture
def env(tmp_path: Path) -> Iterator[ImportHttpTestEnvironment]:
    environment = create_import_http_environment(tmp_path)
    yield environment
    environment.close()


def _seed_operation(env: ImportHttpTestEnvironment, repository_id: UUID, *, key: str) -> UUID:
    artifact_id, size_bytes, raw_sha256 = env.seed_artifact(repository_id)
    body = import_request_body(
        repository_id=repository_id,
        artifact_id=artifact_id,
        size_bytes=size_bytes,
        raw_sha256=raw_sha256,
    )
    service = ImportSubmissionService(env.runtime)
    response = service.submit(
        repository_id,
        ImportRequestHeaders(idempotency_key=key),
        SubmitVersionedImportRequest.model_validate(body),
        request_id="req-1",
    )
    return response.operation_id


def test_concurrent_same_key_converges_to_one_operation(env: ImportHttpTestEnvironment) -> None:
    repository_id = env.seed_repository()
    artifact_id, size_bytes, raw_sha256 = env.seed_artifact(repository_id)
    body = import_request_body(
        repository_id=repository_id,
        artifact_id=artifact_id,
        size_bytes=size_bytes,
        raw_sha256=raw_sha256,
    )
    service = ImportSubmissionService(env.runtime)
    results: list[str] = []
    errors: list[BaseException] = []
    barrier = threading.Barrier(4)
    request_model = SubmitVersionedImportRequest.model_validate(body)
    header_model = ImportRequestHeaders(idempotency_key="concurrent-submit")

    def worker() -> None:
        barrier.wait()
        try:
            response = service.submit(
                repository_id,
                header_model,
                request_model,
                request_id="req-1",
            )
            results.append(str(response.operation_id))
        except BaseException as exc:
            errors.append(exc)

    threads = [threading.Thread(target=worker) for _ in range(4)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert errors == []
    assert len(set(results)) == 1
    assert env.runtime.import_store.count_global_queued() == 1


def test_replay_precedes_queue_full(env: ImportHttpTestEnvironment, tmp_path: Path) -> None:
    limited = create_import_http_environment(tmp_path, max_queued_imports=1)
    try:
        repository_id = limited.seed_repository()
        artifact_id, size_bytes, raw_sha256 = limited.seed_artifact(repository_id)
        body = import_request_body(
            repository_id=repository_id,
            artifact_id=artifact_id,
            size_bytes=size_bytes,
            raw_sha256=raw_sha256,
        )
        service = ImportSubmissionService(limited.runtime)
        request_model = SubmitVersionedImportRequest.model_validate(body)
        header_model = ImportRequestHeaders(idempotency_key="replay-before-full")
        first = service.submit(repository_id, header_model, request_model, request_id="req-1")
        second = service.submit(repository_id, header_model, request_model, request_id="req-2")
        assert first.operation_id == second.operation_id
        other_headers = ImportRequestHeaders(idempotency_key="different-key")
        with pytest.raises(ServiceError) as exc_info:
            service.submit(
                repository_id,
                other_headers,
                request_model,
                request_id="req-3",
            )
        assert exc_info.value.code == "IMPORT_QUEUE_FULL"
    finally:
        limited.close()


@pytest.mark.parametrize(("case_name", "sql", "params_prefix"), STORE_ERROR_CASES)
def test_submit_replay_maps_store_invariant_to_internal_error(
    env: ImportHttpTestEnvironment,
    case_name: str,
    sql: str,
    params_prefix: tuple[object, ...],
) -> None:
    repository_id = env.seed_repository()
    operation_id = _seed_operation(env, repository_id, key=f"invariant-{case_name}")
    env.control_store.connection.execute(sql, (*params_prefix, str(operation_id)))
    env.control_store.connection.commit()
    artifact_id, size_bytes, raw_sha256 = env.seed_artifact(repository_id)
    body = import_request_body(
        repository_id=repository_id,
        artifact_id=artifact_id,
        size_bytes=size_bytes,
        raw_sha256=raw_sha256,
    )
    service = ImportSubmissionService(env.runtime)
    with pytest.raises(ServiceError) as exc_info:
        service.submit(
            repository_id,
            ImportRequestHeaders(idempotency_key=f"invariant-{case_name}"),
            SubmitVersionedImportRequest.model_validate(body),
            request_id="req-1",
        )
    assert exc_info.value.status_code == 500
    assert exc_info.value.code == "INTERNAL_ERROR"


def test_lookup_replay_state_sqlite_fault_maps_to_service_not_ready(env: ImportHttpTestEnvironment) -> None:
    repository_id = env.seed_repository()
    _seed_operation(env, repository_id, key="sqlite-fault")
    artifact_id, size_bytes, raw_sha256 = env.seed_artifact(repository_id)
    body = import_request_body(
        repository_id=repository_id,
        artifact_id=artifact_id,
        size_bytes=size_bytes,
        raw_sha256=raw_sha256,
    )
    service = ImportSubmissionService(env.runtime)

    def failing_lookup(*args: object, **kwargs: object) -> object:
        del args, kwargs
        raise sqlite3.OperationalError("database is locked")

    with patch.object(env.runtime.import_store, "lookup_replay_state", side_effect=failing_lookup):
        with pytest.raises(ServiceError) as exc_info:
            service.submit(
                repository_id,
                ImportRequestHeaders(idempotency_key="sqlite-fault"),
                SubmitVersionedImportRequest.model_validate(body),
                request_id="req-1",
            )
    assert exc_info.value.status_code == 503
    assert exc_info.value.code == "SERVICE_NOT_READY"


@pytest.mark.parametrize(("case_name", "patch_target"), PREFLIGHT_SQLITE_FAULT_CASES)
def test_preflight_sqlite_fault_after_successful_lookup_maps_to_service_not_ready(
    env: ImportHttpTestEnvironment,
    case_name: str,
    patch_target: str,
) -> None:
    repository_id = env.seed_repository()
    artifact_id, size_bytes, raw_sha256 = env.seed_artifact(repository_id)
    body = import_request_body(
        repository_id=repository_id,
        artifact_id=artifact_id,
        size_bytes=size_bytes,
        raw_sha256=raw_sha256,
    )
    service = ImportSubmissionService(env.runtime)

    def failing_preflight(*args: object, **kwargs: object) -> object:
        del args, kwargs
        raise sqlite3.OperationalError("database is locked")

    with patch(patch_target, side_effect=failing_preflight):
        with pytest.raises(ServiceError) as exc_info:
            service.submit(
                repository_id,
                ImportRequestHeaders(idempotency_key=f"preflight-sqlite-{case_name}"),
                SubmitVersionedImportRequest.model_validate(body),
                request_id="req-1",
            )
    assert exc_info.value.status_code == 503
    assert exc_info.value.code == "SERVICE_NOT_READY"


def test_pending_admission_resolution_sqlite_fault_maps_to_service_not_ready(
    env: ImportHttpTestEnvironment,
) -> None:
    repository_id = env.seed_repository()
    artifact_id, size_bytes, raw_sha256 = env.seed_artifact(repository_id)
    body = import_request_body(
        repository_id=repository_id,
        artifact_id=artifact_id,
        size_bytes=size_bytes,
        raw_sha256=raw_sha256,
    )
    service = ImportSubmissionService(env.runtime)
    pause_after_admit = threading.Event()
    resume_admit = threading.Event()
    import_store = env.runtime.import_store
    original_admit = import_store.admit_new_import

    def paused_admit(*args: Any, **kwargs: Any) -> Any:
        result = original_admit(*args, **kwargs)
        pause_after_admit.set()
        assert resume_admit.wait(timeout=5)
        return result

    def first_submit() -> None:
        with patch.object(import_store, "admit_new_import", paused_admit):
            service.submit(
                repository_id,
                ImportRequestHeaders(idempotency_key="pending-sqlite-wait"),
                SubmitVersionedImportRequest.model_validate(body),
                request_id="req-first",
            )

    first_thread = threading.Thread(target=first_submit)
    first_thread.start()
    assert pause_after_admit.wait(timeout=5)

    def failing_status(operation_id: UUID) -> str | None:
        del operation_id
        raise sqlite3.OperationalError("database is locked")

    with patch.object(import_store, "get_operation_durable_status", side_effect=failing_status):
        with pytest.raises(ServiceError) as exc_info:
            service.submit(
                repository_id,
                ImportRequestHeaders(idempotency_key="pending-sqlite-wait"),
                SubmitVersionedImportRequest.model_validate(body),
                request_id="req-second",
            )
    assert exc_info.value.status_code == 503
    assert exc_info.value.code == "SERVICE_NOT_READY"
    resume_admit.set()
    first_thread.join(timeout=5)


def test_new_submit_after_control_db_closed_maps_to_service_not_ready(env: ImportHttpTestEnvironment) -> None:
    repository_id = env.seed_repository()
    artifact_id, size_bytes, raw_sha256 = env.seed_artifact(repository_id)
    body = import_request_body(
        repository_id=repository_id,
        artifact_id=artifact_id,
        size_bytes=size_bytes,
        raw_sha256=raw_sha256,
    )
    env.control_store.close()
    service = ImportSubmissionService(env.runtime)
    with pytest.raises(ServiceError) as exc_info:
        service.submit(
            repository_id,
            ImportRequestHeaders(idempotency_key="db-closed"),
            SubmitVersionedImportRequest.model_validate(body),
            request_id="req-1",
        )
    assert exc_info.value.status_code == 503
    assert exc_info.value.code == "SERVICE_NOT_READY"
