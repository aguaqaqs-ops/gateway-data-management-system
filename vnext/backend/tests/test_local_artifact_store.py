"""LocalArtifactStore filesystem safety and identity tests."""

from __future__ import annotations

import json
import os
from pathlib import Path

import pyarrow as pa
import pytest

from gateway_backend.artifacts import (
    ManifestVerificationError,
    RetentionClass,
    build_logical_ref,
    build_manifest,
    put_with_built_manifest,
)
from gateway_backend.canonical_row_hash_artifact import CanonicalRowHashesArtifactManifest
from gateway_backend.canonical_row_hash_ipc import (
    content_manifest_from_compute_result,
    persist_canonical_row_hash_stream,
    write_row_hash_ipc_stream,
)
from gateway_backend.compute import canonical_row_hashes_v1
from gateway_backend.infrastructure.artifact_store import LocalArtifactStore

_FIELDS = [{"name": "flag", "nullable": True, "semantic_type": {"kind": "boolean"}}]


def _request_jcs() -> bytes:
    return json.dumps(
        {
            "request_schema_version": 1,
            "contract_binding": {
                "contract_id": "gateway-vnext.canonical-row-hash-compute-boundary",
                "semantic_version": "1.0.0",
            },
            "canonical_encoding_version": 1,
            "arrow_mapping_schema_version": 1,
            "declared_table_schema": {"fields": _FIELDS},
        },
        separators=(",", ":"),
        sort_keys=True,
    ).encode()


def _content_manifest() -> CanonicalRowHashesArtifactManifest:
    _, result_jcs = canonical_row_hashes_v1(_request_jcs(), pa.table({"flag": [True]}))
    return content_manifest_from_compute_result(result_jcs)


def test_logical_ref_collision_with_different_identity_rejected(tmp_path: Path) -> None:
    store = LocalArtifactStore(tmp_path / "artifacts")
    content = _content_manifest()
    logical_ref = build_logical_ref("canonical-row-hash", "collision")
    output, _ = canonical_row_hashes_v1(_request_jcs(), pa.table({"flag": [True]}))
    persist_canonical_row_hash_stream(
        store,
        logical_ref=logical_ref,
        reader=output,
        content_manifest=content,
        declared_table_schema_fields=_FIELDS,
    )
    tampered_content = CanonicalRowHashesArtifactManifest.create(
        raw_content_digest=content.raw_content_digest,
        table_schema_digest=content.table_schema_digest,
        row_count="0",
    )
    with pytest.raises(ManifestVerificationError, match="logical_ref already identifies"):
        put_with_built_manifest(
            store,
            b"other-bytes",
            logical_ref=logical_ref,
            content_manifest=tampered_content,
            retention_class=RetentionClass.OPERATION,
        )


def test_unknown_ref_is_rejected(tmp_path: Path) -> None:
    store = LocalArtifactStore(tmp_path / "artifacts")
    content = _content_manifest()
    manifest = build_manifest(
        logical_ref=build_logical_ref("canonical-row-hash", "missing"),
        raw_bytes=b"bytes",
        content=content,
        retention_class=RetentionClass.OPERATION,
    )
    with pytest.raises(ManifestVerificationError, match="unknown logical_ref"):
        store.locate(manifest.to_envelope())


def test_storage_path_is_derived_not_logical_ref(tmp_path: Path) -> None:
    store = LocalArtifactStore(tmp_path / "artifacts")
    logical_ref = build_logical_ref("canonical-row-hash", "path-layout")
    object_path = store._object_path(logical_ref)  # noqa: SLF001
    assert logical_ref not in str(object_path)
    assert ".." not in object_path.parts


def test_cross_instance_logical_ref_collision_rejected_on_disk(tmp_path: Path) -> None:
    artifact_root = tmp_path / "artifacts"
    content = _content_manifest()
    logical_ref = build_logical_ref("canonical-row-hash", "cross-instance")
    output, _ = canonical_row_hashes_v1(_request_jcs(), pa.table({"flag": [True]}))
    persist_canonical_row_hash_stream(
        LocalArtifactStore(artifact_root),
        logical_ref=logical_ref,
        reader=output,
        content_manifest=content,
        declared_table_schema_fields=_FIELDS,
    )
    tampered_content = CanonicalRowHashesArtifactManifest.create(
        raw_content_digest=content.raw_content_digest,
        table_schema_digest=content.table_schema_digest,
        row_count="0",
    )
    fresh_store = LocalArtifactStore(artifact_root)
    with pytest.raises(ManifestVerificationError, match="logical_ref already identifies"):
        put_with_built_manifest(
            fresh_store,
            b"other-bytes",
            logical_ref=logical_ref,
            content_manifest=tampered_content,
            retention_class=RetentionClass.OPERATION,
        )


def test_same_raw_bytes_different_semantic_identity_rejected(tmp_path: Path) -> None:
    artifact_root = tmp_path / "artifacts"
    content = _content_manifest()
    logical_ref = build_logical_ref("canonical-row-hash", "same-raw-semantic")
    output, _ = canonical_row_hashes_v1(_request_jcs(), pa.table({"flag": [True]}))
    raw_bytes = write_row_hash_ipc_stream(output)
    store = LocalArtifactStore(artifact_root)
    put_with_built_manifest(
        store,
        raw_bytes,
        logical_ref=logical_ref,
        content_manifest=content,
        retention_class=RetentionClass.OPERATION,
    )
    tampered_content = CanonicalRowHashesArtifactManifest.create(
        raw_content_digest=content.raw_content_digest,
        table_schema_digest=content.table_schema_digest,
        row_count="0",
    )
    fresh_store = LocalArtifactStore(artifact_root)
    with pytest.raises(ManifestVerificationError, match="logical_ref already identifies"):
        put_with_built_manifest(
            fresh_store,
            raw_bytes,
            logical_ref=logical_ref,
            content_manifest=tampered_content,
            retention_class=RetentionClass.OPERATION,
        )


def test_fresh_store_instance_can_locate_persisted_ref(tmp_path: Path) -> None:
    artifact_root = tmp_path / "artifacts"
    content = _content_manifest()
    logical_ref = build_logical_ref("canonical-row-hash", "fresh-locate")
    output, _ = canonical_row_hashes_v1(_request_jcs(), pa.table({"flag": [True]}))
    ref = persist_canonical_row_hash_stream(
        LocalArtifactStore(artifact_root),
        logical_ref=logical_ref,
        reader=output,
        content_manifest=content,
        declared_table_schema_fields=_FIELDS,
    )
    fresh_store = LocalArtifactStore(artifact_root)
    output_again, _ = canonical_row_hashes_v1(_request_jcs(), pa.table({"flag": [True]}))
    assert fresh_store.locate(ref) == write_row_hash_ipc_stream(output_again)


def test_relative_artifact_root_rejected() -> None:
    with pytest.raises(ValueError, match="absolute path"):
        LocalArtifactStore(Path("relative-artifact-root"))


def test_locate_sanitizes_filesystem_error(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = LocalArtifactStore(tmp_path / "artifacts")
    logical_ref = build_logical_ref("canonical-row-hash", "sanitized-read-error")
    output, _ = canonical_row_hashes_v1(_request_jcs(), pa.table({"flag": [True]}))
    ref = persist_canonical_row_hash_stream(
        store,
        logical_ref=logical_ref,
        reader=output,
        content_manifest=_content_manifest(),
        declared_table_schema_fields=_FIELDS,
    )

    def fail_read(_path: Path) -> bytes:
        raise OSError(f"private path: {tmp_path}")

    monkeypatch.setattr(Path, "read_bytes", fail_read)
    with pytest.raises(ManifestVerificationError, match="artifact read failed") as captured:
        store.locate(ref)
    assert str(tmp_path) not in str(captured.value)


def test_put_sanitizes_filesystem_error(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = LocalArtifactStore(tmp_path / "artifacts")
    logical_ref = build_logical_ref("canonical-row-hash", "sanitized-write-error")
    output, _ = canonical_row_hashes_v1(_request_jcs(), pa.table({"flag": [True]}))
    raw_bytes = write_row_hash_ipc_stream(output)

    def fail_replace(_source: os.PathLike[str], _target: os.PathLike[str]) -> None:
        raise OSError(f"private path: {tmp_path}")

    monkeypatch.setattr(os, "replace", fail_replace)
    with pytest.raises(ManifestVerificationError, match="artifact write failed") as captured:
        put_with_built_manifest(
            store,
            raw_bytes,
            logical_ref=logical_ref,
            content_manifest=_content_manifest(),
            retention_class=RetentionClass.OPERATION,
        )
    assert str(tmp_path) not in str(captured.value)


def test_fresh_locate_rejects_parent_symlink_escape(tmp_path: Path) -> None:
    artifact_root = tmp_path / "artifacts"
    content = _content_manifest()
    logical_ref = build_logical_ref("canonical-row-hash", "parent-symlink")
    output, _ = canonical_row_hashes_v1(_request_jcs(), pa.table({"flag": [True]}))
    ref = persist_canonical_row_hash_stream(
        LocalArtifactStore(artifact_root),
        logical_ref=logical_ref,
        reader=output,
        content_manifest=content,
        declared_table_schema_fields=_FIELDS,
    )
    target = LocalArtifactStore(artifact_root)._object_path(logical_ref)  # noqa: SLF001
    parent = target.parent
    outside = tmp_path / "outside"
    outside.mkdir()
    escaped_target = outside / target.name
    escaped_target.write_bytes(target.read_bytes())
    escaped_sidecar = outside / (target.name + ".manifest.jcs")
    escaped_sidecar.write_bytes(
        LocalArtifactStore(artifact_root)._manifest_sidecar_path(target).read_bytes()  # noqa: SLF001
    )
    if parent.is_dir():
        for child in parent.iterdir():
            child.unlink()
        parent.rmdir()
    parent.symlink_to(outside)
    fresh_store = LocalArtifactStore(artifact_root)
    with pytest.raises(ManifestVerificationError, match="escapes artifact_root"):
        fresh_store.locate(ref)


def test_locate_rejects_symlink_escape_target(tmp_path: Path) -> None:
    store = LocalArtifactStore(tmp_path / "artifacts")
    content = _content_manifest()
    logical_ref = build_logical_ref("canonical-row-hash", "symlink-escape")
    output, _ = canonical_row_hashes_v1(_request_jcs(), pa.table({"flag": [True]}))
    ref = persist_canonical_row_hash_stream(
        store,
        logical_ref=logical_ref,
        reader=output,
        content_manifest=content,
        declared_table_schema_fields=_FIELDS,
    )
    target = store._object_path(logical_ref)  # noqa: SLF001
    outside = tmp_path / "outside.bin"
    outside.write_bytes(b"escaped")
    target.unlink()
    target.symlink_to(outside)
    with pytest.raises(ManifestVerificationError, match="escapes artifact_root"):
        store.locate(ref)
