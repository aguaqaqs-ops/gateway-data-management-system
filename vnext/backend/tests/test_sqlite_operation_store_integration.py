"""File-backed SQLite control DB integration tests."""

from __future__ import annotations

import dataclasses
import os
import selectors
import signal
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from pathlib import Path
from threading import Barrier, Event

import pytest

from gateway_backend.infrastructure.control_db import (
    ControlDbUnitOfWork,
    connect_control_db,
    initialize_control_db,
)
from gateway_backend.infrastructure.control_db import control_db_connect
from gateway_backend.infrastructure.control_db.schema import bootstrap_control_db_schema
from gateway_backend.infrastructure.control_db.sqlite_operations import SQLiteOperationStore
from gateway_backend.operations import (
    OPERATION_RUNTIME_CONTRACT_VERSION,
    CorruptPersistedRecord,
    ConflictingDuplicate,
    OperationDiagnostic,
    OperationDiagnosticDetail,
    OperationDiagnosticSide,
    OperationStatus,
    RecordNotFound,
    StepStatus,
    StaleWrite,
    StoreBusy,
    TransitionDisposition,
    WritePrecondition,
    operation_record_from_document,
    step_record_from_document,
)
from gateway_backend.operations.persistence import OperationLifecycleActions

pytestmark = pytest.mark.integration

FIXED_TRANSACTION_TIME = datetime(2024, 1, 2, 3, 4, 5, tzinfo=UTC)
LATER_TIME = datetime(2024, 1, 2, 3, 5, 5, tzinfo=UTC)

CLAIM_LOCAL_VALIDATION_FAILURES = (
    ("R1 worker identity", "worker\n1", "lease-1", 0, "control characters"),
    ("Step version increment", "worker-1", "lease-1", (2**53) - 1, "I-JSON safe integer"),
)

UNKNOWN_ACTIVE_STATUS_ROWS = (
    ("operation", "operation_records", "operation_id", "op-unknown-status-0001"),
    ("step", "step_records", "step_id", "step-unknown-status-0001"),
)


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
    initialize_control_db(db_path)

    connection = connect_control_db(db_path)
    assert connection.execute("PRAGMA journal_mode").fetchone()[0] == "wal"
    assert connection.execute("PRAGMA foreign_keys").fetchone()[0] == 1
    assert connection.execute("PRAGMA synchronous").fetchone()[0] == 2
    assert connection.execute("PRAGMA busy_timeout").fetchone()[0] == 5_000
    connection.close()

    reopened = connect_control_db(db_path)
    try:
        assert reopened.execute("PRAGMA journal_mode").fetchone()[0] == "wal"
        assert reopened.execute("PRAGMA foreign_keys").fetchone()[0] == 1
        assert reopened.execute("PRAGMA synchronous").fetchone()[0] == 2
        assert reopened.execute("PRAGMA busy_timeout").fetchone()[0] == 5_000
        assert reopened.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table' AND name = 'step_records'"
        ).fetchone()[0] == "step_records"
    finally:
        reopened.close()


def test_file_backed_transaction_visibility_is_atomic_across_connections(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "control.sqlite3"
    initialize_control_db(db_path)
    operation = operation_record_from_document(_operation_document("op-wal-0001"))
    step = step_record_from_document(_step_document("op-wal-0001", "step-wal-0001"))

    with ControlDbUnitOfWork(db_path, now=lambda: LATER_TIME) as writer:
        assert (
            writer.operations.insert_operation_with_initial_step(operation, step)
            is TransitionDisposition.APPLY
        )
        with ControlDbUnitOfWork(db_path, read_only=True, now=lambda: LATER_TIME) as reader:
            with pytest.raises(RecordNotFound):
                reader.operations.get_operation(operation.operation_id)
            with pytest.raises(RecordNotFound):
                reader.operations.get_step(step.step_id)

    with ControlDbUnitOfWork(db_path, read_only=True, now=lambda: LATER_TIME) as reader:
        assert reader.operations.get_operation(operation.operation_id) == operation
        assert reader.operations.get_step(step.step_id) == step

    rollback_operation = operation_record_from_document(_operation_document("op-wal-0002"))
    rollback_step = step_record_from_document(
        _step_document("op-wal-0002", "step-wal-0002")
    )
    with pytest.raises(RuntimeError, match="synthetic rollback"):
        with ControlDbUnitOfWork(db_path, now=lambda: LATER_TIME) as writer:
            writer.operations.insert_operation_with_initial_step(
                rollback_operation,
                rollback_step,
            )
            raise RuntimeError("synthetic rollback")

    with ControlDbUnitOfWork(db_path, read_only=True, now=lambda: LATER_TIME) as reader:
        with pytest.raises(RecordNotFound):
            reader.operations.get_operation(rollback_operation.operation_id)
        with pytest.raises(RecordNotFound):
            reader.operations.get_step(rollback_step.step_id)


def test_file_backed_stale_cas_preserves_the_newer_connection_result(tmp_path: Path) -> None:
    db_path = tmp_path / "control.sqlite3"
    initialize_control_db(db_path)
    operation = operation_record_from_document(_operation_document("op-wal-cas-0001"))
    step = step_record_from_document(_step_document("op-wal-cas-0001", "step-wal-cas-0001"))

    with ControlDbUnitOfWork(db_path, now=lambda: LATER_TIME) as writer:
        writer.operations.insert_operation_with_initial_step(operation, step)

    # Connection A reads version 0 before connection B advances the row.
    connection_a = connect_control_db(db_path)
    connection_a.execute("BEGIN")
    store_a = SQLiteOperationStore(
        connection_a,
        transaction_now=LATER_TIME,
        read_only=True,
    )
    stale_operation = store_a.get_operation(operation.operation_id)
    connection_a.execute("COMMIT")
    running_operation = dataclasses.replace(
        stale_operation,
        status=OperationStatus.RUNNING,
        optimistic_version=1,
        updated_at=LATER_TIME,
    )
    with ControlDbUnitOfWork(db_path, now=lambda: LATER_TIME) as writer:
        assert (
            writer.operations.compare_and_set_operation(
                running_operation,
                WritePrecondition(expected_optimistic_version=0, worker_id=None, lease_token=None),
            )
            is TransitionDisposition.APPLY
        )

    failed_operation = dataclasses.replace(
        stale_operation,
        status=OperationStatus.FAILED,
        diagnostic=OperationDiagnostic(code="FAILED", message="stale candidate"),
        completed_at=LATER_TIME,
        updated_at=LATER_TIME,
        optimistic_version=2,
    )
    try:
        connection_a.execute("BEGIN IMMEDIATE")
        store_a = SQLiteOperationStore(
            connection_a,
            transaction_now=LATER_TIME,
        )
        with pytest.raises(StaleWrite):
            store_a.compare_and_set_operation(
                failed_operation,
                WritePrecondition(expected_optimistic_version=0, worker_id=None, lease_token=None),
            )
    finally:
        if connection_a.in_transaction:
            connection_a.execute("ROLLBACK")
        connection_a.close()

    with ControlDbUnitOfWork(db_path, read_only=True, now=lambda: LATER_TIME) as reader:
        assert reader.operations.get_operation(operation.operation_id) == running_operation


@pytest.mark.serial
def test_file_backed_writer_contention_maps_to_store_busy(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db_path = tmp_path / "control.sqlite3"
    initialize_control_db(db_path)
    monkeypatch.setattr(control_db_connect, "BUSY_TIMEOUT_MS", 0)
    holder = connect_control_db(db_path)
    holder.execute("BEGIN IMMEDIATE")
    started = Event()

    def attempt_second_writer() -> bool:
        started.set()
        try:
            with ControlDbUnitOfWork(db_path, now=lambda: LATER_TIME):
                pass
        except StoreBusy:
            return True
        return False

    executor = ThreadPoolExecutor(max_workers=1)
    future = executor.submit(attempt_second_writer)
    try:
        assert started.wait(timeout=5)
        assert future.result(timeout=5) is True
    finally:
        if holder.in_transaction:
            holder.execute("ROLLBACK")
        holder.close()
        executor.shutdown(wait=True)


def test_unit_of_work_commits_and_rolls_back_on_same_connection(tmp_path: Path) -> None:
    db_path = tmp_path / "control.sqlite3"
    initialize_control_db(db_path)

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
            bootstrap_control_db_schema(connection)
        finally:
            connection.close()

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(lambda _item: bootstrap_from_independent_connection(), (1, 2)))
    assert results == [None, None]

    connection = connect_control_db(db_path)
    try:
        assert connection.execute("PRAGMA journal_mode").fetchone()[0] == "wal"
        assert connection.execute("PRAGMA foreign_keys").fetchone()[0] == 1
        assert connection.execute("PRAGMA synchronous").fetchone()[0] == 2
        assert connection.execute(
            "SELECT name FROM sqlite_master "
            "WHERE type = 'index' AND name = 'step_records_one_active_per_operation'"
        ).fetchone()[0] == "step_records_one_active_per_operation"
    finally:
        connection.close()


@pytest.mark.serial
def test_file_backed_process_termination_rolls_back_uncommitted_probe(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "control.sqlite3"
    initialize_control_db(db_path)
    with ControlDbUnitOfWork(db_path, now=lambda: FIXED_TRANSACTION_TIME) as unit_of_work:
        unit_of_work.connection.execute(
            "CREATE TABLE crash_probe(value TEXT NOT NULL UNIQUE)"
        )

    child_code = """
from pathlib import Path
import sys

sys.path.insert(0, str(Path.cwd() / "src"))
from gateway_backend.infrastructure.control_db import connect_control_db

connection = connect_control_db(Path(sys.argv[1]))
connection.execute("BEGIN IMMEDIATE")
connection.execute("INSERT INTO crash_probe(value) VALUES (?)", ("child",))
print("READY", flush=True)
sys.stdin.buffer.read(1)
"""
    child = subprocess.Popen(
        [sys.executable, "-c", child_code, str(db_path)],
        cwd=Path(__file__).parents[1],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    selector = selectors.DefaultSelector()
    assert child.stdout is not None
    selector.register(child.stdout, selectors.EVENT_READ)
    try:
        assert selector.select(timeout=5)
        assert child.stdout.readline().strip() == "READY"

        with ControlDbUnitOfWork(db_path, read_only=True, now=lambda: LATER_TIME) as reader:
            assert reader.connection.execute(
                "SELECT value FROM crash_probe ORDER BY value"
            ).fetchall() == []

        os.kill(child.pid, signal.SIGKILL)
        assert child.wait(timeout=5) == -signal.SIGKILL
    finally:
        selector.close()
        if child.poll() is None:
            child.kill()
            child.wait(timeout=5)
        if child.stdin is not None:
            child.stdin.close()
        if child.stdout is not None:
            child.stdout.close()
        if child.stderr is not None:
            child.stderr.close()

    with ControlDbUnitOfWork(db_path, read_only=True, now=lambda: LATER_TIME) as reader:
        assert reader.connection.execute(
            "SELECT value FROM crash_probe ORDER BY value"
        ).fetchall() == []

    with ControlDbUnitOfWork(db_path, now=lambda: LATER_TIME) as writer:
        writer.connection.execute(
            "INSERT INTO crash_probe(value) VALUES (?)", ("parent",)
        )

    reopened = connect_control_db(db_path)
    try:
        assert reopened.execute("PRAGMA journal_mode").fetchone()[0] == "wal"
        assert [
            row[0]
            for row in reopened.execute(
                "SELECT value FROM crash_probe ORDER BY value"
            ).fetchall()
        ] == ["parent"]
    finally:
        reopened.close()


def test_operation_store_commits_and_reads_back_after_reopen(tmp_path: Path) -> None:
    db_path = tmp_path / "control.sqlite3"
    initialize_control_db(db_path)
    operation_document = _operation_document("op-file-0001")
    operation_document["diagnostic"] = {
        "code": "PROJECTION_FAILED",
        "message": "2 projection diagnostics",
        "details": [
            {
                "code": "UNKNOWN_COLUMN",
                "side": OperationDiagnosticSide.MODIFIED.value,
                "table_name": "accounts",
                "column_name": "status",
            },
            {
                "code": "UNKNOWN_TABLE",
                "side": OperationDiagnosticSide.INITIAL.value,
                "table_name": "legacy_accounts",
                "column_name": None,
            },
        ],
        "omitted_count": 0,
    }
    operation = operation_record_from_document(operation_document)
    assert operation.diagnostic == OperationDiagnostic(
        code="PROJECTION_FAILED",
        message="2 projection diagnostics",
        details=(
            OperationDiagnosticDetail(
                code="UNKNOWN_COLUMN",
                side=OperationDiagnosticSide.MODIFIED,
                table_name="accounts",
                column_name="status",
            ),
            OperationDiagnosticDetail(
                code="UNKNOWN_TABLE",
                side=OperationDiagnosticSide.INITIAL,
                table_name="legacy_accounts",
                column_name=None,
            ),
        ),
        omitted_count=0,
    )
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


def test_file_backed_active_integrity_scan_rejects_orphan_step_after_reopen(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "control.sqlite3"
    initialize_control_db(db_path)
    operation = operation_record_from_document(_operation_document("op-orphan-0001"))
    step = step_record_from_document(_step_document("op-orphan-0001", "step-orphan-0001"))

    with ControlDbUnitOfWork(db_path, now=lambda: LATER_TIME) as unit_of_work:
        unit_of_work.operations.insert_operation_with_initial_step(operation, step)

    connection = connect_control_db(db_path)
    try:
        connection.execute("PRAGMA foreign_keys=OFF")
        connection.execute(
            "DELETE FROM operation_records WHERE operation_id = ?",
            (operation.operation_id,),
        )
        connection.execute("PRAGMA foreign_keys=ON")
    finally:
        connection.close()

    with ControlDbUnitOfWork(db_path, read_only=True, now=lambda: LATER_TIME) as unit_of_work:
        with pytest.raises(CorruptPersistedRecord, match="owning operation"):
            unit_of_work.operations.scan_active_integrity()


def test_lifecycle_claim_commits_and_reads_back_after_reopen(tmp_path: Path) -> None:
    db_path = tmp_path / "control.sqlite3"
    initialize_control_db(db_path)
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


@pytest.mark.parametrize(
    ("case_name", "worker_id", "lease_token", "step_version", "message"),
    CLAIM_LOCAL_VALIDATION_FAILURES,
)
def test_caught_claim_local_validation_rolls_back_without_a_prefix(
    tmp_path: Path,
    case_name: str,
    worker_id: str,
    lease_token: str,
    step_version: int,
    message: str,
) -> None:
    del case_name
    db_path = tmp_path / "control.sqlite3"
    initialize_control_db(db_path)
    operation = operation_record_from_document(_operation_document("op-claim-validation-0001"))
    step = step_record_from_document(
        _step_document("op-claim-validation-0001", "step-claim-validation-0001")
        | {"optimistic_version": step_version}
    )

    with ControlDbUnitOfWork(db_path, now=lambda: LATER_TIME) as unit_of_work:
        unit_of_work.operations.insert_operation_with_initial_step(operation, step)

    with ControlDbUnitOfWork(db_path, now=lambda: LATER_TIME) as unit_of_work:
        actions = OperationLifecycleActions(
            unit_of_work.operations,
            transaction_now=unit_of_work.transaction_now,
        )
        with pytest.raises(ValueError, match=message):
            actions.claim_one(worker_id, lease_token)

    with ControlDbUnitOfWork(db_path, read_only=True, now=lambda: LATER_TIME) as reader:
        assert reader.operations.get_operation(operation.operation_id) == operation
        assert reader.operations.get_step(step.step_id) == step


@pytest.mark.parametrize(
    ("owner", "table", "identity_column", "identity"),
    UNKNOWN_ACTIVE_STATUS_ROWS,
)
def test_file_backed_active_integrity_scan_fails_closed_on_unknown_status(
    tmp_path: Path,
    owner: str,
    table: str,
    identity_column: str,
    identity: str,
) -> None:
    db_path = tmp_path / "control.sqlite3"
    initialize_control_db(db_path)
    operation = operation_record_from_document(_operation_document("op-unknown-status-0001"))
    step = step_record_from_document(
        _step_document("op-unknown-status-0001", "step-unknown-status-0001")
    )

    with ControlDbUnitOfWork(db_path, now=lambda: LATER_TIME) as unit_of_work:
        unit_of_work.operations.insert_operation_with_initial_step(operation, step)

    connection = connect_control_db(db_path)
    try:
        connection.execute("PRAGMA ignore_check_constraints = ON")
        connection.execute(
            f"UPDATE {table} SET status = ? WHERE {identity_column} = ?",
            ("UNKNOWN", identity),
        )
    finally:
        connection.close()

    with ControlDbUnitOfWork(db_path, read_only=True, now=lambda: LATER_TIME) as reader:
        with pytest.raises(CorruptPersistedRecord, match=f"{owner} row"):
            reader.operations.scan_active_integrity()
        if owner == "operation":
            with pytest.raises(CorruptPersistedRecord, match="operation row"):
                reader.operations.get_operation(operation.operation_id)
        else:
            with pytest.raises(CorruptPersistedRecord, match="step row"):
                reader.operations.get_step(step.step_id)


def test_lifecycle_and_owner_share_commit_and_rollback_boundary(tmp_path: Path) -> None:
    db_path = tmp_path / "control.sqlite3"
    initialize_control_db(db_path)
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


def test_caught_cancel_second_leg_failure_rolls_back_the_whole_uow(tmp_path: Path) -> None:
    db_path = tmp_path / "control.sqlite3"
    initialize_control_db(db_path)
    operation = operation_record_from_document(_operation_document("op-caught-cancel-0001"))
    step = step_record_from_document(_step_document("op-caught-cancel-0001", "step-caught-cancel-0001"))

    with ControlDbUnitOfWork(db_path, now=lambda: LATER_TIME) as unit_of_work:
        unit_of_work.operations.insert_operation_with_initial_step(operation, step)

    with ControlDbUnitOfWork(db_path, now=lambda: LATER_TIME) as unit_of_work:
        actions = OperationLifecycleActions(
            unit_of_work.operations,
            transaction_now=unit_of_work.transaction_now,
        )
        claimed = actions.claim_one("worker-1", "lease-1")
        assert claimed is not None
        claimed_operation, claimed_step = claimed
        operation_cancel = dataclasses.replace(
            claimed_operation,
            cancel_requested=True,
            optimistic_version=2,
            updated_at=LATER_TIME + timedelta(seconds=1),
        )
        step_cancel = dataclasses.replace(
            claimed_step,
            cancel_requested=True,
            optimistic_version=2,
            updated_at=LATER_TIME + timedelta(seconds=1),
        )
        with pytest.raises(StaleWrite):
            actions.cancel_intent(
                operation_cancel,
                WritePrecondition(
                    expected_optimistic_version=1,
                    worker_id=None,
                    lease_token=None,
                ),
                step_cancel,
                WritePrecondition(
                    expected_optimistic_version=0,
                    worker_id="worker-1",
                    lease_token="lease-1",
                ),
            )

    with ControlDbUnitOfWork(db_path, read_only=True, now=lambda: LATER_TIME) as reader:
        persisted_operation = reader.operations.get_operation(operation.operation_id)
        persisted_step = reader.operations.get_step(step.step_id)
        assert persisted_operation.status is OperationStatus.QUEUED
        assert persisted_operation.cancel_requested is False
        assert persisted_step.status is StepStatus.PENDING
        assert persisted_step.cancel_requested is False


def test_caught_successor_second_leg_failure_rolls_back_the_whole_uow(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "control.sqlite3"
    initialize_control_db(db_path)
    operation = operation_record_from_document(_operation_document("op-caught-successor-0001"))
    step = step_record_from_document(
        _step_document("op-caught-successor-0001", "step-caught-successor-0001")
    )

    with ControlDbUnitOfWork(db_path, now=lambda: LATER_TIME) as unit_of_work:
        unit_of_work.operations.insert_operation_with_initial_step(operation, step)

    with ControlDbUnitOfWork(db_path, now=lambda: LATER_TIME) as unit_of_work:
        actions = OperationLifecycleActions(
            unit_of_work.operations,
            transaction_now=unit_of_work.transaction_now,
        )
        claimed = actions.claim_one("worker-1", "lease-1")
        assert claimed is not None
        _, claimed_step = claimed
        terminal_step = dataclasses.replace(
            claimed_step,
            status=StepStatus.SUCCEEDED,
            optimistic_version=2,
            updated_at=LATER_TIME + timedelta(seconds=1),
            completed_at=LATER_TIME + timedelta(seconds=1),
            worker_id=None,
            lease_token=None,
            lease_expires_at=None,
        )
        conflicting_successor = dataclasses.replace(
            step,
            step_name="conflicting-successor",
        )
        with pytest.raises(ConflictingDuplicate):
            actions.complete_with_successor(
                terminal_step,
                WritePrecondition(
                    expected_optimistic_version=1,
                    worker_id="worker-1",
                    lease_token="lease-1",
                ),
                conflicting_successor,
            )

    with ControlDbUnitOfWork(db_path, read_only=True, now=lambda: LATER_TIME) as reader:
        assert reader.operations.get_operation(operation.operation_id).status is OperationStatus.QUEUED
        assert reader.operations.get_step(step.step_id).status is StepStatus.PENDING
        assert reader.operations.get_step(step.step_id).step_name == "validate"


def test_rollback_only_rejects_a_later_valid_create(tmp_path: Path) -> None:
    db_path = tmp_path / "control.sqlite3"
    initialize_control_db(db_path)
    operation = operation_record_from_document(_operation_document("op-poison-create-0001"))
    step = step_record_from_document(_step_document("op-poison-create-0001", "step-poison-create-0001"))
    later_operation = operation_record_from_document(
        _operation_document("op-poison-create-0002")
    )
    later_step = step_record_from_document(
        _step_document("op-poison-create-0002", "step-poison-create-0002")
    )

    with ControlDbUnitOfWork(db_path, now=lambda: LATER_TIME) as unit_of_work:
        unit_of_work.operations.insert_operation_with_initial_step(operation, step)

    with ControlDbUnitOfWork(db_path, now=lambda: LATER_TIME) as unit_of_work:
        actions = OperationLifecycleActions(
            unit_of_work.operations,
            transaction_now=unit_of_work.transaction_now,
        )
        claimed = actions.claim_one("worker-1", "lease-1")
        assert claimed is not None
        claimed_operation, claimed_step = claimed
        with pytest.raises(StaleWrite):
            actions.cancel_intent(
                dataclasses.replace(
                    claimed_operation,
                    cancel_requested=True,
                    optimistic_version=2,
                    updated_at=LATER_TIME + timedelta(seconds=1),
                ),
                WritePrecondition(
                    expected_optimistic_version=1,
                    worker_id=None,
                    lease_token=None,
                ),
                dataclasses.replace(
                    claimed_step,
                    cancel_requested=True,
                    optimistic_version=2,
                    updated_at=LATER_TIME + timedelta(seconds=1),
                ),
                WritePrecondition(
                    expected_optimistic_version=0,
                    worker_id="worker-1",
                    lease_token="lease-1",
                ),
            )
        with pytest.raises(RuntimeError, match="rollback-only"):
            unit_of_work.operations.insert_operation_with_initial_step(
                later_operation,
                later_step,
            )

    with ControlDbUnitOfWork(db_path, read_only=True, now=lambda: LATER_TIME) as reader:
        assert reader.operations.get_operation(operation.operation_id).status is OperationStatus.QUEUED
        assert reader.operations.get_step(step.step_id).status is StepStatus.PENDING
        with pytest.raises(RecordNotFound):
            reader.operations.get_operation(later_operation.operation_id)


def test_rollback_only_rejects_a_later_valid_cas(tmp_path: Path) -> None:
    db_path = tmp_path / "control.sqlite3"
    initialize_control_db(db_path)
    operation = operation_record_from_document(_operation_document("op-poison-cas-0001"))
    step = step_record_from_document(_step_document("op-poison-cas-0001", "step-poison-cas-0001"))

    with ControlDbUnitOfWork(db_path, now=lambda: LATER_TIME) as unit_of_work:
        unit_of_work.operations.insert_operation_with_initial_step(operation, step)

    with ControlDbUnitOfWork(db_path, now=lambda: LATER_TIME) as unit_of_work:
        actions = OperationLifecycleActions(
            unit_of_work.operations,
            transaction_now=unit_of_work.transaction_now,
        )
        claimed = actions.claim_one("worker-1", "lease-1")
        assert claimed is not None
        claimed_operation, claimed_step = claimed
        with pytest.raises(StaleWrite):
            actions.cancel_intent(
                dataclasses.replace(
                    claimed_operation,
                    cancel_requested=True,
                    optimistic_version=2,
                    updated_at=LATER_TIME + timedelta(seconds=1),
                ),
                WritePrecondition(
                    expected_optimistic_version=1,
                    worker_id=None,
                    lease_token=None,
                ),
                dataclasses.replace(
                    claimed_step,
                    cancel_requested=True,
                    optimistic_version=2,
                    updated_at=LATER_TIME + timedelta(seconds=1),
                ),
                WritePrecondition(
                    expected_optimistic_version=0,
                    worker_id="worker-1",
                    lease_token="lease-1",
                ),
            )
        current_operation = unit_of_work.operations.get_operation(operation.operation_id)
        valid_follow_up = dataclasses.replace(
            current_operation,
            updated_at=LATER_TIME + timedelta(seconds=2),
            optimistic_version=current_operation.optimistic_version + 1,
        )
        with pytest.raises(RuntimeError, match="rollback-only"):
            unit_of_work.operations.compare_and_set_operation(
                valid_follow_up,
                WritePrecondition(
                    expected_optimistic_version=current_operation.optimistic_version,
                    worker_id=None,
                    lease_token=None,
                ),
            )

    with ControlDbUnitOfWork(db_path, read_only=True, now=lambda: LATER_TIME) as reader:
        assert reader.operations.get_operation(operation.operation_id).status is OperationStatus.QUEUED
        assert reader.operations.get_step(step.step_id).status is StepStatus.PENDING


def test_terminal_successor_branches_cannot_create_active_step_under_terminal_operation(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "control.sqlite3"
    initialize_control_db(db_path)
    operation = operation_record_from_document(_operation_document("op-terminal-branch-0001"))
    step = step_record_from_document(_step_document("op-terminal-branch-0001", "step-terminal-branch-0001"))
    successor = step_record_from_document(
        _step_document("op-terminal-branch-0001", "step-terminal-successor-0001", step_name="successor")
    )

    with ControlDbUnitOfWork(db_path, now=lambda: LATER_TIME) as unit_of_work:
        unit_of_work.operations.insert_operation_with_initial_step(operation, step)
        actions = OperationLifecycleActions(
            unit_of_work.operations,
            transaction_now=unit_of_work.transaction_now,
        )
        claimed = actions.claim_one("worker-1", "lease-1")
        assert claimed is not None
        claimed_operation, claimed_step = claimed
        terminal_step = dataclasses.replace(
            claimed_step,
            status=StepStatus.SUCCEEDED,
            optimistic_version=2,
            updated_at=LATER_TIME + timedelta(seconds=1),
            completed_at=LATER_TIME + timedelta(seconds=1),
            worker_id=None,
            lease_token=None,
            lease_expires_at=None,
        )
        assert actions.complete_with_successor(
            terminal_step,
            WritePrecondition(
                expected_optimistic_version=1,
                worker_id="worker-1",
                lease_token="lease-1",
            ),
            successor,
        ) == (TransitionDisposition.APPLY, TransitionDisposition.APPLY)

    terminal_operation = dataclasses.replace(
        claimed_operation,
        status=OperationStatus.SUCCEEDED,
        optimistic_version=2,
        updated_at=LATER_TIME + timedelta(seconds=1),
        completed_at=LATER_TIME + timedelta(seconds=1),
    )
    with ControlDbUnitOfWork(db_path, now=lambda: LATER_TIME) as unit_of_work:
        actions = OperationLifecycleActions(
            unit_of_work.operations,
            transaction_now=unit_of_work.transaction_now,
        )
        with pytest.raises(ConflictingDuplicate):
            actions.complete_operation(
                terminal_step,
                WritePrecondition(
                    expected_optimistic_version=2,
                    worker_id=None,
                    lease_token=None,
                ),
                terminal_operation,
                WritePrecondition(
                    expected_optimistic_version=1,
                    worker_id=None,
                    lease_token=None,
                ),
            )

    with ControlDbUnitOfWork(db_path, read_only=True, now=lambda: LATER_TIME) as reader:
        assert reader.operations.get_operation(operation.operation_id).status is OperationStatus.RUNNING
        assert reader.operations.get_step(step.step_id).status is StepStatus.SUCCEEDED
        assert reader.operations.get_step(successor.step_id) == successor
        assert reader.operations.scan_active_integrity().steps_scanned == 1


def test_successor_conflict_rolls_back_prior_step_completion(tmp_path: Path) -> None:
    db_path = tmp_path / "control.sqlite3"
    initialize_control_db(db_path)
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
    initialize_control_db(db_path)
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
    initialize_control_db(db_path)
    operation = operation_record_from_document(_operation_document("op-owner-0001"))
    step = step_record_from_document(_step_document("op-owner-0001", "step-owner-0001"))

    with ControlDbUnitOfWork(db_path, now=lambda: FIXED_TRANSACTION_TIME) as unit_of_work:
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
        with ControlDbUnitOfWork(db_path, now=lambda: FIXED_TRANSACTION_TIME) as unit_of_work:
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
