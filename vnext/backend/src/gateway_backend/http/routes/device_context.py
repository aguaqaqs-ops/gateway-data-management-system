"""Authenticated minimal scope context; no business mutation or additional permission."""

from __future__ import annotations

from typing import Annotated
from fastapi import APIRouter, Depends, Request
from gateway_backend.domain.workspace.models import IdentityContext
from gateway_backend.http.auth import require_identity
from gateway_backend.http.dependencies import get_workspace_http
from gateway_backend.http.errors import ApiError
from gateway_backend.http.schemas.device_registration import DeviceContextResponse

router = APIRouter(tags=["device-context"])


@router.get(
    "/v1/device-context",
    response_model=DeviceContextResponse,
    responses={
        401: {"description": "AUTHENTICATION_REQUIRED"},
        404: {"description": "RESOURCE_NOT_FOUND"},
        422: {"description": "REQUEST_VALIDATION_FAILED"},
        503: {"description": "SERVICE_NOT_READY"},
    },
)
def device_context(
    request: Request, context: Annotated[IdentityContext, Depends(require_identity)]
) -> DeviceContextResponse:
    identity = getattr(request.app.state, "deployment_identity", None)
    if identity is None:
        raise ApiError(
            code="SERVICE_NOT_READY", message="deployment identity unavailable", status_code=503
        )
    scope = get_workspace_http(request).scope_resolution.resolve(context)
    return DeviceContextResponse(
        environment_id=identity[0],
        group_id=identity[1],
        gateway_device_external_key=context.gateway_device_external_key,
        business_project_id=context.business_project_id,
        repository_id=scope.repository_id,
    )
