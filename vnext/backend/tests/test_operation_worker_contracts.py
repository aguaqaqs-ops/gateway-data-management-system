"""SQLite-neutral worker contract tests."""

from __future__ import annotations

import inspect
from dataclasses import fields, is_dataclass
from typing import Any, cast, get_type_hints

import pytest

import gateway_backend.operations as operations
import gateway_backend.operations.worker as worker
from gateway_backend.operations import JobStepKey, OperationUnitOfWork
from gateway_backend.operations.contracts import OperationDiagnostic, OperationRecord, StepRecord
from gateway_backend.operations.recovery import RecoveryTransitionIntent

pytestmark = pytest.mark.unit

EXPECTED_PUBLIC_EXPORTS = frozenset(
    {
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
    }
)

EXPECTED_EVENT_CODES = frozenset(
    {
        "startup_failed",
        "worker_ready",
        "claim_succeeded",
        "claim_busy",
        "heartbeat_succeeded",
        "heartbeat_busy",
        "lease_lost",
        "executor_failed",
        "drain_started",
        "safe_handoff",
        "drain_timed_out",
        "worker_exited",
    }
)

MALFORMED_EVENT_VALUES = (
    {"operation_id": ""},
    {"operation_id": "a" * 256},
    {"operation_id": "bad\nvalue"},
    {"attempt": True},
    {"attempt": -1},
    {"attempt": 2**53},
    {"error_category": ""},
    {"error_category": 1},
    {"error_category": "bad\nvalue"},
    {"error_category": "x" * 129},
    {"duration_ms": True},
    {"duration_ms": -1},
    {"duration_ms": 2**53},
)


def test_worker_module_has_exact_public_exports_and_root_surface_is_unchanged() -> None:
    assert frozenset(worker.__all__) == EXPECTED_PUBLIC_EXPORTS
    assert "ExecutionControl" not in operations.__all__
    assert "WorkerRegistry" not in operations.__all__


def test_worker_values_are_bounded_and_stable() -> None:
    assert {item.value for item in worker.WorkerLifecycle} == {
        "STARTING",
        "READY_TO_CLAIM",
        "DRAINING",
        "QUIESCED",
        "STOPPING",
        "EXITED",
        "DRAINING_TIMEOUT",
    }
    assert {item.value for item in worker.StartupDisposition} == {
        "READY",
        "RETRYABLE_BLOCK",
        "FATAL_BLOCK",
    }
    assert {item.value for item in worker.ExecutorAcknowledgment} == {
        "PUBLISHED",
        "SAFE_HANDOFF",
    }
    assert {item.value for item in worker.WorkerEventCode} == EXPECTED_EVENT_CODES


def test_checkpoint_generation_is_frozen_bounded_and_non_secret() -> None:
    generation = worker.CheckpointGeneration(
        operation_id="operation-1",
        step_id="step-1",
        optimistic_version=7,
    )
    assert is_dataclass(generation)
    assert generation.__slots__ == ("operation_id", "step_id", "optimistic_version")
    assert not hasattr(generation, "__dict__")
    assert "lease_token" not in generation.__slots__

    with pytest.raises(ValueError):
        worker.CheckpointGeneration("operation-1", "step-1", -1)


def test_claimed_work_rejects_non_record_inputs() -> None:
    operation = cast(OperationRecord, object())
    step = cast(StepRecord, object())

    with pytest.raises(ValueError, match="OperationRecord"):
        worker.ClaimedWork(operation, step, lambda *_args: worker.ExecutorAcknowledgment.PUBLISHED)


def test_worker_event_is_frozen_slotted_and_redacted() -> None:
    event = worker.WorkerEvent(
        code=worker.WorkerEventCode.CLAIM_SUCCEEDED,
        operation_id="operation-1",
        step_id="step-1",
        worker_id="worker-1",
        attempt=1,
        error_category="store.busy",
        duration_ms=25,
    )

    assert is_dataclass(event)
    assert event.__slots__ == (
        "code",
        "operation_id",
        "step_id",
        "worker_id",
        "attempt",
        "error_category",
        "duration_ms",
    )
    assert not hasattr(event, "__dict__")
    assert {field.name for field in fields(event)} == set(event.__slots__)
    assert not {
        "lease_token",
        "job_payload",
        "artifact_bytes",
        "absolute_db_path",
        "sql",
        "secret",
        "message",
    } & set(event.__slots__)


@pytest.mark.parametrize("changes", MALFORMED_EVENT_VALUES)
def test_worker_event_rejects_unbounded_or_non_redacted_values(
    changes: dict[str, object],
) -> None:
    with pytest.raises(ValueError):
        worker.WorkerEvent(code=worker.WorkerEventCode.WORKER_READY, **cast(Any, changes))


def test_execution_control_is_monotonic_and_does_not_expose_wait_primitives() -> None:
    control = worker.ExecutionControl()
    assert not control.drain_requested
    assert not control.cancel_requested
    assert not control.lease_lost
    assert not hasattr(control, "__dict__")
    assert not hasattr(control, "wait")
    assert not hasattr(control, "clear")

    control.request_drain()
    control.request_drain()
    control.request_cancel()
    control.request_cancel()
    control.mark_lease_lost()
    control.mark_lease_lost()

    assert control.drain_requested
    assert control.cancel_requested
    assert control.lease_lost


def test_protocol_signatures_use_existing_records_and_ports() -> None:
    registry_hints = get_type_hints(worker.WorkerRegistry.resolve)
    assert list(inspect.signature(worker.WorkerRegistry.resolve).parameters) == ["self", "key"]
    assert registry_hints["key"] is JobStepKey
    assert registry_hints["return"] == worker.ClaimedExecutor | None

    executor_hints = get_type_hints(worker.ClaimedExecutor.__call__)
    assert list(inspect.signature(worker.ClaimedExecutor.__call__).parameters) == [
        "self",
        "operation",
        "step",
        "control",
        "lease_session",
    ]
    assert executor_hints["operation"] is OperationRecord
    assert executor_hints["step"] is StepRecord
    assert executor_hints["control"] is worker.ExecutionControl
    assert executor_hints["lease_session"] is worker.LeaseSession
    assert executor_hints["return"] is worker.ExecutorAcknowledgment

    recovery_hints = get_type_hints(worker.RecoveryHook.__call__)
    assert recovery_hints["operation"] is OperationRecord
    assert recovery_hints["step"] is StepRecord
    assert recovery_hints["return"] is worker.StartupDisposition

    observer_hints = get_type_hints(worker.WorkerObserver.__call__)
    assert observer_hints["event"] is worker.WorkerEvent
    assert observer_hints["return"] is type(None)

    assert get_type_hints(worker.ReadUnitOfWorkFactory.__call__)["return"] is OperationUnitOfWork
    assert get_type_hints(worker.WriteUnitOfWorkFactory.__call__)["return"] is OperationUnitOfWork

    heartbeat_hints = get_type_hints(worker.LeaseSession.heartbeat)
    assert heartbeat_hints["return"] is StepRecord
    checkpoint_hints = get_type_hints(worker.LeaseSession.publish_checkpoint)
    assert checkpoint_hints["return"] is worker.CheckpointGeneration
    handoff_hints = get_type_hints(worker.LeaseSession.acknowledge_safe_handoff)
    assert handoff_hints["generation"] is worker.CheckpointGeneration
    assert handoff_hints["return"] is worker.ExecutorAcknowledgment
    release_hints = get_type_hints(
        worker.LeaseSession.publish_recovery_release,
        globalns={**worker.__dict__, "RecoveryTransitionIntent": RecoveryTransitionIntent},
    )
    assert release_hints["intent"] is RecoveryTransitionIntent
    assert release_hints["diagnostic"] is OperationDiagnostic
    assert release_hints["return"] is worker.ExecutorAcknowledgment
    completion_hints = get_type_hints(worker.LeaseSession.completion_acknowledgment)
    assert completion_hints["return"] == worker.ExecutorAcknowledgment | None


def test_registry_key_is_the_existing_job_step_key() -> None:
    key = JobStepKey(job_kind="import.package", step_name="validate")
    assert type(key) is JobStepKey
