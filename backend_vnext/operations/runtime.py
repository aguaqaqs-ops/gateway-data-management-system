from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from collections.abc import Callable, Mapping, MutableMapping, Sequence
from dataclasses import dataclass, field, replace
from datetime import datetime, timedelta, timezone
from typing import Protocol, runtime_checkable
from uuid import uuid4

from ..core.digests import DigestRef
from ..core.diagnostics import DiagnosticRecord
from ..core.results import ErrorRecord, ResultRecord
from .models import (
    OperationCallerType,
    OperationKind,
    OperationParallelPolicy,
    OperationPlan,
    OperationRecord,
    OperationStatus,
    OperationStepPlan,
    OperationStepRecord,
    OperationStepStatus,
)
from .store import OperationStore, InMemoryOperationStore


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


@dataclass(frozen=True, slots=True)
class OperationStepOutcome:
    result: ResultRecord
    ready_closure_digest: DigestRef | str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.result, ResultRecord):
            raise TypeError("result must be a ResultRecord")
        if self.ready_closure_digest is not None and not isinstance(
            self.ready_closure_digest,
            (DigestRef, str),
        ):
            raise TypeError("ready_closure_digest must be a DigestRef, string or None")

    @classmethod
    def success(
        cls,
        value: object | None = None,
        *,
        diagnostics: Sequence[DiagnosticRecord] = (),
        ready_closure_digest: DigestRef | str | None = None,
        status: str = "SUCCEEDED",
    ) -> "OperationStepOutcome":
        return cls(
            result=ResultRecord(
                status=status,
                value=value,
                error=None,
                diagnostics=tuple(diagnostics),
            ),
            ready_closure_digest=ready_closure_digest,
        )

    @classmethod
    def failure(
        cls,
        *,
        code: str,
        message: str,
        retryable: bool = False,
        value: object | None = None,
        diagnostics: Sequence[DiagnosticRecord] = (),
        ready_closure_digest: DigestRef | str | None = None,
        status: str | None = None,
    ) -> "OperationStepOutcome":
        failure_status = status or (
            "FAILED_RETRYABLE" if retryable else "FAILED_FINAL"
        )
        return cls(
            result=ResultRecord(
                status=failure_status,
                value=value,
                error=ErrorRecord(
                    code=code,
                    message=message,
                    retryable=retryable,
                ),
                diagnostics=tuple(diagnostics),
            ),
            ready_closure_digest=ready_closure_digest,
        )


def _normalize_result_for_storage(result: ResultRecord) -> ResultRecord:
    return replace(result, value=_payload_value(result.value))


@dataclass(frozen=True, slots=True)
class OperationStepContext:
    operation: OperationRecord
    step: OperationStepRecord
    prior_step_outputs: Mapping[str, object] = field(default_factory=dict)
    worker_id: str | None = None
    now: datetime = field(default_factory=_utcnow)

    def __post_init__(self) -> None:
        if not isinstance(self.operation, OperationRecord):
            raise TypeError("operation must be an OperationRecord")
        if not isinstance(self.step, OperationStepRecord):
            raise TypeError("step must be an OperationStepRecord")
        if not isinstance(self.prior_step_outputs, Mapping):
            raise TypeError("prior_step_outputs must be a mapping")
        if self.worker_id is not None and (not isinstance(self.worker_id, str) or not self.worker_id):
            raise ValueError("worker_id must be a non-empty string or None")
        if not isinstance(self.now, datetime) or self.now.tzinfo is None:
            raise ValueError("now must be timezone-aware")


OperationStepHandler = Callable[[OperationStepContext], OperationStepOutcome]


@dataclass(frozen=True, slots=True)
class OperationRunResult:
    operation: OperationRecord
    step_results: tuple[ResultRecord, ...] = field(default_factory=tuple)
    outputs: Mapping[str, object] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not isinstance(self.operation, OperationRecord):
            raise TypeError("operation must be an OperationRecord")
        if not isinstance(self.step_results, tuple):
            object.__setattr__(self, "step_results", tuple(self.step_results))
        for result in self.step_results:
            if not isinstance(result, ResultRecord):
                raise TypeError("step_results must contain ResultRecord values")
        if not isinstance(self.outputs, Mapping):
            raise TypeError("outputs must be a mapping")


@dataclass(frozen=True, slots=True)
class OperationRuntime:
    store: OperationStore = field(default_factory=InMemoryOperationStore)
    claim_lease_seconds: int = 300
    max_save_attempts: int = 3

    def __post_init__(self) -> None:
        if not hasattr(self.store, "create") or not hasattr(self.store, "get") or not hasattr(self.store, "save"):
            raise TypeError("store must implement the OperationStore protocol")
        if (
            not isinstance(self.claim_lease_seconds, int)
            or isinstance(self.claim_lease_seconds, bool)
            or self.claim_lease_seconds <= 0
        ):
            raise ValueError("claim_lease_seconds must be a positive integer")
        if (
            not isinstance(self.max_save_attempts, int)
            or isinstance(self.max_save_attempts, bool)
            or self.max_save_attempts <= 0
        ):
            raise ValueError("max_save_attempts must be a positive integer")

    def create_operation(
        self,
        plan: OperationPlan,
        *,
        operation_id: str | None = None,
        now: datetime | None = None,
    ) -> OperationRecord:
        if not isinstance(plan, OperationPlan):
            raise TypeError("plan must be an OperationPlan")
        current_time = _coerce_now(now)
        operation_id = operation_id or f"op_{uuid4().hex}"
        record = OperationRecord(
            operation_id=operation_id,
            operation_kind=plan.operation_kind,
            caller_type=plan.caller_type,
            status=OperationStatus.QUEUED,
            steps=tuple(
                OperationStepRecord(
                    step_sequence=index,
                    step_name=step.step_name,
                    status=OperationStepStatus.PENDING,
                    retryable=step.retryable,
                    allow_parallel=step.allow_parallel,
                )
                for index, step in enumerate(plan.steps)
            ),
            parallel_policy=plan.parallel_policy,
            request_payload=plan.request_payload,
            generation=plan.generation,
            retry_of=plan.retry_of,
            superseded_by=plan.superseded_by,
            created_at=current_time,
            updated_at=current_time,
            diagnostics=plan.diagnostics,
        )
        return self.store.create(record)

    def get_operation(self, operation_id: str) -> OperationRecord | None:
        return self.store.get(operation_id)

    def run_operation(
        self,
        operation_id: str,
        handlers: Mapping[str, OperationStepHandler],
        *,
        worker_id: str,
        now: datetime | None = None,
    ) -> OperationRunResult:
        current_time = _coerce_now(now)
        operation = self._load(operation_id)
        if operation.status in {OperationStatus.READY, OperationStatus.CANCELLED, OperationStatus.SUPERSEDED}:
            raise ValueError(f"operation {operation_id} is already terminal")
        operation = self._claim_operation(operation, worker_id=worker_id, now=current_time)
        step_results: list[ResultRecord] = []
        outputs: dict[str, object] = {}
        step_index = 0
        while step_index < len(operation.steps):
            step = operation.steps[step_index]
            if (
                operation.parallel_policy is OperationParallelPolicy.FIXED_DUAL_SLOT
                and step.allow_parallel
                and step_index + 1 < len(operation.steps)
                and operation.steps[step_index + 1].allow_parallel
            ):
                operation, batch_results, batch_outputs, batch_failure = self._run_fixed_dual_slot_step_batch(
                    operation=operation,
                    first_step_index=step_index,
                    second_step_index=step_index + 1,
                    handlers=handlers,
                    worker_id=worker_id,
                    prior_step_outputs=outputs,
                    now=current_time,
                )
                step_results.extend(batch_results)
                outputs.update(batch_outputs)
                if batch_failure is not None:
                    operation = self._finalize_failed_operation(operation, batch_failure, now=current_time)
                    return OperationRunResult(operation=operation, step_results=tuple(step_results), outputs=outputs)
                step_index += 2
                continue
            handler = handlers.get(step.step_name)
            if handler is None:
                failure = OperationStepOutcome.failure(
                    code="operation.step.missing-handler",
                    message=f"missing step handler for {step.step_name}",
                    retryable=False,
                )
                operation = self._finish_step(operation, step.step_sequence, worker_id=worker_id, outcome=failure, now=current_time)
                operation = self._finalize_failed_operation(operation, failure.result, now=current_time)
                return OperationRunResult(operation=operation, step_results=tuple(step_results + [failure.result]), outputs=outputs)
            operation = self._claim_step(operation, step.step_sequence, worker_id=worker_id, now=current_time)
            context = OperationStepContext(
                operation=operation,
                step=operation.steps[step.step_sequence],
                prior_step_outputs=dict(outputs),
                worker_id=worker_id,
                now=current_time,
            )
            try:
                outcome = handler(context)
            except Exception as exc:  # pragma: no cover - defensive guard
                outcome = OperationStepOutcome.failure(
                    code="operation.step.exception",
                    message=str(exc),
                    retryable=False,
                )
            operation = self._finish_step(operation, step.step_sequence, worker_id=worker_id, outcome=outcome, now=current_time)
            step_results.append(outcome.result)
            outputs[step.step_name] = outcome.result.value
            if outcome.result.status in {
                OperationStepStatus.FAILED_RETRYABLE.value,
                OperationStepStatus.FAILED_FINAL.value,
                OperationStepStatus.CANCELLED.value,
            }:
                operation = self._finalize_failed_operation(operation, outcome.result, now=current_time)
                return OperationRunResult(operation=operation, step_results=tuple(step_results), outputs=outputs)
            step_index += 1
        operation = self._finalize_ready_operation(operation, outputs=outputs, now=current_time)
        return OperationRunResult(operation=operation, step_results=tuple(step_results), outputs=outputs)

    def retry_operation(
        self,
        operation_id: str,
        *,
        worker_id: str | None = None,
        now: datetime | None = None,
    ) -> OperationRecord:
        current_time = _coerce_now(now)
        operation = self._load(operation_id)
        if operation.status != OperationStatus.FAILED_RETRYABLE:
            raise ValueError("only retryable failures can be retried")
        retryable_steps = [
            replace(step, status=OperationStepStatus.PENDING, worker_id=None, claim_token=None, lease_expires_at=None, started_at=None, finished_at=None, result=None, failure_summary=None, ready_closure_digest=None)
            for step in operation.steps
            if step.status in {OperationStepStatus.FAILED_RETRYABLE, OperationStepStatus.CANCELLED}
            or step.status == OperationStepStatus.PENDING
        ]
        if not retryable_steps:
            raise ValueError("no retryable steps available")
        restored_steps: list[OperationStepRecord] = []
        step_index = 0
        for original_step in operation.steps:
            if original_step.status == OperationStepStatus.SUCCEEDED:
                restored_steps.append(original_step)
                continue
            restored_steps.append(retryable_steps[step_index])
            step_index += 1
        updated = replace(
            operation,
            status=OperationStatus.QUEUED,
            worker_id=worker_id,
            claim_token=None,
            lease_expires_at=None,
            failure_summary=None,
            result=None,
            updated_at=current_time,
            version=operation.version + 1,
            steps=tuple(restored_steps),
        )
        return self._save(operation, updated)

    def cancel_operation(
        self,
        operation_id: str,
        *,
        reason: str | None = None,
        now: datetime | None = None,
    ) -> OperationRecord:
        current_time = _coerce_now(now)
        operation = self._load(operation_id)
        updated = replace(
            operation,
            status=OperationStatus.CANCELLED,
            failure_summary=reason or operation.failure_summary,
            updated_at=current_time,
            version=operation.version + 1,
        )
        updated_steps = []
        for step in updated.steps:
            if step.status in {OperationStepStatus.PENDING, OperationStepStatus.RUNNING}:
                updated_steps.append(
                    replace(
                        step,
                        status=OperationStepStatus.CANCELLED,
                        finished_at=current_time,
                        failure_summary=reason or step.failure_summary,
                    )
                )
            else:
                updated_steps.append(step)
        updated = replace(updated, steps=tuple(updated_steps))
        return self._save(operation, updated)

    def supersede_operation(
        self,
        operation_id: str,
        *,
        superseded_by: str,
        now: datetime | None = None,
    ) -> OperationRecord:
        current_time = _coerce_now(now)
        operation = self._load(operation_id)
        updated = replace(
            operation,
            status=OperationStatus.SUPERSEDED,
            superseded_by=superseded_by,
            updated_at=current_time,
            version=operation.version + 1,
        )
        return self._save(operation, updated)

    def _claim_operation(
        self,
        operation: OperationRecord,
        *,
        worker_id: str,
        now: datetime,
    ) -> OperationRecord:
        lease_expires_at = now + timedelta(seconds=self.claim_lease_seconds)
        updated = replace(
            operation,
            status=OperationStatus.RUNNING,
            worker_id=worker_id,
            claim_token=f"claim_{uuid4().hex}",
            lease_expires_at=lease_expires_at,
            updated_at=now,
            version=operation.version + 1,
        )
        return self._save(operation, updated)

    def _claim_step(
        self,
        operation: OperationRecord,
        step_sequence: int,
        *,
        worker_id: str,
        now: datetime,
    ) -> OperationRecord:
        step = operation.steps[step_sequence]
        lease_expires_at = now + timedelta(seconds=self.claim_lease_seconds)
        updated_steps = list(operation.steps)
        updated_steps[step_sequence] = replace(
            step,
            status=OperationStepStatus.RUNNING,
            worker_id=worker_id,
            claim_token=operation.claim_token,
            lease_expires_at=lease_expires_at,
            started_at=now if step.started_at is None else step.started_at,
        )
        updated = replace(
            operation,
            steps=tuple(updated_steps),
            updated_at=now,
            version=operation.version + 1,
        )
        return self._save(operation, updated)

    def _run_fixed_dual_slot_step_batch(
        self,
        *,
        operation: OperationRecord,
        first_step_index: int,
        second_step_index: int,
        handlers: Mapping[str, OperationStepHandler],
        worker_id: str,
        prior_step_outputs: Mapping[str, object],
        now: datetime,
    ) -> tuple[OperationRecord, tuple[ResultRecord, ResultRecord], dict[str, object], ResultRecord | None]:
        if second_step_index != first_step_index + 1:
            raise ValueError("fixed dual slot batch requires consecutive step indexes")

        first_step = operation.steps[first_step_index]
        second_step = operation.steps[second_step_index]
        first_handler = handlers.get(first_step.step_name)
        second_handler = handlers.get(second_step.step_name)
        if first_handler is None or second_handler is None:
            missing_step_name = (
                first_step.step_name if first_handler is None else second_step.step_name
            )
            raise ValueError(f"missing step handler for {missing_step_name}")

        claimed_operation = self._claim_step(
            operation,
            first_step_index,
            worker_id=worker_id,
            now=now,
        )
        claimed_operation = self._claim_step(
            claimed_operation,
            second_step_index,
            worker_id=worker_id,
            now=now,
        )

        step_context_outputs = dict(prior_step_outputs)
        outcomes: dict[int, OperationStepOutcome] = {}

        def _run_step(handler: OperationStepHandler, context: OperationStepContext) -> OperationStepOutcome:
            try:
                return handler(context)
            except Exception as exc:  # pragma: no cover - defensive guard
                return OperationStepOutcome.failure(
                    code="operation.step.exception",
                    message=str(exc),
                    retryable=False,
                )

        with ThreadPoolExecutor(max_workers=2) as executor:
            future_to_index = {
                executor.submit(
                    _run_step,
                    first_handler,
                    OperationStepContext(
                        operation=claimed_operation,
                        step=claimed_operation.steps[first_step_index],
                        prior_step_outputs=step_context_outputs,
                        worker_id=f"{worker_id}:slot-{first_step_index}",
                        now=now,
                    ),
                ): first_step_index,
                executor.submit(
                    _run_step,
                    second_handler,
                    OperationStepContext(
                        operation=claimed_operation,
                        step=claimed_operation.steps[second_step_index],
                        prior_step_outputs=step_context_outputs,
                        worker_id=f"{worker_id}:slot-{second_step_index}",
                        now=now,
                    ),
                ): second_step_index,
            }
            for future in as_completed(future_to_index):
                step_index = future_to_index[future]
                outcomes[step_index] = future.result()

        batch_operation = claimed_operation
        batch_results: list[ResultRecord] = []
        batch_outputs: dict[str, object] = {}
        failure_result: ResultRecord | None = None
        for step_index in (first_step_index, second_step_index):
            outcome = outcomes[step_index]
            batch_operation = self._finish_step(
                batch_operation,
                step_index,
                worker_id=f"{worker_id}:slot-{step_index}",
                outcome=outcome,
                now=now,
            )
            batch_results.append(outcome.result)
            batch_outputs[batch_operation.steps[step_index].step_name] = outcome.result.value
            if (
                failure_result is None
                and outcome.result.status in {
                    OperationStepStatus.FAILED_RETRYABLE.value,
                    OperationStepStatus.FAILED_FINAL.value,
                    OperationStepStatus.CANCELLED.value,
                }
            ):
                failure_result = outcome.result
        return batch_operation, (batch_results[0], batch_results[1]), batch_outputs, failure_result

    def _finish_step(
        self,
        operation: OperationRecord,
        step_sequence: int,
        *,
        worker_id: str,
        outcome: OperationStepOutcome,
        now: datetime,
    ) -> OperationRecord:
        step = operation.steps[step_sequence]
        result_status = OperationStepStatus(outcome.result.status)
        updated_steps = list(operation.steps)
        updated_steps[step_sequence] = replace(
            step,
            status=result_status,
            worker_id=worker_id,
            claim_token=operation.claim_token,
            lease_expires_at=None,
            started_at=step.started_at or now,
            finished_at=now,
            result=_normalize_result_for_storage(outcome.result),
            failure_summary=(
                None
                if outcome.result.error is None
                else outcome.result.error.message
            ),
            ready_closure_digest=outcome.ready_closure_digest,
            diagnostics=outcome.result.diagnostics,
        )
        updated = replace(
            operation,
            steps=tuple(updated_steps),
            updated_at=now,
            version=operation.version + 1,
            ready_closure_digest=(
                outcome.ready_closure_digest
                if outcome.ready_closure_digest is not None
                else operation.ready_closure_digest
            ),
        )
        return self._save(operation, updated)

    def _finalize_failed_operation(
        self,
        operation: OperationRecord,
        result: ResultRecord,
        *,
        now: datetime,
    ) -> OperationRecord:
        status = (
            OperationStatus.FAILED_RETRYABLE
            if result.status == OperationStepStatus.FAILED_RETRYABLE.value
            else OperationStatus.FAILED_FINAL
        )
        if result.status == OperationStepStatus.CANCELLED.value:
            status = OperationStatus.CANCELLED
        updated = replace(
            operation,
            status=status,
            result=_normalize_result_for_storage(result),
            failure_summary=result.error.message if result.error is not None else operation.failure_summary,
            updated_at=now,
            version=operation.version + 1,
        )
        return self._save(operation, updated)

    def _finalize_ready_operation(
        self,
        operation: OperationRecord,
        *,
        outputs: Mapping[str, object],
        now: datetime,
    ) -> OperationRecord:
        if operation.ready_closure_digest is None:
            raise ValueError("operation ready_closure_digest is required before READY")
        summary_payload = {
            "operation_id": operation.operation_id,
            "operation_kind": operation.operation_kind.value,
            "caller_type": operation.caller_type.value,
            "parallel_policy": operation.parallel_policy.value,
            "outputs": {step_name: _payload_value(value) for step_name, value in outputs.items()},
            "ready_closure_digest": operation.ready_closure_digest.to_payload(),
        }
        result = ResultRecord(
            status=OperationStatus.READY.value,
            value=summary_payload,
            error=None,
            diagnostics=operation.diagnostics,
        )
        updated = replace(
            operation,
            status=OperationStatus.READY,
            result=_normalize_result_for_storage(result),
            updated_at=now,
            version=operation.version + 1,
        )
        return self._save(operation, updated)

    def _load(self, operation_id: str) -> OperationRecord:
        operation = self.store.get(operation_id)
        if operation is None:
            raise KeyError(operation_id)
        return operation

    def _save(self, current: OperationRecord, updated: OperationRecord) -> OperationRecord:
        attempts = 0
        last_error: Exception | None = None
        while attempts < self.max_save_attempts:
            try:
                return self.store.save(updated, expected_version=current.version)
            except ValueError as exc:
                last_error = exc
                current = self._load(current.operation_id)
                updated = replace(updated, version=current.version + 1)
                attempts += 1
        if last_error is not None:
            raise last_error
        raise ValueError("operation save failed")


def _payload_value(value: object) -> object:
    if value is None:
        return None
    to_payload = getattr(value, "to_payload", None)
    if callable(to_payload):
        return _payload_value(to_payload())
    if isinstance(value, Mapping):
        return {str(key): _payload_value(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [_payload_value(item) for item in value]
    if isinstance(value, list):
        return [_payload_value(item) for item in value]
    if isinstance(value, datetime):
        if value.tzinfo is None:
            raise ValueError("datetime values must be timezone-aware")
        return value.astimezone(timezone.utc).isoformat()
    return value


def _coerce_now(now: datetime | None) -> datetime:
    if now is None:
        return _utcnow()
    if not isinstance(now, datetime):
        raise TypeError("now must be a datetime or None")
    if now.tzinfo is None:
        raise ValueError("now must be timezone-aware")
    return now
