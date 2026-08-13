"""Graceful shutdown tests for Versioned import workers."""

from __future__ import annotations

import threading
import time
from pathlib import Path
from uuid import UUID

import pytest

from gateway_repository_contracts import OperationStatus
from gateway_repository_service.runtime import ServiceRuntime
from gateway_repository_service.versioned_import.errors import ImportProviderError
from gateway_repository_service.versioned_import.ports import CancellationCallback
from gateway_repository_service.versioned_import.worker import ImportWorkerPool, ImportWorkerShutdownError
from support.import_worker_harness import WorkerTestEnvironment

REPOSITORY_ID = UUID("018f0f3e-7b0a-7c15-8a9e-2e4b9f4d2c11")
ARTIFACT_ID = UUID("018f0f3e-7b0a-7c16-8a9e-2e4b9f4d2c11")


@pytest.mark.serial
def test_worker_threads_are_not_daemon(tmp_path: Path) -> None:
    env = WorkerTestEnvironment(tmp_path, max_import_workers=1)
    env.pool.start()
    try:
        assert env.pool._dispatcher is not None
        assert env.pool._dispatcher.daemon is False
        assert env.pool._workers
        assert all(not worker.daemon for worker in env.pool._workers)
    finally:
        env.close()


@pytest.mark.serial
def test_shutdown_stops_claim_and_preserves_running(tmp_path: Path) -> None:
    env = WorkerTestEnvironment(tmp_path, max_import_workers=1)
    provider = env.provider_for(REPOSITORY_ID)
    replay_started = threading.Event()
    shutdown_ready = threading.Event()

    def _blocking_replay(
        private_ref: str,
        replay_path: Path,
        cancellation: CancellationCallback | None = None,
    ) -> None:
        replay_started.set()
        shutdown_ready.wait(timeout=5.0)
        if cancellation is not None and cancellation():
            raise RuntimeError("cancelled")
        time.sleep(0.5)

    provider.replay_sql = _blocking_replay  # type: ignore[method-assign]
    env.pool.start()
    try:
        operation_id = env.enqueue(REPOSITORY_ID, artifact_id=ARTIFACT_ID)
        assert replay_started.wait(timeout=5.0)
        operation = env.store.get_operation(REPOSITORY_ID, operation_id)
        assert operation is not None
        assert operation.status == OperationStatus.RUNNING

        env.pool.begin_shutdown()
        shutdown_ready.set()
        assert env.pool._try_claim_one() is None
        time.sleep(0.2)
        operation = env.store.get_operation(REPOSITORY_ID, operation_id)
        assert operation is not None
        assert operation.status == OperationStatus.RUNNING
        assert operation.error is None
    finally:
        shutdown_ready.set()
        env.close()


@pytest.mark.serial
def test_stop_reports_join_timeout(tmp_path: Path) -> None:
    env = WorkerTestEnvironment(
        tmp_path,
        max_import_workers=1,
    )
    env.settings = env.settings.model_copy(update={"import_shutdown_grace_seconds": 0.05})
    env.pool = ImportWorkerPool(
        settings=env.settings,
        layout=env.layout,
        store=env.store,
        provider_factory=env._provider_factory,
        locks=env.locks,
    )
    env.pool.start()
    blocker = threading.Event()

    def _block_replay(
        _private_ref: str,
        _replay_path: Path,
        cancellation: CancellationCallback | None = None,
    ) -> None:
        del cancellation
        blocker.wait(timeout=5.0)

    provider = env.provider_for(REPOSITORY_ID)
    provider.replay_sql = _block_replay  # type: ignore[assignment]
    env.enqueue(REPOSITORY_ID, artifact_id=ARTIFACT_ID)
    time.sleep(0.2)
    with pytest.raises(ImportWorkerShutdownError):
        env.pool.stop(timeout=0.05)
    blocker.set()
    env.pool.stop(timeout=2.0)


@pytest.mark.serial
def test_shutdown_preserves_running_when_replay_cancelled(tmp_path: Path) -> None:
    env = WorkerTestEnvironment(
        tmp_path,
        max_import_workers=1,
    )
    provider = env.provider_for(REPOSITORY_ID)
    replay_started = threading.Event()
    release_replay = threading.Event()

    def _blocking_replay(
        private_ref: str,
        replay_path: Path,
        cancellation: CancellationCallback | None = None,
    ) -> None:
        del private_ref, replay_path
        replay_started.set()
        release_replay.wait(timeout=5.0)
        if cancellation is not None and cancellation():
            raise ImportProviderError("import replay cancelled during shutdown")

    provider.replay_sql = _blocking_replay  # type: ignore[method-assign]
    env.pool.start()
    try:
        operation_id = env.enqueue(REPOSITORY_ID, artifact_id=ARTIFACT_ID)
        assert replay_started.wait(timeout=5.0)
        env.pool.begin_shutdown()
        env.pool.cancel_active_operations()
        release_replay.set()
        time.sleep(0.3)
        operation = env.store.get_operation(REPOSITORY_ID, operation_id)
        assert operation is not None
        assert operation.status == OperationStatus.RUNNING
        assert operation.error is None
    finally:
        release_replay.set()
        env.close()


@pytest.mark.serial
def test_runtime_shutdown_preserves_running_during_active_import(tmp_path: Path) -> None:
    stopping = threading.Event()
    env = WorkerTestEnvironment(
        tmp_path,
        max_import_workers=1,
    )
    env.settings = env.settings.model_copy(update={"import_shutdown_grace_seconds": 0.1})
    env.pool = ImportWorkerPool(
        settings=env.settings,
        layout=env.layout,
        store=env.store,
        provider_factory=env._provider_factory,
        locks=env.locks,
        shutdown_event=stopping,
    )
    provider = env.provider_for(REPOSITORY_ID)
    replay_started = threading.Event()
    release_replay = threading.Event()

    def _blocking_replay(
        private_ref: str,
        replay_path: Path,
        cancellation: CancellationCallback | None = None,
    ) -> None:
        del private_ref, replay_path
        replay_started.set()
        release_replay.wait(timeout=5.0)
        if cancellation is not None and cancellation():
            raise ImportProviderError("import replay cancelled during shutdown")

    provider.replay_sql = _blocking_replay  # type: ignore[method-assign]
    env.pool.start()
    try:
        operation_id = env.enqueue(REPOSITORY_ID, artifact_id=ARTIFACT_ID)
        assert replay_started.wait(timeout=5.0)
        stopping.set()
        env.pool.begin_shutdown()
        if not env.pool.wait_for_quiescence(timeout=env.settings.import_shutdown_grace_seconds):
            env.pool.cancel_active_operations()
        release_replay.set()
        env.pool.stop(timeout=2.0)
        operation = env.store.get_operation(REPOSITORY_ID, operation_id)
        assert operation is not None
        assert operation.status == OperationStatus.RUNNING
        assert operation.error is None
    finally:
        release_replay.set()
        env.close()


@pytest.mark.serial
@pytest.mark.integration
def test_runtime_shutdown_closes_cleanly(tmp_path: Path) -> None:
    from gateway_repository_service.locking import DurableRootLock

    settings = WorkerTestEnvironment(tmp_path).settings.model_copy(
        update={"import_shutdown_grace_seconds": 0.5}
    )
    runtime = ServiceRuntime.start(settings)
    lock_path = runtime.layout.service_lock
    try:
        assert runtime.is_ready()
        assert runtime.is_accepting_import_effects()
    finally:
        runtime.shutdown()
    assert not runtime.control_store.is_open()
    assert not runtime.root_lock.is_held()
    with DurableRootLock(lock_path):
        pass


@pytest.mark.serial
@pytest.mark.integration
def test_runtime_shutdown_retains_ownership_when_worker_hangs(tmp_path: Path) -> None:
    import time

    from gateway_repository_contracts import RepositoryArtifactRef, UnknownTypePolicy, VerificationPolicy
    from gateway_repository_service.mutation_store import IdempotencyKeyHash
    from gateway_repository_service.runtime import ServiceRuntime
    from gateway_repository_service.upload_artifact.visibility import artifact_ready_path
    from gateway_repository_service.versioned_import import ImportRequestBinding, versioned_import_fingerprint_v1
    from gateway_repository_service.versioned_import.worker import ImportWorkerShutdownError
    from support.import_worker_harness import FakeImportProvider, MEDIA_TYPE
    from support.lifecycle_harness import lifecycle_settings
    from test_import_package import build_package_bytes, write_artifact

    settings = lifecycle_settings(tmp_path).model_copy(
        update={"import_shutdown_grace_seconds": 0.05, "max_import_workers": 1}
    )
    runtime = ServiceRuntime.start(settings)
    provider = FakeImportProvider()
    blocker = threading.Event()

    def _hanging_replay(
        _private_ref: str,
        _replay_path: Path,
        cancellation: CancellationCallback | None = None,
    ) -> None:
        del cancellation
        blocker.wait(timeout=5.0)

    provider.replay_sql = _hanging_replay  # type: ignore[assignment]
    runtime.import_worker_pool._provider_factory = lambda _rid: provider

    ready_path = artifact_ready_path(runtime.layout, REPOSITORY_ID, ARTIFACT_ID)
    ready_path.parent.mkdir(parents=True, exist_ok=True)
    size_bytes, raw_sha256 = write_artifact(ready_path, build_package_bytes())
    now = "2026-08-06T00:00:00+00:00"
    with runtime.import_store._lock:
        runtime.import_store.mutation_store._connection.execute(
            """
            INSERT INTO artifact_lifecycle (
                artifact_id, repository_scope, media_type, size_bytes, raw_sha256, created_at, updated_at
            , cleanup_seq) VALUES (?, ?, ?, ?, ?, ?, ?, (SELECT COALESCE(MAX(cleanup_seq), 0) + 1 FROM artifact_lifecycle))
            """,
            (str(ARTIFACT_ID), REPOSITORY_ID.hex, MEDIA_TYPE, size_bytes, raw_sha256, now, now),
        )
        runtime.import_store.mutation_store._connection.commit()

    binding = ImportRequestBinding(
        repository_id=REPOSITORY_ID,
        artifact_ref=RepositoryArtifactRef(
            artifact_id=ARTIFACT_ID,
            media_type=MEDIA_TYPE,
            size_bytes=size_bytes,
            raw_sha256=raw_sha256,
        ),
        target_ref="main",
        expected_commit_id=provider.read_ref("main"),
        verification_policy=VerificationPolicy.STRUCTURAL,
        unknown_type_policy=UnknownTypePolicy.REJECT,
    )
    key_hash = IdempotencyKeyHash.from_raw_key("shutdown-hang")
    fingerprint = versioned_import_fingerprint_v1(binding=binding, key_hash=key_hash)
    runtime.import_store.claim_or_enqueue(
        binding,
        key_hash=key_hash,
        fingerprint=fingerprint,
    )
    runtime.import_worker_pool.notify()
    time.sleep(0.2)
    try:
        with pytest.raises(ExceptionGroup) as exc_info:
            runtime.shutdown()
        assert any(
            isinstance(exc, ImportWorkerShutdownError) for exc in exc_info.value.exceptions
        )
        assert runtime.control_store.is_open()
        assert runtime.root_lock.is_held()
        # Alive worker handles must remain so a later stop can retry join.
        assert any(worker.is_alive() for worker in runtime.import_worker_pool._workers)
    finally:
        blocker.set()
        try:
            runtime.import_worker_pool.stop(timeout=5.0)
        except Exception:
            pass
        if runtime.control_store.is_open():
            runtime.control_store.close()
        if runtime.root_lock.is_held():
            runtime.root_lock.release()


@pytest.mark.serial
@pytest.mark.integration
def test_runtime_shutdown_propagates_bridge_shutdown_error_after_releasing_resources(
    tmp_path: Path,
) -> None:
    from gateway_repository_contracts import UnknownTypePolicy
    from gateway_repository_service.arrow_mapping import ColumnCatalog, TableCatalog, compile_table_plan
    from gateway_repository_service.locking import DurableRootLock
    from gateway_repository_service.versioned_read.arrow_bridge import (
        BRIDGE_REGISTRY,
        ArrowIpcStreamBridge,
        BridgeShutdownError,
    )
    from support.lifecycle_harness import lifecycle_settings

    worker_finish_release = threading.Event()
    bridge: ArrowIpcStreamBridge | None = None
    runtime: ServiceRuntime | None = None
    try:
        settings = lifecycle_settings(tmp_path).model_copy(
            update={"import_shutdown_grace_seconds": 1.0}
        )
        runtime = ServiceRuntime.start(settings)
        lock_path = runtime.layout.service_lock

        table = TableCatalog(
            "items",
            (
                ColumnCatalog(
                    name="id",
                    sql_type="BIGINT",
                    nullable=False,
                    primary_key_position=1,
                ),
            ),
            row_count=1,
        )
        plan = compile_table_plan(table, UnknownTypePolicy.REJECT)
        batch = plan.record_batch([plan.normalize_row((1,))])

        ArrowIpcStreamBridge._test_worker_finish_barrier = worker_finish_release
        bridge = ArrowIpcStreamBridge(plan, iter([batch]), threading.Event())
        assert bridge in BRIDGE_REGISTRY.snapshot()

        deadline = time.monotonic() + 2.0
        while time.monotonic() < deadline:
            if bridge.is_worker_alive() and not bridge._worker_finished:
                break
            time.sleep(0.01)
        else:
            raise AssertionError("bridge worker did not reach finish barrier")

        with pytest.raises(BridgeShutdownError) as exc_info:
            runtime.shutdown()

        assert exc_info.value.failures or exc_info.value.survivor_count
        assert not runtime.control_store.is_open()
        assert not runtime.root_lock.is_held()
        with DurableRootLock(lock_path):
            pass
    finally:
        worker_finish_release.set()
        ArrowIpcStreamBridge._test_worker_finish_barrier = None
        if bridge is not None:
            if bridge.is_worker_alive():
                bridge._worker.join(timeout=5.0)
            try:
                BRIDGE_REGISTRY.unregister(bridge)
            except Exception:
                pass
            if bridge in BRIDGE_REGISTRY.snapshot():
                try:
                    BRIDGE_REGISTRY.close_all(
                        runtime.dolt_runner if runtime is not None else None,
                        join_timeout_seconds=30.0,
                    )
                except BridgeShutdownError:
                    pass
        if runtime is not None:
            try:
                runtime.dolt_runner.terminate_active_children()
            except Exception:
                pass
            try:
                if runtime.control_store.is_open():
                    runtime.control_store.close()
            except Exception:
                pass
            try:
                if runtime.root_lock.is_held():
                    runtime.root_lock.release()
            except Exception:
                pass
            assert BRIDGE_REGISTRY.snapshot() == ()
            assert runtime.dolt_runner._active_children.snapshot() == ()
        if bridge is not None:
            assert not bridge.is_worker_alive()
