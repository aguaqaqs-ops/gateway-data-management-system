"""Tests for durable Versioned import worker orchestration."""

from __future__ import annotations

import time
from collections.abc import Iterator
from pathlib import Path
from uuid import UUID

import pytest

from gateway_repository_contracts import OperationStatus, SimpleError
from gateway_repository_service.upload_artifact.visibility import artifact_ready_path
from gateway_repository_service.versioned_import.faults import (
    ConfigurableImportWorkerFaultInjector,
    ImportWorkerFaultPoint,
    NoOpImportWorkerFaultInjector,
)
from gateway_repository_service.versioned_import.models import MANUAL_RECOVERY_REQUIRED_CODE
from gateway_repository_service.versioned_import.verification import (
    IMPORT_REJECTED_CODE,
    VERIFICATION_FAILED_NOT_PUBLISHED_CODE,
)
from support.import_worker_harness import (
    DEFAULT_MAIN_COMMIT,
    WorkerTestEnvironment,
)

REPOSITORY_ID = UUID("018f0f3e-7b0a-7c15-8a9e-2e4b9f4d2c11")
OTHER_REPOSITORY_ID = UUID("018f0f3e-7b0a-7c16-8a9e-2e4b9f4d2c11")
ARTIFACT_ID = UUID("018f0f3e-7b0a-7c16-8a9e-2e4b9f4d2c11")
OPERATION_ID = UUID("018f0f3e-7b0a-7c17-8a9e-2e4b9f4d2c11")


@pytest.fixture
def worker_env(tmp_path: Path) -> Iterator[WorkerTestEnvironment]:
    env = WorkerTestEnvironment(tmp_path)
    env.pool.start()
    yield env
    env.close()


def test_worker_happy_path(worker_env: WorkerTestEnvironment) -> None:
    operation_id = worker_env.enqueue(
        REPOSITORY_ID,
        artifact_id=ARTIFACT_ID,
        operation_id=OPERATION_ID,
    )
    worker_env.wait_for_status(REPOSITORY_ID, operation_id, OperationStatus.SUCCEEDED)

    operation = worker_env.store.get_operation(REPOSITORY_ID, operation_id)
    assert operation is not None
    assert operation.result is not None
    assert operation.result.commit_id.startswith("candidate-")
    assert operation.result.expected_commit_id == DEFAULT_MAIN_COMMIT
    assert operation.result.canonicalization_manifest_digest == "manifest-digest-1"
    assert worker_env.provider_for(REPOSITORY_ID).read_ref("main") == operation.result.commit_id


def test_failure_mapping_import_rejected_on_replay_failure(
    worker_env: WorkerTestEnvironment,
) -> None:
    provider = worker_env.provider_for(REPOSITORY_ID)
    provider.fail_on_replay = True
    operation_id = worker_env.enqueue(REPOSITORY_ID, artifact_id=ARTIFACT_ID)
    worker_env.wait_for_status(REPOSITORY_ID, operation_id, OperationStatus.FAILED)

    operation = worker_env.store.get_operation(REPOSITORY_ID, operation_id)
    assert operation is not None
    assert operation.error is not None
    assert operation.error.code == IMPORT_REJECTED_CODE


def test_failure_mapping_expected_commit_mismatch(worker_env: WorkerTestEnvironment) -> None:
    operation_id = worker_env.enqueue(
        REPOSITORY_ID,
        artifact_id=ARTIFACT_ID,
        expected_commit_id="wrong-commit",
    )
    worker_env.wait_for_status(REPOSITORY_ID, operation_id, OperationStatus.FAILED)

    operation = worker_env.store.get_operation(REPOSITORY_ID, operation_id)
    assert operation is not None
    assert operation.error is not None
    assert operation.error.code == "EXPECTED_COMMIT_MISMATCH"


def test_failure_mapping_verification_failed_not_published(
    worker_env: WorkerTestEnvironment,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from gateway_repository_service.versioned_import import command as command_module

    def _raise_verification_failure(*_args: object, **_kwargs: object) -> None:
        from gateway_repository_service.versioned_import.verification import ImportVerificationError

        raise ImportVerificationError(
            VERIFICATION_FAILED_NOT_PUBLISHED_CODE,
            detail="user table set mismatch",
        )

    monkeypatch.setattr(command_module, "verify_import_candidate", _raise_verification_failure)
    operation_id = worker_env.enqueue(REPOSITORY_ID, artifact_id=ARTIFACT_ID)
    worker_env.wait_for_status(REPOSITORY_ID, operation_id, OperationStatus.FAILED)

    operation = worker_env.store.get_operation(REPOSITORY_ID, operation_id)
    assert operation is not None
    assert operation.error is not None
    assert operation.error.code == VERIFICATION_FAILED_NOT_PUBLISHED_CODE


def test_failure_mapping_manual_on_publish_ambiguity(worker_env: WorkerTestEnvironment) -> None:
    provider = worker_env.provider_for(REPOSITORY_ID)
    provider.publish_force_fail = True
    operation_id = worker_env.enqueue(REPOSITORY_ID, artifact_id=ARTIFACT_ID)
    worker_env.wait_for_status(REPOSITORY_ID, operation_id, OperationStatus.FAILED)

    operation = worker_env.store.get_operation(REPOSITORY_ID, operation_id)
    assert operation is not None
    assert operation.error is not None
    assert operation.error.code == MANUAL_RECOVERY_REQUIRED_CODE


def test_manual_barrier_skips_queued_operation(worker_env: WorkerTestEnvironment) -> None:
    blocked_id = worker_env.enqueue(
        REPOSITORY_ID,
        artifact_id=ARTIFACT_ID,
        operation_id=OPERATION_ID,
        key="blocked",
    )
    worker_env.store.claim_if_queued(blocked_id)
    worker_env.store.mark_failed(
        blocked_id,
        error=SimpleError(
            code=MANUAL_RECOVERY_REQUIRED_CODE,
            message="manual",
            request_id=None,
        ),
    )

    second_artifact = UUID("018f0f3e-7b0a-7c18-8a9e-2e4b9f4d2c11")
    second_operation = worker_env.enqueue(
        REPOSITORY_ID,
        artifact_id=second_artifact,
        key="queued-behind-barrier",
    )

    time.sleep(0.5)
    pending = worker_env.store.get_operation(REPOSITORY_ID, second_operation)
    assert pending is not None
    assert pending.status == OperationStatus.QUEUED


def test_dispatcher_does_not_double_claim_same_repository(
    worker_env: WorkerTestEnvironment,
) -> None:
    first_artifact = ARTIFACT_ID
    second_artifact = UUID("018f0f3e-7b0a-7c18-8a9e-2e4b9f4d2c11")
    provider = worker_env.provider_for(REPOSITORY_ID)
    provider.replay_delay_seconds = 0.2

    first_operation = worker_env.enqueue(
        REPOSITORY_ID,
        artifact_id=first_artifact,
        key="first",
    )
    worker_env.enqueue(REPOSITORY_ID, artifact_id=second_artifact, key="second")

    time.sleep(0.05)
    running = [
        row
        for row in worker_env.connection.execute(
            "SELECT status FROM repository_import_operations WHERE repository_scope = ?",
            (REPOSITORY_ID.hex,),
        ).fetchall()
        if str(row["status"]) == OperationStatus.RUNNING.value
    ]
    assert len(running) == 1

    worker_env.wait_for_status(REPOSITORY_ID, first_operation, OperationStatus.SUCCEEDED)


@pytest.mark.serial
def test_same_repository_executes_in_fifo_order(tmp_path: Path) -> None:
    env = WorkerTestEnvironment(tmp_path, max_import_workers=4)
    env.pool.start()
    try:
        provider = env.provider_for(REPOSITORY_ID)
        provider.replay_delay_seconds = 0.05
        completion_order: list[UUID] = []

        operation_specs = [
            (
                UUID("018f0f3e-7b0a-7c17-8a9e-2e4b9f4d2c11"),
                UUID("018f0f3e-7b0a-7c18-8a9e-2e4b9f4d2c11"),
                "fifo-1",
            ),
            (
                UUID("018f0f3e-7b0a-7c1a-8a9e-2e4b9f4d2c11"),
                UUID("018f0f3e-7b0a-7c19-8a9e-2e4b9f4d2c11"),
                "fifo-2",
            ),
            (
                UUID("018f0f3e-7b0a-7c1c-8a9e-2e4b9f4d2c11"),
                UUID("018f0f3e-7b0a-7c1b-8a9e-2e4b9f4d2c11"),
                "fifo-3",
            ),
        ]

        for operation_id, artifact_id, key in operation_specs:
            expected_commit = provider.read_ref("main")
            operation = env.enqueue(
                REPOSITORY_ID,
                artifact_id=artifact_id,
                operation_id=operation_id,
                key=key,
                expected_commit_id=expected_commit,
            )
            env.wait_for_status(REPOSITORY_ID, operation, OperationStatus.SUCCEEDED, timeout=10.0)
            completion_order.append(operation)

        assert completion_order == [spec[0] for spec in operation_specs]
    finally:
        env.close()


@pytest.mark.serial
def test_cross_repository_respects_global_worker_bound(tmp_path: Path) -> None:
    env = WorkerTestEnvironment(tmp_path, max_import_workers=2)
    env.pool.start()
    try:
        repositories = [
            UUID(f"018f0f3e-7b0a-7c1{i}-8a9e-2e4b9f4d2c11")
            for i in range(4)
        ]
        for index, repository_id in enumerate(repositories):
            provider = env.provider_for(repository_id)
            provider.replay_delay_seconds = 0.3
            env.enqueue(
                repository_id,
                artifact_id=UUID(f"018f0f3e-7b0a-7c2{index}-8a9e-2e4b9f4d2c11"),
                key=f"repo-{index}",
            )

        peak = 0
        deadline = time.monotonic() + 2.0
        while time.monotonic() < deadline:
            running = env.connection.execute(
                "SELECT COUNT(*) AS count FROM repository_import_operations WHERE status = ?",
                (OperationStatus.RUNNING.value,),
            ).fetchone()
            peak = max(peak, int(running["count"]))
            if peak >= 2:
                break
            time.sleep(0.02)

        assert peak <= 2
        assert peak >= 2
    finally:
        env.close()


@pytest.mark.parametrize(
    "point",
    list(ImportWorkerFaultPoint),
)
def test_fault_injector_points_are_configurable(point: ImportWorkerFaultPoint) -> None:
    injector = ConfigurableImportWorkerFaultInjector(points=frozenset({point}))
    with pytest.raises(RuntimeError, match="injected fault"):
        injector.maybe_raise(point)


def test_noop_fault_injector_is_inert() -> None:
    injector = NoOpImportWorkerFaultInjector()
    for point in ImportWorkerFaultPoint:
        injector.maybe_raise(point)


def test_success_cleanup_failure_does_not_change_result(
    worker_env: WorkerTestEnvironment,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def _fail_delete(_self: object, _context: object, _artifact_path: object) -> None:
        raise OSError("cleanup failed")

    monkeypatch.setattr(
        "gateway_repository_service.versioned_import.command.ImportOperationExecutor._best_effort_delete_artifact_bytes",
        _fail_delete,
    )
    operation_id = worker_env.enqueue(REPOSITORY_ID, artifact_id=ARTIFACT_ID)
    worker_env.wait_for_status(REPOSITORY_ID, operation_id, OperationStatus.SUCCEEDED)

    operation = worker_env.store.get_operation(REPOSITORY_ID, operation_id)
    assert operation is not None
    assert operation.status == OperationStatus.SUCCEEDED
    assert artifact_ready_path(worker_env.layout, REPOSITORY_ID, ARTIFACT_ID).exists()


def test_public_error_detail_does_not_expose_private_ref_or_path(
    worker_env: WorkerTestEnvironment,
) -> None:
    provider = worker_env.provider_for(REPOSITORY_ID)
    provider.fail_on_replay = True
    operation_id = worker_env.enqueue(REPOSITORY_ID, artifact_id=ARTIFACT_ID)
    worker_env.wait_for_status(REPOSITORY_ID, operation_id, OperationStatus.FAILED)

    operation = worker_env.store.get_operation(REPOSITORY_ID, operation_id)
    assert operation is not None
    assert operation.error is not None
    rendered = operation.error.model_dump_json()
    assert "gateway-import-" not in rendered
    assert "/tmp/" not in rendered
    assert "/root/" not in rendered
