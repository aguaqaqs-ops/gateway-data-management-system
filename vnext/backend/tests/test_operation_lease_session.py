"""Fresh-transaction LeaseSession publication tests."""

from __future__ import annotations

import dataclasses
from datetime import UTC, datetime, timedelta
from types import TracebackType
from typing import Self, cast

import pytest
from gateway_shared_kernel.jcs import canonicalize_json_value

from gateway_backend.operations.contracts import (
    OPERATION_RUNTIME_CONTRACT_VERSION,
    OperationRecord,
    OperationStatus,
    StepRecord,
    StepStatus,
)
from gateway_backend.operations.lease_session import LeaseSession
from gateway_backend.operations.state import TransitionDisposition, WritePrecondition
from gateway_backend.operations.store import (
    ClaimCandidate,
    ConflictingDuplicate,
    IntegrityScanPage,
    LeaseExpired,
    OperationStore,
    OperationUnitOfWork,
    RecordNotFound,
    StaleWrite,
)
from gateway_backend.operations.worker import (
    CheckpointGeneration,
    ExecutionControl,
    ExecutorAcknowledgment,
    WorkerEvent,
    WorkerEventCode,
    WorkerObserver,
)
import gateway_backend.operations.worker as worker_contract

pytestmark = pytest.mark.unit

BASE_TIME = datetime(2026, 8, 24, 12, 0, tzinfo=UTC)


def _active_records(
    *,
    operation_id: str = "operation-1",
    step_id: str = "step-1",
    worker_id: str = "worker-1",
    lease_token: str = "lease-1",
) -> tuple[OperationRecord, StepRecord]:
    operation = OperationRecord(
        contract_version=OPERATION_RUNTIME_CONTRACT_VERSION,
        operation_id=operation_id,
        job_kind="import.package",
        job_contract_version="backend-vnext/import-package/v1",
        job_payload=canonicalize_json_value({}),
        job_payload_ref=None,
        business_refs=(),
        artifact_refs=(),
        repository_operation_id=None,
        checkpoint_ref=None,
        ready_closure_ref=None,
        status=OperationStatus.RUNNING,
        diagnostic=None,
        cancel_requested=False,
        created_at=BASE_TIME,
        updated_at=BASE_TIME,
        completed_at=None,
        optimistic_version=4,
    )
    step = StepRecord(
        contract_version=OPERATION_RUNTIME_CONTRACT_VERSION,
        step_id=step_id,
        operation_id=operation_id,
        step_name="validate",
        status=StepStatus.RUNNING,
        attempt_count=1,
        diagnostic=None,
        cancel_requested=False,
        retry_not_before=None,
        worker_id=worker_id,
        lease_token=lease_token,
        lease_expires_at=BASE_TIME + timedelta(seconds=30),
        checkpoint_ref=None,
        prior_output_refs=(),
        created_at=BASE_TIME,
        updated_at=BASE_TIME,
        started_at=BASE_TIME,
        completed_at=None,
        optimistic_version=5,
    )
    return operation, step


def _terminal_step(current: StepRecord, now: datetime) -> StepRecord:
    return dataclasses.replace(
        current,
        status=StepStatus.SUCCEEDED,
        worker_id=None,
        lease_token=None,
        lease_expires_at=None,
        updated_at=now,
        completed_at=now,
        optimistic_version=current.optimistic_version + 1,
    )


def _successor(operation_id: str, now: datetime) -> StepRecord:
    return StepRecord(
        contract_version=OPERATION_RUNTIME_CONTRACT_VERSION,
        step_id="step-2",
        operation_id=operation_id,
        step_name="publish",
        status=StepStatus.PENDING,
        attempt_count=0,
        diagnostic=None,
        cancel_requested=False,
        retry_not_before=None,
        worker_id=None,
        lease_token=None,
        lease_expires_at=None,
        checkpoint_ref=None,
        prior_output_refs=(),
        created_at=now,
        updated_at=now,
        started_at=None,
        completed_at=None,
        optimistic_version=0,
    )


class FakeStore:
    """Small transaction participant that records R2 action calls."""

    def __init__(self, operation: OperationRecord, step: StepRecord) -> None:
        self.operation = operation
        self.step = step
        self.successors: dict[str, StepRecord] = {}
        self.step_writes = 0
        self.operation_writes = 0
        self.successor_writes = 0
        self.fail_successor_insert = False
        self.transaction_now = BASE_TIME + timedelta(seconds=1)
        self._snapshot: tuple[OperationRecord, StepRecord, dict[str, StepRecord]] | None = None

    def begin(self) -> None:
        self._snapshot = (self.operation, self.step, self.successors.copy())

    def finish(self, *, rollback: bool) -> None:
        if rollback:
            assert self._snapshot is not None
            self.operation, self.step, successors = self._snapshot
            self.successors = successors
        self._snapshot = None

    def get_operation(self, operation_id: str) -> OperationRecord:
        if operation_id != self.operation.operation_id:
            raise RecordNotFound(operation_id)
        return self.operation

    def get_step(self, step_id: str) -> StepRecord:
        if step_id != self.step.step_id:
            raise RecordNotFound(step_id)
        return self.step

    def list_steps(
        self,
        operation_id: str,
        *,
        cursor: str | None = None,
        limit: int = 50,
    ) -> tuple[tuple[StepRecord, ...], str | None]:
        raise AssertionError((operation_id, cursor, limit))

    def list_operations_by_status(
        self,
        status: OperationStatus,
        *,
        cursor: str | None = None,
        limit: int = 50,
    ) -> tuple[tuple[OperationRecord, ...], str | None]:
        raise AssertionError((status, cursor, limit))

    def list_claim_candidates(
        self,
        now: datetime,
        *,
        cursor: str | None = None,
        limit: int = 1,
    ) -> tuple[tuple[ClaimCandidate, ...], str | None]:
        raise AssertionError((now, cursor, limit))

    def scan_active_integrity(
        self,
        *,
        cursor: str | None = None,
        limit: int = 50,
    ) -> IntegrityScanPage:
        raise AssertionError((cursor, limit))

    def insert_operation_with_initial_step(
        self,
        operation: OperationRecord,
        step: StepRecord,
    ) -> TransitionDisposition:
        raise AssertionError((operation, step))

    def insert_successor_step(self, step: StepRecord) -> TransitionDisposition:
        if self.fail_successor_insert:
            raise ConflictingDuplicate("synthetic successor conflict")
        self.successors[step.step_id] = step
        self.successor_writes += 1
        return TransitionDisposition.APPLY

    def compare_and_set_operation(
        self,
        candidate: OperationRecord,
        precondition: WritePrecondition,
        *,
        recovery_authorized: bool = False,
    ) -> TransitionDisposition:
        del recovery_authorized
        if precondition.expected_optimistic_version != self.operation.optimistic_version:
            raise StaleWrite("synthetic operation version mismatch")
        if precondition.worker_id is not None or precondition.lease_token is not None:
            raise StaleWrite("synthetic operation lease mismatch")
        self.operation = candidate
        self.operation_writes += 1
        return TransitionDisposition.APPLY

    def compare_and_set_step(
        self,
        candidate: StepRecord,
        precondition: WritePrecondition,
        *,
        recovery_authorized: bool = False,
        require_live_lease: bool = False,
    ) -> TransitionDisposition:
        del recovery_authorized
        if precondition.expected_optimistic_version != self.step.optimistic_version:
            raise StaleWrite("synthetic step version mismatch")
        if (
            precondition.worker_id != self.step.worker_id
            or precondition.lease_token != self.step.lease_token
        ):
            raise StaleWrite("synthetic step lease mismatch")
        if require_live_lease and (
            self.step.lease_expires_at is None or self.step.lease_expires_at <= self.transaction_now
        ):
            raise LeaseExpired("synthetic step lease expired")
        self.step = candidate
        self.step_writes += 1
        return TransitionDisposition.APPLY


class FakeUnitOfWork:
    def __init__(self, store: FakeStore, transaction_now: datetime) -> None:
        self._store = store
        self._transaction_now = transaction_now
        self.committed = False
        self.rolled_back = False

    @property
    def operations(self) -> OperationStore:
        return self._store

    @property
    def transaction_now(self) -> datetime:
        return self._transaction_now

    def __enter__(self) -> Self:
        self._store.transaction_now = self._transaction_now
        self._store.begin()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        del exc_value, traceback
        self.rolled_back = exc_type is not None
        self.committed = exc_type is None
        self._store.finish(rollback=self.rolled_back)


class UowFactory:
    def __init__(self, store: FakeStore, clocks: list[datetime] | None = None) -> None:
        self.store = store
        self.clocks = clocks or [BASE_TIME + timedelta(seconds=1)]
        self.uows: list[FakeUnitOfWork] = []

    def __call__(self) -> OperationUnitOfWork:
        index = min(len(self.uows), len(self.clocks) - 1)
        uow = FakeUnitOfWork(self.store, self.clocks[index])
        self.uows.append(uow)
        return uow


def _make_session(
    store: FakeStore,
    *,
    clocks: list[datetime] | None = None,
    observer: WorkerObserver | None = None,
) -> tuple[LeaseSession, UowFactory, ExecutionControl, list[WorkerEvent]]:
    factory = UowFactory(store, clocks)
    control = ExecutionControl()
    events: list[WorkerEvent] = []
    effective_observer = observer if observer is not None else cast(WorkerObserver, events.append)
    session = LeaseSession(
        worker_id="worker-1",
        lease_token="lease-1",
        operation_id=store.operation.operation_id,
        step_id=store.step.step_id,
        write_uow_factory=factory,
        control=control,
        observer=effective_observer,
    )
    return session, factory, control, events


def test_heartbeat_and_checkpoint_reload_fresh_records_and_versions() -> None:
    operation, step = _active_records()
    store = FakeStore(operation, step)
    second_now = BASE_TIME + timedelta(seconds=2)
    session, factory, control, events = _make_session(
        store,
        clocks=[BASE_TIME + timedelta(seconds=1), second_now],
    )

    heartbeat = session.heartbeat()
    assert heartbeat.optimistic_version == 6
    assert heartbeat.lease_expires_at == BASE_TIME + timedelta(seconds=31)

    observed: tuple[int, datetime] | None = None

    def build_checkpoint(
        current_operation: OperationRecord,
        current_step: StepRecord,
        now: datetime,
    ) -> StepRecord:
        nonlocal observed
        observed = (current_step.optimistic_version, now)
        assert current_operation.operation_id == operation.operation_id
        return dataclasses.replace(
            current_step,
            updated_at=now,
            optimistic_version=current_step.optimistic_version + 1,
        )

    generation = session.publish_checkpoint(build_checkpoint)
    assert observed == (6, second_now)
    assert generation == CheckpointGeneration(operation.operation_id, step.step_id, 7)
    assert len(factory.uows) == 2
    assert all(uow.committed for uow in factory.uows)
    assert control.lease_lost is False
    assert [event.code for event in events] == [WorkerEventCode.HEARTBEAT_SUCCEEDED]


def test_concrete_session_satisfies_the_worker_lease_session_port() -> None:
    operation, step = _active_records()
    session, _, _, _ = _make_session(FakeStore(operation, step))
    assert isinstance(session, worker_contract.LeaseSession)


def test_external_cancel_is_propagated_without_resetting_or_changing_status() -> None:
    operation, step = _active_records()
    store = FakeStore(operation, step)
    session, _, control, _ = _make_session(store)

    store.operation = dataclasses.replace(store.operation, cancel_requested=True)
    store.step = dataclasses.replace(store.step, cancel_requested=True)
    session.refresh_control()
    assert control.cancel_requested

    session.heartbeat()
    assert control.cancel_requested
    assert store.operation.status is OperationStatus.RUNNING
    assert store.step.status is StepStatus.RUNNING


@pytest.mark.parametrize(
    ("fault", "expected_error"),
    (
        ("expired", LeaseExpired),
        ("worker", StaleWrite),
        ("identity", StaleWrite),
    ),
)
def test_stale_or_expired_live_record_loses_lease_and_fences_future_mutation(
    fault: str,
    expected_error: type[Exception],
) -> None:
    operation, step = _active_records()
    store = FakeStore(operation, step)
    if fault == "expired":
        store.step = dataclasses.replace(
            store.step,
            lease_expires_at=BASE_TIME + timedelta(microseconds=1),
        )
    elif fault == "worker":
        store.step = dataclasses.replace(store.step, worker_id="other-worker")
    else:
        store.step = dataclasses.replace(store.step, operation_id="other-operation")
    session, factory, control, events = _make_session(store)

    with pytest.raises(expected_error):
        session.heartbeat()
    assert control.lease_lost
    assert events[-1].code is WorkerEventCode.LEASE_LOST
    calls_after_loss = len(factory.uows)
    with pytest.raises(StaleWrite):
        session.heartbeat()
    assert len(factory.uows) == calls_after_loss


def test_builder_failure_rolls_back_and_does_not_lose_lease() -> None:
    operation, step = _active_records()
    store = FakeStore(operation, step)
    session, factory, control, _ = _make_session(store)

    def failing_builder(
        current_operation: OperationRecord,
        current_step: StepRecord,
        now: datetime,
    ) -> StepRecord:
        del current_operation, current_step, now
        raise RuntimeError("builder failed")

    with pytest.raises(RuntimeError, match="builder failed"):
        session.publish_checkpoint(failing_builder)
    assert factory.uows[-1].rolled_back
    assert store.step == step
    assert control.lease_lost is False


def test_checkpoint_builder_cannot_replace_the_session_lease_expiry() -> None:
    operation, step = _active_records()
    store = FakeStore(operation, step)
    session, factory, control, _ = _make_session(store)

    with pytest.raises(ValueError, match="preserve the current lease expiry"):
        session.publish_checkpoint(
            lambda _, current, at: dataclasses.replace(
                current,
                lease_expires_at=at + timedelta(days=365),
                updated_at=at,
                optimistic_version=current.optimistic_version + 1,
            )
        )

    assert factory.uows[-1].rolled_back
    assert store.step == step
    assert control.lease_lost is False


def test_publication_shapes_are_closed_before_r2_action() -> None:
    operation, step = _active_records()
    store = FakeStore(operation, step)
    session, factory, _, _ = _make_session(store)

    with pytest.raises(ValueError, match="must remain RUNNING"):
        session.publish_checkpoint(
            lambda _, current, at: _terminal_step(current, at),
        )
    assert factory.uows[-1].rolled_back
    assert store.step == step

    with pytest.raises(ValueError, match="successor step must be PENDING"):
        session.publish_successor(
            lambda _, current, at: (
                _terminal_step(current, at),
                dataclasses.replace(
                    _successor(operation.operation_id, at),
                    status=StepStatus.RUNNING,
                    attempt_count=1,
                    worker_id="worker-1",
                    lease_token="lease-1",
                    lease_expires_at=at + timedelta(seconds=30),
                    started_at=at,
                ),
            ),
        )
    assert factory.uows[-1].rolled_back
    assert store.step == step

    with pytest.raises(ValueError, match="published operation"):
        session.publish_operation(
            lambda current_operation, current_step, at: (
                _terminal_step(current_step, at),
                current_operation,
            ),
        )
    assert factory.uows[-1].rolled_back
    assert store.step == step


def test_successor_second_leg_failure_rolls_back_terminal_step() -> None:
    operation, step = _active_records()
    store = FakeStore(operation, step)
    store.fail_successor_insert = True
    session, factory, _, _ = _make_session(store)

    with pytest.raises(ConflictingDuplicate, match="synthetic successor conflict"):
        session.publish_successor(
            lambda _, current, at: (
                _terminal_step(current, at),
                _successor(operation.operation_id, at),
            ),
        )
    assert factory.uows[-1].rolled_back
    assert store.step == step
    assert store.successors == {}


def test_terminal_operation_publication_is_atomic_and_closes_session() -> None:
    operation, step = _active_records()
    store = FakeStore(operation, step)
    session, factory, _, _ = _make_session(store)

    def build_terminal(
        current_operation: OperationRecord,
        current_step: StepRecord,
        now: datetime,
    ) -> tuple[StepRecord, OperationRecord]:
        terminal_step = _terminal_step(current_step, now)
        terminal_operation = dataclasses.replace(
            current_operation,
            status=OperationStatus.SUCCEEDED,
            updated_at=now,
            completed_at=now,
            optimistic_version=current_operation.optimistic_version + 1,
        )
        return terminal_step, terminal_operation

    dispositions = session.publish_operation(build_terminal)
    assert dispositions == (TransitionDisposition.APPLY, TransitionDisposition.APPLY)
    assert session.completion_acknowledgment() is ExecutorAcknowledgment.PUBLISHED
    assert factory.uows[-1].committed
    assert store.step.status is StepStatus.SUCCEEDED
    assert store.operation.status is OperationStatus.SUCCEEDED
    with pytest.raises(StaleWrite):
        session.heartbeat()


def test_safe_handoff_requires_latest_committed_checkpoint_and_is_one_shot() -> None:
    operation, step = _active_records()
    store = FakeStore(operation, step)
    session, factory, _, events = _make_session(store)
    invalid = CheckpointGeneration(operation.operation_id, step.step_id, 6)

    with pytest.raises(ValueError, match="latest committed checkpoint"):
        session.acknowledge_safe_handoff(invalid)
    assert factory.uows == []

    generation = session.publish_checkpoint(
        lambda _, current, at: dataclasses.replace(
            current,
            updated_at=at,
            optimistic_version=current.optimistic_version + 1,
        ),
    )
    assert factory.uows[-1].committed
    assert session.acknowledge_safe_handoff(generation) is ExecutorAcknowledgment.SAFE_HANDOFF
    assert session.completion_acknowledgment() is ExecutorAcknowledgment.SAFE_HANDOFF
    assert events[-1].code is WorkerEventCode.SAFE_HANDOFF
    with pytest.raises(StaleWrite):
        session.acknowledge_safe_handoff(generation)


def test_observer_failure_does_not_rollback_a_committed_heartbeat() -> None:
    operation, step = _active_records()
    store = FakeStore(operation, step)

    def failing_observer(event: WorkerEvent) -> None:
        assert event.code is WorkerEventCode.HEARTBEAT_SUCCEEDED
        raise RuntimeError("observer failed")

    session, factory, _, _ = _make_session(store, observer=failing_observer)
    with pytest.raises(RuntimeError, match="observer failed"):
        session.heartbeat()
    assert factory.uows[-1].committed
    assert store.step.optimistic_version == step.optimistic_version + 1
