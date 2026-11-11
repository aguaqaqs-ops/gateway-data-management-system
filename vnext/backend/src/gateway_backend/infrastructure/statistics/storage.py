"""Bounded read-only ownership pages, followed by current object stat outside SQL."""
from __future__ import annotations

import json
import os
import sqlite3
from collections.abc import Callable, Iterator, Mapping
from contextlib import contextmanager
from pathlib import Path
from time import monotonic, time_ns
from typing import cast
from uuid import uuid4

from gateway_backend.artifacts.computation_cache import ComputationCacheKey, ComputationCacheKind
from gateway_backend.artifacts.location import ArtifactLocation, parse_artifact_id
from gateway_backend.artifacts.store import ArtifactUnavailableError
from gateway_backend.artifacts.serialize import artifact_ref_from_dict
from gateway_backend.infrastructure.artifact_store.local_store import LocalArtifactStore
from gateway_backend.infrastructure.control_db.computation_cache import computation_cache_entry_from_row
from gateway_backend.infrastructure.control_db.sqlite_workspace import upload_revision_from_row, preview_result_from_row
from gateway_backend.infrastructure.control_db.sqlite_submission import submit_attempt_from_row, submission_from_row
from gateway_backend.statistics.config import StatisticsConfig
from gateway_backend.statistics.models import StatisticsIdentity, StorageRecord
from gateway_repository_contracts.statistics import Category, Quality, Reason
from gateway_shared_kernel import DigestRef

# Fixed sources, never recursive JSON walking or artifact-content reads.
_SOURCES = ('canonical_table_cache', 'snapshot_table_export_cache', 'computation_cache_entries',
            'upload_revision_records', 'preview_result_records', 'submit_attempt_records', 'submission_records',
            'operation_records')
_MAX_ROW_BYTES = 256 * 1024


class StorageCandidates:
    def __init__(self, control_db: Path, config: StatisticsConfig) -> None:
        self.path, self.config = control_db, config

    @contextmanager
    def _read(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(f'{self.path.as_uri()}?mode=ro', uri=True,
                                    timeout=self.config.sqlite_busy_timeout_ms / 1000)
        connection.row_factory = sqlite3.Row
        connection.execute('PRAGMA query_only=ON')
        deadline = monotonic() + self.config.scan_slice_ms / 1000
        connection.set_progress_handler(lambda: int(monotonic() > deadline), 1000)
        try:
            yield connection
        finally:
            connection.close()

    def repositories(self, after: str = '') -> list[str]:
        with self._read() as connection:
            return [str(row[0]) for row in connection.execute(
                'SELECT repository_id FROM provisioned_scope_mappings WHERE enabled=1 AND repository_id>? '
                'ORDER BY repository_id LIMIT ?', (after, self.config.storage_page_size))]

    def page(self, source: str, repository_id: str | None, after: int) -> list[Mapping[str, object]]:
        if source not in _SOURCES:
            raise ValueError('unknown statistics source')
        with self._read() as connection:
            if source == 'operation_records':
                owners = (
                    'SELECT p.operation_id FROM preview_idempotency_records p JOIN workspace_records w '
                    'ON p.workspace_id=w.workspace_id WHERE (? IS NULL OR w.repository_id=?) UNION '
                    'SELECT operation_id FROM submit_attempt_records WHERE (? IS NULL OR repository_id=?) UNION '
                    'SELECT operation_id FROM history_compare_acceptance_records WHERE (? IS NULL OR repository_id=?)')
                selection = 'NOT IN' if repository_id is None else 'IN'
                return [dict(row) for row in connection.execute(
                    'SELECT rowid AS cursor,length(artifact_refs)>262144 AS oversized, '
                    'substr(artifact_refs,1,262145) AS artifact_refs FROM operation_records '
                    f'WHERE rowid>? AND operation_id {selection} ({owners}) ORDER BY rowid LIMIT ?',
                    (after, *([repository_id] * 6), self.config.storage_page_size))]
            # Total row bytes are checked by SQLite before copying BLOBs into Python.
            columns = connection.execute(f'PRAGMA table_info({source})').fetchall()
            names = [str(row['name']) for row in columns]
            variable = [str(row['name']) for row in columns if str(row['type']).upper() in ('TEXT', 'BLOB')]
            size = '+'.join(f'coalesce(length(t.{name}),0)' for name in variable)
            projection = ','.join(f'CASE WHEN ({size})<=? THEN t.{name} END AS {name}' for name in names)
            if source == 'upload_revision_records':
                join = 'JOIN workspace_records w ON w.workspace_id=t.workspace_id'
                owner = 'w.repository_id'
            else:
                join, owner = '', 't.repository_id'
            rows = connection.execute(
                f'SELECT t.rowid AS cursor,{owner} AS owner_repository,({size})>? AS oversized,{projection} '
                f'FROM {source} t {join} WHERE (? IS NULL OR {owner}=?) AND t.rowid>? ORDER BY t.rowid LIMIT ?',
                (_MAX_ROW_BYTES, *([_MAX_ROW_BYTES] * len(names)), repository_id, repository_id, after,
                 self.config.storage_page_size)).fetchall()
            return [dict(row) for row in rows]

    def shared(self, artifact_id: str, known_owner: str | None) -> bool:
        """At most two direct cache owners, not a persistent attribution graph."""
        location = parse_artifact_id(artifact_id)
        # Content-addressed comparison and bundle refs can be shared without a cache
        # row. Conservative public classification avoids inventing exclusive owners.
        if location is ArtifactLocation.COMPARISON:
            return True
        with self._read() as connection:
            if location is ArtifactLocation.EXPORT:
                owners = {str(row[0]) for row in connection.execute(
                    'SELECT DISTINCT repository_id FROM snapshot_table_export_cache WHERE artifact_id=? LIMIT 2',
                    (artifact_id,))}
            else:
                owners = {str(row[0]) for row in connection.execute(
                    'SELECT repository_id FROM canonical_table_cache WHERE artifact_id=? UNION '
                    'SELECT repository_id FROM snapshot_table_export_cache WHERE artifact_id=? LIMIT 2',
                    (artifact_id, artifact_id))}
        return ((location is ArtifactLocation.EXPORT and not owners)
                or len(owners) > 1 or (known_owner is not None and bool(owners - {known_owner})))

    @staticmethod
    def refs(source: str, row: Mapping[str, object]) -> tuple[str, ...]:
        if source == 'operation_records':
            raw = row['artifact_refs']
            if not isinstance(raw, (str, bytes)):
                raise ValueError('invalid operation refs')
            values = json.loads(raw)
            if not isinstance(values, list) or len(values) > 1000:
                raise ValueError('invalid operation refs')
            return tuple(artifact_ref_from_dict(value).artifact_id for value in values)
        if source in ('canonical_table_cache', 'snapshot_table_export_cache'):
            return (str(row['artifact_id']),)
        if source == 'computation_cache_entries':
            entry = computation_cache_entry_from_row(ComputationCacheKey(str(row['repository_id']),
                ComputationCacheKind(str(row['kind'])), DigestRef(str(row['task_digest']))),
                tuple(row[name] for name in ('manifest_artifact_id', 'manifest_media_type',
                    'manifest_size_bytes', 'manifest_raw_sha256', 'member_refs_json', 'format')))
            return tuple(ref.artifact_id for ref in (entry.manifest_ref, *entry.member_refs))
        if source == 'upload_revision_records':
            return tuple(ref.artifact_id for ref in upload_revision_from_row(row).source_artifacts.values())
        if source == 'preview_result_records':
            result = preview_result_from_row(row)
            return (result.bundle_artifact_id, result.ready_closure_artifact_id,
                    result.canonical.canonical_table_set_closure_ref.artifact_id,
                    result.canonical.canonicalization_manifest_ref.artifact_id,
                    *(pair.assessment_ref.artifact_id for pair in result.identity_pairs if pair.assessment_ref is not None))
        if source == 'submit_attempt_records':
            attempt = submit_attempt_from_row(row)
            return (*attempt.source_artifact_refs, attempt.canonical_table_set_closure_ref,
                    attempt.preview_ready_closure_ref, attempt.canonicalization_manifest_ref,
                    *((attempt.prepared_canonicalization_manifest_ref,) if attempt.prepared_canonicalization_manifest_ref else ()),
                    *((attempt.repository_import_artifact_ref.artifact_id,) if attempt.repository_import_artifact_ref else ()))
        result_submission = submission_from_row(row)
        return (*result_submission.source_artifact_refs, result_submission.canonicalization_manifest_ref)



class DeviceStorageCollector:
    def __init__(self, candidates: StorageCandidates, store: LocalArtifactStore,
                 identity: StatisticsIdentity, offer: Callable[[StorageRecord], object],
                 config: StatisticsConfig) -> None:
        self.candidates, self.store, self.identity, self.offer, self.config = candidates, store, identity, offer, config
        self.stale_candidates = 0
        self._after_repository = ''
        self._changed: set[str] = set()

    def changed(self, repository_id: str) -> None:
        if len(self._changed) < self.config.queue_max_items and len(repository_id) <= 255:
            self._changed.add(repository_id)

    def collect_next(self) -> None:
        """One repository per invocation; E schedules continuously with a 600s cycle goal."""
        if self._changed:
            repository_id = self._changed.pop()
            # A notification is not authority; recheck enabled mapping.
            with self.candidates._read() as connection:
                if connection.execute('SELECT 1 FROM provisioned_scope_mappings WHERE enabled=1 '
                                      'AND repository_id=?', (repository_id,)).fetchone() is None:
                    return
        else:
            repositories = self.candidates.repositories(self._after_repository)
            if not repositories:
                self._after_repository = ''
                self.collect(None)
                return
            repository_id = repositories[0]
            self._after_repository = repository_id
        self.collect(repository_id)

    def collect(self, repository_id: str | None) -> None:
        start = time_ns() // 1000
        deadline = monotonic() + self.config.scan_total_seconds
        seen: set[str] = set()
        totals = ({'public_unknown': [0, 0, 0]} if repository_id is None else
                  {location.value: [0, 0, 0] for location in ArtifactLocation})
        partial = repository_id is None
        reason: Reason | None = 'not_collected' if repository_id is None else None
        rows_scanned = 0
        try:
            for source in _SOURCES:
                cursor = 0
                while True:
                    if monotonic() >= deadline or rows_scanned >= self.config.scan_total_entries:
                        partial, reason = True, 'budget_exceeded'
                        break
                    rows = self.candidates.page(source, repository_id, cursor)
                    if not rows:
                        break
                    for row in rows:
                        if rows_scanned >= self.config.scan_total_entries or monotonic() >= deadline:
                            partial, reason = True, 'budget_exceeded'
                            break
                        cursor = int(cast(int, row['cursor']))
                        rows_scanned += 1
                        if row['oversized']:
                            partial, reason = True, 'budget_exceeded'
                            continue
                        for artifact_id in self.candidates.refs(source, row):
                            if monotonic() >= deadline or len(seen) >= self.config.scan_total_entries:
                                partial, reason = True, 'budget_exceeded'
                                break
                            if artifact_id in seen:
                                continue
                            shared = self.candidates.shared(artifact_id,
                                str(row['owner_repository']) if row.get('owner_repository') is not None else repository_id)
                            public = shared or (repository_id is None and source == 'operation_records')
                            if public != (repository_id is None):
                                continue
                            if artifact_id in seen:
                                continue
                            if len(seen) >= self.config.scan_total_entries or monotonic() >= deadline:
                                partial, reason = True, 'budget_exceeded'
                                break
                            seen.add(artifact_id)
                            try:
                                value = self.store.observe_object(artifact_id)
                                category = 'public_unknown' if repository_id is None else parse_artifact_id(artifact_id).value
                                bucket = totals[category]
                                bucket[0] += 1
                                bucket[1] += cast(int, value['logical_bytes'])
                                bucket[2] += cast(int, value['allocated_bytes'])
                            except (ArtifactUnavailableError, FileNotFoundError):
                                self.stale_candidates += 1
                            except Exception:
                                partial, reason = True, 'collection_failed'
                    if partial and reason == 'budget_exceeded':
                        break
                if monotonic() >= deadline or rows_scanned >= self.config.scan_total_entries:
                    break
        except Exception:
            partial, reason = True, 'collection_failed'
        end = time_ns() // 1000
        for category, (objects, logical, allocated) in totals.items():
            self.offer(StorageRecord(**self.identity.model_dump(), source_event_id=str(uuid4()),
                repository_id=repository_id, service_owner='backend', category=cast(Category, category),
                object_count=objects, logical_bytes=logical, allocated_bytes=allocated,
                window_start_us=start, window_end_us=end, generated_at_us=end,
                quality='partial' if partial else 'available', reason=reason))



def filesystem_capacity(identity: StatisticsIdentity, roots: Mapping[str, tuple[Path, str]]) -> tuple[StorageRecord, ...]:
    """Configured filesystem identities only; no device-number cross-service inference."""
    records: list[StorageRecord] = []
    seen: set[str] = set()
    for path, filesystem_id in roots.values():
        if filesystem_id in seen:
            continue
        seen.add(filesystem_id)
        now = time_ns() // 1000
        total: int | None
        available: int | None
        inodes: int | None
        quality: Quality
        reason: Reason | None
        try:
            value = os.statvfs(path)
            total, available, inodes = value.f_blocks * value.f_frsize, value.f_bavail * value.f_frsize, value.f_favail
            quality, reason = 'available', None
        except OSError:
            total = available = inodes = None
            quality, reason = 'partial', 'collection_failed'
        records.append(StorageRecord(**identity.model_dump(), source_event_id=str(uuid4()),
            service_owner='backend', category='filesystem', filesystem_id=filesystem_id,
            total_bytes=total, available_bytes=available, available_inodes=inodes,
            window_end_us=now, generated_at_us=now, quality=quality, reason=reason))
    return tuple(records)
