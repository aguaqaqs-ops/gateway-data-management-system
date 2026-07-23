"""Fail-closed runtime validators for artifact wire formats.

JSON Schema files remain the language-neutral wire authority. These validators
mirror their closed v1 acceptance set without making production parsing depend
on repository-relative schema files or the development-only ``jsonschema``
package.
"""

from __future__ import annotations

import re

from gateway_shared_kernel import DigestRef

from gateway_backend.artifacts.types import (
    IJSON_MAX_SAFE_INTEGER,
    ArtifactResolver,
    RetentionClass,
    validate_logical_ref,
)

_REF_REQUIRED = frozenset(
    {
        "artifact_ref_schema_version",
        "logical_ref",
        "media_type",
        "size_bytes",
        "raw_sha256",
        "content_digest",
        "content_contract",
        "content_schema_id",
        "retention_class",
        "access_metadata",
    }
)
_MANIFEST_REQUIRED = frozenset(
    {
        "manifest_schema_version",
        "logical_ref",
        "media_type",
        "size_bytes",
        "raw_sha256",
        "content_digest",
        "content_contract",
        "content_schema_id",
        "retention_class",
        "access_metadata",
        "content",
    }
)
_CONTRACT_KEYS = frozenset({"contract_id", "semantic_version"})
_ACCESS_KEYS = frozenset({"resolver"})
_SEMVER = re.compile(r"^[0-9]+\.[0-9]+\.[0-9]+$")


def validate_artifact_ref(payload: dict[str, object]) -> None:
    _validate_exact_keys(payload, _REF_REQUIRED, "ArtifactRef")
    _require_const_integer(payload, "artifact_ref_schema_version", 1)
    _validate_envelope_fields(payload)


def validate_artifact_manifest(payload: dict[str, object]) -> None:
    _validate_exact_keys(payload, _MANIFEST_REQUIRED, "ArtifactManifest")
    _require_const_integer(payload, "manifest_schema_version", 1)
    _validate_envelope_fields(payload)
    _require_object(payload, "content")


def _validate_envelope_fields(payload: dict[str, object]) -> None:
    logical_ref = _require_string(payload, "logical_ref")
    validate_logical_ref(logical_ref)
    media_type = _require_string(payload, "media_type")
    if not media_type:
        raise ValueError("media_type must be non-empty")
    size_bytes = _require_integer(payload, "size_bytes")
    if size_bytes < 0 or size_bytes > IJSON_MAX_SAFE_INTEGER:
        raise ValueError("size_bytes must be a non-negative I-JSON safe integer")
    _require_digest(payload, "raw_sha256")
    _require_digest(payload, "content_digest")
    content_contract = _require_object(payload, "content_contract")
    _validate_exact_keys(content_contract, _CONTRACT_KEYS, "content_contract")
    contract_id = _require_string(content_contract, "contract_id")
    if not contract_id:
        raise ValueError("content_contract.contract_id must be non-empty")
    semantic_version = _require_string(content_contract, "semantic_version")
    if not _SEMVER.fullmatch(semantic_version):
        raise ValueError("content_contract.semantic_version must be semver")
    content_schema_id = _require_string(payload, "content_schema_id")
    if not content_schema_id:
        raise ValueError("content_schema_id must be non-empty")
    retention = _require_string(payload, "retention_class")
    try:
        RetentionClass(retention)
    except ValueError as exc:
        raise ValueError("unknown retention_class") from exc
    access = _require_object(payload, "access_metadata")
    _validate_exact_keys(access, _ACCESS_KEYS, "access_metadata")
    resolver = _require_string(access, "resolver")
    try:
        ArtifactResolver(resolver)
    except ValueError as exc:
        raise ValueError("unknown access_metadata.resolver") from exc


def _validate_exact_keys(payload: dict[str, object], expected: frozenset[str], label: str) -> None:
    actual = frozenset(payload)
    missing = expected - actual
    unknown = actual - expected
    if missing:
        raise ValueError(f"{label} missing fields: {sorted(missing)!r}")
    if unknown:
        raise ValueError(f"{label} contains unknown fields: {sorted(unknown)!r}")


def _require_object(payload: dict[str, object], key: str) -> dict[str, object]:
    value = payload[key]
    if not isinstance(value, dict):
        raise ValueError(f"{key} must be an object")
    if not all(type(member) is str for member in value):
        raise ValueError(f"{key} member names must be strings")
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


def _require_digest(payload: dict[str, object], key: str) -> None:
    DigestRef(_require_string(payload, key))


def _require_const_integer(payload: dict[str, object], key: str, expected: int) -> None:
    if _require_integer(payload, key) != expected:
        raise ValueError(f"{key} must be {expected}")
