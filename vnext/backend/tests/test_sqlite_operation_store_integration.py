"""File-backed SQLite control DB integration tests."""

from __future__ import annotations

import dataclasses
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from pathlib import Path
from threading import Barrier

import pytest

from gateway_backend.infrastructure.control_db import (
    ControlDbUnitOfWork,
    connect_control_db,
    initialize_control_db,
)
from gateway_backend.infrastructure.control_db.migrations import bootstrap_control_schema
from gateway_backend.operations import (
    OPERATION_RUNTIME_CONTRACT_VERSION,
    ConflictingDuplicate,
    OperationStatus,
    RecordNotFound,
    StepStatus,
    TransitionDisposition,
    WritePrecondition,
    operation_record_from_document,
    step_record_from_document,
)
from gateway_backend.operations.persistence import OperationLifecycleActions

pytestmark = pytest.mark.integration

MIGRATION_TIME = datetime(2024, 1, 2, 3, 4, 5, tzinfo=UTC)
LATER_TIME = datetime(2024, 1, 2, 3, 5, 5, tzinfo=UTC)


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


def _step_document(
    operation_id: str,
    step_id: str,
    *,
    step_name: str = "validate",
) -> dict[str, object]:
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
        "status": "PENDING",
        "step_id": step_id,
        "step_name": step_name,
        "updated_at": "2024-01-02T03:04:05Z",
        "worker_id": None,
    }


def test_file_backed_profile_and_schema_survive_reopen(tmp_path: Path) -> None:
    db_path = tmp_path / "control.sqlite3"
    initialize_control_db(db_path, now=lambda: MIGRATION_TIME)

    connection = connect_control_db(db_path)
    assert connection.execute("PRAGMA journal_mode").fetchone()[0] == "wal"
    assert connection.execute("PRAGMA foreign_keys").fetchone()[0] == 1
    assert connection.execute("PRAGMA synchronous").fetchone()[0] == 2
    assert connection.execute("PRAGMA busy_timeout").fetchone()[0] == 5_000
    connection.close()

    reopened = connect_control_db(db_path)
    try:
        assert reopened.execute(
            "SELECT version FROM control_schema_migrations WHERE component = 'operations'"
        ).fetchone()[0] == 1
        assert reopened.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table' AND name = 'step_records'"
        ).fetchone()[0] == "step_records"
    finally:
        reopened.close()


def test_unit_of_work_commits_and_rolls_back_on_same_connection(tmp_path: Path) -> None:
    db_path = tmp_path / "control.sqlite3"
    initialize_control_db(db_path, now=lambda: MIGRATION_TIME)

    with ControlDbUnitOfWork(db_path) as unit_of_work:
        unit_of_work.connection.execute("CREATE TABLE uow_probe(value INTEGER NOT NULL)")
        unit_of_work.connection.execute("INSERT INTO uow_probe VALUES (1)")

    with ControlDbUnitOfWork(db_path, read_only=True) as unit_of_work:
        assert unit_of_work.connection.execute("SELECT value FROM uow_probe").fetchone()[0] == 1

    with pytest.raises(RuntimeError):
        with ControlDbUnitOfWork(db_path) as unit_of_work:
            unit_of_work.connection.execute("INSERT INTO uow_probe VALUES (2)")
            raise RuntimeError("synthetic rollback")

    with connect_control_db(db_path) as connection:
        values = [row[0] for row in connection.execute("SELECT value FROM uow_probe ORDER BY value")]
    assert values == [1]


def test_missing_parent_is_not_created(tmp_path: Path) -> None:
    missing_parent = tmp_path / "not-created"
    with pytest.raises(ValueError, match="parent directory"):
        connect_control_db(missing_parent / "control.sqlite3")
    assert not missing_parent.exists()


def test_two_connections_can_bootstrap_the_same_file_once(tmp_path: Path) -> None:
    db_path = tmp_path / "control.sqlite3"
    barrier = Barrier(2)

    def bootstrap_from_independent_connection() -> None:
        barrier.wait()
        connection = connect_control_db(db_path)
        try:
            bootstrap_control_schema(connection, now=lambda: MIGRATION_TIME)
        finally:
            connection.close()

    with ThreadPoolExecutor(max_workers=2) as executor:
        list(executor.map(lambda _item: bootstrap_from_independent_connection(), (1, 2)))

    connection = sqlite3.connect(db_path)
    try:
        assert connection.execute(
            "SELECT COUNT(*) FROM control_schema_migrations WHERE component = 'operations'"
        ).fetchone()[0] == 1
    finally:
        connection.close()


def test_operation_store_commits_and_reads_back_after_reopen(tmp_path: Path) -> None:
    db_path = tmp_path / "control.sqlite3"
    initialize_control_db(db_path, now=lambda: MIGRATION_TIME)
    operation = operation_record_from_document(_operation_document("op-file-0001"))
    step = step_record_from_document(_step_document("op-file-0001", "step-file-0001"))

    with ControlDbUnitOfWork(db_path, now=lambda: LATER_TIME) as unit_of_work:
        assert (
            unit_of_work.operations.insert_operation_with_initial_step(operation, step)
            is TransitionDisposition.APPLY
        )

    with ControlDbUnitOfWork(db_path, read_only=True, now=lambda: LATER_TIME) as unit_of_work:
        assert unit_of_work.operations.get_operation(operation.operation_id) == operation
        assert unit_of_work.operations.get_step(step.step_id) == step
        with pytest.raises(RuntimeError, match="read-only"):
            unit_of_work.operations.insert_operation_with_initial_step(operation, step)


def test_lifecycle_claim_commits_and_reads_back_after_reopen(tmp_path: Path) -> None:
    db_path = tmp_path / "control.sqlite3"
    initialize_control_db(db_path, now=lambda: MIGRATION_TIME)
    operation = operation_record_from_document(_operation_document("op-claim-0001"))
    step = step_record_from_document(_step_document("op-claim-0001", "step-claim-0001"))

    with ControlDbUnitOfWork(db_path, now=lambda: LATER_TIME) as unit_of_work:
        assert (
            unit_of_work.operations.insert_operation_with_initial_step(operation, step)
            is TransitionDisposition.APPLY
        )
        actions = OperationLifecycleActions(
            unit_of_work.operations,
            transaction_now=unit_of_work.transaction_now,
        )
        assert actions.claim_one("worker-1", "lease-1") is not None

    with ControlDbUnitOfWork(db_path, read_only=True, now=lambda: LATER_TIME) as unit_of_work:
        persisted_operation = unit_of_work.operations.get_operation(operation.operation_id)
        persisted_step = unit_of_work.operations.get_step(step.step_id)
        assert persisted_operation.status is OperationStatus.RUNNING
        assert persisted_step.status is StepStatus.RUNNING
        assert persisted_step.worker_id == "worker-1"
        assert persisted_step.lease_token == "lease-1"
        assert persisted_step.lease_expires_at == LATER_TIME + timedelta(seconds=30)


def test_lifecycle_and_owner_share_commit_and_rollback_boundary(tmp_path: Path) -> None:
    db_path = tmp_path / "control.sqlite3"
    initialize_control_db(db_path, now=lambda: MIGRATION_TIME)
    operation = operation_record_from_document(_operation_document("op-action-0001"))
    step = step_record_from_document(_step_document("op-action-0001", "step-action-0001"))

    with ControlDbUnitOfWork(db_path, now=lambda: LATER_TIME) as unit_of_work:
        unit_of_work.connection.execute("CREATE TABLE synthetic_owner(value TEXT NOT NULL)")
        unit_of_work.operations.insert_operation_with_initial_step(operation, step)
        actions = OperationLifecycleActions(
            unit_of_work.operations,
            transaction_now=unit_of_work.transaction_now,
        )
        assert actions.claim_one("worker-1", "lease-1") is not None
        unit_of_work.connection.execute("INSERT INTO synthetic_owner VALUES (?)", ("committed",))

    rollback_operation = operation_record_from_document(_operation_document("op-action-0002"))
    rollback_step = step_record_from_document(
        _step_document("op-action-0002", "step-action-0002")
    )
    with pytest.raises(RuntimeError, match="synthetic rollback"):
        with ControlDbUnitOfWork(db_path, now=lambda: LATER_TIME) as unit_of_work:
            unit_of_work.operations.insert_operation_with_initial_step(
                rollback_operation,
                rollback_step,
            )
            actions = OperationLifecycleActions(
                unit_of_work.operations,
                transaction_now=unit_of_work.transaction_now,
            )
            assert actions.claim_one("worker-1", "lease-1") is not None
            unit_of_work.connection.execute(
                "INSERT INTO synthetic_owner VALUES (?)", ("rolled-back",)
            )
            raise RuntimeError("synthetic rollback")

    with ControlDbUnitOfWork(db_path, read_only=True, now=lambda: LATER_TIME) as unit_of_work:
        assert unit_of_work.operations.get_operation(operation.operation_id).status is OperationStatus.RUNNING
        with pytest.raises(RecordNotFound):
            unit_of_work.operations.get_operation(rollback_operation.operation_id)
        assert [
            row[0]
            for row in unit_of_work.connection.execute(
                "SELECT value FROM synthetic_owner ORDER BY value"
            ).fetchall()
        ] == ["committed"]


def test_successor_conflict_rolls_back_prior_step_completion(tmp_path: Path) -> None:
    db_path = tmp_path / "control.sqlite3"
    initialize_control_db(db_path, now=lambda: MIGRATION_TIME)
    operation = operation_record_from_document(_operation_document("op-action-0003"))
    step = step_record_from_document(_step_document("op-action-0003", "step-action-0003"))
    successor = step_record_from_document(
        _step_document("op-action-0003", "step-successor-0003", step_name="successor")
    )

    with ControlDbUnitOfWork(db_path, now=lambda: LATER_TIME) as unit_of_work:
        unit_of_work.operations.insert_operation_with_initial_step(operation, step)

    with pytest.raises(ConflictingDuplicate):
        with ControlDbUnitOfWork(db_path, now=lambda: LATER_TIME) as unit_of_work:
            actions = OperationLifecycleActions(
                unit_of_work.operations,
                transaction_now=unit_of_work.transaction_now,
            )
            claimed = actions.claim_one("worker-1", "lease-1")
            assert claimed is not None
            _, claimed_step = claimed
            terminal = dataclasses.replace(
                claimed_step,
                status=StepStatus.SUCCEEDED,
                updated_at=LATER_TIME + timedelta(seconds=1),
                completed_at=LATER_TIME + timedelta(seconds=1),
                worker_id=None,
                lease_token=None,
                lease_expires_at=None,
                optimistic_version=2,
            )
            conflicting_successor = dataclasses.replace(
                successor,
                step_id=step.step_id,
                step_name="conflict",
            )
            actions.complete_with_successor(
                terminal,
                WritePrecondition(
                    expected_optimistic_version=1,
                    worker_id="worker-1",
                    lease_token="lease-1",
                ),
                conflicting_successor,
            )

    with ControlDbUnitOfWork(db_path, read_only=True, now=lambda: LATER_TIME) as unit_of_work:
        assert unit_of_work.operations.get_operation(operation.operation_id).status is OperationStatus.QUEUED
        assert unit_of_work.operations.get_step(step.step_id).status is StepStatus.PENDING


def test_uow_samples_transaction_clock_once(tmp_path: Path) -> None:
    db_path = tmp_path / "control.sqlite3"
    initialize_control_db(db_path, now=lambda: MIGRATION_TIME)
    calls = 0

    def now() -> datetime:
        nonlocal calls
        calls += 1
        return LATER_TIME

    with ControlDbUnitOfWork(db_path, read_only=True, now=now) as unit_of_work:
        unit_of_work.connection.execute("SELECT 1").fetchone()
    assert calls == 1


def test_owner_and_operation_share_commit_and_rollback_boundary(tmp_path: Path) -> None:
    db_path = tmp_path / "control.sqlite3"
    initialize_control_db(db_path, now=lambda: MIGRATION_TIME)
    operation = operation_record_from_document(_operation_document("op-owner-0001"))
    step = step_record_from_document(_step_document("op-owner-0001", "step-owner-0001"))

    with ControlDbUnitOfWork(db_path, now=lambda: MIGRATION_TIME) as unit_of_work:
        unit_of_work.connection.execute(
            "CREATE TABLE synthetic_owner(value TEXT NOT NULL)"
        )
        assert (
            unit_of_work.operations.insert_operation_with_initial_step(operation, step)
            is TransitionDisposition.APPLY
        )
        unit_of_work.connection.execute("INSERT INTO synthetic_owner VALUES (?)", ("committed",))

    with ControlDbUnitOfWork(db_path, read_only=True, now=lambda: LATER_TIME) as unit_of_work:
        assert unit_of_work.operations.get_operation(operation.operation_id) == operation
        assert [
            row[0]
            for row in unit_of_work.connection.execute(
                "SELECT value FROM synthetic_owner"
            ).fetchall()
        ] == ["committed"]

    rollback_operation = operation_record_from_document(_operation_document("op-owner-0002"))
    rollback_step = step_record_from_document(_step_document("op-owner-0002", "step-owner-0002"))
    with pytest.raises(RuntimeError, match="synthetic rollback"):
        with ControlDbUnitOfWork(db_path, now=lambda: MIGRATION_TIME) as unit_of_work:
            assert (
                unit_of_work.operations.insert_operation_with_initial_step(
                    rollback_operation,
                    rollback_step,
                )
                is TransitionDisposition.APPLY
            )
            unit_of_work.connection.execute(
                "INSERT INTO synthetic_owner VALUES (?)", ("rolled-back",)
            )
            raise RuntimeError("synthetic rollback")

    with ControlDbUnitOfWork(db_path, read_only=True, now=lambda: LATER_TIME) as unit_of_work:
        with pytest.raises(RecordNotFound):
            unit_of_work.operations.get_operation(rollback_operation.operation_id)
        assert [
            row[0]
            for row in unit_of_work.connection.execute(
                "SELECT value FROM synthetic_owner ORDER BY value"
            ).fetchall()
        ] == ["committed"]
