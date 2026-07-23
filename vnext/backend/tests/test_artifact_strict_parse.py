"""Strict JCS, closed-schema, and identity-binding negative tests."""

from __future__ import annotations

import copy

import pytest

from gateway_shared_kernel import CanonicalEncodingError, DigestRef

from gateway_backend.artifacts import (
    AccessMetadata,
    ArtifactRef,
    CANONICAL_ROW_HASHES_ARTIFACT,
    RetentionClass,
    artifact_manifest_from_dict,
    artifact_manifest_to_dict,
    artifact_ref_from_dict,
    artifact_ref_from_json,
    artifact_ref_to_dict,
    artifact_ref_to_json,
    build_logical_ref,
    build_manifest,
    content_contract_from_spec,
)
from gateway_backend.canonical_row_hash_artifact import (
    CanonicalRowHashesArtifactManifest,
)

RAW_SHA256 = DigestRef("sha256:257a0191a8f55365597b56b691ef9608a86034a9226dff5f06c6b84029ed8ac5")


def sample_ref_dict() -> dict[str, object]:
    return artifact_ref_to_dict(
        ArtifactRef(
            artifact_ref_schema_version=1,
            logical_ref=build_logical_ref("canonical-row-hash", "example-0001"),
            media_type=CANONICAL_ROW_HASHES_ARTIFACT.media_type,
            size_bytes=27,
            raw_sha256=RAW_SHA256,
            content_digest=DigestRef(
                "sha256:1111111111111111111111111111111111111111111111111111111111111111"
            ),
            content_contract=content_contract_from_spec(CANONICAL_ROW_HASHES_ARTIFACT),
            content_schema_id=CANONICAL_ROW_HASHES_ARTIFACT.content_schema_id,
            retention_class=RetentionClass.OPERATION,
            access_metadata=AccessMetadata(),
        )
    )


def sample_manifest_dict() -> dict[str, object]:
    content = CanonicalRowHashesArtifactManifest.create(
        raw_content_digest=DigestRef(
            "sha256:1111111111111111111111111111111111111111111111111111111111111111"
        ),
        table_schema_digest=DigestRef(
            "sha256:2222222222222222222222222222222222222222222222222222222222222222"
        ),
        row_count="0",
    )
    return artifact_manifest_to_dict(
        build_manifest(
            logical_ref=build_logical_ref("canonical-row-hash", "example-0001"),
            raw_bytes=b"arrow-ipc-placeholder-bytes",
            content=content,
            retention_class=RetentionClass.OPERATION,
        )
    )


def parse_manifest(payload: dict[str, object]) -> object:
    return artifact_manifest_from_dict(
        payload,
        content_parser=CanonicalRowHashesArtifactManifest.from_wire_dict,
    )


@pytest.mark.parametrize("field", ["metadata", "context", "debug", "provider"])
def test_ref_rejects_arbitrary_escape_fields(field: str) -> None:
    payload = sample_ref_dict()
    payload[field] = {"note": "escape"}
    with pytest.raises(ValueError, match="unknown fields"):
        artifact_ref_from_dict(payload)


def test_ref_rejects_missing_field() -> None:
    payload = sample_ref_dict()
    del payload["raw_sha256"]
    with pytest.raises(ValueError, match="missing fields"):
        artifact_ref_from_dict(payload)


def test_strict_json_rejects_duplicate_member_at_any_depth() -> None:
    text = artifact_ref_to_json(artifact_ref_from_dict(sample_ref_dict()))
    duplicated = text.replace(
        '"contract_id":"gateway-vnext.canonical-row-hash-compute-boundary"',
        '"contract_id":"gateway-vnext.canonical-row-hash-compute-boundary",'
        '"contract_id":"gateway-vnext.canonical-row-hash-compute-boundary"',
        1,
    )
    with pytest.raises(CanonicalEncodingError) as caught:
        artifact_ref_from_json(duplicated)
    assert caught.value.code.value == "CANONICAL_JCS_DUPLICATE_MEMBER"


def test_strict_json_rejects_trailing_data_and_non_object() -> None:
    wire = artifact_ref_to_json(artifact_ref_from_dict(sample_ref_dict()))
    with pytest.raises(CanonicalEncodingError):
        artifact_ref_from_json(wire + "{}")
    with pytest.raises(ValueError, match="must be an object"):
        artifact_ref_from_json("[]")


def test_strict_json_rejects_invalid_utf8_and_unicode() -> None:
    with pytest.raises(CanonicalEncodingError):
        artifact_ref_from_json(b'{"x":"\xff"}')
    with pytest.raises(ValueError, match="invalid Unicode"):
        artifact_ref_from_json('{"x":"\ud800"}')
    with pytest.raises(CanonicalEncodingError):
        artifact_ref_from_json('{"x":"\ufdd0"}')


def test_strict_json_rejects_non_ijson_number() -> None:
    wire = artifact_ref_to_json(artifact_ref_from_dict(sample_ref_dict()))
    invalid = wire.replace('"size_bytes":27', '"size_bytes":NaN')
    with pytest.raises(CanonicalEncodingError):
        artifact_ref_from_json(invalid)


@pytest.mark.parametrize("size_bytes", [-1, 1.5, True, 2**53])
def test_ref_rejects_non_safe_integer_size(size_bytes: object) -> None:
    payload = sample_ref_dict()
    payload["size_bytes"] = size_bytes
    with pytest.raises(ValueError):
        artifact_ref_from_dict(payload)


@pytest.mark.parametrize(
    "digest_value",
    [
        "sha256:" + "A" * 64,
        "sha256:" + "a" * 63,
        "sha256:" + "a" * 64 + "=",
        "a" * 64,
    ],
)
def test_ref_rejects_noncanonical_sha256(digest_value: str) -> None:
    payload = sample_ref_dict()
    payload["raw_sha256"] = digest_value
    with pytest.raises(ValueError):
        artifact_ref_from_dict(payload)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("artifact_ref_schema_version", 2),
        ("retention_class", "forever"),
        ("media_type", "application/octet-stream"),
        (
            "content_schema_id",
            "gateway-vnext.canonical-row-hash.unknown.v1",
        ),
    ],
)
def test_ref_rejects_unknown_closed_value(field: str, value: object) -> None:
    payload = sample_ref_dict()
    payload[field] = value
    with pytest.raises(ValueError):
        artifact_ref_from_dict(payload)


def test_ref_rejects_unknown_resolver() -> None:
    payload = sample_ref_dict()
    payload["access_metadata"] = {"resolver": "filesystem"}
    with pytest.raises(ValueError, match="resolver"):
        artifact_ref_from_dict(payload)


def test_ref_rejects_unknown_contract_or_version() -> None:
    for key, value in [
        ("contract_id", "gateway-vnext.unknown"),
        ("semantic_version", "9.9.9"),
    ]:
        payload = sample_ref_dict()
        contract = copy.deepcopy(payload["content_contract"])
        assert isinstance(contract, dict)
        contract[key] = value
        payload["content_contract"] = contract
        with pytest.raises(ValueError):
            artifact_ref_from_dict(payload)


def test_manifest_rejects_raw_semantic_field_exchange() -> None:
    payload = sample_manifest_dict()
    raw = payload["raw_sha256"]
    payload["raw_sha256"] = payload["content_digest"]
    payload["content_digest"] = raw
    with pytest.raises(ValueError, match="content_digest must match"):
        parse_manifest(payload)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("result_schema_version", 2),
        ("row_count", "00"),
        ("canonical_encoding_version", 2),
        ("arrow_mapping_schema_version", 2),
    ],
)
def test_capability_content_rejects_unknown_version_or_noncanonical_count(
    field: str, value: object
) -> None:
    payload = sample_manifest_dict()
    content = copy.deepcopy(payload["content"])
    assert isinstance(content, dict)
    content[field] = value
    payload["content"] = content
    with pytest.raises(ValueError):
        parse_manifest(payload)


def test_manifest_rejects_content_owner_binding_mismatch() -> None:
    payload = sample_manifest_dict()
    content = copy.deepcopy(payload["content"])
    assert isinstance(content, dict)
    binding = copy.deepcopy(content["contract_binding"])
    assert isinstance(binding, dict)
    binding["semantic_version"] = "9.9.9"
    content["contract_binding"] = binding
    payload["content"] = content
    with pytest.raises(ValueError, match="semantic_version"):
        parse_manifest(payload)


def test_serialization_is_jcs_deterministic() -> None:
    ref = artifact_ref_from_dict(sample_ref_dict())
    first = artifact_ref_to_json(ref)
    assert first == artifact_ref_to_json(ref)
    assert first == artifact_ref_to_json(artifact_ref_from_json(first))
    assert first.index('"access_metadata"') < first.index('"artifact_ref_schema_version"')
