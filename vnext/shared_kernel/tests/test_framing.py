"""Tests for row and collection framing."""

from __future__ import annotations

import pytest

from gateway_shared_kernel import (
    BooleanScalar,
    CanonicalEncodingError,
    CanonicalErrorCode,
    CollectionSemantics,
    DeclaredType,
    DeclaredTypeKind,
    DigestKind,
    NullScalar,
    RowField,
    StringScalar,
    encode_collection,
    encode_row,
    encode_typed_scalar,
    semantic_digest,
)
from gateway_shared_kernel.uleb128 import encode_uleb128


def _null_field(name: str) -> RowField:
    return RowField(
        name=name,
        declared_type=DeclaredType(kind=DeclaredTypeKind.NULL),
        typed_value=NullScalar(),
    )


def _string_field(name: str, text: str) -> RowField:
    return RowField(
        name=name,
        declared_type=DeclaredType(kind=DeclaredTypeKind.STRING),
        typed_value=StringScalar(text=text),
    )


def test_encode_row_empty() -> None:
    encoded = encode_row([])
    assert encoded.row_frame == b"\x00"
    digest = semantic_digest(DigestKind.ROW, encoded.row_frame)
    assert encoded.raw_hash == digest.raw_digest
    assert encoded.digest_ref == digest.digest_ref


def test_encode_row_sorts_by_canonical_utf8_bytes() -> None:
    fields = [
        _string_field("b", "B"),
        _string_field("A", "A"),
        _string_field("aa", "AA"),
    ]
    encoded = encode_row(fields)
    # Canonical names: a, aa, b — order by UTF-8 bytes
    a_frame = encode_typed_scalar(
        DeclaredType(kind=DeclaredTypeKind.STRING), StringScalar(text="A")
    ).scalar_frame
    aa_frame = encode_typed_scalar(
        DeclaredType(kind=DeclaredTypeKind.STRING), StringScalar(text="AA")
    ).scalar_frame
    b_frame = encode_typed_scalar(
        DeclaredType(kind=DeclaredTypeKind.STRING), StringScalar(text="B")
    ).scalar_frame

    expected = bytearray(encode_uleb128(3))
    for name, frame in ((b"a", a_frame), (b"aa", aa_frame), (b"b", b_frame)):
        expected.extend(encode_uleb128(len(name)))
        expected.extend(name)
        expected.extend(frame)
    assert encoded.row_frame == bytes(expected)

    # Input permutation must not change the frame
    permuted = encode_row(list(reversed(fields)))
    assert permuted.row_frame == encoded.row_frame
    assert permuted.digest_ref == encoded.digest_ref


def test_encode_row_collision_after_ascii_fold() -> None:
    with pytest.raises(CanonicalEncodingError) as exc_info:
        encode_row([_null_field("Id"), _null_field("id")])
    assert exc_info.value.code is CanonicalErrorCode.CANONICAL_IDENTIFIER_COLLISION


def test_encode_row_empty_identifier() -> None:
    with pytest.raises(CanonicalEncodingError) as exc_info:
        encode_row([_null_field("")])
    assert exc_info.value.code is CanonicalErrorCode.CANONICAL_IDENTIFIER_EMPTY


def test_encode_collection_sequence_preserves_order() -> None:
    items = [b"z", b"a", b"z"]
    encoded = encode_collection(CollectionSemantics.SEQUENCE, items=items)
    expected = bytearray(encode_uleb128(3))
    for item in items:
        expected.extend(encode_uleb128(len(item)))
        expected.extend(item)
    assert encoded.collection_frame == bytes(expected)


def test_encode_collection_multiset_sorts_and_keeps_duplicates() -> None:
    items = [b"bb", b"a", b"a"]
    encoded = encode_collection(CollectionSemantics.MULTISET, items=items)
    hashes = sorted(
        semantic_digest(
            DigestKind.COLLECTION_ITEM, encode_uleb128(len(item)) + item
        ).raw_digest
        for item in items
    )
    expected = encode_uleb128(3) + b"".join(hashes)
    assert encoded.collection_frame == expected

    # Input order must not matter for multiset
    again = encode_collection(CollectionSemantics.MULTISET, items=list(reversed(items)))
    assert again.collection_frame == encoded.collection_frame


def test_encode_collection_set_rejects_duplicate_item() -> None:
    with pytest.raises(CanonicalEncodingError) as exc_info:
        encode_collection(CollectionSemantics.SET, items=[b"a", b"b", b"a"])
    assert exc_info.value.code is CanonicalErrorCode.CANONICAL_COLLECTION_DUPLICATE_ITEM


def test_encode_collection_set_unique_sorted() -> None:
    items = [b"c", b"a", b"b"]
    encoded = encode_collection(CollectionSemantics.SET, items=items)
    hashes = sorted(
        semantic_digest(
            DigestKind.COLLECTION_ITEM, encode_uleb128(len(item)) + item
        ).raw_digest
        for item in items
    )
    assert encoded.collection_frame == encode_uleb128(3) + b"".join(hashes)


def test_encode_collection_keyed_sorts_and_rejects_duplicate_key() -> None:
    entries = [(b"b", b"2"), (b"a", b"1"), (b"c", b"3")]
    encoded = encode_collection(CollectionSemantics.KEYED_COLLECTION, entries=entries)
    expected = bytearray(encode_uleb128(3))
    for key, value in sorted(entries, key=lambda item: item[0]):
        expected.extend(encode_uleb128(len(key)))
        expected.extend(key)
        expected.extend(encode_uleb128(len(value)))
        expected.extend(value)
    assert encoded.collection_frame == bytes(expected)

    with pytest.raises(CanonicalEncodingError) as exc_info:
        encode_collection(
            CollectionSemantics.KEYED_COLLECTION,
            entries=[(b"k", b"1"), (b"k", b"2")],
        )
    assert exc_info.value.code is CanonicalErrorCode.CANONICAL_COLLECTION_DUPLICATE_KEY


def test_encode_collection_rejects_unknown_semantics_and_wrong_inputs() -> None:
    with pytest.raises(CanonicalEncodingError) as exc_info:
        encode_collection("sequence", items=[])  # type: ignore[arg-type]
    assert exc_info.value.code is CanonicalErrorCode.CANONICAL_COLLECTION_SEMANTICS_UNKNOWN

    with pytest.raises(CanonicalEncodingError) as exc_info:
        encode_collection(CollectionSemantics.SEQUENCE, entries=[(b"a", b"b")])
    assert exc_info.value.code is CanonicalErrorCode.CANONICAL_TYPE_MISMATCH

    with pytest.raises(CanonicalEncodingError) as exc_info:
        encode_collection(CollectionSemantics.KEYED_COLLECTION, items=[b"a"])
    assert exc_info.value.code is CanonicalErrorCode.CANONICAL_TYPE_MISMATCH


def test_encode_row_rejects_non_row_field() -> None:
    with pytest.raises(CanonicalEncodingError) as exc_info:
        encode_row([_null_field("a"), "bad"])  # type: ignore[list-item]
    assert exc_info.value.code is CanonicalErrorCode.CANONICAL_TYPE_MISMATCH

    with pytest.raises(CanonicalEncodingError) as exc_info:
        encode_row("not-a-sequence")  # type: ignore[arg-type]
    assert exc_info.value.code is CanonicalErrorCode.CANONICAL_TYPE_MISMATCH

    bad_name = RowField(
        name=b"id",  # type: ignore[arg-type]
        declared_type=DeclaredType(kind=DeclaredTypeKind.NULL),
        typed_value=NullScalar(),
    )
    with pytest.raises(CanonicalEncodingError) as exc_info:
        encode_row([bad_name])
    assert exc_info.value.code is CanonicalErrorCode.CANONICAL_TYPE_MISMATCH


def test_encode_collection_rejects_non_bytes_items_and_entries() -> None:
    with pytest.raises(CanonicalEncodingError) as exc_info:
        encode_collection(CollectionSemantics.SEQUENCE, items=["a"])  # type: ignore[list-item]
    assert exc_info.value.code is CanonicalErrorCode.CANONICAL_TYPE_MISMATCH

    with pytest.raises(CanonicalEncodingError) as exc_info:
        encode_collection(CollectionSemantics.SET, items=[bytearray(b"a")])  # type: ignore[list-item]
    assert exc_info.value.code is CanonicalErrorCode.CANONICAL_TYPE_MISMATCH

    with pytest.raises(CanonicalEncodingError) as exc_info:
        encode_collection(
            CollectionSemantics.KEYED_COLLECTION,
            entries=[(b"a", b"b", b"c")],  # type: ignore[list-item]
        )
    assert exc_info.value.code is CanonicalErrorCode.CANONICAL_TYPE_MISMATCH

    with pytest.raises(CanonicalEncodingError) as exc_info:
        encode_collection(
            CollectionSemantics.KEYED_COLLECTION,
            entries=[(b"a", "b")],  # type: ignore[list-item]
        )
    assert exc_info.value.code is CanonicalErrorCode.CANONICAL_TYPE_MISMATCH


def test_encode_row_uses_boolean_scalar() -> None:
    field = RowField(
        name="flag",
        declared_type=DeclaredType(kind=DeclaredTypeKind.BOOLEAN),
        typed_value=BooleanScalar(value=True),
    )
    encoded = encode_row([field])
    assert encoded.row_frame.startswith(b"\x01")  # field_count = 1
