"""Digest / row / collection / framing-invalid candidate seeds."""

from __future__ import annotations

from gateway_shared_kernel import DigestKind
from gateway_shared_kernel.testing.cases import CaseSeed
from gateway_shared_kernel.testing.codec import encode_base64url
from gateway_shared_kernel.uleb128 import encode_uleb128

# Fixed empty row frame (ULEB128(0)); semantic-digest copies this literal.
FIXED_EMPTY_ROW_FRAME = b"\x00"

# Fixed sequence frame for items [b"a", b"b"].
FIXED_SEQUENCE_FRAME = b"\x02\x01a\x01b"


def digest_seeds() -> list[CaseSeed]:
    seeds: list[CaseSeed] = [
        CaseSeed(
            case_id="digest.identifier.ascii-fold",
            bucket="digest",
            operation="canonicalize-identifier",
            input={"identifier": "AbC_1"},
        ),
        CaseSeed(
            case_id="digest.row.empty",
            bucket="digest",
            operation="encode-row",
            input={"fields": []},
        ),
        CaseSeed(
            case_id="digest.row.mixed-fields-permuted-a",
            bucket="digest",
            operation="encode-row",
            input={
                "fields": [
                    {
                        "name": "b",
                        "declared_type": {"kind": "null"},
                        "typed_value": {"kind": "null"},
                    },
                    {
                        "name": "A",
                        "declared_type": {"kind": "boolean"},
                        "typed_value": {"kind": "boolean", "value": True},
                    },
                ]
            },
        ),
        CaseSeed(
            case_id="digest.row.mixed-fields-permuted-b",
            bucket="digest",
            operation="encode-row",
            input={
                "fields": [
                    {
                        "name": "A",
                        "declared_type": {"kind": "boolean"},
                        "typed_value": {"kind": "boolean", "value": True},
                    },
                    {
                        "name": "b",
                        "declared_type": {"kind": "null"},
                        "typed_value": {"kind": "null"},
                    },
                ]
            },
        ),
        CaseSeed(
            case_id="digest.collection.sequence.fixed",
            bucket="digest",
            operation="encode-collection",
            input={
                "semantics": "sequence",
                "items_base64url": [
                    encode_base64url(b"a"),
                    encode_base64url(b"b"),
                ],
            },
        ),
        CaseSeed(
            case_id="digest.collection.multiset.duplicates",
            bucket="digest",
            operation="encode-collection",
            input={
                "semantics": "multiset",
                "items_base64url": [
                    encode_base64url(b"b"),
                    encode_base64url(b"a"),
                    encode_base64url(b"a"),
                ],
            },
        ),
        CaseSeed(
            case_id="digest.collection.set.unique",
            bucket="digest",
            operation="encode-collection",
            input={
                "semantics": "set",
                "items_base64url": [
                    encode_base64url(b"c"),
                    encode_base64url(b"a"),
                    encode_base64url(b"b"),
                ],
            },
        ),
        CaseSeed(
            case_id="digest.collection.keyed.sorted",
            bucket="digest",
            operation="encode-collection",
            input={
                "semantics": "keyed-collection",
                "entries": [
                    {
                        "key_base64url": encode_base64url(b"b"),
                        "value_base64url": encode_base64url(b"2"),
                    },
                    {
                        "key_base64url": encode_base64url(b"a"),
                        "value_base64url": encode_base64url(b"1"),
                    },
                ],
            },
        ),
        CaseSeed(
            case_id="digest.semantic.row-empty-frame",
            bucket="digest",
            operation="semantic-digest",
            input={
                "digest_kind": DigestKind.ROW.value,
                "canonical_payload_base64url": encode_base64url(FIXED_EMPTY_ROW_FRAME),
            },
        ),
        CaseSeed(
            case_id="digest.raw-blob.payload",
            bucket="digest",
            operation="raw-blob-digest",
            input={"raw_bytes_base64url": encode_base64url(b"payload")},
        ),
        CaseSeed(
            case_id="invalid.digest.identifier.empty",
            bucket="invalid",
            operation="canonicalize-identifier",
            input={"identifier": ""},
            expected_error="CANONICAL_IDENTIFIER_EMPTY",
        ),
        CaseSeed(
            case_id="invalid.digest.identifier.collision",
            bucket="invalid",
            operation="encode-row",
            input={
                "fields": [
                    {
                        "name": "Id",
                        "declared_type": {"kind": "null"},
                        "typed_value": {"kind": "null"},
                    },
                    {
                        "name": "id",
                        "declared_type": {"kind": "null"},
                        "typed_value": {"kind": "null"},
                    },
                ]
            },
            expected_error="CANONICAL_IDENTIFIER_COLLISION",
        ),
        CaseSeed(
            case_id="invalid.digest.collection.set-duplicate",
            bucket="invalid",
            operation="encode-collection",
            input={
                "semantics": "set",
                "items_base64url": [
                    encode_base64url(b"a"),
                    encode_base64url(b"a"),
                ],
            },
            expected_error="CANONICAL_COLLECTION_DUPLICATE_ITEM",
        ),
        CaseSeed(
            case_id="invalid.digest.collection.keyed-duplicate",
            bucket="invalid",
            operation="encode-collection",
            input={
                "semantics": "keyed-collection",
                "entries": [
                    {
                        "key_base64url": encode_base64url(b"k"),
                        "value_base64url": encode_base64url(b"1"),
                    },
                    {
                        "key_base64url": encode_base64url(b"k"),
                        "value_base64url": encode_base64url(b"2"),
                    },
                ],
            },
            expected_error="CANONICAL_COLLECTION_DUPLICATE_KEY",
        ),
    ]

    for kind in DigestKind:
        seeds.append(
            CaseSeed(
                case_id=f"digest.semantic.domain.{kind.value}",
                bucket="digest",
                operation="semantic-digest",
                input={
                    "digest_kind": kind.value,
                    "canonical_payload_base64url": encode_base64url(b"same-payload"),
                },
            )
        )

    # Framing invalid via validate-scalar-frame
    seeds.extend(
        [
            CaseSeed(
                case_id="invalid.frame.empty",
                bucket="invalid",
                operation="validate-scalar-frame",
                input={"frame_base64url": encode_base64url(b"")},
                expected_error="CANONICAL_FRAME_TRUNCATED",
            ),
            CaseSeed(
                case_id="invalid.frame.uleb128.non-minimal",
                bucket="invalid",
                operation="validate-scalar-frame",
                # tag null + non-minimal ULEB length 0 encoded as 0x80 0x00
                input={"frame_base64url": encode_base64url(b"\x00\x80\x00")},
                expected_error="CANONICAL_ULEB128_NON_MINIMAL",
            ),
            CaseSeed(
                case_id="invalid.frame.uleb128.overflow",
                bucket="invalid",
                operation="validate-scalar-frame",
                input={
                    "frame_base64url": encode_base64url(
                        b"\x20" + bytes([0xFF] * 9) + b"\x01"
                    )
                },
                expected_error="CANONICAL_ULEB128_OVERFLOW",
            ),
            CaseSeed(
                case_id="invalid.frame.truncated-payload",
                bucket="invalid",
                operation="validate-scalar-frame",
                input={
                    "frame_base64url": encode_base64url(
                        bytes([0x20]) + encode_uleb128(2) + b"a"
                    )
                },
                expected_error="CANONICAL_FRAME_TRUNCATED",
            ),
            CaseSeed(
                case_id="invalid.frame.trailing-bytes",
                bucket="invalid",
                operation="validate-scalar-frame",
                input={"frame_base64url": encode_base64url(b"\x00\x00\xff")},
                expected_error="CANONICAL_FRAME_LENGTH_INVALID",
            ),
            CaseSeed(
                case_id="invalid.frame.tag-reserved",
                bucket="invalid",
                operation="validate-scalar-frame",
                input={"frame_base64url": encode_base64url(b"\x02\x00")},
                expected_error="CANONICAL_SCALAR_TAG_RESERVED",
            ),
            CaseSeed(
                case_id="invalid.frame.tag-unknown",
                bucket="invalid",
                operation="validate-scalar-frame",
                input={"frame_base64url": encode_base64url(b"\x80\x00")},
                expected_error="CANONICAL_SCALAR_TAG_UNKNOWN",
            ),
            CaseSeed(
                case_id="invalid.frame.boolean-length",
                bucket="invalid",
                operation="validate-scalar-frame",
                input={"frame_base64url": encode_base64url(b"\x01\x02\x00\x01")},
                expected_error="CANONICAL_FRAME_LENGTH_INVALID",
            ),
        ]
    )
    return seeds
