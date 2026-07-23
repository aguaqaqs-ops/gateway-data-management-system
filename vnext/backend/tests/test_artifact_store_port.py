"""ArtifactStore identity and raw-integrity contract tests."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from gateway_shared_kernel import DigestRef

from gateway_backend.artifacts import (
    InMemoryArtifactStore,
    ManifestVerificationError,
    RetentionClass,
    artifact_ref_to_json,
    build_logical_ref,
    build_manifest,
    put_with_built_manifest,
)
from gateway_backend.canonical_row_hash_artifact import (
    CanonicalRowHashesArtifactManifest,
)
from gateway_backend.settings import BackendSettings

RAW_BYTES = b"arrow-ipc-placeholder-bytes"
LOGICAL_REF = build_logical_ref("canonical-row-hash", "example-0001")


def sample_content() -> CanonicalRowHashesArtifactManifest:
    return CanonicalRowHashesArtifactManifest.create(
        raw_content_digest=DigestRef(
            "sha256:1111111111111111111111111111111111111111111111111111111111111111"
        ),
        table_schema_digest=DigestRef(
            "sha256:2222222222222222222222222222222222222222222222222222222222222222"
        ),
        row_count="0",
    )


def test_in_memory_store_put_and_locate_revalidates_raw_identity() -> None:
    store = InMemoryArtifactStore()
    manifest = build_manifest(
        logical_ref=LOGICAL_REF,
        raw_bytes=RAW_BYTES,
        content=sample_content(),
        retention_class=RetentionClass.OPERATION,
    )
    ref = store.put(RAW_BYTES, manifest)
    assert store.locate(ref) == RAW_BYTES


def test_store_rejects_raw_hash_mismatch_even_when_semantic_digest_matches() -> None:
    store = InMemoryArtifactStore()
    manifest = build_manifest(
        logical_ref=LOGICAL_REF,
        raw_bytes=RAW_BYTES,
        content=sample_content(),
        retention_class=RetentionClass.OPERATION,
    )
    tampered = RAW_BYTES[:-1] + bytes([RAW_BYTES[-1] ^ 0x01])
    with pytest.raises(ManifestVerificationError, match="raw_sha256 mismatch"):
        store.put(tampered, manifest)


def test_store_rejects_same_logical_ref_for_different_exact_identity() -> None:
    store = InMemoryArtifactStore()
    first = build_manifest(
        logical_ref=LOGICAL_REF,
        raw_bytes=RAW_BYTES,
        content=sample_content(),
        retention_class=RetentionClass.OPERATION,
    )
    store.put(RAW_BYTES, first)
    second_bytes = RAW_BYTES + b"x"
    second = build_manifest(
        logical_ref=LOGICAL_REF,
        raw_bytes=second_bytes,
        content=sample_content(),
        retention_class=RetentionClass.OPERATION,
    )
    with pytest.raises(ManifestVerificationError, match="different artifact"):
        store.put(second_bytes, second)


def test_locate_rejects_ref_with_same_logical_but_different_identity() -> None:
    store = InMemoryArtifactStore()
    manifest = build_manifest(
        logical_ref=LOGICAL_REF,
        raw_bytes=RAW_BYTES,
        content=sample_content(),
        retention_class=RetentionClass.OPERATION,
    )
    ref = store.put(RAW_BYTES, manifest)
    forged = replace(
        ref,
        content_digest=DigestRef(
            "sha256:9999999999999999999999999999999999999999999999999999999999999999"
        ),
    )
    with pytest.raises(ManifestVerificationError, match="identity mismatch"):
        store.locate(forged)


def test_put_with_built_manifest_helper() -> None:
    store = InMemoryArtifactStore()
    ref = put_with_built_manifest(
        store,
        RAW_BYTES,
        logical_ref=LOGICAL_REF,
        content_manifest=sample_content(),
        retention_class=RetentionClass.OPERATION,
    )
    assert ref.size_bytes == len(RAW_BYTES)


def test_different_local_roots_do_not_change_serialized_ref(tmp_path: Path) -> None:
    root_a = BackendSettings(artifact_root=tmp_path / "a")
    root_b = BackendSettings(artifact_root=tmp_path / "b")
    assert root_a.artifact_root != root_b.artifact_root
    manifest_a = build_manifest(
        logical_ref=LOGICAL_REF,
        raw_bytes=RAW_BYTES,
        content=sample_content(),
        retention_class=RetentionClass.OPERATION,
    )
    manifest_b = build_manifest(
        logical_ref=LOGICAL_REF,
        raw_bytes=RAW_BYTES,
        content=sample_content(),
        retention_class=RetentionClass.OPERATION,
    )
    assert artifact_ref_to_json(manifest_a.to_envelope()) == artifact_ref_to_json(
        manifest_b.to_envelope()
    )
