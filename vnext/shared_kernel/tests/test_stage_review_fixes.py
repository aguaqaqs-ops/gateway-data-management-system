"""Regression tests for stage-review boundary fixes."""

from __future__ import annotations

import pytest

from gateway_shared_kernel import (
    AnomalyScalar,
    BooleanScalar,
    CanonicalEncodingError,
    CanonicalErrorCode,
    DeclaredType,
    DeclaredTypeKind,
    Utf8LogicalLiteral,
    canonicalize_jcs,
    encode_typed_scalar,
    normalize_logical_literal,
)
from gateway_shared_kernel.base64url import decode_base64url_strict
from gateway_shared_kernel.uleb128 import decode_uleb128


def test_jcs_syntax_invalid_not_unicode() -> None:
    with pytest.raises(CanonicalEncodingError) as exc_info:
        canonicalize_jcs(b"{")
    assert exc_info.value.code is CanonicalErrorCode.CANONICAL_JCS_SYNTAX_INVALID


def test_rejects_fullwidth_digits_and_float_whitespace_underscore() -> None:
    declared_int = DeclaredType(kind=DeclaredTypeKind.SIGNED_INTEGER, bits=32)
    with pytest.raises(CanonicalEncodingError) as exc_info:
        normalize_logical_literal(declared_int, Utf8LogicalLiteral(text="１２"))
    assert exc_info.value.code is CanonicalErrorCode.CANONICAL_TYPE_MISMATCH

    declared_date = DeclaredType(kind=DeclaredTypeKind.DATE)
    with pytest.raises(CanonicalEncodingError) as exc_info:
        normalize_logical_literal(declared_date, Utf8LogicalLiteral(text="２０２４-０１-０２"))
    assert exc_info.value.code is CanonicalErrorCode.CANONICAL_TEMPORAL_INVALID

    declared_float = DeclaredType(kind=DeclaredTypeKind.FLOAT64)
    with pytest.raises(CanonicalEncodingError) as exc_info:
        normalize_logical_literal(declared_float, Utf8LogicalLiteral(text=" 1.5 "))
    assert exc_info.value.code is CanonicalErrorCode.CANONICAL_TYPE_MISMATCH

    with pytest.raises(CanonicalEncodingError) as exc_info:
        normalize_logical_literal(declared_float, Utf8LogicalLiteral(text="1_0"))
    assert exc_info.value.code is CanonicalErrorCode.CANONICAL_TYPE_MISMATCH


def test_float32_overflow_maps_to_non_finite() -> None:
    declared = DeclaredType(kind=DeclaredTypeKind.FLOAT32)
    with pytest.raises(CanonicalEncodingError) as exc_info:
        normalize_logical_literal(declared, Utf8LogicalLiteral(text="3.5e38"))
    assert exc_info.value.code is CanonicalErrorCode.CANONICAL_FLOAT_NON_FINITE


def test_boolean_runtime_type_mismatch() -> None:
    declared = DeclaredType(kind=DeclaredTypeKind.BOOLEAN)
    with pytest.raises(CanonicalEncodingError) as exc_info:
        encode_typed_scalar(declared, BooleanScalar(value=1))  # type: ignore[arg-type]
    assert exc_info.value.code is CanonicalErrorCode.CANONICAL_TYPE_MISMATCH


def test_base64url_rejects_length_mod_4_eq_1() -> None:
    with pytest.raises(CanonicalEncodingError) as exc_info:
        decode_base64url_strict("A")
    assert exc_info.value.code is CanonicalErrorCode.CANONICAL_ANOMALY_INVALID

    with pytest.raises(CanonicalEncodingError) as exc_info:
        encode_typed_scalar(
            DeclaredType(kind=DeclaredTypeKind.SOURCE_LITERAL_ANOMALY),
            AnomalyScalar(
                envelope={
                    "declared_type": {"kind": "date"},
                    "raw_base64url": "A",
                    "raw_encoding": "utf8",
                    "reason": "x",
                }
            ),
        )
    assert exc_info.value.code is CanonicalErrorCode.CANONICAL_ANOMALY_INVALID


def test_uleb128_rejects_negative_offset() -> None:
    with pytest.raises(CanonicalEncodingError) as exc_info:
        decode_uleb128(b"\x00", offset=-1)
    assert exc_info.value.code is CanonicalErrorCode.CANONICAL_FRAME_LENGTH_INVALID


def test_jcs_rejects_very_long_integer_without_host_exception() -> None:
    huge = ("9" * 5000).encode("ascii")
    with pytest.raises(CanonicalEncodingError) as exc_info:
        canonicalize_jcs(huge)
    assert exc_info.value.code is CanonicalErrorCode.CANONICAL_JCS_NUMBER_OUT_OF_RANGE


def test_declared_type_rejects_string_kind_and_bool_bits() -> None:
    with pytest.raises(ValueError):
        DeclaredType(kind="boolean")  # type: ignore[arg-type]
    with pytest.raises(ValueError):
        DeclaredType(kind=DeclaredTypeKind.SIGNED_INTEGER, bits=True)


def test_anomaly_rejects_non_string_keys() -> None:
    with pytest.raises(CanonicalEncodingError) as exc_info:
        encode_typed_scalar(
            DeclaredType(kind=DeclaredTypeKind.SOURCE_LITERAL_ANOMALY),
            AnomalyScalar(
                envelope={
                    1: "x",  # type: ignore[dict-item]
                    "declared_type": {"kind": "date"},
                    "raw_base64url": "YmFk",
                    "raw_encoding": "utf8",
                    "reason": "x",
                }
            ),
        )
    assert exc_info.value.code is CanonicalErrorCode.CANONICAL_ANOMALY_INVALID


def test_anomaly_rejects_nested_non_string_object_keys() -> None:
    with pytest.raises(CanonicalEncodingError) as exc_info:
        encode_typed_scalar(
            DeclaredType(kind=DeclaredTypeKind.SOURCE_LITERAL_ANOMALY),
            AnomalyScalar(
                envelope={
                    "declared_type": {1: "bad"},
                    "raw_base64url": "",
                    "raw_encoding": "utf8",
                    "reason": "x",
                }
            ),
        )
    assert exc_info.value.code is CanonicalErrorCode.CANONICAL_ANOMALY_INVALID


def test_anomaly_rejects_reference_cycles_without_host_exception() -> None:
    declared_type: dict[str, object] = {}
    declared_type["kind"] = declared_type
    with pytest.raises(CanonicalEncodingError) as exc_info:
        encode_typed_scalar(
            DeclaredType(kind=DeclaredTypeKind.SOURCE_LITERAL_ANOMALY),
            AnomalyScalar(
                envelope={
                    "declared_type": declared_type,
                    "raw_base64url": "",
                    "raw_encoding": "utf8",
                    "reason": "x",
                }
            ),
        )
    assert exc_info.value.code is CanonicalErrorCode.CANONICAL_ANOMALY_INVALID
