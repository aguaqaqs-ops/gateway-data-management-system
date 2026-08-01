"""JCS serialization for the minimal BackendArtifactRef."""

from __future__ import annotations

import json

from gateway_shared_kernel import DigestRef, canonicalize_jcs
from gateway_shared_kernel.jcs import canonicalize_json_value

from gateway_backend.artifacts.types import ArtifactRef, assert_no_host_path_identity
from gateway_backend.artifacts.validate import validate_artifact_ref


def artifact_ref_to_dict(ref: ArtifactRef) -> dict[str, object]:
    payload: dict[str, object] = {
        "artifact_id": ref.artifact_id,
        "media_type": ref.media_type,
        "size_bytes": ref.size_bytes,
        "raw_sha256": ref.raw_sha256.value,
    }
    assert_no_host_path_identity(payload)
    return payload


def artifact_ref_from_dict(payload: dict[str, object]) -> ArtifactRef:
    assert_no_host_path_identity(payload)
    validate_artifact_ref(payload)
    return ArtifactRef(
        artifact_id=_require_string(payload, "artifact_id"),
        media_type=_require_string(payload, "media_type"),
        size_bytes=_require_integer(payload, "size_bytes"),
        raw_sha256=DigestRef(_require_string(payload, "raw_sha256")),
    )


def artifact_ref_to_json(ref: ArtifactRef) -> str:
    return canonicalize_json_value(artifact_ref_to_dict(ref)).decode("utf-8")


def artifact_ref_from_json(data: str | bytes) -> ArtifactRef:
    return artifact_ref_from_dict(_loads_strict_jcs_object(data))


def _loads_strict_jcs_object(data: str | bytes) -> dict[str, object]:
    if isinstance(data, str):
        try:
            raw = data.encode("utf-8", errors="strict")
        except UnicodeEncodeError as exc:
            raise ValueError("artifact JSON contains invalid Unicode") from exc
    elif isinstance(data, bytes):
        raw = data
    else:
        raise TypeError("artifact JSON must be str or bytes")
    canonical = canonicalize_jcs(raw)
    value = json.loads(canonical)
    if not isinstance(value, dict):
        raise ValueError("artifact JSON document must be an object")
    if not all(type(key) is str for key in value):
        raise ValueError("artifact JSON object keys must be strings")
    return value


def _require_string(payload: dict[str, object], key: str) -> str:
    value = payload[key]
    if type(value) is not str:
        raise ValueError(f"{key} must be a string")
    return value


def _require_integer(payload: dict[str, object], key: str) -> int:
    value = payload[key]
    if type(value) is not int:
        raise ValueError(f"{key} must be an integer")
    return value
