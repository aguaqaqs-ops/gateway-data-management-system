"""SQLite-neutral worker contracts and process-local execution control."""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import TYPE_CHECKING, Protocol, runtime_checkable

if TYPE_CHECKING:
    from gateway_backend.operations.recovery import RecoveryTransitionIntent

from gateway_backend.operations.contracts import (
    JobStepKey,
    OperationDiagnostic,
    OperationRecord,
    StepRecord,
    _validate_ijson_int_value,
    _validate_opaque_id,
)
from gateway_backend.operations.state import TransitionDisposition
from gateway_backend.operations.store import OperationUnitOfWork

_EVENT_CATEGORY_RE = re.compile(r"^[A-Za-z0-9_.:-]{1,128}$")


class WorkerLifecycle(StrEnum):
    """Worker-local lifecycle values; these are not persisted operation states."""

    STARTING = "STARTING"
    READY_TO_CLAIM = "READY_TO_CLAIM"
    DRAINING = "DRAINING"
    QUIESCED = "QUIESCED"
    STOPPING = "STOPPING"
    EXITED = "EXITED"
    DRAINING_TIMEOUT = "DRAINING_TIMEOUT"


class StartupDisposition(StrEnum):
    """Bounded result of a startup or recovery gate."""

    READY = "READY"
    RETRYABLE_BLOCK = "RETRYABLE_BLOCK"
    FATAL_BLOCK = "FATAL_BLOCK"


class ExecutorAcknowledgment(StrEnum):
    """Closed acknowledgments understood by the future scheduler."""

    PUBLISHED = "PUBLISHED"
    SAFE_HANDOFF = "SAFE_HANDOFF"


class WorkerEventCode(StrEnum):
    """Stable, intentionally small worker event vocabulary."""

    STARTUP_FAILED = "startup_failed"
    WORKER_READY = "worker_ready"
    CLAIM_SUCCEEDED = "claim_succeeded"
    CLAIM_BUSY = "claim_busy"
    HEARTBEAT_SUCCEEDED = "heartbeat_succeeded"
    HEARTBEAT_BUSY = "heartbeat_busy"
    LEASE_LOST = "lease_lost"
    EXECUTOR_FAILED = "executor_failed"
    DRAIN_STARTED = "drain_started"
    SAFE_HANDOFF = "safe_handoff"
    DRAIN_TIMED_OUT = "drain_timed_out"
    WORKER_EXITED = "worker_exited"


@dataclass(frozen=True, slots=True)
class WorkerEvent:
    """Redacted, bounded event data suitable for an injected observer."""

    code: WorkerEventCode
    operation_id: str | None = None
    step_id: str | None = None
    worker_id: str | None = None
    attempt: int | None = None
    error_category: str | None = None
    duration_ms: int | None = None

    def __post_init__(self) -> None:
        if type(self.code) is not WorkerEventCode:
            raise ValueError("code must be WorkerEventCode")
        for event_id, label in (
            (self.operation_id, "operation_id"),
            (self.step_id, "step_id"),
            (self.worker_id, "worker_id"),
        ):
            if event_id is not None:
                _validate_opaque_id(event_id, label)
        for number, label in (
            (self.attempt, "attempt"),
            (self.duration_ms, "duration_ms"),
        ):
            if number is not None:
                _validate_ijson_int_value(number, label)
        if self.error_category is not None:
            if type(self.error_category) is not str or not _EVENT_CATEGORY_RE.fullmatch(
                self.error_category
            ):
                raise ValueError("error_category must match the bounded event category pattern")


class ExecutionControl:
    """Monotonic process-local control signals without an exposed wait primitive."""

    __slots__ = ("_drain_requested", "_cancel_requested", "_lease_lost")

    def __init__(self) -> None:
        self._drain_requested = False
        self._cancel_requested = False
        self._lease_lost = False

    @property
    def drain_requested(self) -> bool:
        return self._drain_requested

    @property
    def cancel_requested(self) -> bool:
        return self._cancel_requested

    @property
    def lease_lost(self) -> bool:
        return self._lease_lost

    def request_drain(self) -> None:
        self._drain_requested = True

    def request_cancel(self) -> None:
        self._cancel_requested = True

    def mark_lease_lost(self) -> None:
        self._lease_lost = True


@dataclass(frozen=True, slots=True)
class CheckpointGeneration:
    """Opaque, non-secret identity for a committed checkpoint mutation."""

    operation_id: str
    step_id: str
    optimistic_version: int

    def __post_init__(self) -> None:
        _validate_opaque_id(self.operation_id, "operation_id")
        _validate_opaque_id(self.step_id, "step_id")
        _validate_ijson_int_value(self.optimistic_version, "optimistic_version")


@dataclass(frozen=True, slots=True)
class ClaimedWork:
    """The committed records and in-memory executor for one claimed step."""

    operation: OperationRecord
    step: StepRecord
    executor: ClaimedExecutor

    def __post_init__(self) -> None:
        if type(self.operation) is not OperationRecord:
            raise ValueError("operation must be OperationRecord")
        if type(self.step) is not StepRecord:
            raise ValueError("step must be StepRecord")
        if not callable(self.executor):
            raise ValueError("executor must be callable")
        if self.step.operation_id != self.operation.operation_id:
            raise ValueError("claimed step must belong to the claimed operation")


@runtime_checkable
class LeaseSession(Protocol):
    """Per-claim capability that serializes fresh lease mutations."""

    def refresh_control(self) -> None:
        """Reload cancellation and lease state before executor work."""

    def heartbeat(self) -> StepRecord:
        """Extend the current lease using a fresh transaction-scoped Step."""

    def publish_checkpoint(
        self,
        builder: Callable[[OperationRecord, StepRecord, datetime], StepRecord],
    ) -> CheckpointGeneration:
        """Publish a same-status RUNNING Step checkpoint."""

    def publish_successor(
        self,
        builder: Callable[
            [OperationRecord, StepRecord, datetime], tuple[StepRecord, StepRecord]
        ],
    ) -> tuple[TransitionDisposition, TransitionDisposition]:
        """Publish a terminal Step and one pending successor atomically."""

    def publish_operation(
        self,
        builder: Callable[
            [OperationRecord, StepRecord, datetime], tuple[StepRecord, OperationRecord]
        ],
    ) -> tuple[TransitionDisposition, TransitionDisposition]:
        """Publish a terminal/manual Step and terminal/manual Operation atomically."""

    def acknowledge_safe_handoff(
        self,
        generation: CheckpointGeneration,
    ) -> ExecutorAcknowledgment:
        """Acknowledge handoff only for a checkpoint committed by this session."""

    def publish_recovery_release(
        self,
        intent: RecoveryTransitionIntent,
        *,
        diagnostic: OperationDiagnostic,
    ) -> ExecutorAcknowledgment:
        """Release a live lease into a bounded recovery transition."""

    def completion_acknowledgment(self) -> ExecutorAcknowledgment | None:
        """Return the terminal or safe-handoff fact committed by this session."""


@runtime_checkable
class WorkerRegistry(Protocol):
    """Immutable lookup surface keyed by the existing R1 JobStepKey."""

    def resolve(self, key: JobStepKey) -> ClaimedExecutor | None:
        """Return the executor for a key, or None when the key is not registered."""


@runtime_checkable
class ClaimedExecutor(Protocol):
    """Executor input is limited to R1 records and process-local worker capabilities."""

    def __call__(
        self,
        operation: OperationRecord,
        step: StepRecord,
        control: ExecutionControl,
        lease_session: LeaseSession,
    ) -> ExecutorAcknowledgment:
        """Execute one claimed step and return a closed acknowledgment."""


@runtime_checkable
class RecoveryHook(Protocol):
    """Injected startup recovery decision; policy remains outside R3."""

    def __call__(self, operation: OperationRecord, step: StepRecord) -> StartupDisposition:
        """Inspect one active pair and return a bounded startup disposition."""


@runtime_checkable
class WorkerObserver(Protocol):
    """Minimal observer sink for already-redacted worker events."""

    def __call__(self, event: WorkerEvent) -> None:
        """Consume one bounded worker event."""


@runtime_checkable
class ReadUnitOfWorkFactory(Protocol):
    """Factory for a fresh transaction-scoped read UoW."""

    def __call__(self) -> OperationUnitOfWork:
        """Create a fresh read unit of work."""


@runtime_checkable
class WriteUnitOfWorkFactory(Protocol):
    """Factory for a fresh transaction-scoped write UoW."""

    def __call__(self) -> OperationUnitOfWork:
        """Create a fresh write unit of work."""


__all__ = [
    "ClaimedExecutor",
    "ClaimedWork",
    "CheckpointGeneration",
    "ExecutionControl",
    "ExecutorAcknowledgment",
    "LeaseSession",
    "ReadUnitOfWorkFactory",
    "RecoveryHook",
    "StartupDisposition",
    "WorkerEvent",
    "WorkerEventCode",
    "WorkerLifecycle",
    "WorkerObserver",
    "WorkerRegistry",
    "WriteUnitOfWorkFactory",
]
