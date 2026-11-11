"""Authorized saved telemetry only. These GETs never collect or mutate data."""
from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query, Request, Response

from gateway_backend.domain.workspace.models import IdentityContext
from gateway_backend.http.auth import assert_statistics_group_permission, require_identity
from gateway_backend.http.dependencies import HistoryHttpDependencies, WorkspaceHttpDependencies, get_history_http, get_workspace_http
from gateway_backend.http.errors import ApiError
from gateway_backend.http.orchestration.operation_scope import assert_workspace_read_permission
from gateway_backend.http.routes.operations import get_operation_route
from gateway_backend.http.schemas.statistics import (
    CollectionHealth, CurrentProcess, ExecutionPage, GroupResourceQuery, GroupStatistics, GroupStorageItem,
    OperationResourceQuery, ResourcePage, StatisticsPage, StatisticsQuery, StoragePage, WritePage,
)
from gateway_backend.http.statistics import get_statistics_http, page_metadata, resource_page, respond, time_range
from gateway_backend.statistics.models import StorageRecord
from gateway_backend.statistics.queries import CollectionKind, ReadRequest, ResourceRequest

router = APIRouter(tags=['statistics'])

# CSV carries the same page metadata in headers; no server export file or query session.
RESPONSES: dict[int | str, dict[str, Any]] = {
    200: {'description': 'Finite saved statistics. CSV implies export. JSON/CSV share authorization and SQL budgets. '
            'Normal limit 100/500 max; export 1000/10000 max and 32MiB. Curves default 1h/max6h, max_points 600/2000 max; '
            'raw reads 50000 rows and 1s SQL budget. No cross-page snapshot. Counters are within-instance interval deltas; '
            'memory is sampled avg/max/count; gaps are not interpolated.',
        'content': {'text/csv': {'schema': {'type': 'string'}}},
        'headers': {name: {'schema': {'type': 'string'}, 'description': description} for name, description in {
            'X-Statistics-Next-Cursor': 'Next page cursor; absent when complete.',
            'X-Statistics-Schema-Version': 'Schema version 1.',
            'X-Statistics-Generated-At-Us': 'Response generation UTC microseconds.',
            'X-Statistics-Window-Start-Us': 'Requested inclusive UTC microseconds.',
            'X-Statistics-Window-End-Us': 'Requested exclusive UTC microseconds.',
            'X-Statistics-Coverage-Start-Us': 'First returned saved sample; absent for empty results.',
            'X-Statistics-Coverage-End-Us': 'Last returned saved sample; absent for empty results.',
            'X-Statistics-Quality': 'available, partial or unavailable.',
            'X-Statistics-Reason': 'Stable missing/partial reason, when known.',
            'X-Statistics-Units': 'Explicit byte/count/time units.',
            'Content-Disposition': 'Bounded attachment for all exports.',
        }.items()}},
    401: {'description': 'AUTHENTICATION_REQUIRED'},
    403: {'description': 'SCOPE_FORBIDDEN'},
    404: {'description': 'RESOURCE_NOT_FOUND'},
    422: {'description': 'REQUEST_VALIDATION_FAILED; narrow range or select claim_version on budget rejection.'},
    429: {'description': 'STATISTICS_EXPORT_BUSY; one preparation/send per backend, no queue.'},
    503: {'description': 'STATISTICS_UNAVAILABLE; disabled or unhealthy database.'},
}

WorkspaceDeps = Annotated[WorkspaceHttpDependencies, Depends(get_workspace_http)]
HistoryDeps = Annotated[HistoryHttpDependencies, Depends(get_history_http)]
Identity = Annotated[IdentityContext, Depends(require_identity)]


def _repository(repository_id: str, context: IdentityContext, deps: WorkspaceHttpDependencies) -> None:
    assert_workspace_read_permission(context)
    if deps.scope_resolution.resolve(context).repository_id != repository_id:
        raise ApiError(code='RESOURCE_NOT_FOUND', message='resource not found', status_code=404)


def _collection(kind: CollectionKind, owner: str, request: Request, query: StatisticsQuery) -> Response:
    deps = get_statistics_http(request)
    now = deps.now()
    start, end = time_range(query, now)

    def prepare() -> StatisticsPage[Any]:
        data = deps.reader.read(ReadRequest(kind=kind, owner_id=owner, start_us=start, end_us=end,
            limit=query.effective_limit, cursor=query.cursor))
        timestamps = [item.window_end_us if isinstance(item, StorageRecord) else item.recorded_at_us for item in data.items]
        model = StoragePage if kind.startswith('storage') else WritePage if kind == 'writes' else ExecutionPage
        return model.model_validate(dict(items=data.items, next_cursor=data.next_cursor, **page_metadata(data.items, start, end, now, timestamps)))

    return respond(deps, query, prepare)


@router.get('/v1/repositories/{repository_id}/statistics/storage', response_model=StoragePage, responses=RESPONSES)
def repository_storage(repository_id: str, request: Request, query: Annotated[StatisticsQuery, Query()], deps: WorkspaceDeps, context: Identity) -> Response:
    _repository(repository_id, context, deps)
    return _collection('storage', repository_id, request, query)


@router.get('/v1/repositories/{repository_id}/statistics/storage/history', response_model=StoragePage, responses=RESPONSES)
def repository_storage_history(repository_id: str, request: Request, query: Annotated[StatisticsQuery, Query()], deps: WorkspaceDeps, context: Identity) -> Response:
    _repository(repository_id, context, deps)
    return _collection('storage_history', repository_id, request, query)


@router.get('/v1/repositories/{repository_id}/statistics/writes', response_model=WritePage, responses=RESPONSES)
def repository_writes(repository_id: str, request: Request, query: Annotated[StatisticsQuery, Query()], deps: WorkspaceDeps, context: Identity) -> Response:
    _repository(repository_id, context, deps)
    return _collection('writes', repository_id, request, query)


@router.get('/v1/operations/{operation_id}/statistics/executions', response_model=ExecutionPage, responses=RESPONSES)
def operation_executions(operation_id: str, request: Request, query: Annotated[StatisticsQuery, Query()], deps: WorkspaceDeps, history_deps: HistoryDeps, context: Identity) -> Response:
    get_operation_route(operation_id, deps, history_deps, context)
    return _collection('executions', operation_id, request, query)


@router.get('/v1/operations/{operation_id}/statistics/resources', response_model=ResourcePage, responses=RESPONSES)
def operation_resources(operation_id: str, request: Request, query: Annotated[OperationResourceQuery, Query()], deps: WorkspaceDeps, history_deps: HistoryDeps, context: Identity) -> Response:
    get_operation_route(operation_id, deps, history_deps, context)
    stats = get_statistics_http(request)
    now = stats.now()
    start, end = time_range(query, now, resources=True)
    return respond(stats, query, lambda: resource_page(stats.reader.resources(ResourceRequest(start_us=start, end_us=end,
        operation_id=operation_id, step_id=query.step_id, attempt_count=query.attempt_count, claim_version=query.claim_version)),
        query, start, end, now, f'{operation_id}:{query.step_id}:{query.attempt_count}:{query.claim_version}',
        sample_interval_seconds=stats.sample_interval_seconds))


@router.get('/v1/statistics/group', response_model=GroupStatistics, responses={**RESPONSES,
    200: {'description': 'Bounded current group capacity, public overhead, recent process identities and collection health.'}})
def group_statistics(request: Request, context: Identity) -> GroupStatistics:
    assert_statistics_group_permission(context)
    stats = get_statistics_http(request)
    now = stats.now()
    start, end = time_range(StatisticsQuery(), now)
    from gateway_backend.http.statistics import query_error
    from gateway_backend.statistics.queries import StatisticsReadError
    try:
        data = stats.reader.group(start, end)
    except StatisticsReadError as exc:
        raise query_error(exc) from None
    # Group access never serializes repository, operation, table names or business fields.
    storage = tuple(GroupStorageItem.model_validate({key: value for key, value in record.model_dump().items()
        if key not in ('environment_id', 'group_id', 'repository_id', 'source_event_id')}) for record in data.storage)
    return GroupStatistics(environment_id=stats.reader.identity.environment_id, group_id=stats.reader.identity.group_id,
        generated_at_us=int(now.timestamp() * 1000000), storage=storage,
        current_instances=tuple(CurrentProcess(role=role, process_instance_id=instance) for role, instance in data.instances),
        health=CollectionHealth(enabled=True, dropped_count=stats.dropped_count(), quality='available'))


@router.get('/v1/statistics/group/resources', response_model=ResourcePage, responses=RESPONSES)
def group_resources(request: Request, query: Annotated[GroupResourceQuery, Query()], context: Identity) -> Response:
    assert_statistics_group_permission(context)
    stats = get_statistics_http(request)
    now = stats.now()
    start, end = time_range(query, now, resources=True)
    return respond(stats, query, lambda: resource_page(stats.reader.resources(ResourceRequest(start_us=start, end_us=end,
        role=query.role, process_instance_id=query.process_instance_id)), query, start, end, now,
        f'{query.role}:{query.process_instance_id}', sample_interval_seconds=stats.sample_interval_seconds))
