"""Typed scalar normalize/encode tests."""

from __future__ import annotations

import base64

import pytest

from gateway_shared_kernel import (
    AnomalyScalar,
    BinaryScalar,
    BitScalar,
    BooleanScalar,
    CanonicalEncodingError,
    CanonicalErrorCode,
    DateScalar,
    DecimalScalar,
    DeclaredType,
    DeclaredTypeKind,
    Float32Scalar,
    NullScalar,
    SignedIntegerScalar,
    StringScalar,
    TimeDurationScalar,
    Utf8LogicalLiteral,
    encode_typed_scalar,
    normalize_logical_literal,
)


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")


def test_normalize_signed_integer_leading_plus_matches_vector_example() -> None:
    declared = DeclaredType(kind=DeclaredTypeKind.SIGNED_INTEGER, bits=32)
    result = normalize_logical_literal(declared, Utf8LogicalLiteral(text="+001"))
    assert isinstance(result.typed_value, SignedIntegerScalar)
    assert result.typed_value.decimal == "1"
    assert _b64url(result.payload) == "AAAAAAAAAAE"
    assert _b64url(result.scalar_frame) == "EAgAAAAAAAAAAQ"


def test_encode_null_boolean_string() -> None:
    null = encode_typed_scalar(DeclaredType(kind=DeclaredTypeKind.NULL), NullScalar())
    assert null.payload == b""
    assert null.scalar_frame == b"\x00\x00"

    boolean = encode_typed_scalar(
        DeclaredType(kind=DeclaredTypeKind.BOOLEAN), BooleanScalar(value=True)
    )
    assert boolean.payload == b"\x01"
    assert boolean.scalar_frame == b"\x01\x01\x01"

    text = encode_typed_scalar(
        DeclaredType(kind=DeclaredTypeKind.STRING), StringScalar(text="hi")
    )
    assert text.payload == b"hi"
    assert text.scalar_frame == b"\x20\x02hi"


def test_integer_width_bounds() -> None:
    declared = DeclaredType(kind=DeclaredTypeKind.SIGNED_INTEGER, bits=8)
    normalize_logical_literal(declared, Utf8LogicalLiteral(text="127"))
    with pytest.raises(CanonicalEncodingError) as exc_info:
        normalize_logical_literal(declared, Utf8LogicalLiteral(text="128"))
    assert exc_info.value.code is CanonicalErrorCode.CANONICAL_INTEGER_OUT_OF_RANGE


def test_decimal_canonical_zero_and_rejects_plus() -> None:
    declared = DeclaredType(kind=DeclaredTypeKind.DECIMAL, precision=10, scale=2)
    result = normalize_logical_literal(declared, Utf8LogicalLiteral(text="-0.00"))
    assert isinstance(result.typed_value, DecimalScalar)
    assert result.typed_value.decimal == "0"
    assert result.payload == b"0"

    with pytest.raises(CanonicalEncodingError) as exc_info:
        normalize_logical_literal(declared, Utf8LogicalLiteral(text="+1.0"))
    assert exc_info.value.code is CanonicalErrorCode.CANONICAL_DECIMAL_INVALID


def test_float32_negative_zero_and_nonfinite() -> None:
    declared = DeclaredType(kind=DeclaredTypeKind.FLOAT32)
    result = normalize_logical_literal(declared, Utf8LogicalLiteral(text="-0.0"))
    assert isinstance(result.typed_value, Float32Scalar)
    assert result.typed_value.bits_hex == "00000000"
    assert result.payload == b"\x00\x00\x00\x00"

    with pytest.raises(CanonicalEncodingError) as exc_info:
        normalize_logical_literal(declared, Utf8LogicalLiteral(text="nan"))
    assert exc_info.value.code is CanonicalErrorCode.CANONICAL_TYPE_MISMATCH


def test_bit_unused_high_bits() -> None:
    declared = DeclaredType(kind=DeclaredTypeKind.BIT, bit_width=9)
    ok = encode_typed_scalar(declared, BitScalar(raw_bytes=b"\x01\x00"))
    assert ok.payload == b"\x01\x00"

    with pytest.raises(CanonicalEncodingError) as exc_info:
        encode_typed_scalar(declared, BitScalar(raw_bytes=b"\x02\x00"))
    assert exc_info.value.code is CanonicalErrorCode.CANONICAL_TYPE_MISMATCH


def test_date_leap_day_and_invalid() -> None:
    declared = DeclaredType(kind=DeclaredTypeKind.DATE)
    result = normalize_logical_literal(declared, Utf8LogicalLiteral(text="2024-02-29"))
    assert isinstance(result.typed_value, DateScalar)
    assert result.typed_value.text == "2024-02-29"

    with pytest.raises(CanonicalEncodingError) as exc_info:
        normalize_logical_literal(declared, Utf8LogicalLiteral(text="2023-02-29"))
    assert exc_info.value.code is CanonicalErrorCode.CANONICAL_TEMPORAL_INVALID


def test_time_duration_boundaries() -> None:
    declared = DeclaredType(kind=DeclaredTypeKind.TIME_DURATION)
    zero = normalize_logical_literal(declared, Utf8LogicalLiteral(text="-00:00:00"))
    assert isinstance(zero.typed_value, TimeDurationScalar)
    assert zero.typed_value.text == "00:00:00"

    big = normalize_logical_literal(declared, Utf8LogicalLiteral(text="838:00:00"))
    assert isinstance(big.typed_value, TimeDurationScalar)
    assert big.typed_value.text == "838:00:00"

    with pytest.raises(CanonicalEncodingError) as exc_info:
        normalize_logical_literal(declared, Utf8LogicalLiteral(text="839:00:00"))
    assert exc_info.value.code is CanonicalErrorCode.CANONICAL_TIME_OUT_OF_RANGE


def test_anomaly_envelope_jcs_payload() -> None:
    declared = DeclaredType(kind=DeclaredTypeKind.SOURCE_LITERAL_ANOMALY)
    envelope = {
        "declared_type": {"kind": "date"},
        "raw_base64url": "YmFk",
        "raw_encoding": "utf8",
        "reason": "owner-reason",
    }
    encoded = encode_typed_scalar(declared, AnomalyScalar(envelope=envelope))
    assert encoded.payload.startswith(b"{")
    assert encoded.scalar_frame[0] == 0x7F

    with pytest.raises(CanonicalEncodingError) as exc_info:
        encode_typed_scalar(declared, AnomalyScalar(envelope={"reason": "x"}))
    assert exc_info.value.code is CanonicalErrorCode.CANONICAL_ANOMALY_INVALID


def test_kind_mismatch() -> None:
    with pytest.raises(CanonicalEncodingError) as exc_info:
        encode_typed_scalar(
            DeclaredType(kind=DeclaredTypeKind.BOOLEAN),
            BinaryScalar(raw_bytes=b"\x00"),
        )
    assert exc_info.value.code is CanonicalErrorCode.CANONICAL_TYPE_MISMATCH
