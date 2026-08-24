"""Deterministic process-local worker lifecycle and drain tests."""

from __future__ import annotations

from pathlib import Path
from typing import cast

import pytest
from pydantic import ValidationError

import gateway_backend.bootstrap.operation_worker as operation_worker_bootstrap
import gateway_backend.operations.worker_runtime as worker_runtime_module
from gateway_backend.bootstrap.operation_worker import _StartupBudget, _StartupObserver
from gateway_backend.operations.worker import (
    ClaimedWork,
    ExecutionControl,
    ExecutorAcknowledgment,
    StartupDisposition,
    WorkerEvent,
    WorkerEventCode,
    WorkerLifecycle,
)
from gateway_backend.operations.worker_lifecycle import (
    DEFAULT_DRAIN_TIMEOUT_SECONDS,
    WorkerLifecycleController,
)
from gateway_backend.operations.worker_startup import WorkerStartup
from gateway_backend.settings import BackendSettings, OperationWorkerSettings

from tests.test_operation_worker_scheduler import (
    FakeClock,
    FakeStartup,
    RuntimeStore,
    RuntimeUowFactory,
    ThreadFactory,
    _checkpoint_then_handoff,
    _active_records,
    _runtime,
)

pytestmark = pytest.mark.unit


def test_worker_settings_are_separate_from_backend_settings_and_fixed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    db_path = tmp_path / "state" / "control.sqlite3"
    monkeypatch.setenv(
        "GATEWAY_BACKEND_OPERATION_WORKER_CONTROL_DB_PATH",
        str(db_path),
    )

    settings = OperationWorkerSettings()  # type: ignore[call-arg]

    assert settings.control_db_path == db_path
    assert settings.lease_duration_seconds == 30.0
    assert settings.heartbeat_interval_seconds == 10.0
    assert settings.max_in_flight == 1
    assert settings.claim_limit == 1
    assert BackendSettings().artifact_root.name == "artifacts"

    with pytest.raises(ValidationError, match="absolute"):
        OperationWorkerSettings(control_db_path=Path("relative/control.sqlite3"))
    with pytest.raises(ValidationError, match="fixed"):
        OperationWorkerSettings(
            control_db_path=db_path,
            heartbeat_interval_seconds=5.0,
        )


def test_worker_settings_are_frozen(tmp_path: Path) -> None:
    settings = OperationWorkerSettings(control_db_path=tmp_path / "control.sqlite3")

    with pytest.raises(ValidationError):
        settings.claim_limit = 2


def test_startup_budget_rejects_a_slow_gate_without_publishing_ready() -> None:
    clock = FakeClock()
    events: list[WorkerEvent] = []

    def observe(event: WorkerEvent) -> None:
        events.append(event)

    startup_observer = _StartupObserver(observe)

    class SlowStartup:
        def startup(self) -> StartupDisposition:
            startup_observer(
                WorkerEvent(
                    code=WorkerEventCode.WORKER_READY,
                    worker_id="worker-slow-startup",
                )
            )
            clock.value = 61.0
            return StartupDisposition.READY

        def claim_one(self) -> None:
            raise AssertionError("a slow startup gate must not reach claim")

    bounded = _StartupBudget(
        cast(WorkerStartup, SlowStartup()),
        monotonic=clock,
        budget=60.0,
        observer=observe,
        startup_observer=startup_observer,
    )

    assert bounded.startup() is StartupDisposition.FATAL_BLOCK
    assert [event.code for event in events] == [WorkerEventCode.STARTUP_FAILED]
    assert events[0].error_category == "startup_timeout"


def test_bootstrap_maps_runtime_timeout_to_nonzero_without_clean_exit(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = OperationWorkerSettings(control_db_path=tmp_path / "control.sqlite3")

    class TimedOutRuntime:
        def run(self, _drain_requested: object, _wait: object) -> None:
            raise RuntimeError("worker drain timed out")

    monkeypatch.setattr(
        operation_worker_bootstrap,
        "_install_signal_handlers",
        lambda _stop_requested: (None, None),
    )
    monkeypatch.setattr(operation_worker_bootstrap, "_restore_signal_handlers", lambda _previous: None)
    monkeypatch.setattr(operation_worker_bootstrap, "bootstrap_control_database", lambda _settings: None)
    monkeypatch.setattr(
        operation_worker_bootstrap,
        "build_worker_runtime",
        lambda _settings: TimedOutRuntime(),
    )

    assert operation_worker_bootstrap.run(settings) == 1


def test_lifecycle_controller_enforces_clean_transition_order() -> None:
    clock = FakeClock()
    lifecycle = WorkerLifecycleController(monotonic=clock)

    assert lifecycle.state is WorkerLifecycle.STARTING
    assert not lifecycle.mark_ready_to_claim()
    state: WorkerLifecycle = lifecycle.state
    assert state is WorkerLifecycle.READY_TO_CLAIM
    assert lifecycle.request_drain()
    state_after_drain: WorkerLifecycle = lifecycle.state
    assert state_after_drain is WorkerLifecycle.DRAINING
    assert lifecycle.drain_deadline == DEFAULT_DRAIN_TIMEOUT_SECONDS
    assert not lifecycle.request_drain()

    with pytest.raises(ValueError, match="QUIESCED"):
        lifecycle.mark_stopping()

    lifecycle.mark_idle_quiesced()
    lifecycle.mark_stopping()
    lifecycle.mark_exited()
    state_final: WorkerLifecycle = lifecycle.state
    assert state_final is WorkerLifecycle.EXITED
    assert not lifecycle.request_drain()


def test_drain_requested_during_startup_is_latched_without_claiming() -> None:
    lifecycle = WorkerLifecycleController(monotonic=FakeClock())

    assert not lifecycle.request_drain()
    assert lifecycle.state is WorkerLifecycle.STARTING
    assert lifecycle.mark_ready_to_claim()
    state: WorkerLifecycle = lifecycle.state
    assert state is WorkerLifecycle.DRAINING


def test_idle_drain_reaches_exit_without_cancel_or_claim() -> None:
    operation, step = _active_records()
    store = RuntimeStore(operation, step)
    factory = RuntimeUowFactory(store)
    startup = FakeStartup([None])
    lifecycle = WorkerLifecycleController(monotonic=FakeClock())
    events: list[WorkerEvent] = []
    drain = [False]
    waits: list[float] = []

    def wait(timeout: float) -> bool:
        waits.append(timeout)
        drain[0] = True
        return True

    _runtime(
        startup,
        factory,
        events,
        lifecycle=lifecycle,
    ).run(
        drain_requested=lambda: drain[0],
        wait=wait,
    )

    assert waits == [1.0]
    assert startup.claim_calls == 1
    assert lifecycle.state is WorkerLifecycle.EXITED
    assert [event.code for event in events] == [
        WorkerEventCode.DRAIN_STARTED,
        WorkerEventCode.WORKER_EXITED,
    ]


def test_timeout_is_one_way_and_does_not_release_executor_or_cancel() -> None:
    clock = FakeClock()
    lifecycle = WorkerLifecycleController(monotonic=clock)
    lifecycle.mark_ready_to_claim()
    lifecycle.request_drain()
    lifecycle.mark_executor_started()

    clock.value = DEFAULT_DRAIN_TIMEOUT_SECONDS
    assert lifecycle.check_timeout()
    assert lifecycle.state is WorkerLifecycle.DRAINING_TIMEOUT
    assert not lifecycle.check_timeout()
    assert lifecycle.executor_active

    control = ExecutionControl()
    assert not control.cancel_requested
    assert not control.drain_requested

    assert not lifecycle.mark_executor_completed(ExecutorAcknowledgment.PUBLISHED)
    assert lifecycle.state is WorkerLifecycle.DRAINING_TIMEOUT
    assert not lifecycle.executor_active
    with pytest.raises(ValueError, match="QUIESCED"):
        lifecycle.mark_stopping()


def test_runtime_timeout_is_worker_fatal_without_worker_exit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    operation, step = _active_records()
    store = RuntimeStore(operation, step)
    factory = RuntimeUowFactory(store)
    startup = FakeStartup([ClaimedWork(operation, step, _checkpoint_then_handoff([False]))])
    events: list[WorkerEvent] = []
    threads = ThreadFactory()
    clock = FakeClock()
    lifecycle = WorkerLifecycleController(monotonic=clock, drain_timeout=1.0)

    class CompletionProbe:
        def __init__(self) -> None:
            self.completed = False

        def is_set(self) -> bool:
            return self.completed

        def set(self) -> None:
            self.completed = True

        def wait(self, timeout: float) -> bool:
            clock.value += timeout
            threads.threads[0].run()
            return self.completed

    completion = CompletionProbe()
    monkeypatch.setattr(getattr(worker_runtime_module, "threading"), "Event", lambda: completion)

    with pytest.raises(RuntimeError, match="drain timed out"):
        _runtime(
            startup,
            factory,
            events,
            clock=clock,
            lifecycle=lifecycle,
            thread_factory=threads,
        ).run(
            drain_requested=lambda: bool(threads.threads and threads.threads[0].started),
            wait=lambda _timeout: False,
        )

    assert lifecycle.state is WorkerLifecycle.DRAINING_TIMEOUT
    assert any(event.code is WorkerEventCode.DRAIN_TIMED_OUT for event in events)
    assert all(event.code is not WorkerEventCode.WORKER_EXITED for event in events)
    assert threads.threads[0].joined
