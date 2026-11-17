"""Internal operator recovery routes."""

from __future__ import annotations

from typing import Annotated, Literal

from fastapi import APIRouter, Depends

from gateway_backend.application.submission.contracts import ExecuteOperatorRecoveryCommand
from gateway_backend.application.submission.operator_recovery import execute_operator_recovery
from gateway_backend.http.auth import require_internal_bearer
from gateway_backend.http.dependencies import WorkspaceHttpDependencies, get_workspace_http
from gateway_backend.http.schemas.operator_recovery import (
    OperatorRecoveryRequestBody,
    OperatorRecoveryResponse,
)
from gateway_backend.operations.recovery import OperatorRecoveryCommand
from gateway_backend.operations.state import TransitionDisposition

router = APIRouter(tags=["operator-recovery"])


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
    command = ExecuteOperatorRecoveryCommand(
        path_operation_id=operation_id,
        path_step_id=step_id,
        body_operation_id=body.operation_id,
        body_step_id=body.step_id,
        command=OperatorRecoveryCommand(body.command),
        expected_operation_optimistic_version=body.expected_operation_optimistic_version,
        expected_step_optimistic_version=body.expected_step_optimistic_version,
        reason=body.reason,
    )
    result = execute_operator_recovery(
        command=command,
        operation_reader=deps.operation_reader,
        submission_reader=deps.submission_reader,
        operator_recovery_port=deps.operator_recovery_port,
        job_registry=deps.job_registry,
    )
    disposition: Literal["APPLY", "IDEMPOTENT"] = (
        "IDEMPOTENT" if result.disposition is TransitionDisposition.IDEMPOTENT else "APPLY"
    )
    return OperatorRecoveryResponse(
        operation_id=result.operation_id,
        step_id=result.step_id,
        command=body.command,
        disposition=disposition,
    )
