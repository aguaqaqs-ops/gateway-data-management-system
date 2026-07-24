"""Strict JSON loader tests."""

from __future__ import annotations

import pytest

from gateway_conformance.strict_json import StrictJSONValidationError, loads_strict_json


def test_strict_json_rejects_duplicate_top_level_key() -> None:
    with pytest.raises(StrictJSONValidationError, match="duplicate"):
        loads_strict_json('{"a":1,"a":2}')


def test_strict_json_rejects_nested_duplicate_key() -> None:
    with pytest.raises(StrictJSONValidationError, match="duplicate"):
        loads_strict_json('{"outer":{"k":1,"k":2}}')


def test_strict_json_rejects_nan() -> None:
    with pytest.raises(StrictJSONValidationError):
        loads_strict_json('{"value": NaN}')


def test_strict_json_rejects_ijson_overflow_integer() -> None:
    with pytest.raises(StrictJSONValidationError):
        loads_strict_json('{"value": 9007199254740993}')


def test_strict_json_accepts_ijson_boundary_integer() -> None:
    doc = loads_strict_json('{"value": 9007199254740991}')
    assert doc["value"] == 9007199254740991
