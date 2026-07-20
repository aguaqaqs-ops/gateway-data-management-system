"""Production typed-model registry and construction tests."""

from __future__ import annotations

import pytest

from gateway_shared_kernel import (
    CollectionSemantics,
    DeclaredType,
    DeclaredTypeKind,
    DigestKind,
    DigestRef,
    EncodedCollection,
    EncodedRow,
    NullScalar,
    RowField,
    SemanticDigest,
)
from gateway_shared_kernel.types import FORMAL_COLLECTION_SEMANTICS, FORMAL_DIGEST_KINDS

_EXPECTED_DIGEST_KINDS = frozenset(
    {
        "row",
        "raw-content",
        "collection-item",
        "vector-set",
        "table-schema",
        "scenario-input",
        "scenario-fixture",
    }
)

_EXPECTED_COLLECTION_SEMANTICS = frozenset(
    {
        "sequence",
        "multiset",
        "set",
        "keyed-collection",
    }
)


def test_digest_kind_registry_matches_formal_contract() -> None:
    actual = frozenset(kind.value for kind in DigestKind)
    assert actual == _EXPECTED_DIGEST_KINDS
    assert FORMAL_DIGEST_KINDS == frozenset(DigestKind)


def test_collection_semantics_registry_matches_formal_contract() -> None:
    actual = frozenset(item.value for item in CollectionSemantics)
    assert actual == _EXPECTED_COLLECTION_SEMANTICS
    assert FORMAL_COLLECTION_SEMANTICS == frozenset(CollectionSemantics)


def test_digest_ref_from_raw_and_rejects_invalid() -> None:
    raw = bytes(range(32))
    ref = DigestRef.from_raw_digest(raw)
    assert ref.value.startswith("sha256:")
    assert ref.raw_digest == raw

    with pytest.raises(ValueError):
        DigestRef.from_raw_digest(b"short")
    with pytest.raises(ValueError):
        DigestRef("sha256:" + ("0" * 63))
    with pytest.raises(ValueError):
        DigestRef("sha256:" + ("A" * 64))


def test_semantic_digest_and_encoded_row_consistency() -> None:
    raw = bytes([1]) * 32
    digest = SemanticDigest.from_raw(DigestKind.ROW, raw)
    assert digest.kind is DigestKind.ROW
    assert digest.digest_ref.raw_digest == raw

    row = EncodedRow(row_frame=b"\x00", raw_hash=raw, digest_ref=digest.digest_ref)
    assert row.digest_ref.value == digest.digest_ref.value

    with pytest.raises(ValueError):
        SemanticDigest(
            kind=DigestKind.ROW,
            raw_digest=raw,
            digest_ref=DigestRef.from_raw_digest(bytes([2]) * 32),
        )


def test_row_field_and_encoded_collection_shape() -> None:
    field = RowField(
        name="Id",
        declared_type=DeclaredType(kind=DeclaredTypeKind.NULL),
        typed_value=NullScalar(),
    )
    assert field.name == "Id"

    encoded = EncodedCollection(collection_frame=b"\x00", digest_ref=None)
    assert encoded.digest_ref is None
