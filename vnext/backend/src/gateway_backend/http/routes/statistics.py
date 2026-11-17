"""Authorized saved telemetry only. These GETs never collect or mutate data."""

from __future__ import annotations

from collections.abc import Callable
from typing import Annotated, Any
from pathlib import Path
import socket
import struct

from fastapi import APIRouter, Depends, Query, Request, Response

from gateway_backend.application.statistics_queries import (
    assert_statistics_group_permission,
    authorize_operation_statistics,
    authorize_repository_statistics,
    read_group_resources,
    read_group_statistics,
    read_operation_executions,
    read_operation_resources,
    read_repository_statistics,
)
from gateway_backend.domain.workspace.models import IdentityContext
from gateway_backend.http.auth import (
    require_identity,
    require_session_identity,
)
from gateway_backend.http.dependencies import (
    HistoryHttpDependencies,
    WorkspaceHttpDependencies,
    get_history_http,
    get_workspace_http,
)
from gateway_backend.http.errors import ApiError
from gateway_backend.http.schemas.statistics import (
    CurrentProcess,
    ExecutionPage,
    GroupResourceQuery,
    GroupStatistics,
    GroupStorageItem,
    OperationResourceQuery,
    ResourcePage,
    StatisticsPage,
    StatisticsQuery,
    StoragePage,
    WritePage,
)
from gateway_backend.http.statistics import (
    StatisticsHttpDependencies,
    get_statistics_http,
    page_metadata,
    query_error,
    resource_page,
    respond,
    time_range,
)
from gateway_backend.statistics.models import StorageRecord
from gateway_backend.statistics.queries import (
    CollectionKind,
    GroupRead,
    ReadPage,
    ReadRequest,
    ResourceRequest,
    StatisticsReadError,
)

router = APIRouter(tags=["statistics"])

# CSV carries the same page metadata in headers; no server export file or query session.
RESPONSES: dict[int | str, dict[str, Any]] = {
    200: {
        "description": "Finite saved statistics. CSV implies export. JSON/CSV share authorization and SQL budgets. "
        "Normal limit 100/500 max; export 1000/10000 max and 32MiB. Curves default 1h/max6h, max_points 600/2000 max; "
        "raw reads 50000 rows and 1s SQL budget. No cross-page snapshot. Counters are within-instance interval deltas; "
        "memory is sampled avg/max/count; gaps are not interpolated.",
        "content": {"text/csv": {"schema": {"type": "string"}}},
        "headers": {
            name: {"schema": {"type": "string"}, "description": description}
            for name, description in {
                "X-Statistics-Next-Cursor": "Next page cursor; absent when complete.",
                "X-Statistics-Schema-Version": "Schema version 1.",
                "X-Statistics-Generated-At-Us": "Response generation UTC microseconds.",
                "X-Statistics-Window-Start-Us": "Requested inclusive UTC microseconds.",
                "X-Statistics-Window-End-Us": "Requested exclusive UTC microseconds.",
                "X-Statistics-Coverage-Start-Us": "First returned saved sample; absent for empty results.",
                "X-Statistics-Coverage-End-Us": "Last returned saved sample; absent for empty results.",
                "X-Statistics-Quality": "available, partial or unavailable.",
                "X-Statistics-Reason": "Stable missing/partial reason, when known.",
                "X-Statistics-Units": "Explicit byte/count/time units.",
                "Content-Disposition": "Bounded attachment for all exports.",
            }.items()
        },
    },
    401: {"description": "AUTHENTICATION_REQUIRED"},
    403: {"description": "SCOPE_FORBIDDEN"},
    404: {"description": "RESOURCE_NOT_FOUND"},
    422: {
        "description": "REQUEST_VALIDATION_FAILED; narrow range or select claim_version on budget rejection."
    },
    429: {"description": "STATISTICS_EXPORT_BUSY; one preparation/send per backend, no queue."},
    503: {"description": "STATISTICS_UNAVAILABLE; disabled or unhealthy database."},
}

WorkspaceDeps = Annotated[WorkspaceHttpDependencies, Depends(get_workspace_http)]
HistoryDeps = Annotated[HistoryHttpDependencies, Depends(get_history_http)]
Identity = Annotated[IdentityContext, Depends(require_identity)]


def _collection(
    kind: CollectionKind,
    request: Request,
    query: StatisticsQuery,
    read_page: Callable[[StatisticsHttpDependencies, int, int], ReadPage],
) -> Response:
    deps = get_statistics_http(request)
    now = deps.now()
    start, end = time_range(query, now)

    def prepare() -> StatisticsPage[Any]:
        data = read_page(deps, start, end)
        timestamps = [
            item.window_end_us if isinstance(item, StorageRecord) else item.recorded_at_us
            for item in data.items
        ]
        model = (
            StoragePage
            if kind.startswith("storage")
            else WritePage
            if kind == "writes"
            else ExecutionPage
        )
        return model.model_validate(
            dict(
                items=data.items,
                next_cursor=data.next_cursor,
                **page_metadata(data.items, start, end, now, timestamps),
            )
        )

    return respond(deps, query, prepare)


def _repository_collection(
    kind: CollectionKind,
    repository_id: str,
    request: Request,
    query: StatisticsQuery,
    deps: WorkspaceHttpDependencies,
    context: IdentityContext,
) -> Response:
    authorize_repository_statistics(
        context=context,
        repository_id=repository_id,
        scope_resolution=deps.scope_resolution,
    )
    return _collection(
        kind,
        request,
        query,
        lambda stats, start, end: read_repository_statistics(
            context=context,
            repository_id=repository_id,
            scope_resolution=deps.scope_resolution,
            reader=stats.reader,
            request=ReadRequest(
                kind=kind,
                owner_id=repository_id,
                start_us=start,
                end_us=end,
                limit=query.effective_limit,
                cursor=query.cursor,
            ),
        ),
    )


@router.get(
    "/v1/repositories/{repository_id}/statistics/storage",
    response_model=StoragePage,
    responses=RESPONSES,
)
def repository_storage(
    repository_id: str,
    request: Request,
    query: Annotated[StatisticsQuery, Query()],
    deps: WorkspaceDeps,
    context: Identity,
) -> Response:
    return _repository_collection("storage", repository_id, request, query, deps, context)


@router.get(
    "/v1/repositories/{repository_id}/statistics/storage/history",
    response_model=StoragePage,
    responses=RESPONSES,
)
def repository_storage_history(
    repository_id: str,
    request: Request,
    query: Annotated[StatisticsQuery, Query()],
    deps: WorkspaceDeps,
    context: Identity,
) -> Response:
    return _repository_collection("storage_history", repository_id, request, query, deps, context)


@router.get(
    "/v1/repositories/{repository_id}/statistics/writes",
    response_model=WritePage,
    responses=RESPONSES,
)
def repository_writes(
    repository_id: str,
    request: Request,
    query: Annotated[StatisticsQuery, Query()],
    deps: WorkspaceDeps,
    context: Identity,
) -> Response:
    return _repository_collection("writes", repository_id, request, query, deps, context)


@router.get(
    "/v1/operations/{operation_id}/statistics/executions",
    response_model=ExecutionPage,
    responses=RESPONSES,
)
def operation_executions(
    operation_id: str,
    request: Request,
    query: Annotated[StatisticsQuery, Query()],
    deps: WorkspaceDeps,
    history_deps: HistoryDeps,
    context: Identity,
) -> Response:
    authorize_operation_statistics(
        context=context,
        operation_id=operation_id,
        operation_reader=deps.operation_reader,
        workspace_repository=deps.workspace_repository,
        submission_reader=deps.submission_reader,
        scope_resolution=deps.scope_resolution,
        history_unit_of_work_factory=history_deps.unit_of_work_factory,
    )
    return _collection(
        "executions",
        request,
        query,
        lambda stats, start, end: read_operation_executions(
            context=context,
            operation_id=operation_id,
            operation_reader=deps.operation_reader,
            workspace_repository=deps.workspace_repository,
            submission_reader=deps.submission_reader,
            scope_resolution=deps.scope_resolution,
            history_unit_of_work_factory=history_deps.unit_of_work_factory,
            reader=stats.reader,
            request=ReadRequest(
                kind="executions",
                owner_id=operation_id,
                start_us=start,
                end_us=end,
                limit=query.effective_limit,
                cursor=query.cursor,
            ),
        ),
    )


@router.get(
    "/v1/operations/{operation_id}/statistics/resources",
    response_model=ResourcePage,
    responses=RESPONSES,
)
def operation_resources(
    operation_id: str,
    request: Request,
    query: Annotated[OperationResourceQuery, Query()],
    deps: WorkspaceDeps,
    history_deps: HistoryDeps,
    context: Identity,
) -> Response:
    authorize_operation_statistics(
        context=context,
        operation_id=operation_id,
        operation_reader=deps.operation_reader,
        workspace_repository=deps.workspace_repository,
        submission_reader=deps.submission_reader,
        scope_resolution=deps.scope_resolution,
        history_unit_of_work_factory=history_deps.unit_of_work_factory,
    )
    stats = get_statistics_http(request)
    now = stats.now()
    start, end = time_range(query, now, resources=True)
    return respond(
        stats,
        query,
        lambda: resource_page(
            read_operation_resources(
                context=context,
                operation_id=operation_id,
                operation_reader=deps.operation_reader,
                workspace_repository=deps.workspace_repository,
                submission_reader=deps.submission_reader,
                scope_resolution=deps.scope_resolution,
                history_unit_of_work_factory=history_deps.unit_of_work_factory,
                reader=stats.reader,
                request=ResourceRequest(
                    start_us=start,
                    end_us=end,
                    operation_id=operation_id,
                    step_id=query.step_id,
                    attempt_count=query.attempt_count,
                    claim_version=query.claim_version,
                ),
            ),
            query,
            start,
            end,
            now,
            f"{operation_id}:{query.step_id}:{query.attempt_count}:{query.claim_version}",
            sample_interval_seconds=stats.sample_interval_seconds,
        ),
    )


def _group_statistics_response(request: Request, context: IdentityContext) -> GroupStatistics:
    assert_statistics_group_permission(context)
    stats = get_statistics_http(request)
    now = stats.now()
    start, end = time_range(StatisticsQuery(), now)

    health = stats.health()
    try:
        data = read_group_statistics(
            context=context,
            reader=stats.reader,
            start_us=start,
            end_us=end,
        )
    except StatisticsReadError as exc:
        if exc.reason != "unavailable":
            raise query_error(exc) from None
        data = GroupRead((), (), False)
        health = health.model_copy(
            update={"quality": "unavailable", "reason": health.reason or "collection_failed"}
        )
    # Group access never serializes repository, operation, table names or business fields.
    storage = tuple(
        GroupStorageItem.model_validate(
            {
                key: value
                for key, value in record.model_dump().items()
                if key not in ("environment_id", "group_id", "repository_id", "source_event_id")
            }
        )
        for record in data.storage
    )
    return GroupStatistics(
        environment_id=stats.reader.identity.environment_id,
        group_id=stats.reader.identity.group_id,
        generated_at_us=int(now.timestamp() * 1000000),
        storage=storage,
        current_instances=tuple(
            CurrentProcess(role=role, process_instance_id=instance)
            for role, instance in data.instances
        ),
        instances_truncated=data.instances_truncated,
        health=health,
    )


def _group_resources_response(
    request: Request, query: GroupResourceQuery, context: IdentityContext
) -> Response:
    assert_statistics_group_permission(context)
    stats = get_statistics_http(request)
    now = stats.now()
    start, end = time_range(query, now, resources=True)
    return respond(
        stats,
        query,
        lambda: resource_page(
            read_group_resources(
                context=context,
                reader=stats.reader,
                request=ResourceRequest(
                    start_us=start,
                    end_us=end,
                    role=query.role,
                    process_instance_id=query.process_instance_id,
                ),
            ),
            query,
            start,
            end,
            now,
            f"{query.role}:{query.process_instance_id}",
            sample_interval_seconds=stats.sample_interval_seconds,
        ),
    )


@router.get(
    "/v1/statistics/group",
    response_model=GroupStatistics,
    responses={
        **RESPONSES,
        200: {
            "description": "Bounded current group capacity, public overhead, recent process identities and collection health."
        },
    },
)
def group_statistics(request: Request, context: Identity) -> GroupStatistics:
    return _group_statistics_response(request, context)


@router.get("/v1/statistics/group/resources", response_model=ResourcePage, responses=RESPONSES)
def group_resources(
    request: Request, query: Annotated[GroupResourceQuery, Query()], context: Identity
) -> Response:
    return _group_resources_response(request, query, context)


def _default_gateway_peer() -> str | None:
    """Kernel-derived host peer for the group's sole inspected Docker bridge.

    The deployment inspector verifies strict host-loopback publication and this
    route against network IPAM. No caller Host/forwarded value grants trust.
    """
    try:
        with Path("/proc/net/route").open("r", encoding="ascii") as routes:
            raw = routes.read(65537)
        if len(raw) > 65536:
            return None
        gateways = {
            socket.inet_ntoa(struct.pack("<I", int(fields[2], 16)))
            for line in raw.splitlines()[1:]
            if len(fields := line.split()) >= 4
            and fields[1] == "00000000"
            and int(fields[3], 16) & 3 == 3
            and fields[2] != "00000000"
        }
        return next(iter(gateways)) if len(gateways) == 1 else None
    except OSError, ValueError, UnicodeError, struct.error:
        return None


def _internal_group_identity(request: Request) -> IdentityContext:
    # The host can reach a bridge backend through its loopback-published port;
    # that connection's socket peer is the actual host gateway, not 127.0.0.1.
    peer = None if request.client is None else request.client.host
    if peer not in {"127.0.0.1", "::1"} and (peer is None or peer != _default_gateway_peer()):
        raise ApiError(code="RESOURCE_NOT_FOUND", message="resource not found", status_code=404)
    context = require_session_identity(request)
    assert_statistics_group_permission(context)
    return context


@router.get(
    "/internal/v1/statistics/group",
    response_model=GroupStatistics,
    responses=RESPONSES,
    include_in_schema=False,
)
def internal_group_statistics(
    request: Request, context: Annotated[IdentityContext, Depends(_internal_group_identity)]
) -> GroupStatistics:
    return _group_statistics_response(request, context)


@router.get(
    "/internal/v1/statistics/group/resources",
    response_model=ResourcePage,
    responses=RESPONSES,
    include_in_schema=False,
)
def internal_group_resources(
    request: Request,
    query: Annotated[GroupResourceQuery, Query()],
    context: Annotated[IdentityContext, Depends(_internal_group_identity)],
) -> Response:
    return _group_resources_response(request, query, context)
