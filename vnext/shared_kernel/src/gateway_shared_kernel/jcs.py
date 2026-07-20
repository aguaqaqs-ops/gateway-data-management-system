"""Strict RFC 8785 JCS canonicalization with I-JSON and Unicode gates."""

from __future__ import annotations

import json
import math
from typing import Any

import rfc8785

from gateway_shared_kernel.errors import CanonicalEncodingError, CanonicalErrorCode
from gateway_shared_kernel.unicode import decode_utf8, validate_unicode_string

_IJSON_MIN_SAFE_INTEGER = -(2**53) + 1
_IJSON_MAX_SAFE_INTEGER = (2**53) - 1
# I-JSON safe integers use at most 16 ASCII digits (excluding optional '-').
_IJSON_MAX_INTEGER_DIGITS = 16


def canonicalize_jcs(json_utf8: bytes) -> bytes:
    """Canonicalize a complete JSON document from raw UTF-8 bytes.

    Validation stages (explicit, library-message-independent):
    1. strict UTF-8 decode
    2. JSON parse with duplicate-member detection and non-finite rejection
    3. Unicode scalar / noncharacter checks on all strings and object keys
    4. I-JSON number range checks
    5. RFC 8785 serialization via ``rfc8785``
    """
    text = decode_utf8(json_utf8)
    value = _parse_json_document(text)
    return canonicalize_json_value(value)


def canonicalize_json_value(value: Any) -> bytes:
    """Canonicalize an already-parsed JSON-compatible value."""
    _validate_unicode_tree(value)
    _validate_ijson_numbers(value)
    return _serialize_jcs(value)


def _parse_json_document(text: str) -> Any:
    try:
        return json.loads(
            text,
            object_pairs_hook=_object_pairs_hook,
            parse_int=_parse_int,
            parse_constant=_parse_constant,
        )
    except CanonicalEncodingError:
        raise
    except json.JSONDecodeError as exc:
        raise CanonicalEncodingError(
            CanonicalErrorCode.CANONICAL_JCS_SYNTAX_INVALID,
            "input is not a valid JSON document",
        ) from exc
    except ValueError as exc:
        # Host integer conversion must not escape; map after our parse_int guard.
        raise CanonicalEncodingError(
            CanonicalErrorCode.CANONICAL_JCS_NUMBER_OUT_OF_RANGE,
            "JSON integer outside I-JSON safe range",
        ) from exc


def _parse_int(lexeme: str) -> int:
    """Parse a JSON integer lexeme without host overflow surprises."""
    if type(lexeme) is not str or lexeme == "":
        raise CanonicalEncodingError(
            CanonicalErrorCode.CANONICAL_JCS_SYNTAX_INVALID,
            "JSON integer lexeme invalid",
        )
    digits = lexeme[1:] if lexeme[0] == "-" else lexeme
    if digits == "" or any(ch < "0" or ch > "9" for ch in digits):
        raise CanonicalEncodingError(
            CanonicalErrorCode.CANONICAL_JCS_SYNTAX_INVALID,
            "JSON integer lexeme invalid",
        )
    if len(digits) > _IJSON_MAX_INTEGER_DIGITS:
        raise CanonicalEncodingError(
            CanonicalErrorCode.CANONICAL_JCS_NUMBER_OUT_OF_RANGE,
            "JSON integer outside I-JSON safe range",
        )
    try:
        value = int(lexeme, 10)
    except ValueError as exc:
        raise CanonicalEncodingError(
            CanonicalErrorCode.CANONICAL_JCS_NUMBER_OUT_OF_RANGE,
            "JSON integer outside I-JSON safe range",
        ) from exc
    if value < _IJSON_MIN_SAFE_INTEGER or value > _IJSON_MAX_SAFE_INTEGER:
        raise CanonicalEncodingError(
            CanonicalErrorCode.CANONICAL_JCS_NUMBER_OUT_OF_RANGE,
            "JSON integer outside I-JSON safe range",
        )
    return value


def _object_pairs_hook(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    seen: set[str] = set()
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in seen:
            raise CanonicalEncodingError(
                CanonicalErrorCode.CANONICAL_JCS_DUPLICATE_MEMBER,
                "duplicate JSON member name",
            )
        seen.add(key)
        result[key] = value
    return result


def _parse_constant(name: str) -> Any:
    if name in {"NaN", "Infinity", "-Infinity"}:
        raise CanonicalEncodingError(
            CanonicalErrorCode.CANONICAL_JCS_NON_FINITE_NUMBER,
            "JSON number must be finite",
        )
    raise CanonicalEncodingError(
        CanonicalErrorCode.CANONICAL_INVALID_UNICODE,
        "unsupported JSON constant",
    )


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
            validate_unicode_string(key)
            _validate_unicode_tree(item)


def _validate_ijson_numbers(value: Any) -> None:
    if isinstance(value, bool):
        return
    if isinstance(value, int):
        if value < _IJSON_MIN_SAFE_INTEGER or value > _IJSON_MAX_SAFE_INTEGER:
            raise CanonicalEncodingError(
                CanonicalErrorCode.CANONICAL_JCS_NUMBER_OUT_OF_RANGE,
                "JSON integer outside I-JSON safe range",
            )
        return
    if isinstance(value, float):
        if not math.isfinite(value):
            raise CanonicalEncodingError(
                CanonicalErrorCode.CANONICAL_JCS_NON_FINITE_NUMBER,
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


def _serialize_jcs(value: Any) -> bytes:
    try:
        return rfc8785.dumps(value)
    except rfc8785.IntegerDomainError as exc:
        raise CanonicalEncodingError(
            CanonicalErrorCode.CANONICAL_JCS_NUMBER_OUT_OF_RANGE,
            "JSON integer outside JCS domain",
        ) from exc
    except rfc8785.FloatDomainError as exc:
        raise CanonicalEncodingError(
            CanonicalErrorCode.CANONICAL_JCS_NON_FINITE_NUMBER,
            "JSON number must be finite",
        ) from exc
    except rfc8785.CanonicalizationError as exc:
        raise CanonicalEncodingError(
            CanonicalErrorCode.CANONICAL_INVALID_UNICODE,
            "JCS serialization rejected input",
        ) from exc
