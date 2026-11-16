"""History HTTP routes."""

from __future__ import annotations

from gateway_backend.http.bundle_response import BundleStreamingResponse

from typing import Annotated

from fastapi import APIRouter, Depends, Header, Query, Request, Response
from fastapi.responses import StreamingResponse

from gateway_backend.application.history.contracts import (
    MAX_HISTORY_CURSOR_BYTES,
    MAX_HISTORY_PAGE_LIMIT,
    HistoryNodeRef,
    HistoryNodeRefKind,
    PERMISSION_READ_PROJECT_HISTORY,
)
from gateway_backend.domain.workspace.models import IdentityContext
from gateway_backend.domain.workspace.policies import assert_permission
from gateway_backend.http.auth import require_identity
from gateway_backend.http.dependencies import HistoryHttpDependencies, get_history_http, get_workspace_http
from gateway_backend.http.orchestration.history_compare import (
    accept_compare_operation,
    assert_history_result_not_expired,
    build_history_compare_accept_command,
    get_compare_result,
    read_compare_bundle,
)
from gateway_backend.http.errors import ApiError
from gateway_backend.http.schemas.errors import ErrorResponse
from gateway_backend.http.orchestration.history_read import list_history_operation
from gateway_backend.http.orchestration.history_compare_list import list_compare_operations
from gateway_backend.http.orchestration.operation_scope import authorize_history_compare_operation_read
from gateway_backend.http.schemas.history import (
    HistoryCompareAcceptRequest,
    HistoryCompareAcceptResponse,
    HistoryCompareResultResponse,
    HistoryCompareListResponse,
    HistoryListResponse,
)

router = APIRouter(tags=["history"])


def _validate_idempotency_key(raw: str | None) -> str:
    if raw is None or not raw.strip():
        raise ApiError(
            code="REQUEST_VALIDATION_FAILED",
            message="Idempotency-Key header is required",
            status_code=422,
        )
    resolved_key = raw.strip()
    key_byte_length = len(resolved_key.encode("utf-8"))
    if not 1 <= key_byte_length <= 255:
        raise ApiError(
            code="REQUEST_VALIDATION_FAILED",
            message="Idempotency-Key must be 1..255 bytes",
            status_code=422,
        )
    return resolved_key


@router.get(
    "/v1/history",
    response_model=HistoryListResponse,
    responses={
        401: {"description": "AUTHENTICATION_REQUIRED"},
        403: {"description": "SCOPE_FORBIDDEN"},
        422: {"description": "REQUEST_VALIDATION_FAILED"},
        503: {"description": "HISTORY_INTEGRITY_FAILURE, DEPENDENCY_UNAVAILABLE"},
    },
)
def list_history_route(
    deps: Annotated[HistoryHttpDependencies, Depends(get_history_http)],
    context: Annotated[IdentityContext, Depends(require_identity)],
    limit: Annotated[int | None, Query(ge=1, le=MAX_HISTORY_PAGE_LIMIT)] = None,
    cursor: Annotated[str | None, Query(max_length=MAX_HISTORY_CURSOR_BYTES)] = None,
) -> HistoryListResponse:
    return list_history_operation(
        context=context,
        deps=deps,
        limit=limit,
        cursor=cursor,
    )


@router.get(
    "/v1/history-compares", response_model=HistoryCompareListResponse,
    responses={
        401: {"description": "AUTHENTICATION_REQUIRED", "model": ErrorResponse},
        403: {"description": "SCOPE_FORBIDDEN", "model": ErrorResponse},
        404: {"description": "RESOURCE_NOT_FOUND", "model": ErrorResponse},
        422: {"description": "REQUEST_VALIDATION_FAILED", "model": ErrorResponse},
        503: {"description": "HISTORY_INTEGRITY_FAILURE, SERVICE_NOT_READY", "model": ErrorResponse},
    },
)
def list_history_compares_route(
    deps: Annotated[HistoryHttpDependencies, Depends(get_history_http)],
    context: Annotated[IdentityContext, Depends(require_identity)],
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    after: Annotated[str | None, Query(max_length=1024)] = None,
) -> HistoryCompareListResponse:
    return list_compare_operations(context=context, deps=deps, limit=limit, cursor=after)


@router.post(
    "/v1/history-compares",
    response_model=HistoryCompareAcceptResponse,
    status_code=202,
    responses={
        200: {"description": "Existing operation reused or replayed", "model": HistoryCompareAcceptResponse},
        401: {"description": "AUTHENTICATION_REQUIRED", "model": ErrorResponse},
        403: {"description": "SCOPE_FORBIDDEN", "model": ErrorResponse},
        404: {"description": "RESOURCE_NOT_FOUND, ARTIFACT_UNAVAILABLE", "model": ErrorResponse},
        409: {"description": "IDEMPOTENCY_CONFLICT, HISTORY_COMPARE_REQUEST_EXPIRED, HISTORY_COMPARE_SCOPE_LIMIT, ADMISSION_CONFLICT; scope limit details include operation_ids", "model": ErrorResponse},
        413: {"description": "REQUEST_TOO_LARGE", "model": ErrorResponse},
        422: {"description": "REQUEST_VALIDATION_FAILED", "model": ErrorResponse},
        429: {"description": "ADMISSION_LIMIT_REACHED, OPERATION_QUEUE_FULL, HISTORY_COMPARE_ALIAS_LIMIT; alias limit details include operation_id", "model": ErrorResponse},
        503: {"description": "SERVICE_NOT_READY, HISTORY_INTEGRITY_FAILURE, BUNDLE_INTEGRITY_FAILURE", "model": ErrorResponse},
    },
)
def accept_history_compare_route(
    body: HistoryCompareAcceptRequest,
    response: Response,
    request: Request,
    deps: Annotated[HistoryHttpDependencies, Depends(get_history_http)],
    context: Annotated[IdentityContext, Depends(require_identity)],
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key")],
) -> HistoryCompareAcceptResponse:
    resolved_key = _validate_idempotency_key(idempotency_key)
    command = build_history_compare_accept_command(
        context=context,
        idempotency_key=resolved_key,
        node_refs=tuple(
            HistoryNodeRef(ref_kind=HistoryNodeRefKind(node.ref_kind), ref_id=node.ref_id)
            for node in body.nodes
        ),
    )
    result = accept_compare_operation(
        command=command,
        unit_of_work_factory=deps.unit_of_work_factory,
        job_registry=deps.job_registry,
        admission_gate=deps.admission_gate,
        comparison_ruleset_digest=deps.comparison_ruleset_digest,
        now=deps.now(),
        result_retention_seconds=deps.history_result_retention_seconds,
        history_scope_active_limit=deps.history_scope_active_limit,
        operation_queue_limit=deps.operation_queue_limit,
        artifact_store=deps.artifact_store,
        bundle_reader=deps.bundle_reader,
        resolve_current_identity=lambda: get_workspace_http(request).session_port.resolve(request),
    )
    response.status_code = 200 if result.replay else 202
    return result.response


@router.get(
    "/v1/history-compares/{operation_id}",
    response_model=HistoryCompareResultResponse,
    responses={
        401: {"description": "AUTHENTICATION_REQUIRED", "model": ErrorResponse},
        403: {"description": "SCOPE_FORBIDDEN", "model": ErrorResponse},
        404: {"description": "RESOURCE_NOT_FOUND, ARTIFACT_UNAVAILABLE", "model": ErrorResponse},
        410: {"description": "HISTORY_COMPARE_RESULT_EXPIRED", "model": ErrorResponse},
        503: {"description": "HISTORY_INTEGRITY_FAILURE, BUNDLE_INTEGRITY_FAILURE", "model": ErrorResponse},
    },
)
def get_history_compare_route(
    operation_id: str,
    deps: Annotated[HistoryHttpDependencies, Depends(get_history_http)],
    context: Annotated[IdentityContext, Depends(require_identity)],
) -> HistoryCompareResultResponse:
    assert_permission(context, PERMISSION_READ_PROJECT_HISTORY)
    operation = deps.operation_reader.get_operation(operation_id)
    acceptance = authorize_history_compare_operation_read(
        context=context,
        operation=operation,
        unit_of_work_factory=deps.unit_of_work_factory,
    )
    assert_history_result_not_expired(operation=operation, acceptance=acceptance, now=deps.now())
    return get_compare_result(
        operation=operation,
        acceptance=acceptance,
        unit_of_work_factory=deps.unit_of_work_factory,
        artifact_store=deps.artifact_store,
    )


@router.get(
    "/v1/history-compares/{operation_id}/bundle",
    response_class=StreamingResponse,
    responses={
        200: {
            "description": "Complete uncompressed POSIX bundle tar",
            "content": {"application/x-tar": {}},
            "headers": {
                "Content-Length": {"schema": {"type": "integer"}, "description": "Exact complete tar byte count"},
                "ETag": {"schema": {"type": "string"}, "description": "Quoted bundle digest"},
                "Content-Disposition": {"schema": {"type": "string"}, "description": "Safe attachment tar filename"},
            },
        },
        401: {"description": "AUTHENTICATION_REQUIRED", "model": ErrorResponse},
        403: {"description": "SCOPE_FORBIDDEN", "model": ErrorResponse},
        404: {"description": "RESOURCE_NOT_FOUND, ARTIFACT_UNAVAILABLE", "model": ErrorResponse},
        410: {"description": "HISTORY_COMPARE_RESULT_EXPIRED", "model": ErrorResponse},
        503: {"description": "HISTORY_INTEGRITY_FAILURE, BUNDLE_INTEGRITY_FAILURE", "model": ErrorResponse},
    },
)
def get_history_compare_bundle_route(
    operation_id: str,
    deps: Annotated[HistoryHttpDependencies, Depends(get_history_http)],
    context: Annotated[IdentityContext, Depends(require_identity)],
) -> StreamingResponse:
    assert_permission(context, PERMISSION_READ_PROJECT_HISTORY)
    operation = deps.operation_reader.get_operation(operation_id)
    acceptance = authorize_history_compare_operation_read(
        context=context,
        operation=operation,
        unit_of_work_factory=deps.unit_of_work_factory,
    )
    assert_history_result_not_expired(operation=operation, acceptance=acceptance, now=deps.now())
    prepared = read_compare_bundle(
        operation=operation,
        bundle_reader=deps.bundle_reader,
        unit_of_work_factory=deps.unit_of_work_factory,
        artifact_store=deps.artifact_store,
    )
    return BundleStreamingResponse(prepared)
