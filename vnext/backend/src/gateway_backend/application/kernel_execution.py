"""Attach the worker's explicit compute budget to each claimed execution."""

from __future__ import annotations

from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import replace

from gateway_backend.artifacts.store import ArtifactStorePort
from gateway_backend.artifacts.types import ArtifactRef
from gateway_backend.capabilities.source_package_staging import (
    RESOURCE_BUDGETS as STAGING_BUDGETS, SourcePackageInput, SourcePackageStagingResult,
    StagingDiagnosticCode, StagingInvocationContext, StagingStatus, stage_source_package,
)

from gateway_backend.capabilities.table_access import (
    KernelExecutionContext,
    OperationMemoryBudget,
    kernel_execution_scope, current_kernel_context, KernelMemoryLimit,
)
from gateway_backend.operations.contracts import OperationRecord, StepRecord
from gateway_backend.operations.store import LeaseExpired
from gateway_backend.operations.worker import (
    ClaimedExecutor, CooperativeExecutionStopped,
    ExecutionControl,
    ExecutorAcknowledgment,
    LeaseSession,
)


class ExecutionControlProbe:
    """A compute stop signal; original flags remain owned by ExecutionControl."""

    def __init__(self, control: ExecutionControl) -> None:
        self._control = control

    def is_set(self) -> bool:
        return self._control.cancel_requested or self._control.drain_requested or self._control.lease_lost


def bind_kernel_execution(
    executor: ClaimedExecutor, *, threads: int, memory_budget_bytes: int,
) -> ClaimedExecutor:
    def execute(
        operation: OperationRecord, step: StepRecord,
        control: ExecutionControl, lease_session: LeaseSession,
    ) -> ExecutorAcknowledgment:
        # No synthetic operation timeout is derived from renewable leases or drain.
        context = KernelExecutionContext(
            memory=OperationMemoryBudget(memory_budget_bytes),
            cancel_probe=ExecutionControlProbe(control), threads=threads,
            deadline_monotonic=None,
        )
        with kernel_execution_scope(context, new_operation=True):
            return executor(operation, step, control, lease_session)

    return execute


@contextmanager
def reserved_artifact_bytes(store: ArtifactStorePort, ref: ArtifactRef) -> Iterator[bytes]:
    context = current_kernel_context()
    if context is None:
        raise ValueError("artifact input read requires an operation kernel context")
    context.checkpoint()
    # The complete bytes read and bounded integrity/hash scratch are admitted
    # before locate grows the input. Binding the returned object avoids charging
    # the same source again when the parser borrows it.
    with context.memory.reserve(ref.size_bytes) as reservation:
        with context.memory.reserve(128 * 1024):
            payload = store.locate(ref)
        reservation.bind_backing(("python-bytes", id(payload)))
        try:
            context.checkpoint()
            yield payload
        finally:
            del payload


def stage_operation_source(source: SourcePackageInput, store: ArtifactStorePort) -> SourcePackageStagingResult:
    context = current_kernel_context()
    if context is None:
        raise ValueError("source staging requires an operation kernel context")
    context.checkpoint()
    available = context.memory.available_bytes
    # Existing staging retains collected members. Three expanded bytes cover
    # retained members, bytearray growth and its bytes conversion overlap.
    # Member/path/manifest objects use an independent bounded entry envelope;
    # gzip/tar read-ahead and hashing retain at most bounded chunk scratch.
    scratch = 512 * 1024 + len(source.payload or b"")
    entry_bytes = STAGING_BUDGETS.max_normalized_path_bytes * 32 + 4096
    header_metadata = min(STAGING_BUDGETS.max_archive_metadata_bytes, max(0, available - scratch) // 8)
    entries = min(STAGING_BUDGETS.max_source_package_entries, max(0, available - scratch - header_metadata) // (8 * entry_bytes))
    metadata = entries * entry_bytes
    expanded = min(STAGING_BUDGETS.max_source_package_expanded_bytes, max(0, available - scratch - metadata - header_metadata) // 3)
    if entries == 0 or expanded == 0:
        raise KernelMemoryLimit("source staging operation memory reservation exceeded")
    local = replace(STAGING_BUDGETS, max_source_package_entries=entries,
                    max_archive_metadata_bytes=header_metadata, max_source_package_expanded_bytes=expanded,
                    max_sql_document_bytes=min(STAGING_BUDGETS.max_sql_document_bytes, expanded),
                    max_xml_document_bytes=min(STAGING_BUDGETS.max_xml_document_bytes, expanded))
    peak = scratch + metadata + header_metadata + expanded * 3
    context.memory.record_stage_admission("source-staging", peak)
    with context.memory.reserve(peak):
        result = stage_source_package(replace(source, context=StagingInvocationContext(
            context.cancel_probe, context.deadline_monotonic)), store, budgets=local)
    context.checkpoint()
    retained_metadata = 8192 + sum(1024 + (len(entry.original_path or "") + len(entry.normalized_path)) * 32
                                   for entry in result.entries)
    context.memory.retain_metadata(result, retained_metadata)
    if result.status is StagingStatus.FAILED and any(
        d.code is StagingDiagnosticCode.RESOURCE_LIMIT_EXCEEDED for d in result.diagnostics
    ) and local != STAGING_BUDGETS:
        raise KernelMemoryLimit("source staging operation memory reservation exceeded")
    return result


def build_cooperative_kernel_stop(
    publish_cancelled: Callable[[LeaseSession], ExecutorAcknowledgment],
) -> Callable[[Exception, OperationRecord, StepRecord, ExecutionControl, LeaseSession], ExecutorAcknowledgment | None]:
    """Classify real control before R5's generic pure-compute failure mapping."""
    def stopped(
        error: Exception, operation: OperationRecord, step: StepRecord,
        control: ExecutionControl, session: LeaseSession,
    ) -> ExecutorAcknowledgment | None:
        if not isinstance(error, (InterruptedError, CooperativeExecutionStopped)):
            return None
        if control.lease_lost:
            raise LeaseExpired("compute observed lease loss")
        session.refresh_control()
        if control.cancel_requested:
            return publish_cancelled(session)
        if control.drain_requested:
            acknowledgment = session.release_for_drain()
            if acknowledgment is None:  # Fresh cancel wins the release transaction.
                return publish_cancelled(session)
            return acknowledgment
        return None  # A distinct caller stop is not fabricated into worker drain.
    return stopped


def publish_generic_stopped_compute_cancelled(session: LeaseSession) -> ExecutorAcknowledgment:
    """Base R3 cancellation for registered jobs with no application projection."""
    from datetime import datetime
    from gateway_backend.operations.contracts import OperationStatus, StepStatus
    def builder(operation: OperationRecord, step: StepRecord, now: datetime) -> tuple[StepRecord, OperationRecord]:
        terminal_step = replace(step, status=StepStatus.CANCELLED, worker_id=None, lease_token=None,
            lease_expires_at=None, completed_at=now, updated_at=now, optimistic_version=step.optimistic_version + 1)
        terminal_operation = replace(operation, status=OperationStatus.CANCELLED, completed_at=now,
            updated_at=now, optimistic_version=operation.optimistic_version + 1)
        return terminal_step, terminal_operation
    session.publish_operation(builder)
    return ExecutorAcknowledgment.PUBLISHED
