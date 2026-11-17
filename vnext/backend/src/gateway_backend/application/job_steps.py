"""Shared operation step checkpoint and lifecycle helpers for job handlers."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from contextlib import AbstractContextManager
import dataclasses
from datetime import datetime
from typing import Protocol, TypeVar

from gateway_backend.application.checkpoints import (
    CheckpointPublicationError,
    make_checkpoint_step_builder,
)
from gateway_backend.application.payloads import PayloadDecodeError
from gateway_backend.artifacts.types import ArtifactRef
from gateway_backend.capabilities.table_access import current_kernel_context
from gateway_backend.operations.contracts import (
    OPERATION_RUNTIME_CONTRACT_VERSION,
    OperationDiagnostic,
    OperationRecord,
    OperationStatus,
    StepRecord,
    StepStatus,
)
from gateway_backend.operations.worker import (
    ClaimedExecutor,
    ExecutionControl,
    ExecutorAcknowledgment,
    LeaseSession,
)

_TransactionT = TypeVar("_TransactionT")


class ArtifactProtectionTransaction(Protocol):
    def set_artifact_protection(
        self,
        refs: tuple[ArtifactRef, ...],
        *,
        owner_kind: str,
        owner_id: str,
        intent: str,
    ) -> bool: ...


class StepLookupOperations(Protocol):
    def get_step(self, step_id: str) -> StepRecord: ...


class StepLookupTransaction(Protocol):
    @property
    def operations(self) -> StepLookupOperations: ...


def pinned_checkpoint_builder(
    *,
    checkpoint_ref: ArtifactRef,
    extra_refs: tuple[ArtifactRef, ...],
    owner_kind: str,
    intent: str,
    active_transaction: Callable[[], ArtifactProtectionTransaction | None],
    transaction_missing: Callable[[], Exception],
    deduplicate_refs: bool = True,
) -> Callable[[OperationRecord, StepRecord, datetime], StepRecord]:
    inner = make_checkpoint_step_builder(checkpoint_ref=checkpoint_ref)

    def builder(
        operation: OperationRecord,
        step: StepRecord,
        transaction_now: datetime,
    ) -> StepRecord:
        candidate = inner(operation, step, transaction_now)
        transaction = active_transaction()
        if transaction is None:
            raise transaction_missing()
        refs = (checkpoint_ref, *extra_refs)
        if deduplicate_refs:
            refs = unique_artifact_refs(refs)
        transaction.set_artifact_protection(
            refs,
            owner_kind=owner_kind,
            owner_id=step.step_id,
            intent=intent,
        )
        return candidate

    return builder


def unique_artifact_refs(refs: tuple[ArtifactRef, ...]) -> tuple[ArtifactRef, ...]:
    seen: set[str] = set()
    unique: list[ArtifactRef] = []
    for ref in refs:
        if ref.artifact_id in seen:
            continue
        seen.add(ref.artifact_id)
        unique.append(ref)
    return tuple(unique)


def successor_step_id(
    operation_id: str,
    step_name: str,
    suffix_by_step: Mapping[str, str],
) -> str:
    try:
        suffix = suffix_by_step[step_name]
    except KeyError:
        raise ValueError(f"unknown step_name: {step_name}") from None
    return f"{operation_id}-step-{suffix}"


def checkpoint_generation(step: StepRecord) -> int:
    attempt_count = step.attempt_count
    if type(attempt_count) is not int or isinstance(attempt_count, bool) or attempt_count < 1:
        raise ValueError("attempt_count must be a positive int for checkpoint generation")
    return attempt_count


def load_step(
    control_transaction_factory: Callable[[], AbstractContextManager[StepLookupTransaction]],
    *,
    operation_id: str,
    step_id: str,
    mismatch_error: Callable[[], Exception],
) -> StepRecord:
    with control_transaction_factory() as unit_of_work:
        step = unit_of_work.operations.get_step(step_id)
    if step.operation_id != operation_id:
        raise mismatch_error()
    return step


def terminal_step(
    step: StepRecord,
    transaction_now: datetime,
    *,
    status: StepStatus,
    diagnostic: OperationDiagnostic | None = None,
) -> StepRecord:
    return dataclasses.replace(
        step,
        status=status,
        diagnostic=diagnostic,
        worker_id=None,
        lease_token=None,
        lease_expires_at=None,
        completed_at=transaction_now,
        updated_at=transaction_now,
        optimistic_version=step.optimistic_version + 1,
    )


def make_successor_builder(
    *,
    operation_id: str,
    successor_step_name: str,
    successor_step_id: str,
) -> Callable[[OperationRecord, StepRecord, datetime], tuple[StepRecord, StepRecord]]:
    def builder(
        operation: OperationRecord,
        current_step: StepRecord,
        transaction_now: datetime,
    ) -> tuple[StepRecord, StepRecord]:
        completed_step = terminal_step(current_step, transaction_now, status=StepStatus.SUCCEEDED)
        successor = StepRecord(
            contract_version=OPERATION_RUNTIME_CONTRACT_VERSION,
            step_id=successor_step_id,
            operation_id=operation_id,
            step_name=successor_step_name,
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
            created_at=transaction_now,
            updated_at=transaction_now,
            started_at=None,
            completed_at=None,
            optimistic_version=0,
        )
        return completed_step, successor

    return builder


def make_cancelled_terminal_builder(
    *,
    active_transaction: Callable[[], _TransactionT | None],
    transaction_missing: Callable[[], Exception],
    release_protection: Callable[[_TransactionT, OperationRecord], None] | None = None,
) -> Callable[[OperationRecord, StepRecord, datetime], tuple[StepRecord, OperationRecord]]:
    def builder(
        operation: OperationRecord,
        step: StepRecord,
        transaction_now: datetime,
    ) -> tuple[StepRecord, OperationRecord]:
        transaction = active_transaction()
        if transaction is None:
            raise transaction_missing()
        if operation.ready_closure_ref is not None:
            raise CheckpointPublicationError(
                "ready_closure_ref is already set",
                code="CLOSURE_ALREADY_SET",
            )
        if release_protection is not None:
            release_protection(transaction, operation)
        cancelled_step = dataclasses.replace(
            step,
            status=StepStatus.CANCELLED,
            worker_id=None,
            lease_token=None,
            lease_expires_at=None,
            completed_at=transaction_now,
            updated_at=transaction_now,
            optimistic_version=step.optimistic_version + 1,
        )
        terminal_operation = dataclasses.replace(
            operation,
            status=OperationStatus.CANCELLED,
            completed_at=transaction_now,
            updated_at=transaction_now,
            optimistic_version=operation.optimistic_version + 1,
        )
        return cancelled_step, terminal_operation

    return builder


def publish_stopped_compute_cancelled(
    lease_session: LeaseSession,
    cancelled_builder: Callable[
        [],
        Callable[[OperationRecord, StepRecord, datetime], tuple[StepRecord, OperationRecord]],
    ],
) -> ExecutorAcknowledgment:
    lease_session.publish_operation(cancelled_builder())
    return ExecutorAcknowledgment.PUBLISHED


def require_non_empty_str(payload_object: dict[str, object], key: str) -> str:
    value = payload_object.get(key)
    if type(value) is not str or not value:
        raise PayloadDecodeError(f"{key} must be a non-empty string", code="PAYLOAD_SHAPE_INVALID")
    return value


def with_resource_failure_terminal(
    handler: ClaimedExecutor,
    *,
    on_memory_error: Callable[
        [OperationRecord, StepRecord, ExecutionControl, LeaseSession, MemoryError],
        None,
    ],
) -> ClaimedExecutor:
    def execute(
        operation: OperationRecord,
        step: StepRecord,
        control: ExecutionControl,
        lease_session: LeaseSession,
    ) -> ExecutorAcknowledgment:
        try:
            return handler(operation, step, control, lease_session)
        except MemoryError as error:
            context = current_kernel_context()
            if context is not None:
                context.checkpoint()  # Preserve real cancel/drain/lease/deadline first.
            on_memory_error(operation, step, control, lease_session, error)
            return ExecutorAcknowledgment.PUBLISHED

    return execute


__all__ = [
    "ArtifactProtectionTransaction",
    "StepLookupOperations",
    "StepLookupTransaction",
    "checkpoint_generation",
    "load_step",
    "make_cancelled_terminal_builder",
    "make_successor_builder",
    "pinned_checkpoint_builder",
    "publish_stopped_compute_cancelled",
    "require_non_empty_str",
    "successor_step_id",
    "terminal_step",
    "unique_artifact_refs",
    "with_resource_failure_terminal",
]
