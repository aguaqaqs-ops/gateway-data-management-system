"""Strict JSON object loader that rejects duplicates and non-JSON constants."""

from __future__ import annotations

import json
from typing import Any, NoReturn


class DuplicateMemberError(ValueError):
    """JSON object contained a duplicate member name."""


class NonJsonConstantError(ValueError):
    """JSON text contained NaN / Infinity / -Infinity."""


def loads_object_rejecting_duplicates(text: str) -> dict[str, Any]:
    """Parse a JSON document that must be a single object without duplicate keys.

    Rejects non-JSON constants ``NaN``, ``Infinity``, and ``-Infinity``.
    """

    def object_pairs_hook(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        out: dict[str, Any] = {}
        for key, value in pairs:
            if key in out:
                raise DuplicateMemberError(f"duplicate JSON member {key!r}")
            out[key] = value
        return out

    def parse_constant(name: str) -> NoReturn:
        raise NonJsonConstantError(f"non-JSON constant {name!r} is not allowed")

    try:
        value = json.loads(
            text,
            object_pairs_hook=object_pairs_hook,
            parse_constant=parse_constant,
        )
    except DuplicateMemberError:
        raise
    except NonJsonConstantError:
        raise
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid JSON: {exc}") from exc
    if not isinstance(value, dict):
        raise ValueError("JSON document must be an object")
    return value
