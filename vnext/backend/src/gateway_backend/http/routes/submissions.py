"""Submission read routes."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends

from gateway_backend.domain.workspace.models import IdentityContext
from gateway_backend.http.auth import require_identity
from gateway_backend.http.dependencies import WorkspaceHttpDependencies, get_workspace_http
from gateway_backend.http.orchestration.operation_scope import read_submission
from gateway_backend.http.schemas.submit import SubmissionResponse, submission_to_response

router = APIRouter(tags=["submissions"])


@router.get(
    "/v1/workspaces/{workspace_id}/submissions/{submission_id}",
    response_model=SubmissionResponse,
    responses={
        401: {"description": "AUTHENTICATION_REQUIRED"},
        403: {"description": "SCOPE_FORBIDDEN"},
        404: {"description": "RESOURCE_NOT_FOUND"},
        503: {"description": "SERVICE_NOT_READY"},
    },
)
def get_submission_route(
    workspace_id: str,
    submission_id: str,
    deps: Annotated[WorkspaceHttpDependencies, Depends(get_workspace_http)],
    context: Annotated[IdentityContext, Depends(require_identity)],
) -> SubmissionResponse:
    submission = read_submission(
        context=context,
        workspace_id=workspace_id,
        submission_id=submission_id,
        workspace_repository=deps.workspace_repository,
        submission_reader=deps.submission_reader,
        scope_resolution=deps.scope_resolution,
    )
    return submission_to_response(submission)
