"""Tests for semantic and raw-blob digests."""

from __future__ import annotations

import hashlib

import pytest

from gateway_shared_kernel import (
    CanonicalEncodingError,
    CanonicalErrorCode,
    CollectionSemantics,
    DigestKind,
    encode_collection,
    encode_row,
    raw_blob_digest,
    semantic_digest,
)

# Formal domain literal: ASCII("gateway-vnext:<digest-kind>:v1\0")
_FORMAL_DOMAIN = {
    kind: f"gateway-vnext:{kind.value}:v1\0".encode("ascii") for kind in DigestKind
}

# Fixed empty row frame — hand-built, not taken from encoder output as digest input.
_FIXED_EMPTY_ROW_FRAME = b"\x00"

# Fixed sequence frame for items [b"a", b"b"] — frame-only; no owner digest kind yet.
# ULEB128(2) || ULEB128(1)||"a" || ULEB128(1)||"b"
_FIXED_SEQUENCE_FRAME = b"\x02\x01a\x01b"


def test_semantic_digest_domain_separation() -> None:
    payload = b"same-payload"
    digests = {kind: semantic_digest(kind, payload) for kind in DigestKind}
    refs = {kind: digests[kind].digest_ref.value for kind in DigestKind}
    assert len(set(refs.values())) == len(DigestKind)

    for kind, result in digests.items():
        expected = hashlib.sha256(_FORMAL_DOMAIN[kind] + payload).digest()
        assert result.raw_digest == expected
        assert result.digest_ref.value == "sha256:" + expected.hex()
        assert result.kind is kind


def test_raw_blob_digest_has_no_semantic_prefix() -> None:
    raw = b"payload"
    ref = raw_blob_digest(raw)
    expected = hashlib.sha256(raw).digest()
    assert ref.value == "sha256:" + expected.hex()

    semantic = semantic_digest(DigestKind.RAW_CONTENT, raw)
    assert ref.value != semantic.digest_ref.value


def test_digest_rejects_non_enum_kind_and_non_bytes() -> None:
    with pytest.raises(CanonicalEncodingError) as exc_info:
        semantic_digest("row", b"x")  # type: ignore[arg-type]
    assert exc_info.value.code is CanonicalErrorCode.CANONICAL_TYPE_MISMATCH

    with pytest.raises(CanonicalEncodingError) as exc_info:
        semantic_digest(DigestKind.ROW, bytearray(b"x"))  # type: ignore[arg-type]
    assert exc_info.value.code is CanonicalErrorCode.CANONICAL_TYPE_MISMATCH

    with pytest.raises(CanonicalEncodingError) as exc_info:
        raw_blob_digest("x")  # type: ignore[arg-type]
    assert exc_info.value.code is CanonicalErrorCode.CANONICAL_TYPE_MISMATCH


def test_encode_collection_matches_fixed_sequence_frame_only() -> None:
    """Collection asserts fixed frame bytes; no forged collection-level owner digest."""
    encoded = encode_collection(
        CollectionSemantics.SEQUENCE,
        items=[b"a", b"b"],
    )
    assert encoded.collection_frame == _FIXED_SEQUENCE_FRAME


def test_encode_row_matches_fixed_empty_row_frame() -> None:
    """encode-row vector asserts frame bytes independently of digest."""
    assert encode_row([]).row_frame == _FIXED_EMPTY_ROW_FRAME


def test_semantic_digest_row_uses_fixed_empty_frame_not_encoder_output() -> None:
    """semantic-digest copies fixed row frame bytes; does not call encode_row for input."""
    result = semantic_digest(DigestKind.ROW, _FIXED_EMPTY_ROW_FRAME)
    expected = hashlib.sha256(
        _FORMAL_DOMAIN[DigestKind.ROW] + _FIXED_EMPTY_ROW_FRAME
    ).digest()
    assert result.raw_digest == expected
    assert result.digest_ref.value == "sha256:" + expected.hex()
    # Encoder separately agrees with the fixed frame (independent assertion).
    assert encode_row([]).row_frame == _FIXED_EMPTY_ROW_FRAME
    assert encode_row([]).raw_hash == expected
