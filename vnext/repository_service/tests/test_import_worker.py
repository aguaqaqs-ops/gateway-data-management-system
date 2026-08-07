"""Tests for durable Versioned import worker orchestration."""

from __future__ import annotations

import time
from collections.abc import Iterator
from pathlib import Path
from uuid import UUID

import pytest

from gateway_repository_contracts import OperationStatus, SimpleError
from gateway_repository_service.upload_artifact.visibility import artifact_ready_path
from gateway_repository_service.versioned_import.errors import ImportProviderError
from gateway_repository_service.versioned_import.faults import (
    ConfigurableImportWorkerFaultInjector,
    ImportWorkerFaultPoint,
    NoOpImportWorkerFaultInjector,
)
from gateway_repository_service.versioned_import.models import (
    MANUAL_RECOVERY_REQUIRED_CODE,
    derive_private_ref_name,
)
from gateway_repository_service.versioned_import.models import ImportOperationExecutionContext
from gateway_repository_service.versioned_import.verification import (
    IMPORT_REJECTED_CODE,
    VERIFICATION_FAILED_NOT_PUBLISHED_CODE,
)
from support.import_worker_harness import (
    DEFAULT_MAIN_COMMIT,
    WorkerTestEnvironment,
)

REPOSITORY_ID = UUID("018f0f3e-7b0a-7c15-8a9e-2e4b9f4d2c11")
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


def test_zero_effect_provider_failure_maps_to_import_rejected(
    worker_env: WorkerTestEnvironment,
) -> None:
    provider = worker_env.provider_for(REPOSITORY_ID)

    def _fail_read_ref(_ref_name: str) -> str:
        raise ImportProviderError("initial read_ref failed")

    provider.read_ref = _fail_read_ref  # type: ignore[assignment]
    operation_id = worker_env.enqueue(REPOSITORY_ID, artifact_id=ARTIFACT_ID)
    worker_env.wait_for_status(REPOSITORY_ID, operation_id, OperationStatus.FAILED)

    operation = worker_env.store.get_operation(REPOSITORY_ID, operation_id)
    assert operation is not None
    assert operation.error is not None
    assert operation.error.code == IMPORT_REJECTED_CODE
    assert worker_env.store.has_unresolved_manual_barrier(REPOSITORY_ID) is False


def test_zero_effect_unknown_failure_maps_to_import_rejected(
    worker_env: WorkerTestEnvironment,
) -> None:
    provider = worker_env.provider_for(REPOSITORY_ID)

    def _fail_read_ref(_ref_name: str) -> str:
        raise RuntimeError("unexpected read failure")

    provider.read_ref = _fail_read_ref  # type: ignore[assignment]
    operation_id = worker_env.enqueue(REPOSITORY_ID, artifact_id=ARTIFACT_ID)
    worker_env.wait_for_status(REPOSITORY_ID, operation_id, OperationStatus.FAILED)

    operation = worker_env.store.get_operation(REPOSITORY_ID, operation_id)
    assert operation is not None
    assert operation.error is not None
    assert operation.error.code == IMPORT_REJECTED_CODE
    assert worker_env.store.has_unresolved_manual_barrier(REPOSITORY_ID) is False


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


@pytest.mark.serial
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


@pytest.mark.serial
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

    peak = 0
    deadline = time.monotonic() + 1.0
    while time.monotonic() < deadline:
        running = worker_env.connection.execute(
            """
            SELECT COUNT(*) AS count
            FROM repository_import_operations
            WHERE repository_scope = ?
              AND status = ?
            """,
            (REPOSITORY_ID.hex, OperationStatus.RUNNING.value),
        ).fetchone()
        peak = max(peak, int(running["count"]))
        if peak > 1:
            break
        time.sleep(0.01)

    assert peak <= 1
    worker_env.wait_for_status(REPOSITORY_ID, first_operation, OperationStatus.SUCCEEDED)


@pytest.mark.serial
def test_same_repository_running_mutex_observed(tmp_path: Path) -> None:
    env = WorkerTestEnvironment(tmp_path, max_import_workers=4)
    env.pool.start()
    try:
        provider = env.provider_for(REPOSITORY_ID)
        provider.replay_delay_seconds = 0.2
        operation_ids = [
            env.enqueue(
                REPOSITORY_ID,
                artifact_id=UUID(f"018f0f3e-7b0a-7c2{index}-8a9e-2e4b9f4d2c11"),
                operation_id=UUID(f"018f0f3e-7b0a-7c1{index}-8a9e-2e4b9f4d2c11"),
                key=f"mutex-{index}",
            )
            for index in range(4)
        ]

        peak = 0
        deadline = time.monotonic() + 5.0
        while time.monotonic() < deadline:
            running = env.connection.execute(
                """
                SELECT COUNT(*) AS count
                FROM repository_import_operations
                WHERE repository_scope = ?
                  AND status = ?
                """,
                (REPOSITORY_ID.hex, OperationStatus.RUNNING.value),
            ).fetchone()
            peak = max(peak, int(running["count"]))
            if all(
                (op := env.store.get_operation(REPOSITORY_ID, operation_id)) is not None
                and op.status in {OperationStatus.SUCCEEDED, OperationStatus.FAILED}
                for operation_id in operation_ids
            ):
                break
            time.sleep(0.02)

        assert peak <= 1
    finally:
        env.close()


@pytest.mark.serial
def test_same_repository_fifo_completion_order(tmp_path: Path) -> None:
    env = WorkerTestEnvironment(tmp_path, max_import_workers=4)
    env.pool.start()
    try:
        provider = env.provider_for(REPOSITORY_ID)
        provider.replay_delay_seconds = 0.05
        expected_commits = [
            DEFAULT_MAIN_COMMIT,
            "candidate-1",
            "candidate-2",
            "candidate-3",
        ]
        operation_specs = [
            (
                UUID(f"018f0f3e-7b0a-7c1{index}-8a9e-2e4b9f4d2c11"),
                UUID(f"018f0f3e-7b0a-7c2{index}-8a9e-2e4b9f4d2c11"),
                f"fifo-{index}",
                expected_commits[index],
            )
            for index in range(4)
        ]
        operation_ids = [
            env.enqueue(
                REPOSITORY_ID,
                artifact_id=artifact_id,
                operation_id=operation_id,
                key=key,
                expected_commit_id=expected_commit,
            )
            for operation_id, artifact_id, key, expected_commit in operation_specs
        ]

        for operation_id in operation_ids:
            env.wait_for_status(
                REPOSITORY_ID,
                operation_id,
                OperationStatus.SUCCEEDED,
                timeout=15.0,
            )

        completed = [
            env.store.get_operation(REPOSITORY_ID, operation_id)
            for operation_id in operation_ids
        ]
        expected_private_refs = [derive_private_ref_name(operation_id) for operation_id in operation_ids]
        assert provider.replay_order == expected_private_refs
        assert all(op is not None and op.status == OperationStatus.SUCCEEDED for op in completed)
    finally:
        env.close()


@pytest.mark.serial
def test_cross_repository_respects_global_worker_bound(tmp_path: Path) -> None:
    env = WorkerTestEnvironment(tmp_path, max_import_workers=2)
    env.pool.start()
    try:
        repositories = [
            UUID(f"018f0f3e-7b0a-7c3{i}-8a9e-2e4b9f4d2c11")
            for i in range(6)
        ]
        operation_ids: list[UUID] = []
        for index, repository_id in enumerate(repositories):
            provider = env.provider_for(repository_id)
            provider.replay_delay_seconds = 0.3
            operation_ids.append(
                env.enqueue(
                    repository_id,
                    artifact_id=UUID(f"018f0f3e-7b0a-7c4{index}-8a9e-2e4b9f4d2c11"),
                    key=f"repo-{index}",
                )
            )

        peak = 0
        deadline = time.monotonic() + 8.0
        while time.monotonic() < deadline:
            running = env.connection.execute(
                "SELECT COUNT(*) AS count FROM repository_import_operations WHERE status = ?",
                (OperationStatus.RUNNING.value,),
            ).fetchone()
            peak = max(peak, int(running["count"]))
            if all(
                (op := env.store.get_operation(repo_id, op_id)) is not None
                and op.status in {OperationStatus.SUCCEEDED, OperationStatus.FAILED}
                for repo_id, op_id in zip(repositories, operation_ids, strict=True)
            ):
                break
            time.sleep(0.02)

        assert peak == 2
    finally:
        env.close()


@pytest.mark.serial
def test_context_load_failure_releases_reservation_and_in_flight(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    env = WorkerTestEnvironment(tmp_path, max_import_workers=2)
    env.pool.start()
    calls = {"count": 0}
    original = env.store.load_execution_context

    def _flaky_load(operation_id: UUID) -> ImportOperationExecutionContext | None:
        calls["count"] += 1
        if calls["count"] == 1:
            raise RuntimeError("forced context load failure")
        return original(operation_id)

    monkeypatch.setattr(env.store, "load_execution_context", _flaky_load)

    first_artifact = ARTIFACT_ID
    second_artifact = UUID("018f0f3e-7b0a-7c18-8a9e-2e4b9f4d2c11")
    first_operation = env.enqueue(REPOSITORY_ID, artifact_id=first_artifact, key="leak-1")
    second_operation = env.enqueue(REPOSITORY_ID, artifact_id=second_artifact, key="leak-2")

    env.wait_for_status(REPOSITORY_ID, first_operation, OperationStatus.FAILED, timeout=5.0)
    env.wait_for_status(REPOSITORY_ID, second_operation, OperationStatus.SUCCEEDED, timeout=5.0)

    assert env.locks.is_active(REPOSITORY_ID) is False
    first = env.store.get_operation(REPOSITORY_ID, first_operation)
    assert first is not None
    assert first.status == OperationStatus.FAILED
    env.close()


@pytest.mark.parametrize(
    ("point", "expected_code", "expect_private_ref"),
    [
        (ImportWorkerFaultPoint.AFTER_RUNNING_CLAIM, IMPORT_REJECTED_CODE, False),
        (ImportWorkerFaultPoint.AFTER_PACKAGE_EXTRACTED, IMPORT_REJECTED_CODE, False),
        (ImportWorkerFaultPoint.AFTER_PRIVATE_REF_CREATED, IMPORT_REJECTED_CODE, True),
        (ImportWorkerFaultPoint.AFTER_REPLAY_BEFORE_MARKER, IMPORT_REJECTED_CODE, True),
        (ImportWorkerFaultPoint.AFTER_MARKER_BEFORE_VERIFICATION, MANUAL_RECOVERY_REQUIRED_CODE, True),
        (
            ImportWorkerFaultPoint.AFTER_VERIFICATION_BEFORE_SECOND_MAIN_CHECK,
            MANUAL_RECOVERY_REQUIRED_CODE,
            True,
        ),
        (
            ImportWorkerFaultPoint.AFTER_SECOND_MAIN_CHECK_BEFORE_PUBLISH,
            MANUAL_RECOVERY_REQUIRED_CODE,
            True,
        ),
        (ImportWorkerFaultPoint.AFTER_MAIN_PUBLISH_BEFORE_SUCCEEDED, MANUAL_RECOVERY_REQUIRED_CODE, True),
        (ImportWorkerFaultPoint.AFTER_SUCCEEDED_BEFORE_PRIVATE_REF_CLEANUP, None, True),
        (ImportWorkerFaultPoint.AFTER_SUCCEEDED_BEFORE_ARTIFACT_CLEANUP, None, False),
    ],
)
def test_fault_injection_through_pool(
    tmp_path: Path,
    point: ImportWorkerFaultPoint,
    expected_code: str | None,
    expect_private_ref: bool,
) -> None:
    env = WorkerTestEnvironment(
        tmp_path,
        fault_injector=ConfigurableImportWorkerFaultInjector(points=frozenset({point})),
    )
    env.pool.start()
    try:
        operation_id = env.enqueue(REPOSITORY_ID, artifact_id=ARTIFACT_ID)
        if expected_code is None:
            env.wait_for_status(REPOSITORY_ID, operation_id, OperationStatus.SUCCEEDED)
        else:
            env.wait_for_status(REPOSITORY_ID, operation_id, OperationStatus.FAILED)
            operation = env.store.get_operation(REPOSITORY_ID, operation_id)
            assert operation is not None
            assert operation.error is not None
            assert operation.error.code == expected_code

        provider = env.provider_for(REPOSITORY_ID)
        private_ref = derive_private_ref_name(operation_id)
        if expect_private_ref:
            assert private_ref in provider.refs
        else:
            assert private_ref not in provider.refs
        assert artifact_ready_path(env.layout, REPOSITORY_ID, ARTIFACT_ID).exists()
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


def test_simple_error_sanitizes_dict_values() -> None:
    from gateway_repository_service.versioned_import.command import _simple_error

    error = _simple_error(
        "EXPECTED_COMMIT_MISMATCH",
        "mismatch",
        detail={
            "expected": "commit-0",
            "actual": "/root/data/gateway-import-abc",
        },
    )
    assert error.details is not None
    assert error.details["actual"] == "<path>"


def test_checkout_failure_maps_to_manual_with_private_ref_residual(
    worker_env: WorkerTestEnvironment,
) -> None:
    provider = worker_env.provider_for(REPOSITORY_ID)
    provider.fail_on_checkout = True
    operation_id = worker_env.enqueue(REPOSITORY_ID, artifact_id=ARTIFACT_ID)
    worker_env.wait_for_status(REPOSITORY_ID, operation_id, OperationStatus.FAILED)

    operation = worker_env.store.get_operation(REPOSITORY_ID, operation_id)
    assert operation is not None
    assert operation.error is not None
    assert operation.error.code == MANUAL_RECOVERY_REQUIRED_CODE
    private_ref = derive_private_ref_name(operation_id)
    assert private_ref in provider.refs


@pytest.mark.serial
def test_context_load_failure_logs_transition_rejection(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    import logging

    from gateway_repository_service.versioned_import.models import ImportOperationTransitionRejected

    env = WorkerTestEnvironment(tmp_path, max_import_workers=1)
    env.pool.start()
    try:
        def _fail_load(_operation_id: UUID) -> ImportOperationExecutionContext | None:
            raise RuntimeError("forced context load failure")

        def _reject_mark_failed(*_args: object, **_kwargs: object) -> None:
            raise ImportOperationTransitionRejected("not running")

        monkeypatch.setattr(env.store, "load_execution_context", _fail_load)
        monkeypatch.setattr(env.store, "mark_failed", _reject_mark_failed)

        with caplog.at_level(logging.ERROR):
            operation_id = env.enqueue(REPOSITORY_ID, artifact_id=ARTIFACT_ID, key="transition-reject")
            time.sleep(1.0)

        assert any(
            "status transition rejected" in record.message for record in caplog.records
        )
        operation = env.store.get_operation(REPOSITORY_ID, operation_id)
        assert operation is not None
        assert operation.status != OperationStatus.FAILED
    finally:
        env.close()


@pytest.mark.serial
def test_dispatcher_survives_storage_glitch(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import sqlite3

    env = WorkerTestEnvironment(tmp_path, max_import_workers=2)
    env.pool.start()
    calls = {"count": 0}
    original = env.store.has_unresolved_manual_barrier

    def _flaky_barrier(repository_id: UUID) -> bool:
        calls["count"] += 1
        if calls["count"] == 1:
            raise sqlite3.OperationalError("cannot start a transaction within a transaction")
        return original(repository_id)

    monkeypatch.setattr(env.store, "has_unresolved_manual_barrier", _flaky_barrier)

    try:
        operation_id = env.enqueue(REPOSITORY_ID, artifact_id=ARTIFACT_ID, key="dispatcher-survives")
        env.wait_for_status(REPOSITORY_ID, operation_id, OperationStatus.SUCCEEDED, timeout=10.0)
        assert env.pool._dispatcher is not None
        assert env.pool._dispatcher.is_alive()
    finally:
        env.close()


def test_sanitized_detail_preserves_readable_diagnostic_text() -> None:
    from gateway_repository_service.versioned_import.errors import sanitize_import_error_detail

    message = "update of main ref did not apply"
    sanitized = sanitize_import_error_detail(message)
    assert sanitized is not None
    assert "update" in sanitized
    assert "main" in sanitized


def test_sanitize_import_error_details_preserves_keys() -> None:
    from gateway_repository_service.versioned_import.errors import sanitize_import_error_details

    payload = {
        "a": {"b": "/root/data/gateway-import-abc"},
        "c": ["/tmp/secret", 7],
        "d": 5,
        "e": None,
    }
    sanitized = sanitize_import_error_details(payload)
    assert set(sanitized.keys()) == set(payload.keys())
    nested = sanitized["a"]
    assert isinstance(nested, dict)
    assert nested["b"] == "<path>"


def test_provider_stderr_not_persisted_raw(worker_env: WorkerTestEnvironment) -> None:
    from gateway_repository_service.versioned_import.command import _simple_error

    stderr = (
        "command failed: dolt sql exit=1 stderr=b'error: duplicate primary key 42; "
        "near INSERT INTO records VALUES (42)'"
    )
    error = _simple_error(IMPORT_REJECTED_CODE, "import rejected", detail=stderr)
    rendered = error.model_dump_json()
    assert "INSERT INTO" not in rendered
    assert "VALUES (42)" not in rendered
    assert "42" not in rendered
    assert "stderr=<redacted>" in rendered
