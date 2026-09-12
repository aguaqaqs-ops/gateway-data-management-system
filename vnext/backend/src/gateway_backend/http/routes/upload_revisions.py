"""Upload revision routes."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Request, status
from starlette.datastructures import UploadFile

from gateway_backend.domain.workspace.models import IdentityContext
from gateway_backend.http.auth import require_identity
from gateway_backend.http.dependencies import WorkspaceHttpDependencies, get_workspace_http
from gateway_backend.http.errors import ApiError
from gateway_backend.http.orchestration.multipart_upload import (
    accept_multipart_upload,
)
from gateway_backend.http.orchestration.source_package_admission import (
    UploadClosureInvalidError,
    UploadLimitExceededError,
    UploadMediaUnsupportedError,
)
from gateway_backend.http.schemas.upload import UploadRevisionResponse

router = APIRouter(tags=["upload"])


@router.post(
    "/v1/workspaces/{workspace_id}/upload-revisions",
    response_model=UploadRevisionResponse,
    status_code=status.HTTP_201_CREATED,
    responses={
        401: {"description": "AUTHENTICATION_REQUIRED"},
        403: {"description": "SCOPE_FORBIDDEN"},
        404: {"description": "RESOURCE_NOT_FOUND"},
        409: {"description": "IDEMPOTENCY_CONFLICT or WORKSPACE_VERSION_CONFLICT"},
        413: {"description": "UPLOAD_LIMIT_EXCEEDED"},
        415: {"description": "UPLOAD_MEDIA_UNSUPPORTED"},
        422: {"description": "REQUEST_VALIDATION_FAILED or UPLOAD_CLOSURE_INVALID"},
        429: {"description": "ADMISSION_LIMIT_REACHED"},
        503: {"description": "SERVICE_NOT_READY"},
    },
)
async def accept_upload_route(
    workspace_id: str,
    request: Request,
    deps: Annotated[WorkspaceHttpDependencies, Depends(get_workspace_http)],
    context: Annotated[IdentityContext, Depends(require_identity)],
) -> UploadRevisionResponse:
    if not deps.admission_gate.allows_new_work():
        raise ApiError(
            code="ADMISSION_LIMIT_REACHED",
            message="gateway admission is closed for new work",
            status_code=429,
        )
    idempotency_key = request.headers.get("Idempotency-Key")
    if idempotency_key is None or not idempotency_key.strip():
        raise ApiError(
            code="REQUEST_VALIDATION_FAILED",
            message="Idempotency-Key header is required",
            status_code=422,
        )
    resolved_key = idempotency_key.strip()
    if len(resolved_key) > 255:
        raise ApiError(
            code="REQUEST_VALIDATION_FAILED",
            message="Idempotency-Key must be 1..255 characters",
            status_code=422,
        )
    form = await request.form()
    manifest_part = form.get("manifest")
    if not isinstance(manifest_part, UploadFile):
        raise ApiError(
            code="REQUEST_VALIDATION_FAILED",
            message="manifest multipart part is required",
            status_code=422,
        )
    file_parts: dict[str, UploadFile] = {}
    for key, value in form.multi_items():
        if key == "manifest":
            continue
        if not isinstance(value, UploadFile):
            raise ApiError(
                code="REQUEST_VALIDATION_FAILED",
                message=f"part {key!r} must be a file upload",
                status_code=422,
            )
        if key in file_parts:
            raise ApiError(
                code="REQUEST_VALIDATION_FAILED",
                message=f"duplicate multipart part {key!r}",
                status_code=422,
            )
        file_parts[key] = value
    try:
        return await accept_multipart_upload(
            context=context,
            workspace_id=workspace_id,
            idempotency_key=resolved_key,
            manifest_part=manifest_part,
            file_parts=file_parts,
            scope_resolution=deps.scope_resolution,
            workspace_repository=deps.workspace_repository,
            unit_of_work_factory=deps.unit_of_work_factory,
            artifact_store=deps.artifact_store,
            now=deps.now(),
        )
    except UploadLimitExceededError as exc:
        raise ApiError(
            code="UPLOAD_LIMIT_EXCEEDED",
            message=str(exc),
            status_code=413,
        ) from exc
    except UploadMediaUnsupportedError as exc:
        raise ApiError(
            code="UPLOAD_MEDIA_UNSUPPORTED",
            message=str(exc),
            status_code=415,
        ) from exc
    except UploadClosureInvalidError as exc:
        raise ApiError(
            code="UPLOAD_CLOSURE_INVALID",
            message=str(exc),
            status_code=422,
        ) from exc
