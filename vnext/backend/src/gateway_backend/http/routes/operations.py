"""Operation read routes."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends

from gateway_backend.domain.workspace.models import IdentityContext
from gateway_backend.http.auth import require_identity
from gateway_backend.http.dependencies import WorkspaceHttpDependencies, get_workspace_http
from gateway_backend.http.mappers import operation_to_response
from gateway_backend.application.history.contracts import HISTORY_COMPARE_JOB_KIND
from gateway_backend.http.orchestration.history_compare import get_compare_result
from gateway_backend.http.orchestration.operation_scope import (
    assert_workspace_read_permission,
    authorize_history_compare_operation_read,
    authorize_operation_read,
)
from gateway_backend.http.dependencies import get_history_http, HistoryHttpDependencies
from gateway_backend.http.errors import ApiError
from gateway_backend.http.schemas.operation import OperationResponse

router = APIRouter(tags=["operations"])


@router.get(
    "/v1/operations/{operation_id}",
    response_model=OperationResponse,
    responses={
        401: {"description": "AUTHENTICATION_REQUIRED"},
        403: {"description": "SCOPE_FORBIDDEN"},
        404: {"description": "RESOURCE_NOT_FOUND"},
        503: {"description": "SERVICE_NOT_READY"},
    },
)
def get_operation_route(
    operation_id: str,
    deps: Annotated[WorkspaceHttpDependencies, Depends(get_workspace_http)],
    history_deps: Annotated[HistoryHttpDependencies, Depends(get_history_http)],
    context: Annotated[IdentityContext, Depends(require_identity)],
) -> OperationResponse:
    try:
        operation = deps.operation_reader.get_operation(operation_id)
    except ApiError as exc:
        if exc.status_code == 404:
            assert_workspace_read_permission(context)
        raise
    if operation.job_kind == HISTORY_COMPARE_JOB_KIND:
        acceptance = authorize_history_compare_operation_read(
            context=context,
            operation=operation,
            unit_of_work_factory=history_deps.unit_of_work_factory,
        )
        compare_result = get_compare_result(
            operation=operation,
            acceptance=acceptance,
            unit_of_work_factory=history_deps.unit_of_work_factory,
            artifact_store=history_deps.artifact_store,
        )
        response = operation_to_response(operation)
        return OperationResponse(
            operation_id=response.operation_id,
            job_kind=response.job_kind,
            status=response.status,
            optimistic_version=response.optimistic_version,
            created_at=response.created_at,
            started_at=response.started_at,
            completed_at=response.completed_at,
            diagnostic=response.diagnostic,
            integrity_incident=compare_result.integrity_incident,
        )
    assert_workspace_read_permission(context)
    authorize_operation_read(
        context=context,
        operation=operation,
        workspace_repository=deps.workspace_repository,
        submission_reader=deps.submission_reader,
        scope_resolution=deps.scope_resolution,
        permission_checked=True,
    )
    return operation_to_response(operation)
