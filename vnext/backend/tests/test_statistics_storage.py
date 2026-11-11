"""Current-object counting uses bounded metadata pages and live owning stat."""
from __future__ import annotations

import sqlite3
from pathlib import Path

from gateway_shared_kernel import raw_blob_digest
from gateway_backend.artifacts.bounded_store import BoundedArtifactStore
from gateway_backend.artifacts.location import ArtifactLocation
from gateway_backend.infrastructure.control_db.database import initialize_control_db
from gateway_backend.infrastructure.statistics.storage import DeviceStorageCollector, StorageCandidates, filesystem_capacity
from gateway_backend.statistics.config import StatisticsConfig
from gateway_backend.statistics.models import StatisticsIdentity, StorageRecord
from tests.support.artifact_layout import open_test_store

IDENTITY = StatisticsIdentity(environment_id='e', group_id='g')


def test_live_object_dedup_and_removed_reference_is_not_current_size(tmp_path: Path) -> None:
    local = open_test_store(tmp_path / 'artifacts')
    ref = BoundedArtifactStore(local).put_stream(ArtifactLocation.CANONICAL, 'test', [b'abc'],
        declared_size=3, declared_raw_sha256=raw_blob_digest(b'abc'), media_type='application/octet-stream')
    path = tmp_path / 'control.db'
    initialize_control_db(path)
    with sqlite3.connect(path) as db:
        db.execute("INSERT INTO provisioned_scope_mappings VALUES ('device','project','repository',1)")
        db.execute('INSERT INTO canonical_table_cache VALUES (?,?,?,?,?,NULL)',
            (ref.artifact_id, 'repository', ref.media_type, ref.size_bytes, ref.raw_sha256.value))
        db.execute('INSERT INTO snapshot_table_export_cache VALUES (?,?,?,?,?,?,?,?)',
            ('repository', 'digest', 1, ref.artifact_id, ref.media_type, ref.size_bytes, ref.raw_sha256.value, 1))
    records: list[StorageRecord] = []
    config = StatisticsConfig()
    candidates = StorageCandidates(path, config)
    collector = DeviceStorageCollector(candidates, local, IDENTITY, records.append, config)
    collector.collect_next()
    canonical = next(row for row in records if row.category == 'canonical')
    assert canonical.quality == 'available'
    assert canonical.object_count == 1 and canonical.logical_bytes == 3
    local.payload_path(ref.artifact_id).unlink()
    records.clear()
    collector.collect('repository')
    canonical = next(row for row in records if row.category == 'canonical')
    assert canonical.object_count == 0 and canonical.logical_bytes == 0
    assert collector.stale_candidates == 1
    assert candidates.repositories('repository') == []


def test_capacity_uses_configured_identity_once(tmp_path: Path) -> None:
    values = filesystem_capacity(IDENTITY, {'a': (tmp_path, 'filesystem'), 'b': (tmp_path, 'filesystem')})
    assert len(values) == 1
    assert values[0].available_bytes is not None
    assert values[0].logical_bytes is None and values[0].repository_id is None
