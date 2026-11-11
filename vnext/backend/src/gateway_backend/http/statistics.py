"""Bounded query presentation and ownership of the process-local export slot."""
from __future__ import annotations

import base64
import csv
import io
import json
import math
from collections import defaultdict
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from threading import BoundedSemaphore
from typing import Any

from fastapi import Request, Response
from pydantic import BaseModel
from starlette.types import Receive, Scope, Send

from gateway_backend.http.errors import ApiError
from gateway_backend.http.schemas.statistics import (
    CollectionHealth, BucketValue, ResourceBucket, ResourcePage, ResourceQuery, ResourceSeries, StatisticsPage, StatisticsQuery,
)
from gateway_backend.statistics.models import ResourceRecord
from gateway_backend.statistics.queries import ResourceRead, Role, StatisticsReadError, StatisticsReader

MAX_RESPONSE_BYTES = 32 * 1024 * 1024


@dataclass(frozen=True)
class StatisticsHttpDependencies:
    reader: StatisticsReader
    now: Callable[[], datetime] = lambda: datetime.now(UTC)
    dropped_count: Callable[[], int] = lambda: 0
    health: Callable[[], CollectionHealth] = lambda: CollectionHealth(enabled=True, quality="available")
    sample_interval_seconds: float = 1
    export_slot: BoundedSemaphore = field(default_factory=lambda: BoundedSemaphore(1))


def get_statistics_http(request: Request) -> StatisticsHttpDependencies:
    deps = getattr(request.app.state, 'statistics_http', None)
    if not isinstance(deps, StatisticsHttpDependencies):
        raise ApiError(code='STATISTICS_UNAVAILABLE', message='statistics unavailable', status_code=503)
    return deps


def query_error(exc: StatisticsReadError) -> ApiError:
    return ApiError(code='STATISTICS_UNAVAILABLE' if exc.reason == 'unavailable' else 'REQUEST_VALIDATION_FAILED',
        message='statistics unavailable' if exc.reason == 'unavailable' else 'narrow statistics query or select a claim',
        status_code=503 if exc.reason == 'unavailable' else 422, details={'reason': exc.reason})


def time_range(query: StatisticsQuery, now: datetime, *, resources: bool = False) -> tuple[int, int]:
    end = query.to or now
    if end <= datetime(1970, 1, 1, tzinfo=UTC):
        raise ApiError(code='REQUEST_VALIDATION_FAILED', message='invalid statistics time range', status_code=422)
    start = query.from_ or (end - timedelta(hours=1) if resources else end - timedelta(days=90))
    if start < datetime(1970, 1, 1, tzinfo=UTC) or not start < end or end - start > timedelta(hours=6 if resources else 90 * 24):
        raise ApiError(code='REQUEST_VALIDATION_FAILED', message='invalid statistics time range', status_code=422)
    return int(start.timestamp() * 1000000), int(end.timestamp() * 1000000)


class _ExportResponse(Response):
    def __init__(self, content: bytes, *, slot: BoundedSemaphore, media_type: str, headers: dict[str, str]) -> None:
        super().__init__(content=content, media_type=media_type, headers=headers)
        self.slot = slot

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        try:
            await super().__call__(scope, receive, send)
        finally:
            self.slot.release()


def _bytes(parts: Sequence[str] | Any) -> bytes:
    buffer = bytearray()
    for part in parts:
        encoded = part.encode('utf-8')
        if len(buffer) + len(encoded) > MAX_RESPONSE_BYTES:
            raise StatisticsReadError('budget_exceeded')
        buffer.extend(encoded)
    return bytes(buffer)


def _cell(value: object) -> object:
    if isinstance(value, (dict, list, tuple)):
        return json.dumps(value, ensure_ascii=False, separators=(',', ':'))
    if isinstance(value, str) and value.lstrip().startswith(('=', '+', '-', '@', '\t', '\r', '\n')):
        return "'" + value
    return value


def _csv(payload: dict[str, Any]) -> bytes:
    rows = payload.get('items', [payload])
    if not rows:
        return b''
    output = bytearray()
    columns = list(rows[0])
    for row in [None, *rows]:
        buffer = io.StringIO(newline='')
        writer = csv.writer(buffer)
        writer.writerow(columns if row is None else [_cell(row.get(column)) for column in columns])
        encoded = buffer.getvalue().encode('utf-8')
        if len(output) + len(encoded) > MAX_RESPONSE_BYTES:
            raise StatisticsReadError('budget_exceeded')
        output.extend(encoded)
    return bytes(output)


def respond(deps: StatisticsHttpDependencies, query: StatisticsQuery, prepare: Callable[[], BaseModel]) -> Response:
    acquired = query.is_export and deps.export_slot.acquire(blocking=False)
    if query.is_export and not acquired:
        raise ApiError(code='STATISTICS_EXPORT_BUSY', message='statistics export busy', status_code=429)
    handed_off = False
    try:
        model = prepare()
        payload = model.model_dump(mode='json')
        headers = {'X-Statistics-' + name.replace('_', '-'): str(payload[name]) for name in (
            'schema_version', 'generated_at_us', 'window_start_us', 'window_end_us', 'coverage_start_us', 'coverage_end_us',
            'next_cursor', 'quality', 'reason', 'units') if payload.get(name) is not None}
        content = _csv(payload) if query.format == 'csv' else _bytes(json.JSONEncoder(ensure_ascii=False, separators=(',', ':'), allow_nan=False).iterencode(payload))
        media = 'text/csv' if query.format == 'csv' else 'application/json'
        if acquired:
            headers['Content-Disposition'] = 'attachment; filename="statistics.' + query.format + '"'
            response = _ExportResponse(content, slot=deps.export_slot, media_type=media, headers=headers)
            handed_off = True
            return response
        return Response(content, media_type=media, headers=headers)
    except StatisticsReadError as exc:
        raise query_error(exc) from None
    finally:
        if acquired and not handed_off:
            deps.export_slot.release()


def page_metadata(items: Sequence[Any], start_us: int, end_us: int, now: datetime, timestamps: Sequence[int]) -> dict[str, Any]:
    partial = any(item.quality != 'available' for item in items)
    return dict(generated_at_us=int(now.timestamp() * 1000000), window_start_us=start_us, window_end_us=end_us,
        coverage_start_us=min(timestamps) if timestamps else None, coverage_end_us=max(timestamps) if timestamps else None,
        quality='unavailable' if not items else 'partial' if partial else 'available',
        reason='not_collected' if not items else next((item.reason for item in items if item.reason is not None), None))


def resource_page(data: ResourceRead, query: ResourceQuery, start_us: int, end_us: int, now: datetime, scope: str,
                  *, sample_interval_seconds: float = 1) -> ResourcePage:
    groups: dict[tuple[Role, str, str | None, int | None, int | None], list[ResourceRecord]] = defaultdict(list)
    for sample in data.samples:
        groups[(sample.role, sample.process_instance_id, sample.step_id, sample.attempt_count, sample.claim_version)].append(sample)
    if len(groups) > query.max_points:
        raise StatisticsReadError('budget_exceeded')
    quota = query.max_points // max(1, len(groups))
    width = max(1, math.ceil((end_us - start_us) / quota))
    series = []
    counters = ('cpu_time_us', 'read_bytes', 'write_bytes')
    fields = (*counters, 'rss_bytes', 'cgroup_bytes')
    for (role, process, step, attempt, claim), samples in groups.items():
        buckets: dict[int, dict[str, list[int]]] = {}
        previous: ResourceRecord | None = None
        reason = None
        for sample in samples:
            index = (sample.sampled_at_us - start_us) // width
            values = buckets.setdefault(index, {name: [] for name in fields})
            if sample.quality != 'available':
                reason = sample.reason or 'counter_unavailable'
            for name in fields:
                value = getattr(sample, name)
                if name in counters:
                    old = getattr(previous, name) if previous is not None else None
                    if previous is None or old is None or value is None:
                        value = None
                    elif value < old:
                        value, reason = None, 'counter_reset'
                    elif sample.sampled_at_us - previous.sampled_at_us > sample_interval_seconds * 2500000:
                        value, reason = None, 'not_collected'
                    else:
                        value -= old
                if value is not None:
                    values[name].append(value)
            previous = sample
        points = tuple(ResourceBucket(bucket_start_us=start_us + index * width, bucket_end_us=min(end_us, start_us + (index + 1) * width),
            **{name: BucketValue(avg=sum(values[name]) / len(values[name]) if values[name] else None,
                max=max(values[name]) if values[name] else None, count=len(values[name])) for name in fields}) for index, values in sorted(buckets.items()))
        series.append(ResourceSeries(role=role, process_instance_id=process, step_id=step, attempt_count=attempt, claim_version=claim,
            window_start_us=samples[0].sampled_at_us, window_end_us=samples[-1].sampled_at_us,
            bucket_width_us=width, points=points, quality='available' if reason is None else 'partial', reason=reason))
    series.sort(key=lambda item: (item.window_start_us, item.process_instance_id, item.claim_version or 0))
    if query.cursor:
        try:
            cursor = json.loads(base64.b64decode(query.cursor, altchars=b'-_', validate=True))
            if (not isinstance(cursor, list) or len(cursor) != 4 or cursor[0] != scope
                    or type(cursor[1]) is not int or type(cursor[2]) is not str or type(cursor[3]) is not int):
                raise ValueError
            series = [item for item in series if (item.window_start_us, item.process_instance_id, item.claim_version or 0) > tuple(cursor[1:])]
        except (ValueError, TypeError, UnicodeError, RecursionError):
            raise StatisticsReadError('invalid_cursor') from None
    retained = tuple(series[:query.effective_limit])
    next_cursor = None
    if len(series) > query.effective_limit:
        last = retained[-1]
        next_cursor = base64.urlsafe_b64encode(json.dumps([scope, last.window_start_us, last.process_instance_id, last.claim_version or 0]).encode()).decode()
    coverage = [timestamp for item in retained for timestamp in (item.window_start_us, item.window_end_us)]
    metadata = page_metadata(retained, start_us, end_us, now, coverage)
    return StatisticsPage[ResourceSeries](items=retained, next_cursor=next_cursor, **metadata)
