"""Thin loader and dispatcher for the Repository ENUM/SET golden corpus."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from gateway_repository_service.arrow_mapping import normalize_sql_type
from gateway_repository_service.enum_set_sql import (
    SQL_TYPE_MALFORMED_CODE,
    SQL_VALUE_ILLEGAL_CODE,
    SqlTypeMalformedError,
    SqlValueIllegalError,
    parse_enum_value,
    parse_set_value,
)
from support.sql_enum_set_frames import (
    encode_base64url,
    encode_null_scalar_frame,
    encode_sequence_frame,
    encode_string_scalar_frame,
)

CORPUS_ROOT = (
    Path(__file__).resolve().parents[3]
    / "fixtures"
    / "vectors"
    / "repository"
    / "sql-enum-set"
    / "v1"
)
CASE_FILES = ("normalize.jsonl", "values.jsonl", "invalid.jsonl")
OPERATIONS = frozenset(
    {
        "normalize-sql-type",
        "encode-enum-value",
        "encode-set-value",
        "reject-malformed-type",
        "reject-illegal-value",
    }
)


class GoldenMismatch(AssertionError):
    """Raised when a golden case expected value or error code does not match."""


def load_sql_enum_set_cases() -> list[dict[str, Any]]:
    cases: list[dict[str, Any]] = []
    for file_name in CASE_FILES:
        path = CORPUS_ROOT / file_name
        for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if not line:
                raise ValueError(f"{path}:{line_number}: empty case line")
            case = json.loads(line)
            if not isinstance(case, dict):
                raise ValueError(f"{path}:{line_number}: case must be an object")
            case_id = case.get("case_id")
            if not isinstance(case_id, str) or not case_id:
                raise ValueError(f"{path}:{line_number}: case_id must be a non-empty string")
            if case.get("case_schema_version") != 1:
                raise ValueError(f"{path}:{line_number}: case_schema_version must be 1")
            operation = case.get("operation")
            if operation not in OPERATIONS:
                raise ValueError(f"{path}:{line_number}: unsupported operation {operation!r}")
            cases.append(case)
    ids = [case["case_id"] for case in cases]
    if len(ids) != len(set(ids)):
        raise ValueError("ENUM/SET corpus contains duplicate case_id")
    return cases


def dispatch_sql_enum_set_case(case: dict[str, Any]) -> None:
    operation = case["operation"]
    if "expected_error" in case:
        _dispatch_invalid(operation, case["input"], case["expected_error"]["code"])
        return
    actual = compute_sql_enum_set_expected(operation, case["input"])
    expected = case["expected"]
    if actual != expected:
        raise GoldenMismatch(
            f"case {case.get('case_id')!r} mismatch:\n"
            f"  actual={actual!r}\n"
            f"  expected={expected!r}"
        )


def compute_sql_enum_set_expected(operation: str, input_obj: dict[str, Any]) -> dict[str, Any]:
    if operation == "normalize-sql-type":
        normalized = normalize_sql_type(input_obj["data_type"], input_obj["column_type"])
        return {"normalized_sql_type": normalized}
    if operation == "encode-enum-value":
        enum_value = parse_enum_value(input_obj["sql_type"], _python_value(input_obj["value"]))
        return _enum_expected(enum_value)
    if operation == "encode-set-value":
        set_value = parse_set_value(input_obj["sql_type"], _python_value(input_obj["value"]))
        return _set_expected(set_value)
    if operation == "reject-malformed-type":
        normalize_sql_type(input_obj["data_type"], input_obj["column_type"])
        raise GoldenMismatch("reject-malformed-type succeeded")
    if operation == "reject-illegal-value":
        _illegal_value(input_obj)
        raise GoldenMismatch("reject-illegal-value succeeded")
    raise GoldenMismatch(f"unsupported operation {operation!r}")


def _dispatch_invalid(operation: str, input_obj: dict[str, Any], code: str) -> None:
    try:
        compute_sql_enum_set_expected(operation, input_obj)
    except SqlTypeMalformedError as exc:
        if exc.code != code or code != SQL_TYPE_MALFORMED_CODE:
            raise GoldenMismatch(f"expected stable code {code}, got {exc.code}") from exc
        return
    except SqlValueIllegalError as exc:
        if exc.code != code or code != SQL_VALUE_ILLEGAL_CODE:
            raise GoldenMismatch(f"expected stable code {code}, got {exc.code}") from exc
        return
    raise GoldenMismatch(f"expected stable code {code}, but operation succeeded")


def _illegal_value(input_obj: dict[str, Any]) -> None:
    sql_type = input_obj["sql_type"]
    value = _python_value(input_obj["value"])
    if sql_type.startswith("ENUM"):
        parse_enum_value(sql_type, value)
        return
    parse_set_value(sql_type, value)


def _python_value(value_obj: dict[str, Any]) -> object:
    kind = value_obj["kind"]
    if kind == "null":
        return None
    if kind == "string":
        return value_obj["text"]
    if kind == "set-members":
        return list(value_obj["members"])
    if kind == "set-text":
        return value_obj["text"]
    if kind == "integer":
        return value_obj["value"]
    raise GoldenMismatch(f"unsupported value kind {kind!r}")


def _enum_expected(parsed: str | None) -> dict[str, str]:
    if parsed is None:
        return {"scalar_frame_base64url": encode_base64url(encode_null_scalar_frame())}
    payload, frame = encode_string_scalar_frame(parsed)
    return {
        "payload_base64url": encode_base64url(payload),
        "scalar_frame_base64url": encode_base64url(frame),
    }


def _set_expected(parsed: list[str] | None) -> dict[str, str]:
    if parsed is None:
        return {"scalar_frame_base64url": encode_base64url(encode_null_scalar_frame())}
    item_frames = tuple(encode_string_scalar_frame(member)[1] for member in parsed)
    return {"sequence_frame_base64url": encode_base64url(encode_sequence_frame(item_frames))}
