"""Additional scalar/uleb coverage for declared widths and temporals."""

from __future__ import annotations

import pytest

from gateway_shared_kernel import (
    BinaryScalar,
    BooleanScalar,
    CanonicalEncodingError,
    CanonicalErrorCode,
    DateTimeScalar,
    DecimalScalar,
    DeclaredType,
    DeclaredTypeKind,
    Float64Scalar,
    RawLogicalLiteral,
    TimeDurationScalar,
    TimestampScalar,
    UnsignedIntegerScalar,
    Utf8LogicalLiteral,
    encode_typed_scalar,
    normalize_logical_literal,
)
from gateway_shared_kernel.uleb128 import encode_uleb128


def test_boolean_raw_and_text_literals() -> None:
    declared = DeclaredType(kind=DeclaredTypeKind.BOOLEAN)
    false_value = normalize_logical_literal(declared, Utf8LogicalLiteral(text="false"))
    assert isinstance(false_value.typed_value, BooleanScalar)
    assert false_value.typed_value.value is False

    true_value = normalize_logical_literal(declared, RawLogicalLiteral(raw_bytes=b"\x01"))
    assert isinstance(true_value.typed_value, BooleanScalar)
    assert true_value.typed_value.value is True

    with pytest.raises(CanonicalEncodingError) as exc_info:
        normalize_logical_literal(declared, Utf8LogicalLiteral(text="yes"))
    assert exc_info.value.code is CanonicalErrorCode.CANONICAL_TYPE_MISMATCH


def test_unsigned_integer_and_negative_rejection() -> None:
    declared = DeclaredType(kind=DeclaredTypeKind.UNSIGNED_INTEGER, bits=16)
    result = normalize_logical_literal(declared, Utf8LogicalLiteral(text="+00042"))
    assert isinstance(result.typed_value, UnsignedIntegerScalar)
    assert result.typed_value.decimal == "42"
    assert result.payload == (42).to_bytes(8, "big", signed=False)

    with pytest.raises(CanonicalEncodingError) as exc_info:
        normalize_logical_literal(declared, Utf8LogicalLiteral(text="-1"))
    assert exc_info.value.code is CanonicalErrorCode.CANONICAL_INTEGER_OUT_OF_RANGE


def test_float64_and_binary_string_paths() -> None:
    f64 = normalize_logical_literal(
        DeclaredType(kind=DeclaredTypeKind.FLOAT64),
        Utf8LogicalLiteral(text="1.5"),
    )
    assert isinstance(f64.typed_value, Float64Scalar)
    assert len(f64.payload) == 8

    binary = encode_typed_scalar(
        DeclaredType(kind=DeclaredTypeKind.BINARY),
        BinaryScalar(raw_bytes=b"\x00\xff"),
    )
    assert binary.payload == b"\x00\xff"
    assert binary.scalar_frame[0] == 0x21


def test_datetime_timestamp_fraction_stripping() -> None:
    dt = normalize_logical_literal(
        DeclaredType(kind=DeclaredTypeKind.DATETIME),
        Utf8LogicalLiteral(text="2024-01-02T03:04:05.120000"),
    )
    assert isinstance(dt.typed_value, DateTimeScalar)
    assert dt.typed_value.text == "2024-01-02T03:04:05.12"

    ts = normalize_logical_literal(
        DeclaredType(kind=DeclaredTypeKind.TIMESTAMP),
        Utf8LogicalLiteral(text="2024-01-02T03:04:05.000000Z"),
    )
    assert isinstance(ts.typed_value, TimestampScalar)
    assert ts.typed_value.text == "2024-01-02T03:04:05Z"


def test_null_and_decimal_boundaries() -> None:
    null = normalize_logical_literal(
        DeclaredType(kind=DeclaredTypeKind.NULL),
        Utf8LogicalLiteral(text="null"),
    )
    assert null.payload == b""

    declared = DeclaredType(kind=DeclaredTypeKind.DECIMAL, precision=5, scale=2)
    ok = normalize_logical_literal(declared, Utf8LogicalLiteral(text="001.2300"))
    assert isinstance(ok.typed_value, DecimalScalar)
    assert ok.typed_value.decimal == "1.23"

    with pytest.raises(CanonicalEncodingError) as exc_info:
        normalize_logical_literal(declared, Utf8LogicalLiteral(text="1.234"))
    assert exc_info.value.code is CanonicalErrorCode.CANONICAL_DECIMAL_INVALID

    with pytest.raises(CanonicalEncodingError) as exc_info:
        normalize_logical_literal(declared, Utf8LogicalLiteral(text="1234.56"))
    assert exc_info.value.code is CanonicalErrorCode.CANONICAL_DECIMAL_INVALID


def test_time_duration_digit_width_rules() -> None:
    declared = DeclaredType(kind=DeclaredTypeKind.TIME_DURATION)
    two_digit = normalize_logical_literal(declared, Utf8LogicalLiteral(text="99:00:00"))
    assert isinstance(two_digit.typed_value, TimeDurationScalar)
    assert two_digit.typed_value.text == "99:00:00"

    three_digit = normalize_logical_literal(declared, Utf8LogicalLiteral(text="100:00:00"))
    assert isinstance(three_digit.typed_value, TimeDurationScalar)
    assert three_digit.typed_value.text == "100:00:00"

    with pytest.raises(CanonicalEncodingError) as exc_info:
        normalize_logical_literal(declared, Utf8LogicalLiteral(text="099:00:00"))
    assert exc_info.value.code is CanonicalErrorCode.CANONICAL_TEMPORAL_INVALID


def test_uleb128_overflow_negative() -> None:
    with pytest.raises(CanonicalEncodingError) as exc_info:
        encode_uleb128(-1)
    assert exc_info.value.code is CanonicalErrorCode.CANONICAL_ULEB128_OVERFLOW


def test_declared_type_construction_guards() -> None:
    with pytest.raises(ValueError):
        DeclaredType(kind=DeclaredTypeKind.DECIMAL, precision=10, scale=11)
    with pytest.raises(ValueError):
        DeclaredType(kind=DeclaredTypeKind.SIGNED_INTEGER)
    with pytest.raises(ValueError):
        DeclaredType(kind=DeclaredTypeKind.BIT, bit_width=0)
