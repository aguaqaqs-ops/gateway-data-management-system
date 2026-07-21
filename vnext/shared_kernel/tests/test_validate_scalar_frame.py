"""validate_scalar_frame structural checks."""

from __future__ import annotations

import pytest

from gateway_shared_kernel import CanonicalEncodingError, CanonicalErrorCode
from gateway_shared_kernel.testing import validate_scalar_frame
from gateway_shared_kernel.uleb128 import encode_uleb128


def test_valid_null_and_boolean_frames() -> None:
    validate_scalar_frame(b"\x00\x00")
    validate_scalar_frame(b"\x01\x01\x01")
    validate_scalar_frame(b"\x01\x01\x00")


def test_empty_frame_truncated() -> None:
    with pytest.raises(CanonicalEncodingError) as exc_info:
        validate_scalar_frame(b"")
    assert exc_info.value.code is CanonicalErrorCode.CANONICAL_FRAME_TRUNCATED


def test_reserved_and_unknown_tags() -> None:
    with pytest.raises(CanonicalEncodingError) as exc_info:
        validate_scalar_frame(b"\x02\x00")
    assert exc_info.value.code is CanonicalErrorCode.CANONICAL_SCALAR_TAG_RESERVED

    with pytest.raises(CanonicalEncodingError) as exc_info:
        validate_scalar_frame(b"\x80\x00")
    assert exc_info.value.code is CanonicalErrorCode.CANONICAL_SCALAR_TAG_UNKNOWN


def test_non_minimal_uleb_and_trailing() -> None:
    with pytest.raises(CanonicalEncodingError) as exc_info:
        validate_scalar_frame(b"\x00\x80\x00")
    assert exc_info.value.code is CanonicalErrorCode.CANONICAL_ULEB128_NON_MINIMAL

    with pytest.raises(CanonicalEncodingError) as exc_info:
        validate_scalar_frame(b"\x00\x00\xff")
    assert exc_info.value.code is CanonicalErrorCode.CANONICAL_FRAME_LENGTH_INVALID


def test_truncated_payload() -> None:
    frame = bytes([0x20]) + encode_uleb128(2) + b"a"
    with pytest.raises(CanonicalEncodingError) as exc_info:
        validate_scalar_frame(frame)
    assert exc_info.value.code is CanonicalErrorCode.CANONICAL_FRAME_TRUNCATED
