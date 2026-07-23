"""ArtifactRef identity, equality, and wire round-trip tests."""

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

from gateway_shared_kernel import DigestRef

from gateway_backend.artifacts import (
    AccessMetadata,
    ArtifactRef,
    CANONICAL_ROW_HASHES_ARTIFACT,
    RetentionClass,
    artifact_ref_from_dict,
    artifact_ref_from_json,
    artifact_ref_to_dict,
    artifact_ref_to_json,
    build_logical_ref,
    content_contract_from_spec,
    validate_artifact_ref,
)

VECTOR_ROOT = Path(__file__).resolve().parents[2] / "fixtures" / "vectors" / "artifacts" / "v1"
RAW_SHA256 = DigestRef("sha256:257a0191a8f55365597b56b691ef9608a86034a9226dff5f06c6b84029ed8ac5")
SEMANTIC_DIGEST = DigestRef(
    "sha256:1111111111111111111111111111111111111111111111111111111111111111"
)


def sample_ref() -> ArtifactRef:
    return ArtifactRef(
        artifact_ref_schema_version=1,
        logical_ref=build_logical_ref("canonical-row-hash", "example-0001"),
        media_type=CANONICAL_ROW_HASHES_ARTIFACT.media_type,
        size_bytes=27,
        raw_sha256=RAW_SHA256,
        content_digest=SEMANTIC_DIGEST,
        content_contract=content_contract_from_spec(CANONICAL_ROW_HASHES_ARTIFACT),
        content_schema_id=CANONICAL_ROW_HASHES_ARTIFACT.content_schema_id,
        retention_class=RetentionClass.OPERATION,
        access_metadata=AccessMetadata(),
    )


def test_minimal_legal_ref_constructs_and_round_trips() -> None:
    ref = sample_ref()
    payload = artifact_ref_to_dict(ref)
    validate_artifact_ref(payload)
    assert artifact_ref_from_dict(payload) == ref
    assert artifact_ref_from_json(artifact_ref_to_json(ref)) == ref


def test_valid_fixture_matches_runtime_schema_projection() -> None:
    payload = json.loads((VECTOR_ROOT / "valid" / "canonical-row-hashes-ref.json").read_text())
    ref = artifact_ref_from_dict(payload)
    assert ref.logical_ref == build_logical_ref("canonical-row-hash", "example-0001")


def test_logical_raw_and_semantic_identities_are_independent() -> None:
    original = sample_ref()
    different_raw = replace(
        original,
        size_bytes=28,
        raw_sha256=DigestRef(
            "sha256:3333333333333333333333333333333333333333333333333333333333333333"
        ),
    )
    different_semantic = replace(
        original,
        content_digest=DigestRef(
            "sha256:4444444444444444444444444444444444444444444444444444444444444444"
        ),
    )
    assert different_raw.logical_identity == original.logical_identity
    assert different_raw.semantic_identity == original.semantic_identity
    assert different_raw.integrity_identity != original.integrity_identity
    assert different_semantic.logical_identity == original.logical_identity
    assert different_semantic.integrity_identity == original.integrity_identity
    assert different_semantic.semantic_identity != original.semantic_identity


def test_explicit_equality_and_cache_key_cover_exact_wire_identity() -> None:
    ref = sample_ref()
    same = artifact_ref_from_json(artifact_ref_to_json(ref))
    assert ref == same
    assert ref.cache_key == same.cache_key
    assert replace(ref, logical_ref=build_logical_ref("canonical-row-hash", "example-0002")) != ref
    assert replace(ref, retention_class=RetentionClass.STAGED_DURABLE) != ref
    assert all("path" not in str(part) for part in ref.cache_key)
