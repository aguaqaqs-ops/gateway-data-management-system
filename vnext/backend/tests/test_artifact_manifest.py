"""Generic ArtifactManifest and capability-content binding tests."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from gateway_shared_kernel import DigestRef
from gateway_shared_kernel.jcs import canonicalize_json_value

from gateway_backend.artifacts import (
    ArtifactManifest,
    RetentionClass,
    artifact_manifest_from_dict,
    artifact_manifest_from_json,
    artifact_manifest_to_dict,
    artifact_manifest_to_json,
    build_logical_ref,
    build_manifest,
)
from gateway_backend.canonical_row_hash_artifact import (
    CanonicalRowHashesArtifactManifest,
)

VECTOR_ROOT = Path(__file__).resolve().parents[2] / "fixtures" / "vectors" / "artifacts" / "v1"
RAW_BYTES = b"arrow-ipc-placeholder-bytes"


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


def sample_manifest() -> ArtifactManifest:
    return build_manifest(
        logical_ref=build_logical_ref("canonical-row-hash", "example-0001"),
        raw_bytes=RAW_BYTES,
        content=sample_content(),
        retention_class=RetentionClass.OPERATION,
    )


def test_manifest_wire_is_jcs_and_deterministic() -> None:
    manifest = sample_manifest()
    payload = artifact_manifest_to_dict(manifest)
    wire = artifact_manifest_to_json(manifest)
    assert wire.encode() == canonicalize_json_value(payload)
    assert wire == artifact_manifest_to_json(sample_manifest())


def test_manifest_round_trip_uses_capability_owned_parser() -> None:
    manifest = sample_manifest()
    restored = artifact_manifest_from_json(
        artifact_manifest_to_json(manifest),
        content_parser=CanonicalRowHashesArtifactManifest.from_wire_dict,
    )
    assert restored == manifest
    assert restored.to_envelope() == manifest.to_envelope()


def test_valid_fixture_manifest_parses() -> None:
    payload = json.loads((VECTOR_ROOT / "valid" / "canonical-row-hashes-manifest.json").read_text())
    manifest = artifact_manifest_from_dict(
        payload,
        content_parser=CanonicalRowHashesArtifactManifest.from_wire_dict,
    )
    assert manifest.size_bytes == 27


def test_manifest_rejects_semantic_digest_binding_mismatch() -> None:
    payload = json.loads(
        (VECTOR_ROOT / "invalid" / "manifest-content-digest-mismatch.json").read_text()
    )
    with pytest.raises(ValueError, match="content_digest must match"):
        artifact_manifest_from_dict(
            payload,
            content_parser=CanonicalRowHashesArtifactManifest.from_wire_dict,
        )
