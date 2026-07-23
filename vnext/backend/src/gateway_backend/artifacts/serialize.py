"""Artifact JCS serialization and strict parsing."""

from __future__ import annotations

import json
from collections.abc import Callable

from gateway_shared_kernel import DigestRef, canonicalize_jcs
from gateway_shared_kernel.jcs import canonicalize_json_value

from gateway_backend.artifacts.digest import raw_sha256_from_bytes
from gateway_backend.artifacts.types import (
    AccessMetadata,
    ArtifactContentManifest,
    ArtifactManifest,
    ArtifactRef,
    ContentContract,
    RetentionClass,
    assert_no_host_path_identity,
)
from gateway_backend.artifacts.validate import (
    validate_artifact_manifest,
    validate_artifact_ref,
)

ContentParser = Callable[[dict[str, object]], ArtifactContentManifest]


def artifact_ref_to_dict(ref: ArtifactRef) -> dict[str, object]:
    payload: dict[str, object] = {
        "artifact_ref_schema_version": ref.artifact_ref_schema_version,
        "logical_ref": ref.logical_ref,
        "media_type": ref.media_type,
        "size_bytes": ref.size_bytes,
        "raw_sha256": ref.raw_sha256.value,
        "content_digest": ref.content_digest.value,
        "content_contract": {
            "contract_id": ref.content_contract.contract_id,
            "semantic_version": ref.content_contract.semantic_version,
        },
        "content_schema_id": ref.content_schema_id,
        "retention_class": ref.retention_class.value,
        "access_metadata": _access_metadata_to_dict(ref.access_metadata),
    }
    assert_no_host_path_identity(payload)
    return payload


def artifact_ref_from_dict(payload: dict[str, object]) -> ArtifactRef:
    assert_no_host_path_identity(payload)
    validate_artifact_ref(payload)
    return ArtifactRef(
        artifact_ref_schema_version=_require_integer(payload, "artifact_ref_schema_version"),
        logical_ref=_require_string(payload, "logical_ref"),
        media_type=_require_string(payload, "media_type"),
        size_bytes=_require_integer(payload, "size_bytes"),
        raw_sha256=DigestRef(_require_string(payload, "raw_sha256")),
        content_digest=DigestRef(_require_string(payload, "content_digest")),
        content_contract=_content_contract_from_payload(
            _require_object(payload, "content_contract")
        ),
        content_schema_id=_require_string(payload, "content_schema_id"),
        retention_class=RetentionClass(_require_string(payload, "retention_class")),
        access_metadata=_access_metadata_from_dict(_require_object(payload, "access_metadata")),
    )


def artifact_manifest_to_dict(
    manifest: ArtifactManifest,
) -> dict[str, object]:
    payload: dict[str, object] = {
        "manifest_schema_version": manifest.manifest_schema_version,
        "logical_ref": manifest.logical_ref,
        "media_type": manifest.media_type,
        "size_bytes": manifest.size_bytes,
        "raw_sha256": manifest.raw_sha256.value,
        "content_digest": manifest.content_digest.value,
        "content_contract": {
            "contract_id": manifest.content_contract.contract_id,
            "semantic_version": manifest.content_contract.semantic_version,
        },
        "content_schema_id": manifest.content_schema_id,
        "retention_class": manifest.retention_class.value,
        "access_metadata": _access_metadata_to_dict(manifest.access_metadata),
        "content": manifest.content.to_wire_dict(),
    }
    assert_no_host_path_identity(payload)
    return payload


def artifact_manifest_from_dict(
    payload: dict[str, object],
    *,
    content_parser: ContentParser,
) -> ArtifactManifest:
    assert_no_host_path_identity(payload)
    validate_artifact_manifest(payload)
    content = content_parser(_require_object(payload, "content"))
    return ArtifactManifest(
        manifest_schema_version=_require_integer(payload, "manifest_schema_version"),
        logical_ref=_require_string(payload, "logical_ref"),
        media_type=_require_string(payload, "media_type"),
        size_bytes=_require_integer(payload, "size_bytes"),
        raw_sha256=DigestRef(_require_string(payload, "raw_sha256")),
        content_digest=DigestRef(_require_string(payload, "content_digest")),
        content_contract=_content_contract_from_payload(
            _require_object(payload, "content_contract")
        ),
        content_schema_id=_require_string(payload, "content_schema_id"),
        retention_class=RetentionClass(_require_string(payload, "retention_class")),
        access_metadata=_access_metadata_from_dict(_require_object(payload, "access_metadata")),
        content=content,
    )


def build_manifest(
    *,
    logical_ref: str,
    raw_bytes: bytes,
    content: ArtifactContentManifest,
    retention_class: RetentionClass,
    access_metadata: AccessMetadata = AccessMetadata(),
) -> ArtifactManifest:
    raw_sha256 = raw_sha256_from_bytes(raw_bytes)
    return ArtifactManifest(
        manifest_schema_version=1,
        logical_ref=logical_ref,
        media_type=content.media_type,
        size_bytes=len(raw_bytes),
        raw_sha256=raw_sha256,
        content_digest=content.semantic_content_digest,
        content_contract=ContentContract(
            contract_id=content.contract_binding.contract_id,
            semantic_version=content.contract_binding.semantic_version,
        ),
        content_schema_id=content.content_schema_id,
        retention_class=retention_class,
        access_metadata=access_metadata,
        content=content,
    )


def artifact_ref_to_json(ref: ArtifactRef) -> str:
    return _to_jcs_text(artifact_ref_to_dict(ref))


def artifact_ref_from_json(data: str | bytes) -> ArtifactRef:
    return artifact_ref_from_dict(_loads_strict_jcs_object(data))


def artifact_manifest_to_json(manifest: ArtifactManifest) -> str:
    return _to_jcs_text(artifact_manifest_to_dict(manifest))


def artifact_manifest_from_json(
    data: str | bytes,
    *,
    content_parser: ContentParser,
) -> ArtifactManifest:
    return artifact_manifest_from_dict(
        _loads_strict_jcs_object(data), content_parser=content_parser
    )


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


def _to_jcs_text(payload: dict[str, object]) -> str:
    return canonicalize_json_value(payload).decode("utf-8")


def _content_contract_from_payload(payload: dict[str, object]) -> ContentContract:
    return ContentContract(
        contract_id=_require_string(payload, "contract_id"),
        semantic_version=_require_string(payload, "semantic_version"),
    )


def _access_metadata_to_dict(metadata: AccessMetadata) -> dict[str, object]:
    return {"resolver": metadata.resolver.value}


def _access_metadata_from_dict(payload: dict[str, object]) -> AccessMetadata:
    from gateway_backend.artifacts.types import ArtifactResolver

    return AccessMetadata(resolver=ArtifactResolver(_require_string(payload, "resolver")))


def _require_object(payload: dict[str, object], key: str) -> dict[str, object]:
    value = payload[key]
    if not isinstance(value, dict):
        raise ValueError(f"{key} must be an object")
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
