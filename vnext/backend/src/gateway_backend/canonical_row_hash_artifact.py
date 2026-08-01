"""Canonical Row Hash capability-owned artifact content metadata."""

from __future__ import annotations

import re
from dataclasses import dataclass

from gateway_shared_kernel import DigestRef

CANONICAL_ROW_HASHES_MEDIA_TYPE = "application/vnd.apache.arrow.stream"
CANONICAL_ROW_HASHES_CONTENT_SCHEMA_ID = (
    "gateway-vnext.canonical-row-hash.canonical-row-hashes-artifact.v2"
)
CANONICAL_ROW_HASH_BOUNDARY_VERSION = 2
CANONICAL_ENCODING_VERSION = 1
ARROW_MAPPING_VERSION = 1
_CANONICAL_UNSIGNED_DECIMAL = re.compile(r"^(?:0|[1-9][0-9]*)$")


@dataclass(frozen=True, slots=True, eq=False)
class CanonicalRowHashesArtifactMetadata:
    """Semantic result metadata kept with the capability-owned artifact."""

    content_schema_id: str
    media_type: str
    boundary_version: int
    canonical_encoding_version: int
    arrow_mapping_version: int
    raw_content_digest: DigestRef
    table_schema_digest: DigestRef
    row_count: str

    def __post_init__(self) -> None:
        if self.content_schema_id != CANONICAL_ROW_HASHES_CONTENT_SCHEMA_ID:
            raise ValueError("content_schema_id mismatch")
        if self.media_type != CANONICAL_ROW_HASHES_MEDIA_TYPE:
            raise ValueError("media_type mismatch")
        if self.boundary_version != CANONICAL_ROW_HASH_BOUNDARY_VERSION:
            raise ValueError("boundary_version must be 2")
        if self.canonical_encoding_version != CANONICAL_ENCODING_VERSION:
            raise ValueError("canonical_encoding_version must be 1")
        if self.arrow_mapping_version != ARROW_MAPPING_VERSION:
            raise ValueError("arrow_mapping_version must be 1")
        if type(self.raw_content_digest) is not DigestRef:
            raise ValueError("raw_content_digest must be DigestRef")
        if type(self.table_schema_digest) is not DigestRef:
            raise ValueError("table_schema_digest must be DigestRef")
        if not _CANONICAL_UNSIGNED_DECIMAL.fullmatch(self.row_count):
            raise ValueError("row_count must be a canonical unsigned decimal string")

    @property
    def semantic_content_digest(self) -> DigestRef:
        return self.raw_content_digest

    @property
    def identity_key(self) -> tuple[object, ...]:
        return (
            self.content_schema_id,
            self.media_type,
            self.boundary_version,
            self.canonical_encoding_version,
            self.arrow_mapping_version,
            self.raw_content_digest.value,
            self.table_schema_digest.value,
            self.row_count,
        )

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, CanonicalRowHashesArtifactMetadata):
            return NotImplemented
        return self.identity_key == other.identity_key

    @classmethod
    def create(
        cls,
        *,
        raw_content_digest: DigestRef,
        table_schema_digest: DigestRef,
        row_count: str,
    ) -> CanonicalRowHashesArtifactMetadata:
        return cls(
            content_schema_id=CANONICAL_ROW_HASHES_CONTENT_SCHEMA_ID,
            media_type=CANONICAL_ROW_HASHES_MEDIA_TYPE,
            boundary_version=CANONICAL_ROW_HASH_BOUNDARY_VERSION,
            canonical_encoding_version=CANONICAL_ENCODING_VERSION,
            arrow_mapping_version=ARROW_MAPPING_VERSION,
            raw_content_digest=raw_content_digest,
            table_schema_digest=table_schema_digest,
            row_count=row_count,
        )

    def to_wire_dict(self) -> dict[str, object]:
        return {
            "content_schema_id": self.content_schema_id,
            "media_type": self.media_type,
            "boundary_version": self.boundary_version,
            "canonical_encoding_version": self.canonical_encoding_version,
            "arrow_mapping_version": self.arrow_mapping_version,
            "raw_content_digest": self.raw_content_digest.value,
            "table_schema_digest": self.table_schema_digest.value,
            "row_count": self.row_count,
        }

    @classmethod
    def from_wire_dict(cls, payload: dict[str, object]) -> CanonicalRowHashesArtifactMetadata:
        _validate_wire_dict(payload)
        return cls(
            content_schema_id=_require_string(payload, "content_schema_id"),
            media_type=_require_string(payload, "media_type"),
            boundary_version=_require_integer(payload, "boundary_version"),
            canonical_encoding_version=_require_integer(payload, "canonical_encoding_version"),
            arrow_mapping_version=_require_integer(payload, "arrow_mapping_version"),
            raw_content_digest=DigestRef(_require_string(payload, "raw_content_digest")),
            table_schema_digest=DigestRef(_require_string(payload, "table_schema_digest")),
            row_count=_require_string(payload, "row_count"),
        )


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


def _validate_wire_dict(payload: dict[str, object]) -> None:
    expected = {
        "content_schema_id",
        "media_type",
        "boundary_version",
        "canonical_encoding_version",
        "arrow_mapping_version",
        "raw_content_digest",
        "table_schema_digest",
        "row_count",
    }
    if set(payload) != expected:
        raise ValueError("canonical row-hash content fields do not match v2 schema")
    if _require_string(payload, "content_schema_id") != CANONICAL_ROW_HASHES_CONTENT_SCHEMA_ID:
        raise ValueError("content_schema_id mismatch")
    if _require_string(payload, "media_type") != CANONICAL_ROW_HASHES_MEDIA_TYPE:
        raise ValueError("media_type mismatch")
    if _require_integer(payload, "boundary_version") != CANONICAL_ROW_HASH_BOUNDARY_VERSION:
        raise ValueError("boundary_version must be 2")
    if _require_integer(payload, "canonical_encoding_version") != CANONICAL_ENCODING_VERSION:
        raise ValueError("canonical_encoding_version must be 1")
    if _require_integer(payload, "arrow_mapping_version") != ARROW_MAPPING_VERSION:
        raise ValueError("arrow_mapping_version must be 1")
    DigestRef(_require_string(payload, "raw_content_digest"))
    DigestRef(_require_string(payload, "table_schema_digest"))
    if not _CANONICAL_UNSIGNED_DECIMAL.fullmatch(_require_string(payload, "row_count")):
        raise ValueError("row_count must be a canonical unsigned decimal string")
