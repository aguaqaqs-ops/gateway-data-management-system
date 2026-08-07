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
    settings = WorkerTestEnvironment(tmp_path).settings.model_copy(
        update={"import_shutdown_grace_seconds": 0.5}
    )
    runtime = ServiceRuntime.start(settings)
    try:
        assert runtime.is_ready()
        assert runtime.is_accepting_import_effects()
    finally:
        runtime.shutdown()
    assert not runtime.control_store.is_open()
