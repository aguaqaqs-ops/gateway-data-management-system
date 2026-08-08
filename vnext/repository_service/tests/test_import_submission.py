"""Unit tests for import submission admission ordering."""

from __future__ import annotations

import threading
from collections.abc import Iterator
from pathlib import Path

import pytest

from gateway_repository_contracts import ImportRequestHeaders, SubmitVersionedImportRequest
from gateway_repository_service.http.errors import ServiceError
from gateway_repository_service.versioned_import.submission import ImportSubmissionService
from support.http_harness import ImportHttpTestEnvironment, create_import_http_environment, import_request_body


@pytest.fixture
def env(tmp_path: Path) -> Iterator[ImportHttpTestEnvironment]:
    environment = create_import_http_environment(tmp_path)
    yield environment
    environment.close()


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
