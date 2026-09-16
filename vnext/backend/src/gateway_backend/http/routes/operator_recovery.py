"""Internal operator recovery routes."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends

from gateway_backend.application.job_definitions import JobDefinitionLookupError, JobDefinitionRegistry
from gateway_backend.http.errors import ApiError
from gateway_backend.application.recovery import RecoveryCapability
from gateway_backend.application.submission.contracts import SUBMIT_JOB_CONTRACT_VERSION
from gateway_backend.application.submission.job_payload import (
    SUBMIT_JOB_KIND,
    SUBMIT_STEP_AWAIT,
    SUBMIT_STEP_PREPARE,
    SUBMIT_STEP_SUBMIT,
)
from gateway_backend.http.auth import require_internal_bearer
from gateway_backend.http.dependencies import WorkspaceHttpDependencies, get_workspace_http
from gateway_backend.http.orchestration.operator_recovery import CapabilityLookup, execute_operator_recovery
from gateway_backend.http.schemas.operator_recovery import OperatorRecoveryRequestBody, OperatorRecoveryResponse
from gateway_backend.operations import JobStepKey
from gateway_backend.operations.recovery import RecoveryCapabilityValue

router = APIRouter(tags=["operator-recovery"])


def _capability_lookup(registry: JobDefinitionRegistry) -> CapabilityLookup:
    mapping: dict[tuple[str, str], RecoveryCapabilityValue] = {}
    try:
        for step_name in (SUBMIT_STEP_PREPARE, SUBMIT_STEP_SUBMIT, SUBMIT_STEP_AWAIT):
            definition = registry.resolve_runnable(
                JobStepKey(job_kind=SUBMIT_JOB_KIND, step_name=step_name),
                SUBMIT_JOB_CONTRACT_VERSION,
            )
            capability = definition.recovery_capability
            if capability is RecoveryCapability.PURE_RECOMPUTE:
                mapped = RecoveryCapabilityValue.PURE_RECOMPUTE
            elif capability is RecoveryCapability.EXTERNAL_EFFECT:
                mapped = RecoveryCapabilityValue.EXTERNAL_EFFECT
            else:
                mapped = RecoveryCapabilityValue.NON_RETRYABLE
            mapping[(SUBMIT_JOB_KIND, step_name)] = mapped
    except JobDefinitionLookupError as exc:
        raise ApiError(
            code="SERVICE_NOT_READY",
            message="submit job definition is not registered",
            status_code=503,
        ) from exc
    return CapabilityLookup(mapping)


@router.post(
    "/internal/v1/operations/{operation_id}/steps/{step_id}/recovery",
    response_model=OperatorRecoveryResponse,
    responses={
        401: {"description": "AUTHENTICATION_REQUIRED"},
        404: {"description": "RECOVERY_TARGET_NOT_FOUND"},
        409: {
            "description": "RECOVERY_IDENTITY_CONFLICT, OPERATION_VERSION_CONFLICT, STEP_VERSION_CONFLICT, "
            "RECOVERY_STATE_CONFLICT, RECOVERY_CAPABILITY_CONFLICT, ABORT_PROOF_NOT_SATISFIED"
        },
        422: {"description": "REQUEST_VALIDATION_FAILED"},
        503: {"description": "SERVICE_NOT_READY, DEPENDENCY_UNAVAILABLE"},
    },
)
def operator_recovery_route(
    operation_id: str,
    step_id: str,
    body: OperatorRecoveryRequestBody,
    deps: Annotated[WorkspaceHttpDependencies, Depends(get_workspace_http)],
    _: Annotated[None, Depends(require_internal_bearer)],
) -> OperatorRecoveryResponse:
    return execute_operator_recovery(
        path_operation_id=operation_id,
        path_step_id=step_id,
        body=body,
        operation_reader=deps.operation_reader,
        submission_reader=deps.submission_reader,
        operator_recovery_port=deps.operator_recovery_port,
        capability_lookup=_capability_lookup(deps.job_registry),
    )
