"""Canonical row and collection framing."""

from __future__ import annotations

from collections.abc import Sequence

from gateway_shared_kernel.digest import semantic_digest
from gateway_shared_kernel.errors import CanonicalEncodingError, CanonicalErrorCode
from gateway_shared_kernel.identifier import canonicalize_identifier
from gateway_shared_kernel.scalar import encode_typed_scalar
from gateway_shared_kernel.types import (
    CollectionSemantics,
    DigestKind,
    EncodedCollection,
    EncodedRow,
    RowField,
    SemanticDigest,
)
from gateway_shared_kernel.uleb128 import encode_uleb128


def encode_row(fields: Sequence[RowField]) -> EncodedRow:
    """Encode a row: sort by CanonicalIdentifier UTF-8 bytes, then frame + digest."""
    _assert_sequence(fields, "fields")
    prepared: list[tuple[bytes, RowField]] = []
    seen: dict[bytes, str] = {}
    for index, field in enumerate(fields):
        if not isinstance(field, RowField):
            raise CanonicalEncodingError(
                CanonicalErrorCode.CANONICAL_TYPE_MISMATCH,
                f"fields[{index}] must be RowField",
            )
        if type(field.name) is not str:
            raise CanonicalEncodingError(
                CanonicalErrorCode.CANONICAL_TYPE_MISMATCH,
                f"fields[{index}].name must be str",
            )
        canonical = canonicalize_identifier(field.name)
        name_utf8 = canonical.encode("utf-8")
        prior = seen.get(name_utf8)
        if prior is not None:
            raise CanonicalEncodingError(
                CanonicalErrorCode.CANONICAL_IDENTIFIER_COLLISION,
                f"canonical identifier collision between {prior!r} and {field.name!r}",
            )
        seen[name_utf8] = field.name
        prepared.append((name_utf8, field))

    prepared.sort(key=lambda item: item[0])

    parts = bytearray(encode_uleb128(len(prepared)))
    for name_utf8, field in prepared:
        encoded = encode_typed_scalar(field.declared_type, field.typed_value)
        parts.extend(encode_uleb128(len(name_utf8)))
        parts.extend(name_utf8)
        parts.extend(encoded.scalar_frame)

    row_frame = bytes(parts)
    digest = semantic_digest(DigestKind.ROW, row_frame)
    return EncodedRow(
        row_frame=row_frame,
        raw_hash=digest.raw_digest,
        digest_ref=digest.digest_ref,
    )


def encode_collection(
    semantics: CollectionSemantics,
    *,
    items: Sequence[bytes] | None = None,
    entries: Sequence[tuple[bytes, bytes]] | None = None,
) -> EncodedCollection:
    """Encode a collection under explicit ``CollectionSemantics`` (no host-type guessing)."""
    if type(semantics) is not CollectionSemantics:
        raise CanonicalEncodingError(
            CanonicalErrorCode.CANONICAL_COLLECTION_SEMANTICS_UNKNOWN,
            "collection semantics must be CollectionSemantics",
        )

    if semantics is CollectionSemantics.KEYED_COLLECTION:
        if entries is None or items is not None:
            raise CanonicalEncodingError(
                CanonicalErrorCode.CANONICAL_TYPE_MISMATCH,
                "keyed-collection requires entries and rejects items",
            )
        frame = _encode_keyed_collection(entries)
    else:
        if items is None or entries is not None:
            raise CanonicalEncodingError(
                CanonicalErrorCode.CANONICAL_TYPE_MISMATCH,
                f"{semantics.value} requires items and rejects entries",
            )
        if semantics is CollectionSemantics.SEQUENCE:
            frame = _encode_sequence(items)
        elif semantics is CollectionSemantics.MULTISET:
            frame = _encode_hash_collection(items, allow_duplicates=True)
        else:
            frame = _encode_hash_collection(items, allow_duplicates=False)

    return EncodedCollection(collection_frame=frame)


def _encode_sequence(items: Sequence[bytes]) -> bytes:
    _assert_sequence(items, "items")
    parts = bytearray(encode_uleb128(len(items)))
    for index, item in enumerate(items):
        if type(item) is not bytes:
            raise CanonicalEncodingError(
                CanonicalErrorCode.CANONICAL_TYPE_MISMATCH,
                f"items[{index}] must be bytes",
            )
        parts.extend(_framed_item(item))
    return bytes(parts)


def _encode_hash_collection(items: Sequence[bytes], *, allow_duplicates: bool) -> bytes:
    _assert_sequence(items, "items")
    hashes: list[bytes] = []
    for index, item in enumerate(items):
        if type(item) is not bytes:
            raise CanonicalEncodingError(
                CanonicalErrorCode.CANONICAL_TYPE_MISMATCH,
                f"items[{index}] must be bytes",
            )
        hashes.append(_item_hash(item))

    hashes.sort()
    if not allow_duplicates:
        for index in range(1, len(hashes)):
            if hashes[index] == hashes[index - 1]:
                raise CanonicalEncodingError(
                    CanonicalErrorCode.CANONICAL_COLLECTION_DUPLICATE_ITEM,
                    "set collection rejects duplicate item hashes",
                )

    parts = bytearray(encode_uleb128(len(hashes)))
    for item_hash in hashes:
        parts.extend(item_hash)
    return bytes(parts)


def _encode_keyed_collection(entries: Sequence[tuple[bytes, bytes]]) -> bytes:
    _assert_sequence(entries, "entries")
    prepared: list[tuple[bytes, bytes]] = []
    seen: set[bytes] = set()
    for index, entry in enumerate(entries):
        if type(entry) is not tuple or len(entry) != 2:
            raise CanonicalEncodingError(
                CanonicalErrorCode.CANONICAL_TYPE_MISMATCH,
                f"entries[{index}] must be a (key, value) tuple",
            )
        key, value = entry
        if type(key) is not bytes or type(value) is not bytes:
            raise CanonicalEncodingError(
                CanonicalErrorCode.CANONICAL_TYPE_MISMATCH,
                f"entries[{index}] key and value must be bytes",
            )
        if key in seen:
            raise CanonicalEncodingError(
                CanonicalErrorCode.CANONICAL_COLLECTION_DUPLICATE_KEY,
                "keyed-collection rejects duplicate keys",
            )
        seen.add(key)
        prepared.append((key, value))

    prepared.sort(key=lambda item: item[0])

    parts = bytearray(encode_uleb128(len(prepared)))
    for key, value in prepared:
        parts.extend(encode_uleb128(len(key)))
        parts.extend(key)
        parts.extend(encode_uleb128(len(value)))
        parts.extend(value)
    return bytes(parts)


def _framed_item(item_bytes: bytes) -> bytes:
    return encode_uleb128(len(item_bytes)) + item_bytes


def _item_hash(item_bytes: bytes) -> bytes:
    return semantic_digest(DigestKind.COLLECTION_ITEM, _framed_item(item_bytes)).raw_digest


def _assert_sequence(value: object, label: str) -> None:
    if isinstance(value, (str, bytes, bytearray)) or not isinstance(value, Sequence):
        raise CanonicalEncodingError(
            CanonicalErrorCode.CANONICAL_TYPE_MISMATCH,
            f"{label} must be a sequence",
        )


_RAW_ROW_HASH_LEN = 32


def encode_unordered_row_hashes_frame(row_hashes: Sequence[bytes]) -> bytes:
    """Encode unordered table frame: ULEB128(count) + sorted 32-byte row hashes."""
    _assert_sequence(row_hashes, "row_hashes")
    hashes: list[bytes] = []
    for index, item in enumerate(row_hashes):
        if type(item) is not bytes:
            raise CanonicalEncodingError(
                CanonicalErrorCode.CANONICAL_TYPE_MISMATCH,
                f"row_hashes[{index}] must be bytes",
            )
        if len(item) != _RAW_ROW_HASH_LEN:
            raise CanonicalEncodingError(
                CanonicalErrorCode.CANONICAL_FRAME_LENGTH_INVALID,
                "row hash must be exactly 32 bytes",
            )
        hashes.append(item)
    hashes.sort()
    parts = bytearray(encode_uleb128(len(hashes)))
    for item_hash in hashes:
        parts.extend(item_hash)
    return bytes(parts)


def _sort_fixed_width_chunks_inplace(buf: bytearray, *, width: int) -> None:
    if len(buf) % width != 0:
        raise CanonicalEncodingError(
            CanonicalErrorCode.CANONICAL_FRAME_LENGTH_INVALID,
            "row buffer length must be a multiple of row hash width",
        )
    row_count = len(buf) // width
    if row_count < 2:
        return
    order = sorted(range(row_count), key=lambda index: buf[index * width : (index + 1) * width])
    if order == list(range(row_count)):
        return
    scratch = bytearray(buf)
    for new_index, old_index in enumerate(order):
        start = new_index * width
        old_start = old_index * width
        buf[start : start + width] = scratch[old_start : old_start + width]


def encode_unordered_row_hashes_frame_from_row_buffer(
    buf: bytes | bytearray,
    row_count: int,
) -> bytes:
    """Encode unordered table frame from a contiguous 32-byte row-hash buffer."""
    expected_len = row_count * _RAW_ROW_HASH_LEN
    if len(buf) != expected_len:
        raise CanonicalEncodingError(
            CanonicalErrorCode.CANONICAL_FRAME_LENGTH_INVALID,
            "row buffer length does not match row_count",
        )
    if row_count == 0:
        return encode_uleb128(0)
    working = bytearray(buf)
    _sort_fixed_width_chunks_inplace(working, width=_RAW_ROW_HASH_LEN)
    parts = bytearray(encode_uleb128(row_count))
    parts.extend(working)
    return bytes(parts)


def encode_sorted_row_hashes_frame(buf: bytes | bytearray, row_count: int) -> bytes:
    """Encode table frame from an already unsigned-sorted contiguous row-hash buffer."""
    expected_len = row_count * _RAW_ROW_HASH_LEN
    if len(buf) != expected_len:
        raise CanonicalEncodingError(
            CanonicalErrorCode.CANONICAL_FRAME_LENGTH_INVALID,
            "row buffer length does not match row_count",
        )
    if row_count == 0:
        return encode_uleb128(0)
    parts = bytearray(encode_uleb128(row_count))
    parts.extend(buf)
    return bytes(parts)


def unordered_row_hashes_content_digest(
    row_hashes: Sequence[bytes],
) -> SemanticDigest:
    """Unordered raw-content digest over raw 32-byte row hashes (duplicates retained)."""
    frame = encode_unordered_row_hashes_frame(row_hashes)
    return semantic_digest(DigestKind.RAW_CONTENT, frame)


def unordered_row_hashes_content_digest_from_row_buffer(
    buf: bytes | bytearray,
    row_count: int,
) -> SemanticDigest:
    """Unordered raw-content digest over a contiguous row-hash buffer."""
    frame = encode_unordered_row_hashes_frame_from_row_buffer(buf, row_count)
    return semantic_digest(DigestKind.RAW_CONTENT, frame)


def unordered_row_hashes_content_digest_from_sorted_row_buffer(
    buf: bytes | bytearray,
    row_count: int,
) -> SemanticDigest:
    """Raw-content digest over an already unsigned-sorted contiguous row-hash buffer."""
    frame = encode_sorted_row_hashes_frame(buf, row_count)
    return semantic_digest(DigestKind.RAW_CONTENT, frame)
