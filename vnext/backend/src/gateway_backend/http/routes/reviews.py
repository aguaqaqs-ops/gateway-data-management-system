"""Review HTTP routes."""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, Request, Response, status

from gateway_backend.http.dependencies import request_scratch

from gateway_backend.domain.workspace.models import IdentityContext
from gateway_backend.http.auth import require_identity
from gateway_backend.http.dependencies import (
    WorkspaceHttpDependencies,
    acquire_new_work,
    get_workspace_http,
)
from gateway_backend.http.orchestration.review import (
    apply_review_operation,
    build_apply_review_command,
    get_review_facts_operation,
    parse_review_idempotency_key,
    read_submission_result_operation,
)
from gateway_backend.http.schemas.review import (
    ApplyReviewRequest,
    ReviewAppliedResponse,
    ReviewFactsResponse,
    SubmissionResultResponse,
    SubmissionResultPairResponse,
)
from fastapi.responses import StreamingResponse
from gateway_backend.http.bundle_response import BundleStreamingResponse
from gateway_backend.http.errors import ApiError
from gateway_backend.artifacts.bundle_download import BundleIntegrityError
from gateway_backend.artifacts.store import ArtifactUnavailableError

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
            "REVIEW_TRANSITION_CONFLICT, WORKSPACE_OCCUPANCY_CONFLICT, "
            "BASELINE_VERSION_CONFLICT, ARCHIVE_CLOSED"
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
    with acquire_new_work(deps.admission_gate), request_scratch(deps.scratch):
        result = apply_review_operation(
            command=command,
            scope_resolution=deps.scope_resolution,
            unit_of_work_factory=deps.review_unit_of_work_factory,
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
        unit_of_work_factory=deps.review_unit_of_work_factory,
    )


_RESULT_ERRORS: dict[int | str, dict[str, Any]] = {
    401: {"description": "AUTHENTICATION_REQUIRED"},
    403: {"description": "SCOPE_FORBIDDEN"},
    404: {"description": "RESOURCE_NOT_FOUND"},
    503: {"description": "SUBMISSION_RESULT_UNAVAILABLE, SUBMISSION_RESULT_INTEGRITY_FAILURE"},
}


@router.get(
    "/v1/submissions/{submission_id}/result",
    response_model=SubmissionResultResponse,
    responses=_RESULT_ERRORS,
)
def get_submission_result_route(
    submission_id: str,
    deps: Annotated[WorkspaceHttpDependencies, Depends(get_workspace_http)],
    context: Annotated[IdentityContext, Depends(require_identity)],
) -> SubmissionResultResponse:
    preview = read_submission_result_operation(
        context=context, submission_id=submission_id, deps=deps
    )
    return SubmissionResultResponse(
        submission_id=submission_id,
        preview_result_id=preview.preview_result_id,
        bundle_digest=preview.digests.bundle_digest,
        default_pair_id="initial_to_modified",
        input_completeness=("FULL" if len(preview.comparison_pairs) == 2 else "MODIFIED_ONLY"),
        pairs=[
            SubmissionResultPairResponse(
                pair_id=pair.pair_id,
                comparison_digest=pair.comparison_digest,
                risk_digest=pair.risk_digest,
                surface_digest=pair.surface_digest,
            )
            for pair in preview.comparison_pairs
        ],
    )


@router.get(
    "/v1/submissions/{submission_id}/result/bundle",
    response_class=StreamingResponse,
    responses={
        **_RESULT_ERRORS,
        200: {
            "description": "Immutable submission-bound Preview bundle",
            "content": {"application/x-tar": {}},
            "headers": {
                "Content-Length": {"schema": {"type": "integer"}},
                "ETag": {"schema": {"type": "string"}},
                "Content-Disposition": {"schema": {"type": "string"}},
            },
        },
    },
)
def get_submission_result_bundle_route(
    submission_id: str,
    deps: Annotated[WorkspaceHttpDependencies, Depends(get_workspace_http)],
    context: Annotated[IdentityContext, Depends(require_identity)],
) -> StreamingResponse:
    preview = read_submission_result_operation(
        context=context, submission_id=submission_id, deps=deps
    )
    try:
        prepared = deps.bundle_reader.prepare_bundle(preview.bundle_artifact_id)
        if prepared.bundle_digest != preview.digests.bundle_digest:
            prepared.close()
            raise BundleIntegrityError("Submission bundle digest mismatch")
        return BundleStreamingResponse(prepared)
    except ArtifactUnavailableError:
        raise ApiError(
            code="SUBMISSION_RESULT_UNAVAILABLE",
            message="submission result is unavailable",
            status_code=503,
        ) from None
    except BundleIntegrityError:
        raise ApiError(
            code="SUBMISSION_RESULT_INTEGRITY_FAILURE",
            message="submission result failed integrity verification",
            status_code=503,
        ) from None
