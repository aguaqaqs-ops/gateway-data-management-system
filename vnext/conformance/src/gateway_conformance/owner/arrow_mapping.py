"""Arrow Mapping v1 physical schema cross-check (fail-closed)."""

from __future__ import annotations

from typing import Any

import pyarrow as pa

from gateway_conformance.errors import ConformanceValidationError
from gateway_shared_kernel import DeclaredType, DeclaredTypeKind, canonicalize_identifier


def declared_type_from_json(semantic_type: dict[str, Any]) -> DeclaredType:
    kind = str(semantic_type["kind"])
    if kind == "null":
        return DeclaredType(kind=DeclaredTypeKind.NULL)
    if kind == "boolean":
        return DeclaredType(kind=DeclaredTypeKind.BOOLEAN)
    if kind == "signed-integer":
        return DeclaredType(kind=DeclaredTypeKind.SIGNED_INTEGER, bits=int(semantic_type["bits"]))
    if kind == "unsigned-integer":
        return DeclaredType(kind=DeclaredTypeKind.UNSIGNED_INTEGER, bits=int(semantic_type["bits"]))
    if kind == "decimal":
        return DeclaredType(
            kind=DeclaredTypeKind.DECIMAL,
            precision=int(semantic_type["precision"]),
            scale=int(semantic_type["scale"]),
        )
    if kind == "float32":
        return DeclaredType(kind=DeclaredTypeKind.FLOAT32)
    if kind == "float64":
        return DeclaredType(kind=DeclaredTypeKind.FLOAT64)
    if kind == "string":
        return DeclaredType(kind=DeclaredTypeKind.STRING)
    if kind == "binary":
        return DeclaredType(kind=DeclaredTypeKind.BINARY)
    raise ConformanceValidationError(f"unsupported semantic_type kind for oracle: {kind}")


_EXTENSION_NAME_KEY = "ARROW:extension:name"
_EXTENSION_METADATA_KEY = "ARROW:extension:metadata"


def _normalize_metadata(metadata: Any) -> dict[str, str]:
    if not metadata:
        return {}
    normalized: dict[str, str] = {}
    for key, value in metadata.items():
        key_text = key.decode("utf-8") if isinstance(key, bytes) else str(key)
        if isinstance(value, bytes):
            value_text = value.decode("utf-8")
        else:
            value_text = str(value)
        normalized[key_text] = value_text
    return normalized


def _has_extension_metadata(metadata: dict[str, str]) -> bool:
    return _EXTENSION_NAME_KEY in metadata or _EXTENSION_METADATA_KEY in metadata


def _is_rejected_type(data_type: pa.DataType) -> bool:
    import pyarrow.types as pat

    if pat.is_large_string(data_type) or pat.is_large_binary(data_type):
        return True
    if pat.is_string_view(data_type) or pat.is_binary_view(data_type):
        return True
    if pat.is_dictionary(data_type) or pat.is_union(data_type):
        return True
    if pat.is_list(data_type) or pat.is_large_list(data_type):
        return True
    if pat.is_fixed_size_list(data_type) or pat.is_struct(data_type) or pat.is_map(data_type):
        return True
    if pat.is_run_end_encoded(data_type):
        return True
    if pat.is_timestamp(data_type):
        unit = data_type.unit
        tz = data_type.tz
        if unit != "us":
            return True
        return tz is not None and str(tz) != "UTC"
    if pat.is_duration(data_type):
        return bool(data_type.unit != "us")
    if pat.is_date64(data_type):
        return True
    if pat.is_time(data_type) or pat.is_interval(data_type):
        return True
    return False


def _check_mapping(
    declared_kind: DeclaredTypeKind,
    data_type: pa.DataType,
    *,
    bits: int | None,
    precision: int | None,
    scale: int | None,
) -> bool:
    import pyarrow.types as pat

    if _is_rejected_type(data_type):
        return False
    if declared_kind is DeclaredTypeKind.NULL:
        return bool(pat.is_null(data_type))
    if declared_kind is DeclaredTypeKind.BOOLEAN:
        return bool(pat.is_boolean(data_type))
    if declared_kind is DeclaredTypeKind.SIGNED_INTEGER:
        if bits == 8:
            return bool(pat.is_int8(data_type))
        if bits == 16:
            return bool(pat.is_int16(data_type))
        if bits == 24:
            return bool(pat.is_int32(data_type))
        if bits == 32:
            return bool(pat.is_int32(data_type))
        if bits == 64:
            return bool(pat.is_int64(data_type))
        return False
    if declared_kind is DeclaredTypeKind.UNSIGNED_INTEGER:
        if bits == 8:
            return bool(pat.is_uint8(data_type))
        if bits == 16:
            return bool(pat.is_uint16(data_type))
        if bits == 24:
            return bool(pat.is_uint32(data_type))
        if bits == 32:
            return bool(pat.is_uint32(data_type))
        if bits == 64:
            return bool(pat.is_uint64(data_type))
        return False
    if declared_kind is DeclaredTypeKind.DECIMAL:
        if precision is None or scale is None:
            return False
        if precision <= 38:
            if not pat.is_decimal128(data_type):
                return False
        elif precision <= 65:
            if not pat.is_decimal256(data_type):
                return False
        else:
            return False
        return int(data_type.precision) == precision and int(data_type.scale) == scale
    if declared_kind is DeclaredTypeKind.FLOAT32:
        return bool(pat.is_float32(data_type))
    if declared_kind is DeclaredTypeKind.FLOAT64:
        return bool(pat.is_float64(data_type))
    if declared_kind is DeclaredTypeKind.STRING:
        return bool(pat.is_string(data_type))
    if declared_kind is DeclaredTypeKind.BINARY:
        return bool(pat.is_binary(data_type))
    return False


def _schemas_equal(left: pa.Schema, right: pa.Schema) -> bool:
    if len(left) != len(right):
        return False
    if left.metadata != right.metadata:
        return False
    for lf, rf in zip(left, right, strict=True):
        if lf.name != rf.name or lf.type != rf.type or lf.nullable != rf.nullable:
            return False
        if lf.metadata != rf.metadata:
            return False
    return True


def cross_check_stream_schema(
    declared_fields: list[dict[str, Any]], stream_schema: pa.Schema
) -> None:
    if _has_extension_metadata(_normalize_metadata(stream_schema.metadata)):
        raise ConformanceValidationError("arrow schema extension metadata unsupported")

    declared_by_name: dict[str, dict[str, Any]] = {}
    for field_decl in declared_fields:
        name = str(field_decl["name"])
        canonical = canonicalize_identifier(name)
        if canonical in declared_by_name:
            raise ConformanceValidationError("declared schema canonical name collision")
        declared_by_name[canonical] = field_decl

    if len(stream_schema) != len(declared_by_name):
        raise ConformanceValidationError("arrow schema field count mismatch")

    matched: set[str] = set()
    for index in range(len(stream_schema)):
        arrow_field = stream_schema.field(index)
        if _has_extension_metadata(_normalize_metadata(arrow_field.metadata)):
            raise ConformanceValidationError("arrow field extension metadata unsupported")
        if _is_rejected_type(arrow_field.type):
            raise ConformanceValidationError("arrow physical type unsupported")

        canonical = canonicalize_identifier(arrow_field.name)
        if canonical not in declared_by_name:
            raise ConformanceValidationError("arrow schema missing declared field")
        field_decl_match: dict[str, Any] = declared_by_name[canonical]
        nullable = bool(field_decl_match["nullable"])
        if arrow_field.nullable != nullable:
            raise ConformanceValidationError("arrow field nullability mismatch")
        declared = declared_type_from_json(field_decl_match["semantic_type"])
        if not _check_mapping(
            declared.kind,
            arrow_field.type,
            bits=declared.bits,
            precision=declared.precision,
            scale=declared.scale,
        ):
            raise ConformanceValidationError("arrow physical type mismatch")
        matched.add(canonical)

    if len(matched) != len(declared_by_name):
        raise ConformanceValidationError("arrow schema missing declared field")


def assert_batch_schema_matches(stream_schema: pa.Schema, batch_schema: pa.Schema) -> None:
    if not _schemas_equal(stream_schema, batch_schema):
        raise ConformanceValidationError("arrow batch schema mismatch")


def assert_no_trailing_ipc_bytes(ipc_bytes: bytes, consumed: int) -> None:
    if consumed != len(ipc_bytes):
        raise ConformanceValidationError("arrow ipc stream has trailing bytes")
