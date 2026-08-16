"""Shared Kernel consumer of Repository ENUM/SET content-byte goldens.

SQL grammar stays in Repository Service. This module only re-encodes already
canonical labels/members with production string/null/sequence primitives.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from gateway_shared_kernel import (
    CollectionSemantics,
    DeclaredType,
    DeclaredTypeKind,
    EncodedScalar,
    NullScalar,
    StringScalar,
    encode_collection,
    encode_typed_scalar,
)
from gateway_shared_kernel.testing.codec import encode_base64url

VALUES_PATH = (
    Path(__file__).resolve().parents[2]
    / "fixtures"
    / "vectors"
    / "repository"
    / "sql-enum-set"
    / "v1"
    / "values.jsonl"
)
EXPECTED_VALUE_CASE_COUNT = 9


def _load_value_cases() -> list[dict[str, Any]]:
    cases: list[dict[str, Any]] = []
    for line_number, line in enumerate(VALUES_PATH.read_text(encoding="utf-8").splitlines(), 1):
        if not line:
            raise ValueError(f"{VALUES_PATH}:{line_number}: empty case line")
        case = json.loads(line)
        if not isinstance(case, dict):
            raise ValueError(f"{VALUES_PATH}:{line_number}: case must be an object")
        if not isinstance(case.get("case_id"), str):
            raise ValueError(f"{VALUES_PATH}:{line_number}: case_id must be a string")
        cases.append(case)
    ids = [case["case_id"] for case in cases]
    if len(ids) != len(set(ids)):
        raise ValueError("ENUM/SET values corpus contains duplicate case_id")
    return cases


_CASES = _load_value_cases()


def test_sql_enum_set_value_case_set_is_exact() -> None:
    assert len(_CASES) == EXPECTED_VALUE_CASE_COUNT
    assert {case["operation"] for case in _CASES} <= {"encode-enum-value", "encode-set-value"}


@pytest.mark.parametrize("case", _CASES, ids=lambda case: case["case_id"])
def test_sql_enum_set_values_match_shared_kernel_bytes(case: dict[str, Any]) -> None:
    actual = _encode_content_bytes(case["operation"], case["input"])
    expected = case["expected"]
    for key, value in expected.items():
        assert actual[key] == value, f"{case['case_id']} field {key}"


def _encode_content_bytes(operation: str, input_obj: dict[str, Any]) -> dict[str, str]:
    value = input_obj["value"]
    kind = value["kind"]
    if operation == "encode-enum-value":
        encoded = _encode_scalar(kind, value)
        return {
            "payload_base64url": encode_base64url(encoded.payload),
            "scalar_frame_base64url": encode_base64url(encoded.scalar_frame),
        }
    if operation != "encode-set-value":
        raise AssertionError(f"unsupported operation {operation!r}")
    if kind == "null":
        encoded = _encode_scalar(kind, value)
        return {"scalar_frame_base64url": encode_base64url(encoded.scalar_frame)}
    if kind != "set-members":
        raise AssertionError(f"unsupported SET value kind {kind!r}")
    items = [_encode_scalar("string", {"text": member}).scalar_frame for member in value["members"]]
    encoded_collection = encode_collection(CollectionSemantics.SEQUENCE, items=items)
    return {
        "sequence_frame_base64url": encode_base64url(encoded_collection.collection_frame),
    }


def _encode_scalar(kind: str, value: dict[str, Any]) -> EncodedScalar:
    if kind == "null":
        return encode_typed_scalar(DeclaredType(kind=DeclaredTypeKind.NULL), NullScalar())
    if kind == "string":
        return encode_typed_scalar(
            DeclaredType(kind=DeclaredTypeKind.STRING),
            StringScalar(text=value["text"]),
        )
    raise AssertionError(f"unsupported scalar kind {kind!r}")
