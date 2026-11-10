"""Corrupt artifact, cancel, timeout, and I/O cleanup tests."""

from __future__ import annotations

from tests.support.artifact_layout import open_test_store

from gateway_backend.artifacts.location import ArtifactLocation, build_artifact_id

from collections.abc import Callable
from pathlib import Path

import pytest
from gateway_backend.artifacts import (
    ArtifactRef,
    InMemoryArtifactStore,
    ManifestVerificationError,
    put_with_built_ref,
)
from gateway_backend.artifacts.serialize import artifact_ref_to_dict
from gateway_backend.capabilities.snapshot_materialization.artifact import (
    ArtifactPublishError,
    manifest_to_payload,
    open_snapshot_table_artifact,
    publish_snapshot_table_artifact,
)
from gateway_backend.capabilities.snapshot_materialization.contracts import (
    MANIFEST_MEDIA_TYPE,
    MaterializationDiagnosticCode,
    MaterializationPolicy,
    SnapshotMaterializationStatus,
)
from gateway_backend.capabilities.table_access.contracts import (
    NeverCancel,
    ParserInvocationContext,
)
from gateway_shared_kernel.jcs import canonicalize_json_value
from tests.support.artifact_staging import open_local_store, staging_root
from tests.support.snapshot_artifact import first_ready_table, publish_first_table
from tests.support.snapshot_materialization import materialize_sql, parse_fixture

_WRONG_DIGEST = "sha256:" + ("0" * 64)


def _put_manifest(store: InMemoryArtifactStore, payload: dict[str, object], artifact_id: str) -> ArtifactRef:
    return put_with_built_ref(
        store,
        canonicalize_json_value(payload),
        artifact_id=build_artifact_id(ArtifactLocation.EXPORT, "test-fixture", artifact_id),
        media_type=MANIFEST_MEDIA_TYPE,
    )


def _fault_corrupt_manifest(store: InMemoryArtifactStore) -> ArtifactRef:
    return put_with_built_ref(
        store,
        b"{not-json",
        artifact_id="a1:durable:849e84e1e018f8ba99481a36a9fe2c271d65433cc2f6c1eecdccd59f4417e350",
        media_type=MANIFEST_MEDIA_TYPE,
    )


def _fault_missing_row_file(store: InMemoryArtifactStore) -> ArtifactRef:
    artifact, _digest = publish_first_table(store)
    store._artifacts.pop(artifact.manifest.row_file_refs[0].artifact_id)
    return artifact.manifest_ref


def _fault_truncated_parquet(store: InMemoryArtifactStore) -> ArtifactRef:
    artifact, _digest = publish_first_table(store)
    truncated = put_with_built_ref(
        store,
        b"PAR1",
        artifact_id="a1:durable:5ac927de14a95725025866b7dd626c15c19eb4c790a714a9bb0d0ff36591681f",
        media_type=artifact.manifest.row_file_refs[0].media_type,
    )
    payload = manifest_to_payload(artifact.manifest)
    payload["row_file_refs"] = [artifact_ref_to_dict(truncated)]
    return _put_manifest(store, payload, "sta-manifest-trunc001")


def _fault_digest_mismatch(store: InMemoryArtifactStore) -> ArtifactRef:
    artifact, _digest = publish_first_table(store)
    payload = manifest_to_payload(artifact.manifest)
    payload["artifact_content_digest"] = _WRONG_DIGEST
    return _put_manifest(store, payload, "sta-manifest-digest01")


def _fault_schema_mismatch(store: InMemoryArtifactStore) -> ArtifactRef:
    artifact, _digest = publish_first_table(store)
    payload = manifest_to_payload(artifact.manifest)
    descriptor = payload["descriptor"]
    assert isinstance(descriptor, dict)
    descriptor["row_count"] = int(descriptor["row_count"]) + 1
    return _put_manifest(store, payload, "sta-manifest-schema01")


ARTIFACT_OPEN_FAULTS: tuple[
    tuple[str, Callable[[InMemoryArtifactStore], ArtifactRef], MaterializationDiagnosticCode],
    ...,
] = (
    ("corrupt_manifest", _fault_corrupt_manifest, MaterializationDiagnosticCode.ARTIFACT_MANIFEST_CORRUPT),
    ("missing_row_file", _fault_missing_row_file, MaterializationDiagnosticCode.ARTIFACT_TRUNCATED),
    ("truncated_parquet", _fault_truncated_parquet, MaterializationDiagnosticCode.ARTIFACT_TRUNCATED),
    ("digest_mismatch", _fault_digest_mismatch, MaterializationDiagnosticCode.ARTIFACT_DIGEST_MISMATCH),
    ("schema_mismatch", _fault_schema_mismatch, MaterializationDiagnosticCode.ARTIFACT_SCHEMA_MISMATCH),
)


class CountCancel:
    def __init__(self, trip_after: int) -> None:
        self.trip_after = trip_after
        self.calls = 0

    def is_set(self) -> bool:
        self.calls += 1
        return self.calls >= self.trip_after


@pytest.mark.parametrize(("name", "fault", "code"), ARTIFACT_OPEN_FAULTS)
def test_corrupt_artifact_cannot_open_as_ready(
    name: str,
    fault: Callable[[InMemoryArtifactStore], ArtifactRef],
    code: MaterializationDiagnosticCode,
) -> None:
    store = InMemoryArtifactStore()
    ref = fault(store)
    with pytest.raises(ArtifactPublishError) as raised:
        open_snapshot_table_artifact(store, ref)
    assert raised.value.code is code, name


def test_publish_cancel_does_not_put_manifest() -> None:
    store = InMemoryArtifactStore()
    table = first_ready_table()
    result = materialize_sql(
        parse_fixture("sql/valid/s2-minimal-create-insert/input.sql"),
        policy=MaterializationPolicy.READERS_REQUIRED,
    )
    assert result.snapshot is not None
    with pytest.raises(ArtifactPublishError) as raised:
        publish_snapshot_table_artifact(
            table,
            snapshot_digest=result.snapshot.snapshot_digest,
            store=store,
            context=ParserInvocationContext(CountCancel(1)),
        )
    assert raised.value.code is MaterializationDiagnosticCode.MATERIALIZATION_CANCELLED
    assert store._artifacts == {}


def test_publish_timeout_does_not_put_manifest() -> None:
    store = InMemoryArtifactStore()
    table = first_ready_table()
    result = materialize_sql(
        parse_fixture("sql/valid/s2-minimal-create-insert/input.sql"),
        policy=MaterializationPolicy.READERS_REQUIRED,
    )
    assert result.snapshot is not None
    with pytest.raises(ArtifactPublishError) as raised:
        publish_snapshot_table_artifact(
            table,
            snapshot_digest=result.snapshot.snapshot_digest,
            store=store,
            context=ParserInvocationContext(NeverCancel(), 0.0),
        )
    assert raised.value.code is MaterializationDiagnosticCode.MATERIALIZATION_TIMEOUT
    assert store._artifacts == {}


def test_store_io_failure_does_not_publish_manifest() -> None:
    class FailingStore(InMemoryArtifactStore):
        def put(self, raw_bytes: bytes, ref: ArtifactRef) -> ArtifactRef:
            raise ManifestVerificationError("artifact write failed")

    table = first_ready_table()
    result = materialize_sql(
        parse_fixture("sql/valid/s2-minimal-create-insert/input.sql"),
        policy=MaterializationPolicy.READERS_REQUIRED,
    )
    assert result.snapshot is not None
    with pytest.raises(ArtifactPublishError) as raised:
        publish_snapshot_table_artifact(
            table,
            snapshot_digest=result.snapshot.snapshot_digest,
            store=FailingStore(),
            context=ParserInvocationContext(NeverCancel()),
        )
    assert raised.value.code is MaterializationDiagnosticCode.ARTIFACT_PUBLISH_FAILED


def test_local_store_tmp_cleanup_and_no_path_in_refs(tmp_path: Path) -> None:
    root = staging_root(tmp_path)
    store = open_local_store(root)
    result = materialize_sql(
        parse_fixture("sql/valid/s2-minimal-create-insert/input.sql"),
        policy=MaterializationPolicy.ARTIFACTS_REQUIRED,
        artifact_store=store,
    )
    assert result.status is SnapshotMaterializationStatus.COMPLETE
    assert result.table_set is not None
    assert result.summary is not None
    artifact = result.table_set.tables[0].artifact
    assert artifact is not None
    payload = artifact_ref_to_dict(artifact.manifest_ref)
    assert set(payload) == {"artifact_id", "media_type", "size_bytes", "raw_sha256"}
    leftover = [path for path in root.rglob("*") if path.suffix == ".tmp" or path.name.endswith(".tmp")]
    assert leftover == []
    opened = open_snapshot_table_artifact(store, artifact.manifest_ref)
    assert opened.descriptor.raw_content_digest == result.summary.tables[0].raw_content_digest


def test_local_oversize_object_is_rejected_before_body_read(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import hashlib
    import io
    from typing import Any

    from gateway_backend.infrastructure.artifact_store.local_store import LocalArtifactStore

    store = open_test_store(tmp_path / "objects")
    ref = put_with_built_ref(store, b"small", artifact_id="a1:durable:4e6cd69eb33a2b12f384dbd0dd2c36f9eecfabf9c80fa7e79fd41132dcb86cd2", media_type="application/octet-stream")
    digest = hashlib.sha256(ref.artifact_id.encode()).hexdigest()
    target = store.payload_path(ref.artifact_id)
    target.write_bytes(b"oversize")
    original = Path.open
    body_reads: list[int] = []

    class TracedFile(io.BufferedReader):
        def read(self, size: int | None = -1) -> bytes:
            body_reads.append(-1 if size is None else size)
            return super().read(size)

    def open_path(path: Path, *args: Any, **kwargs: Any) -> object:
        if path == target:
            return TracedFile(io.FileIO(path, "r"))
        return original(path, *args, **kwargs)

    monkeypatch.setattr(Path, "open", open_path)
    with pytest.raises(ManifestVerificationError):
        store.locate(ref)
    assert body_reads == []
