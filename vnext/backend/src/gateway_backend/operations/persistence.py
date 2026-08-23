"""SQLite-neutral atomic compositions for the durable operation lifecycle."""

from __future__ import annotations

import dataclasses
from datetime import UTC, datetime, timedelta

from gateway_backend.operations.contracts import (
    OperationRecord,
    OperationStatus,
    StepRecord,
    StepStatus,
)
from gateway_backend.operations.state import TransitionDisposition, WritePrecondition
from gateway_backend.operations.store import OperationStore

LEASE_DURATION = timedelta(seconds=30)


class OperationLifecycleActions:
    """Compose guarded operation mutations inside a caller-owned transaction.

    The class intentionally only depends on the SQLite-neutral ``OperationStore`` port.  The
    caller must construct it from a store bound to an active writable UoW and must let that UoW
    own commit and rollback.
    """

    def __init__(
        self,
        store: OperationStore,
        *,
        transaction_now: datetime,
    ) -> None:
        if not isinstance(store, OperationStore):
            raise ValueError("store must satisfy OperationStore")
        _validate_utc_datetime(transaction_now, "transaction_now")
        self._store = store
        self._transaction_now = transaction_now

    def claim_one(
        self,
        worker_id: str,
        lease_token: str,
    ) -> tuple[OperationRecord, StepRecord] | None:
        """Claim the first due runnable step, or return ``None`` when no candidate exists."""

        _validate_identity(worker_id, "worker_id")
        _validate_identity(lease_token, "lease_token")
        candidates, _ = self._store.list_claim_candidates(
            self._transaction_now,
            limit=1,
        )
        if not candidates:
            return None

        candidate = candidates[0]
        operation = self._store.get_operation(candidate.operation_id)
        step = self._store.get_step(candidate.step_id)
        if operation.status not in {OperationStatus.QUEUED, OperationStatus.RUNNING}:
            raise ValueError("claim candidate operation is not runnable")
        if step.status not in {StepStatus.PENDING, StepStatus.RETRY_WAIT}:
            raise ValueError("claim candidate step is not runnable")
        if step.operation_id != operation.operation_id:
            raise ValueError("claim candidate step belongs to a different operation")

        operation_after = operation
        if operation.status is OperationStatus.QUEUED:
            operation_after = dataclasses.replace(
                operation,
                status=OperationStatus.RUNNING,
                updated_at=self._transaction_now,
                optimistic_version=operation.optimistic_version + 1,
            )
            self._store.compare_and_set_operation(
                operation_after,
                _null_precondition(operation),
            )

        step_after = dataclasses.replace(
            step,
            status=StepStatus.RUNNING,
            attempt_count=step.attempt_count + 1,
            updated_at=self._transaction_now,
            started_at=(
                self._transaction_now if step.started_at is None else step.started_at
            ),
            diagnostic=None,
            retry_not_before=None,
            worker_id=worker_id,
            lease_token=lease_token,
            lease_expires_at=self._transaction_now + LEASE_DURATION,
            optimistic_version=step.optimistic_version + 1,
        )
        self._store.compare_and_set_step(
            step_after,
            _null_precondition(step),
        )
        return operation_after, step_after

    def mutate_live_step(
        self,
        candidate: StepRecord,
        precondition: WritePrecondition,
        *,
        recovery_authorized: bool = False,
    ) -> TransitionDisposition:
        """Apply a heartbeat, checkpoint, or terminal candidate under its live lease."""

        return self._store.compare_and_set_step(
            candidate,
            precondition,
            recovery_authorized=recovery_authorized,
            require_live_lease=True,
        )

    def cancel_intent(
        self,
        operation_candidate: OperationRecord,
        operation_precondition: WritePrecondition,
        step_candidate: StepRecord,
        step_precondition: WritePrecondition,
    ) -> tuple[TransitionDisposition, TransitionDisposition]:
        """Persist cancellation intent on an operation and its current non-final step."""

        if not operation_candidate.cancel_requested or not step_candidate.cancel_requested:
            raise ValueError("cancel intent candidates must set cancel_requested")
        if operation_candidate.status not in {OperationStatus.QUEUED, OperationStatus.RUNNING}:
            raise ValueError("cancel intent requires a QUEUED or RUNNING operation")
        if step_candidate.status not in {
            StepStatus.PENDING,
            StepStatus.RETRY_WAIT,
            StepStatus.RUNNING,
        }:
            raise ValueError("cancel intent requires a non-final runnable step")
        if step_candidate.operation_id != operation_candidate.operation_id:
            raise ValueError("cancel intent candidates must belong to one operation")

        operation_disposition = self._store.compare_and_set_operation(
            operation_candidate,
            operation_precondition,
        )
        step_disposition = self._store.compare_and_set_step(
            step_candidate,
            step_precondition,
            require_live_lease=step_candidate.status is StepStatus.RUNNING,
        )
        return operation_disposition, step_disposition

    def complete_with_successor(
        self,
        step_candidate: StepRecord,
        step_precondition: WritePrecondition,
        successor: StepRecord,
        *,
        recovery_authorized: bool = False,
    ) -> tuple[TransitionDisposition, TransitionDisposition]:
        """Complete a live step and materialize its caller-selected pending successor."""

        if not step_candidate.status.is_final_terminal():
            raise ValueError("successor composition requires a final step candidate")
        if successor.status is not StepStatus.PENDING:
            raise ValueError("successor composition requires a PENDING successor")
        if successor.operation_id != step_candidate.operation_id:
            raise ValueError("step and successor must belong to one operation")
        step_disposition = self.mutate_live_step(
            step_candidate,
            step_precondition,
            recovery_authorized=recovery_authorized,
        )
        successor_disposition = self._store.insert_successor_step(successor)
        return step_disposition, successor_disposition

    def complete_operation(
        self,
        step_candidate: StepRecord,
        step_precondition: WritePrecondition,
        operation_candidate: OperationRecord,
        operation_precondition: WritePrecondition,
        *,
        step_recovery_authorized: bool = False,
        operation_recovery_authorized: bool = False,
    ) -> tuple[TransitionDisposition, TransitionDisposition]:
        """Complete a live step and publish its caller-selected operation outcome."""

        if step_candidate.operation_id != operation_candidate.operation_id:
            raise ValueError("step and operation candidates must belong to one operation")
        if not (
            step_candidate.status.is_final_terminal()
            or step_candidate.status.requires_manual_recovery()
        ):
            raise ValueError("operation composition requires a terminal or recovery step candidate")
        if not (
            operation_candidate.status.is_final_terminal()
            or operation_candidate.status.requires_manual_recovery()
        ):
            raise ValueError(
                "operation composition requires a terminal or recovery operation candidate"
            )
        step_disposition = self.mutate_live_step(
            step_candidate,
            step_precondition,
            recovery_authorized=step_recovery_authorized,
        )
        operation_disposition = self._store.compare_and_set_operation(
            operation_candidate,
            operation_precondition,
            recovery_authorized=operation_recovery_authorized,
        )
        return step_disposition, operation_disposition


def _null_precondition(record: OperationRecord | StepRecord) -> WritePrecondition:
    return WritePrecondition(
        expected_optimistic_version=record.optimistic_version,
        worker_id=None,
        lease_token=None,
    )


def _validate_identity(value: object, label: str) -> None:
    if type(value) is not str or not value:
        raise ValueError(f"{label} must be a non-empty string")
    if len(value.encode("utf-8")) > 255:
        raise ValueError(f"{label} exceeds maximum length")


def _validate_utc_datetime(value: object, label: str) -> None:
    if not isinstance(value, datetime) or value.tzinfo is None:
        raise ValueError(f"{label} must be an aware UTC datetime")
    if value.utcoffset() != UTC.utcoffset(value):
        raise ValueError(f"{label} must be an aware UTC datetime")


__all__ = ["LEASE_DURATION", "OperationLifecycleActions"]
