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
