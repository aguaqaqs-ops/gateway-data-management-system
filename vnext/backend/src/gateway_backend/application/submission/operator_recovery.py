"""Internal operator recovery application use case."""

from __future__ import annotations

from gateway_backend.application.job_definitions import (
    JobDefinitionLookupError,
    JobDefinitionRegistry,
)
from gateway_backend.application.operation_reads import (
    OperationReaderPort,
    submit_attempt_id_from_operation,
)
from gateway_backend.application.submission.contracts import (
    ExecuteOperatorRecoveryCommand,
    ExecuteOperatorRecoveryResult,
)
from gateway_backend.application.submission.errors import (
    OperatorRecoveryCapabilityConflict,
    OperatorRecoveryIdentityConflict,
    OperatorRecoveryOperationVersionConflict,
    OperatorRecoveryStateConflict,
    OperatorRecoveryStepVersionConflict,
    OperatorRecoveryTargetNotFound,
    SubmitJobNotRegistered,
)
from gateway_backend.application.submission.job_payload import SUBMIT_JOB_KIND
from gateway_backend.application.submission.operator_recovery_mapping import (
    classify_operator_recovery_stale_write,
    classify_operator_recovery_value_error,
)
from gateway_backend.application.submission.ports import (
    OperatorRecoveryApplicationPort,
    SubmissionReaderPort,
)
from gateway_backend.application.submit_registry import build_submit_recovery_capability_mapping
from gateway_backend.operations.contracts import OperationRecord, StepRecord
from gateway_backend.operations.recovery import (
    OperatorRecoveryRequest,
    RecoveryCapabilityValue,
    authorize_operator_command,
)
from gateway_backend.operations.store import RecordNotFound, StaleWrite


class CapabilityLookup:
    def __init__(self, lookup: dict[tuple[str, str], RecoveryCapabilityValue]) -> None:
        self._lookup = dict(lookup)

    def __call__(self, job_kind: str, step_name: str) -> RecoveryCapabilityValue:
        try:
            return self._lookup[(job_kind, step_name)]
        except KeyError:
            raise OperatorRecoveryCapabilityConflict(
                "recovery capability is not registered for this step"
            ) from None


def _build_capability_lookup(registry: JobDefinitionRegistry) -> CapabilityLookup:
    try:
        mapping = build_submit_recovery_capability_mapping(registry)
    except JobDefinitionLookupError as exc:
        raise SubmitJobNotRegistered() from exc
    return CapabilityLookup(mapping)


def execute_operator_recovery(
    *,
    command: ExecuteOperatorRecoveryCommand,
    operation_reader: OperationReaderPort,
    submission_reader: SubmissionReaderPort,
    operator_recovery_port: OperatorRecoveryApplicationPort,
    job_registry: JobDefinitionRegistry,
) -> ExecuteOperatorRecoveryResult:
    capability_lookup = _build_capability_lookup(job_registry)

    if (
        command.body_operation_id != command.path_operation_id
        or command.body_step_id != command.path_step_id
    ):
        raise OperatorRecoveryIdentityConflict("recovery path and body identity do not match")

    operation = _load_operation(operation_reader, command.path_operation_id)
    step = _load_step(operation_reader, command.path_step_id)
    _assert_submit_recovery_target(operation, step, submission_reader)

    if command.expected_operation_optimistic_version != operation.optimistic_version:
        raise OperatorRecoveryOperationVersionConflict(
            "operation optimistic version is stale",
            expected=command.expected_operation_optimistic_version,
            actual=operation.optimistic_version,
        )
    if command.expected_step_optimistic_version != step.optimistic_version:
        raise OperatorRecoveryStepVersionConflict(
            "step optimistic version is stale",
            expected=command.expected_step_optimistic_version,
            actual=step.optimistic_version,
        )

    capability = capability_lookup(operation.job_kind, step.step_name)
    try:
        authorize_operator_command(
            command.command,
            capability=capability,
            operation_status=operation.status,
            step_status=step.status,
        )
    except ValueError as exc:
        raise _map_classified_recovery_error(classify_operator_recovery_value_error(exc)) from exc

    request = OperatorRecoveryRequest(
        command=command.command,
        operation_id=operation.operation_id,
        step_id=step.step_id,
        expected_operation_optimistic_version=command.expected_operation_optimistic_version,
        expected_step_optimistic_version=command.expected_step_optimistic_version,
        reason=command.reason,
    )

    try:
        disposition = operator_recovery_port.execute_recovery(request)
    except StaleWrite as exc:
        code, message = classify_operator_recovery_stale_write(exc)
        if code == "OPERATION_VERSION_CONFLICT":
            raise OperatorRecoveryOperationVersionConflict(message) from exc
        raise OperatorRecoveryStepVersionConflict(message) from exc
    except ValueError as exc:
        raise _map_classified_recovery_error(classify_operator_recovery_value_error(exc)) from exc

    return ExecuteOperatorRecoveryResult(
        operation_id=operation.operation_id,
        step_id=step.step_id,
        command=command.command,
        disposition=disposition,
    )


def _load_operation(operation_reader: OperationReaderPort, operation_id: str) -> OperationRecord:
    try:
        return operation_reader.get_operation(operation_id)
    except RecordNotFound as exc:
        raise OperatorRecoveryTargetNotFound() from exc


def _load_step(operation_reader: OperationReaderPort, step_id: str) -> StepRecord:
    try:
        return operation_reader.get_step(step_id)
    except RecordNotFound as exc:
        raise OperatorRecoveryTargetNotFound() from exc


def _map_classified_recovery_error(exc: Exception) -> Exception:
    if isinstance(
        exc,
        (
            OperatorRecoveryCapabilityConflict,
            OperatorRecoveryStateConflict,
            OperatorRecoveryIdentityConflict,
        ),
    ):
        return exc
    if isinstance(exc, ValueError):
        return OperatorRecoveryStateConflict("recovery source state does not allow this command")
    return exc


def _assert_submit_recovery_target(
    operation: OperationRecord,
    step: StepRecord,
    submission_reader: SubmissionReaderPort,
) -> None:
    if operation.job_kind != SUBMIT_JOB_KIND:
        raise OperatorRecoveryIdentityConflict("recovery target is not a submit operation")
    if step.operation_id != operation.operation_id:
        raise OperatorRecoveryIdentityConflict(
            "recovery step does not belong to the requested operation"
        )
    submit_attempt_id = submit_attempt_id_from_operation(operation)
    if submit_attempt_id is None:
        raise OperatorRecoveryTargetNotFound()
    attempt = submission_reader.get_submit_attempt(submit_attempt_id)
    if attempt is None:
        raise OperatorRecoveryTargetNotFound()
