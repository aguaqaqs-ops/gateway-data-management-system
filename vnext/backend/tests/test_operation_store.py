"""SQLite-neutral Operation Store port tests."""

from __future__ import annotations

import dataclasses
import inspect
from datetime import UTC, datetime, timedelta, timezone

import pytest

import gateway_backend.operations as operations
from gateway_backend.operations import (
    DEFAULT_CLAIM_LIMIT,
    DEFAULT_PAGE_LIMIT,
    MAX_CLAIM_LIMIT,
    MAX_PAGE_LIMIT,
    ClaimCandidate,
    CorruptPersistedRecord,
    ConflictingDuplicate,
    JobStepKey,
    LeaseExpired,
    OperationStore,
    OperationUnitOfWork,
    OperationStatus,
    RecordNotFound,
    StaleWrite,
    StepStatus,
    StoreBusy,
    UnsupportedSchemaVersion,
)
from gateway_backend.operations.store import _validate_page_request

pytestmark = pytest.mark.unit


STORE_PUBLIC_EXPORTS = frozenset(
    {
        "DEFAULT_CLAIM_LIMIT",
        "DEFAULT_PAGE_LIMIT",
        "MAX_CLAIM_LIMIT",
        "MAX_PAGE_LIMIT",
        "ClaimCandidate",
        "CorruptPersistedRecord",
        "ConflictingDuplicate",
        "LeaseExpired",
        "OperationStore",
        "OperationUnitOfWork",
        "RecordNotFound",
        "StaleWrite",
        "StoreBusy",
        "UnsupportedSchemaVersion",
    }
)


def test_store_public_exports_are_controlled() -> None:
    import gateway_backend.operations.store as store

    assert frozenset(store.__all__) == STORE_PUBLIC_EXPORTS
    for symbol in STORE_PUBLIC_EXPORTS:
        assert hasattr(store, symbol)
        assert hasattr(operations, symbol)
    assert not hasattr(operations, "OperationStoreError")


def test_store_port_methods_have_frozen_signatures() -> None:
    expected_parameters = {
        "get_operation": ("self", "operation_id"),
        "get_step": ("self", "step_id"),
        "list_steps": ("self", "operation_id", "cursor", "limit"),
        "list_operations_by_status": ("self", "status", "cursor", "limit"),
        "list_claim_candidates": ("self", "now", "cursor", "limit"),
        "insert_operation_with_initial_step": ("self", "operation", "step"),
        "insert_successor_step": ("self", "step"),
        "compare_and_set_operation": ("self", "candidate", "precondition", "recovery_authorized"),
        "compare_and_set_step": (
            "self",
            "candidate",
            "precondition",
            "recovery_authorized",
            "require_live_lease",
        ),
    }
    for method_name, names in expected_parameters.items():
        signature = inspect.signature(getattr(OperationStore, method_name))
        assert tuple(signature.parameters) == names

    assert inspect.signature(OperationStore.list_steps).parameters["limit"].default == DEFAULT_PAGE_LIMIT
    assert (
        inspect.signature(OperationStore.list_operations_by_status).parameters["limit"].default
        == DEFAULT_PAGE_LIMIT
    )
    assert (
        inspect.signature(OperationStore.list_claim_candidates).parameters["limit"].default
        == DEFAULT_CLAIM_LIMIT
    )
    assert inspect.signature(OperationStore.compare_and_set_operation).parameters[
        "recovery_authorized"
    ].default is False
    step_signature = inspect.signature(OperationStore.compare_and_set_step)
    assert step_signature.parameters["recovery_authorized"].default is False
    assert step_signature.parameters["require_live_lease"].default is False


def test_claim_candidate_is_bounded_and_immutable() -> None:
    candidate = ClaimCandidate(
        operation_id="op-0001",
        step_id="step-0001",
        job_step_key=JobStepKey(job_kind="import.package", step_name="validate"),
        status=StepStatus.PENDING,
        eligible_at=datetime(2024, 1, 2, 3, 4, 5, tzinfo=UTC),
        created_at=datetime(2024, 1, 2, 3, 4, 5, tzinfo=UTC),
    )

    assert dataclasses.is_dataclass(candidate)
    assert candidate.__slots__ == (
        "operation_id",
        "step_id",
        "job_step_key",
        "status",
        "eligible_at",
        "created_at",
    )
    with pytest.raises(dataclasses.FrozenInstanceError):
        candidate.status = StepStatus.RETRY_WAIT  # type: ignore[misc]


@pytest.mark.parametrize("status", [StepStatus.RUNNING, StepStatus.SUCCEEDED])
def test_claim_candidate_rejects_non_claimable_status(status: StepStatus) -> None:
    with pytest.raises(ValueError, match="PENDING or RETRY_WAIT"):
        ClaimCandidate(
            operation_id="op-0001",
            step_id="step-0001",
            job_step_key=JobStepKey(job_kind="import.package", step_name="validate"),
            status=status,
            eligible_at=datetime(2024, 1, 2, 3, 4, 5, tzinfo=UTC),
            created_at=datetime(2024, 1, 2, 3, 4, 5, tzinfo=UTC),
        )


@pytest.mark.parametrize(
    "created_at",
    [
        datetime(2024, 1, 2, 3, 4, 5),
        datetime(2024, 1, 2, 3, 4, 5, tzinfo=timezone(timedelta(hours=1))),
    ],
)
def test_claim_candidate_rejects_non_utc_timestamps(created_at: datetime) -> None:
    with pytest.raises(ValueError, match="aware UTC"):
        ClaimCandidate(
            operation_id="op-0001",
            step_id="step-0001",
            job_step_key=JobStepKey(job_kind="import.package", step_name="validate"),
            status=StepStatus.PENDING,
            eligible_at=created_at,
            created_at=datetime(2024, 1, 2, 3, 4, 5, tzinfo=UTC),
        )


@pytest.mark.parametrize(
    ("error_type", "other_types"),
    [
        (RecordNotFound, (StaleWrite, LeaseExpired, ConflictingDuplicate, StoreBusy)),
        (StaleWrite, (RecordNotFound, LeaseExpired, ConflictingDuplicate, StoreBusy)),
        (LeaseExpired, (RecordNotFound, StaleWrite, ConflictingDuplicate, StoreBusy)),
        (ConflictingDuplicate, (RecordNotFound, StaleWrite, LeaseExpired, StoreBusy)),
        (StoreBusy, (RecordNotFound, StaleWrite, LeaseExpired, ConflictingDuplicate)),
        (CorruptPersistedRecord, (UnsupportedSchemaVersion, RecordNotFound)),
        (UnsupportedSchemaVersion, (CorruptPersistedRecord, RecordNotFound)),
    ],
)
def test_store_errors_are_distinct(error_type: type[Exception], other_types: tuple[type[Exception], ...]) -> None:
    error = error_type("safe diagnostic")
    assert isinstance(error, Exception)
    assert all(not isinstance(error, other_type) for other_type in other_types)
    assert error_type.__name__ in operations.__all__


@pytest.mark.parametrize("limit", [0, -1, MAX_PAGE_LIMIT + 1, True, 1.0, "1"])
def test_page_limit_is_positive_integer_and_bounded(limit: object) -> None:
    with pytest.raises(ValueError, match="limit"):
        _validate_page_request(limit, None, maximum=MAX_PAGE_LIMIT)


def test_claim_limit_cannot_exceed_hard_maximum() -> None:
    _validate_page_request(MAX_CLAIM_LIMIT, None, maximum=MAX_CLAIM_LIMIT)
    with pytest.raises(ValueError, match="limit"):
        _validate_page_request(MAX_CLAIM_LIMIT + 1, None, maximum=MAX_CLAIM_LIMIT)


@pytest.mark.parametrize("cursor", ["", 1, b"cursor", "\x00cursor", "x" * 1025])
def test_cursor_is_opaque_but_bounded_and_textual(cursor: object) -> None:
    with pytest.raises(ValueError, match="cursor"):
        _validate_page_request(1, cursor, maximum=MAX_CLAIM_LIMIT)


class _Participant:
    def __init__(self) -> None:
        self.committed = False
        self.rolled_back = False

    def commit(self) -> None:
        self.committed = True

    def rollback(self) -> None:
        self.rolled_back = True


class _FakeUnitOfWork:
    def __init__(self) -> None:
        self.operations = object()
        self.participant = _Participant()

    def __enter__(self) -> _FakeUnitOfWork:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: object | None,
    ) -> None:
        if exc_type is None:
            self.participant.commit()
        else:
            self.participant.rollback()


def test_uow_owns_transaction_composition_not_store() -> None:
    assert isinstance(_FakeUnitOfWork(), OperationUnitOfWork)
    assert "commit" not in OperationStore.__dict__
    assert "rollback" not in OperationStore.__dict__

    committed_uow = _FakeUnitOfWork()
    with committed_uow as current:
        assert current.operations is committed_uow.operations
    assert committed_uow.participant.committed
    assert not committed_uow.participant.rolled_back

    rolled_back_uow = _FakeUnitOfWork()
    with pytest.raises(RuntimeError):
        with rolled_back_uow:
            raise RuntimeError("synthetic participant failure")
    assert rolled_back_uow.participant.rolled_back
    assert not rolled_back_uow.participant.committed


def test_operations_store_port_has_no_sqlite_dependency() -> None:
    import gateway_backend.operations.store as store

    assert "sqlite3" not in store.__dict__
    assert not hasattr(store, "sqlite3")
    assert not hasattr(store, "connection")
    assert not hasattr(store, "cursor")
    assert not hasattr(store, "sql")
    assert not hasattr(store, "path")


def test_status_import_is_available_for_store_contract() -> None:
    assert OperationStatus.QUEUED.value == "QUEUED"
