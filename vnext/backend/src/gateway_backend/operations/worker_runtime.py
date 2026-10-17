"""SQLite-neutral single-executor worker scheduling and lease renewal."""

from __future__ import annotations

import random
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol

from gateway_backend.operations.lease_session import LeaseSession
from gateway_backend.operations.persistence import LEASE_DURATION
from gateway_backend.operations.store import LeaseExpired, StaleWrite, StoreBusy
from gateway_backend.operations.worker import (
    ClaimedWork,
    ExecutionControl,
    ExecutorAcknowledgment,
    StartupDisposition,
    WorkerEvent,
    WorkerEventCode,
    WorkerLifecycle,
    WorkerObserver,
    WriteUnitOfWorkFactory,
)
from gateway_backend.operations.worker_lifecycle import WorkerLifecycleController
from gateway_backend.operations.worker_startup import WorkerStartup

_DEFAULT_HEARTBEAT_INTERVAL = 10.0
_DEFAULT_IDLE_POLL = 1.0
_DEFAULT_BUSY_BACKOFF_MIN = 1.0
_DEFAULT_BUSY_BACKOFF_MAX = 10.0


class _ExecutorThread(Protocol):
    @property
    def daemon(self) -> bool: ...

    def start(self) -> None: ...

    def join(self) -> None: ...


ThreadFactory = Callable[[Callable[[], None]], _ExecutorThread]
Wait = Callable[[float], bool]
DrainRequested = Callable[[], bool]
Jitter = Callable[[float, float], float]


def _new_executor_thread(target: Callable[[], None]) -> _ExecutorThread:
    return threading.Thread(target=target, daemon=False)


def _default_jitter(lower: float, upper: float) -> float:
    return random.uniform(lower, upper)


_NO_EXECUTOR_VALUE = object()


@dataclass(slots=True)
class _ExecutorOutcome:
    value: object = _NO_EXECUTOR_VALUE
    error: BaseException | None = None


class WorkerRuntime:
    """Run one worker with at most one active executor and lease session.

    The runtime owns only process-local scheduling.  Durable operation mutations remain
    exclusively behind ``LeaseSession`` and the injected transaction factory.
    """

    __slots__ = (
        "_startup",
        "_write_uow_factory",
        "_observer",
        "_monotonic",
        "_lifecycle",
        "_thread_factory",
        "_jitter",
        "_heartbeat_interval",
        "_lease_duration",
        "_idle_poll",
        "_busy_backoff_min",
        "_busy_backoff_max",
    )

    def __init__(
        self,
        *,
        startup: WorkerStartup,
        write_uow_factory: WriteUnitOfWorkFactory,
        observer: WorkerObserver,
        lifecycle: WorkerLifecycleController | None = None,
        monotonic: Callable[[], float] = time.monotonic,
        thread_factory: ThreadFactory = _new_executor_thread,
        jitter: Jitter = _default_jitter,
        heartbeat_interval: float = _DEFAULT_HEARTBEAT_INTERVAL,
        lease_duration: float = LEASE_DURATION.total_seconds(),
        idle_poll: float = _DEFAULT_IDLE_POLL,
        busy_backoff_min: float = _DEFAULT_BUSY_BACKOFF_MIN,
        busy_backoff_max: float = _DEFAULT_BUSY_BACKOFF_MAX,
    ) -> None:
        if not callable(getattr(startup, "startup", None)) or not callable(
            getattr(startup, "claim_one", None)
        ):
            raise ValueError("startup must provide callable startup and claim_one methods")
        if not callable(write_uow_factory):
            raise ValueError("write_uow_factory must be callable")
        if not callable(observer):
            raise ValueError("observer must be callable")
        if not callable(monotonic):
            raise ValueError("monotonic must be callable")
        if not callable(thread_factory):
            raise ValueError("thread_factory must be callable")
        if not callable(jitter):
            raise ValueError("jitter must be callable")
        for value, label in (
            (heartbeat_interval, "heartbeat_interval"),
            (lease_duration, "lease_duration"),
            (idle_poll, "idle_poll"),
            (busy_backoff_min, "busy_backoff_min"),
            (busy_backoff_max, "busy_backoff_max"),
        ):
            _validate_positive_number(value, label)
        if lease_duration <= heartbeat_interval:
            raise ValueError("lease_duration must exceed heartbeat_interval")
        if busy_backoff_min > busy_backoff_max:
            raise ValueError("busy_backoff_min must not exceed busy_backoff_max")

        self._startup = startup
        self._write_uow_factory = write_uow_factory
        self._observer = observer
        self._monotonic = monotonic
        self._lifecycle = lifecycle or WorkerLifecycleController(monotonic=monotonic)
        self._thread_factory = thread_factory
        self._jitter = jitter
        self._heartbeat_interval = float(heartbeat_interval)
        self._lease_duration = float(lease_duration)
        self._idle_poll = float(idle_poll)
        self._busy_backoff_min = float(busy_backoff_min)
        self._busy_backoff_max = float(busy_backoff_max)

    def run(self, drain_requested: DrainRequested, wait: Wait) -> None:
        """Run until clean drain, timeout supervision, or a worker-fatal condition."""

        if not callable(drain_requested):
            raise ValueError("drain_requested must be callable")
        if not callable(wait):
            raise ValueError("wait must be callable")

        startup_attempt = 0
        while True:
            self._observe_drain_intent(drain_requested)
            disposition = self._startup.startup()
            if disposition is StartupDisposition.READY:
                if self._lifecycle.mark_ready_to_claim():
                    self._emit_drain_started()
                break
            if disposition is StartupDisposition.FATAL_BLOCK:
                raise ValueError("worker startup was fatally blocked")
            startup_attempt += 1
            self._wait_backoff(startup_attempt, drain_requested, wait)

        claim_busy_attempt = 0
        while True:
            self._observe_drain_intent(drain_requested)
            if self._lifecycle.state is WorkerLifecycle.DRAINING:
                self._finish_clean_drain()
                return
            if self._lifecycle.state is WorkerLifecycle.DRAINING_TIMEOUT:
                raise RuntimeError("worker drain timed out")

            claim_anchor = self._monotonic()
            try:
                work = self._startup.claim_one()
            except StoreBusy:
                claim_busy_attempt += 1
                self._emit(
                    WorkerEvent(
                        code=WorkerEventCode.CLAIM_BUSY,
                        attempt=claim_busy_attempt,
                    )
                )
                self._wait_backoff(claim_busy_attempt, drain_requested, wait)
                continue

            claim_busy_attempt = 0
            if work is None:
                self._wait_interruptibly(self._idle_poll, drain_requested, wait)
                continue

            self._run_claim(work, drain_requested, wait, claim_anchor=claim_anchor)
            state: WorkerLifecycle = self._lifecycle.state
            if state is WorkerLifecycle.QUIESCED:
                self._finish_clean_drain()
                return
            if state is WorkerLifecycle.DRAINING_TIMEOUT:
                raise RuntimeError("worker drain timed out")

    def _run_claim(
        self,
        work: ClaimedWork,
        drain_requested: DrainRequested,
        wait: Wait,
        *,
        claim_anchor: float,
    ) -> None:
        worker_id = work.step.worker_id
        lease_token = work.step.lease_token
        if not isinstance(worker_id, str) or not worker_id:
            raise ValueError("claimed step must have a worker_id")
        if not isinstance(lease_token, str) or not lease_token:
            raise ValueError("claimed step must have a lease_token")

        control = ExecutionControl()
        session = LeaseSession(
            worker_id=worker_id,
            lease_token=lease_token,
            operation_id=work.operation.operation_id,
            step_id=work.step.step_id,
            write_uow_factory=self._write_uow_factory,
            control=control,
            observer=self._observer,
        )
        session.refresh_control()
        lease_deadline = claim_anchor + self._lease_duration
        if self._monotonic() >= lease_deadline:
            self._fence_lease_for_busy_budget(work, control)
            raise StoreBusy("lease budget exhausted before executor start")
        self._lifecycle.mark_executor_started()
        self._observe_drain_intent(drain_requested, control)

        outcome = _ExecutorOutcome()
        completed = threading.Event()

        def execute() -> None:
            try:
                outcome.value = work.executor(
                    work.operation,
                    work.step,
                    control,
                    session,
                )
            except BaseException as error:
                outcome.error = error
            finally:
                completed.set()

        thread = self._thread_factory(execute)
        if thread.daemon:
            raise ValueError("executor thread must be non-daemon")
        thread.start()

        pending_drain = self._lifecycle.state is WorkerLifecycle.DRAINING
        next_heartbeat = claim_anchor + self._heartbeat_interval

        try:
            while not completed.is_set():
                self._observe_drain_intent(drain_requested, control)
                pending_drain = pending_drain or self._lifecycle.state is WorkerLifecycle.DRAINING
                if self._lifecycle.check_timeout():
                    self._emit_drain_timeout()

                now = self._monotonic()
                if now >= next_heartbeat:
                    pending_drain, heartbeat_succeeded, renewal_anchor = self._heartbeat_until_due(
                        work=work,
                        session=session,
                        control=control,
                        completed=completed,
                        pending_drain=pending_drain,
                        lease_deadline=lease_deadline,
                        drain_requested=drain_requested,
                        wait=wait,
                    )
                    if heartbeat_succeeded:
                        assert renewal_anchor is not None
                        next_heartbeat = renewal_anchor + self._heartbeat_interval
                        lease_deadline = renewal_anchor + self._lease_duration
                    continue

                timeout = max(0.0, next_heartbeat - now)
                drain_deadline = self._lifecycle.drain_deadline
                if (
                    pending_drain
                    and self._lifecycle.state is WorkerLifecycle.DRAINING
                    and drain_deadline is not None
                ):
                    timeout = min(timeout, max(0.0, drain_deadline - now))

                if pending_drain:
                    completed.wait(timeout)
                elif self._wait_interruptibly(timeout, drain_requested, wait):
                    pending_drain = True
                    self._observe_drain_intent(drain_requested, control)
        except BaseException:
            thread.join()
            raise

        thread.join()
        if self._lifecycle.check_timeout():
            self._emit_drain_timeout()
        self._observe_drain_intent(drain_requested, control)
        acknowledgment = self._validate_executor_outcome(work, session, outcome)
        self._lifecycle.mark_executor_completed(acknowledgment)

    def _heartbeat_until_due(
        self,
        *,
        work: ClaimedWork,
        session: LeaseSession,
        control: ExecutionControl,
        completed: threading.Event,
        pending_drain: bool,
        lease_deadline: float,
        drain_requested: DrainRequested,
        wait: Wait,
    ) -> tuple[bool, bool, float | None]:
        retry_attempt = 0
        while True:
            if completed.is_set():
                return pending_drain, False, None
            now = self._monotonic()
            self._observe_drain_intent(drain_requested, control)
            pending_drain = pending_drain or self._lifecycle.state is WorkerLifecycle.DRAINING
            if self._lifecycle.check_timeout():
                self._emit_drain_timeout()
            if now >= lease_deadline:
                self._fence_lease_for_busy_budget(work, control)
                raise StoreBusy("heartbeat retry budget exhausted before lease renewal")
            renewal_anchor = self._monotonic()
            try:
                session.heartbeat()
            except StoreBusy:
                retry_attempt += 1
                self._emit(
                    WorkerEvent(
                        code=WorkerEventCode.HEARTBEAT_BUSY,
                        operation_id=work.operation.operation_id,
                        step_id=work.step.step_id,
                        attempt=retry_attempt,
                    )
                )
                remaining = lease_deadline - self._monotonic()
                if remaining <= 0:
                    self._fence_lease_for_busy_budget(work, control)
                    raise StoreBusy("heartbeat retry budget exhausted before lease renewal")
                delay = self._backoff_delay(retry_attempt)
                if delay > remaining:
                    delay = remaining
                if pending_drain:
                    completed.wait(delay)
                elif self._wait_interruptibly(delay, drain_requested, wait):
                    pending_drain = True
                    self._observe_drain_intent(drain_requested, control)
                continue
            except (StaleWrite, LeaseExpired):
                if session.completion_acknowledgment() is not None:
                    completed.wait()
                    return pending_drain, False, None
                raise
            return pending_drain, True, renewal_anchor

    def _validate_executor_outcome(
        self,
        work: ClaimedWork,
        session: LeaseSession,
        outcome: _ExecutorOutcome,
    ) -> ExecutorAcknowledgment:
        if outcome.error is not None:
            self._emit_executor_failure(work, "executor_exception")
            raise outcome.error
        if type(outcome.value) is not ExecutorAcknowledgment:
            self._emit_executor_failure(work, "unproven_acknowledgment")
            raise ValueError("executor returned an unproven acknowledgment")

        acknowledgment = outcome.value
        committed = session.completion_acknowledgment()
        if acknowledgment is not committed or committed not in {
            ExecutorAcknowledgment.PUBLISHED,
            ExecutorAcknowledgment.SAFE_HANDOFF,
        }:
            self._emit_executor_failure(work, "unproven_acknowledgment")
            raise ValueError("executor acknowledgment was not committed by LeaseSession")
        return acknowledgment

    def _fence_lease_for_busy_budget(
        self,
        work: ClaimedWork,
        control: ExecutionControl,
    ) -> None:
        control.mark_lease_lost()
        self._emit(
            WorkerEvent(
                code=WorkerEventCode.LEASE_LOST,
                operation_id=work.operation.operation_id,
                step_id=work.step.step_id,
                error_category="heartbeat_busy_deadline",
            )
        )

    def _wait_backoff(
        self,
        attempt: int,
        drain_requested: DrainRequested,
        wait: Wait,
    ) -> bool:
        return self._wait_interruptibly(
            self._backoff_delay(attempt),
            drain_requested,
            wait,
        )

    def _backoff_delay(self, attempt: int) -> float:
        if type(attempt) is not int or attempt < 1:
            raise ValueError("backoff attempt must be a positive integer")
        base = min(
            self._busy_backoff_max,
            self._busy_backoff_min * (2 ** (attempt - 1)),
        )
        delay = self._jitter(base, self._busy_backoff_max)
        if isinstance(delay, bool) or not isinstance(delay, (int, float)):
            raise ValueError("jitter must return a number")
        if delay < base or delay > self._busy_backoff_max:
            raise ValueError("jitter result must remain within the bounded backoff")
        return float(delay)

    @staticmethod
    def _wait_interruptibly(
        timeout: float,
        drain_requested: DrainRequested,
        wait: Wait,
    ) -> bool:
        if drain_requested():
            return True
        if wait(timeout):
            return True
        return drain_requested()

    def _observe_drain_intent(
        self,
        drain_requested: DrainRequested,
        control: ExecutionControl | None = None,
    ) -> None:
        if drain_requested():
            if control is not None:
                control.request_drain()
            if self._lifecycle.request_drain():
                self._emit_drain_started()

    def _finish_clean_drain(self) -> None:
        if self._lifecycle.state is WorkerLifecycle.DRAINING:
            self._lifecycle.mark_idle_quiesced()
        if self._lifecycle.state is not WorkerLifecycle.QUIESCED:
            raise ValueError("clean drain requires QUIESCED lifecycle")
        self._lifecycle.mark_stopping()
        self._lifecycle.mark_exited()
        self._emit(
            WorkerEvent(
                code=WorkerEventCode.WORKER_EXITED,
            )
        )

    def _emit_drain_started(self) -> None:
        self._emit(WorkerEvent(code=WorkerEventCode.DRAIN_STARTED))

    def _emit_drain_timeout(self) -> None:
        self._emit(WorkerEvent(code=WorkerEventCode.DRAIN_TIMED_OUT))

    def _emit_executor_failure(self, work: ClaimedWork, category: str) -> None:
        self._emit(
            WorkerEvent(
                code=WorkerEventCode.EXECUTOR_FAILED,
                operation_id=work.operation.operation_id,
                step_id=work.step.step_id,
                attempt=work.step.attempt_count,
                error_category=category,
            )
        )

    def _emit(self, event: WorkerEvent) -> None:
        self._observer(event)


def _validate_positive_number(value: object, label: str) -> None:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or value <= 0:
        raise ValueError(f"{label} must be a positive number")


__all__ = ["WorkerRuntime"]
