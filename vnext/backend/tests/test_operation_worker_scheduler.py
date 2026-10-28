"""Deterministic scheduler, executor, and heartbeat tests."""

from __future__ import annotations

import dataclasses
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from threading import Event, Thread
from types import TracebackType
from typing import Self, cast

import pytest
from gateway_shared_kernel.jcs import canonicalize_json_value

from gateway_backend.operations.lease_session import LeaseSession as ConcreteLeaseSession
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
    StaleWrite,
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


class InjectedWakeEvent:
    def __init__(self, on_wait: Callable[[float, InjectedWakeEvent], bool]) -> None:
        self._event = Event()
        self.on_wait = on_wait
        self.wait_calls: list[float] = []

    def clear(self) -> None:
        self._event.clear()

    def is_set(self) -> bool:
        return self._event.is_set()

    def set(self) -> None:
        self._event.set()

    def wait(self, timeout: float | None = None) -> bool:
        resolved = 0.0 if timeout is None else timeout
        self.wait_calls.append(resolved)
        if self._event.is_set():
            return True
        return self.on_wait(resolved, self)


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
    wake_event_factory: Callable[[], InjectedWakeEvent] | None = None,
) -> WorkerRuntime:
    def observe(event: WorkerEvent) -> None:
        events.append(event)

    active_threads = thread_factory or ThreadFactory()

    def default_wake_event() -> InjectedWakeEvent:
        def run_executor(_timeout: float, event: InjectedWakeEvent) -> bool:
            if isinstance(active_threads, ThreadFactory) and active_threads.threads:
                active_threads.threads[-1].run()
                return event.is_set()
            return event._event.wait(_timeout)

        return InjectedWakeEvent(run_executor)

    return WorkerRuntime(
        startup=cast(WorkerStartup, startup),
        write_uow_factory=cast(Callable[[], OperationUnitOfWork], factory),
        observer=observe,
        lifecycle=lifecycle,
        monotonic=clock or FakeClock(),
        thread_factory=active_threads,
        wake_event_factory=wake_event_factory or default_wake_event,
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


def test_short_executor_completion_wakes_before_heartbeat() -> None:
    operation, step = _active_records()
    store = RuntimeStore(operation, step)
    factory = RuntimeUowFactory(store)
    stop = [False]

    def short_executor(
        _operation: OperationRecord,
        _step: StepRecord,
        _control: ExecutionControl,
        session: LeaseSession,
    ) -> ExecutorAcknowledgment:
        generation = session.publish_checkpoint(
            lambda _, current, now: dataclasses.replace(
                current,
                updated_at=now,
                optimistic_version=current.optimistic_version + 1,
            )
        )
        return session.acknowledge_safe_handoff(generation)

    work = ClaimedWork(operation, step, cast(ClaimedExecutor, short_executor))
    startup = FakeStartup([work, None])
    events: list[WorkerEvent] = []
    threads = ThreadFactory()
    clock = FakeClock()
    event_waits: list[float] = []
    idle_waits: list[float] = []

    def wake_wait(timeout: float, event: InjectedWakeEvent) -> bool:
        event_waits.append(timeout)
        threads.threads[0].run()
        return event.is_set()

    def idle_wait(timeout: float) -> bool:
        idle_waits.append(timeout)
        stop[0] = True
        return False

    _runtime(
        startup,
        factory,
        events,
        clock=clock,
        thread_factory=threads,
        wake_event_factory=lambda: InjectedWakeEvent(wake_wait),
    ).run(
        drain_requested=lambda: stop[0],
        wait=idle_wait,
    )

    assert event_waits == [10.0]
    assert idle_waits == [1.0]
    assert startup.claim_calls == 2
    assert clock.value == 0.0
    assert not any(event.code is WorkerEventCode.HEARTBEAT_SUCCEEDED for event in events)
    assert threads.threads[0].joined


def test_stop_signal_during_executor_wakes_supervisor_and_enters_drain() -> None:
    operation, step = _active_records()
    store = RuntimeStore(operation, step)
    factory = RuntimeUowFactory(store)
    stop = [False]
    events: list[WorkerEvent] = []
    threads = ThreadFactory()
    clock = FakeClock()
    lifecycle = WorkerLifecycleController(monotonic=clock)
    runtime_holder: list[WorkerRuntime] = []
    wake_event: InjectedWakeEvent | None = None
    signal_woke_executor: list[bool] = []

    def executor(
        current_operation: OperationRecord,
        current_step: StepRecord,
        _control: ExecutionControl,
        session: LeaseSession,
    ) -> ExecutorAcknowledgment:
        stop[0] = True
        runtime_holder[0].notify_stop_signal()
        assert wake_event is not None
        signal_woke_executor.append(wake_event.is_set())
        generation = session.publish_checkpoint(
            lambda _, current, now: dataclasses.replace(
                current,
                updated_at=now,
                optimistic_version=current.optimistic_version + 1,
            )
        )
        return session.acknowledge_safe_handoff(generation)

    def wake_wait(_timeout: float, event: InjectedWakeEvent) -> bool:
        threads.threads[0].run()
        return event.is_set()

    def make_wake_event() -> InjectedWakeEvent:
        nonlocal wake_event
        wake_event = InjectedWakeEvent(wake_wait)
        return wake_event

    startup = FakeStartup(
        [ClaimedWork(operation, step, cast(ClaimedExecutor, executor))]
    )
    runtime = _runtime(
        startup,
        factory,
        events,
        clock=clock,
        thread_factory=threads,
        lifecycle=lifecycle,
        wake_event_factory=make_wake_event,
    )
    runtime_holder.append(runtime)
    runtime.run(drain_requested=lambda: stop[0], wait=lambda _timeout: False)

    assert signal_woke_executor == [True]
    assert lifecycle.state is WorkerLifecycle.EXITED
    assert any(event.code is WorkerEventCode.DRAIN_STARTED for event in events)
    assert threads.threads[0].joined


def test_long_executor_continues_heartbeating_at_the_configured_interval() -> None:
    operation, step = _active_records()
    store = RuntimeStore(operation, step)
    factory = RuntimeUowFactory(store)
    stop = [False]
    startup = FakeStartup(
        [ClaimedWork(operation, step, _checkpoint_then_handoff(stop))]
    )
    events: list[WorkerEvent] = []
    threads = ThreadFactory()
    clock = FakeClock()
    event_waits: list[float] = []

    def wake_wait(timeout: float, event: InjectedWakeEvent) -> bool:
        event_waits.append(timeout)
        if len(event_waits) == 1:
            clock.value += timeout
            return False
        threads.threads[0].run()
        return event.is_set()

    _runtime(
        startup,
        factory,
        events,
        clock=clock,
        thread_factory=threads,
        wake_event_factory=lambda: InjectedWakeEvent(wake_wait),
    ).run(
        drain_requested=lambda: stop[0],
        wait=lambda _timeout: False,
    )

    assert event_waits == [10.0, 10.0]
    assert clock.value == 10.0
    assert [event.code for event in events].count(WorkerEventCode.HEARTBEAT_SUCCEEDED) == 1
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
    event_waits: list[float] = []

    def wake_wait(timeout: float, event: InjectedWakeEvent) -> bool:
        event_waits.append(timeout)
        clock.value += timeout
        if len(event_waits) == 1:
            store.operation = dataclasses.replace(store.operation, cancel_requested=True)
            store.step = dataclasses.replace(store.step, cancel_requested=True)
        elif len(event_waits) == 2:
            threads.threads[0].run()
            return event.is_set()
        return False

    _runtime(
        startup,
        factory,
        events,
        clock=clock,
        thread_factory=threads,
        lifecycle=lifecycle,
        wake_event_factory=lambda: InjectedWakeEvent(wake_wait),
    ).run(
        drain_requested=lambda: stop[0],
        wait=lambda _timeout: False,
    )

    assert event_waits == [10.0, 10.0]
    assert observed_cancel == [True]
    assert store.max_active_transactions == 1
    assert any(event.code is WorkerEventCode.HEARTBEAT_SUCCEEDED for event in events)
    assert lifecycle.state is WorkerLifecycle.EXITED
    assert [event.code for event in events].count(WorkerEventCode.DRAIN_STARTED) == 1
    assert [event.code for event in events].count(WorkerEventCode.WORKER_EXITED) == 1


@pytest.mark.serial
def test_committed_terminal_operation_is_not_heartbeat_lease_loss(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    operation, step = _active_records()
    store = RuntimeStore(operation, step)
    factory = RuntimeUowFactory(store)
    terminal_published = Event()
    heartbeat_attempted = Event()
    clock = FakeClock()

    def executor(
        current_operation: OperationRecord,
        current_step: StepRecord,
        _control: ExecutionControl,
        session: LeaseSession,
    ) -> ExecutorAcknowledgment:
        def build_terminal(
            live_operation: OperationRecord,
            live_step: StepRecord,
            now: datetime,
        ) -> tuple[StepRecord, OperationRecord]:
            assert live_operation == current_operation
            assert live_step == current_step
            terminal_step = dataclasses.replace(
                live_step,
                status=StepStatus.SUCCEEDED,
                worker_id=None,
                lease_token=None,
                lease_expires_at=None,
                updated_at=now,
                completed_at=now,
                optimistic_version=live_step.optimistic_version + 1,
            )
            terminal_operation = dataclasses.replace(
                live_operation,
                status=OperationStatus.SUCCEEDED,
                updated_at=now,
                completed_at=now,
                optimistic_version=live_operation.optimistic_version + 1,
            )
            return terminal_step, terminal_operation

        session.publish_operation(build_terminal)
        terminal_published.set()
        if not heartbeat_attempted.wait(timeout=5):
            raise AssertionError("worker did not heartbeat during the terminal publication window")
        return ExecutorAcknowledgment.PUBLISHED

    original_heartbeat = ConcreteLeaseSession.heartbeat

    def observe_heartbeat(session: ConcreteLeaseSession) -> StepRecord:
        heartbeat_attempted.set()
        return original_heartbeat(session)

    monkeypatch.setattr(ConcreteLeaseSession, "heartbeat", observe_heartbeat)
    startup = FakeStartup([ClaimedWork(operation, step, cast(ClaimedExecutor, executor))])
    events: list[WorkerEvent] = []
    draining = [False]

    def wake_wait(timeout: float, _event: InjectedWakeEvent) -> bool:
        if not terminal_published.wait(timeout=5):
            raise AssertionError("executor did not commit the terminal operation")
        clock.value += timeout
        return False

    _runtime(
        startup,
        factory,
        events,
        clock=clock,
        thread_factory=cast(ThreadFactory, lambda target: Thread(target=target)),
        wake_event_factory=lambda: InjectedWakeEvent(wake_wait),
    ).run(
        drain_requested=lambda: draining[0],
        wait=lambda timeout: (draining.__setitem__(0, True) or timeout == 1.0),
    )

    assert heartbeat_attempted.is_set()
    assert store.operation.status is OperationStatus.SUCCEEDED
    assert store.step.status is StepStatus.SUCCEEDED
    assert not any(event.code is WorkerEventCode.LEASE_LOST for event in events)


def test_heartbeat_stale_write_before_terminal_commit_still_loses_worker_lease() -> None:
    operation, step = _active_records()
    store = RuntimeStore(operation, step)
    factory = RuntimeUowFactory(store)
    clock = FakeClock()
    startup = FakeStartup(
        [ClaimedWork(operation, step, cast(ClaimedExecutor, lambda *_args: None))]
    )
    events: list[WorkerEvent] = []

    def wake_wait(timeout: float, _event: InjectedWakeEvent) -> bool:
        assert timeout == 10.0
        store.step = dataclasses.replace(
            store.step,
            lease_token="lease-taken-over",
            optimistic_version=store.step.optimistic_version + 1,
        )
        clock.value += timeout
        return False

    with pytest.raises(StaleWrite, match="worker or token no longer matches"):
        _runtime(
            startup,
            factory,
            events,
            clock=clock,
            wake_event_factory=lambda: InjectedWakeEvent(wake_wait),
        ).run(
            drain_requested=lambda: False,
            wait=lambda _timeout: False,
        )

    assert any(event.code is WorkerEventCode.LEASE_LOST for event in events)


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

    def wake_wait(timeout: float, _event: InjectedWakeEvent) -> bool:
        waits.append(timeout)
        clock.value += timeout
        return False

    with pytest.raises(StoreBusy, match="retry budget"):
        _runtime(
            startup,
            factory,
            events,
            clock=clock,
            thread_factory=threads,
            wake_event_factory=lambda: InjectedWakeEvent(wake_wait),
        ).run(
            drain_requested=lambda: False,
            wait=lambda _timeout: False,
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

    def wake_wait(timeout: float, _event: InjectedWakeEvent) -> bool:
        waits.append(timeout)
        clock.value += timeout
        return False

    runtime = WorkerRuntime(
        startup=cast(WorkerStartup, startup),
        write_uow_factory=cast(Callable[[], OperationUnitOfWork], factory),
        observer=observe,
        monotonic=clock,
        thread_factory=threads,
        wake_event_factory=lambda: InjectedWakeEvent(wake_wait),
        jitter=lambda lower, _upper: lower,
    )
    with pytest.raises(StoreBusy, match="retry budget"):
        runtime.run(drain_requested=lambda: False, wait=lambda _timeout: False)

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

    def wake_wait(_timeout: float, event: InjectedWakeEvent) -> bool:
        threads.threads[0].run()
        return event.is_set()

    runtime = WorkerRuntime(
        startup=cast(WorkerStartup, startup),
        write_uow_factory=cast(Callable[[], OperationUnitOfWork], factory),
        observer=observer,
        thread_factory=threads,
        wake_event_factory=lambda: InjectedWakeEvent(wake_wait),
    )
    with pytest.raises(RuntimeError, match="observer failed"):
        runtime.run(drain_requested=lambda: False, wait=lambda _timeout: False)


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
