"""Minimal ArtifactRef envelope round-trip and invalid-shape conformance."""

from __future__ import annotations

import json

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

EXAMPLE_ARTIFACT_ID = "canonical-row-hash-example-0001"
EXAMPLE_MEDIA_TYPE = "application/vnd.apache.arrow.stream"
EXAMPLE_RAW_SHA256 = "sha256:" + "a" * 64
EXAMPLE_JCS = (
    '{"artifact_id":"canonical-row-hash-example-0001",'
    '"media_type":"application/vnd.apache.arrow.stream",'
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
    with pytest.raises(ValueError, match="bounded opaque"):
        ArtifactRef(
            artifact_id="/tmp/secret.arrow",
            media_type=EXAMPLE_MEDIA_TYPE,
            size_bytes=0,
            raw_sha256=DigestRef("sha256:" + "0" * 64),
        )


def test_raw_sha256_from_bytes_matches_shared_kernel_vector() -> None:
    assert raw_sha256_from_bytes(b"payload").value == RAW_BLOB_PAYLOAD_DIGEST
