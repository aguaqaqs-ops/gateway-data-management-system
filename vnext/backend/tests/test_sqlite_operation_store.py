"""SQLite operation row mapping unit tests."""

from __future__ import annotations

import pytest

from gateway_backend.infrastructure.control_db.sqlite_operations import (
    operation_record_from_row,
    operation_record_to_row,
    step_record_from_row,
    step_record_to_row,
)
from gateway_backend.operations import (
    OPERATION_RUNTIME_CONTRACT_VERSION,
    OperationRecord,
    StepRecord,
    operation_record_from_document,
    step_record_from_document,
)
from gateway_backend.operations import CorruptPersistedRecord

pytestmark = pytest.mark.unit

TIMESTAMP = "2024-01-02T03:04:05.678901Z"
LATER_TIMESTAMP = "2024-01-02T03:05:05.678901Z"
RETRY_TIMESTAMP = "2024-01-02T03:06:05.678901Z"
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


def test_operation_mapping_round_trips_all_composite_fields() -> None:
    record = _operation_record()
    row = operation_record_to_row(record)

    assert row["job_payload"] == b'{"request":{"value":1.5}}'
    assert isinstance(row["business_refs"], bytes)
    assert isinstance(row["artifact_refs"], bytes)
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
    ("boolean has invalid integer", {"cancel_requested": 2}),
    ("enum has unknown value", {"status": "UNKNOWN"}),
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
    ("boolean has invalid integer", {"cancel_requested": 2}),
    ("eligible metadata is inconsistent", {"eligible_at_us": 0}),
    ("status has unknown value", {"status": "UNKNOWN", "eligible_at_us": None}),
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
