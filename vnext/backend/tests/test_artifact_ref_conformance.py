"""Minimal ArtifactRef envelope round-trip and invalid-shape conformance."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from gateway_shared_kernel import CanonicalEncodingError, DigestRef

from gateway_backend.artifacts import (
    ArtifactRef,
    artifact_ref_from_dict,
    artifact_ref_from_json,
    artifact_ref_to_dict,
    artifact_ref_to_json,
    raw_sha256_from_bytes,
)

EXAMPLE_ARTIFACT_ID = "a1:durable:f476e64814ea84210e63df6e0a58006d29895542703f626aa399f87af08f6580"
EXAMPLE_MEDIA_TYPE = "application/octet-stream"
EXAMPLE_RAW_SHA256 = "sha256:" + "a" * 64
EXAMPLE_JCS = (
    '{"artifact_id":"a1:durable:f476e64814ea84210e63df6e0a58006d29895542703f626aa399f87af08f6580",'
    '"media_type":"application/octet-stream",'
    f'"raw_sha256":"{EXAMPLE_RAW_SHA256}",'
    '"size_bytes":3}'
)
RAW_BLOB_PAYLOAD_DIGEST = (
    "sha256:239f59ed55e737c77147cf55ad0c1b030b6d7ee748a7426952f9b852d5a935e5"
)


def _ref_payload(**changes: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "artifact_id": EXAMPLE_ARTIFACT_ID,
        "media_type": EXAMPLE_MEDIA_TYPE,
        "size_bytes": 3,
        "raw_sha256": EXAMPLE_RAW_SHA256,
    }
    payload.update(changes)
    return payload


def _without(key: str) -> dict[str, object]:
    payload = _ref_payload()
    del payload[key]
    return payload


ARTIFACT_REF_FAULTS: tuple[tuple[str, dict[str, object], str], ...] = (
    ("missing-artifact-id", _without("artifact_id"), "missing fields"),
    ("missing-media-type", _without("media_type"), "missing fields"),
    ("missing-size-bytes", _without("size_bytes"), "missing fields"),
    ("missing-raw-sha256", _without("raw_sha256"), "missing fields"),
    (
        "unknown-content-digest",
        _ref_payload(content_digest="sha256:" + "b" * 64),
        "unknown fields",
    ),
    (
        "unknown-schema-id",
        _ref_payload(content_schema_id="example"),
        "unknown fields",
    ),
    (
        "forbidden-key-path",
        _ref_payload(path="/tmp/secret.arrow"),
        "forbidden key",
    ),
    (
        "forbidden-key-artifact-root",
        _ref_payload(artifact_root="/var/artifacts"),
        "forbidden key",
    ),
    (
        "host-path-file-scheme",
        _ref_payload(artifact_id="file:secret"),
        "host path",
    ),
    (
        "slash-artifact-id",
        _ref_payload(artifact_id="/tmp/secret.arrow"),
        "host path",
    ),
    (
        "empty-media-type",
        _ref_payload(media_type=""),
        "media_type must be a non-empty string",
    ),
    (
        "size-bytes-bool",
        _ref_payload(size_bytes=True),
        "size_bytes must be a non-negative integer",
    ),
    (
        "size-bytes-negative",
        _ref_payload(size_bytes=-1),
        "size_bytes must be a non-negative integer",
    ),
    (
        "size-bytes-ijson-overflow",
        _ref_payload(size_bytes=2**53),
        "I-JSON",
    ),
    (
        "raw-sha256-uppercase",
        _ref_payload(raw_sha256="sha256:" + "A" * 64),
        "DigestRef must be sha256:",
    ),
    (
        "raw-sha256-missing-prefix",
        _ref_payload(raw_sha256="a" * 64),
        "DigestRef must be sha256:",
    ),
)


def test_backend_ref_is_exactly_minimal_and_round_trips_exact_jcs() -> None:
    ref = ArtifactRef(
        artifact_id=EXAMPLE_ARTIFACT_ID,
        media_type=EXAMPLE_MEDIA_TYPE,
        size_bytes=3,
        raw_sha256=DigestRef(EXAMPLE_RAW_SHA256),
    )
    assert set(artifact_ref_to_dict(ref)) == {
        "artifact_id",
        "media_type",
        "size_bytes",
        "raw_sha256",
    }
    encoded = artifact_ref_to_json(ref)
    assert encoded == EXAMPLE_JCS
    assert artifact_ref_from_json(encoded) == ref
    assert artifact_ref_from_dict(artifact_ref_to_dict(ref)) == ref


@pytest.mark.parametrize(
    ("payload", "match"),
    [(payload, match) for _name, payload, match in ARTIFACT_REF_FAULTS],
    ids=[name for name, _payload, _match in ARTIFACT_REF_FAULTS],
)
@pytest.mark.parametrize("loader", ["from_dict", "from_json"])
def test_backend_ref_rejects_malformed_envelope(
    payload: dict[str, object], match: str, loader: str
) -> None:
    with pytest.raises((ValueError, CanonicalEncodingError), match=match):
        if loader == "from_dict":
            artifact_ref_from_dict(payload)
        else:
            artifact_ref_from_json(json.dumps(payload))


def test_artifact_ref_constructor_rejects_slash_id_as_opaque_bound() -> None:
    with pytest.raises(ValueError, match="a1:"):
        ArtifactRef(
            artifact_id="/tmp/secret.arrow",
            media_type=EXAMPLE_MEDIA_TYPE,
            size_bytes=0,
            raw_sha256=DigestRef("sha256:" + "0" * 64),
        )


def test_raw_sha256_from_bytes_matches_shared_kernel_vector() -> None:
    assert raw_sha256_from_bytes(b"payload").value == RAW_BLOB_PAYLOAD_DIGEST


@pytest.mark.parametrize("vector", json.loads(
    (Path(__file__).resolve().parents[2] / "fixtures/runtime-config/v1/artifact-ids.json").read_bytes()
))
def test_artifact_location_codec_matches_fixed_preimage_vectors(vector: dict[str, object]) -> None:
    from gateway_backend.artifacts.location import ArtifactLocation, build_artifact_id, parse_artifact_id
    location = ArtifactLocation(str(vector["location"]))
    identity = vector["identity_payload"]
    actual = build_artifact_id(location, str(vector["kind"]), identity)
    assert actual == vector["artifact_id"]
    assert parse_artifact_id(actual) is location
    # A physical path is deliberately absent from this complete content key.
    assert build_artifact_id(location, str(vector["kind"]), identity) == actual


@pytest.mark.parametrize("artifact_id", [
    "old-artifact-1", "canonical-table:" + "a" * 64,
    "a1:unknown:" + "a" * 64, "a1:scratch:" + "a" * 64,
    "a1:durable:" + "A" * 64, "a1:durable:" + "a" * 63,
    "a1:durable:" + "a" * 65, "a1:durable:" + "a" * 64 + "/child",
    "a1:durable:" + "a" * 64 + "\n",
])
def test_artifact_location_codec_and_bare_inmemory_lookup_reject_unsupported_ids(artifact_id: str) -> None:
    from gateway_backend.artifacts import InMemoryArtifactStore
    from gateway_backend.artifacts.location import parse_artifact_id
    with pytest.raises(ValueError, match="a1:"):
        parse_artifact_id(artifact_id)
    with pytest.raises(ValueError, match="a1:"):
        InMemoryArtifactStore().get_ref(artifact_id)


def test_canonical_identity_keeps_every_scope_and_projection_input() -> None:
    from dataclasses import replace
    from gateway_backend.artifacts.canonical_table_store import CanonicalTableKey
    key = CanonicalTableKey("repo-1", "3", DigestRef("sha256:" + "1" * 64),
        2, DigestRef("sha256:" + "2" * 64))
    variants = (key, replace(key, repository_id="repo-2"),
        replace(key, storage_projection_version="4"),
        replace(key, business_schema_digest=DigestRef("sha256:" + "3" * 64)),
        replace(key, row_count=3), replace(key, table_digest=DigestRef("sha256:" + "4" * 64)),
        replace(key, canonical_mapping_version=2))
    assert len({variant.artifact_id for variant in variants}) == 7
