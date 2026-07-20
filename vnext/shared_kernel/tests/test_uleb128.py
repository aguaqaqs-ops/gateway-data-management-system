"""ULEB128 encode/decode tests."""

from __future__ import annotations

import pytest

from gateway_shared_kernel.errors import CanonicalEncodingError, CanonicalErrorCode
from gateway_shared_kernel.uleb128 import decode_uleb128, encode_uleb128


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (0, b"\x00"),
        (1, b"\x01"),
        (127, b"\x7f"),
        (128, b"\x80\x01"),
        (255, b"\xff\x01"),
        (300, b"\xac\x02"),
    ],
)
def test_encode_minimal(value: int, expected: bytes) -> None:
    assert encode_uleb128(value) == expected


def test_decode_roundtrip_and_non_minimal() -> None:
    encoded = encode_uleb128(300)
    value, next_offset = decode_uleb128(encoded)
    assert value == 300
    assert next_offset == len(encoded)

    with pytest.raises(CanonicalEncodingError) as exc_info:
        decode_uleb128(b"\x80\x00")
    assert exc_info.value.code is CanonicalErrorCode.CANONICAL_ULEB128_NON_MINIMAL


def test_decode_truncated() -> None:
    with pytest.raises(CanonicalEncodingError) as exc_info:
        decode_uleb128(b"\x80")
    assert exc_info.value.code is CanonicalErrorCode.CANONICAL_FRAME_TRUNCATED
