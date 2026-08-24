"""Process-local worker lifecycle and graceful drain coordination."""

from __future__ import annotations

import time
from collections.abc import Callable

from gateway_backend.operations.worker import ExecutorAcknowledgment, WorkerLifecycle

DEFAULT_DRAIN_TIMEOUT_SECONDS = 180.0
Monotonic = Callable[[], float]


class WorkerLifecycleController:
    """Own the non-durable lifecycle of one operation-worker process.

    The controller deliberately contains no wait primitive, signal handling, or
    persistence.  ``WorkerRuntime`` is the only caller that advances executor
    and shutdown state; external callers only submit the monotonic drain intent.
    """

    __slots__ = (
        "_monotonic",
        "_drain_timeout",
        "_state",
        "_drain_intent",
        "_drain_deadline",
        "_executor_active",
    )

    def __init__(
        self,
        *,
        monotonic: Monotonic = time.monotonic,
        drain_timeout: float = DEFAULT_DRAIN_TIMEOUT_SECONDS,
    ) -> None:
        if not callable(monotonic):
            raise ValueError("monotonic must be callable")
        if isinstance(drain_timeout, bool) or not isinstance(drain_timeout, (int, float)):
            raise ValueError("drain_timeout must be a positive number")
        if drain_timeout <= 0:
            raise ValueError("drain_timeout must be a positive number")

        self._monotonic = monotonic
        self._drain_timeout = float(drain_timeout)
        self._state = WorkerLifecycle.STARTING
        self._drain_intent = False
        self._drain_deadline: float | None = None
        self._executor_active = False

    @property
    def state(self) -> WorkerLifecycle:
        """Return the current worker-local lifecycle state."""

        return self._state

    @property
    def drain_requested(self) -> bool:
        """Return whether a drain intent has been latched."""

        return self._drain_intent

    @property
    def drain_deadline(self) -> float | None:
        """Return the monotonic deadline once draining has started."""

        return self._drain_deadline

    @property
    def executor_active(self) -> bool:
        """Return whether the worker currently owns an executor slot."""

        return self._executor_active

    def mark_ready_to_claim(self) -> bool:
        """Complete startup and optionally enter drain before the first claim.

        A drain requested during startup is latched while the worker remains in
        ``STARTING``.  Once startup succeeds, the state still passes through
        ``READY_TO_CLAIM`` and immediately enters ``DRAINING`` without claiming.
        """

        if self._state is not WorkerLifecycle.STARTING:
            raise ValueError("worker startup can only complete from STARTING")
        self._state = WorkerLifecycle.READY_TO_CLAIM
        if self._drain_intent:
            return self._enter_draining()
        return False

    def request_drain(self) -> bool:
        """Latch drain intent and return whether this call started draining."""

        self._drain_intent = True
        if self._state is WorkerLifecycle.READY_TO_CLAIM:
            return self._enter_draining()
        return False

    def mark_executor_started(self) -> None:
        """Record the single active executor slot."""

        if self._state not in {
            WorkerLifecycle.READY_TO_CLAIM,
            WorkerLifecycle.DRAINING,
        }:
            raise ValueError("executor cannot start in the current lifecycle state")
        if self._executor_active:
            raise ValueError("worker already has an active executor")
        self._executor_active = True

    def mark_executor_completed(self, acknowledgment: ExecutorAcknowledgment) -> bool:
        """Release the executor slot and quiesce a clean draining worker."""

        if type(acknowledgment) is not ExecutorAcknowledgment:
            raise ValueError("acknowledgment must be ExecutorAcknowledgment")
        if not self._executor_active:
            raise ValueError("worker has no active executor")

        self._executor_active = False
        if self._state is WorkerLifecycle.DRAINING:
            self._state = WorkerLifecycle.QUIESCED
            return True
        return False

    def mark_idle_quiesced(self) -> None:
        """Quiesce after drain when no executor was ever active."""

        if self._state is not WorkerLifecycle.DRAINING:
            raise ValueError("idle quiescence requires DRAINING")
        if self._executor_active:
            raise ValueError("active executor prevents idle quiescence")
        self._state = WorkerLifecycle.QUIESCED

    def check_timeout(self) -> bool:
        """Enter the one-way timeout state when the drain deadline is reached."""

        if self._state is not WorkerLifecycle.DRAINING:
            return False
        if self._drain_deadline is None:
            raise ValueError("DRAINING must have a deadline")
        if self._monotonic() < self._drain_deadline:
            return False
        self._state = WorkerLifecycle.DRAINING_TIMEOUT
        return True

    def mark_stopping(self) -> None:
        """Move a cleanly quiesced worker to its stopping state."""

        if self._state is not WorkerLifecycle.QUIESCED:
            raise ValueError("worker can stop only from QUIESCED")
        self._state = WorkerLifecycle.STOPPING

    def mark_exited(self) -> None:
        """Record clean process-local exit after STOPPING."""

        if self._state is not WorkerLifecycle.STOPPING:
            raise ValueError("worker can exit only from STOPPING")
        self._state = WorkerLifecycle.EXITED

    def _enter_draining(self) -> bool:
        if self._state is not WorkerLifecycle.READY_TO_CLAIM:
            return False
        self._state = WorkerLifecycle.DRAINING
        self._drain_deadline = self._monotonic() + self._drain_timeout
        return True


__all__ = ["DEFAULT_DRAIN_TIMEOUT_SECONDS", "WorkerLifecycleController"]
