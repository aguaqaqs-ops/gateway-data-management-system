"""Private typed stream frame metadata models."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Self

from gateway_repository_contracts._json import JSONValue, decode_wire_mapping, require_mapping_keys
from gateway_repository_contracts._unicode import validate_unicode_string
from gateway_repository_contracts.enums import StoreKind, parse_store_kind
from gateway_repository_contracts.errors import RepositoryContractError, RepositoryContractErrorCode
from gateway_repository_contracts.identities import (
    CommitId,
    CurrentTableGenerationId,
    CursorToken,
    RepositoryId,
    RepositoryIncarnationId,
)

_SHA256_HEX_PATTERN = re.compile(r"^[0-9a-f]{64}$")

_VERSIONED_HEADER_KEYS = frozenset(
    {
        "repository_id",
        "repository_incarnation_id",
        "store_kind",
        "table_name",
        "declared_schema_digest",
        "query_options_digest",
        "snapshot_commit_id",
    }
)
_CURRENT_HEADER_KEYS = frozenset(
    {
        "repository_id",
        "repository_incarnation_id",
        "store_kind",
        "table_name",
        "declared_schema_digest",
        "query_options_digest",
        "current_table_generation_id",
    }
)
_HEADER_REQUIRED = frozenset(
    {
        "repository_id",
        "repository_incarnation_id",
        "store_kind",
        "table_name",
        "declared_schema_digest",
        "query_options_digest",
    }
)
_CHECKPOINT_KEYS = frozenset({"cursor_token"})
_END_KEYS = frozenset({"frames_raw_sha256", "final_row_count"})
_ERROR_KEYS = frozenset({"error_code", "message"})


def _require_str(value: object, *, label: str) -> str:
    if type(value) is not str:
        raise RepositoryContractError(
            RepositoryContractErrorCode.WIRE_INVALID_VALUE,
            f"{label} must be string",
        )
    return value


TABLE_NAME_MAX_SCALARS = 64
TABLE_NAME_MAX_UTF8_BYTES = 256


def validate_table_name(value: object) -> str:
    """Canonical table name: valid Unicode with ASCII A-Z folded to a-z."""
    wire = _require_str(value, label="table_name")
    if wire == "":
        raise RepositoryContractError(
            RepositoryContractErrorCode.WIRE_INVALID_VALUE,
            "table_name must be non-empty",
        )
    validate_unicode_string(wire)
    if len(wire) > TABLE_NAME_MAX_SCALARS:
        raise RepositoryContractError(
            RepositoryContractErrorCode.WIRE_INVALID_VALUE,
            "table_name exceeds maximum scalar count",
        )
    if len(wire.encode("utf-8")) > TABLE_NAME_MAX_UTF8_BYTES:
        raise RepositoryContractError(
            RepositoryContractErrorCode.WIRE_INVALID_VALUE,
            "table_name exceeds maximum UTF-8 byte length",
        )
    return "".join(chr(ord(char) + 32) if "A" <= char <= "Z" else char for char in wire)


def _require_sha256_hex(value: object, *, label: str) -> str:
    wire = _require_str(value, label=label)
    if not _SHA256_HEX_PATTERN.fullmatch(wire):
        raise RepositoryContractError(
            RepositoryContractErrorCode.WIRE_INVALID_VALUE,
            f"{label} must be lowercase SHA-256 hex",
        )
    return wire


def _require_non_negative_int(value: object, *, label: str) -> int:
    if type(value) is not int or isinstance(value, bool) or value < 0:
        raise RepositoryContractError(
            RepositoryContractErrorCode.WIRE_INVALID_VALUE,
            f"{label} must be non-negative integer",
        )
    return value


@dataclass(frozen=True, slots=True)
class VersionedStreamHeaderMetadata:
    repository_id: str
    repository_incarnation_id: str
    table_name: str
    declared_schema_digest: str
    query_options_digest: str
    snapshot_commit_id: str

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "repository_id", RepositoryId.from_wire(self.repository_id).to_wire()
        )
        object.__setattr__(
            self,
            "repository_incarnation_id",
            RepositoryIncarnationId.from_wire(self.repository_incarnation_id).to_wire(),
        )
        object.__setattr__(self, "table_name", validate_table_name(self.table_name))
        _require_sha256_hex(self.declared_schema_digest, label="declared_schema_digest")
        _require_sha256_hex(self.query_options_digest, label="query_options_digest")
        object.__setattr__(
            self,
            "snapshot_commit_id",
            CommitId.from_wire(self.snapshot_commit_id).to_wire(),
        )

    @property
    def store_kind(self) -> StoreKind:
        return StoreKind.VERSIONED

    def to_wire_dict(self) -> dict[str, JSONValue]:
        return {
            "repository_id": self.repository_id,
            "repository_incarnation_id": self.repository_incarnation_id,
            "store_kind": StoreKind.VERSIONED.value,
            "table_name": self.table_name,
            "declared_schema_digest": self.declared_schema_digest,
            "query_options_digest": self.query_options_digest,
            "snapshot_commit_id": self.snapshot_commit_id,
        }

    @classmethod
    def from_wire_dict(cls, value: object) -> Self:
        mapping = decode_wire_mapping(
            value,
            allowed_keys=_VERSIONED_HEADER_KEYS,
            label="versioned_stream_header_metadata",
        )
        require_mapping_keys(mapping, _HEADER_REQUIRED | {"snapshot_commit_id"}, label="header")
        store_kind = parse_store_kind(mapping["store_kind"])
        if store_kind is not StoreKind.VERSIONED:
            raise RepositoryContractError(
                RepositoryContractErrorCode.WIRE_INVALID_VALUE,
                "versioned header requires VERSIONED store_kind",
            )
        return cls(
            repository_id=_require_str(mapping["repository_id"], label="repository_id"),
            repository_incarnation_id=_require_str(
                mapping["repository_incarnation_id"], label="repository_incarnation_id"
            ),
            table_name=_require_str(mapping["table_name"], label="table_name"),
            declared_schema_digest=_require_str(
                mapping["declared_schema_digest"], label="declared_schema_digest"
            ),
            query_options_digest=_require_str(
                mapping["query_options_digest"], label="query_options_digest"
            ),
            snapshot_commit_id=_require_str(
                mapping["snapshot_commit_id"], label="snapshot_commit_id"
            ),
        )


@dataclass(frozen=True, slots=True)
class CurrentStreamHeaderMetadata:
    repository_id: str
    repository_incarnation_id: str
    table_name: str
    declared_schema_digest: str
    query_options_digest: str
    current_table_generation_id: str

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "repository_id", RepositoryId.from_wire(self.repository_id).to_wire()
        )
        object.__setattr__(
            self,
            "repository_incarnation_id",
            RepositoryIncarnationId.from_wire(self.repository_incarnation_id).to_wire(),
        )
        object.__setattr__(self, "table_name", validate_table_name(self.table_name))
        _require_sha256_hex(self.declared_schema_digest, label="declared_schema_digest")
        _require_sha256_hex(self.query_options_digest, label="query_options_digest")
        object.__setattr__(
            self,
            "current_table_generation_id",
            CurrentTableGenerationId.from_wire(self.current_table_generation_id).to_wire(),
        )

    @property
    def store_kind(self) -> StoreKind:
        return StoreKind.CURRENT

    def to_wire_dict(self) -> dict[str, JSONValue]:
        return {
            "repository_id": self.repository_id,
            "repository_incarnation_id": self.repository_incarnation_id,
            "store_kind": StoreKind.CURRENT.value,
            "table_name": self.table_name,
            "declared_schema_digest": self.declared_schema_digest,
            "query_options_digest": self.query_options_digest,
            "current_table_generation_id": self.current_table_generation_id,
        }

    @classmethod
    def from_wire_dict(cls, value: object) -> Self:
        mapping = decode_wire_mapping(
            value,
            allowed_keys=_CURRENT_HEADER_KEYS,
            label="current_stream_header_metadata",
        )
        require_mapping_keys(
            mapping, _HEADER_REQUIRED | {"current_table_generation_id"}, label="header"
        )
        store_kind = parse_store_kind(mapping["store_kind"])
        if store_kind is not StoreKind.CURRENT:
            raise RepositoryContractError(
                RepositoryContractErrorCode.WIRE_INVALID_VALUE,
                "current header requires CURRENT store_kind",
            )
        return cls(
            repository_id=_require_str(mapping["repository_id"], label="repository_id"),
            repository_incarnation_id=_require_str(
                mapping["repository_incarnation_id"], label="repository_incarnation_id"
            ),
            table_name=_require_str(mapping["table_name"], label="table_name"),
            declared_schema_digest=_require_str(
                mapping["declared_schema_digest"], label="declared_schema_digest"
            ),
            query_options_digest=_require_str(
                mapping["query_options_digest"], label="query_options_digest"
            ),
            current_table_generation_id=_require_str(
                mapping["current_table_generation_id"], label="current_table_generation_id"
            ),
        )


StreamHeaderMetadata = VersionedStreamHeaderMetadata | CurrentStreamHeaderMetadata


def decode_stream_header_metadata(value: object) -> StreamHeaderMetadata:
    if not isinstance(value, dict):
        raise RepositoryContractError(
            RepositoryContractErrorCode.WIRE_INVALID_VALUE,
            "header metadata must be object",
        )
    has_snapshot = "snapshot_commit_id" in value
    has_generation = "current_table_generation_id" in value
    if has_snapshot and not has_generation:
        return VersionedStreamHeaderMetadata.from_wire_dict(value)
    if has_generation and not has_snapshot:
        return CurrentStreamHeaderMetadata.from_wire_dict(value)
    raise RepositoryContractError(
        RepositoryContractErrorCode.WIRE_INVALID_VALUE,
        "header requires exactly one snapshot binding",
    )


@dataclass(frozen=True, slots=True)
class StreamCheckpointMetadata:
    cursor_token: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "cursor_token", CursorToken.from_wire(self.cursor_token).to_wire())

    def to_wire_dict(self) -> dict[str, JSONValue]:
        return {"cursor_token": self.cursor_token}

    @classmethod
    def from_wire_dict(cls, value: object) -> Self:
        mapping = decode_wire_mapping(
            value, allowed_keys=_CHECKPOINT_KEYS, label="stream_checkpoint_metadata"
        )
        require_mapping_keys(mapping, _CHECKPOINT_KEYS, label="stream_checkpoint_metadata")
        return cls(cursor_token=_require_str(mapping["cursor_token"], label="cursor_token"))


@dataclass(frozen=True, slots=True)
class StreamEndMetadata:
    frames_raw_sha256: str
    final_row_count: int

    def __post_init__(self) -> None:
        _require_sha256_hex(self.frames_raw_sha256, label="frames_raw_sha256")
        _require_non_negative_int(self.final_row_count, label="final_row_count")

    def to_wire_dict(self) -> dict[str, JSONValue]:
        return {
            "frames_raw_sha256": self.frames_raw_sha256,
            "final_row_count": self.final_row_count,
        }

    @classmethod
    def from_wire_dict(cls, value: object) -> Self:
        mapping = decode_wire_mapping(value, allowed_keys=_END_KEYS, label="stream_end_metadata")
        require_mapping_keys(mapping, _END_KEYS, label="stream_end_metadata")
        return cls(
            frames_raw_sha256=_require_str(mapping["frames_raw_sha256"], label="frames_raw_sha256"),
            final_row_count=_require_non_negative_int(
                mapping["final_row_count"], label="final_row_count"
            ),
        )


@dataclass(frozen=True, slots=True)
class StreamErrorMetadata:
    error_code: str
    message: str | None = None

    def __post_init__(self) -> None:
        if type(self.error_code) is not str or not self.error_code:
            raise RepositoryContractError(
                RepositoryContractErrorCode.WIRE_INVALID_VALUE,
                "error_code must be non-empty string",
            )
        if self.message is not None and (type(self.message) is not str or not self.message):
            raise RepositoryContractError(
                RepositoryContractErrorCode.WIRE_INVALID_VALUE,
                "message must be non-empty string",
            )

    def to_wire_dict(self) -> dict[str, JSONValue]:
        payload: dict[str, JSONValue] = {"error_code": self.error_code}
        if self.message is not None:
            payload["message"] = self.message
        return payload

    @classmethod
    def from_wire_dict(cls, value: object) -> Self:
        mapping = decode_wire_mapping(
            value, allowed_keys=_ERROR_KEYS, label="stream_error_metadata"
        )
        require_mapping_keys(mapping, frozenset({"error_code"}), label="stream_error_metadata")
        message = mapping.get("message")
        if message is not None:
            message = _require_str(message, label="message")
        return cls(
            error_code=_require_str(mapping["error_code"], label="error_code"),
            message=message,
        )


@dataclass(frozen=True, slots=True)
class EmptyFrameMetadata:
    def to_wire_dict(self) -> dict[str, JSONValue]:
        return {}

    @classmethod
    def from_wire_dict(cls, value: object) -> Self:
        mapping = decode_wire_mapping(value, allowed_keys=frozenset(), label="empty_metadata")
        if mapping:
            raise RepositoryContractError(
                RepositoryContractErrorCode.WIRE_INVALID_VALUE,
                "metadata must be empty object",
            )
        return cls()


StreamFrameMetadata = (
    StreamHeaderMetadata
    | StreamCheckpointMetadata
    | StreamEndMetadata
    | StreamErrorMetadata
    | EmptyFrameMetadata
)
