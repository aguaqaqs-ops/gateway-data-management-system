"""Canonical Row Hash capability-owned artifact content contract."""

from __future__ import annotations

import re
from dataclasses import dataclass

from gateway_shared_kernel import DigestRef

from gateway_backend.artifacts.contracts import CANONICAL_ROW_HASHES_ARTIFACT
from gateway_backend.artifacts.types import ContractBinding

_CONTENT_SCHEMA_ID = CANONICAL_ROW_HASHES_ARTIFACT.content_schema_id
_MEDIA_TYPE = CANONICAL_ROW_HASHES_ARTIFACT.media_type
_CANONICAL_UNSIGNED_DECIMAL = re.compile(r"^(?:0|[1-9][0-9]*)$")


@dataclass(frozen=True, slots=True, eq=False)
class CanonicalRowHashesArtifactManifest:
    content_schema_id: str
    media_type: str
    raw_content_digest: DigestRef
    table_schema_digest: DigestRef
    canonical_encoding_version: int
    arrow_mapping_schema_version: int
    contract_binding: ContractBinding
    result_schema_version: int
    row_count: str

    def __post_init__(self) -> None:
        if self.content_schema_id != _CONTENT_SCHEMA_ID:
            raise ValueError(f"content_schema_id must be {_CONTENT_SCHEMA_ID!r}")
        if self.media_type != _MEDIA_TYPE:
            raise ValueError(f"media_type must be {_MEDIA_TYPE!r}")
        if type(self.raw_content_digest) is not DigestRef:
            raise ValueError("raw_content_digest must be DigestRef")
        if type(self.table_schema_digest) is not DigestRef:
            raise ValueError("table_schema_digest must be DigestRef")
        if type(self.contract_binding) is not ContractBinding:
            raise ValueError("contract_binding must be ContractBinding")
        if type(self.canonical_encoding_version) is not int:
            raise ValueError("canonical_encoding_version must be an integer")
        if self.canonical_encoding_version != 1:
            raise ValueError("canonical_encoding_version must be 1")
        if type(self.arrow_mapping_schema_version) is not int:
            raise ValueError("arrow_mapping_schema_version must be an integer")
        if self.arrow_mapping_schema_version != 1:
            raise ValueError("arrow_mapping_schema_version must be 1")
        if self.contract_binding.contract_id != CANONICAL_ROW_HASHES_ARTIFACT.contract_id:
            raise ValueError("contract_binding.contract_id mismatch")
        if self.contract_binding.semantic_version != CANONICAL_ROW_HASHES_ARTIFACT.semantic_version:
            raise ValueError("contract_binding.semantic_version mismatch")
        if type(self.result_schema_version) is not int:
            raise ValueError("result_schema_version must be an integer")
        if self.result_schema_version != 1:
            raise ValueError("result_schema_version must be 1")
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
            self.raw_content_digest.value,
            self.table_schema_digest.value,
            self.canonical_encoding_version,
            self.arrow_mapping_schema_version,
            self.contract_binding.contract_id,
            self.contract_binding.semantic_version,
            self.result_schema_version,
            self.row_count,
        )

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, CanonicalRowHashesArtifactManifest):
            return NotImplemented
        return self.identity_key == other.identity_key

    @classmethod
    def create(
        cls,
        *,
        raw_content_digest: DigestRef,
        table_schema_digest: DigestRef,
        row_count: str,
    ) -> CanonicalRowHashesArtifactManifest:
        return cls(
            content_schema_id=_CONTENT_SCHEMA_ID,
            media_type=_MEDIA_TYPE,
            raw_content_digest=raw_content_digest,
            table_schema_digest=table_schema_digest,
            canonical_encoding_version=1,
            arrow_mapping_schema_version=1,
            contract_binding=ContractBinding(
                contract_id=CANONICAL_ROW_HASHES_ARTIFACT.contract_id,
                semantic_version=CANONICAL_ROW_HASHES_ARTIFACT.semantic_version,
            ),
            result_schema_version=1,
            row_count=row_count,
        )

    def to_wire_dict(self) -> dict[str, object]:
        return {
            "content_schema_id": self.content_schema_id,
            "media_type": self.media_type,
            "raw_content_digest": self.raw_content_digest.value,
            "table_schema_digest": self.table_schema_digest.value,
            "canonical_encoding_version": self.canonical_encoding_version,
            "arrow_mapping_schema_version": self.arrow_mapping_schema_version,
            "contract_binding": {
                "contract_id": self.contract_binding.contract_id,
                "semantic_version": self.contract_binding.semantic_version,
            },
            "result_schema_version": self.result_schema_version,
            "row_count": self.row_count,
        }

    @classmethod
    def from_wire_dict(cls, payload: dict[str, object]) -> CanonicalRowHashesArtifactManifest:
        _validate_wire_dict(payload)
        contract_binding = payload["contract_binding"]
        if not isinstance(contract_binding, dict):
            raise ValueError("contract_binding must be an object")
        return cls(
            content_schema_id=_require_string(payload, "content_schema_id"),
            media_type=_require_string(payload, "media_type"),
            raw_content_digest=DigestRef(_require_string(payload, "raw_content_digest")),
            table_schema_digest=DigestRef(_require_string(payload, "table_schema_digest")),
            canonical_encoding_version=_require_integer(payload, "canonical_encoding_version"),
            arrow_mapping_schema_version=_require_integer(payload, "arrow_mapping_schema_version"),
            contract_binding=ContractBinding(
                contract_id=_require_string(contract_binding, "contract_id"),
                semantic_version=_require_string(contract_binding, "semantic_version"),
            ),
            result_schema_version=_require_integer(payload, "result_schema_version"),
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
        "raw_content_digest",
        "table_schema_digest",
        "canonical_encoding_version",
        "arrow_mapping_schema_version",
        "contract_binding",
        "result_schema_version",
        "row_count",
    }
    if set(payload) != expected:
        raise ValueError("canonical row-hash content fields do not match v1 schema")
    if _require_string(payload, "content_schema_id") != _CONTENT_SCHEMA_ID:
        raise ValueError("content_schema_id mismatch")
    if _require_string(payload, "media_type") != _MEDIA_TYPE:
        raise ValueError("media_type mismatch")
    DigestRef(_require_string(payload, "raw_content_digest"))
    DigestRef(_require_string(payload, "table_schema_digest"))
    if _require_integer(payload, "canonical_encoding_version") != 1:
        raise ValueError("canonical_encoding_version must be 1")
    if _require_integer(payload, "arrow_mapping_schema_version") != 1:
        raise ValueError("arrow_mapping_schema_version must be 1")
    if _require_integer(payload, "result_schema_version") != 1:
        raise ValueError("result_schema_version must be 1")
    row_count = _require_string(payload, "row_count")
    if not _CANONICAL_UNSIGNED_DECIMAL.fullmatch(row_count):
        raise ValueError("row_count must be a canonical unsigned decimal string")
    binding = payload["contract_binding"]
    if not isinstance(binding, dict) or set(binding) != {
        "contract_id",
        "semantic_version",
    }:
        raise ValueError("contract_binding fields do not match v1 schema")
    if _require_string(binding, "contract_id") != CANONICAL_ROW_HASHES_ARTIFACT.contract_id:
        raise ValueError("contract_binding.contract_id mismatch")
    if (
        _require_string(binding, "semantic_version")
        != CANONICAL_ROW_HASHES_ARTIFACT.semantic_version
    ):
        raise ValueError("contract_binding.semantic_version mismatch")
