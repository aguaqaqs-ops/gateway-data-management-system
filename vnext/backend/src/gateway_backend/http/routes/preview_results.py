"""Preview result read routes."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse

from gateway_backend.application.workspace.preview import read_preview_result
from gateway_backend.domain.workspace.models import IdentityContext
from gateway_backend.http.auth import require_identity
from gateway_backend.http.dependencies import WorkspaceHttpDependencies, get_workspace_http
from gateway_backend.http.mappers import preview_result_to_response
from gateway_backend.http.orchestration.bundle_stream import stream_preview_bundle
from gateway_backend.http.schemas.preview import PreviewResultResponse

router = APIRouter(tags=["preview-results"])


@router.get(
    "/v1/workspaces/{workspace_id}/preview-results/{preview_result_id}",
    response_model=PreviewResultResponse,
    responses={
        401: {"description": "AUTHENTICATION_REQUIRED"},
        403: {"description": "SCOPE_FORBIDDEN"},
        404: {"description": "RESOURCE_NOT_FOUND"},
        503: {"description": "SERVICE_NOT_READY"},
    },
)
def get_preview_result_route(
    workspace_id: str,
    preview_result_id: str,
    deps: Annotated[WorkspaceHttpDependencies, Depends(get_workspace_http)],
    context: Annotated[IdentityContext, Depends(require_identity)],
) -> PreviewResultResponse:
    state = read_preview_result(
        context=context,
        preview_result_id=preview_result_id,
        workspace_id=workspace_id,
        repository=deps.workspace_repository,
        baseline_head_read=deps.baseline_head_read,
    )
    return preview_result_to_response(state)


@router.get(
    "/v1/workspaces/{workspace_id}/preview-results/{preview_result_id}/bundle",
    responses={
        200: {"content": {"application/octet-stream": {}}},
        401: {"description": "AUTHENTICATION_REQUIRED"},
        403: {"description": "SCOPE_FORBIDDEN"},
        404: {"description": "RESOURCE_NOT_FOUND"},
        503: {"description": "SERVICE_NOT_READY"},
    },
)
def read_preview_bundle_route(
    workspace_id: str,
    preview_result_id: str,
    deps: Annotated[WorkspaceHttpDependencies, Depends(get_workspace_http)],
    context: Annotated[IdentityContext, Depends(require_identity)],
) -> StreamingResponse:
    logical_name, stream = stream_preview_bundle(
        context=context,
        workspace_id=workspace_id,
        preview_result_id=preview_result_id,
        workspace_repository=deps.workspace_repository,
        baseline_head_read=deps.baseline_head_read,
        bundle_reader=deps.bundle_reader,
    )
    return StreamingResponse(
        stream,
        media_type="application/octet-stream",
        headers={"Content-Disposition": f'attachment; filename="{logical_name}"'},
    )
