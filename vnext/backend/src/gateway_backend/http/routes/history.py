"""History HTTP routes."""

from __future__ import annotations

from typing import Annotated, cast

from fastapi import APIRouter, Depends, Header, Query, Response
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
from gateway_backend.http.dependencies import HistoryHttpDependencies, get_history_http
from gateway_backend.http.orchestration.history_compare import (
    accept_compare_operation,
    build_history_compare_accept_command,
    get_compare_result,
    read_compare_bundle,
)
from gateway_backend.http.errors import ApiError
from gateway_backend.http.orchestration.history_read import list_history_operation
from gateway_backend.http.orchestration.operation_scope import authorize_history_compare_operation_read
from gateway_backend.http.schemas.history import (
    HistoryCompareAcceptRequest,
    HistoryCompareAcceptResponse,
    HistoryCompareResultResponse,
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


@router.post(
    "/v1/history-compares",
    response_model=HistoryCompareAcceptResponse,
    responses={
        401: {"description": "AUTHENTICATION_REQUIRED"},
        403: {"description": "SCOPE_FORBIDDEN"},
        404: {"description": "RESOURCE_NOT_FOUND"},
        409: {"description": "IDEMPOTENCY_CONFLICT, ADMISSION_CONFLICT"},
        413: {"description": "REQUEST_TOO_LARGE"},
        422: {"description": "REQUEST_VALIDATION_FAILED"},
        429: {"description": "ADMISSION_LIMIT_REACHED"},
        503: {"description": "SERVICE_NOT_READY"},
    },
)
def accept_history_compare_route(
    body: HistoryCompareAcceptRequest,
    response: Response,
    deps: Annotated[HistoryHttpDependencies, Depends(get_history_http)],
    context: Annotated[IdentityContext, Depends(require_identity)],
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
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
    )
    response.status_code = 200 if result.replay else 202
    return result.response


@router.get(
    "/v1/history-compares/{operation_id}",
    response_model=HistoryCompareResultResponse,
    responses={
        401: {"description": "AUTHENTICATION_REQUIRED"},
        403: {"description": "SCOPE_FORBIDDEN"},
        404: {"description": "RESOURCE_NOT_FOUND, ARTIFACT_UNAVAILABLE"},
        503: {"description": "HISTORY_INTEGRITY_FAILURE"},
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
    return get_compare_result(
        operation=operation,
        acceptance=acceptance,
        unit_of_work_factory=deps.unit_of_work_factory,
        artifact_store=deps.artifact_store,
    )


@router.get(
    "/v1/history-compares/{operation_id}/bundle",
    responses={
        401: {"description": "AUTHENTICATION_REQUIRED"},
        403: {"description": "SCOPE_FORBIDDEN"},
        404: {"description": "RESOURCE_NOT_FOUND, ARTIFACT_UNAVAILABLE"},
    },
)
def get_history_compare_bundle_route(
    operation_id: str,
    deps: Annotated[HistoryHttpDependencies, Depends(get_history_http)],
    context: Annotated[IdentityContext, Depends(require_identity)],
) -> StreamingResponse:
    assert_permission(context, PERMISSION_READ_PROJECT_HISTORY)
    operation = deps.operation_reader.get_operation(operation_id)
    authorize_history_compare_operation_read(
        context=context,
        operation=operation,
        unit_of_work_factory=deps.unit_of_work_factory,
    )
    _logical_name, stream = read_compare_bundle(
        operation=operation,
        bundle_reader=deps.bundle_reader,
        unit_of_work_factory=deps.unit_of_work_factory,
        artifact_store=deps.artifact_store,
    )
    from collections.abc import Iterable

    return StreamingResponse(
        cast(Iterable[bytes], stream),
        media_type="application/octet-stream",
        headers={
            "Content-Disposition": f'attachment; filename="history-compare-{operation_id}.bundle"'
        },
    )
