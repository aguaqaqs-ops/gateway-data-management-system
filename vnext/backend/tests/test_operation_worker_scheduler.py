"""Deterministic scheduler, executor, and heartbeat tests."""

from __future__ import annotations

import dataclasses
from collections.abc import Callable
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
from gateway_backend.operations.state import TransitionDisposition, WritePrecondition
from gateway_backend.operations.store import (
    ClaimCandidate,
    IntegrityScanPage,
    OperationStore,
    OperationUnitOfWork,
    RecordNotFound,
    StoreBusy,
)
from gateway_backend.operations.worker import (
    ClaimedExecutor,
    ClaimedWork,
    ExecutionControl,
    ExecutorAcknowledgment,
    LeaseSession,
    StartupDisposition,
    WorkerEvent,
    WorkerEventCode,
    WorkerLifecycle,
)
from gateway_backend.operations.worker_lifecycle import WorkerLifecycleController
from gateway_backend.operations.worker_runtime import WorkerRuntime
from gateway_backend.operations.worker_startup import WorkerStartup
import gateway_backend.operations.worker_runtime as worker_runtime_module

pytestmark = pytest.mark.unit

BASE_TIME = datetime(2026, 8, 24, 12, 0, tzinfo=UTC)


def _active_records() -> tuple[OperationRecord, StepRecord]:
    operation = OperationRecord(
        contract_version=OPERATION_RUNTIME_CONTRACT_VERSION,
        operation_id="operation-1",
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
        optimistic_version=1,
    )
    step = StepRecord(
        contract_version=OPERATION_RUNTIME_CONTRACT_VERSION,
        step_id="step-1",
        operation_id=operation.operation_id,
        step_name="validate",
        status=StepStatus.RUNNING,
        attempt_count=1,
        diagnostic=None,
        cancel_requested=False,
        retry_not_before=None,
        worker_id="worker-1",
        lease_token="lease-1",
        lease_expires_at=BASE_TIME + timedelta(seconds=300),
        checkpoint_ref=None,
        prior_output_refs=(),
        created_at=BASE_TIME,
        updated_at=BASE_TIME,
        started_at=BASE_TIME,
        completed_at=None,
        optimistic_version=2,
    )
    return operation, step


class RuntimeStore:
    def __init__(self, operation: OperationRecord, step: StepRecord) -> None:
        self.operation = operation
        self.step = step
        self.transaction_now = BASE_TIME + timedelta(seconds=1)
        self.busy_heartbeat = False
        self.active_transactions = 0
        self.max_active_transactions = 0
        self.write_count = 0

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
        raise AssertionError(step)

    def compare_and_set_operation(
        self,
        candidate: OperationRecord,
        precondition: WritePrecondition,
        *,
        recovery_authorized: bool = False,
    ) -> TransitionDisposition:
        del recovery_authorized
        assert precondition.expected_optimistic_version == self.operation.optimistic_version
        self.operation = candidate
        self.write_count += 1
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
        if self.busy_heartbeat and require_live_lease:
            raise StoreBusy("synthetic heartbeat busy")
        assert precondition.expected_optimistic_version == self.step.optimistic_version
        assert precondition.worker_id == self.step.worker_id
        assert precondition.lease_token == self.step.lease_token
        if require_live_lease:
            assert self.step.lease_expires_at is not None
            assert self.step.lease_expires_at > self.transaction_now
        self.step = candidate
        self.write_count += 1
        return TransitionDisposition.APPLY

    @property
    def transaction_clock(self) -> datetime:
        return self.transaction_now


class RuntimeUnitOfWork:
    def __init__(self, store: RuntimeStore, transaction_now: datetime) -> None:
        self._store = store
        self._transaction_now = transaction_now
        self.committed = False
        self.rolled_back = False

    @property
    def operations(self) -> OperationStore:
        return self._store

    def __enter__(self) -> Self:
        self._store.transaction_now = self._transaction_now
        self._store.active_transactions += 1
        self._store.max_active_transactions = max(
            self._store.max_active_transactions,
            self._store.active_transactions,
        )
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        del exc_value, traceback
        self._store.active_transactions -= 1
        self.rolled_back = exc_type is not None
        self.committed = exc_type is None


class RuntimeUowFactory:
    def __init__(self, store: RuntimeStore) -> None:
        self.store = store
        self.uows: list[RuntimeUnitOfWork] = []

    def __call__(self) -> OperationUnitOfWork:
        now = BASE_TIME + timedelta(seconds=len(self.uows) + 1)
        uow = RuntimeUnitOfWork(self.store, now)
        self.uows.append(uow)
        return uow


class FakeStartup:
    def __init__(self, outcomes: list[ClaimedWork | None | BaseException]) -> None:
        self.outcomes = outcomes
        self.startup_calls = 0
        self.claim_calls = 0

    def startup(self) -> StartupDisposition:
        self.startup_calls += 1
        return StartupDisposition.READY

    def claim_one(self) -> ClaimedWork | None:
        self.claim_calls += 1
        if not self.outcomes:
            return None
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, BaseException):
            raise outcome
        return outcome


class ControlledThread:
    def __init__(self, target: Callable[[], None], *, daemon: bool = False) -> None:
        self.target = target
        self.daemon = daemon
        self.started = False
        self.joined = False
        self.ran = False

    def start(self) -> None:
        self.started = True

    def run(self) -> None:
        if not self.ran:
            self.ran = True
            self.target()

    def join(self) -> None:
        self.joined = True


class ThreadFactory:
    def __init__(self, *, daemon: bool = False) -> None:
        self.daemon = daemon
        self.threads: list[ControlledThread] = []

    def __call__(self, target: Callable[[], None]) -> ControlledThread:
        thread = ControlledThread(target, daemon=self.daemon)
        self.threads.append(thread)
        return thread


class FakeClock:
    def __init__(self) -> None:
        self.value = 0.0

    def __call__(self) -> float:
        return self.value


def _checkpoint_then_handoff(
    stop: list[bool],
    observed_cancel: list[bool] | None = None,
) -> ClaimedExecutor:
    def execute(
        _operation: OperationRecord,
        _step: StepRecord,
        control: ExecutionControl,
        session: LeaseSession,
    ) -> ExecutorAcknowledgment:
        if observed_cancel is not None:
            observed_cancel.append(control.cancel_requested)
        generation = session.publish_checkpoint(
            lambda _, current, now: dataclasses.replace(
                current,
                updated_at=now,
                optimistic_version=current.optimistic_version + 1,
            )
        )
        acknowledgment = session.acknowledge_safe_handoff(generation)
        stop[0] = True
        return acknowledgment

    return cast(ClaimedExecutor, execute)


def _runtime(
    startup: FakeStartup,
    factory: RuntimeUowFactory,
    events: list[WorkerEvent],
    *,
    clock: FakeClock | None = None,
    thread_factory: ThreadFactory | None = None,
    jitter: Callable[[float, float], float] | None = None,
    lifecycle: WorkerLifecycleController | None = None,
) -> WorkerRuntime:
    def observe(event: WorkerEvent) -> None:
        events.append(event)

    return WorkerRuntime(
        startup=cast(WorkerStartup, startup),
        write_uow_factory=cast(Callable[[], OperationUnitOfWork], factory),
        observer=observe,
        lifecycle=lifecycle,
        monotonic=clock or FakeClock(),
        thread_factory=thread_factory or ThreadFactory(),
        jitter=jitter or (lambda lower, _upper: lower),
    )


def test_empty_queue_uses_one_second_interruptible_idle_poll() -> None:
    operation, step = _active_records()
    store = RuntimeStore(operation, step)
    factory = RuntimeUowFactory(store)
    startup = FakeStartup([None])
    events: list[WorkerEvent] = []
    waits: list[float] = []
    drain = [False]

    def wait(timeout: float) -> bool:
        waits.append(timeout)
        drain[0] = True
        return True

    _runtime(startup, factory, events).run(
        drain_requested=lambda: drain[0],
        wait=wait,
    )

    assert waits == [1.0]
    assert startup.claim_calls == 1


def test_one_claim_has_one_non_daemon_executor_and_no_overlap() -> None:
    operation, step = _active_records()
    store = RuntimeStore(operation, step)
    factory = RuntimeUowFactory(store)
    stop = [False]
    work = ClaimedWork(operation, step, _checkpoint_then_handoff(stop))
    startup = FakeStartup([work])
    events: list[WorkerEvent] = []
    threads = ThreadFactory()
    waits: list[float] = []

    def wait(timeout: float) -> bool:
        waits.append(timeout)
        threads.threads[0].run()
        return False

    _runtime(startup, factory, events, thread_factory=threads).run(
        drain_requested=lambda: stop[0],
        wait=wait,
    )

    assert startup.claim_calls == 1
    assert len(threads.threads) == 1
    assert threads.threads[0].started
    assert threads.threads[0].daemon is False
    assert threads.threads[0].joined
    assert store.max_active_transactions == 1
    assert any(event.code is WorkerEventCode.SAFE_HANDOFF for event in events)


def test_active_drain_latches_executor_wait_without_polling_spin(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    operation, step = _active_records()
    store = RuntimeStore(operation, step)
    factory = RuntimeUowFactory(store)
    stop = [False]
    work = ClaimedWork(operation, step, _checkpoint_then_handoff(stop))
    startup = FakeStartup([work])
    events: list[WorkerEvent] = []
    threads = ThreadFactory()

    class CompletionProbe:
        def __init__(self) -> None:
            self.completed = False
            self.wait_calls: list[float] = []

        def is_set(self) -> bool:
            return self.completed

        def set(self) -> None:
            self.completed = True

        def wait(self, timeout: float) -> bool:
            self.wait_calls.append(timeout)
            threads.threads[0].run()
            return self.completed

    completion = CompletionProbe()
    monkeypatch.setattr(getattr(worker_runtime_module, "threading"), "Event", lambda: completion)
    drain_calls = 0

    def drain_requested() -> bool:
        nonlocal drain_calls
        if not threads.threads or not threads.threads[0].started:
            return False
        drain_calls += 1
        if drain_calls > 4:
            raise AssertionError("active drain was polled instead of waiting for completion")
        return True

    def wait(_timeout: float) -> bool:
        raise AssertionError("pending drain must wait on executor completion")

    _runtime(
        startup,
        factory,
        events,
        thread_factory=threads,
    ).run(
        drain_requested=drain_requested,
        wait=wait,
    )

    assert completion.wait_calls == [10.0]
    assert drain_calls <= 4
    assert threads.threads[0].joined


def test_heartbeat_serializes_with_publication_and_propagates_cancel() -> None:
    operation, step = _active_records()
    store = RuntimeStore(operation, step)
    factory = RuntimeUowFactory(store)
    stop = [False]
    observed_cancel: list[bool] = []
    work = ClaimedWork(operation, step, _checkpoint_then_handoff(stop, observed_cancel))
    startup = FakeStartup([work])
    events: list[WorkerEvent] = []
    threads = ThreadFactory()
    clock = FakeClock()
    lifecycle = WorkerLifecycleController(monotonic=clock)
    waits: list[float] = []

    def wait(timeout: float) -> bool:
        waits.append(timeout)
        clock.value += timeout
        if len(waits) == 1:
            store.operation = dataclasses.replace(store.operation, cancel_requested=True)
            store.step = dataclasses.replace(store.step, cancel_requested=True)
        elif len(waits) == 2:
            threads.threads[0].run()
        return False

    _runtime(
        startup,
        factory,
        events,
        clock=clock,
        thread_factory=threads,
        lifecycle=lifecycle,
    ).run(
        drain_requested=lambda: stop[0],
        wait=wait,
    )

    assert waits[:2] == [10.0, 10.0]
    assert observed_cancel == [True]
    assert store.max_active_transactions == 1
    assert any(event.code is WorkerEventCode.HEARTBEAT_SUCCEEDED for event in events)
    assert lifecycle.state is WorkerLifecycle.EXITED
    assert [event.code for event in events].count(WorkerEventCode.DRAIN_STARTED) == 1
    assert [event.code for event in events].count(WorkerEventCode.WORKER_EXITED) == 1


def test_claim_busy_uses_bounded_exponential_backoff() -> None:
    operation, step = _active_records()
    store = RuntimeStore(operation, step)
    factory = RuntimeUowFactory(store)
    startup = FakeStartup([StoreBusy("one"), StoreBusy("two"), None])
    events: list[WorkerEvent] = []
    waits: list[float] = []
    drain = [False]

    def wait(timeout: float) -> bool:
        waits.append(timeout)
        if len(waits) == 2:
            drain[0] = True
        return len(waits) == 2

    _runtime(startup, factory, events, jitter=lambda lower, _upper: lower).run(
        drain_requested=lambda: drain[0],
        wait=wait,
    )

    assert waits == [1.0, 2.0]
    assert [event.attempt for event in events if event.code is WorkerEventCode.CLAIM_BUSY] == [1, 2]


def test_heartbeat_busy_budget_fences_lease_and_joins_executor() -> None:
    operation, step = _active_records()
    store = RuntimeStore(operation, step)
    store.busy_heartbeat = True
    factory = RuntimeUowFactory(store)
    work = ClaimedWork(operation, step, lambda *_args: ExecutorAcknowledgment.PUBLISHED)
    startup = FakeStartup([work])
    events: list[WorkerEvent] = []
    threads = ThreadFactory()
    clock = FakeClock()
    waits: list[float] = []

    def wait(timeout: float) -> bool:
        waits.append(timeout)
        clock.value += timeout
        return False

    with pytest.raises(StoreBusy, match="retry budget"):
        _runtime(startup, factory, events, clock=clock, thread_factory=threads).run(
            drain_requested=lambda: False,
            wait=wait,
        )

    assert threads.threads[0].joined
    assert any(event.code is WorkerEventCode.HEARTBEAT_BUSY for event in events)
    assert any(event.code is WorkerEventCode.LEASE_LOST for event in events)


def test_heartbeat_budget_includes_claim_and_observer_elapsed_time() -> None:
    operation, step = _active_records()
    store = RuntimeStore(operation, step)
    factory = RuntimeUowFactory(store)
    work = ClaimedWork(operation, step, lambda *_args: ExecutorAcknowledgment.PUBLISHED)
    startup = FakeStartup([work])
    events: list[WorkerEvent] = []
    threads = ThreadFactory()
    clock = FakeClock()
    waits: list[float] = []

    def observe(event: WorkerEvent) -> None:
        events.append(event)
        if event.code is WorkerEventCode.HEARTBEAT_SUCCEEDED:
            clock.value += 25.0
            store.busy_heartbeat = True

    def wait(timeout: float) -> bool:
        waits.append(timeout)
        clock.value += timeout
        return False

    runtime = WorkerRuntime(
        startup=cast(WorkerStartup, startup),
        write_uow_factory=cast(Callable[[], OperationUnitOfWork], factory),
        observer=observe,
        monotonic=clock,
        thread_factory=threads,
        jitter=lambda lower, _upper: lower,
    )
    with pytest.raises(StoreBusy, match="retry budget"):
        runtime.run(drain_requested=lambda: False, wait=wait)

    assert waits[0] == 10.0
    assert clock.value == 40.0
    assert threads.threads[0].joined


def test_executor_exception_and_unproven_return_are_worker_fatal() -> None:
    cases = (
        (RuntimeError("executor failed"), "executor_exception"),
        (ExecutorAcknowledgment.PUBLISHED, "unproven_acknowledgment"),
    )
    for result, category in cases:
        operation, step = _active_records()
        store = RuntimeStore(operation, step)
        factory = RuntimeUowFactory(store)
        def executor(
            _operation: OperationRecord,
            _step: StepRecord,
            _control: ExecutionControl,
            _session: LeaseSession,
        ) -> ExecutorAcknowledgment:
            if isinstance(result, BaseException):
                raise result
            return result
        startup = FakeStartup([ClaimedWork(operation, step, cast(ClaimedExecutor, executor))])
        events: list[WorkerEvent] = []
        threads = ThreadFactory()

        def wait(_timeout: float) -> bool:
            threads.threads[0].run()
            return False

        runtime = _runtime(startup, factory, events, thread_factory=threads)
        expected = type(result) if isinstance(result, BaseException) else ValueError
        with pytest.raises(expected):
            runtime.run(drain_requested=lambda: False, wait=wait)
        assert any(
            event.code is WorkerEventCode.EXECUTOR_FAILED
            and event.error_category == category
            for event in events
        )


def test_observer_failure_is_not_recovered_as_success() -> None:
    operation, step = _active_records()
    store = RuntimeStore(operation, step)
    factory = RuntimeUowFactory(store)
    threads = ThreadFactory()
    startup = FakeStartup(
        [ClaimedWork(operation, step, lambda *_args: (_ for _ in ()).throw(RuntimeError("boom")))]
    )

    def observer(event: WorkerEvent) -> None:
        if event.code is WorkerEventCode.EXECUTOR_FAILED:
            raise RuntimeError("observer failed")

    def wait(_timeout: float) -> bool:
        threads.threads[0].run()
        return False

    runtime = WorkerRuntime(
        startup=cast(WorkerStartup, startup),
        write_uow_factory=cast(Callable[[], OperationUnitOfWork], factory),
        observer=observer,
        thread_factory=threads,
    )
    with pytest.raises(RuntimeError, match="observer failed"):
        runtime.run(drain_requested=lambda: False, wait=wait)


def test_daemon_executor_is_rejected() -> None:
    operation, step = _active_records()
    store = RuntimeStore(operation, step)
    factory = RuntimeUowFactory(store)
    startup = FakeStartup([ClaimedWork(operation, step, lambda *_args: ExecutorAcknowledgment.PUBLISHED)])
    events: list[WorkerEvent] = []

    with pytest.raises(ValueError, match="non-daemon"):
        _runtime(
            startup,
            factory,
            events,
            thread_factory=ThreadFactory(daemon=True),
        ).run(drain_requested=lambda: False, wait=lambda _timeout: False)
