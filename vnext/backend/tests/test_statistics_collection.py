"""Finite disposable storage and scalar collection behavior; no Dolt fixture."""
from __future__ import annotations

import dataclasses
import sqlite3
from pathlib import Path

import pytest

from gateway_backend.infrastructure.statistics.collection import BufferedTelemetrySink, bounded_metrics
from gateway_backend.infrastructure.statistics.sampling import ProcessSampler, counter_delta
from gateway_backend.infrastructure.statistics.sqlite_store import SQLiteStatisticsStore, StatisticsUnavailable
from gateway_backend.statistics.config import StatisticsConfig
from gateway_backend.statistics.metrics import (
    Metrics, cache_hit, cache_lookup, duration, input_shape, ordered_input_table, pair_table, pair_totals, set_metrics, timed,
)
from gateway_backend.statistics.models import ExecutionSummary, ResourceRecord, StatisticsIdentity
from tests.test_operation_worker_scheduler import _active_records
from gateway_backend.operations.worker import ClaimedWork, ExecutorAcknowledgment

IDENTITY = StatisticsIdentity(environment_id='e', group_id='g')


def _summary(**changes: object) -> ExecutionSummary:
    return ExecutionSummary.model_validate({**dict(environment_id='e', group_id='g', operation_id='op',
        step_id='s', claim_version=3, attempt_count=1, process_instance_id='p', worker_id='w',
        recorded_at_us=100), **changes})


def _resource(**changes: object) -> ResourceRecord:
    fields: dict[str, object] = dict(environment_id='e', group_id='g', role='worker', process_instance_id='p',
        source_event_id='event', sampled_at_us=100, cpu_time_us=0, read_bytes=0, write_bytes=0)
    return ResourceRecord.model_validate({**fields, **changes})


def test_sqlite_missing_begin_merge_distinct_claims_and_retention(tmp_path: Path) -> None:
    store = SQLiteStatisticsStore(tmp_path / 'telemetry/db', IDENTITY, StatisticsConfig())
    store.open()
    try:
        store.write_batch([_summary(ended_at_us=200, quality='partial'),
                           _summary(started_at_us=50),
                           _summary(claim_version=4, ended_at_us=250)])
        assert store.connection is not None
        rows = store.connection.execute('SELECT claim_version,started_at_us,ended_at_us,recorded_at_us FROM execution_summaries ORDER BY claim_version').fetchall()
        assert rows == [(3, 50, 200, 100), (4, None, 250, 100)]
        store.write_batch([_summary(ended_at_us=200, recorded_at_us=999)])
        assert store.connection.execute('SELECT recorded_at_us FROM execution_summaries WHERE claim_version=3').fetchone() == (100,)
        store.maintain(91 * 86400 * 1000000)
        assert store.connection.execute('SELECT count(*) FROM execution_summaries').fetchone() == (0,)
    finally:
        store.close()


@pytest.mark.parametrize('fault', ['schema', 'identity', 'corrupt', 'shrunk_budget'])
def test_sqlite_rejects_existing_invalid_database_without_rebuilding(tmp_path: Path, fault: str) -> None:
    path = tmp_path / 'db'
    store = SQLiteStatisticsStore(path, IDENTITY, StatisticsConfig())
    store.open()
    store.write_batch([_summary()])
    store.close()
    if fault == 'corrupt':
        path.write_bytes(b'not a SQLite database')
    else:
        with sqlite3.connect(path) as db:
            if fault == 'schema':
                db.execute('CREATE TABLE unexpected(x)')
            elif fault == 'identity':
                db.execute("UPDATE execution_summaries SET group_id='other'")
            else:
                # A valid large data page count cannot be silently accepted on budget shrink.
                db.execute('CREATE TABLE padding(x)')
                db.execute('INSERT INTO padding VALUES (?)', (b'x' * 1024 * 1024,))
                db.execute('DROP TABLE padding')
    original = path.read_bytes()
    config = StatisticsConfig(total_budget_bytes=1024 * 1024) if fault == 'shrunk_budget' else StatisticsConfig()
    with pytest.raises((StatisticsUnavailable, sqlite3.DatabaseError)):
        SQLiteStatisticsStore(path, IDENTITY, config).open()
    assert path.read_bytes() == original


def test_queue_is_nonblocking_and_bounded_by_items_and_bytes(tmp_path: Path) -> None:
    config = StatisticsConfig(queue_max_items=2, write_batch_items=2, queue_max_bytes=32768, write_batch_bytes=32768)
    sink = BufferedTelemetrySink(SQLiteStatisticsStore(tmp_path / 'db', IDENTITY, config), IDENTITY, config)
    assert sink.offer(_resource())
    assert sink.offer(_resource(source_event_id='second'))
    assert not sink.offer(_resource(source_event_id='third'))
    assert sink.health.dropped == 1
    sink._lock.acquire()
    try:
        assert not sink.offer(_resource())
    finally:
        sink._lock.release()
    assert len(sink._take_batch()) == 2
    assert sink.health.dropped == 2


def test_execution_keeps_claim_version_and_does_not_invent_short_window_counters(tmp_path: Path) -> None:
    config = StatisticsConfig()
    sink = BufferedTelemetrySink(SQLiteStatisticsStore(tmp_path / 'db', IDENTITY, config), IDENTITY, config)
    operation, step = _active_records()
    work = ClaimedWork(operation, step, lambda *_: ExecutorAcknowledgment.PUBLISHED)
    for claim in (step.optimistic_version, step.optimistic_version + 3):
        claimed = dataclasses.replace(work, step=dataclasses.replace(step, optimistic_version=claim))
        sink.begin_execution(claimed)
        duration('parse', 0)
        sink.end_execution(claimed)
    records = sink._take_batch()
    ends = [record for record in records if isinstance(record, ExecutionSummary) and record.ended_at_us is not None]
    assert [record.claim_version for record in ends] == [2, 5]
    assert all(record.attempt_count == 1 and record.cpu_time_us is None and record.observed_outcome == 'unknown' for record in ends)
    assert ends[0].metrics is not None
    assert ends[0].metrics.stage_duration_ms.parse == 0


def test_metrics_preserve_zero_missing_pair_identity_and_byte_truncation() -> None:
    metrics = Metrics()
    set_metrics(metrics)
    try:
        input_shape('current', table_count=2, total_rows=3, max_table_rows=2)
        input_shape('current', table_count=2, total_rows=3, max_table_rows=2)
        cache_lookup('canonical')
        cache_hit('canonical')
        cache_lookup('comparison')
        pair_totals(changed_tables=1, changed_rows=0)
        for pair in ('a', 'b'):
            for index in range(80):
                pair_table(pair, f'{index}' + '表' * 80, 'DETAILED', 0, 0, 0)
        @timed('parse')
        def failing() -> None:
            raise ValueError('parse failed')
        with pytest.raises(ValueError, match='parse failed'):
            failing()
    finally:
        set_metrics(None)
    result = bounded_metrics(metrics)
    assert result.input_shape.total_rows == 3
    assert result.input_shape.changed_rows == 0
    assert result.input_shape.sql_bytes is None
    assert result.cache_hits.canonical == 1 and result.cache_hits.comparison == 0
    assert result.cache_hits.snapshot_export is None
    assert result.tables_total == 160 and result.tables_truncated
    assert len(result.model_dump_json().encode()) <= 12288
    assert result.stage_duration_ms.parse is not None and result.stage_duration_ms.bundle is None


@pytest.mark.parametrize('changes,expected,reset', [
    ({'sampled_at_us': 200, 'cpu_time_us': 0}, 0, False),
    ({'sampled_at_us': 200, 'cpu_time_us': 12}, 12, False),
    ({'sampled_at_us': 200, 'cpu_time_us': None}, None, False),
    ({'sampled_at_us': 200, 'process_instance_id': 'new'}, None, True),
])
def test_counter_delta_never_crosses_process_instance(changes: dict[str, object], expected: int | None, reset: bool) -> None:
    assert counter_delta(_resource(), _resource(**changes), 'cpu_time_us') == (expected, reset)
    assert counter_delta(_resource(cpu_time_us=10), _resource(sampled_at_us=200, cpu_time_us=1), 'cpu_time_us') == (None, True)


def test_proc_sampling_is_bounded_missing_and_uses_current_rss(tmp_path: Path) -> None:
    proc = tmp_path / 'proc/self'
    proc.mkdir(parents=True)
    fields = ['0'] * 22
    fields[11], fields[12], fields[21] = '2', '3', '7'
    (proc / 'stat').write_text('123 (a process) ' + ' '.join(fields))
    (proc / 'io').write_text('read_bytes: 12\nwrite_bytes: 34\n')
    (proc / 'cgroup').write_text('0::/service\n')
    (tmp_path / 'cgroup/service').mkdir(parents=True)
    (tmp_path / 'cgroup/service/memory.current').write_text('456')
    sampler = ProcessSampler(IDENTITY, 'worker', 'p', proc_root=tmp_path / 'proc', cgroup_root=tmp_path / 'cgroup')
    sample = sampler.sample()
    assert sample.rss_bytes is not None and sample.rss_bytes > 0
    assert sample.cgroup_bytes == 456 and sample.read_bytes == 12 and sample.quality == 'available'
    (proc / 'stat').write_text('x' * 65537)
    assert sampler.sample().cpu_time_us is None


def test_statistics_lock_failure_does_not_write_partial_batch(tmp_path: Path) -> None:
    path = tmp_path / 'db'
    store = SQLiteStatisticsStore(path, IDENTITY, StatisticsConfig())
    store.open()
    other = sqlite3.connect(path)
    try:
        other.execute('BEGIN IMMEDIATE')
        with pytest.raises(sqlite3.OperationalError, match='locked'):
            store.write_batch([_summary()])
        other.rollback()
        assert store.connection is not None
        assert store.connection.execute('SELECT count(*) FROM execution_summaries').fetchone() == (0,)
        store.write_batch([_summary()])
        assert store.connection.execute('SELECT count(*) FROM execution_summaries').fetchone() == (1,)
    finally:
        other.close()
        store.close()


def test_background_failure_discards_finite_buffer_and_keeps_health_in_memory(tmp_path: Path) -> None:
    path = tmp_path / 'db'
    path.write_bytes(b'broken')
    config = StatisticsConfig()
    sink = BufferedTelemetrySink(SQLiteStatisticsStore(path, IDENTITY, config), IDENTITY, config)
    sink.offer(_resource())
    sink._stop.set()
    sink._run()
    assert not sink.health.available and sink.health.reason == 'collection_failed'
    assert sink.health.dropped == 1
    assert path.read_bytes() == b'broken'


def test_incomplete_pair_and_different_input_keep_totals_unknown() -> None:
    metrics = Metrics()
    set_metrics(metrics)
    try:
        input_shape('a', table_count=1, total_rows=2, max_table_rows=2)
        ordered_input_table('a', 'table', 2)
        ordered_input_table('a', 'table', 2)
        assert metrics.shape['ordered_table_rows'] == 2
        pair_totals(changed_tables=1, changed_rows=2)
        pair_totals(changed_tables=0, changed_rows=0, complete=False)
        pair_totals(changed_tables=1, changed_rows=2)
        input_shape('b', table_count=1, total_rows=3, max_table_rows=3)
    finally:
        set_metrics(None)
    result = bounded_metrics(metrics)
    assert result.input_shape.changed_rows is None and result.input_shape.changed_tables is None
    assert result.input_shape.total_rows is None and result.input_shape.ordered_table_rows is None


@pytest.mark.parametrize("pressure", ["wal", "pages"])
def test_wal_and_main_page_pressure_reclaim_curves_and_resume(tmp_path: Path, pressure: str) -> None:
    config = StatisticsConfig(total_budget_bytes=1024 * 1024)
    store = SQLiteStatisticsStore(tmp_path / 'db', IDENTITY, config)
    store.open()
    assert store.connection is not None
    db = store.connection
    db.execute('PRAGMA wal_autocheckpoint=0')
    store.write_batch([_summary()])
    try:
        for batch in range(20):
            records = [_resource(source_event_id=f'{batch}-{index}' + 'x' * 240,
                                 sampled_at_us=batch * 100 + index + 1) for index in range(100)]
            store.write_batch(records)
            if pressure == 'pages':
                db.execute('PRAGMA wal_checkpoint(TRUNCATE)')
            if store.under_pressure():
                break
        else:
            pytest.fail('small configured budget never applied pressure')
        count = db.execute('SELECT count(*) FROM resource_samples').fetchone()[0]
        assert count > 0
        assert store.maintain(1000000)
        assert db.execute('SELECT count(*) FROM resource_samples').fetchone()[0] < count
        assert db.execute('SELECT count(*) FROM execution_summaries').fetchone() == (1,)
        assert Path(str(store.path) + '-wal').stat().st_size == 0
        store.write_batch([_resource(source_event_id='resumed')])
    finally:
        store.close()


def test_sampler_never_attributes_a_read_across_claim_switch(tmp_path: Path) -> None:
    config = StatisticsConfig()
    operation, step = _active_records()
    first = ClaimedWork(operation, step, lambda *_: ExecutorAcknowledgment.PUBLISHED)
    second = dataclasses.replace(first, step=dataclasses.replace(step, optimistic_version=step.optimistic_version + 1))
    sink = BufferedTelemetrySink(SQLiteStatisticsStore(tmp_path / 'db', IDENTITY, config), IDENTITY, config)
    sink.begin_execution(first)

    def switch_claim() -> ResourceRecord:
        sink.end_execution(first)
        sink.begin_execution(second)
        return _resource()

    sink.sampler = switch_claim
    try:
        sample = sink._sample()
        assert sample.operation_id is None and sample.claim_version is None
        assert sink._active is not None and sink._active.first is None
    finally:
        sink.end_execution(second)
