"""One bounded best effort buffer and sampling/writing thread per process."""
from __future__ import annotations

import logging
import sqlite3
import threading
from collections import deque
from dataclasses import dataclass, field
from time import monotonic, time_ns
from typing import Callable
from uuid import uuid4

from gateway_backend.infrastructure.statistics.sampling import ProcessSampler, counter_delta
from gateway_backend.infrastructure.statistics.sqlite_store import Record, SQLiteStatisticsStore, StatisticsUnavailable
from gateway_backend.operations.worker import ClaimedWork
from gateway_backend.statistics.config import StatisticsConfig
from gateway_backend.statistics.metrics import Metrics, set_metrics
from gateway_repository_contracts.statistics import Reason

from gateway_backend.statistics.models import (
    CacheCounts, ExecutionMetrics, ExecutionSummary, InputShape, ResourceRecord, StageDurations,
    StatisticsIdentity, TableMetric,
)

_LOG = logging.getLogger(__name__)


@dataclass
class CollectionHealth:
    available: bool = False
    reason: str | None = 'not_collected'
    dropped: int = 0
    written: int = 0


@dataclass
class _Window:
    operation_id: str
    step_id: str
    claim_version: int
    attempt_count: int
    worker_id: str
    started_us: int
    started_mono: float
    metrics: Metrics = field(default_factory=Metrics)
    ended_us: int | None = None
    duration_ms: int | None = None
    first: ResourceRecord | None = None
    last: ResourceRecord | None = None
    rss_peak: int | None = None
    cgroup_peak: int | None = None
    repository_id: str | None = None
    submit_attempt_id: str | None = None


@dataclass(frozen=True)
class _WindowEvent:
    window: _Window
    ended: bool


def bounded_metrics(metrics: Metrics) -> ExecutionMetrics:
    fields = dict(input_shape=InputShape(**metrics.shape), stage_duration_ms=StageDurations(**metrics.durations),
                  cache_lookups=CacheCounts(**metrics.lookups), cache_hits=CacheCounts(**metrics.hits),
                  tables_total=metrics.tables_total, tables_truncated=metrics.truncated)
    tables: list[TableMetric] = []
    for pair, name, mode, before, after, changed in metrics.tables:
        table = TableMetric(pair_id=pair, table_name=name, comparison_mode=mode,
                            before_rows=before, after_rows=after, changed_rows=changed)
        try:
            ExecutionMetrics.model_validate({**fields, 'tables': tuple([*tables, table]),
                                'tables_truncated': metrics.tables_total > len(tables) + 1 or metrics.truncated})
        except ValueError:
            break
        tables.append(table)
    return ExecutionMetrics.model_validate({**fields, 'tables': tuple(tables),
                              'tables_truncated': metrics.truncated or metrics.tables_total > len(tables)})


class BufferedTelemetrySink:
    def __init__(self, store: SQLiteStatisticsStore, identity: StatisticsIdentity,
                 config: StatisticsConfig, *, role: str = 'worker', revision: str | None = None,
                 config_digest: str | None = None, process_instance_id: str | None = None,
                 sampler: Callable[[], ResourceRecord] | None = None) -> None:
        self.store, self.identity, self.config = store, identity, config
        self.process_instance_id = process_instance_id or str(uuid4())
        self.revision, self.config_digest = revision, config_digest
        from gateway_repository_contracts.statistics import Role
        from typing import cast
        self.sampler = sampler or ProcessSampler(identity, cast(Role, role), self.process_instance_id).sample
        self.health = CollectionHealth(reason=None if config.enabled else 'disabled')
        self._queue: deque[Record | _WindowEvent] = deque()
        self._lock = threading.Lock()
        self._active: _Window | None = None
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._permanent_failure = False
        self._last_log = -float('inf')

    def _offer(self, record: Record | _WindowEvent) -> bool:
        # Charge every event at the maximum encoded record size; conservative byte bound,
        # with zero JSON construction in an executor/HTTP callback.
        if not self.config.enabled or not self._lock.acquire(blocking=False):
            self.health.dropped += 1
            return False
        try:
            if (len(self._queue) >= self.config.queue_max_items
                    or (len(self._queue) + 1) * self.config.record_max_bytes > self.config.queue_max_bytes):
                self.health.dropped += 1
                return False
            self._queue.append(record)
            return True
        finally:
            self._lock.release()

    def offer(self, record: Record) -> bool:
        return self._offer(record)

    def begin_execution(self, work: ClaimedWork) -> None:
        if not self.config.enabled:
            return
        window = _Window(work.operation.operation_id, work.step.step_id, work.step.optimistic_version,
                         work.step.attempt_count, work.step.worker_id or 'unknown', time_ns() // 1000, monotonic())
        # Business refs are already bounded, structured and nonsecret. No payload decoding/query.
        for reference in work.operation.business_refs:
            if reference.kind == 'repository':
                window.repository_id = reference.value
            elif reference.kind == 'submit_attempt':
                window.submit_attempt_id = reference.value
        self._active = window
        set_metrics(window.metrics)
        self._offer(_WindowEvent(window, False))

    def end_execution(self, work: ClaimedWork) -> None:
        window = self._active
        self._active = None
        set_metrics(None)
        if window is None:
            return
        window.ended_us = time_ns() // 1000
        window.duration_ms = max(0, int((monotonic() - window.started_mono) * 1000))
        self._offer(_WindowEvent(window, True))

    def start(self) -> None:
        if not self.config.enabled or self._thread is not None:
            return
        try:
            self._thread = threading.Thread(target=self._run, name='statistics', daemon=True)
            self._thread.start()
        except Exception:
            self._thread = None
            self._failure('collection_failed')

    def close(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=self.config.shutdown_flush_seconds)

    def _failure(self, reason: str) -> None:
        self.health.available, self.health.reason = False, reason
        now = monotonic()
        if now - self._last_log >= 60:
            _LOG.warning('statistics unavailable reason=%s', reason)
            self._last_log = now

    def _summary(self, event: _WindowEvent) -> ExecutionSummary:
        window = event.window
        cpu = read = write = None
        reset = False
        if event.ended and window.first is not None and window.last is not None:
            cpu, cpu_reset = counter_delta(window.first, window.last, 'cpu_time_us')
            read, read_reset = counter_delta(window.first, window.last, 'read_bytes')
            write, write_reset = counter_delta(window.first, window.last, 'write_bytes')
            reset = cpu_reset or read_reset or write_reset
        metrics = None
        reason: Reason = 'counter_reset' if reset else 'counter_unavailable'
        if event.ended:
            try:
                metrics = bounded_metrics(window.metrics)
            except ValueError:
                reason = 'budget_exceeded'
        return ExecutionSummary(**self.identity.model_dump(), operation_id=window.operation_id,
            step_id=window.step_id, claim_version=window.claim_version, attempt_count=window.attempt_count,
            process_instance_id=self.process_instance_id, worker_id=window.worker_id,
            repository_id=window.metrics.repository_id or window.repository_id,
            submit_attempt_id=window.metrics.submit_attempt_id or window.submit_attempt_id,
            started_at_us=None if event.ended else window.started_us,
            ended_at_us=window.ended_us if event.ended else None,
            duration_ms=window.duration_ms if event.ended else None, recorded_at_us=time_ns() // 1000,
            cpu_time_us=cpu, read_bytes=read, write_bytes=write, rss_peak_bytes=window.rss_peak,
            cgroup_peak_bytes=window.cgroup_peak, revision=self.revision, config_digest=self.config_digest,
            metrics=metrics, quality='partial', reason=reason)

    def _sample(self) -> ResourceRecord:
        sample = self.sampler()
        window = self._active
        if window is not None and window.ended_us is None:
            window.first = window.first or sample
            window.last = sample
            if sample.rss_bytes is not None:
                window.rss_peak = max(window.rss_peak or 0, sample.rss_bytes)
            if sample.cgroup_bytes is not None:
                window.cgroup_peak = max(window.cgroup_peak or 0, sample.cgroup_bytes)
            sample = sample.model_copy(update=dict(operation_id=window.operation_id, step_id=window.step_id,
                attempt_count=window.attempt_count, claim_version=window.claim_version))
        return sample

    def _take_batch(self) -> list[Record]:
        batch: list[Record] = []
        # Conservative reservation avoids encoding on the callback and bounds each SQL batch.
        maximum = min(self.config.write_batch_items, self.config.write_batch_bytes // self.config.record_max_bytes)
        with self._lock:
            events = [self._queue.popleft() for _ in range(min(maximum, len(self._queue)))]
        for event in events:
            try:
                batch.append(self._summary(event) if isinstance(event, _WindowEvent) else event)
            except Exception:
                self.health.dropped += 1
        return batch

    def _run(self) -> None:
        next_open = next_sample = next_maintenance = 0.0
        try:
            while True:
                now = monotonic()
                if self.store.connection is None and not self._permanent_failure and now >= next_open:
                    next_open = now + self.config.maintenance_seconds
                    try:
                        self.store.open()
                        self.health.available, self.health.reason = True, None
                    except (StatisticsUnavailable, sqlite3.DatabaseError) as error:
                        self._permanent_failure = isinstance(error, StatisticsUnavailable) or not isinstance(error, sqlite3.OperationalError)
                        self._failure('collection_failed')
                    except OSError:
                        self._failure('collection_failed')
                if not self._stop.is_set() and now >= next_sample:
                    next_sample = now + self.config.sample_interval_seconds
                    try:
                        self.offer(self._sample())
                    except Exception:
                        self._failure('counter_unavailable')
                if self.store.connection is not None:
                    try:
                        if now >= next_maintenance:
                            next_maintenance = now + self.config.maintenance_seconds
                            self.store.maintain(time_ns() // 1000)
                        if self.store.under_pressure():
                            self._failure('budget_exceeded')
                            # Drop bounded input, never keep growing or retry a business action.
                            with self._lock:
                                self.health.dropped += len(self._queue)
                                self._queue.clear()
                        else:
                            batch = self._take_batch()
                            if batch:
                                self.store.write_batch(batch)
                                self.health.written += len(batch)
                            self.health.available, self.health.reason = True, None
                    except Exception:
                        self._failure('collection_failed')
                        self.store.close()
                        next_open = now + self.config.maintenance_seconds
                else:
                    with self._lock:
                        self.health.dropped += len(self._queue)
                        self._queue.clear()
                if self._stop.is_set():
                    break
                self._stop.wait(min(self.config.flush_seconds, self.config.sample_interval_seconds))
        except Exception:
            self._failure('collection_failed')
        finally:
            self.store.close()
