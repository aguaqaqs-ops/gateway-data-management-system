"""Test-only scalar-frame structural validator for invalid-case coverage."""

from __future__ import annotations

from gateway_shared_kernel.errors import CanonicalEncodingError, CanonicalErrorCode
from gateway_shared_kernel.scalar import (
    TAG_ANOMALY,
    TAG_BINARY,
    TAG_BOOLEAN,
    TAG_DATE,
    TAG_DATETIME,
    TAG_DECIMAL,
    TAG_FLOAT32,
    TAG_FLOAT64,
    TAG_NULL,
    TAG_SIGNED_INTEGER,
    TAG_STRING,
    TAG_TIME_DURATION,
    TAG_TIMESTAMP,
    TAG_UNSIGNED_INTEGER,
)
from gateway_shared_kernel.uleb128 import decode_uleb128

_ASSIGNED_TAGS = frozenset(
    {
        TAG_NULL,
        TAG_BOOLEAN,
        TAG_SIGNED_INTEGER,
        TAG_UNSIGNED_INTEGER,
        TAG_DECIMAL,
        TAG_FLOAT32,
        TAG_FLOAT64,
        TAG_STRING,
        TAG_BINARY,
        TAG_DATE,
        TAG_DATETIME,
        TAG_TIMESTAMP,
        TAG_TIME_DURATION,
        TAG_ANOMALY,
    }
)


def validate_scalar_frame(frame: bytes) -> None:
    """Validate scalar frame structure; raise ``CanonicalEncodingError`` on failure."""
    if type(frame) is not bytes:
        raise CanonicalEncodingError(
            CanonicalErrorCode.CANONICAL_TYPE_MISMATCH,
            "scalar frame must be bytes",
        )
    if len(frame) == 0:
        raise CanonicalEncodingError(
            CanonicalErrorCode.CANONICAL_FRAME_TRUNCATED,
            "scalar frame is empty",
        )

    tag = frame[0]
    if tag not in _ASSIGNED_TAGS:
        # Formal v1 partition (Shared Canonical Encoding):
        # unassigned tags in 0x00..=0x7F -> RESERVED; 0x80..=0xFF -> UNKNOWN.
        if tag <= 0x7F:
            raise CanonicalEncodingError(
                CanonicalErrorCode.CANONICAL_SCALAR_TAG_RESERVED,
                f"reserved scalar tag 0x{tag:02x}",
            )
        raise CanonicalEncodingError(
            CanonicalErrorCode.CANONICAL_SCALAR_TAG_UNKNOWN,
            f"unknown scalar tag 0x{tag:02x}",
        )

    length, offset = decode_uleb128(frame, offset=1)
    if offset + length > len(frame):
        raise CanonicalEncodingError(
            CanonicalErrorCode.CANONICAL_FRAME_TRUNCATED,
            "scalar frame payload truncated",
        )
    if offset + length < len(frame):
        raise CanonicalEncodingError(
            CanonicalErrorCode.CANONICAL_FRAME_LENGTH_INVALID,
            "scalar frame has trailing bytes after payload",
        )

    payload = frame[offset : offset + length]
    _check_obvious_payload(tag, payload)


def _check_obvious_payload(tag: int, payload: bytes) -> None:
    if tag == TAG_NULL:
        if len(payload) != 0:
            raise CanonicalEncodingError(
                CanonicalErrorCode.CANONICAL_FRAME_LENGTH_INVALID,
                "null payload must be empty",
            )
        return
    if tag == TAG_BOOLEAN:
        if len(payload) != 1 or payload[0] not in (0x00, 0x01):
            raise CanonicalEncodingError(
                CanonicalErrorCode.CANONICAL_FRAME_LENGTH_INVALID,
                "boolean payload must be a single 0x00 or 0x01 byte",
            )
        return
    if tag == TAG_SIGNED_INTEGER or tag == TAG_UNSIGNED_INTEGER:
        if len(payload) != 8:
            raise CanonicalEncodingError(
                CanonicalErrorCode.CANONICAL_FRAME_LENGTH_INVALID,
                "integer payload must be exactly 8 bytes",
            )
        return
    if tag == TAG_FLOAT32:
        if len(payload) != 4:
            raise CanonicalEncodingError(
                CanonicalErrorCode.CANONICAL_FRAME_LENGTH_INVALID,
                "float32 payload must be exactly 4 bytes",
            )
        return
    if tag == TAG_FLOAT64:
        if len(payload) != 8:
            raise CanonicalEncodingError(
                CanonicalErrorCode.CANONICAL_FRAME_LENGTH_INVALID,
                "float64 payload must be exactly 8 bytes",
            )
        return
