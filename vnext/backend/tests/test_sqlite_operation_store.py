"""SQLite operation row mapping unit tests."""

from __future__ import annotations

import dataclasses
import json
import sqlite3
from datetime import datetime, timedelta

import pytest

from gateway_backend.infrastructure.control_db.sqlite_operations import (
    SQLiteOperationStore,
    operation_record_from_row,
    operation_record_to_row,
    step_record_from_row,
    step_record_to_row,
)
from gateway_backend.infrastructure.control_db.schema import bootstrap_control_db_schema
from gateway_backend.operations import (
    OPERATION_RUNTIME_CONTRACT_VERSION,
    ConflictingDuplicate,
    LeaseExpired,
    OperationDiagnostic,
    OperationDiagnosticDetail,
    OperationDiagnosticSide,
    OperationRecord,
    OperationStore,
    OperationStatus,
    MAX_PAGE_LIMIT,
    RecordNotFound,
    StepRecord,
    StepStatus,
    StaleWrite,
    TransitionDisposition,
    WritePrecondition,
    operation_record_from_document,
    step_record_from_document,
)
from gateway_backend.operations import CorruptPersistedRecord
from gateway_backend.operations.persistence import OperationLifecycleActions

pytestmark = pytest.mark.unit

TIMESTAMP = "2024-01-02T03:04:05.678901Z"
LATER_TIMESTAMP = "2024-01-02T03:05:05.678901Z"
RETRY_TIMESTAMP = "2024-01-02T03:06:05.678901Z"
AFTER_RETRY_TIMESTAMP = "2024-01-02T03:07:05.678901Z"
RAW_SHA = "sha256:" + "a" * 64


def _artifact_ref_dict(identifier: str) -> dict[str, object]:
    return {
        "artifact_id": identifier,
        "media_type": "application/octet-stream",
        "size_bytes": 3,
        "raw_sha256": RAW_SHA,
    }


def _operation_document(**changes: object) -> dict[str, object]:
    document: dict[str, object] = {
        "artifact_refs": [
            _artifact_ref_dict("operation-artifact-1"),
            _artifact_ref_dict("operation-artifact-2"),
        ],
        "business_refs": [{"kind": "workspace", "value": "workspace-1"}],
        "cancel_requested": False,
        "checkpoint_ref": _artifact_ref_dict("operation-artifact-3"),
        "completed_at": None,
        "contract_version": OPERATION_RUNTIME_CONTRACT_VERSION,
        "created_at": TIMESTAMP,
        "diagnostic": None,
        "document_type": "operation",
        "job_contract_version": "backend-vnext/import-package/v1",
        "job_kind": "import.package",
        "job_payload": {"request": {"value": 1.5}},
        "job_payload_ref": None,
        "operation_id": "op-0001",
        "optimistic_version": 0,
        "ready_closure_ref": _artifact_ref_dict("operation-artifact-4"),
        "repository_operation_id": "repo-op-0001",
        "status": "QUEUED",
        "updated_at": LATER_TIMESTAMP,
    }
    document.update(changes)
    return document


def _step_document(**changes: object) -> dict[str, object]:
    document: dict[str, object] = {
        "attempt_count": 1,
        "cancel_requested": False,
        "checkpoint_ref": _artifact_ref_dict("step-artifact-1"),
        "completed_at": None,
        "contract_version": OPERATION_RUNTIME_CONTRACT_VERSION,
        "created_at": TIMESTAMP,
        "diagnostic": {"code": "RETRY", "message": "retry later"},
        "document_type": "step",
        "lease_expires_at": None,
        "lease_token": None,
        "operation_id": "op-0001",
        "optimistic_version": 1,
        "prior_output_refs": [_artifact_ref_dict("step-artifact-2")],
        "retry_not_before": RETRY_TIMESTAMP,
        "started_at": LATER_TIMESTAMP,
        "status": "RETRY_WAIT",
        "step_id": "step-0001",
        "step_name": "validate",
        "updated_at": LATER_TIMESTAMP,
        "worker_id": None,
    }
    document.update(changes)
    return document


def _operation_record() -> OperationRecord:
    return operation_record_from_document(_operation_document())


def _step_record() -> StepRecord:
    return step_record_from_document(_step_document())


def _initial_step_record(**changes: object) -> StepRecord:
    document = _step_document()
    document.update(
        {
            "attempt_count": 0,
            "diagnostic": None,
            "optimistic_version": 0,
            "retry_not_before": None,
            "started_at": None,
            "status": "PENDING",
            "updated_at": TIMESTAMP,
            "worker_id": None,
            "lease_token": None,
            "lease_expires_at": None,
            **changes,
        }
    )
    return step_record_from_document(document)


def _memory_store(
    *,
    transaction_now: str = TIMESTAMP,
) -> tuple[sqlite3.Connection, SQLiteOperationStore]:
    connection = sqlite3.connect(":memory:", isolation_level=None)
    connection.row_factory = sqlite3.Row
    bootstrap_control_db_schema(connection)
    connection.execute("BEGIN IMMEDIATE")
    return connection, SQLiteOperationStore(
        connection,
        transaction_now=datetime_from_text(transaction_now),
    )


def datetime_from_text(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def test_operation_mapping_round_trips_all_composite_fields() -> None:
    record = _operation_record()
    row = operation_record_to_row(record)

    assert row["job_payload"] == b'{"request":{"value":1.5}}'
    assert isinstance(row["business_refs"], bytes)
    assert isinstance(row["artifact_refs"], bytes)
    assert operation_record_from_row(row) == record


def test_operation_mapping_round_trips_diagnostic_details_json_blob() -> None:
    diagnostic = OperationDiagnostic(
        code="UNSUPPORTED_TABLE",
        message="2 projection failures",
        details=(
            OperationDiagnosticDetail(
                code="UNSUPPORTED_TABLE",
                side=OperationDiagnosticSide.MODIFIED,
                table_name="broken_b",
                column_name="bad_b",
            ),
            OperationDiagnosticDetail(
                code="UNSUPPORTED_TABLE",
                side=OperationDiagnosticSide.MODIFIED,
                table_name="broken_a",
                column_name="bad_a",
            ),
        ),
        omitted_count=0,
    )
    record = dataclasses.replace(
        _operation_record(),
        status=OperationStatus.FAILED,
        diagnostic=diagnostic,
        completed_at=datetime_from_text(LATER_TIMESTAMP),
        optimistic_version=1,
    )

    row = operation_record_to_row(record)

    assert isinstance(row["diagnostic"], bytes)
    assert json.loads(row["diagnostic"]) == diagnostic.to_document()
    assert operation_record_from_row(row) == record


def test_step_mapping_round_trips_retry_metadata_and_refs() -> None:
    record = _step_record()
    row = step_record_to_row(record)

    assert row["eligible_at_us"] == row["retry_not_before_us"]
    assert isinstance(row["prior_output_refs"], bytes)
    assert step_record_from_row(row) == record


def test_timestamp_mapping_preserves_microsecond_boundaries() -> None:
    record = operation_record_from_document(
        _operation_document(
            created_at="0001-01-01T00:00:00.000001Z",
            updated_at="9999-12-31T23:59:59.999999Z",
        )
    )
    assert operation_record_from_row(operation_record_to_row(record)) == record


CORRUPT_OPERATION_ROWS = (
    ("business blob is not JSON", {"business_refs": b"not-json"}),
    ("business JSON has wrong root", {"business_refs": b"{}"}),
    ("non-canonical JSON blob", {"business_refs": b'[{"kind":"workspace", "value":"workspace-1"}]'}),
    ("scalar has wrong type", {"optimistic_version": "0"}),
    ("scalar is outside the R1 range", {"optimistic_version": -1}),
    ("boolean has invalid integer", {"cancel_requested": 2}),
    ("enum has unknown value", {"status": "UNKNOWN"}),
    ("contract version is unknown", {"contract_version": "backend-vnext/operation-runtime/v1"}),
    ("canonical JSON is not UTF-8", {"job_payload": b"\xff"}),
    ("composite binding is inconsistent", {"job_payload": None, "job_payload_ref": None}),
)


@pytest.mark.parametrize(("name", "changes"), CORRUPT_OPERATION_ROWS)
def test_operation_row_corruption_is_owner_specific(
    name: str,
    changes: dict[str, object],
) -> None:
    row = operation_record_to_row(_operation_record())
    row.update(changes)
    with pytest.raises(CorruptPersistedRecord, match="operation row"):
        operation_record_from_row(row)


CORRUPT_STEP_ROWS = (
    ("canonical blob is truncated", {"prior_output_refs": b"["}),
    ("scalar has wrong type", {"attempt_count": "1"}),
    ("scalar is negative", {"attempt_count": -1}),
    ("boolean has invalid integer", {"cancel_requested": 2}),
    ("eligible metadata is inconsistent", {"eligible_at_us": 0}),
    ("status has unknown value", {"status": "UNKNOWN", "eligible_at_us": None}),
    ("contract version is unknown", {"contract_version": "backend-vnext/operation-runtime/v1"}),
)

CLAIM_LOCAL_VALIDATION_FAILURES = (
    ("R1 worker identity", "worker\n1", "lease-1", 0, "control characters"),
    ("Step version increment", "worker-1", "lease-1", (2**53) - 1, "I-JSON safe integer"),
)

UNKNOWN_ACTIVE_STATUS_ROWS = (
    ("operation", "operation_records", "operation_id", "op-0001"),
    ("step", "step_records", "step_id", "step-0001"),
)


@pytest.mark.parametrize(("name", "changes"), CORRUPT_STEP_ROWS)
def test_step_row_corruption_is_owner_specific(
    name: str,
    changes: dict[str, object],
) -> None:
    row = step_record_to_row(_step_record())
    row.update(changes)
    with pytest.raises(CorruptPersistedRecord, match="step row"):
        step_record_from_row(row)


def test_pending_step_uses_created_time_and_terminal_step_has_no_eligibility() -> None:
    pending = step_record_from_document(
        _step_document(
            attempt_count=0,
            diagnostic=None,
            retry_not_before=None,
            started_at=None,
            status="PENDING",
            updated_at=TIMESTAMP,
        )
    )
    assert step_record_to_row(pending)["eligible_at_us"] == step_record_to_row(pending)["created_at_us"]

    terminal = step_record_from_document(
        _step_document(
            completed_at=LATER_TIMESTAMP,
            diagnostic=None,
            retry_not_before=None,
            status="CANCELLED",
            updated_at=LATER_TIMESTAMP,
        )
    )
    assert step_record_to_row(terminal)["eligible_at_us"] is None


def test_active_integrity_scan_is_bounded_keyset_and_checks_operations_before_steps() -> None:
    connection, store = _memory_store()
    try:
        for index in range(2):
            operation = dataclasses.replace(
                _operation_record(),
                operation_id=f"op-integrity-{index}",
            )
            step = dataclasses.replace(
                _initial_step_record(),
                operation_id=operation.operation_id,
                step_id=f"step-integrity-{index}",
            )
            assert (
                store.insert_operation_with_initial_step(operation, step)
                is TransitionDisposition.APPLY
            )

        pages = []
        cursor = None
        while True:
            page = store.scan_active_integrity(cursor=cursor, limit=1)
            pages.append(page)
            cursor = page.next_cursor
            if cursor is None:
                break

        assert [(page.operations_scanned, page.steps_scanned) for page in pages] == [
            (1, 0),
            (1, 0),
            (0, 1),
            (0, 1),
        ]
        assert sum(page.operations_scanned for page in pages) == 2
        assert sum(page.steps_scanned for page in pages) == 2
    finally:
        connection.close()


def test_active_integrity_scan_rejects_corruption_without_repairing_the_row() -> None:
    connection, store = _memory_store()
    try:
        operation = _operation_record()
        step = _initial_step_record()
        store.insert_operation_with_initial_step(operation, step)
        connection.execute(
            "UPDATE operation_records SET business_refs = ? WHERE operation_id = ?",
            (b"not-json", operation.operation_id),
        )

        with pytest.raises(CorruptPersistedRecord, match="operation row"):
            store.scan_active_integrity()
        assert connection.execute(
            "SELECT business_refs FROM operation_records WHERE operation_id = ?",
            (operation.operation_id,),
        ).fetchone()[0] == b"not-json"
    finally:
        connection.close()


@pytest.mark.parametrize(
    ("owner", "table", "identity_column", "identity"),
    UNKNOWN_ACTIVE_STATUS_ROWS,
)
def test_active_integrity_scan_fails_closed_on_unknown_status(
    owner: str,
    table: str,
    identity_column: str,
    identity: str,
) -> None:
    connection, store = _memory_store()
    try:
        operation = _operation_record()
        step = _initial_step_record()
        store.insert_operation_with_initial_step(operation, step)
        connection.execute("PRAGMA ignore_check_constraints = ON")
        connection.execute(
            f"UPDATE {table} SET status = ? WHERE {identity_column} = ?",
            ("UNKNOWN", identity),
        )

        with pytest.raises(CorruptPersistedRecord, match=f"{owner} row"):
            store.scan_active_integrity()
    finally:
        connection.close()


def test_active_integrity_scan_rejects_step_owned_by_terminal_operation() -> None:
    connection, store = _memory_store()
    try:
        operation = _operation_record()
        step = _initial_step_record()
        store.insert_operation_with_initial_step(operation, step)
        at_us = operation_record_to_row(operation)["updated_at_us"]
        connection.execute(
            """
            UPDATE operation_records
            SET status = 'SUCCEEDED', completed_at_us = ?, updated_at_us = ?
            WHERE operation_id = ?
            """,
            (at_us, at_us, operation.operation_id),
        )

        with pytest.raises(CorruptPersistedRecord, match="terminal operation"):
            store.scan_active_integrity()
    finally:
        connection.close()


def test_terminal_corruption_is_not_part_of_active_integrity_scan() -> None:
    connection, store = _memory_store()
    try:
        operation = _operation_record()
        step = _initial_step_record()
        store.insert_operation_with_initial_step(operation, step)
        operation_row = operation_record_to_row(operation)
        at_us = operation_row["updated_at_us"]
        connection.execute(
            """
            UPDATE operation_records
            SET status = 'SUCCEEDED', completed_at_us = ?, updated_at_us = ?, business_refs = ?
            WHERE operation_id = ?
            """,
            (at_us, at_us, b"not-json", operation.operation_id),
        )
        connection.execute(
            """
            UPDATE step_records
            SET status = 'CANCELLED', completed_at_us = ?, updated_at_us = ?, eligible_at_us = NULL,
                prior_output_refs = ?
            WHERE step_id = ?
            """,
            (at_us, at_us, b"[", step.step_id),
        )

        page = store.scan_active_integrity()
        assert (page.operations_scanned, page.steps_scanned, page.next_cursor) == (0, 0, None)
        with pytest.raises(CorruptPersistedRecord):
            store.get_operation(operation.operation_id)
        with pytest.raises(CorruptPersistedRecord):
            store.get_step(step.step_id)
    finally:
        connection.close()


@pytest.mark.parametrize("limit", [0, -1, MAX_PAGE_LIMIT + 1])
def test_active_integrity_scan_rejects_unbounded_limits(limit: int) -> None:
    connection, store = _memory_store()
    try:
        with pytest.raises(ValueError, match="limit"):
            store.scan_active_integrity(limit=limit)
    finally:
        connection.close()


def test_active_integrity_scan_rejects_malformed_cursor() -> None:
    connection, store = _memory_store()
    try:
        with pytest.raises(ValueError, match="integrity cursor"):
            store.scan_active_integrity(cursor="not-a-cursor")
    finally:
        connection.close()


@pytest.mark.parametrize(
    ("case_name", "worker_id", "lease_token", "step_version", "message"),
    CLAIM_LOCAL_VALIDATION_FAILURES,
)
def test_claim_local_validation_does_not_commit_a_cross_table_prefix(
    case_name: str,
    worker_id: str,
    lease_token: str,
    step_version: int,
    message: str,
) -> None:
    del case_name
    connection, store = _memory_store(transaction_now=LATER_TIMESTAMP)
    try:
        operation = _operation_record()
        step = _initial_step_record(optimistic_version=step_version)
        store.insert_operation_with_initial_step(operation, step)
        actions = OperationLifecycleActions(
            store,
            transaction_now=datetime_from_text(LATER_TIMESTAMP),
        )

        with pytest.raises(ValueError, match=message):
            actions.claim_one(worker_id, lease_token)

        assert store.get_operation(operation.operation_id) == operation
        assert store.get_step(step.step_id) == step
    finally:
        connection.close()


def test_store_create_readback_and_claim_candidate_round_trip() -> None:
    connection, store = _memory_store()
    try:
        assert isinstance(store, OperationStore)
        operation = _operation_record()
        step = _initial_step_record()

        assert (
            store.insert_operation_with_initial_step(operation, step)
            is TransitionDisposition.APPLY
        )
        assert store.get_operation(operation.operation_id) == operation
        assert store.get_step(step.step_id) == step

        candidates, next_cursor = store.list_claim_candidates(
            store.transaction_now,
        )
        assert len(candidates) == 1
        assert candidates[0].operation_id == operation.operation_id
        assert candidates[0].step_id == step.step_id
        assert candidates[0].job_step_key.job_kind == operation.job_kind
        assert next_cursor is None
        with pytest.raises(ValueError, match="transaction clock"):
            store.list_claim_candidates(datetime_from_text(LATER_TIMESTAMP))
    finally:
        connection.close()


def test_create_is_exactly_idempotent_and_rejects_conflicting_duplicates() -> None:
    connection, store = _memory_store()
    try:
        operation = _operation_record()
        step = _initial_step_record()
        assert store.insert_operation_with_initial_step(operation, step) is TransitionDisposition.APPLY
        assert (
            store.insert_operation_with_initial_step(operation, step)
            is TransitionDisposition.IDEMPOTENT
        )

        conflicting_operation = dataclasses.replace(operation, job_kind="import.other")
        with pytest.raises(ConflictingDuplicate):
            store.insert_operation_with_initial_step(conflicting_operation, step)
    finally:
        connection.close()

    connection, store = _memory_store()
    try:
        operation = _operation_record()
        step = _initial_step_record()
        assert store.insert_operation_with_initial_step(operation, step) is TransitionDisposition.APPLY
        conflicting_step = dataclasses.replace(step, step_name="other")
        with pytest.raises(ConflictingDuplicate):
            store.insert_operation_with_initial_step(operation, conflicting_step)
    finally:
        connection.close()


def test_reads_report_missing_records_and_keyset_pages_are_bounded() -> None:
    connection, store = _memory_store()
    try:
        with pytest.raises(RecordNotFound):
            store.get_operation("missing-operation")
        with pytest.raises(RecordNotFound):
            store.get_step("missing-step")

        for index in range(3):
            operation = dataclasses.replace(
                _operation_record(),
                operation_id=f"op-{index:04d}",
            )
            step = dataclasses.replace(
                _initial_step_record(),
                operation_id=operation.operation_id,
                step_id=f"step-{index:04d}",
                step_name=f"validate-{index}",
            )
            store.insert_operation_with_initial_step(operation, step)

        first, cursor = store.list_operations_by_status(OperationStatus.QUEUED, limit=1)
        assert [record.operation_id for record in first] == ["op-0000"]
        assert cursor is not None
        second, cursor = store.list_operations_by_status(
            OperationStatus.QUEUED,
            cursor=cursor,
            limit=1,
        )
        assert [record.operation_id for record in second] == ["op-0001"]
        assert cursor is not None

        with pytest.raises(ValueError, match="cursor"):
            store.list_operations_by_status(OperationStatus.QUEUED, cursor="not-a-cursor")
        with pytest.raises(ValueError, match="cursor status"):
            store.list_operations_by_status(OperationStatus.RUNNING, cursor=cursor)
    finally:
        connection.close()


def test_step_keyset_page_and_successor_idempotency() -> None:
    connection, store = _memory_store()
    try:
        operation = _operation_record()
        first_step = _initial_step_record()
        store.insert_operation_with_initial_step(operation, first_step)

        cancelled = dataclasses.replace(
            first_step,
            status=StepStatus.CANCELLED,
            updated_at=datetime_from_text(LATER_TIMESTAMP),
            completed_at=datetime_from_text(LATER_TIMESTAMP),
            optimistic_version=1,
        )
        assert (
            store.compare_and_set_step(
                cancelled,
                WritePrecondition(expected_optimistic_version=0, worker_id=None, lease_token=None),
            )
            is TransitionDisposition.APPLY
        )
        successor = _initial_step_record(
            operation_id=operation.operation_id,
            step_id="step-0002",
            step_name="successor",
            created_at=LATER_TIMESTAMP,
            updated_at=LATER_TIMESTAMP,
        )
        assert store.insert_successor_step(successor) is TransitionDisposition.APPLY
        assert store.insert_successor_step(successor) is TransitionDisposition.IDEMPOTENT

        first, cursor = store.list_steps(operation.operation_id, limit=1)
        assert [record.step_id for record in first] == [first_step.step_id]
        assert cursor is not None
        second, next_cursor = store.list_steps(operation.operation_id, cursor=cursor, limit=1)
        assert [record.step_id for record in second] == [successor.step_id]
        assert next_cursor is None
    finally:
        connection.close()


def test_guarded_cas_applies_stale_writes_and_terminal_duplicates_correctly() -> None:
    connection, store = _memory_store()
    try:
        operation = _operation_record()
        step = _initial_step_record()
        store.insert_operation_with_initial_step(operation, step)

        running_operation = dataclasses.replace(
            operation,
            status=OperationStatus.RUNNING,
            optimistic_version=1,
            updated_at=datetime_from_text(LATER_TIMESTAMP),
        )
        assert (
            store.compare_and_set_operation(
                running_operation,
                WritePrecondition(expected_optimistic_version=0, worker_id=None, lease_token=None),
            )
            is TransitionDisposition.APPLY
        )
        running_step = dataclasses.replace(
            step,
            status=StepStatus.RUNNING,
            attempt_count=1,
            started_at=datetime_from_text(LATER_TIMESTAMP),
            worker_id="worker-1",
            lease_token="lease-1",
            lease_expires_at=datetime_from_text(RETRY_TIMESTAMP),
            updated_at=datetime_from_text(LATER_TIMESTAMP),
            optimistic_version=1,
        )
        assert (
            store.compare_and_set_step(
                running_step,
                WritePrecondition(expected_optimistic_version=0, worker_id=None, lease_token=None),
            )
            is TransitionDisposition.APPLY
        )
        terminal_step = dataclasses.replace(
            running_step,
            status=StepStatus.SUCCEEDED,
            updated_at=datetime_from_text(RETRY_TIMESTAMP),
            completed_at=datetime_from_text(RETRY_TIMESTAMP),
            worker_id=None,
            lease_token=None,
            lease_expires_at=None,
            optimistic_version=2,
        )
        assert (
            store.compare_and_set_step(
                terminal_step,
                WritePrecondition(
                    expected_optimistic_version=1,
                    worker_id="worker-1",
                    lease_token="lease-1",
                ),
            )
            is TransitionDisposition.APPLY
        )

        failed_operation = dataclasses.replace(
            running_operation,
            status=OperationStatus.FAILED,
            optimistic_version=2,
            diagnostic=OperationDiagnostic(code="FAILED", message="failed"),
            completed_at=datetime_from_text(LATER_TIMESTAMP),
        )
        assert (
            store.compare_and_set_operation(
                failed_operation,
                WritePrecondition(expected_optimistic_version=1, worker_id=None, lease_token=None),
            )
            is TransitionDisposition.APPLY
        )
        assert (
            store.compare_and_set_operation(
                failed_operation,
                WritePrecondition(expected_optimistic_version=2, worker_id=None, lease_token=None),
            )
            is TransitionDisposition.IDEMPOTENT
        )
    finally:
        connection.close()


def test_stale_operation_write_poisoning_rejects_a_later_valid_cas() -> None:
    connection, store = _memory_store(transaction_now=LATER_TIMESTAMP)
    try:
        operation = _operation_record()
        step = _initial_step_record()
        store.insert_operation_with_initial_step(operation, step)
        running_operation = dataclasses.replace(
            operation,
            status=OperationStatus.RUNNING,
            optimistic_version=1,
            updated_at=datetime_from_text(LATER_TIMESTAMP),
        )
        store.compare_and_set_operation(
            running_operation,
            WritePrecondition(expected_optimistic_version=0, worker_id=None, lease_token=None),
        )
        stale_candidate = dataclasses.replace(
            running_operation,
            updated_at=datetime_from_text(RETRY_TIMESTAMP),
            optimistic_version=2,
        )
        with pytest.raises(StaleWrite):
            store.compare_and_set_operation(
                stale_candidate,
                WritePrecondition(expected_optimistic_version=0, worker_id=None, lease_token=None),
            )
        valid_follow_up = dataclasses.replace(
            running_operation,
            updated_at=datetime_from_text(RETRY_TIMESTAMP),
            optimistic_version=2,
        )
        with pytest.raises(RuntimeError, match="rollback-only"):
            store.compare_and_set_operation(
                valid_follow_up,
                WritePrecondition(expected_optimistic_version=1, worker_id=None, lease_token=None),
            )
    finally:
        connection.close()


def test_lifecycle_actions_reject_a_mismatched_transaction_clock() -> None:
    connection, store = _memory_store(transaction_now=TIMESTAMP)
    try:
        with pytest.raises(ValueError, match="transaction clock"):
            OperationLifecycleActions(
                store,
                transaction_now=datetime_from_text(LATER_TIMESTAMP),
            )
    finally:
        connection.close()


def test_terminal_operation_publication_rejects_an_active_step() -> None:
    connection, store = _memory_store(transaction_now=LATER_TIMESTAMP)
    try:
        operation = _operation_record()
        step = _initial_step_record()
        store.insert_operation_with_initial_step(operation, step)
        running_operation = dataclasses.replace(
            operation,
            status=OperationStatus.RUNNING,
            optimistic_version=1,
            updated_at=datetime_from_text(LATER_TIMESTAMP),
        )
        store.compare_and_set_operation(
            running_operation,
            WritePrecondition(expected_optimistic_version=0, worker_id=None, lease_token=None),
        )
        terminal_operation = dataclasses.replace(
            running_operation,
            status=OperationStatus.SUCCEEDED,
            optimistic_version=2,
            updated_at=datetime_from_text(RETRY_TIMESTAMP),
            completed_at=datetime_from_text(RETRY_TIMESTAMP),
        )
        with pytest.raises(ConflictingDuplicate, match="active step"):
            store.compare_and_set_operation(
                terminal_operation,
                WritePrecondition(expected_optimistic_version=1, worker_id=None, lease_token=None),
            )
        assert store.get_operation(operation.operation_id) == running_operation
        assert store.get_step(step.step_id) == step
    finally:
        connection.close()


def test_terminal_operation_rejects_direct_successor_insertion() -> None:
    connection, store = _memory_store(transaction_now=LATER_TIMESTAMP)
    try:
        operation = _operation_record()
        step = _initial_step_record()
        store.insert_operation_with_initial_step(operation, step)
        running_step = dataclasses.replace(
            step,
            status=StepStatus.RUNNING,
            attempt_count=1,
            started_at=datetime_from_text(LATER_TIMESTAMP),
            worker_id="worker-1",
            lease_token="lease-1",
            lease_expires_at=datetime_from_text(RETRY_TIMESTAMP),
            updated_at=datetime_from_text(LATER_TIMESTAMP),
            optimistic_version=1,
        )
        store.compare_and_set_step(
            running_step,
            WritePrecondition(expected_optimistic_version=0, worker_id=None, lease_token=None),
        )
        terminal_step = dataclasses.replace(
            running_step,
            status=StepStatus.SUCCEEDED,
            optimistic_version=2,
            updated_at=datetime_from_text(RETRY_TIMESTAMP),
            completed_at=datetime_from_text(RETRY_TIMESTAMP),
            worker_id=None,
            lease_token=None,
            lease_expires_at=None,
        )
        store.compare_and_set_step(
            terminal_step,
            WritePrecondition(
                expected_optimistic_version=1,
                worker_id="worker-1",
                lease_token="lease-1",
            ),
        )
        running_operation = dataclasses.replace(
            operation,
            status=OperationStatus.RUNNING,
            optimistic_version=1,
            updated_at=datetime_from_text(LATER_TIMESTAMP),
        )
        store.compare_and_set_operation(
            running_operation,
            WritePrecondition(expected_optimistic_version=0, worker_id=None, lease_token=None),
        )
        terminal_operation = dataclasses.replace(
            running_operation,
            status=OperationStatus.SUCCEEDED,
            optimistic_version=2,
            updated_at=datetime_from_text(RETRY_TIMESTAMP),
            completed_at=datetime_from_text(RETRY_TIMESTAMP),
        )
        store.compare_and_set_operation(
            terminal_operation,
            WritePrecondition(expected_optimistic_version=1, worker_id=None, lease_token=None),
        )
        successor = _initial_step_record(
            step_id="step-successor-terminal",
            step_name="successor",
        )
        with pytest.raises(ConflictingDuplicate, match="terminal operation"):
            store.insert_successor_step(successor)
        assert store.get_operation(operation.operation_id) == terminal_operation
        with pytest.raises(RecordNotFound):
            store.get_step(successor.step_id)
    finally:
        connection.close()


def test_terminal_operation_retry_rejects_an_existing_active_successor() -> None:
    connection, store = _memory_store(transaction_now=LATER_TIMESTAMP)
    try:
        operation = _operation_record()
        step = _initial_step_record()
        store.insert_operation_with_initial_step(operation, step)
        actions = OperationLifecycleActions(
            store,
            transaction_now=datetime_from_text(LATER_TIMESTAMP),
        )
        claimed = actions.claim_one("worker-1", "lease-1")
        assert claimed is not None
        claimed_operation, claimed_step = claimed
        at = datetime_from_text(RETRY_TIMESTAMP)
        terminal_step = dataclasses.replace(
            claimed_step,
            status=StepStatus.SUCCEEDED,
            optimistic_version=2,
            updated_at=at,
            completed_at=at,
            worker_id=None,
            lease_token=None,
            lease_expires_at=None,
        )
        successor = _initial_step_record(
            step_id="step-successor-retry",
            step_name="successor",
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
            updated_at=at,
            completed_at=at,
        )
        with pytest.raises(ConflictingDuplicate, match="active step"):
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
        assert store.get_operation(operation.operation_id) == claimed_operation
        assert store.get_step(step.step_id) == terminal_step
        assert store.get_step(successor.step_id) == successor
    finally:
        connection.close()


def test_live_lease_guard_rejects_expired_step_without_mutating_it() -> None:
    connection, store = _memory_store(transaction_now=AFTER_RETRY_TIMESTAMP)
    try:
        operation = _operation_record()
        step = _initial_step_record()
        store.insert_operation_with_initial_step(operation, step)
        running = dataclasses.replace(
            step,
            status=StepStatus.RUNNING,
            attempt_count=1,
            optimistic_version=1,
            started_at=datetime_from_text(LATER_TIMESTAMP),
            updated_at=datetime_from_text(LATER_TIMESTAMP),
            worker_id="worker-1",
            lease_token="lease-1",
            lease_expires_at=datetime_from_text(RETRY_TIMESTAMP),
        )
        with pytest.raises(LeaseExpired):
            store.compare_and_set_step(
                running,
                WritePrecondition(expected_optimistic_version=0, worker_id=None, lease_token=None),
                require_live_lease=True,
            )
        assert store.get_step(step.step_id) == step
    finally:
        connection.close()


def test_lifecycle_claim_is_bounded_deterministic_and_promotes_queued_operation() -> None:
    connection, store = _memory_store(transaction_now=LATER_TIMESTAMP)
    try:
        operation = _operation_record()
        step = _initial_step_record()
        store.insert_operation_with_initial_step(operation, step)
        actions = OperationLifecycleActions(
            store,
            transaction_now=datetime_from_text(LATER_TIMESTAMP),
        )

        claimed = actions.claim_one("worker-1", "lease-1")
        assert claimed is not None
        claimed_operation, claimed_step = claimed
        assert claimed_operation.status is OperationStatus.RUNNING
        assert claimed_operation.optimistic_version == 1
        assert claimed_step.status is StepStatus.RUNNING
        assert claimed_step.attempt_count == 1
        assert claimed_step.started_at == datetime_from_text(LATER_TIMESTAMP)
        assert claimed_step.lease_expires_at == datetime_from_text(LATER_TIMESTAMP) + timedelta(
            seconds=30
        )
        assert actions.claim_one("worker-2", "lease-2") is None
    finally:
        connection.close()


def test_lifecycle_claim_reclaims_due_retry_step_with_incremented_attempt() -> None:
    connection, store = _memory_store(transaction_now=AFTER_RETRY_TIMESTAMP)
    try:
        operation = _operation_record()
        step = _initial_step_record()
        store.insert_operation_with_initial_step(operation, step)
        actions = OperationLifecycleActions(
            store,
            transaction_now=datetime_from_text(AFTER_RETRY_TIMESTAMP),
        )
        first_claim = actions.claim_one("worker-1", "lease-1")
        assert first_claim is not None
        _, claimed_step = first_claim
        retry_wait = dataclasses.replace(
            claimed_step,
            status=StepStatus.RETRY_WAIT,
            diagnostic=OperationDiagnostic(code="RETRY", message="retry later"),
            retry_not_before=datetime_from_text(AFTER_RETRY_TIMESTAMP),
            updated_at=datetime_from_text(AFTER_RETRY_TIMESTAMP),
            worker_id=None,
            lease_token=None,
            lease_expires_at=None,
            optimistic_version=2,
        )
        assert (
            store.compare_and_set_step(
                retry_wait,
                WritePrecondition(
                    expected_optimistic_version=1,
                    worker_id="worker-1",
                    lease_token="lease-1",
                ),
                require_live_lease=True,
            )
            is TransitionDisposition.APPLY
        )
        reclaimed = actions.claim_one("worker-2", "lease-2")
        assert reclaimed is not None
        _, reclaimed_step = reclaimed
        assert reclaimed_step.attempt_count == 2
        assert reclaimed_step.started_at == claimed_step.started_at
        assert reclaimed_step.status is StepStatus.RUNNING
    finally:
        connection.close()


def test_claim_candidate_query_excludes_manual_operation() -> None:
    connection, store = _memory_store(transaction_now=LATER_TIMESTAMP)
    try:
        operation = _operation_record()
        step = _initial_step_record()
        store.insert_operation_with_initial_step(operation, step)
        running = dataclasses.replace(
            operation,
            status=OperationStatus.RUNNING,
            optimistic_version=1,
            updated_at=datetime_from_text(LATER_TIMESTAMP),
        )
        store.compare_and_set_operation(
            running,
            WritePrecondition(expected_optimistic_version=0, worker_id=None, lease_token=None),
        )
        manual = dataclasses.replace(
            running,
            status=OperationStatus.MANUAL_RECOVERY_REQUIRED,
            optimistic_version=2,
            diagnostic=OperationDiagnostic(code="MANUAL", message="operator required"),
        )
        store.compare_and_set_operation(
            manual,
            WritePrecondition(expected_optimistic_version=1, worker_id=None, lease_token=None),
        )
        actions = OperationLifecycleActions(
            store,
            transaction_now=datetime_from_text(LATER_TIMESTAMP),
        )
        assert actions.claim_one("worker-1", "lease-1") is None
    finally:
        connection.close()


def test_live_step_actions_extend_lease_reject_swap_and_publish_terminal_idempotently() -> None:
    connection, store = _memory_store(transaction_now=LATER_TIMESTAMP)
    try:
        operation = _operation_record()
        step = _initial_step_record()
        store.insert_operation_with_initial_step(operation, step)
        actions = OperationLifecycleActions(
            store,
            transaction_now=datetime_from_text(LATER_TIMESTAMP),
        )
        claimed = actions.claim_one("worker-1", "lease-1")
        assert claimed is not None
        claimed_operation, claimed_step = claimed
        assert claimed_operation.status is OperationStatus.RUNNING

        heartbeat = dataclasses.replace(
            claimed_step,
            updated_at=datetime_from_text(LATER_TIMESTAMP) + timedelta(seconds=5),
            lease_expires_at=datetime_from_text(LATER_TIMESTAMP) + timedelta(seconds=60),
            optimistic_version=2,
        )
        assert (
            actions.mutate_live_step(
                heartbeat,
                WritePrecondition(
                    expected_optimistic_version=1,
                    worker_id="worker-1",
                    lease_token="lease-1",
                ),
            )
            is TransitionDisposition.APPLY
        )

        terminal = dataclasses.replace(
            heartbeat,
            status=StepStatus.SUCCEEDED,
            updated_at=datetime_from_text(LATER_TIMESTAMP) + timedelta(seconds=10),
            completed_at=datetime_from_text(LATER_TIMESTAMP) + timedelta(seconds=10),
            worker_id=None,
            lease_token=None,
            lease_expires_at=None,
            optimistic_version=3,
        )
        assert (
            actions.mutate_live_step(
                terminal,
                WritePrecondition(
                    expected_optimistic_version=2,
                    worker_id="worker-1",
                    lease_token="lease-1",
                ),
            )
            is TransitionDisposition.APPLY
        )
        assert (
            actions.mutate_live_step(
                terminal,
                WritePrecondition(expected_optimistic_version=3, worker_id=None, lease_token=None),
            )
            is TransitionDisposition.IDEMPOTENT
        )
    finally:
        connection.close()


def test_live_step_actions_reject_worker_lease_swap() -> None:
    connection, store = _memory_store(transaction_now=LATER_TIMESTAMP)
    try:
        operation = _operation_record()
        step = _initial_step_record()
        store.insert_operation_with_initial_step(operation, step)
        actions = OperationLifecycleActions(
            store,
            transaction_now=datetime_from_text(LATER_TIMESTAMP),
        )
        claimed = actions.claim_one("worker-1", "lease-1")
        assert claimed is not None
        _, claimed_step = claimed
        heartbeat = dataclasses.replace(
            claimed_step,
            updated_at=datetime_from_text(LATER_TIMESTAMP) + timedelta(seconds=5),
            lease_expires_at=datetime_from_text(LATER_TIMESTAMP) + timedelta(seconds=60),
            optimistic_version=2,
        )
        assert (
            actions.mutate_live_step(
                heartbeat,
                WritePrecondition(
                    expected_optimistic_version=1,
                    worker_id="worker-1",
                    lease_token="lease-1",
                ),
            )
            is TransitionDisposition.APPLY
        )
        swapped = dataclasses.replace(
            heartbeat,
            worker_id="worker-2",
            optimistic_version=3,
        )
        with pytest.raises(ValueError, match="worker_id and lease_token"):
            actions.mutate_live_step(
                swapped,
                WritePrecondition(
                    expected_optimistic_version=2,
                    worker_id="worker-1",
                    lease_token="lease-1",
                ),
            )
    finally:
        connection.close()


def test_live_step_stale_write_poisoning_rejects_follow_up_mutation() -> None:
    connection, store = _memory_store(transaction_now=LATER_TIMESTAMP)
    try:
        operation = _operation_record()
        step = _initial_step_record()
        store.insert_operation_with_initial_step(operation, step)
        actions = OperationLifecycleActions(
            store,
            transaction_now=datetime_from_text(LATER_TIMESTAMP),
        )
        claimed = actions.claim_one("worker-1", "lease-1")
        assert claimed is not None
        _, claimed_step = claimed
        heartbeat = dataclasses.replace(
            claimed_step,
            updated_at=datetime_from_text(LATER_TIMESTAMP) + timedelta(seconds=5),
            lease_expires_at=datetime_from_text(LATER_TIMESTAMP) + timedelta(seconds=60),
            optimistic_version=2,
        )
        assert (
            actions.mutate_live_step(
                heartbeat,
                WritePrecondition(
                    expected_optimistic_version=1,
                    worker_id="worker-1",
                    lease_token="lease-1",
                ),
            )
            is TransitionDisposition.APPLY
        )
        stale_candidate = dataclasses.replace(
            heartbeat,
            updated_at=datetime_from_text(LATER_TIMESTAMP) + timedelta(seconds=6),
            optimistic_version=3,
        )
        with pytest.raises(StaleWrite):
            actions.mutate_live_step(
                stale_candidate,
                WritePrecondition(
                    expected_optimistic_version=1,
                    worker_id="worker-1",
                    lease_token="lease-1",
                ),
            )
        with pytest.raises(RuntimeError, match="rollback-only"):
            actions.mutate_live_step(
                dataclasses.replace(
                    heartbeat,
                    updated_at=datetime_from_text(LATER_TIMESTAMP) + timedelta(seconds=6),
                    optimistic_version=3,
                ),
                WritePrecondition(
                    expected_optimistic_version=2,
                    worker_id="worker-1",
                    lease_token="lease-1",
                ),
            )
    finally:
        connection.close()


def test_live_step_and_operation_terminal_action_is_atomic() -> None:
    connection, store = _memory_store(transaction_now=LATER_TIMESTAMP)
    try:
        operation = _operation_record()
        step = _initial_step_record()
        store.insert_operation_with_initial_step(operation, step)
        actions = OperationLifecycleActions(
            store,
            transaction_now=datetime_from_text(LATER_TIMESTAMP),
        )
        claimed = actions.claim_one("worker-1", "lease-1")
        assert claimed is not None
        claimed_operation, claimed_step = claimed
        at = datetime_from_text(LATER_TIMESTAMP) + timedelta(seconds=1)
        terminal_step = dataclasses.replace(
            claimed_step,
            status=StepStatus.SUCCEEDED,
            updated_at=at,
            completed_at=at,
            worker_id=None,
            lease_token=None,
            lease_expires_at=None,
            optimistic_version=2,
        )
        terminal_operation = dataclasses.replace(
            claimed_operation,
            status=OperationStatus.SUCCEEDED,
            updated_at=at,
            completed_at=at,
            optimistic_version=2,
        )
        assert actions.complete_operation(
            terminal_step,
            WritePrecondition(
                expected_optimistic_version=1,
                worker_id="worker-1",
                lease_token="lease-1",
            ),
            terminal_operation,
            WritePrecondition(expected_optimistic_version=1, worker_id=None, lease_token=None),
        ) == (TransitionDisposition.APPLY, TransitionDisposition.APPLY)
        assert actions.complete_operation(
            terminal_step,
            WritePrecondition(expected_optimistic_version=2, worker_id=None, lease_token=None),
            terminal_operation,
            WritePrecondition(expected_optimistic_version=2, worker_id=None, lease_token=None),
        ) == (TransitionDisposition.IDEMPOTENT, TransitionDisposition.IDEMPOTENT)
        assert store.get_operation(operation.operation_id).status is OperationStatus.SUCCEEDED
        assert store.get_step(step.step_id).status is StepStatus.SUCCEEDED
    finally:
        connection.close()


def test_live_step_action_rejects_expired_lease_without_mutation() -> None:
    connection, store = _memory_store(transaction_now=AFTER_RETRY_TIMESTAMP)
    try:
        operation = _operation_record()
        step = _initial_step_record()
        store.insert_operation_with_initial_step(operation, step)
        running = dataclasses.replace(
            step,
            status=StepStatus.RUNNING,
            attempt_count=1,
            optimistic_version=1,
            started_at=datetime_from_text(LATER_TIMESTAMP),
            updated_at=datetime_from_text(LATER_TIMESTAMP),
            worker_id="worker-1",
            lease_token="lease-1",
            lease_expires_at=datetime_from_text(RETRY_TIMESTAMP),
        )
        store.compare_and_set_step(
            running,
            WritePrecondition(expected_optimistic_version=0, worker_id=None, lease_token=None),
        )
        candidate = dataclasses.replace(running, optimistic_version=2)
        actions = OperationLifecycleActions(
            store,
            transaction_now=datetime_from_text(AFTER_RETRY_TIMESTAMP),
        )
        with pytest.raises(LeaseExpired):
            actions.mutate_live_step(
                candidate,
                WritePrecondition(
                    expected_optimistic_version=1,
                    worker_id="worker-1",
                    lease_token="lease-1",
                ),
            )
        assert store.get_step(step.step_id) == running
    finally:
        connection.close()


def test_cancel_intent_is_atomic_and_requires_live_running_lease() -> None:
    connection, store = _memory_store(transaction_now=LATER_TIMESTAMP)
    try:
        operation = _operation_record()
        step = _initial_step_record()
        store.insert_operation_with_initial_step(operation, step)
        actions = OperationLifecycleActions(
            store,
            transaction_now=datetime_from_text(LATER_TIMESTAMP),
        )
        claimed = actions.claim_one("worker-1", "lease-1")
        assert claimed is not None
        claimed_operation, claimed_step = claimed
        operation_cancel = dataclasses.replace(
            claimed_operation,
            cancel_requested=True,
            updated_at=datetime_from_text(LATER_TIMESTAMP) + timedelta(seconds=1),
            optimistic_version=2,
        )
        step_cancel = dataclasses.replace(
            claimed_step,
            cancel_requested=True,
            updated_at=datetime_from_text(LATER_TIMESTAMP) + timedelta(seconds=1),
            optimistic_version=2,
        )
        assert actions.cancel_intent(
            operation_cancel,
            WritePrecondition(expected_optimistic_version=1, worker_id=None, lease_token=None),
            step_cancel,
            WritePrecondition(
                expected_optimistic_version=1,
                worker_id="worker-1",
                lease_token="lease-1",
            ),
        ) == (TransitionDisposition.APPLY, TransitionDisposition.APPLY)
        assert store.get_operation(operation.operation_id).cancel_requested is True
        assert store.get_step(step.step_id).cancel_requested is True
    finally:
        connection.close()


def test_completion_compositions_use_caller_candidates_and_keep_successor_pending() -> None:
    connection, store = _memory_store(transaction_now=LATER_TIMESTAMP)
    try:
        operation = _operation_record()
        step = _initial_step_record()
        store.insert_operation_with_initial_step(operation, step)
        actions = OperationLifecycleActions(
            store,
            transaction_now=datetime_from_text(LATER_TIMESTAMP),
        )
        claimed = actions.claim_one("worker-1", "lease-1")
        assert claimed is not None
        claimed_operation, claimed_step = claimed
        terminal = dataclasses.replace(
            claimed_step,
            status=StepStatus.SUCCEEDED,
            updated_at=datetime_from_text(LATER_TIMESTAMP) + timedelta(seconds=1),
            completed_at=datetime_from_text(LATER_TIMESTAMP) + timedelta(seconds=1),
            worker_id=None,
            lease_token=None,
            lease_expires_at=None,
            optimistic_version=2,
        )
        successor = _initial_step_record(
            operation_id=operation.operation_id,
            step_id="step-0002",
            step_name="successor",
            created_at=LATER_TIMESTAMP,
            updated_at=LATER_TIMESTAMP,
        )
        assert actions.complete_with_successor(
            terminal,
            WritePrecondition(
                expected_optimistic_version=1,
                worker_id="worker-1",
                lease_token="lease-1",
            ),
            successor,
        ) == (TransitionDisposition.APPLY, TransitionDisposition.APPLY)
        assert store.get_step(step.step_id).status is StepStatus.SUCCEEDED
        assert store.get_step(successor.step_id) == successor
        assert store.get_operation(operation.operation_id) == claimed_operation
    finally:
        connection.close()
