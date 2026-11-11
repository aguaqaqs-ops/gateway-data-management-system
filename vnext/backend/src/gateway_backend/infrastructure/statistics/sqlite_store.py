"""Independent disposable telemetry SQLite, finite transactions and maintenance."""
from __future__ import annotations

import sqlite3
import os
import math
from collections.abc import Sequence
from pathlib import Path
from typing import TypeAlias

from gateway_backend.infrastructure.statistics.schema import SCHEMA_SQL, SCHEMA_VERSION
from gateway_backend.statistics.config import StatisticsConfig
from gateway_backend.statistics.models import ExecutionSummary, ResourceRecord, StatisticsIdentity, StorageRecord, WriteRecord

Record: TypeAlias = ExecutionSummary | ResourceRecord | StorageRecord | WriteRecord


class StatisticsUnavailable(Exception):
    """Telemetry failure. Never a business failure."""


class SQLiteStatisticsStore:
    def __init__(self, path: Path, identity: StatisticsIdentity, config: StatisticsConfig, *,
                 capacity_path: Path | None = None, min_free_bytes: int = 0, min_free_fraction: float = 0) -> None:
        self.path, self.identity, self.config = path, identity, config
        self.capacity_path, self.min_free_bytes, self.min_free_fraction = capacity_path, min_free_bytes, min_free_fraction
        self.connection: sqlite3.Connection | None = None

    def open(self) -> None:
        if self.capacity_path is not None and self._filesystem_pressure():
            raise sqlite3.OperationalError('statistics filesystem capacity unavailable')
        self.path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self.path, timeout=self.config.sqlite_busy_timeout_ms / 1000)
        try:
            connection.execute(f'PRAGMA busy_timeout={self.config.sqlite_busy_timeout_ms}')
            objects = connection.execute("SELECT name,type,sql FROM sqlite_master WHERE name NOT LIKE 'sqlite_%' ORDER BY name").fetchall()
            if not objects and connection.execute('PRAGMA user_version').fetchone()[0] == 0:
                connection.execute('PRAGMA page_size=4096')
                connection.executescript('BEGIN IMMEDIATE;\n' + SCHEMA_SQL + '\nCOMMIT;')
            expected = sqlite3.connect(':memory:')
            try:
                expected.executescript(SCHEMA_SQL)
                baseline = expected.execute("SELECT name,type,sql FROM sqlite_master WHERE name NOT LIKE 'sqlite_%' ORDER BY name").fetchall()
            finally:
                expected.close()
            actual = connection.execute("SELECT name,type,sql FROM sqlite_master WHERE name NOT LIKE 'sqlite_%' ORDER BY name").fetchall()
            if actual != baseline or connection.execute('PRAGMA user_version').fetchone()[0] != SCHEMA_VERSION:
                raise StatisticsUnavailable('schema_mismatch')
            if connection.execute('PRAGMA quick_check(1)').fetchone()[0] != 'ok':
                raise StatisticsUnavailable('database_corrupt')
            for table in ('storage_observations', 'execution_summaries', 'resource_samples', 'write_observations'):
                if connection.execute(f'SELECT 1 FROM {table} WHERE environment_id != ? OR group_id != ? LIMIT 1',
                                      (self.identity.environment_id, self.identity.group_id)).fetchone():
                    raise StatisticsUnavailable('identity_mismatch')
            current_pages = connection.execute('PRAGMA page_count').fetchone()[0]
            if current_pages > self.config.max_page_count:
                raise StatisticsUnavailable('budget_exceeded')
            connection.execute(f'PRAGMA max_page_count={self.config.max_page_count}')
            connection.execute('PRAGMA journal_mode=WAL')
            connection.execute('PRAGMA wal_autocheckpoint=256')
            connection.execute(f'PRAGMA journal_size_limit={self.config.wal_soft_limit_bytes}')
            self.connection = connection
        except BaseException:
            connection.close()
            raise

    def close(self) -> None:
        if self.connection is not None:
            self.connection.close()
            self.connection = None

    def _connection(self) -> sqlite3.Connection:
        if self.connection is None:
            raise StatisticsUnavailable('not_open')
        return self.connection

    def disk_bytes(self) -> int:
        return sum(path.stat().st_size if path.exists() else 0 for path in
                   (self.path, Path(str(self.path) + '-wal'), Path(str(self.path) + '-shm')))

    def _filesystem_pressure(self) -> bool:
        info = os.statvfs(self.capacity_path or self.path.parent)
        reserve = min(self.config.write_batch_bytes * 4, self.config.total_budget_bytes // 16)
        minimum = max(self.min_free_bytes, math.ceil(info.f_blocks * info.f_frsize * self.min_free_fraction))
        return (bool(info.f_flag & os.ST_RDONLY) or info.f_favail == 0
                or info.f_bavail * info.f_frsize < minimum + reserve)

    def under_pressure(self) -> bool:
        reserve = min(self.config.write_batch_bytes * 4, self.config.total_budget_bytes // 16)
        wal = Path(str(self.path) + '-wal')
        connection = self._connection()
        pages = connection.execute('PRAGMA page_count').fetchone()[0]
        free_pages = connection.execute('PRAGMA freelist_count').fetchone()[0]
        # SQLite's main-file cap is independent of the DB+WAL budget. Reserve enough
        # reusable/growable pages for one bounded batch, including index maintenance.
        batch_pages = (self.config.write_batch_bytes + 4095) // 4096 + 8
        page_pressure = self.config.max_page_count - pages + free_pages < batch_pages
        return (page_pressure or self.disk_bytes() + reserve >= self.config.total_budget_bytes
                or (wal.exists() and wal.stat().st_size >= self.config.wal_soft_limit_bytes)
                or self._filesystem_pressure())

    def write_batch(self, records: Sequence[Record]) -> None:
        if len(records) > self.config.write_batch_items:
            raise ValueError('batch exceeds item budget')
        encoded: list[tuple[str, dict[str, object]]] = []
        total_bytes = 0
        for record in records:
            if record.environment_id != self.identity.environment_id or record.group_id != self.identity.group_id:
                raise ValueError('statistics identity mismatch')
            size = len(record.model_dump_json().encode())
            total_bytes += size
            if size > self.config.record_max_bytes or total_bytes > self.config.write_batch_bytes:
                raise ValueError('batch exceeds byte budget')
            fields = record.model_dump(mode='json')
            if isinstance(record, ExecutionSummary):
                fields.pop('metrics')
                fields['metrics_json'] = None if record.metrics is None else record.metrics.model_dump_json()
                table = 'execution_summaries'
            elif isinstance(record, ResourceRecord):
                table = 'resource_samples'
            elif isinstance(record, StorageRecord):
                table = 'storage_observations'
            else:
                table = 'write_observations'
            encoded.append((table, fields))
        connection = self._connection()
        with connection:
            for table, fields in encoded:
                names = tuple(fields)
                columns = ','.join(names)
                values = ','.join('?' for _ in names)
                if table in ('execution_summaries', 'write_observations'):
                    key = ('operation_id', 'step_id', 'claim_version') if table == 'execution_summaries' else ('observation_id',)
                    # First successful recording time is immutable. Unknown end fields never erase facts.
                    updates = ','.join(f'{name}=COALESCE(excluded.{name},{table}.{name})' for name in names
                                       if name not in (*key, 'recorded_at_us', 'observed_outcome', 'quality', 'reason'))
                    updates += f",observed_outcome=CASE WHEN excluded.observed_outcome='unknown' THEN {table}.observed_outcome ELSE excluded.observed_outcome END"
                    # Completeness is derived from the merged start/end, never from arrival order.
                    if table == 'execution_summaries':
                        updates += f",quality=CASE WHEN COALESCE(excluded.started_at_us,{table}.started_at_us) IS NULL THEN 'partial' ELSE excluded.quality END,reason=excluded.reason"
                    else:
                        updates += ',quality=excluded.quality,reason=excluded.reason'
                    sql = f'INSERT INTO {table} ({columns}) VALUES ({values}) ON CONFLICT({",".join(key)}) DO UPDATE SET {updates}'
                else:
                    sql = f'INSERT OR IGNORE INTO {table} ({columns}) VALUES ({values})'
                connection.execute(sql, tuple(fields.values()))

    def maintain(self, now_us: int) -> bool:
        connection = self._connection()
        limit = self.config.retention_batch_rows
        with connection:
            for table, timestamp, days in (
                ('resource_samples', 'sampled_at_us', self.config.curve_retention_days),
                ('storage_observations', 'window_end_us', self.config.summary_retention_days),
                ('execution_summaries', 'recorded_at_us', self.config.summary_retention_days),
                ('write_observations', 'recorded_at_us', self.config.summary_retention_days),
            ):
                connection.execute(f'DELETE FROM {table} WHERE rowid IN (SELECT rowid FROM {table} WHERE {timestamp} < ? ORDER BY {timestamp} LIMIT ?)',
                                   (now_us - days * 86400 * 1000000, limit))
            if self.under_pressure():
                connection.execute('DELETE FROM resource_samples WHERE id IN (SELECT id FROM resource_samples ORDER BY sampled_at_us,id LIMIT ?)', (limit,))
        connection.execute('PRAGMA wal_checkpoint(PASSIVE)')
        wal = Path(str(self.path) + '-wal')
        if wal.exists() and wal.stat().st_size >= self.config.wal_soft_limit_bytes:
            # PASSIVE makes pages reusable but leaves the physical WAL file in place.
            # A zero-wait standard checkpoint can reclaim it once readers permit it.
            connection.execute('PRAGMA busy_timeout=0')
            try:
                connection.execute('PRAGMA wal_checkpoint(TRUNCATE)')
            finally:
                connection.execute(f'PRAGMA busy_timeout={self.config.sqlite_busy_timeout_ms}')
        return not self.under_pressure()
