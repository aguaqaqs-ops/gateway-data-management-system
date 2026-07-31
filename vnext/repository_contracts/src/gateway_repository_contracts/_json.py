"""Internal JSON freeze, parse, and wire encode helpers."""

from __future__ import annotations

import json
import math
from collections.abc import Mapping
from types import MappingProxyType
from typing import Any, TypeAlias

from gateway_repository_contracts._jcs import parse_json_constant, parse_json_int
from gateway_repository_contracts._unicode import validate_unicode_string
from gateway_repository_contracts.errors import RepositoryContractError, RepositoryContractErrorCode

JSONValue: TypeAlias = (
    None
    | bool
    | int
    | float
    | str
    | tuple["JSONValue", ...]
    | list["JSONValue"]
    | Mapping[str, "JSONValue"]
)

CONTROL_JSON_MAX_BYTES = 1_048_576
JSON_MAX_DEPTH = 64


def freeze_json_value(value: object) -> JSONValue:
    """Return a defensive deep-frozen JSON-compatible value tree."""
    try:
        return _freeze_json_value(value, active=set(), depth=0)
    except RecursionError as exc:
        raise RepositoryContractError(
            RepositoryContractErrorCode.JSON_NESTING_TOO_DEEP,
            "JSON nesting too deep",
        ) from exc


def _freeze_json_value(value: object, *, active: set[int], depth: int) -> JSONValue:
    if depth > JSON_MAX_DEPTH:
        raise RepositoryContractError(
            RepositoryContractErrorCode.JSON_NESTING_TOO_DEEP,
            "JSON nesting too deep",
        )
    if value is None or type(value) is bool:
        return value
    if type(value) is str:
        validate_unicode_string(value)
        return value
    if type(value) is int:
        return value
    if type(value) is float:
        if not math.isfinite(value):
            raise RepositoryContractError(
                RepositoryContractErrorCode.JSON_INCOMPATIBLE_VALUE,
                "non-finite number",
            )
        return value
    if type(value) is list or type(value) is tuple:
        identity = id(value)
        if identity in active:
            raise RepositoryContractError(
                RepositoryContractErrorCode.JSON_CYCLE_DETECTED,
                "reference cycle",
            )
        active.add(identity)
        try:
            return tuple(_freeze_json_value(item, active=active, depth=depth + 1) for item in value)
        finally:
            active.remove(identity)
    if type(value) is dict:
        identity = id(value)
        if identity in active:
            raise RepositoryContractError(
                RepositoryContractErrorCode.JSON_CYCLE_DETECTED,
                "reference cycle",
            )
        active.add(identity)
        try:
            frozen = {
                key: _freeze_json_value(item, active=active, depth=depth + 1)
                for key, item in value.items()
                if type(key) is str
            }
            if len(frozen) != len(value):
                raise RepositoryContractError(
                    RepositoryContractErrorCode.JSON_INCOMPATIBLE_VALUE,
                    "object key must be string",
                )
            for key in frozen:
                validate_unicode_string(key)
            return MappingProxyType(frozen)
        finally:
            active.remove(identity)
    if isinstance(value, Mapping):
        identity = id(value)
        if identity in active:
            raise RepositoryContractError(
                RepositoryContractErrorCode.JSON_CYCLE_DETECTED,
                "reference cycle",
            )
        active.add(identity)
        try:
            frozen = {
                str(key): _freeze_json_value(item, active=active, depth=depth + 1)
                for key, item in value.items()
                if type(key) is str
            }
            if len(frozen) != len(value):
                raise RepositoryContractError(
                    RepositoryContractErrorCode.JSON_INCOMPATIBLE_VALUE,
                    "object key must be string",
                )
            for key in frozen:
                validate_unicode_string(key)
            return MappingProxyType(frozen)
        finally:
            active.remove(identity)
    raise RepositoryContractError(
        RepositoryContractErrorCode.JSON_INCOMPATIBLE_VALUE,
        "value is not JSON-compatible",
    )


def materialize_json_value(value: JSONValue) -> JSONValue:
    """Convert frozen JSON values into plain JSON-serializable Python objects."""
    if value is None or type(value) is bool or type(value) is str:
        return value
    if type(value) is int or type(value) is float:
        return value
    if type(value) is tuple:
        return [materialize_json_value(item) for item in value]
    if type(value) is list:
        return [materialize_json_value(item) for item in value]
    if isinstance(value, Mapping):
        return {key: materialize_json_value(item) for key, item in value.items()}
    raise RepositoryContractError(
        RepositoryContractErrorCode.JSON_INCOMPATIBLE_VALUE,
        "value is not JSON-compatible",
    )


def encode_deterministic_json(value: JSONValue) -> bytes:
    """Encode a JSON value to deterministic sorted UTF-8 bytes (not RFC 8785 JCS)."""
    return json.dumps(
        materialize_json_value(value),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def encode_jcs_bytes(value: JSONValue) -> bytes:
    """Encode a JSON value to RFC 8785 JCS UTF-8 bytes."""
    from gateway_repository_contracts._jcs import encode_jcs_bytes as _encode_jcs_bytes

    return _encode_jcs_bytes(materialize_json_value(value))


def _reject_duplicate_members(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    seen: set[str] = set()
    result: dict[str, Any] = {}
    for key, item in pairs:
        if key in seen:
            raise RepositoryContractError(
                RepositoryContractErrorCode.WIRE_DUPLICATE_MEMBER,
                "duplicate member",
            )
        seen.add(key)
        result[key] = item
    return result


def parse_json_document(payload: bytes) -> Any:
    """Parse strict JSON document bytes with fail-closed semantics."""
    if len(payload) > CONTROL_JSON_MAX_BYTES:
        raise RepositoryContractError(
            RepositoryContractErrorCode.WIRE_PAYLOAD_TOO_LARGE,
            "payload exceeds limit",
        )
    try:
        text = payload.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise RepositoryContractError(
            RepositoryContractErrorCode.WIRE_INVALID_UTF8,
            "invalid UTF-8",
        ) from exc
    try:
        decoder = json.JSONDecoder(
            object_pairs_hook=_reject_duplicate_members,
            parse_int=parse_json_int,
            parse_constant=parse_json_constant,
        )
        value, end = decoder.raw_decode(text)
    except RepositoryContractError:
        raise
    except RecursionError as exc:
        raise RepositoryContractError(
            RepositoryContractErrorCode.JSON_NESTING_TOO_DEEP,
            "JSON nesting too deep",
        ) from exc
    except json.JSONDecodeError as exc:
        raise RepositoryContractError(
            RepositoryContractErrorCode.WIRE_JSON_SYNTAX_INVALID,
            "invalid JSON",
        ) from exc
    if end != len(text):
        raise RepositoryContractError(
            RepositoryContractErrorCode.WIRE_TRAILING_DATA,
            "trailing data",
        )
    _validate_json_depth(value, depth=0)
    freeze_json_value(value)
    return value


def _validate_json_depth(value: object, *, depth: int) -> None:
    if depth > JSON_MAX_DEPTH:
        raise RepositoryContractError(
            RepositoryContractErrorCode.JSON_NESTING_TOO_DEEP,
            "JSON nesting too deep",
        )
    if isinstance(value, list):
        for item in value:
            _validate_json_depth(item, depth=depth + 1)
    elif isinstance(value, dict):
        for item in value.values():
            _validate_json_depth(item, depth=depth + 1)


def parse_control_json(
    payload: bytes,
    *,
    max_bytes: int = CONTROL_JSON_MAX_BYTES,
) -> dict[str, JSONValue]:
    """Parse strict UTF-8 control JSON object with fail-closed semantics."""
    if len(payload) > max_bytes:
        raise RepositoryContractError(
            RepositoryContractErrorCode.WIRE_PAYLOAD_TOO_LARGE,
            "payload exceeds limit",
        )
    value = parse_json_document(payload)
    if not isinstance(value, dict):
        raise RepositoryContractError(
            RepositoryContractErrorCode.WIRE_NON_OBJECT_ROOT,
            "root must be object",
        )
    materialized = materialize_json_value(freeze_json_value(value))
    if not isinstance(materialized, dict):
        raise RepositoryContractError(
            RepositoryContractErrorCode.WIRE_NON_OBJECT_ROOT,
            "root must be object",
        )
    return materialized


def decode_wire_mapping(
    value: object,
    *,
    allowed_keys: frozenset[str],
    label: str,
    ignore_unknown: bool = True,
) -> dict[str, JSONValue]:
    """Decode a wire object with optional forward-compatible unknown-field tolerance."""
    if not isinstance(value, Mapping):
        raise RepositoryContractError(
            RepositoryContractErrorCode.WIRE_INVALID_VALUE,
            f"{label} must be object",
        )
    decoded: dict[str, JSONValue] = {}
    for key, item in value.items():
        if type(key) is not str:
            raise RepositoryContractError(
                RepositoryContractErrorCode.WIRE_INVALID_VALUE,
                f"{label} key must be string",
            )
        validate_unicode_string(key)
        if key not in allowed_keys:
            if ignore_unknown:
                continue
            raise RepositoryContractError(
                RepositoryContractErrorCode.WIRE_UNKNOWN_FIELD,
                f"{label} unknown field",
            )
        decoded[key] = freeze_json_value(item)
    return decoded


def require_mapping_keys(
    mapping: Mapping[str, JSONValue],
    required: frozenset[str],
    *,
    label: str,
) -> None:
    missing = required - mapping.keys()
    if missing:
        raise RepositoryContractError(
            RepositoryContractErrorCode.WIRE_INVALID_VALUE,
            f"{label} missing required field",
        )
