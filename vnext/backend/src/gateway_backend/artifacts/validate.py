"""Fail-closed validation for the minimal BackendArtifactRef."""

from __future__ import annotations

from gateway_shared_kernel import DigestRef

from gateway_backend.artifacts.types import ArtifactRef, validate_artifact_id

_REF_REQUIRED = frozenset({"artifact_id", "media_type", "size_bytes", "raw_sha256"})


def validate_artifact_ref(payload: dict[str, object]) -> None:
    actual = frozenset(payload)
    missing = _REF_REQUIRED - actual
    unknown = actual - _REF_REQUIRED
    if missing:
        raise ValueError(f"ArtifactRef missing fields: {sorted(missing)!r}")
    if unknown:
        raise ValueError(f"ArtifactRef contains unknown fields: {sorted(unknown)!r}")

    artifact_id = payload["artifact_id"]
    if type(artifact_id) is not str:
        raise ValueError("artifact_id must be a string")
    validate_artifact_id(artifact_id)

    media_type = payload["media_type"]
    if type(media_type) is not str or not media_type:
        raise ValueError("media_type must be a non-empty string")

    size_bytes = payload["size_bytes"]
    if type(size_bytes) is not int or size_bytes < 0:
        raise ValueError("size_bytes must be a non-negative integer")

    raw_sha256 = payload["raw_sha256"]
    if type(raw_sha256) is not str:
        raise ValueError("raw_sha256 must be a string")
    DigestRef(raw_sha256)


def validate_artifact_ref_model(ref: ArtifactRef) -> None:
    validate_artifact_ref(
        {
            "artifact_id": ref.artifact_id,
            "media_type": ref.media_type,
            "size_bytes": ref.size_bytes,
            "raw_sha256": ref.raw_sha256.value,
        }
    )
