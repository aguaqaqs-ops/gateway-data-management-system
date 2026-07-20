"""canonicalize_jcs unit tests."""

from __future__ import annotations

import base64

import pytest

from gateway_shared_kernel import CanonicalEncodingError, CanonicalErrorCode, canonicalize_jcs


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")


def test_canonicalize_jcs_object_key_order_and_no_whitespace() -> None:
    raw = b'{"b":1,"a":2}'
    assert canonicalize_jcs(raw) == b'{"a":2,"b":1}'


def test_canonicalize_jcs_array_preserves_order() -> None:
    raw = b'[3,1,2]'
    assert canonicalize_jcs(raw) == b"[3,1,2]"


def test_canonicalize_jcs_non_bmp_key_order() -> None:
    # U+1F600 (😀) UTF-16: D83D DE00; U+0061 is "a"
    # JCS sorts by UTF-16 code units: "a" (0061) before 😀 (D83D DE00)
    raw = '{"\U0001f600":1,"a":2}'.encode()
    assert canonicalize_jcs(raw) == b'{"a":2,"\xf0\x9f\x98\x80":1}'


def test_canonicalize_jcs_negative_zero_float_normalizes() -> None:
    assert canonicalize_jcs(b"-0.0") == b"0"


def test_canonicalize_jcs_safe_integer_extrema() -> None:
    assert canonicalize_jcs(b"9007199254740991") == b"9007199254740991"
    assert canonicalize_jcs(b"-9007199254740991") == b"-9007199254740991"


def test_canonicalize_jcs_rejects_invalid_utf8() -> None:
    with pytest.raises(CanonicalEncodingError) as exc_info:
        canonicalize_jcs(b"\xff")
    assert exc_info.value.code is CanonicalErrorCode.CANONICAL_INVALID_UTF8


def test_canonicalize_jcs_rejects_duplicate_member() -> None:
    with pytest.raises(CanonicalEncodingError) as exc_info:
        canonicalize_jcs(b'{"a":1,"a":2}')
    assert exc_info.value.code is CanonicalErrorCode.CANONICAL_JCS_DUPLICATE_MEMBER


def test_canonicalize_jcs_rejects_integer_out_of_ijson_range() -> None:
    with pytest.raises(CanonicalEncodingError) as exc_info:
        canonicalize_jcs(b"9007199254740992")
    assert exc_info.value.code is CanonicalErrorCode.CANONICAL_JCS_NUMBER_OUT_OF_RANGE


def test_canonicalize_jcs_rejects_nan() -> None:
    with pytest.raises(CanonicalEncodingError) as exc_info:
        canonicalize_jcs(b"NaN")
    assert exc_info.value.code is CanonicalErrorCode.CANONICAL_JCS_NON_FINITE_NUMBER


def test_canonicalize_jcs_rejects_infinity() -> None:
    with pytest.raises(CanonicalEncodingError) as exc_info:
        canonicalize_jcs(b"Infinity")
    assert exc_info.value.code is CanonicalErrorCode.CANONICAL_JCS_NON_FINITE_NUMBER


def test_canonicalize_jcs_rejects_surrogate_escape() -> None:
    with pytest.raises(CanonicalEncodingError) as exc_info:
        canonicalize_jcs(b'"\\uD800"')
    assert exc_info.value.code is CanonicalErrorCode.CANONICAL_INVALID_UNICODE


def test_canonicalize_jcs_rejects_noncharacter() -> None:
    with pytest.raises(CanonicalEncodingError) as exc_info:
        canonicalize_jcs(b'"\\uFFFF"')
    assert exc_info.value.code is CanonicalErrorCode.CANONICAL_UNICODE_NONCHARACTER


def test_canonicalize_jcs_idempotent_on_canonical_output() -> None:
    first = canonicalize_jcs(b'{"z":true,"a":[1,2],"m":null}')
    second = canonicalize_jcs(first)
    assert first == second


def test_vector_case_shape_roundtrip_helper_encoding() -> None:
    # Sanity that base64url helpers match vector envelope conventions.
    payload = b'{"a":1}'
    assert canonicalize_jcs(payload) == b'{"a":1}'
    assert _b64url(payload) == "eyJhIjoxfQ"
