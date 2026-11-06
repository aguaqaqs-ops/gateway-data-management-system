"""Attach the worker's explicit compute budget to each claimed execution."""

from __future__ import annotations

from gateway_backend.capabilities.table_access import (
    KernelExecutionContext,
    OperationMemoryBudget,
    kernel_execution_scope,
)
from gateway_backend.operations.contracts import OperationRecord, StepRecord
from gateway_backend.operations.worker import (
    ClaimedExecutor,
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
