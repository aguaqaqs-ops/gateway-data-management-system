"""Fresh-transaction lease mutation and publication capability."""

from __future__ import annotations

import dataclasses
import threading
from collections.abc import Callable
from datetime import datetime

from gateway_backend.operations.contracts import (
    OperationDiagnostic,
    OperationRecord,
    OperationStatus,
    StepRecord,
    StepStatus,
    _validate_opaque_id,
)
from gateway_backend.operations.persistence import LEASE_DURATION, OperationLifecycleActions
from gateway_backend.operations.recovery import RecoveryTransitionIntent
from gateway_backend.operations.state import TransitionDisposition, WritePrecondition, validate_step_transition
from gateway_backend.operations.store import (
    LeaseExpired,
    OperationUnitOfWork,
    StaleWrite,
)
from gateway_backend.operations.worker import (
    CheckpointGeneration,
    ExecutionControl,
    ExecutorAcknowledgment,
    WorkerEvent,
    WorkerEventCode,
    WorkerObserver,
    WriteUnitOfWorkFactory,
)

class LeaseSession:
    """One live lease's sole serialized channel for durable mutations.

    The session never retains a mutable Operation/Step snapshot between calls. Every
    mutation opens a new caller-owned transaction, reloads both records, and only then
    builds and applies a candidate through ``OperationLifecycleActions``.
    """

    __slots__ = (
        "_worker_id",
        "_lease_token",
        "_operation_id",
        "_step_id",
        "_write_uow_factory",
        "_control",
        "_observer",
        "_mutation_lock",
        "_closed",
        "_last_checkpoint_generation",
        "_completion_acknowledgment",
    )

    def __init__(
        self,
        *,
        worker_id: str,
        lease_token: str,
        operation_id: str,
        step_id: str,
        write_uow_factory: WriteUnitOfWorkFactory,
        control: ExecutionControl,
        observer: WorkerObserver,
    ) -> None:
        _validate_opaque_id(worker_id, "worker_id")
        _validate_opaque_id(lease_token, "lease_token")
        _validate_opaque_id(operation_id, "operation_id")
        _validate_opaque_id(step_id, "step_id")
        if not callable(write_uow_factory):
            raise ValueError("write_uow_factory must be callable")
        if type(control) is not ExecutionControl:
            raise ValueError("control must be ExecutionControl")
        if not callable(observer):
            raise ValueError("observer must be callable")
        self._worker_id = worker_id
        self._lease_token = lease_token
        self._operation_id = operation_id
        self._step_id = step_id
        self._write_uow_factory = write_uow_factory
        self._control = control
        self._observer = observer
        self._mutation_lock = threading.Lock()
        self._closed = False
        self._last_checkpoint_generation: CheckpointGeneration | None = None
        self._completion_acknowledgment: ExecutorAcknowledgment | None = None

    def refresh_control(self) -> None:
        """Reload the active records and propagate cancellation before execution."""

        with self._mutation_lock:
            self._ensure_open()
            try:
                with self._write_uow_factory() as unit_of_work:
                    self._load_live_records(unit_of_work)
            except (StaleWrite, LeaseExpired) as exc:
                self._lose_lease(exc)
                raise

    def heartbeat(self) -> StepRecord:
        """Extend the lease from a transaction-fresh Step and version it once."""

        with self._mutation_lock:
            self._ensure_open()
            try:
                with self._write_uow_factory() as unit_of_work:
                    operation, current_step = self._load_live_records(unit_of_work)
                    transaction_now = unit_of_work.operations.transaction_now
                    candidate = dataclasses.replace(
                        current_step,
                        updated_at=transaction_now,
                        lease_expires_at=transaction_now + LEASE_DURATION,
                        optimistic_version=current_step.optimistic_version + 1,
                    )
                    self._actions(unit_of_work).mutate_live_step(
                        candidate,
                        self._step_precondition(current_step),
                    )
            except (StaleWrite, LeaseExpired) as exc:
                self._lose_lease(exc)
                raise

            self._emit(
                WorkerEvent(
                    code=WorkerEventCode.HEARTBEAT_SUCCEEDED,
                    operation_id=operation.operation_id,
                    step_id=candidate.step_id,
                    worker_id=self._worker_id,
                    attempt=candidate.attempt_count,
                )
            )
            return candidate

    def publish_checkpoint(
        self,
        builder: Callable[[OperationRecord, StepRecord, datetime], StepRecord],
    ) -> CheckpointGeneration:
        """Build and commit a same-status RUNNING Step candidate."""

        with self._mutation_lock:
            self._ensure_open()
            try:
                with self._write_uow_factory() as unit_of_work:
                    operation, current_step = self._load_live_records(unit_of_work)
                    transaction_now = unit_of_work.operations.transaction_now
                    candidate = builder(operation, current_step, transaction_now)
                    self._validate_checkpoint_candidate(current_step, candidate, transaction_now)
                    self._actions(unit_of_work).mutate_live_step(
                        candidate,
                        self._step_precondition(current_step),
                    )
            except (StaleWrite, LeaseExpired) as exc:
                self._lose_lease(exc)
                raise

            generation = CheckpointGeneration(
                operation_id=operation.operation_id,
                step_id=candidate.step_id,
                optimistic_version=candidate.optimistic_version,
            )
            self._last_checkpoint_generation = generation
            return generation

    def publish_successor(
        self,
        builder: Callable[
            [OperationRecord, StepRecord, datetime], tuple[StepRecord, StepRecord]
        ],
    ) -> tuple[TransitionDisposition, TransitionDisposition]:
        """Commit a terminal Step and pending successor in one UoW."""

        with self._mutation_lock:
            self._ensure_open()
            try:
                with self._write_uow_factory() as unit_of_work:
                    operation, current_step = self._load_live_records(unit_of_work)
                    transaction_now = unit_of_work.operations.transaction_now
                    result = builder(operation, current_step, transaction_now)
                    if type(result) is not tuple or len(result) != 2:
                        raise ValueError("successor builder must return a Step/Step tuple")
                    terminal_step, successor = result
                    self._validate_terminal_step_candidate(
                        current_step,
                        terminal_step,
                        transaction_now,
                        allow_manual=False,
                    )
                    self._validate_successor_candidate(operation, terminal_step, successor)
                    dispositions = self._actions(unit_of_work).complete_with_successor(
                        terminal_step,
                        self._step_precondition(current_step),
                        successor,
                    )
            except (StaleWrite, LeaseExpired) as exc:
                self._lose_lease(exc)
                raise

            self._closed = True
            self._completion_acknowledgment = ExecutorAcknowledgment.PUBLISHED
            return dispositions

    def publish_operation(
        self,
        builder: Callable[
            [OperationRecord, StepRecord, datetime], tuple[StepRecord, OperationRecord]
        ],
    ) -> tuple[TransitionDisposition, TransitionDisposition]:
        """Commit a terminal/manual Step and terminal/manual Operation in one UoW."""

        with self._mutation_lock:
            self._ensure_open()
            try:
                with self._write_uow_factory() as unit_of_work:
                    current_operation, current_step = self._load_live_records(unit_of_work)
                    transaction_now = unit_of_work.operations.transaction_now
                    result = builder(current_operation, current_step, transaction_now)
                    if type(result) is not tuple or len(result) != 2:
                        raise ValueError("operation builder must return a Step/Operation tuple")
                    terminal_step, terminal_operation = result
                    self._validate_terminal_step_candidate(
                        current_step,
                        terminal_step,
                        transaction_now,
                        allow_manual=True,
                    )
                    self._validate_terminal_operation_candidate(
                        current_operation,
                        terminal_operation,
                    )
                    dispositions = self._actions(unit_of_work).complete_operation(
                        terminal_step,
                        self._step_precondition(current_step),
                        terminal_operation,
                        self._operation_precondition(current_operation),
                    )
            except (StaleWrite, LeaseExpired) as exc:
                self._lose_lease(exc)
                raise

            self._closed = True
            self._completion_acknowledgment = ExecutorAcknowledgment.PUBLISHED
            return dispositions

    def acknowledge_safe_handoff(
        self,
        generation: CheckpointGeneration,
    ) -> ExecutorAcknowledgment:
        """Close the session only after its exact checkpoint generation committed."""

        with self._mutation_lock:
            self._ensure_open()
            if type(generation) is not CheckpointGeneration:
                raise ValueError("generation must be CheckpointGeneration")
            if generation != self._last_checkpoint_generation:
                raise ValueError("safe handoff requires the latest committed checkpoint")
            self._closed = True
            self._completion_acknowledgment = ExecutorAcknowledgment.SAFE_HANDOFF
            self._emit(
                WorkerEvent(
                    code=WorkerEventCode.SAFE_HANDOFF,
                    operation_id=self._operation_id,
                    step_id=self._step_id,
                    worker_id=self._worker_id,
                )
            )
            return ExecutorAcknowledgment.SAFE_HANDOFF

    def publish_recovery_release(
        self,
        intent: RecoveryTransitionIntent,
        *,
        diagnostic: OperationDiagnostic,
    ) -> ExecutorAcknowledgment:
        """Release a live lease into a bounded recovery transition."""

        with self._mutation_lock:
            self._ensure_open()
            try:
                with self._write_uow_factory() as unit_of_work:
                    operation, current_step = self._load_live_records(unit_of_work)
                    transaction_now = unit_of_work.operations.transaction_now
                    step_target = intent.step_target
                    if step_target is None:
                        raise ValueError("recovery release requires a step target")
                    if intent.step_source is not StepStatus.RUNNING:
                        raise ValueError("recovery release only supports RUNNING step sources")

                    step_candidate = dataclasses.replace(
                        current_step,
                        status=step_target,
                        diagnostic=(
                            diagnostic
                            if step_target
                            in {
                                StepStatus.RETRY_WAIT,
                                StepStatus.FAILED,
                                StepStatus.MANUAL_RECOVERY_REQUIRED,
                            }
                            else None
                        ),
                        retry_not_before=intent.set_retry_not_before,
                        updated_at=transaction_now,
                        worker_id=None,
                        lease_token=None,
                        lease_expires_at=None,
                        optimistic_version=current_step.optimistic_version + 1,
                        completed_at=(
                            transaction_now if step_target.is_final_terminal() else None
                        ),
                    )
                    validate_step_transition(current_step, step_candidate)

                    if step_target is StepStatus.RETRY_WAIT:
                        self._validate_retry_wait_release_candidate(
                            current_step,
                            step_candidate,
                            transaction_now,
                        )
                        self._actions(unit_of_work).mutate_live_step(
                            step_candidate,
                            self._step_precondition(current_step),
                        )
                    elif step_target.is_final_terminal() or step_target.requires_manual_recovery():
                        operation_target = intent.operation_target
                        if operation_target is None:
                            raise ValueError("recovery release requires an operation target")
                        operation_candidate = dataclasses.replace(
                            operation,
                            status=operation_target,
                            diagnostic=(
                                diagnostic
                                if operation_target
                                in {
                                    OperationStatus.FAILED,
                                    OperationStatus.MANUAL_RECOVERY_REQUIRED,
                                }
                                else None
                            ),
                            updated_at=transaction_now,
                            optimistic_version=operation.optimistic_version + 1,
                            completed_at=(
                                transaction_now
                                if operation_target.is_final_terminal()
                                else None
                            ),
                        )
                        self._validate_terminal_step_candidate(
                            current_step,
                            step_candidate,
                            transaction_now,
                            allow_manual=step_target.requires_manual_recovery(),
                        )
                        self._validate_terminal_operation_candidate(
                            operation,
                            operation_candidate,
                        )
                        self._actions(unit_of_work).complete_operation(
                            step_candidate,
                            self._step_precondition(current_step),
                            operation_candidate,
                            self._operation_precondition(operation),
                            step_recovery_authorized=step_target.requires_manual_recovery(),
                            operation_recovery_authorized=operation_target.requires_manual_recovery(),
                        )
                    else:
                        raise ValueError("unsupported recovery release step target")
            except (StaleWrite, LeaseExpired) as exc:
                self._lose_lease(exc)
                raise

            self._closed = True
            self._completion_acknowledgment = ExecutorAcknowledgment.PUBLISHED
            return ExecutorAcknowledgment.PUBLISHED

    def completion_acknowledgment(self) -> ExecutorAcknowledgment | None:
        """Return only a publication fact committed by this session."""

        with self._mutation_lock:
            return self._completion_acknowledgment

    def _load_live_records(
        self,
        unit_of_work: OperationUnitOfWork,
    ) -> tuple[OperationRecord, StepRecord]:
        operation = unit_of_work.operations.get_operation(self._operation_id)
        step = unit_of_work.operations.get_step(self._step_id)
        transaction_now = unit_of_work.operations.transaction_now
        if operation.operation_id != self._operation_id:
            raise StaleWrite("lease session operation identity no longer matches")
        if step.step_id != self._step_id or step.operation_id != self._operation_id:
            raise StaleWrite("lease session step identity no longer matches")
        if operation.status is not OperationStatus.RUNNING or step.status is not StepStatus.RUNNING:
            raise StaleWrite("lease session no longer owns a RUNNING operation and step")
        if step.worker_id != self._worker_id or step.lease_token != self._lease_token:
            raise StaleWrite("lease session worker or token no longer matches")
        if step.lease_expires_at is None or step.lease_expires_at <= transaction_now:
            raise LeaseExpired("step lease is no longer live")
        if operation.cancel_requested or step.cancel_requested:
            self._control.request_cancel()
        return operation, step

    def _actions(self, unit_of_work: OperationUnitOfWork) -> OperationLifecycleActions:
        return OperationLifecycleActions(
            unit_of_work.operations,
            transaction_now=unit_of_work.operations.transaction_now,
        )

    def _step_precondition(self, current_step: StepRecord) -> WritePrecondition:
        return WritePrecondition(
            expected_optimistic_version=current_step.optimistic_version,
            worker_id=self._worker_id,
            lease_token=self._lease_token,
        )

    def _operation_precondition(self, current_operation: OperationRecord) -> WritePrecondition:
        return WritePrecondition(
            expected_optimistic_version=current_operation.optimistic_version,
            worker_id=None,
            lease_token=None,
        )

    def _validate_checkpoint_candidate(
        self,
        current_step: StepRecord,
        candidate: StepRecord,
        transaction_now: datetime,
    ) -> None:
        if type(candidate) is not StepRecord:
            raise ValueError("checkpoint builder must return StepRecord")
        if candidate.step_id != current_step.step_id or candidate.operation_id != self._operation_id:
            raise ValueError("checkpoint candidate identity does not match the lease session")
        if candidate.status is not StepStatus.RUNNING:
            raise ValueError("checkpoint candidate must remain RUNNING")
        if candidate.worker_id != self._worker_id or candidate.lease_token != self._lease_token:
            raise ValueError("checkpoint candidate lease identity does not match the session")
        if candidate.lease_expires_at is None or candidate.lease_expires_at <= transaction_now:
            raise ValueError("checkpoint candidate lease must remain live")
        if candidate.lease_expires_at != current_step.lease_expires_at:
            raise ValueError("checkpoint candidate must preserve the current lease expiry")
        if candidate.optimistic_version != current_step.optimistic_version + 1:
            raise ValueError("checkpoint candidate must increment optimistic_version once")

    def _validate_terminal_step_candidate(
        self,
        current_step: StepRecord,
        candidate: StepRecord,
        transaction_now: datetime,
        *,
        allow_manual: bool,
    ) -> None:
        if type(candidate) is not StepRecord:
            raise ValueError("publication builder must return StepRecord")
        if candidate.step_id != current_step.step_id or candidate.operation_id != self._operation_id:
            raise ValueError("terminal step identity does not match the lease session")
        if not candidate.status.is_final_terminal() and not (
            allow_manual and candidate.status.requires_manual_recovery()
        ):
            message = "published step must be terminal or manual recovery"
            if not allow_manual:
                message = "published step must be terminal"
            raise ValueError(message)
        if candidate.worker_id is not None or candidate.lease_token is not None:
            raise ValueError("published step must clear worker and lease token")
        if candidate.lease_expires_at is not None:
            raise ValueError("published step must clear lease expiry")
        if candidate.optimistic_version != current_step.optimistic_version + 1:
            raise ValueError("published step must increment optimistic_version once")
        if candidate.updated_at < transaction_now:
            raise ValueError("published step updated_at cannot precede transaction_now")

    def _validate_successor_candidate(
        self,
        operation: OperationRecord,
        terminal_step: StepRecord,
        successor: StepRecord,
    ) -> None:
        if type(successor) is not StepRecord:
            raise ValueError("successor builder must return StepRecord")
        if successor.operation_id != operation.operation_id:
            raise ValueError("successor must belong to the current operation")
        if successor.step_id == terminal_step.step_id:
            raise ValueError("successor must have a distinct step identity")
        if successor.status is not StepStatus.PENDING:
            raise ValueError("successor step must be PENDING")

    def _validate_retry_wait_release_candidate(
        self,
        current_step: StepRecord,
        candidate: StepRecord,
        transaction_now: datetime,
    ) -> None:
        if type(candidate) is not StepRecord:
            raise ValueError("recovery release builder must return StepRecord")
        if candidate.step_id != current_step.step_id or candidate.operation_id != self._operation_id:
            raise ValueError("recovery release step identity does not match the lease session")
        if candidate.status is not StepStatus.RETRY_WAIT:
            raise ValueError("recovery release candidate must target RETRY_WAIT")
        if candidate.worker_id is not None or candidate.lease_token is not None:
            raise ValueError("recovery release must clear worker and lease token")
        if candidate.lease_expires_at is not None:
            raise ValueError("recovery release must clear lease expiry")
        if candidate.optimistic_version != current_step.optimistic_version + 1:
            raise ValueError("recovery release must increment optimistic_version once")
        if candidate.updated_at < transaction_now:
            raise ValueError("recovery release updated_at cannot precede transaction_now")
        if candidate.retry_not_before is None:
            raise ValueError("recovery release requires retry_not_before")

    def _validate_terminal_operation_candidate(
        self,
        current_operation: OperationRecord,
        candidate: OperationRecord,
    ) -> None:
        if type(candidate) is not OperationRecord:
            raise ValueError("operation builder must return OperationRecord")
        if candidate.operation_id != current_operation.operation_id:
            raise ValueError("terminal operation identity does not match the lease session")
        if not (
            candidate.status.is_final_terminal() or candidate.status.requires_manual_recovery()
        ):
            raise ValueError("published operation must be terminal or manual recovery")
        if candidate.optimistic_version != current_operation.optimistic_version + 1:
            raise ValueError("published operation must increment optimistic_version once")

    def _ensure_open(self) -> None:
        if self._closed or self._control.lease_lost:
            raise StaleWrite("lease session is closed")

    def _lose_lease(self, error: StaleWrite | LeaseExpired) -> None:
        self._control.mark_lease_lost()
        self._closed = True
        try:
            self._emit(
                WorkerEvent(
                    code=WorkerEventCode.LEASE_LOST,
                    operation_id=self._operation_id,
                    step_id=self._step_id,
                    worker_id=self._worker_id,
                    error_category=(
                        "stale_write" if isinstance(error, StaleWrite) else "lease_expired"
                    ),
                )
            )
        except BaseException:
            # Preserve the typed fencing error that caused the lease loss.
            pass

    def _emit(self, event: WorkerEvent) -> None:
        self._observer(event)


__all__ = ["LeaseSession"]
