"""RFC 8785 JCS serialization without external runtime dependencies."""

from __future__ import annotations

import math
import re
from io import BytesIO
from typing import Any

from gateway_repository_contracts._unicode import validate_unicode_string
from gateway_repository_contracts.errors import RepositoryContractError, RepositoryContractErrorCode

_IJSON_MIN_SAFE_INTEGER = -(2**53) + 1
_IJSON_MAX_SAFE_INTEGER = (2**53) - 1
_IJSON_MAX_INTEGER_DIGITS = 16
_JSON_WHITESPACE = frozenset({0x20, 0x09, 0x0A, 0x0D})

# Adapted from Andrew Rundgren's RFC 8785 reference implementation (Apache-2.0).
_ESCAPE = re.compile(r'[\x00-\x1f\\"\b\f\n\r\t]')
_ESCAPE_DCT = {
    "\\": "\\\\",
    '"': '\\"',
    "\b": "\\b",
    "\f": "\\f",
    "\n": "\\n",
    "\r": "\\r",
    "\t": "\\t",
}
for _codepoint in range(0x20):
    _ESCAPE_DCT.setdefault(chr(_codepoint), f"\\u{_codepoint:04x}")


class _BoundedBytesIO(BytesIO):
    def __init__(self, max_bytes: int) -> None:
        super().__init__()
        self._max_bytes = max_bytes

    def write(self, data: bytes) -> int:  # type: ignore[override]
        if self.tell() + len(data) > self._max_bytes:
            raise RepositoryContractError(
                RepositoryContractErrorCode.WIRE_PAYLOAD_TOO_LARGE,
                "JCS payload exceeds maximum size",
            )
        return super().write(data)


def encode_jcs_bytes(value: object, *, max_bytes: int | None = None) -> bytes:
    """Canonicalize a JSON-compatible value tree to RFC 8785 UTF-8 bytes."""
    _validate_unicode_tree(value)
    _validate_ijson_numbers(value)
    if max_bytes is None:
        sink = BytesIO()
        _dump_jcs(value, sink)
        return sink.getvalue()
    sink = _BoundedBytesIO(max_bytes)
    _dump_jcs(value, sink)
    return sink.getvalue()


def canonicalize_jcs_bytes(json_utf8: bytes) -> bytes:
    """Parse and canonicalize a complete JSON document from raw UTF-8 bytes."""
    from gateway_repository_contracts._json import parse_json_document

    try:
        text = json_utf8.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise RepositoryContractError(
            RepositoryContractErrorCode.WIRE_INVALID_UTF8,
            "invalid UTF-8",
        ) from exc
    stripped = _strip_json_whitespace(text)
    return encode_jcs_bytes(parse_json_document(stripped.encode("utf-8")))


def _strip_json_whitespace(text: str) -> str:
    start = 0
    end = len(text)
    while start < end and ord(text[start]) in _JSON_WHITESPACE:
        start += 1
    while end > start and ord(text[end - 1]) in _JSON_WHITESPACE:
        end -= 1
    return text[start:end]


def _utf16_sort_key(text: str) -> tuple[int, ...]:
    encoded = text.encode("utf-16-be")
    return tuple(encoded[index] << 8 | encoded[index + 1] for index in range(0, len(encoded), 2))


def _validate_ijson_int(value: int) -> None:
    if value < _IJSON_MIN_SAFE_INTEGER or value > _IJSON_MAX_SAFE_INTEGER:
        raise RepositoryContractError(
            RepositoryContractErrorCode.JSON_INCOMPATIBLE_VALUE,
            "JSON integer outside I-JSON safe range",
        )


def _validate_ijson_numbers(value: Any) -> None:
    if isinstance(value, bool):
        return
    if type(value) is int:
        _validate_ijson_int(value)
        return
    if type(value) is float:
        if not math.isfinite(value):
            raise RepositoryContractError(
                RepositoryContractErrorCode.JSON_INCOMPATIBLE_VALUE,
                "JSON number must be finite",
            )
        return
    if isinstance(value, list):
        for item in value:
            _validate_ijson_numbers(item)
        return
    if isinstance(value, dict):
        for item in value.values():
            _validate_ijson_numbers(item)


def _validate_unicode_tree(value: Any) -> None:
    if isinstance(value, str):
        validate_unicode_string(value)
        return
    if isinstance(value, list):
        for item in value:
            _validate_unicode_tree(item)
        return
    if isinstance(value, dict):
        for key, item in value.items():
            if type(key) is not str:
                raise RepositoryContractError(
                    RepositoryContractErrorCode.JSON_INCOMPATIBLE_VALUE,
                    "object key must be string",
                )
            validate_unicode_string(key)
            _validate_unicode_tree(item)


def _serialize_str_to_sink(text: str, sink: BytesIO) -> None:
    def _replace(match: re.Match[str]) -> str:
        return _ESCAPE_DCT[match.group(0)]

    sink.write(b'"')
    try:
        sink.write(_ESCAPE.sub(_replace, text).encode("utf-8"))
    except UnicodeEncodeError as exc:
        raise RepositoryContractError(
            RepositoryContractErrorCode.WIRE_INVALID_UTF8,
            "invalid UTF-8 in string",
        ) from exc
    sink.write(b'"')


def _serialize_float_to_sink(value: float, sink: BytesIO) -> None:
    if math.isnan(value) or math.isinf(value):
        raise RepositoryContractError(
            RepositoryContractErrorCode.JSON_INCOMPATIBLE_VALUE,
            "JSON number must be finite",
        )
    if value == 0.0:
        sink.write(b"0")
        return
    if value < 0:
        sink.write(b"-")
        _serialize_float_to_sink(-value, sink)
        return

    stringified = str(value)
    exponent_str = ""
    exponent_value = 0
    exponent_index = stringified.find("e")
    if exponent_index > 0:
        exponent_str = stringified[exponent_index:]
        if len(exponent_str) > 2 and exponent_str[2:3] == "0":
            exponent_str = exponent_str[:2] + exponent_str[3:]
        stringified = stringified[:exponent_index]
        exponent_value = int(exponent_str[1:])

    first = stringified
    dot = ""
    last = ""
    dot_index = stringified.find(".")
    if dot_index > 0:
        dot = "."
        first = stringified[:dot_index]
        last = stringified[dot_index + 1 :]

    if last == "0":
        dot = ""
        last = ""

    if exponent_value > 0 and exponent_value < 21:
        first += last
        last = ""
        dot = ""
        exponent_str = ""
        q = exponent_value - len(first)
        while q >= 0:
            q -= 1
            first += "0"
    elif exponent_value < 0 and exponent_value > -7:
        last = first + last
        first = "0"
        dot = "."
        exponent_str = ""
        padding = exponent_value
        while padding < -1:
            padding += 1
            last = "0" + last

    sink.write(f"{first}{dot}{last}{exponent_str}".encode("ascii"))


def _dump_jcs(value: Any, sink: BytesIO) -> None:
    if value is None:
        sink.write(b"null")
        return
    if type(value) is bool:
        sink.write(b"true" if value else b"false")
        return
    if type(value) is int:
        _validate_ijson_int(value)
        sink.write(str(value).encode("ascii"))
        return
    if type(value) is float:
        _serialize_float_to_sink(value, sink)
        return
    if isinstance(value, str):
        validate_unicode_string(value)
        _serialize_str_to_sink(value, sink)
        return
    if isinstance(value, list):
        sink.write(b"[")
        for index, item in enumerate(value):
            if index > 0:
                sink.write(b",")
            _dump_jcs(item, sink)
        sink.write(b"]")
        return
    if isinstance(value, dict):
        sink.write(b"{")
        keys = sorted(value.keys(), key=_utf16_sort_key)
        for index, key in enumerate(keys):
            if index > 0:
                sink.write(b",")
            _serialize_str_to_sink(key, sink)
            sink.write(b":")
            _dump_jcs(value[key], sink)
        sink.write(b"}")
        return
    raise RepositoryContractError(
        RepositoryContractErrorCode.JSON_INCOMPATIBLE_VALUE,
        "value is not JSON-compatible",
    )


def parse_json_int(lexeme: str) -> int:
    if type(lexeme) is not str or lexeme == "":
        raise RepositoryContractError(
            RepositoryContractErrorCode.WIRE_JSON_SYNTAX_INVALID,
            "JSON integer lexeme invalid",
        )
    digits = lexeme[1:] if lexeme[0] == "-" else lexeme
    if digits == "" or any(ch < "0" or ch > "9" for ch in digits):
        raise RepositoryContractError(
            RepositoryContractErrorCode.WIRE_JSON_SYNTAX_INVALID,
            "JSON integer lexeme invalid",
        )
    if len(digits) > _IJSON_MAX_INTEGER_DIGITS:
        raise RepositoryContractError(
            RepositoryContractErrorCode.JSON_INCOMPATIBLE_VALUE,
            "JSON integer outside I-JSON safe range",
        )
    try:
        parsed = int(lexeme, 10)
    except ValueError as exc:
        raise RepositoryContractError(
            RepositoryContractErrorCode.JSON_INCOMPATIBLE_VALUE,
            "JSON integer outside I-JSON safe range",
        ) from exc
    _validate_ijson_int(parsed)
    return parsed


def parse_json_constant(name: str) -> Any:
    if name in {"NaN", "Infinity", "-Infinity"}:
        raise RepositoryContractError(
            RepositoryContractErrorCode.JSON_INCOMPATIBLE_VALUE,
            "JSON number must be finite",
        )
    raise RepositoryContractError(
        RepositoryContractErrorCode.JSON_INCOMPATIBLE_VALUE,
        "unsupported JSON constant",
    )
