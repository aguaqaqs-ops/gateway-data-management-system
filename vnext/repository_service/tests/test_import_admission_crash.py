"""Subprocess crash tests for Versioned import HTTP admission."""

from __future__ import annotations

import time
from pathlib import Path
from uuid import UUID

import pytest

from gateway_repository_contracts import OperationStatus
from gateway_repository_service.upload_artifact.visibility import artifact_ready_path
from gateway_repository_service.versioned_import.faults import ImportAdmissionFaultPoint
from support.import_admission_crash_harness import (
    IMPORT_ADMISSION_PENDING_STATUS,
    assert_crash_exit,
    crash_admission_subprocess,
    open_import_store,
    restart_runtime,
    seed_repository_with_import_artifact,
    submit_import_http,
    wait_for_import_status,
)


@pytest.mark.integration
@pytest.mark.serial
def test_crash_after_pending_commit_restarts_to_succeeded(tmp_path: Path) -> None:
    settings, repository_id, artifact_id, expected_commit_id, size_bytes, raw_sha256 = (
        seed_repository_with_import_artifact(tmp_path)
    )
    idempotency_key = "pending-commit-crash"
    status_out = tmp_path / "pending-commit-status.txt"

    completed = crash_admission_subprocess(
        settings,
        repository_id=repository_id,
        artifact_id=artifact_id,
        size_bytes=size_bytes,
        raw_sha256=raw_sha256,
        expected_commit_id=expected_commit_id,
        idempotency_key=idempotency_key,
        fault_point=ImportAdmissionFaultPoint.AFTER_ADMISSION_PENDING_COMMIT.value,
        status_out=status_out,
    )
    assert_crash_exit(completed)
    assert not status_out.exists()

    control_store, store = open_import_store(settings)
    try:
        operations = list(store.list_operations_by_durable_status(IMPORT_ADMISSION_PENDING_STATUS))
        assert len(operations) == 1
        operation_id = operations[0].operation_id
        assert store.count_global_queued() == 1
    finally:
        control_store.close()

    runtime = restart_runtime(settings)
    try:
        wait_for_import_status(
            runtime,
            repository_id,
            operation_id,
            OperationStatus.SUCCEEDED,
            timeout=90.0,
        )
        operation = runtime.import_store.get_operation(repository_id, operation_id)
        assert operation is not None
        assert operation.result is not None
        assert operation.result.expected_commit_id == expected_commit_id
        deadline = time.monotonic() + 30.0
        artifact_path = artifact_ready_path(runtime.layout, repository_id, artifact_id)
        while time.monotonic() < deadline:
            lifecycle = runtime.mutation_store.get_artifact_lifecycle(artifact_id)
            if lifecycle is not None and lifecycle.bytes_deleted_at is not None and not artifact_path.exists():
                break
            time.sleep(0.1)
        else:
            lifecycle = runtime.mutation_store.get_artifact_lifecycle(artifact_id)
            raise AssertionError(
                f"artifact cleanup incomplete: path_exists={artifact_path.exists()} lifecycle={lifecycle}"
            )
    finally:
        runtime.shutdown()


@pytest.mark.integration
@pytest.mark.serial
def test_crash_after_pending_commit_aborts_on_restart(tmp_path: Path) -> None:
    settings, repository_id, artifact_id, expected_commit_id, size_bytes, raw_sha256 = (
        seed_repository_with_import_artifact(tmp_path)
    )
    idempotency_key = "pending-commit-abort"

    completed = crash_admission_subprocess(
        settings,
        repository_id=repository_id,
        artifact_id=artifact_id,
        size_bytes=size_bytes,
        raw_sha256=raw_sha256,
        expected_commit_id=expected_commit_id,
        idempotency_key=idempotency_key,
        fault_point=ImportAdmissionFaultPoint.AFTER_ADMISSION_PENDING_COMMIT.value,
    )
    assert_crash_exit(completed)

    from gateway_repository_service.layout import DurableLayout

    layout = DurableLayout.create_for_probe(settings.data_root)
    ready_path = artifact_ready_path(layout, repository_id, artifact_id)
    assert ready_path.exists()
    ready_path.unlink()

    control_store, store = open_import_store(settings)
    try:
        operations = list(store.list_operations_by_durable_status(IMPORT_ADMISSION_PENDING_STATUS))
        assert len(operations) == 1
        operation_id = operations[0].operation_id
    finally:
        control_store.close()

    runtime = restart_runtime(settings)
    try:
        operation = runtime.import_store.get_operation(repository_id, operation_id)
        assert operation is None
        assert runtime.import_store.count_global_queued() == 0
    finally:
        runtime.shutdown()

    replay_status, _ = submit_import_http(
        settings,
        repository_id=repository_id,
        artifact_id=artifact_id,
        size_bytes=size_bytes,
        raw_sha256=raw_sha256,
        expected_commit_id=expected_commit_id,
        idempotency_key=idempotency_key,
    )
    assert replay_status == 404


@pytest.mark.integration
@pytest.mark.serial
def test_crash_after_queued_publish_replay_returns_same_202(tmp_path: Path) -> None:
    settings, repository_id, artifact_id, expected_commit_id, size_bytes, raw_sha256 = (
        seed_repository_with_import_artifact(tmp_path)
    )
    idempotency_key = "queued-before-202-crash"
    status_out = tmp_path / "queued-publish-status.txt"

    completed = crash_admission_subprocess(
        settings,
        repository_id=repository_id,
        artifact_id=artifact_id,
        size_bytes=size_bytes,
        raw_sha256=raw_sha256,
        expected_commit_id=expected_commit_id,
        idempotency_key=idempotency_key,
        fault_point=ImportAdmissionFaultPoint.AFTER_QUEUED_PUBLISH_BEFORE_202.value,
        status_out=status_out,
    )
    assert_crash_exit(completed)

    control_store, store = open_import_store(settings)
    try:
        assert store.count_global_queued() == 1
        operations = store.list_operations_by_status(OperationStatus.QUEUED)
        assert len(operations) == 1
        operation_id = operations[0].operation_id
        assert store.get_operation_durable_status(operation_id) == OperationStatus.QUEUED.value
    finally:
        control_store.close()

    replay_status, replay_body = submit_import_http(
        settings,
        repository_id=repository_id,
        artifact_id=artifact_id,
        size_bytes=size_bytes,
        raw_sha256=raw_sha256,
        expected_commit_id=expected_commit_id,
        idempotency_key=idempotency_key,
    )
    assert replay_status == 202
    assert UUID(str(replay_body["operation_id"])) == operation_id

    runtime = restart_runtime(settings)
    try:
        wait_for_import_status(
            runtime,
            repository_id,
            operation_id,
            OperationStatus.SUCCEEDED,
            timeout=90.0,
        )
    finally:
        runtime.shutdown()
