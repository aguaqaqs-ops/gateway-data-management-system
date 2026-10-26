"""Schema, content, view and manifest digests owned by Storage Projection."""

from __future__ import annotations

import hashlib
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Literal

from gateway_shared_kernel import (
    CollectionSemantics,
    DeclaredType,
    DeclaredTypeKind,
    DigestRef,
    NullScalar,
    SignedIntegerScalar,
    StringScalar,
    TypedScalar,
    UnsignedIntegerScalar,
    encode_collection,
    encode_typed_scalar,
)
from gateway_shared_kernel.jcs import canonicalize_json_value

from gateway_backend.capabilities.storage_projection.contracts import (
    CanonicalizationManifest,
    CanonicalizationManifestTable,
)
from gateway_backend.capabilities.table_rules.contracts import StorageRuleView

MANIFEST_DIGEST_PREFIX = b"gateway-vnext:canonicalization-manifest:v1\0"
_NULL_DECLARED_TYPE = DeclaredType(kind=DeclaredTypeKind.NULL)
_STRING_DECLARED_TYPE = DeclaredType(kind=DeclaredTypeKind.STRING)
_ENUM_SET_HEAD = re.compile(r"^(ENUM|SET)\s*\(", re.IGNORECASE)
CellFamily = Literal["scalar", "enum", "set"]


class CanonicalCellError(ValueError):
    """Raised when a retained cell cannot be encoded as canonical content."""


@dataclass(frozen=True, slots=True)
class CanonicalColumnCodec:
    sql_type: str
    nullable: bool
    family: CellFamily
    declared_type: DeclaredType | None = None
    labels: tuple[str, ...] = ()


def compute_storage_rule_digest(view: StorageRuleView) -> DigestRef:
    payload = {
        "canonical_key_columns": list(view.canonical_key_columns),
        "canonical_key_policy": view.canonical_key_policy.value,
        "canonical_table": view.canonical_table,
        "dropped_columns": [
            {"name": item.name, "reason": item.reason} for item in view.dropped_columns
        ],
        "ordered_policy": view.ordered_policy.value,
        "retained_columns": list(view.retained_columns),
        "structural_columns": list(view.structural_columns),
    }
    return _sha256_jcs(payload)


def compute_schema_digest(
    *,
    columns: Sequence[Mapping[str, object]],
    primary_key: Sequence[str],
) -> DigestRef:
    payload = {
        "columns": [dict(column) for column in columns],
        "primary_key": list(primary_key),
    }
    return _sha256_jcs(payload)


def encode_retained_cell(cell: object, declared_type: DeclaredType) -> bytes:
    return encode_canonical_cell(
        cell,
        CanonicalColumnCodec(
            sql_type="",
            nullable=True,
            family="scalar",
            declared_type=declared_type,
        ),
    )


def encode_canonical_cell(cell: object, codec: CanonicalColumnCodec) -> bytes:
    if codec.family == "enum":
        return _encode_enum_cell(cell, codec.labels)
    if codec.family == "set":
        return _encode_set_cell(cell, codec.labels)
    if codec.declared_type is None:
        raise CanonicalCellError("scalar codec requires declared_type")
    if isinstance(cell, NullScalar):
        return encode_typed_scalar(_NULL_DECLARED_TYPE, cell).scalar_frame
    typed = _coerce_scalar(cell, codec.declared_type)
    return encode_typed_scalar(codec.declared_type, typed).scalar_frame


def classify_enum_set_sql_type(sql_type: str) -> tuple[str, tuple[str, ...]] | None:
    stripped = sql_type.strip()
    match = _ENUM_SET_HEAD.match(stripped)
    if match is None:
        upper = stripped.upper()
        if upper == "ENUM" or upper == "SET" or upper.startswith("ENUM ") or upper.startswith("SET "):
            raise CanonicalCellError("ENUM/SET sql_type is malformed")
        if upper.startswith("ENUM") or upper.startswith("SET"):
            raise CanonicalCellError("ENUM/SET sql_type is malformed")
        return None
    kind = match.group(1).upper()
    labels = _parse_sql_string_list(stripped[match.end() :])
    if kind == "SET" and any(label == "" for label in labels):
        raise CanonicalCellError("SET labels must not be empty")
    return kind, labels


def compute_manifest_digest(manifest: CanonicalizationManifest) -> DigestRef:
    payload = canonicalize_json_value(manifest_document(manifest))
    return DigestRef.from_raw_digest(hashlib.sha256(MANIFEST_DIGEST_PREFIX + payload).digest())


def manifest_document(manifest: CanonicalizationManifest) -> dict[str, Any]:
    return {
        "contract_version": manifest.contract_version,
        "ruleset_digest": manifest.ruleset_digest.value,
        "ruleset_id": manifest.ruleset_id,
        "ruleset_version": manifest.ruleset_version,
        "source_artifact_digest": manifest.source_artifact_digest.value,
        "storage_projection_version": manifest.storage_projection_version,
        "tables": [_manifest_table_document(table) for table in manifest.tables],
    }


def _manifest_table_document(table: CanonicalizationManifestTable) -> dict[str, Any]:
    return {
        "canonical_key_columns": list(table.canonical_key_columns),
        "canonical_key_policy": table.canonical_key_policy.value,
        "canonical_row_count": table.canonical_row_count,
        "canonical_schema_digest": _optional_digest(table.canonical_schema_digest),
        "content_digest": _optional_digest(table.content_digest),
        "dropped_columns": [
            {"name": item.name, "reason": item.reason} for item in table.dropped_columns
        ],
        "gid_pseudo_count": table.gid_pseudo_count,
        "gid_real_count": table.gid_real_count,
        "name": table.name,
        "ordered_policy": table.ordered_policy.value,
        "retained_columns": list(table.retained_columns),
        "source_row_count": table.source_row_count,
        "source_schema_digest": _optional_digest(table.source_schema_digest),
        "structural_columns": list(table.structural_columns),
    }


def _optional_digest(digest: DigestRef | None) -> str | None:
    if digest is None:
        return None
    return digest.value


def _sha256_jcs(payload: Mapping[str, object]) -> DigestRef:
    return DigestRef.from_raw_digest(hashlib.sha256(canonicalize_json_value(dict(payload))).digest())


def _coerce_scalar(cell: object, declared_type: DeclaredType) -> TypedScalar:
    if not isinstance(cell, TypedScalar):
        raise TypeError("cell is not a typed scalar")
    if (
        declared_type.kind is DeclaredTypeKind.UNSIGNED_INTEGER
        and isinstance(cell, SignedIntegerScalar)
    ):
        return UnsignedIntegerScalar(decimal=cell.decimal)
    return cell


def _encode_enum_cell(cell: object, labels: tuple[str, ...]) -> bytes:
    if isinstance(cell, NullScalar):
        return encode_typed_scalar(_NULL_DECLARED_TYPE, cell).scalar_frame
    if not isinstance(cell, StringScalar):
        raise TypeError("ENUM cell must be a string scalar or null")
    if cell.text not in labels:
        raise CanonicalCellError("ENUM value is not a declared label")
    return encode_typed_scalar(_STRING_DECLARED_TYPE, cell).scalar_frame


def _encode_set_cell(cell: object, labels: tuple[str, ...]) -> bytes:
    if isinstance(cell, NullScalar):
        return encode_typed_scalar(_NULL_DECLARED_TYPE, cell).scalar_frame
    members = getattr(cell, "members", None)
    if type(members) is not tuple:
        raise TypeError("SET cell must expose a members tuple or be null")
    declared = {label: index for index, label in enumerate(labels)}
    seen: set[str] = set()
    for index, member in enumerate(members):
        if type(member) is not str:
            raise CanonicalCellError(f"SET member {index} must be str")
        if member not in declared:
            raise CanonicalCellError("SET member is not a declared label")
        if member in seen:
            raise CanonicalCellError("SET members must not repeat")
        seen.add(member)
    item_frames = tuple(
        encode_typed_scalar(_STRING_DECLARED_TYPE, StringScalar(text=label)).scalar_frame
        for label in labels
        if label in seen
    )
    return encode_collection(CollectionSemantics.SEQUENCE, items=item_frames).collection_frame


def _parse_sql_string_list(body: str) -> tuple[str, ...]:
    labels: list[str] = []
    cursor = 0
    length = len(body)
    while True:
        while cursor < length and body[cursor].isspace():
            cursor += 1
        if cursor >= length:
            raise CanonicalCellError("ENUM/SET sql_type is malformed")
        if body[cursor] == ")":
            if labels:
                raise CanonicalCellError("ENUM/SET sql_type is malformed")
            cursor += 1
            break
        if body[cursor] != "'":
            raise CanonicalCellError("ENUM/SET sql_type is malformed")
        cursor += 1
        label_chars: list[str] = []
        while cursor < length:
            char = body[cursor]
            if char == "'":
                if cursor + 1 < length and body[cursor + 1] == "'":
                    label_chars.append("'")
                    cursor += 2
                    continue
                cursor += 1
                break
            label_chars.append(char)
            cursor += 1
        else:
            raise CanonicalCellError("ENUM/SET sql_type is malformed")
        labels.append("".join(label_chars))
        while cursor < length and body[cursor].isspace():
            cursor += 1
        if cursor >= length:
            raise CanonicalCellError("ENUM/SET sql_type is malformed")
        if body[cursor] == ",":
            cursor += 1
            continue
        if body[cursor] == ")":
            cursor += 1
            break
        raise CanonicalCellError("ENUM/SET sql_type is malformed")
    while cursor < length and body[cursor].isspace():
        cursor += 1
    if cursor != length:
        raise CanonicalCellError("ENUM/SET sql_type is malformed")
    if not labels:
        raise CanonicalCellError("ENUM/SET sql_type is malformed")
    return tuple(labels)
