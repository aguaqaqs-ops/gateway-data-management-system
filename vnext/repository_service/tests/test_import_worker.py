"""Tests for durable Versioned import worker orchestration."""

from __future__ import annotations

import threading
import time
from collections.abc import Iterator
from pathlib import Path
from typing import cast
from uuid import UUID, uuid4

import pytest

from gateway_repository_contracts import (
    OperationStatus,
    RepositoryArtifactRef,
    SimpleError,
    UnknownTypePolicy,
    VerificationPolicy,
)
from gateway_repository_service.mutation_store import IdempotencyKeyHash, IdempotencyScope, MutationKind
from gateway_repository_service.upload_artifact.visibility import artifact_ready_path
from gateway_repository_service.versioned_import import versioned_import_fingerprint_v1
from gateway_repository_service.versioned_import.errors import ImportProviderError
from gateway_repository_service.versioned_import.faults import (
    ConfigurableImportWorkerFaultInjector,
    ImportWorkerFaultPoint,
    NoOpImportWorkerFaultInjector,
)
from gateway_repository_service.versioned_import.models import (
    MANUAL_RECOVERY_REQUIRED_CODE,
    ImportOperationExecutionContext,
    ImportRequestBinding,
    derive_private_ref_name,
)
from gateway_repository_service.arrow_mapping import CompiledTablePlan, ColumnCatalog, TableCatalog
from gateway_repository_service.versioned_import.verification import (
    IMPORT_REJECTED_CODE,
    VERIFICATION_FAILED_NOT_PUBLISHED_CODE,
    ImportVerificationError,
    verify_import_candidate,
)
from support.import_worker_harness import (
    DEFAULT_MAIN_COMMIT,
    MEDIA_TYPE,
    WorkerTestEnvironment,
)

REPOSITORY_ID = UUID("018f0f3e-7b0a-7c15-8a9e-2e4b9f4d2c11")
OTHER_REPOSITORY_ID = UUID("018f0f3e-7b0a-7c15-9a9e-2e4b9f4d2c11")
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


def test_failure_mapping_manual_recovery_on_replay_failure(
    worker_env: WorkerTestEnvironment,
) -> None:
    provider = worker_env.provider_for(REPOSITORY_ID)
    provider.fail_on_replay = True
    operation_id = worker_env.enqueue(REPOSITORY_ID, artifact_id=ARTIFACT_ID)
    worker_env.wait_for_status(REPOSITORY_ID, operation_id, OperationStatus.FAILED)

    operation = worker_env.store.get_operation(REPOSITORY_ID, operation_id)
    assert operation is not None
    assert operation.error is not None
    assert operation.error.code == MANUAL_RECOVERY_REQUIRED_CODE


def test_failure_mappers_agree_on_private_ref_evidence() -> None:
    from gateway_repository_service.versioned_import.command import (
        ExecutionEvidence,
        _map_provider_failure,
        _map_unknown_failure,
    )

    evidence = ExecutionEvidence(
        expected_commit_id="commit-main",
        main_before="commit-main",
        main_after_first_check="commit-main",
        private_ref_created=True,
    )
    provider_error = _map_provider_failure(evidence, detail="provider failure")
    unknown_error = _map_unknown_failure(evidence, detail="unknown failure")
    assert provider_error.code == MANUAL_RECOVERY_REQUIRED_CODE
    assert unknown_error.code == MANUAL_RECOVERY_REQUIRED_CODE
    assert provider_error.code == unknown_error.code


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


def test_dispatcher_rechecks_manual_barrier_when_claiming(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    env = WorkerTestEnvironment(tmp_path)
    try:
        barrier_operation = env.enqueue(
            REPOSITORY_ID,
            artifact_id=ARTIFACT_ID,
            operation_id=OPERATION_ID,
            key="barrier-race",
        )
        assert env.store.claim_if_queued(barrier_operation) is not None

        queued_artifact = UUID("018f0f3e-7b0a-7c18-8a9e-2e4b9f4d2c11")
        queued_operation = env.enqueue(
            REPOSITORY_ID,
            artifact_id=queued_artifact,
            key="stale-dispatch-candidate",
        )
        stale_candidates = env.store.list_earliest_queued_per_repository()
        assert [candidate[1] for candidate in stale_candidates] == [queued_operation]

        env.store.mark_failed(
            barrier_operation,
            error=SimpleError(
                code=MANUAL_RECOVERY_REQUIRED_CODE,
                message="manual",
                request_id=None,
            ),
        )
        monkeypatch.setattr(
            env.store,
            "list_earliest_queued_per_repository",
            lambda: stale_candidates,
        )

        assert env.pool._try_claim_one() is None
        queued = env.store.get_operation(REPOSITORY_ID, queued_operation)
        assert queued is not None
        assert queued.status == OperationStatus.QUEUED
    finally:
        env.close()


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
        with worker_env.store._lock:
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
            with env.store._lock:
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
            with env.store._lock:
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

    # Terminal status is committed inside the executor; reservation release is
    # the immediately following worker-finally step and may not yet be visible.
    deadline = time.monotonic() + 5.0
    while env.locks.is_active(REPOSITORY_ID) and time.monotonic() < deadline:
        time.sleep(0.01)
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
        (ImportWorkerFaultPoint.AFTER_PRIVATE_REF_CREATED, MANUAL_RECOVERY_REQUIRED_CODE, True),
        (ImportWorkerFaultPoint.AFTER_REPLAY_BEFORE_MARKER, MANUAL_RECOVERY_REQUIRED_CODE, True),
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
    original = env.store.list_earliest_queued_per_repository

    def _flaky_candidates() -> list[tuple[UUID, UUID, int]]:
        calls["count"] += 1
        if calls["count"] == 1:
            raise sqlite3.OperationalError("cannot start a transaction within a transaction")
        return original()

    monkeypatch.setattr(env.store, "list_earliest_queued_per_repository", _flaky_candidates)

    try:
        operation_id = env.enqueue(REPOSITORY_ID, artifact_id=ARTIFACT_ID, key="dispatcher-survives")
        env.wait_for_status(REPOSITORY_ID, operation_id, OperationStatus.SUCCEEDED, timeout=10.0)
        assert env.pool._dispatcher is not None
        assert env.pool._dispatcher.is_alive()
    finally:
        env.close()


def test_import_worker_pool_starts_exactly_one_dispatcher(tmp_path: Path) -> None:
    env = WorkerTestEnvironment(tmp_path, max_import_workers=2)
    env.pool.start()
    try:
        dispatcher = env.pool._dispatcher
        assert dispatcher is not None
        assert dispatcher.name == "import-worker-dispatcher"
        assert dispatcher.is_alive()
        env.pool.start()
        assert env.pool._dispatcher is dispatcher
        assert len(env.pool._workers) == 2
    finally:
        env.close()


@pytest.mark.serial
def test_dispatcher_idle_does_not_poll(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    env = WorkerTestEnvironment(tmp_path, max_import_workers=1)
    original = env.store.list_earliest_queued_per_repository
    query_times: list[float] = []
    query_lock = threading.Lock()
    original_wait = env.pool._notify.wait

    def _counting_list() -> list[tuple[UUID, UUID, int]]:
        with query_lock:
            query_times.append(time.monotonic())
        return original()

    def _wait_without_idle_timeout(timeout: float | None = None) -> bool:
        assert timeout is None
        return original_wait(timeout=timeout)

    monkeypatch.setattr(env.store, "list_earliest_queued_per_repository", _counting_list)
    monkeypatch.setattr(env.pool._notify, "wait", _wait_without_idle_timeout)
    env.pool.start()
    try:
        deadline = time.monotonic() + 2.0
        while time.monotonic() < deadline:
            with query_lock:
                if query_times:
                    break
            time.sleep(0.01)
        with query_lock:
            assert query_times
            baseline = len(query_times)
        time.sleep(0.5)
        with query_lock:
            assert len(query_times) == baseline
        operation_id = env.enqueue(REPOSITORY_ID, artifact_id=ARTIFACT_ID, key="idle-wake")
        env.wait_for_status(REPOSITORY_ID, operation_id, OperationStatus.SUCCEEDED, timeout=10.0)
        with query_lock:
            assert len(query_times) > baseline
    finally:
        env.close()


@pytest.mark.serial
def test_notification_generation_prevents_lost_wakeup(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    env = WorkerTestEnvironment(tmp_path, max_import_workers=1)
    original = env.store.list_earliest_queued_per_repository
    entered_query = threading.Event()
    release_query = threading.Event()
    calls = {"count": 0}
    wait_timeouts: list[float | None] = []
    original_wait = env.pool._notify.wait

    def _gated_list() -> list[tuple[UUID, UUID, int]]:
        calls["count"] += 1
        if calls["count"] == 1:
            entered_query.set()
            assert release_query.wait(timeout=5.0)
            return []
        return original()

    def _record_wait(timeout: float | None = None) -> bool:
        wait_timeouts.append(timeout)
        return original_wait(timeout=timeout)

    monkeypatch.setattr(env.store, "list_earliest_queued_per_repository", _gated_list)
    monkeypatch.setattr(env.pool._notify, "wait", _record_wait)
    env.pool.start()
    try:
        assert entered_query.wait(timeout=5.0)
        operation_id = env.enqueue(
            REPOSITORY_ID,
            artifact_id=ARTIFACT_ID,
            key="lost-wakeup",
        )
        release_query.set()
        env.wait_for_status(REPOSITORY_ID, operation_id, OperationStatus.SUCCEEDED, timeout=10.0)
        assert all(timeout is None for timeout in wait_timeouts)
        assert calls["count"] >= 2
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


@pytest.mark.serial
def test_manual_barrier_allows_other_repository_to_succeed(worker_env: WorkerTestEnvironment) -> None:
    blocked_id = worker_env.enqueue(
        REPOSITORY_ID,
        artifact_id=ARTIFACT_ID,
        operation_id=OPERATION_ID,
        key="blocked-repo",
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

    other_artifact = UUID("018f0f3e-7b0a-7c18-8a9e-2e4b9f4d2c11")
    other_operation = worker_env.enqueue(
        OTHER_REPOSITORY_ID,
        artifact_id=other_artifact,
        key="other-repo",
    )
    worker_env.wait_for_status(
        OTHER_REPOSITORY_ID,
        other_operation,
        OperationStatus.SUCCEEDED,
        timeout=10.0,
    )


@pytest.mark.serial
def test_dispatcher_and_mutation_store_do_not_nested_transaction(tmp_path: Path) -> None:
    env = WorkerTestEnvironment(tmp_path)
    errors: list[BaseException] = []
    barrier = threading.Barrier(2)

    def claim_worker() -> None:
        try:
            barrier.wait()
            binding = ImportRequestBinding(
                repository_id=REPOSITORY_ID,
                artifact_ref=RepositoryArtifactRef(
                    artifact_id=uuid4(),
                    media_type=MEDIA_TYPE,
                    size_bytes=1,
                    raw_sha256="a" * 64,
                ),
                target_ref="main",
                expected_commit_id="commit-main",
                verification_policy=VerificationPolicy.STRUCTURAL,
                unknown_type_policy=UnknownTypePolicy.REJECT,
            )
            key_hash = IdempotencyKeyHash.from_raw_key(f"nested-{uuid4()}")
            fingerprint = versioned_import_fingerprint_v1(binding=binding, key_hash=key_hash)
            env.store.claim_or_enqueue(binding, key_hash=key_hash, fingerprint=fingerprint)
        except BaseException as exc:
            errors.append(exc)

    def mutation_worker() -> None:
        try:
            barrier.wait()
            scope = IdempotencyScope(
                mutation_kind=MutationKind.CREATE_REPOSITORY,
                repository_id=None,
            )
            key_hash = IdempotencyKeyHash.from_raw_key(f"create-{uuid4()}")
            env.mutation_store.claim_or_lookup(
                scope,
                key_hash=key_hash,
                fingerprint=b"create-fingerprint",
            )
        except BaseException as exc:
            errors.append(exc)

    threads = [
        threading.Thread(target=claim_worker),
        threading.Thread(target=mutation_worker),
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    env.close()
    assert errors == []


@pytest.mark.serial
def test_repository_lock_eviction_preserves_mutual_exclusion() -> None:
    from gateway_repository_service.versioned_import.locks import RepositoryLockRegistry

    registry = RepositoryLockRegistry(max_repository_lock_entries=2)
    repository_ids = (
        UUID("018f0f3e-7b0a-7c15-8a9e-2e4b9f4d2c11"),
        UUID("018f0f3e-7b0a-7c15-8a9e-2e4b9f4d2c12"),
        UUID("018f0f3e-7b0a-7c15-8a9e-2e4b9f4d2c13"),
    )
    for repository_id in repository_ids:
        assert registry.try_reserve(repository_id)
        with registry.repository_execution(repository_id):
            pass
        registry.release_reservation(repository_id)

    target = repository_ids[0]
    counter = 0
    max_concurrent = 0
    counter_lock = threading.Lock()
    barrier = threading.Barrier(2)
    errors: list[BaseException] = []

    def worker() -> None:
        nonlocal counter, max_concurrent
        try:
            barrier.wait()
            with registry.repository_execution(target):
                with counter_lock:
                    counter += 1
                    max_concurrent = max(max_concurrent, counter)
                time.sleep(0.05)
                with counter_lock:
                    counter -= 1
        except BaseException as exc:
            errors.append(exc)

    threads = [threading.Thread(target=worker), threading.Thread(target=worker)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert errors == []
    assert max_concurrent == 1


@pytest.mark.serial
def test_repository_lock_does_not_block_other_repositories() -> None:
    from gateway_repository_service.versioned_import.locks import RepositoryLockRegistry

    registry = RepositoryLockRegistry()
    repo_a = UUID("018f0f3e-7b0a-7c15-8a9e-2e4b9f4d2c11")
    repo_b = UUID("018f0f3e-7b0a-7c15-8a9e-2e4b9f4d2c12")
    a_holding = threading.Event()
    a_can_release = threading.Event()
    errors: list[BaseException] = []

    def hold_repo_a() -> None:
        try:
            with registry.repository_execution(repo_a):
                a_holding.set()
                assert a_can_release.wait(timeout=5.0)
                time.sleep(0.05)
        except BaseException as exc:
            errors.append(exc)

    thread_a = threading.Thread(target=hold_repo_a)
    thread_a.start()
    assert a_holding.wait(timeout=5.0)

    start = time.monotonic()
    with registry.repository_execution(repo_b):
        elapsed = time.monotonic() - start
    a_can_release.set()
    thread_a.join(timeout=5.0)

    assert errors == []
    assert elapsed < 0.5


@pytest.mark.serial
def test_worker_rejects_when_import_disk_admission_fails(tmp_path: Path) -> None:
    from unittest.mock import patch

    from gateway_repository_service.capacity import CapacityAdmissionError

    env = WorkerTestEnvironment(tmp_path)
    try:
        repository_id = UUID("018f0f3e-7b0a-7c15-8a9e-2e4b9f4d2c11")
        artifact_id = UUID("018f0f3e-7b0a-7c16-8a9e-2e4b9f4d2c11")
        operation_id = env.enqueue(repository_id, artifact_id=artifact_id)
        with patch(
            "gateway_repository_service.versioned_import.command.assert_import_disk_admission",
            side_effect=CapacityAdmissionError("disk admission denied"),
        ):
            env.pool.start()
            env.pool.notify()
            env.wait_for_status(repository_id, operation_id, OperationStatus.FAILED, timeout=5.0)
        operation = env.store.get_operation(repository_id, operation_id)
        assert operation is not None
        assert operation.error is not None
        assert operation.error.code == "IMPORT_REJECTED"
        provider = env.provider_for(repository_id)
        assert provider.replay_order == []
        assert provider.markers == {}
    finally:
        env.close()


@pytest.mark.unit
@pytest.mark.parametrize(
    ("wrapper_cancelled", "caller_cancelled", "has_caller"),
    [
        (False, False, True),
        (True, False, True),
        (False, True, True),
        (True, True, True),
        (False, False, False),
        (True, False, False),
    ],
)
def test_cancellable_provider_wrapper_merges_replay_cancellation(
    wrapper_cancelled: bool,
    caller_cancelled: bool,
    has_caller: bool,
) -> None:
    from unittest.mock import MagicMock

    from gateway_repository_service.versioned_import.ports import CancellationCallback
    from gateway_repository_service.versioned_import.worker import _CancellableProviderWrapper

    inner = MagicMock()
    received: list[CancellationCallback] = []

    def _record_replay(
        _private_ref: str,
        _replay_path: object,
        cancellation: CancellationCallback | None = None,
    ) -> None:
        assert cancellation is not None
        received.append(cancellation)

    inner.replay_sql.side_effect = _record_replay
    wrapper = _CancellableProviderWrapper(inner, lambda: wrapper_cancelled)

    caller: CancellationCallback | None = (lambda: caller_cancelled) if has_caller else None
    wrapper.replay_sql("private-ref", Path("replay.sql"), cancellation=caller)

    assert len(received) == 1
    assert received[0]() is (wrapper_cancelled or (caller_cancelled if has_caller else False))


@pytest.mark.unit
def test_cancellable_provider_wrapper_propagates_caller_cancellation_exception() -> None:
    from unittest.mock import MagicMock

    from gateway_repository_service.versioned_import.ports import CancellationCallback
    from gateway_repository_service.versioned_import.worker import _CancellableProviderWrapper

    inner = MagicMock()
    received: list[CancellationCallback | None] = []

    def _record_replay(
        _private_ref: str,
        _replay_path: object,
        cancellation: CancellationCallback | None = None,
    ) -> None:
        received.append(cancellation)
        assert cancellation is not None
        cancellation()

    inner.replay_sql.side_effect = _record_replay
    wrapper = _CancellableProviderWrapper(inner, lambda: False)

    def _boom() -> bool:
        raise RuntimeError("caller callback failed")

    with pytest.raises(RuntimeError, match="caller callback failed"):
        wrapper.replay_sql("private-ref", Path("replay.sql"), cancellation=_boom)
    assert len(received) == 1


@pytest.mark.serial
def test_import_worker_pool_partial_start_joins_started_threads(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    env = WorkerTestEnvironment(tmp_path, max_import_workers=2)
    started: list[threading.Thread] = []
    original_start = threading.Thread.start

    def flaky_start(self: threading.Thread) -> None:
        if len(started) >= 2:
            raise RuntimeError("forced thread start failure")
        original_start(self)
        started.append(self)

    monkeypatch.setattr(threading.Thread, "start", flaky_start)
    with pytest.raises(RuntimeError, match="forced thread start failure"):
        env.pool.start()

    deadline = time.monotonic() + 5.0
    while time.monotonic() < deadline:
        if all(not thread.is_alive() for thread in started):
            break
        time.sleep(0.01)
    else:
        raise AssertionError("partially started import worker threads were not joined")

    assert env.pool._dispatcher is None
    assert env.pool._workers == []
    env.close()


@pytest.mark.unit
def test_full_scan_deadline_is_cumulative(monkeypatch: pytest.MonkeyPatch) -> None:
    import pyarrow as pa  # type: ignore[import-untyped]

    from test_import_verification import manifest_from_tables

    from gateway_repository_service.versioned_import.ports import (
        CallTimeoutCallback,
        CancellationCallback,
        VersionedImportProvider,
    )

    times = iter([0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 11.0])
    monkeypatch.setattr(time, "monotonic", lambda: next(times, 100.0))

    columns = (ColumnCatalog("id", "BIGINT", False, 1),)
    catalog = (
        TableCatalog("t1", columns, 1),
        TableCatalog("t2", columns, 1),
    )
    manifest = manifest_from_tables(catalog)
    recorded_timeouts: list[float] = []
    streamed_tables: list[str] = []

    class _Provider:
        def read_catalog(
            self,
            candidate: str,
            *,
            cancellation: CancellationCallback | None = None,
            call_timeout: CallTimeoutCallback | None = None,
        ) -> tuple[TableCatalog, ...]:
            del candidate, cancellation
            if call_timeout is not None:
                recorded_timeouts.append(call_timeout(30.0))
            return catalog

        def stream_table(
            self,
            candidate: str,
            table: TableCatalog,
            policy: UnknownTypePolicy,
            *,
            table_plan: object = None,
            cancellation: CancellationCallback | None = None,
            call_timeout: CallTimeoutCallback | None = None,
        ) -> Iterator[pa.RecordBatch]:
            del candidate, policy, table_plan, cancellation
            streamed_tables.append(table.name)
            if call_timeout is not None:
                recorded_timeouts.append(call_timeout(3600.0))
            yield pa.record_batch({"id": pa.array([1], type=pa.int64())})

    provider = cast(VersionedImportProvider, _Provider())

    with pytest.raises(ImportVerificationError) as exc_info:
        verify_import_candidate(
            provider,
            candidate="candidate-1",
            manifest=manifest,
            verification_policy=VerificationPolicy.FULL_SCAN,
            unknown_type_policy=UnknownTypePolicy.STRINGIFY,
            full_scan_timeout_seconds=10,
        )

    assert exc_info.value.code == VERIFICATION_FAILED_NOT_PUBLISHED_CODE
    assert recorded_timeouts == [10.0, 10.0]
    assert streamed_tables == ["t1"]


@pytest.mark.unit
def test_full_scan_deadline_covers_plan_compilation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from test_import_verification import manifest_from_tables

    from gateway_repository_service.versioned_import import verification as verification_module
    from gateway_repository_service.versioned_import.ports import VersionedImportProvider

    clock = [0.0]
    monkeypatch.setattr(time, "monotonic", lambda: clock[0])
    catalog = (
        TableCatalog(
            "records",
            (ColumnCatalog("id", "BIGINT", False, 1),),
            0,
        ),
    )

    class _Provider:
        def read_catalog(self, *_args: object, **_kwargs: object) -> tuple[TableCatalog, ...]:
            return catalog

        def stream_table(self, *_args: object, **_kwargs: object) -> Iterator[object]:
            raise AssertionError("deadline exhaustion must prevent table streaming")

    original_compile = verification_module._compile_table_plans

    def _compile_after_deadline(
        actual_catalog: tuple[TableCatalog, ...],
        policy: UnknownTypePolicy,
    ) -> dict[str, CompiledTablePlan]:
        plans = original_compile(actual_catalog, policy)
        clock[0] = 11.0
        return plans

    monkeypatch.setattr(verification_module, "_compile_table_plans", _compile_after_deadline)

    with pytest.raises(ImportVerificationError) as exc_info:
        verify_import_candidate(
            cast(VersionedImportProvider, _Provider()),
            candidate="candidate-1",
            manifest=manifest_from_tables(catalog),
            verification_policy=VerificationPolicy.FULL_SCAN,
            unknown_type_policy=UnknownTypePolicy.STRINGIFY,
            full_scan_timeout_seconds=10,
        )

    assert exc_info.value.code == VERIFICATION_FAILED_NOT_PUBLISHED_CODE


def _wait_until_pid_reaped(pid: int, *, timeout_seconds: float = 5.0) -> None:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        if not Path(f"/proc/{pid}").exists():
            return
        time.sleep(0.02)
    raise AssertionError(f"process {pid} was not reaped")


@pytest.mark.integration
@pytest.mark.serial
def test_full_scan_timeout_cancels_and_reaps(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from gateway_repository_service.candidate_a.dolt_cli import write_query
    from gateway_repository_service.layout import DurableLayout
    from gateway_repository_service.process import DoltRunner
    from gateway_repository_service.versioned_import.provider import CandidateAImportProvider
    from test_import_verification import manifest_from_tables
    from support.lifecycle_harness import lifecycle_settings

    import subprocess
    from typing import BinaryIO

    settings = lifecycle_settings(tmp_path)
    layout = DurableLayout.create_for_probe(settings.data_root)
    repository = layout.staging_artifacts / "full-scan-deadline-repo"
    repository.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(DoltRunner, "_validate_version", lambda self: None)
    runner = DoltRunner(settings, layout.root)
    runner.run(
        "init",
        [
            "init",
            f"--name={settings.author_name}",
            f"--email={settings.author_email}",
            "--initial-branch=main",
        ],
        cwd=repository,
        timeout=settings.metadata_timeout_seconds,
    )
    values = ", ".join(f"({index})" for index in range(8192))
    setup_sql = write_query(
        layout.staging_artifacts,
        (
            "CREATE TABLE stream_probe (id BIGINT NOT NULL PRIMARY KEY);\n"
            f"INSERT INTO stream_probe (id) VALUES {values};\n"
        ),
    )
    runner.run(
        "setup_probe",
        ["sql", "--result-format=csv"],
        cwd=repository,
        timeout=settings.import_timeout_seconds,
        stdin_path=setup_sql,
    )
    setup_sql.unlink(missing_ok=True)
    runner.run(
        "commit_probe",
        ["commit", "-Am", "probe"],
        cwd=repository,
        timeout=settings.metadata_timeout_seconds,
    )
    provider = CandidateAImportProvider(settings, layout, repository, runner)
    candidate = provider.read_ref("main")

    columns = (ColumnCatalog("id", "BIGINT", False, 1),)
    catalog = (TableCatalog("stream_probe", columns, 8192),)
    manifest = manifest_from_tables(catalog)

    clock = [0.0]

    def fake_monotonic() -> float:
        return clock[0]

    monkeypatch.setattr(time, "monotonic", fake_monotonic)

    observed_pids: list[int] = []
    original_start = DoltRunner._start

    def tracking_start(
        self: DoltRunner,
        command_kind: str,
        args: list[str],
        *,
        cwd: Path,
        stdin_path: Path | None = None,
        stdout_target: BinaryIO | int | None = None,
        owner: object | None = None,
    ) -> tuple[subprocess.Popen[bytes], BinaryIO | None]:
        process, stdin_handle = original_start(
            self,
            command_kind,
            args,
            cwd=cwd,
            stdin_path=stdin_path,
            stdout_target=stdout_target,
            owner=owner,
        )
        if command_kind == "row_stream":
            clock[0] = 5.0
            if process.poll() is None:
                observed_pids.append(process.pid)
        return process, stdin_handle

    monkeypatch.setattr(DoltRunner, "_start", tracking_start)

    query_files_before = list(layout.staging_artifacts.glob("query-*.sql"))

    with pytest.raises(ImportVerificationError) as exc_info:
        verify_import_candidate(
            provider,
            candidate=candidate,
            manifest=manifest,
            verification_policy=VerificationPolicy.FULL_SCAN,
            unknown_type_policy=UnknownTypePolicy.STRINGIFY,
            full_scan_timeout_seconds=1,
        )

    assert exc_info.value.code == VERIFICATION_FAILED_NOT_PUBLISHED_CODE
    assert observed_pids
    for pid in observed_pids:
        _wait_until_pid_reaped(pid)
    query_files_after = list(layout.staging_artifacts.glob("query-*.sql"))
    assert query_files_after == query_files_before


@pytest.mark.unit
def test_cancellable_provider_wrapper_merges_catalog_cancellation() -> None:
    from unittest.mock import MagicMock

    from gateway_repository_service.versioned_import.ports import CancellationCallback
    from gateway_repository_service.versioned_import.worker import _CancellableProviderWrapper

    inner = MagicMock()
    received: list[CancellationCallback | None] = []

    def _record_catalog(
        _candidate: str,
        *,
        cancellation: CancellationCallback | None = None,
        call_timeout: object = None,
    ) -> tuple[object, ...]:
        del call_timeout
        received.append(cancellation)
        return ()

    inner.read_catalog.side_effect = _record_catalog
    wrapper = _CancellableProviderWrapper(inner, lambda: True)
    wrapper.read_catalog("candidate-1", cancellation=lambda: False)
    assert len(received) == 1
    assert received[0] is not None
    assert received[0]() is True
