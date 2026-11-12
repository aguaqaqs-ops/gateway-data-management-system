"""Saved-only reads, scope authorization, finite queries and export lifetime."""
from __future__ import annotations

import asyncio
import csv
import io
from dataclasses import replace
from datetime import UTC, datetime
from collections.abc import Iterator
from pathlib import Path
from typing import Any, cast

from fastapi import FastAPI
from uuid import uuid4

import pytest
from gateway_backend.domain.workspace.errors import ScopeNotFound

from gateway_backend.http.schemas.statistics import StatisticsQuery
from gateway_backend.device_identity import device_route_key
from gateway_backend.http.statistics import StatisticsHttpDependencies, respond
from gateway_backend.infrastructure.statistics import queries
from gateway_backend.infrastructure.statistics.queries import SQLiteStatisticsReader
from gateway_backend.infrastructure.statistics.sqlite_store import SQLiteStatisticsStore
from gateway_backend.statistics.config import StatisticsConfig
from gateway_backend.statistics.models import ExecutionMetrics, ExecutionSummary, ResourceRecord, StatisticsIdentity, StorageRecord, TableMetric, WriteRecord
from gateway_backend.statistics.queries import ReadRequest, ResourceRequest, StatisticsReadError
from tests.support.http_workspace_harness import WorkspaceHttpTestEnvironment, create_workspace_http_environment
from tests.support.workspace_fixtures import make_identity
from tests.test_operation_http import _seed_preview_operation

pytestmark = pytest.mark.unit
IDENTITY = StatisticsIdentity(environment_id='e', group_id='g')
NOW = datetime(2024, 6, 1, 12, 0, tzinfo=UTC)
BASE = int(NOW.timestamp() * 1000000) - 10000000


@pytest.fixture
def store(tmp_path: Path) -> Iterator[SQLiteStatisticsStore]:
    store = SQLiteStatisticsStore(tmp_path / 'telemetry/db', IDENTITY, StatisticsConfig())
    store.open()
    try:
        yield store
    finally:
        store.close()


def _storage(event: str, **changes: object) -> StorageRecord:
    return StorageRecord.model_validate(dict(environment_id='e', group_id='g', repository_id='repo-1', service_owner='backend',
        category='canonical', source_event_id=event, window_end_us=BASE, generated_at_us=BASE, logical_bytes=0) | changes)


def _summary(claim: int = 1, **changes: object) -> ExecutionSummary:
    return ExecutionSummary.model_validate(dict(environment_id='e', group_id='g', operation_id='op', step_id='s', attempt_count=1,
        claim_version=claim, process_instance_id=f'p{claim}', worker_id='w', recorded_at_us=BASE,
        started_at_us=BASE, ended_at_us=BASE + 5000000) | changes)


def _resource(event: str, **changes: object) -> ResourceRecord:
    return ResourceRecord.model_validate(dict(environment_id='e', group_id='g', source_event_id=event,
        role='worker', process_instance_id='p1', operation_id='op', step_id='s', attempt_count=1, claim_version=1,
        sampled_at_us=BASE, cpu_time_us=100, rss_bytes=200, read_bytes=0) | changes)


def _reader(store: SQLiteStatisticsStore) -> SQLiteStatisticsReader:
    return SQLiteStatisticsReader(store.path, IDENTITY)


def _env(tmp_path: Path, store: SQLiteStatisticsStore) -> WorkspaceHttpTestEnvironment:
    env = create_workspace_http_environment(tmp_path, now=lambda: NOW, extra_sessions={
        'group': make_identity(permissions=frozenset({'statistics_read_group'})),
        'cross': make_identity(device_key='other-device'),
    })
    cast(FastAPI, env.client.app).state.statistics_http = StatisticsHttpDependencies(_reader(store), now=lambda: NOW)
    return env


def test_latest_and_keyset_pages_do_not_scan_old_history(store: SQLiteStatisticsStore, monkeypatch: pytest.MonkeyPatch) -> None:
    store.write_batch([_storage(str(index), window_end_us=BASE + index) for index in range(20)])
    reader = _reader(store)
    request = ReadRequest('storage_history', 'repo-1', BASE, BASE + 100, 3)
    first = reader.read(request)
    second = reader.read(replace(request, cursor=first.next_cursor))
    assert [item.source_event_id for item in first.items if isinstance(item, StorageRecord)] == ['0', '1', '2']
    assert [item.source_event_id for item in second.items if isinstance(item, StorageRecord)] == ['3', '4', '5']
    assert reader.read(replace(request, owner_id='other')).items == ()
    with pytest.raises(StatisticsReadError, match='invalid_cursor'):
        reader.read(replace(request, kind='writes', cursor=first.next_cursor))
    monkeypatch.setattr(queries, 'MAX_READ_ROWS', 5)
    current = reader.read(replace(request, kind='storage'))
    assert [item.source_event_id for item in current.items if isinstance(item, StorageRecord)] == ['19']


@pytest.mark.parametrize('budget', ['rows', 'bytes', 'time'])
def test_resource_read_has_one_total_budget(store: SQLiteStatisticsStore, monkeypatch: pytest.MonkeyPatch, budget: str) -> None:
    store.write_batch([_summary(), _resource('1'), _resource('2', sampled_at_us=BASE + 1000000)])
    if budget == 'rows':
        monkeypatch.setattr(queries, 'MAX_READ_ROWS', 2)
    elif budget == 'bytes':
        monkeypatch.setattr(queries, 'MAX_READ_BYTES', 20)
    else:
        monkeypatch.setattr(queries, 'SQL_SECONDS', -1)
    with pytest.raises(StatisticsReadError, match='budget_exceeded'):
        _reader(store).resources(ResourceRequest(BASE, BASE + 3000000, operation_id='op', step_id='s', attempt_count=1))
    # A finite failed read has closed its transaction, so writers can still complete.
    store.write_batch([_storage('after-budget')])


def test_claim_selection_is_finite_and_does_not_combine_attempts(store: SQLiteStatisticsStore) -> None:
    for batch in (range(1, 102),):
        store.write_batch([_summary(index) for index in batch])
    reader = _reader(store)
    request = ResourceRequest(BASE, BASE + 6000000, operation_id='op', step_id='s', attempt_count=1)
    with pytest.raises(StatisticsReadError, match='select_claim'):
        reader.resources(request)
    assert len(reader.resources(replace(request, claim_version=77)).windows) == 1
    assert reader.resources(replace(request, attempt_count=2)).windows == ()


def test_device_permission_mapping_and_missing_database_matrix(tmp_path: Path, store: SQLiteStatisticsStore) -> None:
    env = _env(tmp_path, store)
    url = '/v1/repositories/repo-1/statistics/storage'
    assert env.client.get(url).status_code == 401
    assert env.client.get(url, headers={**env.auth_headers(), 'Authorization': 'Bearer group'}).status_code == 403
    assert env.client.get(url.replace('repo-1', 'other'), headers=env.auth_headers()).status_code == 404
    env.scope_resolution.simulate_resolution_error = ScopeNotFound('provisioned mapping is disabled')
    assert env.client.get(url, headers=env.auth_headers()).status_code == 404
    env.scope_resolution.simulate_resolution_error = None
    empty = env.client.get(url, headers=env.auth_headers())
    assert empty.status_code == 200 and empty.json()['reason'] == 'not_collected'
    assert empty.json()['coverage_start_us'] is None
    cast(FastAPI, env.client.app).state.statistics_http = StatisticsHttpDependencies(SQLiteStatisticsReader(tmp_path / 'absent', IDENTITY))
    response = env.client.get(url, headers=env.auth_headers())
    assert response.status_code == 503 and str(tmp_path) not in response.text
    assert not (tmp_path / 'absent').exists()


@pytest.mark.parametrize('params', [dict(limit=501), dict(limit=10001, export='true'), dict(cursor='bad'),
    {'from': '2024-06-02T00:00:00Z'}, {'to': '0001-01-01T00:00:00Z'},
    {'to': '2023-01-01T00:00:00Z', 'from': '2023-05-01T00:00:00Z'}])
def test_http_rejects_invalid_or_unbounded_queries(tmp_path: Path, store: SQLiteStatisticsStore, params: dict[str, Any]) -> None:
    env = _env(tmp_path, store)
    response = env.client.get('/v1/repositories/repo-1/statistics/storage/history', headers=env.auth_headers(), params=params)
    assert response.status_code == 422


def test_http_export_pages_and_signed_csv_values(tmp_path: Path, store: SQLiteStatisticsStore) -> None:
    env = _env(tmp_path, store)
    store.write_batch([_storage('a'), _storage('b', window_end_us=BASE + 1), WriteRecord(environment_id='e', group_id='g',
        observation_id='write', repository_id='repo-1', rs_operation_id=uuid4(), process_instance_id='p', recorded_at_us=BASE,
        logical_net_change_bytes=-5, observed_outcome='succeeded')])
    url = '/v1/repositories/repo-1/statistics/storage/history'
    first = env.client.get(url, headers=env.auth_headers(), params={'limit': 1, 'export': 'true'})
    assert first.status_code == 200
    cursor = first.headers['X-Statistics-Next-Cursor']
    assert first.json()['next_cursor'] == cursor
    second = env.client.get(url, headers=env.auth_headers(), params={'limit': 1, 'cursor': cursor})
    assert second.status_code == 200 and second.json()['items'][0]['source_event_id'] == 'b'
    csv_response = env.client.get('/v1/repositories/repo-1/statistics/writes', headers=env.auth_headers(), params={'format': 'csv'})
    assert csv_response.status_code == 200 and 'attachment' in csv_response.headers['content-disposition']
    row = list(csv.DictReader(io.StringIO(csv_response.text)))[0]
    assert row['logical_net_change_bytes'] == '-5'
    assert str(store.path) not in csv_response.text


def test_operation_curves_segment_claim_process_and_bound_all_points(tmp_path: Path, store: SQLiteStatisticsStore) -> None:
    env = _env(tmp_path, store)
    _, operation = _seed_preview_operation(env.client, env.auth_headers())
    op = operation['operation_id']
    records: list[ExecutionSummary | ResourceRecord] = []
    for claim in (1, 2):
        records.append(_summary(claim, operation_id=op))
        for index, cpu in enumerate((100, 150, 20, 40)):
            records.append(_resource(f'{claim}-{index}', operation_id=op, claim_version=claim, process_instance_id=f'p{claim}',
                sampled_at_us=BASE + index * 1000000, cpu_time_us=cpu))
    # An invalid process association must not be connected to the valid execution window.
    records.append(_resource('wrong-process', operation_id=op, process_instance_id='wrong', cpu_time_us=999999))
    store.write_batch(records)
    url = f'/v1/operations/{op}/statistics/resources'
    params = {'step_id': 's', 'attempt_count': 1, 'max_points': 2}
    response = env.client.get(url, headers=env.auth_headers(), params=params)
    assert response.status_code == 200, response.text
    items = response.json()['items']
    assert [item['claim_version'] for item in items] == [1, 2]
    assert sum(len(item['points']) for item in items) <= 2
    assert all(item['reason'] == 'counter_reset' for item in items)
    assert all(item['points'][0]['cpu_time_us'] == {'avg': 35.0, 'max': 50, 'count': 2} for item in items)
    assert env.client.get(url, headers=env.auth_headers(), params={'step_id': 's', 'attempt_count': 2}).json()['items'] == []
    assert env.client.get(url, headers={**env.auth_headers(), 'Authorization': 'Bearer group'}, params=params).status_code == 403
    assert env.client.get(url, headers={'Authorization': 'Bearer cross',
        'X-Gateway-Device-Key': device_route_key('other-device')}, params=params).status_code == 404
    executions = env.client.get(f'/v1/operations/{op}/statistics/executions', headers=env.auth_headers())
    assert executions.status_code == 200 and len(executions.json()['items']) == 2


def test_group_is_separate_and_never_contains_device_fields(tmp_path: Path, store: SQLiteStatisticsStore) -> None:
    env = _env(tmp_path, store)
    store.write_batch([_storage('device'), _storage('public', repository_id=None, category='public_unknown'),
        _storage('fs-rs', repository_id=None, category='filesystem', filesystem_id='disk', logical_bytes=None, available_bytes=10, service_owner='repository_service'),
        _storage('fs-be', repository_id=None, category='filesystem', filesystem_id='disk', logical_bytes=None, available_bytes=12),
        _resource('device-resource'), _resource('shared', role='backend', process_instance_id='http', operation_id=None, step_id=None, claim_version=None, attempt_count=None)])
    assert env.client.get('/v1/statistics/group', headers=env.auth_headers()).status_code == 403
    headers = {**env.auth_headers(), 'Authorization': 'Bearer group'}
    response = env.client.get('/v1/statistics/group', headers=headers)
    assert response.status_code == 200
    storage = response.json()['storage']
    assert len(storage) == 2 and sum(item['available_bytes'] or 0 for item in storage) == 10
    assert not any(name in response.text for name in ('repository_id', 'operation_id', 'table_name', str(store.path)))
    curve = env.client.get('/v1/statistics/group/resources', headers=headers, params={'role': 'backend', 'process_instance_id': 'http'})
    assert curve.status_code == 200 and len(curve.json()['items']) == 1
    busy = env.client.get('/v1/statistics/group/resources', headers=headers, params={'role': 'worker', 'process_instance_id': 'p1'})
    assert busy.status_code == 200 and len(busy.json()['items']) == 1
    assert busy.json()['items'][0]['step_id'] is None
    assert busy.json()['items'][0]['claim_version'] is None
    assert busy.json()['items'][0]['attempt_count'] is None
    assert 'operation_id' not in busy.text and 'repo-1' not in busy.text


@pytest.mark.parametrize('failure', ['normal', 'prepare', 'send', 'cancel', 'bytes'])
def test_export_slot_rejects_busy_and_releases_for_every_exit(store: SQLiteStatisticsStore, monkeypatch: pytest.MonkeyPatch, failure: str) -> None:
    from gateway_backend.http import statistics as presentation
    from gateway_backend.http.errors import ApiError
    deps = StatisticsHttpDependencies(_reader(store))
    query = StatisticsQuery(export=True)
    summary = _summary(metrics=ExecutionMetrics(tables=(TableMetric(table_name='=formula'),)))
    assert deps.export_slot.acquire(blocking=False)
    with pytest.raises(ApiError) as busy:
        respond(deps, query, lambda: summary)
    assert busy.value.code == 'STATISTICS_EXPORT_BUSY'
    deps.export_slot.release()
    def prepare() -> ExecutionSummary:
        if failure == 'prepare':
            raise StatisticsReadError('unavailable')
        return summary
    if failure == 'bytes':
        monkeypatch.setattr(presentation, 'MAX_RESPONSE_BYTES', 10)
    async def run() -> None:
        async def send(message: Any) -> None:
            assert not deps.export_slot.acquire(blocking=False)
            if failure == 'send':
                raise RuntimeError('disconnected')
            if failure == 'cancel':
                raise asyncio.CancelledError
        async def receive() -> Any:
            return {'type': 'http.disconnect'}
        response = respond(deps, query, prepare)
        await response({'type': 'http'}, receive, send)
    if failure == 'normal':
        asyncio.run(run())
    else:
        with pytest.raises((ApiError, RuntimeError, asyncio.CancelledError)):
            asyncio.run(run())
    assert deps.export_slot.acquire(blocking=False)
    deps.export_slot.release()


def test_openapi_documents_seven_read_routes_and_export_headers(tmp_path: Path, store: SQLiteStatisticsStore) -> None:
    schema = _env(tmp_path, store).client.get('/openapi.json').json()
    paths = {path: value for path, value in schema['paths'].items()
        if path.startswith('/v1/') and '/statistics/' in path}
    assert len(paths) == 7
    assert all(set(value) == {'get'} for value in paths.values())
    for path, value in paths.items():
        if path == '/v1/statistics/group':
            continue
        assert {'from', 'to', 'cursor', 'export', 'format', 'limit'} <= {item['name'] for item in value['get']['parameters']}
        assert 'text/csv' in value['get']['responses']['200']['content']
        assert 'X-Statistics-Next-Cursor' in value['get']['responses']['200']['headers']


def test_history_statistics_use_history_acceptance_permission(tmp_path: Path, store: SQLiteStatisticsStore) -> None:
    from gateway_backend.application.history.contracts import PERMISSION_READ_PROJECT_HISTORY
    from tests.support.history_compare_job_harness import seed_archived_baseline_node
    from tests.support.http_workspace_harness import BASELINE_HEAD
    env = create_workspace_http_environment(tmp_path, identity=make_identity(permissions=frozenset({PERMISSION_READ_PROJECT_HISTORY})),
        extra_sessions={'workspace': make_identity(permissions=frozenset({'workspace_read'})),
                        'other-history': make_identity(device_key='other', permissions=frozenset({PERMISSION_READ_PROJECT_HISTORY}))})
    cast(FastAPI, env.client.app).state.statistics_http = StatisticsHttpDependencies(_reader(store), now=lambda: NOW)
    seed_archived_baseline_node(env.db_path, node_id='bn-statistics', commit_id='commit-statistics', created_at_us=2)
    accepted = env.client.post('/v1/history-compares', headers=env.auth_headers(idempotency_key='statistics-history'), json={'nodes': [
        {'ref_kind': 'baseline_node', 'ref_id': BASELINE_HEAD.business_baseline_node_id},
        {'ref_kind': 'baseline_node', 'ref_id': 'bn-statistics'}]})
    assert accepted.status_code == 202
    operation_id = accepted.json()['operation_id']
    store.write_batch([_summary(operation_id=operation_id)])
    executions = f'/v1/operations/{operation_id}/statistics/executions'
    resources = f'/v1/operations/{operation_id}/statistics/resources'
    for url, params in ((executions, {}), (resources, {'step_id': 's', 'attempt_count': 1})):
        assert env.client.get(url, headers=env.auth_headers(), params=params).status_code == 200
        assert env.client.get(url, headers={**env.auth_headers(), 'Authorization': 'Bearer workspace'}, params=params).status_code == 403
        assert env.client.get(url, headers={'Authorization': 'Bearer other-history',
            'X-Gateway-Device-Key': device_route_key('other')}, params=params).status_code == 404


def test_service_curve_respects_configured_interval_and_page_coverage(tmp_path: Path, store: SQLiteStatisticsStore) -> None:
    env = _env(tmp_path, store)
    deps = StatisticsHttpDependencies(_reader(store), now=lambda: NOW, sample_interval_seconds=5)
    cast(FastAPI, env.client.app).state.statistics_http = deps
    store.write_batch([_resource('service-a', role='backend', process_instance_id='http', sampled_at_us=BASE,
        operation_id=None, step_id=None, attempt_count=None, claim_version=None),
        _resource('service-b', role='backend', process_instance_id='http', sampled_at_us=BASE + 5000000, cpu_time_us=200,
        operation_id=None, step_id=None, attempt_count=None, claim_version=None)])
    response = env.client.get('/v1/statistics/group/resources', headers={**env.auth_headers(), 'Authorization': 'Bearer group'},
        params={'role': 'backend', 'process_instance_id': 'http', 'max_points': 1})
    assert response.status_code == 200
    item = response.json()['items'][0]
    assert item['points'][0]['cpu_time_us'] == {'avg': 100.0, 'max': 100, 'count': 1}
    assert item['quality'] == 'available'
    assert response.json()['coverage_start_us'] == BASE
    assert response.json()['coverage_end_us'] == BASE + 5000000


def test_group_keeps_worker_generations_and_bounds_recent_instances(store: SQLiteStatisticsStore) -> None:
    store.write_batch([_resource('old', process_instance_id='worker-old'),
        _resource('same', process_instance_id='worker-old', sampled_at_us=BASE + 1),
        _resource('peer', process_instance_id='worker-peer', sampled_at_us=BASE + 2),
        _resource('restart', process_instance_id='worker-restarted', sampled_at_us=BASE + 3)])
    data = _reader(store).group(BASE, BASE + 1000)
    assert data.instances == (('worker', 'worker-restarted'), ('worker', 'worker-peer'), ('worker', 'worker-old'))
    assert not data.instances_truncated
    store.write_batch([_resource(f'extra-{i}', process_instance_id=f'p{i:03}', sampled_at_us=BASE + 4) for i in range(101)])
    data = _reader(store).group(BASE, BASE + 1000)
    assert len(data.instances) == 100 and data.instances_truncated
    assert data.instances[0] == ('worker', 'p000')
    assert data.instances[-1] == ('worker', 'p099')
