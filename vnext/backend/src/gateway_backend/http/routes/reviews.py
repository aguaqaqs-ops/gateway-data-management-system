"""Review HTTP routes."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response, status

from gateway_backend.domain.workspace.models import IdentityContext
from gateway_backend.http.auth import require_identity
from gateway_backend.http.dependencies import WorkspaceHttpDependencies, acquire_new_work, get_workspace_http
from gateway_backend.http.orchestration.review import (
    apply_review_operation,
    build_apply_review_command,
    get_review_facts_operation,
    parse_review_idempotency_key,
)
from gateway_backend.http.schemas.review import ApplyReviewRequest, ReviewAppliedResponse, ReviewFactsResponse

router = APIRouter(tags=["reviews"])


@router.post(
    "/v1/submissions/{submission_id}/review-events",
    response_model=ReviewAppliedResponse,
    status_code=status.HTTP_201_CREATED,
    responses={
        200: {"description": "Idempotent replay", "model": ReviewAppliedResponse},
        401: {"description": "AUTHENTICATION_REQUIRED"},
        403: {"description": "SCOPE_FORBIDDEN"},
        404: {"description": "RESOURCE_NOT_FOUND"},
        409: {
            "description": "IDEMPOTENCY_CONFLICT, REVIEW_VERSION_CONFLICT, "
            "REVIEW_TRANSITION_CONFLICT, WORKSPACE_OCCUPANCY_CONFLICT"
        },
        422: {"description": "REQUEST_VALIDATION_FAILED"},
        429: {"description": "ADMISSION_LIMIT_REACHED"},
        503: {"description": "DEPENDENCY_UNAVAILABLE, SERVICE_NOT_READY"},
    },
)
def apply_review_route(
    submission_id: str,
    body: ApplyReviewRequest,
    request: Request,
    response: Response,
    deps: Annotated[WorkspaceHttpDependencies, Depends(get_workspace_http)],
    context: Annotated[IdentityContext, Depends(require_identity)],
) -> ReviewAppliedResponse:
    idempotency_key = parse_review_idempotency_key(request.headers.get("Idempotency-Key"))
    command = build_apply_review_command(
        context=context,
        submission_id=submission_id,
        body=body,
        idempotency_key=idempotency_key,
    )
    with acquire_new_work(deps.admission_gate):
        result = apply_review_operation(
            command=command,
            scope_resolution=deps.scope_resolution,
            unit_of_work_factory=deps.unit_of_work_factory,
            now=deps.now(),
        )
    if result.replay:
        response.status_code = status.HTTP_200_OK
    return result.response


@router.get(
    "/v1/submissions/{submission_id}/review",
    response_model=ReviewFactsResponse,
    responses={
        401: {"description": "AUTHENTICATION_REQUIRED"},
        403: {"description": "SCOPE_FORBIDDEN"},
        404: {"description": "RESOURCE_NOT_FOUND"},
        503: {"description": "DEPENDENCY_UNAVAILABLE, SERVICE_NOT_READY"},
    },
)
def get_review_facts_route(
    submission_id: str,
    deps: Annotated[WorkspaceHttpDependencies, Depends(get_workspace_http)],
    context: Annotated[IdentityContext, Depends(require_identity)],
) -> ReviewFactsResponse:
    return get_review_facts_operation(
        context=context,
        submission_id=submission_id,
        scope_resolution=deps.scope_resolution,
        unit_of_work_factory=deps.unit_of_work_factory,
    )
