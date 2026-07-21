"""Hypothesis property tests for row/collection framing and digests."""

from __future__ import annotations

import hashlib
import json

from hypothesis import given, settings, strategies as st

from gateway_shared_kernel import (
    CanonicalEncodingError,
    CanonicalErrorCode,
    CollectionSemantics,
    DeclaredType,
    DeclaredTypeKind,
    DigestKind,
    NullScalar,
    RowField,
    encode_collection,
    encode_row,
    raw_blob_digest,
    semantic_digest,
)

# Fixed budget + deterministic (derandomize) configuration per Phase 1 plan §5.4.
_PROP = settings(max_examples=40, deadline=None, derandomize=True)

_FORMAL_DOMAIN = {
    kind: f"gateway-vnext:{kind.value}:v1\0".encode("ascii") for kind in DigestKind
}


def _null_field(name: str) -> RowField:
    return RowField(
        name=name,
        declared_type=DeclaredType(kind=DeclaredTypeKind.NULL),
        typed_value=NullScalar(),
    )


@st.composite
def unique_ascii_field_names(draw: st.DrawFn) -> list[str]:
    """ASCII names that remain unique after CanonicalIdentifier fold."""
    count = draw(st.integers(min_value=0, max_value=6))
    names: list[str] = []
    seen: set[str] = set()
    for _ in range(count):
        name = draw(
            st.text(
                alphabet=st.characters(min_codepoint=33, max_codepoint=126),
                min_size=1,
                max_size=8,
            )
        )
        folded = "".join(
            chr(ord(ch) + 32) if "A" <= ch <= "Z" else ch for ch in name
        )
        if folded in seen:
            continue
        seen.add(folded)
        names.append(name)
    return names


@_PROP
@given(unique_ascii_field_names())
def test_row_field_permutation_invariance(names: list[str]) -> None:
    fields = [_null_field(name) for name in names]
    base = encode_row(fields)
    for order in (list(reversed(fields)), sorted(fields, key=lambda f: f.name)):
        assert encode_row(order).row_frame == base.row_frame
        assert encode_row(order).raw_hash == base.raw_hash


@_PROP
@given(st.lists(st.binary(max_size=16), max_size=8))
def test_sequence_preserves_order(items: list[bytes]) -> None:
    encoded = encode_collection(CollectionSemantics.SEQUENCE, items=items)
    again = encode_collection(CollectionSemantics.SEQUENCE, items=list(items))
    assert encoded.collection_frame == again.collection_frame
    if len(items) >= 2 and items != list(reversed(items)):
        reversed_frame = encode_collection(
            CollectionSemantics.SEQUENCE,
            items=list(reversed(items)),
        ).collection_frame
        assert reversed_frame != encoded.collection_frame


@_PROP
@given(st.lists(st.binary(max_size=16), max_size=8))
def test_multiset_permutation_invariance(items: list[bytes]) -> None:
    base = encode_collection(CollectionSemantics.MULTISET, items=items)
    permuted = encode_collection(
        CollectionSemantics.MULTISET,
        items=list(reversed(items)),
    )
    assert permuted.collection_frame == base.collection_frame


@_PROP
@given(st.lists(st.binary(max_size=16), max_size=8, unique=True))
def test_set_permutation_invariance(items: list[bytes]) -> None:
    base = encode_collection(CollectionSemantics.SET, items=items)
    permuted = encode_collection(CollectionSemantics.SET, items=list(reversed(items)))
    assert permuted.collection_frame == base.collection_frame


@_PROP
@given(
    st.lists(st.binary(max_size=12), min_size=1, max_size=6),
    st.data(),
)
def test_set_duplicate_item_rejected(
    items: list[bytes],
    data: st.DataObject,
) -> None:
    duplicate = data.draw(st.sampled_from(items))
    with_dup = list(items) + [duplicate]
    orders = [
        with_dup,
        list(reversed(with_dup)),
        list(data.draw(st.permutations(with_dup))),
    ]
    for order in orders:
        try:
            encode_collection(CollectionSemantics.SET, items=order)
        except CanonicalEncodingError as exc:
            assert exc.code is CanonicalErrorCode.CANONICAL_COLLECTION_DUPLICATE_ITEM
        else:
            raise AssertionError(
                "expected CANONICAL_COLLECTION_DUPLICATE_ITEM "
                f"for order={order!r}"
            )


@st.composite
def unique_keyed_entries(draw: st.DrawFn) -> list[tuple[bytes, bytes]]:
    count = draw(st.integers(min_value=0, max_value=6))
    entries: list[tuple[bytes, bytes]] = []
    seen: set[bytes] = set()
    for _ in range(count):
        key = draw(st.binary(max_size=12))
        if key in seen:
            continue
        seen.add(key)
        value = draw(st.binary(max_size=12))
        entries.append((key, value))
    return entries


@_PROP
@given(unique_keyed_entries())
def test_keyed_permutation_invariance(entries: list[tuple[bytes, bytes]]) -> None:
    base = encode_collection(CollectionSemantics.KEYED_COLLECTION, entries=entries)
    permuted = encode_collection(
        CollectionSemantics.KEYED_COLLECTION,
        entries=list(reversed(entries)),
    )
    assert permuted.collection_frame == base.collection_frame


@_PROP
@given(st.binary(max_size=32))
def test_digest_domain_separation_property(payload: bytes) -> None:
    digests = [semantic_digest(kind, payload).raw_digest for kind in DigestKind]
    assert len(set(digests)) == len(DigestKind)
    for kind, raw in zip(DigestKind, digests, strict=True):
        assert raw == hashlib.sha256(_FORMAL_DOMAIN[kind] + payload).digest()
    assert raw_blob_digest(payload).raw_digest == hashlib.sha256(payload).digest()
    assert raw_blob_digest(payload).raw_digest != digests[
        list(DigestKind).index(DigestKind.RAW_CONTENT)
    ]


@_PROP
@given(
    st.dictionaries(
        keys=st.text(
            alphabet=st.characters(min_codepoint=97, max_codepoint=122),
            min_size=1,
            max_size=4,
        ),
        values=st.integers(min_value=-(2**53) + 1, max_value=(2**53) - 1),
        max_size=5,
    )
)
def test_jcs_idempotence_and_determinism(obj: dict[str, int]) -> None:
    from gateway_shared_kernel.jcs import canonicalize_json_value

    reversed_obj = {key: obj[key] for key in reversed(list(obj))}
    first = canonicalize_json_value(obj)
    second = canonicalize_json_value(reversed_obj)
    assert first == second
    assert canonicalize_json_value(json.loads(first.decode("utf-8"))) == first


@_PROP
@given(st.integers(min_value=0, max_value=(1 << 63) - 1))
def test_uleb128_minimality_roundtrip(value: int) -> None:
    from gateway_shared_kernel.uleb128 import decode_uleb128, encode_uleb128

    encoded = encode_uleb128(value)
    decoded, next_offset = decode_uleb128(encoded)
    assert decoded == value
    assert next_offset == len(encoded)
    assert encode_uleb128(decoded) == encoded
