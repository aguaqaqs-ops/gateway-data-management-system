from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
import time

from fastapi import HTTPException, status

from ..operations import OperationRecord, OperationStatus


OperationGetter = Callable[[], OperationRecord | None]
ReadyPredicate = Callable[[OperationRecord], bool]
FailureMapper = Callable[[OperationRecord], HTTPException]
TimeoutMapper = Callable[[OperationRecord | None], HTTPException]


@dataclass(frozen=True, slots=True)
class FormalOperationWaitPolicy:
    timeout_seconds: float = 30.0
    poll_interval_seconds: float = 0.1

    def __post_init__(self) -> None:
        if self.timeout_seconds < 0:
            raise ValueError("timeout_seconds must be non-negative")
        if self.poll_interval_seconds <= 0:
            raise ValueError("poll_interval_seconds must be positive")


def wait_for_ready(
    operation_getter: OperationGetter,
    *,
    ready_predicate: ReadyPredicate | None = None,
    failure_mapper: FailureMapper | None = None,
    timeout_mapper: TimeoutMapper | None = None,
    wait_policy: FormalOperationWaitPolicy | None = None,
) -> OperationRecord:
    policy = wait_policy or FormalOperationWaitPolicy()
    is_ready = ready_predicate or _default_ready_predicate
    map_failure = failure_mapper or _default_failure_mapper
    map_timeout = timeout_mapper or _default_timeout_mapper
    deadline = time.monotonic() + policy.timeout_seconds
    last_operation: OperationRecord | None = None

    while True:
        operation = operation_getter()
        last_operation = operation
        if operation is not None:
            if is_ready(operation):
                return operation
            if operation.status in _TERMINAL_FAILURE_STATUSES:
                raise map_failure(operation)
        if time.monotonic() >= deadline:
            raise map_timeout(last_operation)
        remaining = max(0.0, deadline - time.monotonic())
        time.sleep(min(policy.poll_interval_seconds, remaining))


def _default_ready_predicate(operation: OperationRecord) -> bool:
    return operation.status is OperationStatus.READY


def _default_failure_mapper(operation: OperationRecord) -> HTTPException:
    status_code = (
        status.HTTP_409_CONFLICT
        if operation.status in _CONFLICT_FAILURE_STATUSES
        else status.HTTP_500_INTERNAL_SERVER_ERROR
    )
    return HTTPException(
        status_code=status_code,
        detail={
            "message": "Operation failed before the formal response was ready.",
            "operation_id": operation.operation_id,
            "operation_status": operation.status.value,
            "error_code": _operation_error_code(operation),
        },
    )


def _default_timeout_mapper(operation: OperationRecord | None) -> HTTPException:
    detail: dict[str, object] = {
        "message": "Operation did not become ready before the formal response timeout.",
        "error_code": "formal.operation_timeout",
    }
    if operation is not None:
        detail["operation_id"] = operation.operation_id
        detail["operation_status"] = operation.status.value
    return HTTPException(status_code=status.HTTP_409_CONFLICT, detail=detail)


def _operation_error_code(operation: OperationRecord) -> str | None:
    for step in operation.steps:
        if step.failure_summary:
            return step.failure_summary
        if step.result is not None and step.result.error is not None:
            return step.result.error.code
    return None


_CONFLICT_FAILURE_STATUSES = {
    OperationStatus.FAILED_RETRYABLE,
    OperationStatus.CANCELLED,
    OperationStatus.SUPERSEDED,
}

_TERMINAL_FAILURE_STATUSES = _CONFLICT_FAILURE_STATUSES | {
    OperationStatus.FAILED_FINAL,
}
