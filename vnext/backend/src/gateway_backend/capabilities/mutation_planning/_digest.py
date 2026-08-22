"""Canonical row digest helpers for mutation planning."""

from __future__ import annotations

import base64
from typing import Any, Mapping, cast

from gateway_shared_kernel import DigestRef, encode_row
from gateway_shared_kernel.jcs import canonicalize_json_value
from gateway_shared_kernel.types import (
    AnomalyScalar,
    BinaryScalar,
    BitScalar,
    BooleanScalar,
    DateScalar,
    DateTimeScalar,
    DeclaredType,
    DeclaredTypeKind,
    DecimalScalar,
    Float32Scalar,
    Float64Scalar,
    NullScalar,
    RowField,
    SignedIntegerScalar,
    StringScalar,
    TimeDurationScalar,
    TimestampScalar,
    UnsignedIntegerScalar,
)

from gateway_backend.capabilities.mutation_planning.contracts import (
    CanonicalCellValue,
    CanonicalStorageKey,
    PersistedRowImage,
    validate_canonical_cell_value,
)


def key_bytes_for_ordering(key: CanonicalStorageKey) -> bytes:
    return canonicalize_json_value(key.to_document())


def row_digest_from_image(
    image: PersistedRowImage,
    *,
    retained_columns: tuple[str, ...],
) -> DigestRef:
    fields = [_row_field(column, _image_column_value(image, column)) for column in retained_columns]
    return encode_row(fields).digest_ref


def row_digest_from_keyed_image(
    image: PersistedRowImage,
    *,
    retained_columns: tuple[str, ...],
) -> DigestRef:
    return row_digest_from_image(image, retained_columns=retained_columns)


def _image_column_value(image: PersistedRowImage, column: str) -> CanonicalCellValue:
    for name, value in image.columns:
        if name == column:
            return value
    raise ValueError(f"row image missing retained column {column}")


def _row_field(column: str, cell: CanonicalCellValue) -> RowField:
    validated = validate_canonical_cell_value(cell, column)
    kind = validated["kind"]
    if kind == "null":
        return RowField(
            name=column,
            declared_type=DeclaredType(kind=DeclaredTypeKind.NULL),
            typed_value=NullScalar(),
        )
    if kind == "boolean":
        return RowField(
            name=column,
            declared_type=DeclaredType(kind=DeclaredTypeKind.BOOLEAN),
            typed_value=BooleanScalar(value=validated["value"]),  # type: ignore[arg-type]
        )
    if kind == "signed-integer":
        return RowField(
            name=column,
            declared_type=DeclaredType(kind=DeclaredTypeKind.SIGNED_INTEGER, bits=32),
            typed_value=SignedIntegerScalar(decimal=validated["decimal"]),  # type: ignore[arg-type]
        )
    if kind == "unsigned-integer":
        return RowField(
            name=column,
            declared_type=DeclaredType(kind=DeclaredTypeKind.UNSIGNED_INTEGER, bits=32),
            typed_value=UnsignedIntegerScalar(decimal=validated["decimal"]),  # type: ignore[arg-type]
        )
    if kind == "decimal":
        text = str(validated["decimal"])
        if "." in text:
            left, right = text.split(".", 1)
            precision = len(left.lstrip("-")) + len(right)
            scale = len(right)
        else:
            precision = len(text.lstrip("-"))
            scale = 0
        return RowField(
            name=column,
            declared_type=DeclaredType(
                kind=DeclaredTypeKind.DECIMAL,
                precision=max(precision, 1),
                scale=scale,
            ),
            typed_value=DecimalScalar(decimal=text),
        )
    if kind == "float32":
        return RowField(
            name=column,
            declared_type=DeclaredType(kind=DeclaredTypeKind.FLOAT32),
            typed_value=Float32Scalar(bits_hex=validated["bits_hex"]),  # type: ignore[arg-type]
        )
    if kind == "float64":
        return RowField(
            name=column,
            declared_type=DeclaredType(kind=DeclaredTypeKind.FLOAT64),
            typed_value=Float64Scalar(bits_hex=validated["bits_hex"]),  # type: ignore[arg-type]
        )
    if kind == "string":
        return RowField(
            name=column,
            declared_type=DeclaredType(kind=DeclaredTypeKind.STRING),
            typed_value=StringScalar(text=validated["text"]),  # type: ignore[arg-type]
        )
    if kind == "binary":
        return RowField(
            name=column,
            declared_type=DeclaredType(kind=DeclaredTypeKind.BINARY),
            typed_value=BinaryScalar(
                raw_bytes=base64.urlsafe_b64decode(str(validated["bytes_base64url"]) + "==")
            ),
        )
    if kind == "bit":
        return RowField(
            name=column,
            declared_type=DeclaredType(kind=DeclaredTypeKind.BIT, bit_width=8),
            typed_value=BitScalar(
                raw_bytes=base64.urlsafe_b64decode(str(validated["bytes_base64url"]) + "==")
            ),
        )
    if kind == "date":
        return RowField(
            name=column,
            declared_type=DeclaredType(kind=DeclaredTypeKind.DATE),
            typed_value=DateScalar(text=validated["text"]),  # type: ignore[arg-type]
        )
    if kind == "datetime":
        return RowField(
            name=column,
            declared_type=DeclaredType(kind=DeclaredTypeKind.DATETIME),
            typed_value=DateTimeScalar(text=validated["text"]),  # type: ignore[arg-type]
        )
    if kind == "timestamp":
        return RowField(
            name=column,
            declared_type=DeclaredType(kind=DeclaredTypeKind.TIMESTAMP),
            typed_value=TimestampScalar(text=validated["text"]),  # type: ignore[arg-type]
        )
    if kind == "time-duration":
        return RowField(
            name=column,
            declared_type=DeclaredType(kind=DeclaredTypeKind.TIME_DURATION),
            typed_value=TimeDurationScalar(text=validated["text"]),  # type: ignore[arg-type]
        )
    envelope = cast(Mapping[str, Any], validated["envelope"])
    return RowField(
        name=column,
        declared_type=DeclaredType(kind=DeclaredTypeKind.SOURCE_LITERAL_ANOMALY),
        typed_value=AnomalyScalar(envelope=dict(envelope)),
    )
