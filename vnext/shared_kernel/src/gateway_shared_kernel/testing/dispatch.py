"""Dispatch a single vector case against production or test-only helpers."""

from __future__ import annotations

from typing import Any

from gateway_shared_kernel import (
    AnomalyScalar,
    BinaryScalar,
    BitScalar,
    BooleanScalar,
    CanonicalEncodingError,
    CanonicalErrorCode,
    CollectionSemantics,
    DateScalar,
    DateTimeScalar,
    DecimalScalar,
    DeclaredType,
    DeclaredTypeKind,
    DigestKind,
    Float32Scalar,
    Float64Scalar,
    NullScalar,
    RawLogicalLiteral,
    RowField,
    SignedIntegerScalar,
    StringScalar,
    TimeDurationScalar,
    TimestampScalar,
    TypedScalar,
    UnsignedIntegerScalar,
    Utf8LogicalLiteral,
    canonicalize_identifier,
    canonicalize_jcs,
    encode_collection,
    encode_row,
    encode_typed_scalar,
    normalize_logical_literal,
    raw_blob_digest,
    semantic_digest,
)
from gateway_shared_kernel.testing.codec import decode_base64url_strict, encode_base64url
from gateway_shared_kernel.testing.validate_frame import validate_scalar_frame


class DispatchMismatch(AssertionError):
    """Raised when a valid case expected value does not match the implementation."""


def dispatch_case(case: dict[str, Any]) -> None:
    """Execute ``case`` and compare expected output or stable error code."""
    operation = case["operation"]
    if "expected_error" in case:
        _dispatch_invalid(operation, case["input"], case["expected_error"]["code"])
        return
    expected = case["expected"]
    actual = _compute_expected(operation, case["input"])
    if actual != expected:
        raise DispatchMismatch(
            f"case {case.get('case_id')!r} mismatch:\n"
            f"  actual={actual!r}\n"
            f"  expected={expected!r}"
        )


def compute_expected(operation: str, input_obj: dict[str, Any]) -> dict[str, Any]:
    """Compute valid-case expected fields from logical input (for generation)."""
    return _compute_expected(operation, input_obj)


def _dispatch_invalid(operation: str, input_obj: dict[str, Any], code: str) -> None:
    try:
        if operation == "validate-scalar-frame":
            validate_scalar_frame(decode_base64url_strict(input_obj["frame_base64url"]))
        else:
            _compute_expected(operation, input_obj)
    except CanonicalEncodingError as exc:
        if exc.code.value != code:
            raise DispatchMismatch(
                f"expected stable code {code}, got {exc.code.value}"
            ) from exc
        return
    raise DispatchMismatch(f"expected stable code {code}, but operation succeeded")


def _compute_expected(operation: str, input_obj: dict[str, Any]) -> dict[str, Any]:
    if operation == "canonicalize-jcs":
        out = canonicalize_jcs(decode_base64url_strict(input_obj["json_utf8_base64url"]))
        return {"canonical_bytes_base64url": encode_base64url(out)}

    if operation == "normalize-logical-literal":
        declared = _parse_declared_type(input_obj["declared_type"])
        source = _parse_logical_literal(input_obj["source"])
        normalized = normalize_logical_literal(declared, source)
        return {
            "typed_value": _typed_value_to_dict(normalized.typed_value),
            "payload_base64url": encode_base64url(normalized.payload),
            "scalar_frame_base64url": encode_base64url(normalized.scalar_frame),
        }

    if operation == "encode-typed-scalar":
        declared = _parse_declared_type(input_obj["declared_type"])
        typed = _parse_typed_value(input_obj["typed_value"])
        encoded_scalar = encode_typed_scalar(declared, typed)
        return {
            "payload_base64url": encode_base64url(encoded_scalar.payload),
            "scalar_frame_base64url": encode_base64url(encoded_scalar.scalar_frame),
        }

    if operation == "canonicalize-identifier":
        canonical = canonicalize_identifier(input_obj["identifier"])
        return {"canonical_utf8_base64url": encode_base64url(canonical.encode("utf-8"))}

    if operation == "encode-row":
        fields = [
            RowField(
                name=item["name"],
                declared_type=_parse_declared_type(item["declared_type"]),
                typed_value=_parse_typed_value(item["typed_value"]),
            )
            for item in input_obj["fields"]
        ]
        encoded_row = encode_row(fields)
        return {
            "row_frame_base64url": encode_base64url(encoded_row.row_frame),
            "row_hash": encoded_row.digest_ref.value,
        }

    if operation == "encode-collection":
        semantics = CollectionSemantics(input_obj["semantics"])
        if semantics is CollectionSemantics.KEYED_COLLECTION:
            entries = [
                (
                    decode_base64url_strict(entry["key_base64url"]),
                    decode_base64url_strict(entry["value_base64url"]),
                )
                for entry in input_obj["entries"]
            ]
            encoded_collection = encode_collection(semantics, entries=entries)
        else:
            items = [
                decode_base64url_strict(item) for item in input_obj["items_base64url"]
            ]
            encoded_collection = encode_collection(semantics, items=items)
        return {
            "collection_frame_base64url": encode_base64url(
                encoded_collection.collection_frame
            ),
        }

    if operation == "semantic-digest":
        kind = DigestKind(input_obj["digest_kind"])
        payload = decode_base64url_strict(input_obj["canonical_payload_base64url"])
        digest = semantic_digest(kind, payload)
        return {
            "raw_hash_base64url": encode_base64url(digest.raw_digest),
            "digest_ref": digest.digest_ref.value,
        }

    if operation == "raw-blob-digest":
        raw = decode_base64url_strict(input_obj["raw_bytes_base64url"])
        return {"digest_ref": raw_blob_digest(raw).value}

    if operation == "validate-scalar-frame":
        validate_scalar_frame(decode_base64url_strict(input_obj["frame_base64url"]))
        return {}

    raise CanonicalEncodingError(
        CanonicalErrorCode.CANONICAL_TYPE_MISMATCH,
        f"unsupported operation {operation!r}",
    )


def _parse_declared_type(obj: dict[str, Any]) -> DeclaredType:
    kind = DeclaredTypeKind(obj["kind"])
    return DeclaredType(
        kind=kind,
        bits=obj.get("bits"),
        precision=obj.get("precision"),
        scale=obj.get("scale"),
        bit_width=obj.get("bit_width"),
    )


def _parse_logical_literal(
    obj: dict[str, Any],
) -> Utf8LogicalLiteral | RawLogicalLiteral:
    if obj["kind"] == "utf8-logical-literal":
        return Utf8LogicalLiteral(text=obj["text"])
    if obj["kind"] == "raw-logical-literal":
        return RawLogicalLiteral(raw_bytes=decode_base64url_strict(obj["bytes_base64url"]))
    raise CanonicalEncodingError(
        CanonicalErrorCode.CANONICAL_TYPE_MISMATCH,
        f"unknown logical literal kind {obj['kind']!r}",
    )


def _parse_typed_value(obj: dict[str, Any]) -> TypedScalar:
    kind = obj["kind"]
    if kind == "null":
        return NullScalar()
    if kind == "boolean":
        return BooleanScalar(value=obj["value"])
    if kind == "signed-integer":
        return SignedIntegerScalar(decimal=obj["decimal"])
    if kind == "unsigned-integer":
        return UnsignedIntegerScalar(decimal=obj["decimal"])
    if kind == "decimal":
        return DecimalScalar(decimal=obj["decimal"])
    if kind == "float32":
        return Float32Scalar(bits_hex=obj["bits_hex"])
    if kind == "float64":
        return Float64Scalar(bits_hex=obj["bits_hex"])
    if kind == "string":
        return StringScalar(text=obj["text"])
    if kind == "binary":
        return BinaryScalar(raw_bytes=decode_base64url_strict(obj["bytes_base64url"]))
    if kind == "bit":
        return BitScalar(raw_bytes=decode_base64url_strict(obj["bytes_base64url"]))
    if kind == "date":
        return DateScalar(text=obj["text"])
    if kind == "datetime":
        return DateTimeScalar(text=obj["text"])
    if kind == "timestamp":
        return TimestampScalar(text=obj["text"])
    if kind == "time-duration":
        return TimeDurationScalar(text=obj["text"])
    if kind == "source-literal-anomaly":
        return AnomalyScalar(envelope=obj["envelope"])
    raise CanonicalEncodingError(
        CanonicalErrorCode.CANONICAL_TYPE_MISMATCH,
        f"unknown typed value kind {kind!r}",
    )


def _typed_value_to_dict(value: TypedScalar) -> dict[str, Any]:
    if isinstance(value, NullScalar):
        return {"kind": "null"}
    if isinstance(value, BooleanScalar):
        return {"kind": "boolean", "value": value.value}
    if isinstance(value, SignedIntegerScalar):
        return {"kind": "signed-integer", "decimal": value.decimal}
    if isinstance(value, UnsignedIntegerScalar):
        return {"kind": "unsigned-integer", "decimal": value.decimal}
    if isinstance(value, DecimalScalar):
        return {"kind": "decimal", "decimal": value.decimal}
    if isinstance(value, Float32Scalar):
        return {"kind": "float32", "bits_hex": value.bits_hex}
    if isinstance(value, Float64Scalar):
        return {"kind": "float64", "bits_hex": value.bits_hex}
    if isinstance(value, StringScalar):
        return {"kind": "string", "text": value.text}
    if isinstance(value, BinaryScalar):
        return {
            "kind": "binary",
            "bytes_base64url": encode_base64url(value.raw_bytes),
        }
    if isinstance(value, BitScalar):
        return {
            "kind": "bit",
            "bytes_base64url": encode_base64url(value.raw_bytes),
        }
    if isinstance(value, DateScalar):
        return {"kind": "date", "text": value.text}
    if isinstance(value, DateTimeScalar):
        return {"kind": "datetime", "text": value.text}
    if isinstance(value, TimestampScalar):
        return {"kind": "timestamp", "text": value.text}
    if isinstance(value, TimeDurationScalar):
        return {"kind": "time-duration", "text": value.text}
    if isinstance(value, AnomalyScalar):
        return {"kind": "source-literal-anomaly", "envelope": dict(value.envelope)}
    raise CanonicalEncodingError(
        CanonicalErrorCode.CANONICAL_TYPE_MISMATCH,
        "unsupported typed scalar for vector export",
    )
