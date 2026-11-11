"""Finite SQLite read transactions. Never opens roots or asks collectors to run."""
from __future__ import annotations

import base64
import hashlib
import json
import sqlite3
import time
from collections.abc import Callable, Iterator, Sequence
from contextlib import contextmanager
from pathlib import Path
from typing import Literal, TypeVar, cast
from gateway_repository_contracts.statistics import Role

from pydantic import BaseModel, ValidationError

from gateway_backend.statistics.models import ExecutionSummary, ResourceRecord, StatisticsIdentity, StorageRecord, WriteRecord
from gateway_backend.statistics.queries import GroupRead, ReadPage, ReadRequest, ResourceRead, ResourceRequest, StatisticsReadError

MAX_READ_ROWS = 50000
MAX_READ_BYTES = 32 * 1024 * 1024
SQL_SECONDS = 1.0
T = TypeVar('T', bound=BaseModel)


class _Read:
    def __init__(self, connection: sqlite3.Connection, deadline: float) -> None:
        self.connection, self.deadline = connection, deadline
        self.rows = self.bytes = 0

    def select(self, sql: str, parameters: Sequence[object] = ()) -> list[dict[str, object]]:
        result: list[dict[str, object]] = []
        for row in self.connection.execute(sql, parameters):
            self.rows += 1
            self.bytes += sum(len(value.encode()) if isinstance(value, str) else 16 for value in row)
            if self.rows > MAX_READ_ROWS or self.bytes > MAX_READ_BYTES or time.monotonic() > self.deadline:
                raise StatisticsReadError('budget_exceeded')
            result.append(dict(row))
        return result


def _decode(model: type[T], rows: list[dict[str, object]]) -> tuple[T, ...]:
    result: list[T] = []
    for raw in rows:
        row = {key: value for key, value in raw.items() if key != 'id'}
        if 'metrics_json' in row:
            metrics = row.pop('metrics_json')
            row['metrics'] = None if metrics is None else json.loads(str(metrics))
        result.append(model.model_validate(row))
    return tuple(result)


def _scope(request: ReadRequest) -> str:
    return hashlib.sha256(f'{request.kind}:{request.owner_id}'.encode()).hexdigest()[:16]


def _cursor(request: ReadRequest, key: tuple[object, ...]) -> str:
    return base64.urlsafe_b64encode(json.dumps([_scope(request), *key], separators=(',', ':')).encode()).decode()


def _after(request: ReadRequest, columns: tuple[str, ...], types: tuple[type, ...]) -> tuple[str, tuple[object, ...]]:
    if request.cursor is None:
        return '', ()
    try:
        value = json.loads(base64.b64decode(request.cursor, altchars=b'-_', validate=True))
        if (type(value) is not list or len(value) != len(columns) + 1 or value[0] != _scope(request)
                or any(type(item) is not expected for item, expected in zip(value[1:], types, strict=True))):
            raise ValueError
        # Time and SQLite integer IDs must stay in the supported counter domain.
        if any(type(item) is int and not 0 <= item <= 2**63 - 1 for item in value[1:]):
            raise ValueError
        return f' AND ({",".join(columns)}) > ({",".join("?" for _ in columns)})', tuple(value[1:])
    except (ValueError, TypeError, UnicodeError, RecursionError):
        raise StatisticsReadError('invalid_cursor') from None


class SQLiteStatisticsReader:
    def __init__(self, path: Path, identity: StatisticsIdentity, *, available: Callable[[], bool] = lambda: True) -> None:
        self.path, self.identity, self.available = path, identity, available

    @contextmanager
    def _transaction(self) -> Iterator[_Read]:
        connection: sqlite3.Connection | None = None
        try:
            if not self.available():
                raise StatisticsReadError('unavailable')
            deadline = time.monotonic() + SQL_SECONDS
            connection = sqlite3.connect(self.path.as_uri() + '?mode=ro', uri=True, timeout=0.05)
            connection.row_factory = sqlite3.Row
            connection.execute('PRAGMA query_only=ON')
            connection.set_progress_handler(lambda: int(time.monotonic() > deadline), 1000)
            if connection.execute('PRAGMA user_version').fetchone()[0] != 1:
                raise StatisticsReadError('unavailable')
            connection.execute('BEGIN')
            yield _Read(connection, deadline)
        except (sqlite3.Error, OSError, ValidationError, json.JSONDecodeError) as exc:
            reason: Literal['budget_exceeded', 'unavailable'] = 'budget_exceeded' if isinstance(exc, sqlite3.OperationalError) and str(exc) == 'interrupted' else 'unavailable'
            raise StatisticsReadError(reason) from None
        finally:
            if connection is not None:
                connection.close()

    @property
    def _identity(self) -> tuple[str, str]:
        return self.identity.environment_id, self.identity.group_id

    def read(self, request: ReadRequest) -> ReadPage:
        kind = request.kind
        keys: tuple[str, ...]
        types: tuple[type, ...]
        model: type[StorageRecord] | type[WriteRecord] | type[ExecutionSummary]
        if kind in ('storage', 'storage_history'):
            table, timestamp, keys, types = 'storage_observations', 'window_end_us', ('id',), (int, int)
            owner, model = 'repository_id', StorageRecord
        elif kind == 'writes':
            table, timestamp, keys, types = 'write_observations', 'recorded_at_us', ('observation_id',), (int, str)
            owner, model = 'repository_id', WriteRecord
        else:
            table, timestamp, keys, types = 'execution_summaries', 'recorded_at_us', ('step_id', 'claim_version'), (int, str, int)
            owner, model = 'operation_id', ExecutionSummary
        columns = (timestamp, *keys)
        after, cursor_values = _after(request, columns, types)
        predicates = f'environment_id=? AND group_id=? AND {owner}=? AND {timestamp}>=? AND {timestamp}<?'
        parameters = (*self._identity, request.owner_id, request.start_us, request.end_us)
        with self._transaction() as query:
            if kind == 'storage':
                rows = []
                for service in ('backend', 'repository_service'):
                    for category in ('repository', 'durable', 'canonical', 'comparison', 'export', 'scratch', 'metadata', 'public_unknown'):
                        rows.extend(query.select(f'SELECT * FROM {table} WHERE {predicates} AND service_owner=? AND category=? AND filesystem_id IS NULL'
                            f' ORDER BY {timestamp} DESC,id DESC LIMIT 1', (*parameters, service, category)))
                rows.sort(key=lambda row: (row[timestamp], row['id']))
                if cursor_values:
                    rows = [row for row in rows if (row[timestamp], row['id']) > cursor_values]
                rows = rows[:request.limit + 1]
            else:
                rows = query.select(f'SELECT * FROM {table} WHERE {predicates}{after} ORDER BY {",".join(columns)} LIMIT ?',
                                    (*parameters, *cursor_values, request.limit + 1))
            next_cursor = _cursor(request, tuple(rows[request.limit - 1][column] for column in columns)) if len(rows) > request.limit else None
            items = _decode(model, rows[:request.limit])
        return ReadPage(items=items, next_cursor=next_cursor)

    def resources(self, request: ResourceRequest) -> ResourceRead:
        with self._transaction() as query:
            windows: tuple[ExecutionSummary, ...] = ()
            if request.operation_id is not None:
                clause = '' if request.claim_version is None else ' AND claim_version=?'
                params = () if request.claim_version is None else (request.claim_version,)
                rows = query.select('SELECT * FROM execution_summaries WHERE environment_id=? AND group_id=? AND operation_id=? AND step_id=? AND attempt_count=?'
                                    + clause + ' ORDER BY claim_version LIMIT 101', (*self._identity, request.operation_id, request.step_id, request.attempt_count, *params))
                if len(rows) > 100:
                    raise StatisticsReadError('select_claim')
                windows = _decode(ExecutionSummary, rows)
                samples = []
                for window in windows:
                    if window.started_at_us is None:
                        continue
                    samples.extend(query.select('SELECT * FROM resource_samples WHERE environment_id=? AND group_id=? AND operation_id=? AND step_id=? AND claim_version=?'
                        ' AND process_instance_id=? AND role=\'worker\' AND sampled_at_us>=? AND sampled_at_us<? ORDER BY sampled_at_us,id LIMIT ?',
                        (*self._identity, request.operation_id, request.step_id, window.claim_version, window.process_instance_id,
                         max(request.start_us, window.started_at_us), min(request.end_us, window.ended_at_us + 1 if window.ended_at_us is not None else request.end_us), MAX_READ_ROWS + 1)))
            else:
                samples = query.select('SELECT * FROM resource_samples WHERE environment_id=? AND group_id=? AND role=? AND process_instance_id=?'
                    ' AND sampled_at_us>=? AND sampled_at_us<? ORDER BY sampled_at_us,id LIMIT ?',
                    (*self._identity, request.role, request.process_instance_id, request.start_us, request.end_us, MAX_READ_ROWS + 1))
                # Group permission grants a service curve, never the business association.
                for sample in samples:
                    for key in ('operation_id', 'step_id', 'attempt_count', 'claim_version'):
                        sample[key] = None
            records = _decode(ResourceRecord, samples)
        return ResourceRead(samples=records, windows=windows)

    def group(self, start_us: int, end_us: int) -> GroupRead:
        with self._transaction() as query:
            scopes = query.select('SELECT DISTINCT category,service_owner,filesystem_id FROM storage_observations WHERE environment_id=? AND group_id=? AND repository_id IS NULL LIMIT 501', self._identity)
            if len(scopes) > 500:
                raise StatisticsReadError('budget_exceeded')
            rows = []
            for scope in scopes:
                rows.extend(query.select('SELECT * FROM storage_observations WHERE environment_id=? AND group_id=? AND repository_id IS NULL'
                    ' AND category=? AND service_owner=? AND filesystem_id IS ? AND window_end_us>=? AND window_end_us<?'
                    ' ORDER BY window_end_us DESC,id DESC LIMIT 1',
                    (*self._identity, scope['category'], scope['service_owner'], scope['filesystem_id'], start_us, end_us)))
            rows.sort(key=lambda row: (row['window_end_us'], row['service_owner'], row['id']))
            latest: dict[tuple[object, ...], dict[str, object]] = {}
            for row in rows:
                # A configured filesystem identity is counted once across services.
                key = ('filesystem', row['filesystem_id']) if row['category'] == 'filesystem' else (row['service_owner'], row['category'])
                latest[key] = row
            instance_rows = query.select(
                'SELECT role,process_instance_id,MAX(sampled_at_us) AS latest FROM resource_samples'
                ' WHERE environment_id=? AND group_id=? AND sampled_at_us>=? AND sampled_at_us<?'
                ' GROUP BY role,process_instance_id ORDER BY latest DESC,role,process_instance_id LIMIT 101',
                (*self._identity, start_us, end_us))
            instances = tuple((cast(Role, row['role']), str(row['process_instance_id'])) for row in instance_rows[:100])
            storage = _decode(StorageRecord, list(latest.values()))
        return GroupRead(storage=storage, instances=instances, instances_truncated=len(instance_rows) > 100)
