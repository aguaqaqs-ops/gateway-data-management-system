"""canonicalize_jcs unit tests."""

from __future__ import annotations

import base64
import hashlib
from typing import Any

import pytest
import rfc8785

from gateway_shared_kernel import (
    CanonicalEncodingError, CanonicalErrorCode, canonical_json_digest, canonicalize_jcs,
)
from gateway_shared_kernel.jcs import _HashSink, canonicalize_json_value


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


def test_canonicalize_jcs_supplementary_key_precedes_later_bmp_key() -> None:
    # U+10000 starts with UTF-16 D800, before U+E000; UTF-8 byte order is opposite.
    raw = '{"\ue000":2,"\U00010000":1}'.encode("utf-8")
    assert canonicalize_jcs(raw) == b'{"\xf0\x90\x80\x80":1,"\xee\x80\x80":2}'


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


@pytest.mark.parametrize("value", (
    None, {}, [],
    {"mutations": []},
    {"\ue000": 1, "\U0001f600": 2, "a": [True, None, 'quote"\\\n\t']},
    [-(2**53) + 1, 2**53 - 1, -0.0, 1e-27, 1e21],
    {"text": "é" * 32767},
    {"text": "x" * 65536},
    {"text": "\\" * 65537},
))
def test_json_digest_matches_original_jcs_bytes(value: Any) -> None:
    # The pinned library's original bytes API is an independent sink reference.
    expected_bytes = rfc8785.dumps(value)
    assert canonicalize_json_value(value) == expected_bytes
    assert canonical_json_digest(value).value == "sha256:" + hashlib.sha256(expected_bytes).hexdigest()


JCS_DIGEST_FAULTS: tuple[tuple[Any, CanonicalErrorCode], ...] = (
    ([2**53, "\ud800"], CanonicalErrorCode.CANONICAL_INVALID_UNICODE),
    ([object(), "\uffff"], CanonicalErrorCode.CANONICAL_UNICODE_NONCHARACTER),
    ([object(), 2**53], CanonicalErrorCode.CANONICAL_JCS_NUMBER_OUT_OF_RANGE),
    ([float("nan")], CanonicalErrorCode.CANONICAL_JCS_NON_FINITE_NUMBER),
    # Existing validators deliberately leave tuples to the library's own checks.
    ((2**53,), CanonicalErrorCode.CANONICAL_JCS_NUMBER_OUT_OF_RANGE),
    ((float("inf"),), CanonicalErrorCode.CANONICAL_JCS_NON_FINITE_NUMBER),
    (["valid output first", object()], CanonicalErrorCode.CANONICAL_INVALID_UNICODE),
)


@pytest.mark.parametrize(("value", "code"), JCS_DIGEST_FAULTS)
def test_json_digest_preserves_global_validation_order_and_serialization_errors(
    value: Any, code: CanonicalErrorCode,
) -> None:
    with pytest.raises(CanonicalEncodingError) as original:
        canonicalize_json_value(value)
    with pytest.raises(CanonicalEncodingError) as streamed:
        canonical_json_digest(value)
    assert streamed.value.code is original.value.code is code
    assert str(streamed.value) == str(original.value)
    assert type(streamed.value.__cause__) is type(original.value.__cause__)


def test_hash_buffer_is_bounded_across_small_and_large_writes() -> None:
    sink = _HashSink()
    chunks = (b"", b"a" * 65535, b"b", b"c" * 65536, b"d" * 65537, b"tail")
    for chunk in chunks:
        assert sink.write(chunk) == len(chunk)
        assert len(sink._buffer) <= 65536
        assert 0 <= sink._used <= len(sink._buffer)
    assert sink.digest().value == "sha256:" + hashlib.sha256(b"".join(chunks)).hexdigest()
