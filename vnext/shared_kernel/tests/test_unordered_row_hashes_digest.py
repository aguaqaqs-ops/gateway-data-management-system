"""Tests for unordered row-hash content digest framing."""

from __future__ import annotations

from gateway_shared_kernel import (
    DeclaredType,
    DeclaredTypeKind,
    DigestKind,
    NullScalar,
    RowField,
    encode_row,
    semantic_digest,
    unordered_row_hashes_content_digest,
    unordered_row_hashes_content_digest_from_row_buffer,
    unordered_row_hashes_content_digest_from_sorted_row_buffer,
)
from gateway_shared_kernel.uleb128 import encode_uleb128


def _null_field(name: str) -> RowField:
    return RowField(
        name=name,
        declared_type=DeclaredType(kind=DeclaredTypeKind.NULL),
        typed_value=NullScalar(),
    )


def test_empty_table_matches_oracle() -> None:
    digest = unordered_row_hashes_content_digest([])
    assert encode_uleb128(0) == b"\x00"
    assert (
        digest.digest_ref.value
        == "sha256:dff710f3604586654b1320ff0c6e161230cdce4f82ca41506110bc4a811fca63"
    )


def test_single_row_matches_manual_frame() -> None:
    row_hash = encode_row([]).raw_hash
    frame = encode_uleb128(1) + row_hash
    expected = semantic_digest(DigestKind.RAW_CONTENT, frame)
    digest = unordered_row_hashes_content_digest([row_hash])
    assert digest.digest_ref.value == expected.digest_ref.value


def test_retains_duplicates() -> None:
    row_hash = encode_row([]).raw_hash
    one = unordered_row_hashes_content_digest([row_hash])
    two = unordered_row_hashes_content_digest([row_hash, row_hash])
    assert one.digest_ref.value != two.digest_ref.value


def test_permutation_invariant() -> None:
    row_a = encode_row([]).raw_hash
    row_b = encode_row([_null_field("x")]).raw_hash
    digest_a = unordered_row_hashes_content_digest([row_a, row_b])
    digest_b = unordered_row_hashes_content_digest([row_b, row_a])
    assert digest_a.digest_ref.value == digest_b.digest_ref.value


def test_row_buffer_digest_matches_list_oracle() -> None:
    row_a = encode_row([]).raw_hash
    row_b = encode_row([_null_field("x")]).raw_hash
    list_digest = unordered_row_hashes_content_digest([row_a, row_b])
    row_buffer = bytearray(row_a + row_b)
    buffer_digest = unordered_row_hashes_content_digest_from_row_buffer(row_buffer, 2)
    assert list_digest.digest_ref.value == buffer_digest.digest_ref.value


def test_row_buffer_digest_empty_matches_oracle() -> None:
    list_digest = unordered_row_hashes_content_digest([])
    buffer_digest = unordered_row_hashes_content_digest_from_row_buffer(b"", 0)
    assert list_digest.digest_ref.value == buffer_digest.digest_ref.value
    sorted_digest = unordered_row_hashes_content_digest_from_sorted_row_buffer(b"", 0)
    assert list_digest.digest_ref.value == sorted_digest.digest_ref.value


def test_sorted_row_buffer_digest_matches_list_oracle() -> None:
    row_a = encode_row([]).raw_hash
    row_b = encode_row([_null_field("x")]).raw_hash
    sorted_hashes = sorted([row_a, row_b])
    ordered = sorted_hashes[0] + sorted_hashes[1]
    list_digest = unordered_row_hashes_content_digest([row_a, row_b])
    sorted_digest = unordered_row_hashes_content_digest_from_sorted_row_buffer(ordered, 2)
    assert list_digest.digest_ref.value == sorted_digest.digest_ref.value


def test_rejects_non_32_byte_hash() -> None:
    try:
        unordered_row_hashes_content_digest([b"\x00" * 31])
    except Exception as exc:
        assert "32 bytes" in str(exc)
    else:
        raise AssertionError("expected invalid row hash length to fail")
