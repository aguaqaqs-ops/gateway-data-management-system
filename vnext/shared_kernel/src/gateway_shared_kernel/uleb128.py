"""Minimal ULEB128 encode/decode for scalar and framing lengths."""

from __future__ import annotations

from gateway_shared_kernel.errors import CanonicalEncodingError, CanonicalErrorCode

_MAX_LENGTH = (1 << 63) - 1


def encode_uleb128(value: int) -> bytes:
    if type(value) is not int:
        raise CanonicalEncodingError(
            CanonicalErrorCode.CANONICAL_TYPE_MISMATCH,
            "ULEB128 value must be int",
        )
    if value < 0:
        raise CanonicalEncodingError(
            CanonicalErrorCode.CANONICAL_ULEB128_OVERFLOW,
            "ULEB128 length must be non-negative",
        )
    if value > _MAX_LENGTH:
        raise CanonicalEncodingError(
            CanonicalErrorCode.CANONICAL_ULEB128_OVERFLOW,
            "ULEB128 length exceeds 2^63-1",
        )
    if value == 0:
        return b"\x00"
    out = bytearray()
    while True:
        byte = value & 0x7F
        value >>= 7
        if value:
            out.append(byte | 0x80)
        else:
            out.append(byte)
            break
    return bytes(out)


def decode_uleb128(data: bytes, *, offset: int = 0) -> tuple[int, int]:
    """Decode a minimal ULEB128 starting at ``offset``.

    Returns ``(value, next_offset)``.
    """
    if type(data) is not bytes:
        raise CanonicalEncodingError(
            CanonicalErrorCode.CANONICAL_TYPE_MISMATCH,
            "ULEB128 input must be bytes",
        )
    if type(offset) is not int:
        raise CanonicalEncodingError(
            CanonicalErrorCode.CANONICAL_TYPE_MISMATCH,
            "ULEB128 offset must be int",
        )
    if offset < 0 or offset > len(data):
        raise CanonicalEncodingError(
            CanonicalErrorCode.CANONICAL_FRAME_LENGTH_INVALID,
            "ULEB128 offset out of range",
        )
    if offset == len(data):
        raise CanonicalEncodingError(
            CanonicalErrorCode.CANONICAL_FRAME_TRUNCATED,
            "truncated ULEB128",
        )
    value = 0
    shift = 0
    index = offset
    while True:
        if index >= len(data):
            raise CanonicalEncodingError(
                CanonicalErrorCode.CANONICAL_FRAME_TRUNCATED,
                "truncated ULEB128",
            )
        byte = data[index]
        index += 1
        if shift >= 63:
            raise CanonicalEncodingError(
                CanonicalErrorCode.CANONICAL_ULEB128_OVERFLOW,
                "ULEB128 overflow",
            )
        value |= (byte & 0x7F) << shift
        if value > _MAX_LENGTH:
            raise CanonicalEncodingError(
                CanonicalErrorCode.CANONICAL_ULEB128_OVERFLOW,
                "ULEB128 overflow",
            )
        if byte & 0x80 == 0:
            break
        shift += 7
        if shift > 63:
            raise CanonicalEncodingError(
                CanonicalErrorCode.CANONICAL_ULEB128_OVERFLOW,
                "ULEB128 overflow",
            )
    encoded = data[offset:index]
    if encode_uleb128(value) != encoded:
        raise CanonicalEncodingError(
            CanonicalErrorCode.CANONICAL_ULEB128_NON_MINIMAL,
            "non-minimal ULEB128 encoding",
        )
    return value, index
