"""Strict JSON loader rejecting duplicate keys and non-JSON constants."""

from __future__ import annotations

import json
import math
from typing import Any, NoReturn

from gateway_conformance.errors import ConformanceValidationError

_IJSON_MIN = -(2**53) + 1
_IJSON_MAX = (2**53) - 1


class StrictJSONValidationError(ConformanceValidationError):
    """JSON document violates the strict I-JSON subset."""


def _validate_json_number(value: Any) -> Any:
    if isinstance(value, bool) or value is None:
        return value
    if isinstance(value, int):
        if value < _IJSON_MIN or value > _IJSON_MAX:
            raise StrictJSONValidationError("integer outside I-JSON safe range")
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise StrictJSONValidationError("non-finite floats are not allowed")
        if value < _IJSON_MIN or value > _IJSON_MAX:
            raise StrictJSONValidationError("float outside I-JSON safe range")
        if value == int(value) and abs(value) <= _IJSON_MAX:
            return int(value)
        return value
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        return [_validate_json_number(item) for item in value]
    if isinstance(value, dict):
        return {key: _validate_json_number(item) for key, item in value.items()}
    raise StrictJSONValidationError(f"unsupported JSON value type: {type(value).__name__}")


def loads_strict_json(text: str) -> dict[str, Any]:
    def object_pairs_hook(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        out: dict[str, Any] = {}
        for key, value in pairs:
            if key in out:
                raise StrictJSONValidationError(f"duplicate JSON member {key!r}")
            out[key] = value
        return out

    def parse_constant(name: str) -> NoReturn:
        raise StrictJSONValidationError(f"non-JSON constant {name!r} is not allowed")

    try:
        value = json.loads(
            text,
            object_pairs_hook=object_pairs_hook,
            parse_constant=parse_constant,
        )
    except StrictJSONValidationError:
        raise
    except json.JSONDecodeError as exc:
        raise StrictJSONValidationError(f"invalid JSON: {exc}") from exc
    if not isinstance(value, dict):
        raise StrictJSONValidationError("JSON document root must be an object")
    validated = _validate_json_number(value)
    if not isinstance(validated, dict):
        raise StrictJSONValidationError("JSON document root must be an object")
    return validated


def loads_strict_json_bytes(raw: bytes) -> dict[str, Any]:
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise StrictJSONValidationError("JSON document is not valid UTF-8") from exc
    return loads_strict_json(text)
