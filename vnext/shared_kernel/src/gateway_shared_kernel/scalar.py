"""Typed scalar normalization and frame encoding."""

from __future__ import annotations

import math
import re
import struct
from collections.abc import Callable, Mapping
from typing import Any, cast

from gateway_shared_kernel.base64url import decode_base64url_strict
from gateway_shared_kernel.errors import CanonicalEncodingError, CanonicalErrorCode
from gateway_shared_kernel.jcs import canonicalize_json_value
from gateway_shared_kernel.types import (
    AnomalyScalar,
    BinaryScalar,
    BitScalar,
    BooleanScalar,
    DateScalar,
    DateTimeScalar,
    DecimalScalar,
    DeclaredType,
    DeclaredTypeKind,
    EncodedScalar,
    Float32Scalar,
    Float64Scalar,
    LogicalLiteral,
    NormalizedScalar,
    NullScalar,
    RawLogicalLiteral,
    SignedIntegerScalar,
    StringScalar,
    TimeDurationScalar,
    TimestampScalar,
    TypedScalar,
    UnsignedIntegerScalar,
    Utf8LogicalLiteral,
)
from gateway_shared_kernel.uleb128 import encode_uleb128
from gateway_shared_kernel.unicode import decode_utf8, validate_unicode_string

TAG_NULL = 0x00
TAG_BOOLEAN = 0x01
TAG_SIGNED_INTEGER = 0x10
TAG_UNSIGNED_INTEGER = 0x11
TAG_DECIMAL = 0x12
TAG_FLOAT32 = 0x13
TAG_FLOAT64 = 0x14
TAG_STRING = 0x20
TAG_BINARY = 0x21
TAG_DATE = 0x30
TAG_DATETIME = 0x31
TAG_TIMESTAMP = 0x32
TAG_TIME_DURATION = 0x33
TAG_ANOMALY = 0x7F

_LEADING_ZERO_BUDGET = 16
_ASCII_DIGIT_RE = re.compile(r"^[0-9]+$")
_INTEGER_LITERAL_RE = re.compile(r"^[+-]?[0-9]+$")
_DECIMAL_LITERAL_RE = re.compile(r"^-?(?:[0-9]+(?:\.[0-9]+)?|\.[0-9]+)$")
_FLOAT_LITERAL_RE = re.compile(
    r"^[+-]?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)(?:[eE][+-]?[0-9]+)?$"
)
_DATE_RE = re.compile(r"^([0-9]{4})-([0-9]{2})-([0-9]{2})$")
_DATETIME_RE = re.compile(
    r"^([0-9]{4})-([0-9]{2})-([0-9]{2})T([0-9]{2}):([0-9]{2}):([0-9]{2})(?:\.([0-9]{1,6}))?$"
)
_TIMESTAMP_RE = re.compile(
    r"^([0-9]{4})-([0-9]{2})-([0-9]{2})T([0-9]{2}):([0-9]{2}):([0-9]{2})(?:\.([0-9]{1,6}))?Z$"
)
_TIME_RE = re.compile(r"^(-)?([0-9]{2,3}):([0-9]{2}):([0-9]{2})(?:\.([0-9]{1,6}))?$")
_BITS_HEX32_RE = re.compile(r"^[0-9a-f]{8}$")
_BITS_HEX64_RE = re.compile(r"^[0-9a-f]{16}$")
_ASCII_TEXT_RE = re.compile(r"^[\x00-\x7f]*$")

_ANOMALY_REQUIRED = frozenset({"declared_type", "raw_base64url", "raw_encoding", "reason"})


def normalize_logical_literal(
    declared_type: DeclaredType,
    source: LogicalLiteral,
) -> NormalizedScalar:
    if not isinstance(declared_type, DeclaredType):
        raise CanonicalEncodingError(
            CanonicalErrorCode.CANONICAL_TYPE_MISMATCH,
            "declared_type must be DeclaredType",
        )
    if not isinstance(source, (Utf8LogicalLiteral, RawLogicalLiteral)):
        raise CanonicalEncodingError(
            CanonicalErrorCode.CANONICAL_TYPE_MISMATCH,
            "source must be a LogicalLiteral",
        )
    typed = _normalize_to_typed(declared_type, source)
    encoded = encode_typed_scalar(declared_type, typed)
    return NormalizedScalar(
        typed_value=typed,
        payload=encoded.payload,
        scalar_frame=encoded.scalar_frame,
    )


def encode_typed_scalar(declared_type: DeclaredType, value: TypedScalar) -> EncodedScalar:
    if not isinstance(declared_type, DeclaredType):
        raise CanonicalEncodingError(
            CanonicalErrorCode.CANONICAL_TYPE_MISMATCH,
            "declared_type must be DeclaredType",
        )
    if type(declared_type.kind) is not DeclaredTypeKind:
        raise CanonicalEncodingError(
            CanonicalErrorCode.CANONICAL_TYPE_MISMATCH,
            "declared_type.kind must be DeclaredTypeKind",
        )
    _assert_kind_match(declared_type, value)
    _assert_runtime_scalar_types(value)
    payload = _encode_payload(declared_type, value)
    tag = _tag_for(declared_type.kind)
    frame = bytes([tag]) + encode_uleb128(len(payload)) + payload
    return EncodedScalar(payload=payload, scalar_frame=frame)


def _assert_kind_match(declared_type: DeclaredType, value: TypedScalar) -> None:
    if not hasattr(value, "kind") or value.kind != declared_type.kind.value:
        raise CanonicalEncodingError(
            CanonicalErrorCode.CANONICAL_TYPE_MISMATCH,
            "typed scalar kind does not match declared type",
        )


def _assert_runtime_scalar_types(value: TypedScalar) -> None:
    if isinstance(value, NullScalar):
        return
    if isinstance(value, BooleanScalar):
        if type(value.value) is not bool:
            raise CanonicalEncodingError(
                CanonicalErrorCode.CANONICAL_TYPE_MISMATCH,
                "boolean value must be bool",
            )
        return
    if isinstance(value, (SignedIntegerScalar, UnsignedIntegerScalar, DecimalScalar)):
        if type(value.decimal) is not str:
            raise CanonicalEncodingError(
                CanonicalErrorCode.CANONICAL_TYPE_MISMATCH,
                "decimal field must be str",
            )
        return
    if isinstance(value, (Float32Scalar, Float64Scalar)):
        if type(value.bits_hex) is not str:
            raise CanonicalEncodingError(
                CanonicalErrorCode.CANONICAL_TYPE_MISMATCH,
                "bits_hex must be str",
            )
        return
    if isinstance(
        value, (StringScalar, DateScalar, DateTimeScalar, TimestampScalar, TimeDurationScalar)
    ):
        if type(value.text) is not str:
            raise CanonicalEncodingError(
                CanonicalErrorCode.CANONICAL_TYPE_MISMATCH,
                "text field must be str",
            )
        return
    if isinstance(value, (BinaryScalar, BitScalar)):
        if type(value.raw_bytes) is not bytes:
            raise CanonicalEncodingError(
                CanonicalErrorCode.CANONICAL_TYPE_MISMATCH,
                "raw_bytes must be bytes",
            )
        return
    if isinstance(value, AnomalyScalar):
        if not isinstance(value.envelope, Mapping):
            raise CanonicalEncodingError(
                CanonicalErrorCode.CANONICAL_TYPE_MISMATCH,
                "anomaly envelope must be a mapping",
            )
        return
    raise CanonicalEncodingError(
        CanonicalErrorCode.CANONICAL_TYPE_MISMATCH,
        "unsupported typed scalar",
    )


def _tag_for(kind: DeclaredTypeKind) -> int:
    return {
        DeclaredTypeKind.NULL: TAG_NULL,
        DeclaredTypeKind.BOOLEAN: TAG_BOOLEAN,
        DeclaredTypeKind.SIGNED_INTEGER: TAG_SIGNED_INTEGER,
        DeclaredTypeKind.UNSIGNED_INTEGER: TAG_UNSIGNED_INTEGER,
        DeclaredTypeKind.DECIMAL: TAG_DECIMAL,
        DeclaredTypeKind.FLOAT32: TAG_FLOAT32,
        DeclaredTypeKind.FLOAT64: TAG_FLOAT64,
        DeclaredTypeKind.STRING: TAG_STRING,
        DeclaredTypeKind.BINARY: TAG_BINARY,
        DeclaredTypeKind.BIT: TAG_BINARY,
        DeclaredTypeKind.DATE: TAG_DATE,
        DeclaredTypeKind.DATETIME: TAG_DATETIME,
        DeclaredTypeKind.TIMESTAMP: TAG_TIMESTAMP,
        DeclaredTypeKind.TIME_DURATION: TAG_TIME_DURATION,
        DeclaredTypeKind.SOURCE_LITERAL_ANOMALY: TAG_ANOMALY,
    }[kind]


def _literal_text(source: LogicalLiteral) -> str:
    if isinstance(source, Utf8LogicalLiteral):
        if type(source.text) is not str:
            raise CanonicalEncodingError(
                CanonicalErrorCode.CANONICAL_TYPE_MISMATCH,
                "utf8 logical literal text must be str",
            )
        validate_unicode_string(source.text)
        return source.text
    if type(source.raw_bytes) is not bytes:
        raise CanonicalEncodingError(
            CanonicalErrorCode.CANONICAL_TYPE_MISMATCH,
            "raw logical literal must be bytes",
        )
    return decode_utf8(source.raw_bytes)


def _literal_bytes(source: LogicalLiteral) -> bytes:
    if isinstance(source, RawLogicalLiteral):
        if type(source.raw_bytes) is not bytes:
            raise CanonicalEncodingError(
                CanonicalErrorCode.CANONICAL_TYPE_MISMATCH,
                "raw logical literal must be bytes",
            )
        return source.raw_bytes
    if type(source.text) is not str:
        raise CanonicalEncodingError(
            CanonicalErrorCode.CANONICAL_TYPE_MISMATCH,
            "utf8 logical literal text must be str",
        )
    validate_unicode_string(source.text)
    return source.text.encode("utf-8")


def _max_integer_digits(bits: int) -> int:
    # ceil(bits * log10(2)) + leading-zero budget
    return math.ceil(bits * math.log10(2)) + _LEADING_ZERO_BUDGET


def _normalize_to_typed(declared_type: DeclaredType, source: LogicalLiteral) -> TypedScalar:
    kind = declared_type.kind
    if kind is DeclaredTypeKind.NULL:
        if isinstance(source, RawLogicalLiteral):
            if source.raw_bytes != b"":
                raise CanonicalEncodingError(
                    CanonicalErrorCode.CANONICAL_TYPE_MISMATCH,
                    "null raw literal must be empty",
                )
            return NullScalar()
        text = _literal_text(source)
        if text not in {"", "null"}:
            raise CanonicalEncodingError(
                CanonicalErrorCode.CANONICAL_TYPE_MISMATCH,
                "null logical literal must be empty or 'null'",
            )
        return NullScalar()
    if kind is DeclaredTypeKind.BOOLEAN:
        return BooleanScalar(value=_parse_boolean_literal(source))
    if kind is DeclaredTypeKind.SIGNED_INTEGER:
        assert declared_type.bits is not None
        return SignedIntegerScalar(
            decimal=_normalize_integer_literal(
                _literal_text(source), signed=True, bits=declared_type.bits
            )
        )
    if kind is DeclaredTypeKind.UNSIGNED_INTEGER:
        assert declared_type.bits is not None
        return UnsignedIntegerScalar(
            decimal=_normalize_integer_literal(
                _literal_text(source), signed=False, bits=declared_type.bits
            )
        )
    if kind is DeclaredTypeKind.DECIMAL:
        assert declared_type.precision is not None and declared_type.scale is not None
        return DecimalScalar(
            decimal=_normalize_decimal_literal(
                _literal_text(source),
                precision=declared_type.precision,
                scale=declared_type.scale,
            )
        )
    if kind is DeclaredTypeKind.FLOAT32:
        return Float32Scalar(bits_hex=_normalize_float_literal(_literal_text(source), width=32))
    if kind is DeclaredTypeKind.FLOAT64:
        return Float64Scalar(bits_hex=_normalize_float_literal(_literal_text(source), width=64))
    if kind is DeclaredTypeKind.STRING:
        text = _literal_text(source)
        validate_unicode_string(text)
        return StringScalar(text=text)
    if kind is DeclaredTypeKind.BINARY:
        return BinaryScalar(raw_bytes=_literal_bytes(source))
    if kind is DeclaredTypeKind.BIT:
        assert declared_type.bit_width is not None
        raw = _literal_bytes(source)
        _validate_bit_bytes(raw, declared_type.bit_width)
        return BitScalar(raw_bytes=raw)
    if kind is DeclaredTypeKind.DATE:
        return DateScalar(text=_canonicalize_date(_literal_text(source)))
    if kind is DeclaredTypeKind.DATETIME:
        return DateTimeScalar(text=_canonicalize_datetime(_literal_text(source)))
    if kind is DeclaredTypeKind.TIMESTAMP:
        return TimestampScalar(text=_canonicalize_timestamp(_literal_text(source)))
    if kind is DeclaredTypeKind.TIME_DURATION:
        return TimeDurationScalar(text=_canonicalize_time_duration(_literal_text(source)))
    raise CanonicalEncodingError(
        CanonicalErrorCode.CANONICAL_TYPE_MISMATCH,
        "anomaly scalars are not produced from logical literals",
    )


def _parse_boolean_literal(source: LogicalLiteral) -> bool:
    if isinstance(source, RawLogicalLiteral):
        if type(source.raw_bytes) is not bytes:
            raise CanonicalEncodingError(
                CanonicalErrorCode.CANONICAL_TYPE_MISMATCH,
                "boolean raw literal must be bytes",
            )
        if source.raw_bytes == b"\x00":
            return False
        if source.raw_bytes == b"\x01":
            return True
        raise CanonicalEncodingError(
            CanonicalErrorCode.CANONICAL_TYPE_MISMATCH,
            "boolean raw literal must be 0x00 or 0x01",
        )
    text = _literal_text(source)
    if text in {"true", "1"}:
        return True
    if text in {"false", "0"}:
        return False
    raise CanonicalEncodingError(
        CanonicalErrorCode.CANONICAL_TYPE_MISMATCH,
        "boolean logical literal must be true/false/0/1",
    )


def _normalize_integer_literal(text: str, *, signed: bool, bits: int) -> str:
    if _INTEGER_LITERAL_RE.fullmatch(text) is None:
        raise CanonicalEncodingError(
            CanonicalErrorCode.CANONICAL_TYPE_MISMATCH,
            "integer literal must be optional ASCII sign plus digits",
        )
    body = text
    sign = 1
    if body[0] == "+":
        body = body[1:]
    elif body[0] == "-":
        if not signed:
            raise CanonicalEncodingError(
                CanonicalErrorCode.CANONICAL_INTEGER_OUT_OF_RANGE,
                "unsigned integer rejects negative literal",
            )
        sign = -1
        body = body[1:]
    if body == "" or _ASCII_DIGIT_RE.fullmatch(body) is None:
        raise CanonicalEncodingError(
            CanonicalErrorCode.CANONICAL_TYPE_MISMATCH,
            "integer literal must be decimal digits",
        )
    if len(body) > _max_integer_digits(bits):
        raise CanonicalEncodingError(
            CanonicalErrorCode.CANONICAL_TYPE_MISMATCH,
            "integer literal exceeds lexical length budget",
        )
    try:
        value = sign * int(body, 10)
    except ValueError as exc:
        raise CanonicalEncodingError(
            CanonicalErrorCode.CANONICAL_TYPE_MISMATCH,
            "integer literal is not convertible",
        ) from exc
    if value == 0:
        return "0"
    lo, hi = _integer_bounds(signed=signed, bits=bits)
    if value < lo or value > hi:
        raise CanonicalEncodingError(
            CanonicalErrorCode.CANONICAL_INTEGER_OUT_OF_RANGE,
            "integer outside declared width",
        )
    return str(value)


def _integer_bounds(*, signed: bool, bits: int) -> tuple[int, int]:
    if signed:
        return -(1 << (bits - 1)), (1 << (bits - 1)) - 1
    return 0, (1 << bits) - 1


def _normalize_decimal_literal(text: str, *, precision: int, scale: int) -> str:
    if _DECIMAL_LITERAL_RE.fullmatch(text) is None:
        raise CanonicalEncodingError(
            CanonicalErrorCode.CANONICAL_DECIMAL_INVALID,
            "decimal literal rejects non-ASCII or invalid form",
        )
    negative = False
    body = text
    if body[0] == "-":
        negative = True
        body = body[1:]
    if "." in body:
        integer_part, frac_part = body.split(".", 1)
    else:
        integer_part, frac_part = body, ""
    if integer_part == "":
        integer_part = "0"
    if len(integer_part) + len(frac_part) > precision + _LEADING_ZERO_BUDGET:
        raise CanonicalEncodingError(
            CanonicalErrorCode.CANONICAL_DECIMAL_INVALID,
            "decimal literal exceeds lexical length budget",
        )
    integer_part = integer_part.lstrip("0") or "0"
    frac_part = frac_part.rstrip("0")
    if len(frac_part) > scale:
        raise CanonicalEncodingError(
            CanonicalErrorCode.CANONICAL_DECIMAL_INVALID,
            "decimal fractional digits exceed scale",
        )
    int_digits = 0 if integer_part == "0" else len(integer_part)
    if int_digits > precision - scale:
        raise CanonicalEncodingError(
            CanonicalErrorCode.CANONICAL_DECIMAL_INVALID,
            "decimal integer digits exceed precision-scale",
        )
    canonical = f"{integer_part}.{frac_part}" if frac_part else integer_part
    if canonical == "0":
        return "0"
    return f"-{canonical}" if negative else canonical


def _normalize_float_literal(text: str, *, width: int) -> str:
    if _FLOAT_LITERAL_RE.fullmatch(text) is None:
        raise CanonicalEncodingError(
            CanonicalErrorCode.CANONICAL_TYPE_MISMATCH,
            "float literal must match ASCII float grammar",
        )
    digit_count = sum(1 for ch in text if "0" <= ch <= "9")
    if digit_count > (38 if width == 32 else 309) + _LEADING_ZERO_BUDGET:
        raise CanonicalEncodingError(
            CanonicalErrorCode.CANONICAL_TYPE_MISMATCH,
            "float literal exceeds lexical length budget",
        )
    try:
        value = float(text)
    except ValueError as exc:
        raise CanonicalEncodingError(
            CanonicalErrorCode.CANONICAL_TYPE_MISMATCH,
            "float literal is not numeric",
        ) from exc
    return _float_bits_hex(value, width=width)


def _float_bits_hex(value: float, *, width: int) -> str:
    if not math.isfinite(value):
        raise CanonicalEncodingError(
            CanonicalErrorCode.CANONICAL_FLOAT_NON_FINITE,
            "float must be finite",
        )
    try:
        if width == 32:
            packed = struct.pack(">f", value)
            bits = struct.unpack(">I", packed)[0]
            rounded = struct.unpack(">f", packed)[0]
            if not math.isfinite(rounded):
                raise CanonicalEncodingError(
                    CanonicalErrorCode.CANONICAL_FLOAT_NON_FINITE,
                    "float32 packing produced non-finite",
                )
            if bits == 0x80000000:
                bits = 0
            return f"{bits:08x}"
        packed = struct.pack(">d", value)
        bits = struct.unpack(">Q", packed)[0]
        if bits == 0x8000000000000000:
            bits = 0
        return f"{bits:016x}"
    except OverflowError as exc:
        raise CanonicalEncodingError(
            CanonicalErrorCode.CANONICAL_FLOAT_NON_FINITE,
            "float packing overflowed to non-finite",
        ) from exc


def _encode_ascii_payload(text: str) -> bytes:
    if _ASCII_TEXT_RE.fullmatch(text) is None:
        raise CanonicalEncodingError(
            CanonicalErrorCode.CANONICAL_TYPE_MISMATCH,
            "payload text must be ASCII",
        )
    return text.encode("ascii")


def _encode_payload(declared_type: DeclaredType, value: TypedScalar) -> bytes:
    if isinstance(value, NullScalar):
        return b""
    if isinstance(value, BooleanScalar):
        return b"\x01" if value.value else b"\x00"
    if isinstance(value, SignedIntegerScalar):
        assert declared_type.bits is not None
        number = _require_canonical_int(value.decimal, signed=True, bits=declared_type.bits)
        return number.to_bytes(8, "big", signed=True)
    if isinstance(value, UnsignedIntegerScalar):
        assert declared_type.bits is not None
        number = _require_canonical_int(value.decimal, signed=False, bits=declared_type.bits)
        return number.to_bytes(8, "big", signed=False)
    if isinstance(value, DecimalScalar):
        assert declared_type.precision is not None and declared_type.scale is not None
        canonical = _normalize_decimal_literal(
            value.decimal,
            precision=declared_type.precision,
            scale=declared_type.scale,
        )
        if canonical != value.decimal:
            raise CanonicalEncodingError(
                CanonicalErrorCode.CANONICAL_DECIMAL_INVALID,
                "decimal typed value is not canonical",
            )
        return _encode_ascii_payload(canonical)
    if isinstance(value, Float32Scalar):
        return _encode_float_bits(value.bits_hex, width=32)
    if isinstance(value, Float64Scalar):
        return _encode_float_bits(value.bits_hex, width=64)
    if isinstance(value, StringScalar):
        validate_unicode_string(value.text)
        return value.text.encode("utf-8")
    if isinstance(value, BinaryScalar):
        return value.raw_bytes
    if isinstance(value, BitScalar):
        assert declared_type.bit_width is not None
        _validate_bit_bytes(value.raw_bytes, declared_type.bit_width)
        return value.raw_bytes
    if isinstance(value, DateScalar):
        return _encode_ascii_payload(
            _require_canonical_temporal(value.text, _canonicalize_date)
        )
    if isinstance(value, DateTimeScalar):
        return _encode_ascii_payload(
            _require_canonical_temporal(value.text, _canonicalize_datetime)
        )
    if isinstance(value, TimestampScalar):
        return _encode_ascii_payload(
            _require_canonical_temporal(value.text, _canonicalize_timestamp)
        )
    if isinstance(value, TimeDurationScalar):
        return _encode_ascii_payload(
            _require_canonical_temporal(value.text, _canonicalize_time_duration)
        )
    if isinstance(value, AnomalyScalar):
        return _encode_anomaly_envelope(value.envelope)
    raise CanonicalEncodingError(
        CanonicalErrorCode.CANONICAL_TYPE_MISMATCH,
        "unsupported typed scalar",
    )


def _require_canonical_int(decimal: str, *, signed: bool, bits: int) -> int:
    normalized = _normalize_integer_literal(decimal, signed=signed, bits=bits)
    if normalized != decimal:
        raise CanonicalEncodingError(
            CanonicalErrorCode.CANONICAL_TYPE_MISMATCH,
            "integer typed value must be canonical decimal",
        )
    return int(decimal, 10)


def _require_canonical_temporal(text: str, canon: Callable[[str], str]) -> str:
    canonical = canon(text)
    if canonical != text:
        raise CanonicalEncodingError(
            CanonicalErrorCode.CANONICAL_TEMPORAL_INVALID,
            "temporal typed value is not canonical",
        )
    return text


def _encode_float_bits(bits_hex: str, *, width: int) -> bytes:
    pattern = _BITS_HEX32_RE if width == 32 else _BITS_HEX64_RE
    if pattern.fullmatch(bits_hex) is None:
        raise CanonicalEncodingError(
            CanonicalErrorCode.CANONICAL_TYPE_MISMATCH,
            "float bits_hex must be lowercase hex of declared width",
        )
    bits = int(bits_hex, 16)
    try:
        if width == 32:
            value = struct.unpack(">f", struct.pack(">I", bits))[0]
            if not math.isfinite(value):
                raise CanonicalEncodingError(
                    CanonicalErrorCode.CANONICAL_FLOAT_NON_FINITE,
                    "float32 bits are non-finite",
                )
            if bits == 0x80000000:
                bits = 0
            return struct.pack(">I", bits)
        value = struct.unpack(">d", struct.pack(">Q", bits))[0]
        if not math.isfinite(value):
            raise CanonicalEncodingError(
                CanonicalErrorCode.CANONICAL_FLOAT_NON_FINITE,
                "float64 bits are non-finite",
            )
        if bits == 0x8000000000000000:
            bits = 0
        return struct.pack(">Q", bits)
    except OverflowError as exc:
        raise CanonicalEncodingError(
            CanonicalErrorCode.CANONICAL_FLOAT_NON_FINITE,
            "float packing overflowed to non-finite",
        ) from exc


def _validate_bit_bytes(raw: bytes, bit_width: int) -> None:
    expected_len = (bit_width + 7) // 8
    if len(raw) != expected_len:
        raise CanonicalEncodingError(
            CanonicalErrorCode.CANONICAL_TYPE_MISMATCH,
            "BIT payload length must be ceil(bit_width/8)",
        )
    if int.from_bytes(raw, "big") >> bit_width:
        raise CanonicalEncodingError(
            CanonicalErrorCode.CANONICAL_TYPE_MISMATCH,
            "BIT unused high bits must be zero",
        )


def _is_leap_year(year: int) -> bool:
    return year % 4 == 0 and (year % 100 != 0 or year % 400 == 0)


def _days_in_month(year: int, month: int) -> int:
    if month in {1, 3, 5, 7, 8, 10, 12}:
        return 31
    if month in {4, 6, 9, 11}:
        return 30
    if month == 2:
        return 29 if _is_leap_year(year) else 28
    return 0


def _validate_civil_date(year: int, month: int, day: int) -> None:
    if year < 1 or month < 1 or month > 12 or day < 1:
        raise CanonicalEncodingError(
            CanonicalErrorCode.CANONICAL_TEMPORAL_INVALID,
            "civil date out of range",
        )
    if day > _days_in_month(year, month):
        raise CanonicalEncodingError(
            CanonicalErrorCode.CANONICAL_TEMPORAL_INVALID,
            "civil date day invalid for month",
        )


def _validate_clock(hour: int, minute: int, second: int) -> None:
    if hour > 23 or minute > 59 or second > 59:
        raise CanonicalEncodingError(
            CanonicalErrorCode.CANONICAL_TEMPORAL_INVALID,
            "civil time out of range",
        )


def _format_fraction(frac: str | None) -> str:
    if frac is None:
        return ""
    trimmed = frac.rstrip("0")
    return f".{trimmed}" if trimmed else ""


def _canonicalize_date(text: str) -> str:
    match = _DATE_RE.fullmatch(text)
    if match is None:
        raise CanonicalEncodingError(
            CanonicalErrorCode.CANONICAL_TEMPORAL_INVALID,
            "date must be YYYY-MM-DD",
        )
    year, month, day = (int(match.group(i)) for i in range(1, 4))
    _validate_civil_date(year, month, day)
    return f"{year:04d}-{month:02d}-{day:02d}"


def _canonicalize_datetime(text: str) -> str:
    match = _DATETIME_RE.fullmatch(text)
    if match is None:
        raise CanonicalEncodingError(
            CanonicalErrorCode.CANONICAL_TEMPORAL_INVALID,
            "datetime must be YYYY-MM-DDTHH:MM:SS[.fraction]",
        )
    year, month, day, hour, minute, second = (int(match.group(i)) for i in range(1, 7))
    _validate_civil_date(year, month, day)
    _validate_clock(hour, minute, second)
    fraction = _format_fraction(match.group(7))
    return f"{year:04d}-{month:02d}-{day:02d}T{hour:02d}:{minute:02d}:{second:02d}{fraction}"


def _canonicalize_timestamp(text: str) -> str:
    match = _TIMESTAMP_RE.fullmatch(text)
    if match is None:
        raise CanonicalEncodingError(
            CanonicalErrorCode.CANONICAL_TEMPORAL_INVALID,
            "timestamp must be YYYY-MM-DDTHH:MM:SS[.fraction]Z",
        )
    year, month, day, hour, minute, second = (int(match.group(i)) for i in range(1, 7))
    _validate_civil_date(year, month, day)
    _validate_clock(hour, minute, second)
    fraction = _format_fraction(match.group(7))
    return (
        f"{year:04d}-{month:02d}-{day:02d}T{hour:02d}:{minute:02d}:{second:02d}{fraction}Z"
    )


def _canonicalize_time_duration(text: str) -> str:
    match = _TIME_RE.fullmatch(text)
    if match is None:
        raise CanonicalEncodingError(
            CanonicalErrorCode.CANONICAL_TEMPORAL_INVALID,
            "time duration lexical form invalid",
        )
    negative = match.group(1) is not None
    hour_token = match.group(2)
    hour = int(hour_token)
    minute = int(match.group(3))
    second = int(match.group(4))
    if minute > 59 or second > 59:
        raise CanonicalEncodingError(
            CanonicalErrorCode.CANONICAL_TEMPORAL_INVALID,
            "time duration minute/second out of range",
        )
    if hour > 838:
        raise CanonicalEncodingError(
            CanonicalErrorCode.CANONICAL_TIME_OUT_OF_RANGE,
            "time duration exceeds 838 hours",
        )
    if hour <= 99 and len(hour_token) != 2:
        raise CanonicalEncodingError(
            CanonicalErrorCode.CANONICAL_TEMPORAL_INVALID,
            "time duration 0-99 hours must use two digits",
        )
    if hour >= 100 and len(hour_token) != 3:
        raise CanonicalEncodingError(
            CanonicalErrorCode.CANONICAL_TEMPORAL_INVALID,
            "time duration 100-838 hours must use three digits",
        )
    fraction = _format_fraction(match.group(5))
    if hour == 0 and minute == 0 and second == 0 and fraction == "":
        return "00:00:00"
    hour_text = f"{hour:02d}" if hour <= 99 else f"{hour:03d}"
    body = f"{hour_text}:{minute:02d}:{second:02d}{fraction}"
    return f"-{body}" if negative else body


def _encode_anomaly_envelope(envelope: Mapping[str, Any]) -> bytes:
    if not isinstance(envelope, Mapping):
        raise CanonicalEncodingError(
            CanonicalErrorCode.CANONICAL_ANOMALY_INVALID,
            "anomaly envelope must be an object",
        )
    _assert_json_compatible_tree(envelope)
    if set(envelope) != _ANOMALY_REQUIRED:
        raise CanonicalEncodingError(
            CanonicalErrorCode.CANONICAL_ANOMALY_INVALID,
            "anomaly envelope must contain exactly the four v1 fields",
        )
    materialised = {
        "declared_type": envelope["declared_type"],
        "raw_base64url": envelope["raw_base64url"],
        "raw_encoding": envelope["raw_encoding"],
        "reason": envelope["reason"],
    }
    raw_b64 = materialised["raw_base64url"]
    raw_encoding = materialised["raw_encoding"]
    reason = materialised["reason"]
    declared_type = materialised["declared_type"]
    if type(raw_b64) is not str or type(raw_encoding) is not str or type(reason) is not str:
        raise CanonicalEncodingError(
            CanonicalErrorCode.CANONICAL_ANOMALY_INVALID,
            "anomaly raw_base64url/raw_encoding/reason must be strings",
        )
    if raw_encoding == "" or reason == "":
        raise CanonicalEncodingError(
            CanonicalErrorCode.CANONICAL_ANOMALY_INVALID,
            "anomaly raw_encoding/reason must be non-empty",
        )
    _parse_declared_type_json(declared_type)
    decode_base64url_strict(raw_b64)
    validate_unicode_string(raw_encoding)
    validate_unicode_string(reason)
    return canonicalize_json_value(materialised)


def _assert_json_compatible_tree(value: Any, *, active_containers: set[int] | None = None) -> None:
    """Reject non-JSON host values anywhere in the anomaly envelope tree."""
    if value is None or type(value) is bool or type(value) is str:
        if type(value) is str:
            validate_unicode_string(value)
        return
    if type(value) is int:
        return
    if type(value) is float:
        if not math.isfinite(value):
            raise CanonicalEncodingError(
                CanonicalErrorCode.CANONICAL_ANOMALY_INVALID,
                "anomaly envelope numbers must be finite",
            )
        return
    if type(value) is list or isinstance(value, Mapping):
        active = active_containers if active_containers is not None else set()
        identity = id(value)
        if identity in active:
            raise CanonicalEncodingError(
                CanonicalErrorCode.CANONICAL_ANOMALY_INVALID,
                "anomaly envelope must not contain reference cycles",
            )
        active.add(identity)
        try:
            if type(value) is list:
                for item in value:
                    _assert_json_compatible_tree(item, active_containers=active)
                return
            mapping = cast(Mapping[Any, Any], value)
            for key, item in mapping.items():
                if type(key) is not str:
                    raise CanonicalEncodingError(
                        CanonicalErrorCode.CANONICAL_ANOMALY_INVALID,
                        "anomaly envelope object keys must be strings",
                    )
                validate_unicode_string(key)
                _assert_json_compatible_tree(item, active_containers=active)
            return
        finally:
            active.remove(identity)
    raise CanonicalEncodingError(
        CanonicalErrorCode.CANONICAL_ANOMALY_INVALID,
        "anomaly envelope contains non-JSON-compatible value",
    )


def _parse_declared_type_json(value: Any) -> DeclaredType:
    if type(value) is not dict:
        raise CanonicalEncodingError(
            CanonicalErrorCode.CANONICAL_ANOMALY_INVALID,
            "anomaly declared_type must be a DeclaredType object",
        )
    kind_raw = value.get("kind")
    if type(kind_raw) is not str:
        raise CanonicalEncodingError(
            CanonicalErrorCode.CANONICAL_ANOMALY_INVALID,
            "anomaly declared_type.kind must be a string",
        )
    try:
        kind = DeclaredTypeKind(kind_raw)
    except ValueError as exc:
        raise CanonicalEncodingError(
            CanonicalErrorCode.CANONICAL_ANOMALY_INVALID,
            "anomaly declared_type.kind is not a known kind",
        ) from exc
    allowed_keys = {"kind", "bits", "precision", "scale", "bit_width"}
    if set(value) - allowed_keys:
        raise CanonicalEncodingError(
            CanonicalErrorCode.CANONICAL_ANOMALY_INVALID,
            "anomaly declared_type has unknown fields",
        )
    try:
        return DeclaredType(
            kind=kind,
            bits=value.get("bits"),
            precision=value.get("precision"),
            scale=value.get("scale"),
            bit_width=value.get("bit_width"),
        )
    except ValueError as exc:
        raise CanonicalEncodingError(
            CanonicalErrorCode.CANONICAL_ANOMALY_INVALID,
            "anomaly declared_type is invalid",
        ) from exc
