"""File-backed worker composition and startup evidence."""

from __future__ import annotations

import dataclasses
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Event, Thread

import pytest

from gateway_backend.bootstrap.operation_worker import (
    bootstrap_control_database,
    build_worker_runtime,
)
from gateway_backend.infrastructure.control_db import ControlDbUnitOfWork, connect_control_db
from gateway_backend.operations import (
    OPERATION_RUNTIME_CONTRACT_VERSION,
    OperationStatus,
    StepStatus,
    TransitionDisposition,
    operation_record_from_document,
    step_record_from_document,
)
from gateway_backend.operations.lease_session import LeaseSession
from gateway_backend.operations.persistence import OperationLifecycleActions
from gateway_backend.operations.state import WritePrecondition
from gateway_backend.operations.worker import CheckpointGeneration, ExecutionControl, WorkerEvent
from gateway_backend.operations.store import StaleWrite
from gateway_backend.settings import OperationWorkerSettings

pytestmark = pytest.mark.integration


def _operation_document(operation_id: str) -> dict[str, object]:
    return {
        "artifact_refs": [],
        "business_refs": [],
        "cancel_requested": False,
        "checkpoint_ref": None,
        "completed_at": None,
        "contract_version": OPERATION_RUNTIME_CONTRACT_VERSION,
        "created_at": "2024-01-02T03:04:05Z",
        "diagnostic": None,
        "document_type": "operation",
        "job_contract_version": "backend-vnext/import-package/v1",
        "job_kind": "import.package",
        "job_payload": {"request": {"value": 1}},
        "job_payload_ref": None,
        "operation_id": operation_id,
        "optimistic_version": 0,
        "ready_closure_ref": None,
        "repository_operation_id": None,
        "status": OperationStatus.QUEUED.value,
        "updated_at": "2024-01-02T03:04:05Z",
    }


def _step_document(operation_id: str, step_id: str) -> dict[str, object]:
    return {
        "attempt_count": 0,
        "cancel_requested": False,
        "checkpoint_ref": None,
        "completed_at": None,
        "contract_version": OPERATION_RUNTIME_CONTRACT_VERSION,
        "created_at": "2024-01-02T03:04:05Z",
        "diagnostic": None,
        "document_type": "step",
        "lease_expires_at": None,
        "lease_token": None,
        "operation_id": operation_id,
        "optimistic_version": 0,
        "prior_output_refs": [],
        "retry_not_before": None,
        "started_at": None,
        "status": StepStatus.PENDING.value,
        "step_id": step_id,
        "step_name": "validate",
        "updated_at": "2024-01-02T03:04:05Z",
        "worker_id": None,
    }


@pytest.mark.serial
def test_empty_file_backed_worker_reaches_ready_drains_and_reopens_wal(
    tmp_path: Path,
) -> None:
    settings = OperationWorkerSettings(control_db_path=tmp_path / "state" / "control.sqlite3")
    bootstrap_control_database(settings)
    events: list[str] = []
    ready = Event()
    stop = Event()

    def observe(event: WorkerEvent) -> None:
        code = event.code.value
        events.append(code)
        if code == "worker_ready":
            ready.set()

    runtime = build_worker_runtime(settings, observer=observe)
    runner = Thread(target=runtime.run, args=(stop.is_set, stop.wait), daemon=False)
    runner.start()
    try:
        assert ready.wait(timeout=5)
        stop.set()
        runner.join(timeout=5)
        assert not runner.is_alive()
    finally:
        stop.set()
        runner.join(timeout=5)

    assert events[:1] == ["worker_ready"]
    assert events[-2:] == ["drain_started", "worker_exited"]
    with connect_control_db(settings.control_db_path) as connection:
        assert connection.execute("PRAGMA journal_mode").fetchone()[0] == "wal"
        assert connection.execute(
            "SELECT version FROM control_schema_migrations WHERE component = 'operations'"
        ).fetchone()[0] == 1


def test_missing_runnable_handler_fails_closed_before_claim(tmp_path: Path) -> None:
    settings = OperationWorkerSettings(control_db_path=tmp_path / "control.sqlite3")
    bootstrap_control_database(settings)
    operation = operation_record_from_document(_operation_document("operation-worker-1"))
    step = step_record_from_document(_step_document(operation.operation_id, "step-worker-1"))
    with ControlDbUnitOfWork(settings.control_db_path) as unit_of_work:
        assert (
            unit_of_work.operations.insert_operation_with_initial_step(operation, step)
            is TransitionDisposition.APPLY
        )

    events: list[WorkerEvent] = []

    def observe(event: WorkerEvent) -> None:
        events.append(event)

    runtime = build_worker_runtime(settings, observer=observe)
    with pytest.raises(ValueError, match="fatally blocked"):
        runtime.run(lambda: False, lambda _timeout: False)

    with ControlDbUnitOfWork(settings.control_db_path, read_only=True) as unit_of_work:
        assert unit_of_work.operations.get_operation(operation.operation_id).status is OperationStatus.QUEUED
        assert unit_of_work.operations.get_step(step.step_id).status is StepStatus.PENDING
    assert any(event.code.value == "startup_failed" for event in events)


@pytest.mark.serial
def test_file_backed_heartbeat_and_concurrent_cancel_are_read_back(
    tmp_path: Path,
) -> None:
    settings = OperationWorkerSettings(control_db_path=tmp_path / "control.sqlite3")
    bootstrap_control_database(settings)
    operation = operation_record_from_document(_operation_document("operation-worker-2"))
    step = step_record_from_document(_step_document(operation.operation_id, "step-worker-2"))
    with ControlDbUnitOfWork(settings.control_db_path) as unit_of_work:
        assert (
            unit_of_work.operations.insert_operation_with_initial_step(operation, step)
            is TransitionDisposition.APPLY
        )
        transaction_now = unit_of_work.operations.transaction_now
        claimed = OperationLifecycleActions(
            unit_of_work.operations,
            transaction_now=transaction_now,
        ).claim_one("worker-file-1", "lease-file-1")
    assert claimed is not None
    claimed_operation, claimed_step = claimed

    def write_uow_factory() -> ControlDbUnitOfWork:
        return ControlDbUnitOfWork(settings.control_db_path)

    control = ExecutionControl()
    events: list[WorkerEvent] = []

    def observe(event: WorkerEvent) -> None:
        events.append(event)

    session = LeaseSession(
        worker_id="worker-file-1",
        lease_token="lease-file-1",
        operation_id=claimed_operation.operation_id,
        step_id=claimed_step.step_id,
        write_uow_factory=write_uow_factory,
        control=control,
        observer=observe,
    )
    session.refresh_control()
    heartbeated = session.heartbeat()
    assert heartbeated.optimistic_version == claimed_step.optimistic_version + 1

    writer_started = Event()
    release_writer = Event()

    def cancel_writer() -> tuple[TransitionDisposition, TransitionDisposition]:
        with ControlDbUnitOfWork(settings.control_db_path) as unit_of_work:
            store = unit_of_work.operations
            current_operation = store.get_operation(claimed_operation.operation_id)
            current_step = store.get_step(claimed_step.step_id)
            transaction_now = store.transaction_now
            writer_started.set()
            assert release_writer.wait(timeout=5)
            operation_after = dataclasses.replace(
                current_operation,
                cancel_requested=True,
                optimistic_version=current_operation.optimistic_version + 1,
                updated_at=transaction_now,
            )
            step_after = dataclasses.replace(
                current_step,
                cancel_requested=True,
                optimistic_version=current_step.optimistic_version + 1,
                updated_at=transaction_now,
            )
            result = OperationLifecycleActions(
                store,
                transaction_now=transaction_now,
            ).cancel_intent(
                operation_after,
                WritePrecondition(
                    expected_optimistic_version=current_operation.optimistic_version,
                    worker_id=None,
                    lease_token=None,
                ),
                step_after,
                WritePrecondition(
                    expected_optimistic_version=current_step.optimistic_version,
                    worker_id="worker-file-1",
                    lease_token="lease-file-1",
                ),
            )
            return result

    with ThreadPoolExecutor(max_workers=2) as executor:
        cancel_future = executor.submit(cancel_writer)
        assert writer_started.wait(timeout=5)
        refresh_future = executor.submit(session.refresh_control)
        release_writer.set()
        assert cancel_future.result(timeout=5) == (
            TransitionDisposition.APPLY,
            TransitionDisposition.APPLY,
        )
        assert refresh_future.result(timeout=5) is None

    assert control.cancel_requested
    assert any(event.code.value == "heartbeat_succeeded" for event in events)
    with ControlDbUnitOfWork(settings.control_db_path, read_only=True) as unit_of_work:
        read_operation = unit_of_work.operations.get_operation(claimed_operation.operation_id)
        read_step = unit_of_work.operations.get_step(claimed_step.step_id)
    assert read_operation.cancel_requested
    assert read_step.cancel_requested
    assert read_step.worker_id == "worker-file-1"
    assert read_step.lease_token == "lease-file-1"

    with pytest.raises(ValueError, match="cancel_requested cannot be reset"):
        session.publish_checkpoint(
            lambda _operation, current_step, now: dataclasses.replace(
                current_step,
                cancel_requested=False,
                updated_at=now,
                optimistic_version=current_step.optimistic_version + 1,
            )
        )


def test_file_backed_publication_reloads_versions_after_multiple_heartbeats(
    tmp_path: Path,
) -> None:
    settings = OperationWorkerSettings(control_db_path=tmp_path / "control.sqlite3")
    bootstrap_control_database(settings)
    operation = operation_record_from_document(_operation_document("operation-worker-3"))
    step = step_record_from_document(_step_document(operation.operation_id, "step-worker-3"))
    with ControlDbUnitOfWork(settings.control_db_path) as unit_of_work:
        assert (
            unit_of_work.operations.insert_operation_with_initial_step(operation, step)
            is TransitionDisposition.APPLY
        )
        claimed = OperationLifecycleActions(
            unit_of_work.operations,
            transaction_now=unit_of_work.operations.transaction_now,
        ).claim_one("worker-file-2", "lease-file-2")
    assert claimed is not None
    claimed_operation, claimed_step = claimed

    session = LeaseSession(
        worker_id="worker-file-2",
        lease_token="lease-file-2",
        operation_id=claimed_operation.operation_id,
        step_id=claimed_step.step_id,
        write_uow_factory=lambda: ControlDbUnitOfWork(settings.control_db_path),
        control=ExecutionControl(),
        observer=lambda _event: None,
    )
    first_heartbeat = session.heartbeat()
    second_heartbeat = session.heartbeat()
    assert first_heartbeat.optimistic_version == claimed_step.optimistic_version + 1
    assert second_heartbeat.optimistic_version == claimed_step.optimistic_version + 2

    generation = session.publish_checkpoint(
        lambda _operation, current_step, now: dataclasses.replace(
            current_step,
            updated_at=now,
            optimistic_version=current_step.optimistic_version + 1,
        )
    )
    assert generation == CheckpointGeneration(
        claimed_operation.operation_id,
        claimed_step.step_id,
        claimed_step.optimistic_version + 3,
    )

    session.publish_operation(
        lambda current_operation, current_step, now: (
            dataclasses.replace(
                current_step,
                status=StepStatus.SUCCEEDED,
                completed_at=now,
                worker_id=None,
                lease_token=None,
                lease_expires_at=None,
                updated_at=now,
                optimistic_version=current_step.optimistic_version + 1,
            ),
            dataclasses.replace(
                current_operation,
                status=OperationStatus.SUCCEEDED,
                completed_at=now,
                updated_at=now,
                optimistic_version=current_operation.optimistic_version + 1,
            ),
        )
    )

    with ControlDbUnitOfWork(settings.control_db_path, read_only=True) as unit_of_work:
        persisted_operation = unit_of_work.operations.get_operation(claimed_operation.operation_id)
        persisted_step = unit_of_work.operations.get_step(claimed_step.step_id)
    assert persisted_operation.status is OperationStatus.SUCCEEDED
    assert persisted_step.status is StepStatus.SUCCEEDED
    assert persisted_step.optimistic_version == claimed_step.optimistic_version + 4
    with pytest.raises(StaleWrite, match="closed"):
        session.heartbeat()
