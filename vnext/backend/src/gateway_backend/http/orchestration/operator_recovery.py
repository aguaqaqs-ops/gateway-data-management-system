"""Internal operator recovery HTTP orchestration."""

from __future__ import annotations

from typing import Literal

from gateway_backend.application.submission.errors import (
    AbortProofNotSatisfied,
    OperatorRecoveryCapabilityConflict,
    OperatorRecoveryIdentityConflict,
    OperatorRecoveryStateConflict,
)
from gateway_backend.application.submission.operator_recovery_mapping import (
    classify_operator_recovery_stale_write,
    classify_operator_recovery_value_error,
)
from gateway_backend.application.submission.job_payload import SUBMIT_JOB_KIND
from gateway_backend.http.dependencies import (
    OperatorRecoveryApplicationPort,
    OperationReaderPort,
    SubmissionReaderPort,
)
from gateway_backend.http.errors import ApiError
from gateway_backend.http.orchestration.operation_scope import submit_attempt_id_from_operation
from gateway_backend.http.schemas.operator_recovery import OperatorRecoveryRequestBody, OperatorRecoveryResponse
from gateway_backend.operations.contracts import OperationRecord, StepRecord
from gateway_backend.operations.recovery import (
    OperatorRecoveryCommand,
    OperatorRecoveryRequest,
    RecoveryCapabilityValue,
    authorize_operator_command,
)
from gateway_backend.operations.state import TransitionDisposition
from gateway_backend.operations.store import StaleWrite


def execute_operator_recovery(
    *,
    path_operation_id: str,
    path_step_id: str,
    body: OperatorRecoveryRequestBody,
    operation_reader: OperationReaderPort,
    submission_reader: SubmissionReaderPort,
    operator_recovery_port: OperatorRecoveryApplicationPort,
    capability_lookup: CapabilityLookup,
) -> OperatorRecoveryResponse:
    if body.operation_id != path_operation_id or body.step_id != path_step_id:
        raise ApiError(
            code="RECOVERY_IDENTITY_CONFLICT",
            message="recovery path and body identity do not match",
            status_code=409,
        )

    operation = _load_operation(operation_reader, path_operation_id)
    step = _load_step(operation_reader, path_step_id)
    _assert_submit_recovery_target(operation, step, submission_reader)

    if body.expected_operation_optimistic_version != operation.optimistic_version:
        raise ApiError(
            code="OPERATION_VERSION_CONFLICT",
            message="operation optimistic version is stale",
            status_code=409,
            details={
                "expected": body.expected_operation_optimistic_version,
                "actual": operation.optimistic_version,
            },
        )
    if body.expected_step_optimistic_version != step.optimistic_version:
        raise ApiError(
            code="STEP_VERSION_CONFLICT",
            message="step optimistic version is stale",
            status_code=409,
            details={
                "expected": body.expected_step_optimistic_version,
                "actual": step.optimistic_version,
            },
        )

    command = OperatorRecoveryCommand(body.command)
    capability = capability_lookup(operation.job_kind, step.step_name)
    try:
        authorize_operator_command(
            command,
            capability=capability,
            operation_status=operation.status,
            step_status=step.status,
        )
    except ValueError as exc:
        raise _map_classified_recovery_error(classify_operator_recovery_value_error(exc)) from exc

    request = OperatorRecoveryRequest(
        command=command,
        operation_id=operation.operation_id,
        step_id=step.step_id,
        expected_operation_optimistic_version=body.expected_operation_optimistic_version,
        expected_step_optimistic_version=body.expected_step_optimistic_version,
        reason=body.reason,
    )

    try:
        disposition = operator_recovery_port.execute_recovery(request)
    except AbortProofNotSatisfied as exc:
        raise ApiError(
            code="ABORT_PROOF_NOT_SATISFIED",
            message=str(exc),
            status_code=409,
        ) from exc
    except StaleWrite as exc:
        code, message = classify_operator_recovery_stale_write(exc)
        raise ApiError(code=code, message=message, status_code=409) from exc
    except ValueError as exc:
        raise _map_classified_recovery_error(classify_operator_recovery_value_error(exc)) from exc

    response_disposition: Literal["APPLY", "IDEMPOTENT"]
    if disposition is TransitionDisposition.IDEMPOTENT:
        response_disposition = "IDEMPOTENT"
    else:
        response_disposition = "APPLY"

    return OperatorRecoveryResponse(
        operation_id=operation.operation_id,
        step_id=step.step_id,
        command=body.command,
        disposition=response_disposition,
    )


class CapabilityLookup:
    def __init__(self, lookup: dict[tuple[str, str], RecoveryCapabilityValue]) -> None:
        self._lookup = dict(lookup)

    def __call__(self, job_kind: str, step_name: str) -> RecoveryCapabilityValue:
        try:
            return self._lookup[(job_kind, step_name)]
        except KeyError:
            raise ApiError(
                code="RECOVERY_CAPABILITY_CONFLICT",
                message="recovery capability is not registered for this step",
                status_code=409,
            )


def _load_operation(operation_reader: OperationReaderPort, operation_id: str) -> OperationRecord:
    try:
        return operation_reader.get_operation(operation_id)
    except ApiError as exc:
        if exc.code == "RESOURCE_NOT_FOUND":
            raise ApiError(
                code="RECOVERY_TARGET_NOT_FOUND",
                message="recovery target not found",
                status_code=404,
            ) from exc
        raise


def _load_step(operation_reader: OperationReaderPort, step_id: str) -> StepRecord:
    return operation_reader.get_step(step_id)


def _map_classified_recovery_error(exc: Exception) -> ApiError:
    if isinstance(exc, OperatorRecoveryCapabilityConflict):
        return ApiError(
            code=exc.stable_code,
            message="recovery command is not allowed for this step capability",
            status_code=409,
        )
    if isinstance(exc, OperatorRecoveryStateConflict):
        return ApiError(
            code=exc.stable_code,
            message="recovery source state does not allow this command",
            status_code=409,
        )
    if isinstance(exc, OperatorRecoveryIdentityConflict):
        return ApiError(
            code=exc.stable_code,
            message="recovery target identity is invalid",
            status_code=409,
        )
    if isinstance(exc, ValueError):
        return ApiError(
            code="RECOVERY_STATE_CONFLICT",
            message="recovery source state does not allow this command",
            status_code=409,
        )
    raise exc


def _assert_submit_recovery_target(
    operation: OperationRecord,
    step: StepRecord,
    submission_reader: SubmissionReaderPort,
) -> None:
    if operation.job_kind != SUBMIT_JOB_KIND:
        raise ApiError(
            code="RECOVERY_IDENTITY_CONFLICT",
            message="recovery target is not a submit operation",
            status_code=409,
        )
    if step.operation_id != operation.operation_id:
        raise ApiError(
            code="RECOVERY_IDENTITY_CONFLICT",
            message="recovery step does not belong to the requested operation",
            status_code=409,
        )
    submit_attempt_id = submit_attempt_id_from_operation(operation)
    if submit_attempt_id is None:
        raise ApiError(
            code="RECOVERY_TARGET_NOT_FOUND",
            message="recovery target not found",
            status_code=404,
        )
    attempt = submission_reader.get_submit_attempt(submit_attempt_id)
    if attempt is None:
        raise ApiError(
            code="RECOVERY_TARGET_NOT_FOUND",
            message="recovery target not found",
            status_code=404,
        )
