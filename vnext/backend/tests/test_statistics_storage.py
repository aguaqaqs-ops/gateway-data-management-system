"""Current-object counting uses bounded metadata pages and live owning stat."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from gateway_shared_kernel import raw_blob_digest
from gateway_backend.infrastructure.artifact_store import BoundedArtifactStore
from gateway_backend.artifacts.location import ArtifactLocation
from gateway_backend.infrastructure.control_db.database import initialize_control_db
from gateway_backend.infrastructure.statistics.storage import (
    DeviceStorageCollector,
    StorageCandidates,
    filesystem_capacity,
)
from gateway_backend.statistics.config import StatisticsConfig
from gateway_backend.statistics.models import StatisticsIdentity, StorageRecord
from tests.support.artifact_layout import open_test_store

IDENTITY = StatisticsIdentity(environment_id="e", group_id="g")


def test_live_object_dedup_and_removed_reference_is_not_current_size(tmp_path: Path) -> None:
    local = open_test_store(tmp_path / "artifacts")
    ref = BoundedArtifactStore(local).put_stream(
        ArtifactLocation.CANONICAL,
        "test",
        [b"abc"],
        declared_size=3,
        declared_raw_sha256=raw_blob_digest(b"abc"),
        media_type="application/octet-stream",
    )
    path = tmp_path / "control.db"
    initialize_control_db(path)
    with sqlite3.connect(path) as db:
        db.execute(
            "INSERT INTO provisioned_scope_mappings VALUES ('device','project','repository',1)"
        )
        db.execute(
            "INSERT INTO canonical_table_cache VALUES (?,?,?,?,?,NULL)",
            (ref.artifact_id, "repository", ref.media_type, ref.size_bytes, ref.raw_sha256.value),
        )
        db.execute(
            "INSERT INTO snapshot_table_export_cache VALUES (?,?,?,?,?,?,?,?)",
            (
                "repository",
                "digest",
                1,
                ref.artifact_id,
                ref.media_type,
                ref.size_bytes,
                ref.raw_sha256.value,
                1,
            ),
        )
    records: list[StorageRecord] = []
    config = StatisticsConfig()
    candidates = StorageCandidates(path, config)
    collector = DeviceStorageCollector(candidates, local, IDENTITY, records.append, config)
    collector.collect_next()
    canonical = next(row for row in records if row.category == "canonical")
    assert canonical.quality == "available"
    assert canonical.object_count == 1 and canonical.logical_bytes == 3
    local.payload_path(ref.artifact_id).unlink()
    records.clear()
    collector.collect("repository")
    canonical = next(row for row in records if row.category == "canonical")
    assert canonical.object_count == 0 and canonical.logical_bytes == 0
    assert collector.stale_candidates == 1
    assert candidates.repositories("repository") == []


def test_capacity_uses_configured_identity_once(tmp_path: Path) -> None:
    values = filesystem_capacity(
        IDENTITY, {"a": (tmp_path, "filesystem"), "b": (tmp_path, "filesystem")}
    )
    assert len(values) == 1
    assert values[0].available_bytes is not None
    assert values[0].logical_bytes is None and values[0].repository_id is None


def test_storage_budget_is_explicit_partial(tmp_path: Path) -> None:
    local = open_test_store(tmp_path / "artifacts")
    path = tmp_path / "control.db"
    initialize_control_db(path)
    with sqlite3.connect(path) as db:
        for index in range(3):
            db.execute(
                "INSERT INTO canonical_table_cache VALUES (?,?,?,?,?,NULL)",
                (
                    "a1:canonical:" + str(index) * 64,
                    "repository",
                    "application/octet-stream",
                    123,
                    "sha256:" + "a" * 64,
                ),
            )
    records: list[StorageRecord] = []
    config = StatisticsConfig(scan_total_entries=1)
    collector = DeviceStorageCollector(
        StorageCandidates(path, config), local, IDENTITY, records.append, config
    )
    collector.collect("repository")
    assert all(row.quality == "partial" and row.reason == "budget_exceeded" for row in records)
    assert collector.stale_candidates == 1


def test_shared_cache_ref_is_public_and_not_charged_to_both_devices(tmp_path: Path) -> None:
    local = open_test_store(tmp_path / "artifacts")
    ref = BoundedArtifactStore(local).put_stream(
        ArtifactLocation.COMPARISON,
        "test",
        [b"abc"],
        declared_size=3,
        declared_raw_sha256=raw_blob_digest(b"abc"),
        media_type="application/octet-stream",
    )
    path = tmp_path / "control.db"
    initialize_control_db(path)
    with sqlite3.connect(path) as db:
        for index, repository in enumerate(("one", "two")):
            db.execute(
                "INSERT INTO provisioned_scope_mappings VALUES (?,?,?,1)",
                (f"device-{index}", "project", repository),
            )
            db.execute(
                "INSERT INTO snapshot_table_export_cache VALUES (?,?,?,?,?,?,?,?)",
                (
                    repository,
                    "digest",
                    1,
                    ref.artifact_id,
                    ref.media_type,
                    ref.size_bytes,
                    ref.raw_sha256.value,
                    1,
                ),
            )
    records: list[StorageRecord] = []
    config = StatisticsConfig()
    collector = DeviceStorageCollector(
        StorageCandidates(path, config), local, IDENTITY, records.append, config
    )
    collector.collect("one")
    collector.collect("two")
    assert all(row.logical_bytes == 0 for row in records)
    records.clear()
    collector.collect(None)
    assert len(records) == 1
    assert records[0].repository_id is None and records[0].category == "public_unknown"
    assert records[0].object_count == 1 and records[0].logical_bytes == 3
    assert records[0].quality == "partial"  # not a scan of all unreferenced physical files


def test_uncached_identity_assessment_from_two_previews_is_public(tmp_path: Path) -> None:
    from dataclasses import replace
    from gateway_shared_kernel.jcs import canonicalize_json_value
    from gateway_backend.domain.workspace.models import (
        PreviewArtifactRef,
        PreviewIdentityPair,
        ProjectIdentityApplicability,
        ProjectIdentityMode,
        ProjectIdentityStatus,
    )
    from gateway_backend.infrastructure.control_db.sqlite_workspace import preview_result_to_row
    from tests.test_workspace_domain import _preview_result

    local = open_test_store(tmp_path / "artifacts")
    ref = BoundedArtifactStore(local).put_stream(
        ArtifactLocation.COMPARISON,
        "project-identity",
        [b"abc"],
        declared_size=3,
        declared_raw_sha256=raw_blob_digest(b"abc"),
        media_type="application/json",
    )
    identity = PreviewIdentityPair(
        pair_id="initial_to_modified",
        applicability=ProjectIdentityApplicability.APPLICABLE,
        status=ProjectIdentityStatus.SAME_PROJECT,
        mode=ProjectIdentityMode.DETAILED,
        assessment_ref=PreviewArtifactRef(
            ref.artifact_id, ref.media_type, ref.size_bytes, ref.raw_sha256
        ),
        assessment_digest=ref.raw_sha256,
    )
    path = tmp_path / "control.db"
    initialize_control_db(path)
    base = _preview_result()
    with sqlite3.connect(path) as db:
        for index, repository in enumerate(("one", "two")):
            value = replace(
                base,
                preview_result_id=f"preview-{index}",
                repository_id=repository,
                operation_id=f"op-{index}",
                identity_pairs=(identity,),
                identity_assessment_set_digest=raw_blob_digest(
                    canonicalize_json_value(
                        {
                            "schema": "project-identity-assessment-set/v1",
                            "pairs": [
                                [
                                    identity.pair_id,
                                    identity.applicability.value,
                                    identity.status.value,
                                    ref.raw_sha256.value,
                                ]
                            ],
                        }
                    )
                ),
                canonical=replace(
                    base.canonical,
                    configuration_facts=replace(
                        base.canonical.configuration_facts,
                        repository_id=repository,
                        operation_id=f"op-{index}",
                    ),
                ),
            )
            db.execute(
                "INSERT INTO preview_result_records VALUES (?,?,?,?,?,?,?,?)",
                preview_result_to_row(value),
            )
    records: list[StorageRecord] = []
    config = StatisticsConfig()
    collector = DeviceStorageCollector(
        StorageCandidates(path, config), local, IDENTITY, records.append, config
    )
    collector.collect("one")
    collector.collect("two")
    assert sum(row.logical_bytes or 0 for row in records) == 0
    records.clear()
    collector.collect(None)
    assert records[0].object_count == 1 and records[0].logical_bytes == 3
