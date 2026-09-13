"""File-backed worker composition and startup evidence."""

from __future__ import annotations

import dataclasses
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from pathlib import Path
from threading import Event, Thread
from typing import cast

import pytest

from gateway_backend.application.job_definitions import JobDefinition, NormalPublicationCapability
from gateway_backend.application.recovery import RecoveryCapability
from gateway_backend.application.checkpoints import (
    CheckpointPublicationError,
    make_terminal_ready_closure_builder,
    prepare_ready_closure,
)
from gateway_backend.artifacts import InMemoryArtifactStore, put_with_built_ref
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
from gateway_backend.operations.contracts import JobStepKey, OperationRecord, StepRecord
from gateway_backend.operations.lease_session import LeaseSession
from gateway_backend.operations.persistence import OperationLifecycleActions
from gateway_backend.operations.state import WritePrecondition
from gateway_backend.operations.worker import (
    CheckpointGeneration,
    ClaimedExecutor,
    ExecutionControl,
    ExecutorAcknowledgment,
    StartupDisposition,
    WorkerEvent,
)
from gateway_backend.operations.store import StaleWrite
from tests.support.runtime_settings import make_operation_worker_settings

pytestmark = pytest.mark.integration

REGISTERED_KEY = JobStepKey(job_kind="import.package", step_name="validate")
REGISTERED_VERSION = "backend-vnext/import-package/v1"
REGISTERED_DECODER = "backend-vnext/import-package/decoder/v1"
REGISTERED_HANDLER = "backend-vnext/import-package/handler/v1"


def _registered_definition() -> JobDefinition:
    return JobDefinition(
        key=REGISTERED_KEY,
        supported_payload_versions=frozenset({REGISTERED_VERSION}),
        decoder_identity=REGISTERED_DECODER,
        handler_identity=REGISTERED_HANDLER,
        publication_capability=NormalPublicationCapability.TERMINAL,
        recovery_capability=RecoveryCapability.PURE_RECOMPUTE,
    )


def _noop_handler(
    operation: OperationRecord,
    step: StepRecord,
    control: ExecutionControl,
    lease_session: LeaseSession,
) -> ExecutorAcknowledgment:
    del operation, step, control, lease_session
    return ExecutorAcknowledgment.PUBLISHED


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
    settings = make_operation_worker_settings(tmp_path, control_db_path=tmp_path / "state" / "control.sqlite3")
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
    settings = make_operation_worker_settings(tmp_path, control_db_path=tmp_path / "control.sqlite3")
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


def test_unsupported_job_contract_version_fails_closed_before_claim(tmp_path: Path) -> None:
    settings = make_operation_worker_settings(tmp_path, control_db_path=tmp_path / "control.sqlite3")
    bootstrap_control_database(settings)
    operation = operation_record_from_document(
        {
            **_operation_document("operation-worker-unsupported"),
            "job_contract_version": "backend-vnext/unsupported/v9",
        }
    )
    step = step_record_from_document(
        _step_document(operation.operation_id, "step-worker-unsupported")
    )
    with ControlDbUnitOfWork(settings.control_db_path) as unit_of_work:
        assert (
            unit_of_work.operations.insert_operation_with_initial_step(operation, step)
            is TransitionDisposition.APPLY
        )

    events: list[WorkerEvent] = []

    def observe(event: WorkerEvent) -> None:
        events.append(event)

    runtime = build_worker_runtime(
        settings,
        observer=observe,
        job_definitions=(_registered_definition(),),
        handlers={REGISTERED_HANDLER: cast(ClaimedExecutor, _noop_handler)},
        payload_decoders={REGISTERED_DECODER: lambda payload: payload},
    )
    with pytest.raises(ValueError, match="fatally blocked"):
        runtime.run(lambda: False, lambda _timeout: False)

    with ControlDbUnitOfWork(settings.control_db_path, read_only=True) as unit_of_work:
        persisted_operation = unit_of_work.operations.get_operation(operation.operation_id)
        persisted_step = unit_of_work.operations.get_step(step.step_id)
    assert persisted_operation.status is OperationStatus.QUEUED
    assert persisted_step.status is StepStatus.PENDING
    assert persisted_step.worker_id is None
    assert persisted_step.lease_token is None
    assert any(event.code.value == "startup_failed" for event in events)


def test_unsupported_job_contract_version_rejected_at_claim_without_running_lease(
    tmp_path: Path,
) -> None:
    settings = make_operation_worker_settings(
        tmp_path,
        control_db_path=tmp_path / "claim-version-gate" / "control.sqlite3"
    )
    bootstrap_control_database(settings)
    runtime = build_worker_runtime(
        settings,
        observer=lambda _event: None,
        job_definitions=(_registered_definition(),),
        handlers={REGISTERED_HANDLER: cast(ClaimedExecutor, _noop_handler)},
        payload_decoders={REGISTERED_DECODER: lambda payload: payload},
    )
    assert runtime._startup.startup() is StartupDisposition.READY

    operation = operation_record_from_document(
        {
            **_operation_document("operation-claim-version-race"),
            "job_contract_version": "backend-vnext/import-package/v9",
        }
    )
    step = step_record_from_document(
        _step_document(operation.operation_id, "step-claim-version-race")
    )
    with ControlDbUnitOfWork(settings.control_db_path) as unit_of_work:
        assert (
            unit_of_work.operations.insert_operation_with_initial_step(operation, step)
            is TransitionDisposition.APPLY
        )

    with pytest.raises(ValueError, match="not supported"):
        runtime._startup.claim_one()

    with ControlDbUnitOfWork(settings.control_db_path, read_only=True) as unit_of_work:
        persisted_operation = unit_of_work.operations.get_operation(operation.operation_id)
        persisted_step = unit_of_work.operations.get_step(step.step_id)
    assert persisted_operation.status is OperationStatus.QUEUED
    assert persisted_step.status is StepStatus.PENDING
    assert persisted_step.worker_id is None
    assert persisted_step.lease_token is None


@pytest.mark.serial
def test_registered_key_reaches_ready_with_empty_queue(tmp_path: Path) -> None:
    settings = make_operation_worker_settings(tmp_path, control_db_path=tmp_path / "registered" / "control.sqlite3")
    bootstrap_control_database(settings)
    events: list[str] = []
    ready = Event()
    stop = Event()

    def observe(event: WorkerEvent) -> None:
        code = event.code.value
        events.append(code)
        if code == "worker_ready":
            ready.set()

    runtime = build_worker_runtime(
        settings,
        observer=observe,
        job_definitions=(_registered_definition(),),
        handlers={REGISTERED_HANDLER: cast(ClaimedExecutor, _noop_handler)},
        payload_decoders={REGISTERED_DECODER: lambda payload: payload},
    )
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


def test_registered_runtime_startup_recovers_expired_running_step(tmp_path: Path) -> None:
    """The concrete worker composition applies R5 startup takeover before claiming."""

    settings = make_operation_worker_settings(tmp_path, control_db_path=tmp_path / "startup-recovery" / "control.sqlite3")
    bootstrap_control_database(settings)
    operation = operation_record_from_document(_operation_document("operation-startup-recovery"))
    step = step_record_from_document(_step_document(operation.operation_id, "step-startup-recovery"))
    with ControlDbUnitOfWork(settings.control_db_path) as unit_of_work:
        assert (
            unit_of_work.operations.insert_operation_with_initial_step(operation, step)
            is TransitionDisposition.APPLY
        )
        claimed = OperationLifecycleActions(
            unit_of_work.operations,
            transaction_now=unit_of_work.operations.transaction_now,
        ).claim_one("worker-startup-old", "lease-startup-old")
    assert claimed is not None
    with connect_control_db(settings.control_db_path) as connection:
        connection.execute(
            "UPDATE step_records SET started_at_us = ?, updated_at_us = ?, lease_expires_at_us = ? WHERE step_id = ?",
            (1735689600000000, 1735689600000000, 1735689601000000, step.step_id),
        )
        connection.execute(
            "UPDATE operation_records SET updated_at_us = ? WHERE operation_id = ?",
            (1735689600000000, operation.operation_id),
        )
        connection.commit()

    events: list[WorkerEvent] = []

    def observe(event: WorkerEvent) -> None:
        events.append(event)

    runtime = build_worker_runtime(
        settings,
        observer=observe,
        job_definitions=(_registered_definition(),),
        handlers={REGISTERED_HANDLER: cast(ClaimedExecutor, _noop_handler)},
        payload_decoders={REGISTERED_DECODER: lambda payload: payload},
    )
    disposition = runtime._startup.startup()
    assert disposition is StartupDisposition.RETRYABLE_BLOCK, events
    with ControlDbUnitOfWork(settings.control_db_path, read_only=True) as unit_of_work:
        recovered_step = unit_of_work.operations.get_step(step.step_id)
    assert recovered_step.status is StepStatus.RETRY_WAIT
    assert recovered_step.lease_token is None


@pytest.mark.serial
def test_file_backed_heartbeat_and_concurrent_cancel_are_read_back(
    tmp_path: Path,
) -> None:
    settings = make_operation_worker_settings(tmp_path, control_db_path=tmp_path / "control.sqlite3")
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
    settings = make_operation_worker_settings(tmp_path, control_db_path=tmp_path / "control.sqlite3")
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


def test_stale_cas_after_closure_artifact_put_leaves_no_ready_closure_ref(
    tmp_path: Path,
) -> None:
    settings = make_operation_worker_settings(tmp_path, control_db_path=tmp_path / "stale-cas.sqlite3")
    bootstrap_control_database(settings)
    artifact_store = InMemoryArtifactStore()
    operation = operation_record_from_document(_operation_document("operation-stale-cas"))
    step = step_record_from_document(_step_document(operation.operation_id, "step-stale-cas"))
    with ControlDbUnitOfWork(settings.control_db_path) as unit_of_work:
        assert (
            unit_of_work.operations.insert_operation_with_initial_step(operation, step)
            is TransitionDisposition.APPLY
        )
        claimed = OperationLifecycleActions(
            unit_of_work.operations,
            transaction_now=unit_of_work.operations.transaction_now,
        ).claim_one("worker-stale-cas", "lease-stale-cas")
    assert claimed is not None
    claimed_operation, claimed_step = claimed

    session = LeaseSession(
        worker_id="worker-stale-cas",
        lease_token="lease-stale-cas",
        operation_id=claimed_operation.operation_id,
        step_id=claimed_step.step_id,
        write_uow_factory=lambda: ControlDbUnitOfWork(settings.control_db_path),
        control=ExecutionControl(),
        observer=lambda _event: None,
    )
    output_ref = put_with_built_ref(
        artifact_store,
        b"ready-output",
        artifact_id="artifact-ready-output",
        media_type="application/octet-stream",
    )
    closure_ref = prepare_ready_closure(
        artifact_store,
        (output_ref,),
        claimed_operation.job_contract_version,
    )
    session.heartbeat()

    with ControlDbUnitOfWork(settings.control_db_path, read_only=True) as unit_of_work:
        current_operation = unit_of_work.operations.get_operation(claimed_operation.operation_id)
        current_step = unit_of_work.operations.get_step(claimed_step.step_id)
        transaction_now = unit_of_work.operations.transaction_now
    terminal_step, terminal_operation = make_terminal_ready_closure_builder(
        closure_ref=closure_ref,
    )(current_operation, current_step, transaction_now)

    with ControlDbUnitOfWork(settings.control_db_path) as unit_of_work:
        store = unit_of_work.operations
        transaction_now = store.transaction_now
        with pytest.raises(StaleWrite):
            OperationLifecycleActions(
                store,
                transaction_now=transaction_now,
            ).complete_operation(
                terminal_step,
                WritePrecondition(
                    expected_optimistic_version=claimed_step.optimistic_version,
                    worker_id="worker-stale-cas",
                    lease_token="lease-stale-cas",
                ),
                terminal_operation,
                WritePrecondition(
                    expected_optimistic_version=claimed_operation.optimistic_version,
                    worker_id=None,
                    lease_token=None,
                ),
            )

    with ControlDbUnitOfWork(settings.control_db_path, read_only=True) as unit_of_work:
        persisted_operation = unit_of_work.operations.get_operation(claimed_operation.operation_id)
        persisted_step = unit_of_work.operations.get_step(claimed_step.step_id)
    assert persisted_operation.ready_closure_ref is None
    assert persisted_operation.status is OperationStatus.RUNNING
    assert persisted_step.status is StepStatus.RUNNING
    assert artifact_store.locate(closure_ref) is not None


def test_ready_closure_ref_set_once_rejects_second_publication(tmp_path: Path) -> None:
    settings = make_operation_worker_settings(tmp_path, control_db_path=tmp_path / "closure-once.sqlite3")
    bootstrap_control_database(settings)
    artifact_store = InMemoryArtifactStore()
    operation = operation_record_from_document(_operation_document("operation-closure-once"))
    step = step_record_from_document(_step_document(operation.operation_id, "step-closure-once"))
    with ControlDbUnitOfWork(settings.control_db_path) as unit_of_work:
        assert (
            unit_of_work.operations.insert_operation_with_initial_step(operation, step)
            is TransitionDisposition.APPLY
        )
        claimed = OperationLifecycleActions(
            unit_of_work.operations,
            transaction_now=unit_of_work.operations.transaction_now,
        ).claim_one("worker-closure-once", "lease-closure-once")
    assert claimed is not None
    claimed_operation, claimed_step = claimed

    session = LeaseSession(
        worker_id="worker-closure-once",
        lease_token="lease-closure-once",
        operation_id=claimed_operation.operation_id,
        step_id=claimed_step.step_id,
        write_uow_factory=lambda: ControlDbUnitOfWork(settings.control_db_path),
        control=ExecutionControl(),
        observer=lambda _event: None,
    )
    first_output = put_with_built_ref(
        artifact_store,
        b"first-output",
        artifact_id="artifact-first-output",
        media_type="application/octet-stream",
    )
    first_closure = prepare_ready_closure(
        artifact_store,
        (first_output,),
        claimed_operation.job_contract_version,
        artifact_id="ready-closure-first",
    )
    session.publish_operation(make_terminal_ready_closure_builder(closure_ref=first_closure))

    second_output = put_with_built_ref(
        artifact_store,
        b"second-output",
        artifact_id="artifact-second-output",
        media_type="application/octet-stream",
    )
    second_closure = prepare_ready_closure(
        artifact_store,
        (second_output,),
        claimed_operation.job_contract_version,
        artifact_id="ready-closure-second",
    )
    with ControlDbUnitOfWork(settings.control_db_path, read_only=True) as unit_of_work:
        terminal_operation = unit_of_work.operations.get_operation(claimed_operation.operation_id)
        terminal_step = unit_of_work.operations.get_step(claimed_step.step_id)
    assert terminal_operation.ready_closure_ref == first_closure
    with pytest.raises(CheckpointPublicationError, match="ready_closure_ref is already set"):
        make_terminal_ready_closure_builder(closure_ref=second_closure)(
            terminal_operation,
            terminal_step,
            datetime.now(UTC),
        )
    with ControlDbUnitOfWork(settings.control_db_path, read_only=True) as unit_of_work:
        persisted_operation = unit_of_work.operations.get_operation(claimed_operation.operation_id)
    assert persisted_operation.ready_closure_ref == first_closure


def _execute_claimed_work(
    db_path: Path,
    work: object,
    *,
    worker_id: str,
    lease_token: str,
) -> ExecutorAcknowledgment:
    from gateway_backend.operations.worker import ClaimedWork

    assert type(work) is ClaimedWork
    control = ExecutionControl()
    session = LeaseSession(
        worker_id=worker_id,
        lease_token=lease_token,
        operation_id=work.operation.operation_id,
        step_id=work.step.step_id,
        write_uow_factory=lambda: ControlDbUnitOfWork(db_path),
        control=control,
        observer=lambda _event: None,
    )
    return work.executor(work.operation, work.step, control, session)


def _expire_step_lease(db_path: Path, step_id: str) -> None:
    from gateway_backend.infrastructure.control_db.sqlite_operations import _datetime_to_epoch_us

    with ControlDbUnitOfWork(db_path, read_only=True) as unit_of_work:
        step = unit_of_work.operations.get_step(step_id)
        transaction_now = unit_of_work.operations.transaction_now
    lease_expires_at = transaction_now - timedelta(seconds=1)
    updated_at = lease_expires_at - timedelta(seconds=1)
    started_at = step.started_at
    if started_at is None or started_at > updated_at:
        started_at = updated_at - timedelta(seconds=1)
    with connect_control_db(db_path) as connection:
        connection.execute(
            "UPDATE step_records SET started_at_us = ?, updated_at_us = ?, lease_expires_at_us = ? WHERE step_id = ?",
            (
                _datetime_to_epoch_us(started_at),
                _datetime_to_epoch_us(updated_at),
                _datetime_to_epoch_us(lease_expires_at),
                step_id,
            ),
        )
        connection.commit()


def _due_retry_wait(db_path: Path, step_id: str) -> None:
    from gateway_backend.infrastructure.control_db.sqlite_operations import _datetime_to_epoch_us

    with ControlDbUnitOfWork(db_path, read_only=True) as unit_of_work:
        step = unit_of_work.operations.get_step(step_id)
        transaction_now = unit_of_work.operations.transaction_now
    retry_not_before = transaction_now - timedelta(seconds=1)
    updated_at = retry_not_before
    started_at = step.started_at
    if started_at is None or started_at > updated_at:
        started_at = updated_at - timedelta(seconds=1)
    with connect_control_db(db_path) as connection:
        connection.execute(
            "UPDATE step_records SET retry_not_before_us = ?, updated_at_us = ?, started_at_us = ?, eligible_at_us = ? WHERE step_id = ?",
            (
                _datetime_to_epoch_us(retry_not_before),
                _datetime_to_epoch_us(updated_at),
                _datetime_to_epoch_us(started_at),
                _datetime_to_epoch_us(retry_not_before),
                step_id,
            ),
        )
        connection.commit()


def test_worker_runtime_external_effect_accepted_takeover_polls_original_identity(
    tmp_path: Path,
) -> None:
    """P4-R5-S5: recovery-routed worker executor polls the original identity after takeover."""

    from gateway_backend.application.external_effect_stub import (
        DeterministicExternalEffectStub,
        RecordingExternalEffectStub,
        StubOutcome,
        build_request_bytes,
        compute_operation_identity,
    )
    from gateway_backend.application.synthetic_jobs import (
        EXTERNAL_EFFECT_STUB_PAYLOAD_VERSION,
        PollingExternalEffectStub,
        external_effect_stub_composition_bundle,
    )

    settings = make_operation_worker_settings(
        tmp_path,
        control_db_path=tmp_path / "worker-external-recovery" / "control.sqlite3",
    )
    from gateway_backend.infrastructure.artifact_store import LocalArtifactStore

    bootstrap_control_database(settings)
    artifact_store = LocalArtifactStore(settings.control_db_path.parent / "artifacts")

    request_bytes = build_request_bytes("idem-worker-recovery", "request-worker-recovery")
    expected_identity = compute_operation_identity("idem-worker-recovery", request_bytes)
    inner_stub = DeterministicExternalEffectStub(request_bytes=request_bytes)
    polling_stub = PollingExternalEffectStub(inner_stub, default_poll_result=None)
    polling_stub.configure_poll(expected_identity, [None, StubOutcome.CONFIRMED])
    recording_stub = RecordingExternalEffectStub(polling_stub)

    definitions, handlers, decoders = external_effect_stub_composition_bundle(
        artifact_store,
        external_stub=recording_stub,
    )

    operation_id = "operation-worker-external-recovery"
    step_id = "step-worker-external-recovery"
    operation = operation_record_from_document(
        {
            "artifact_refs": [],
            "business_refs": [],
            "cancel_requested": False,
            "checkpoint_ref": None,
            "completed_at": None,
            "contract_version": OPERATION_RUNTIME_CONTRACT_VERSION,
            "created_at": "2026-08-24T12:00:00Z",
            "diagnostic": None,
            "document_type": "operation",
            "job_contract_version": EXTERNAL_EFFECT_STUB_PAYLOAD_VERSION,
            "job_kind": definitions[0].key.job_kind,
            "job_payload": {
                "idempotency_key": "idem-worker-recovery",
                "request_body": "request-worker-recovery",
                "stub_outcome": StubOutcome.ACCEPTED.value,
            },
            "job_payload_ref": None,
            "operation_id": operation_id,
            "optimistic_version": 0,
            "ready_closure_ref": None,
            "repository_operation_id": None,
            "status": OperationStatus.QUEUED.value,
            "updated_at": "2026-08-24T12:00:00Z",
        }
    )
    step = step_record_from_document(
        {
            "attempt_count": 0,
            "cancel_requested": False,
            "checkpoint_ref": None,
            "completed_at": None,
            "contract_version": OPERATION_RUNTIME_CONTRACT_VERSION,
            "created_at": "2026-08-24T12:00:00Z",
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
            "step_name": definitions[0].key.step_name,
            "updated_at": "2026-08-24T12:00:00Z",
            "worker_id": None,
        }
    )
    with ControlDbUnitOfWork(settings.control_db_path) as unit_of_work:
        assert (
            unit_of_work.operations.insert_operation_with_initial_step(operation, step)
            is TransitionDisposition.APPLY
        )

    runtime = build_worker_runtime(
        settings,
        job_definitions=definitions,
        handlers=handlers,
        payload_decoders=decoders,
        external_effect_stub=polling_stub,
    )
    startup = runtime._startup
    assert startup.startup() is StartupDisposition.READY

    first_work = startup.claim_one()
    assert first_work is not None
    first_ack = _execute_claimed_work(
        settings.control_db_path,
        first_work,
        worker_id=first_work.step.worker_id or "worker-first",
        lease_token=first_work.step.lease_token or "lease-first",
    )
    assert first_ack is ExecutorAcknowledgment.SAFE_HANDOFF
    assert recording_stub.submit_count == 1

    _expire_step_lease(settings.control_db_path, step_id)
    assert startup.startup() is StartupDisposition.RETRYABLE_BLOCK
    with ControlDbUnitOfWork(settings.control_db_path, read_only=True) as unit_of_work:
        retry_step = unit_of_work.operations.get_step(step_id)
    assert retry_step.status is StepStatus.RETRY_WAIT

    _due_retry_wait(settings.control_db_path, step_id)
    assert startup.startup() is StartupDisposition.READY
    second_work = startup.claim_one()
    assert second_work is not None
    second_ack = _execute_claimed_work(
        settings.control_db_path,
        second_work,
        worker_id=second_work.step.worker_id or "worker-second",
        lease_token=second_work.step.lease_token or "lease-second",
    )
    assert second_ack is ExecutorAcknowledgment.PUBLISHED
    assert recording_stub.submit_count == 1

    with ControlDbUnitOfWork(settings.control_db_path, read_only=True) as unit_of_work:
        retry_step = unit_of_work.operations.get_step(step_id)
    assert retry_step.status is StepStatus.RETRY_WAIT

    _due_retry_wait(settings.control_db_path, step_id)
    assert startup.startup() is StartupDisposition.READY
    third_work = startup.claim_one()
    assert third_work is not None
    third_ack = _execute_claimed_work(
        settings.control_db_path,
        third_work,
        worker_id=third_work.step.worker_id or "worker-third",
        lease_token=third_work.step.lease_token or "lease-third",
    )
    assert third_ack is ExecutorAcknowledgment.PUBLISHED
    assert recording_stub.submit_count == 1

    with ControlDbUnitOfWork(settings.control_db_path, read_only=True) as unit_of_work:
        persisted_operation = unit_of_work.operations.get_operation(operation_id)
        persisted_step = unit_of_work.operations.get_step(step_id)
    assert persisted_operation.status is OperationStatus.SUCCEEDED
    assert persisted_step.status is StepStatus.SUCCEEDED
    assert persisted_operation.repository_operation_id == expected_identity
    assert recording_stub.submit_count == 1
