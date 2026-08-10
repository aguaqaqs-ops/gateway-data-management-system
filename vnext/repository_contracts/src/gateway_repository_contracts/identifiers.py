"""Contract-owned exact identifier validation for versioned reads."""

from __future__ import annotations

from typing import Annotated

from pydantic import BeforeValidator

_MIN_CODE_POINTS = 1
_MAX_CODE_POINTS = 64


def _code_point_count(value: str) -> int:
    return len(value)


def validate_versioned_identifier(value: object, *, reject_edge_whitespace: bool) -> str:
    if not isinstance(value, str):
        raise ValueError("identifier must be a string")
    if reject_edge_whitespace and value != value.strip():
        raise ValueError("table name must not have leading or trailing whitespace")
    count = _code_point_count(value)
    if count < _MIN_CODE_POINTS or count > _MAX_CODE_POINTS:
        raise ValueError("identifier length must be between 1 and 64 Unicode code points")
    for char in value:
        code = ord(char)
        if char == "\x00":
            raise ValueError("identifier must not contain NUL")
        if code < 32 or code == 127:
            raise ValueError("identifier must not contain ASCII control characters")
        if char in {"/", "\\"}:
            raise ValueError("identifier must not contain path separators")
    return value


def _validate_column_identifier(value: object) -> str:
    return validate_versioned_identifier(value, reject_edge_whitespace=False)


def _validate_table_identifier(value: object) -> str:
    return validate_versioned_identifier(value, reject_edge_whitespace=True)


VersionedIdentifierString = Annotated[str, BeforeValidator(_validate_column_identifier)]
VersionedTableNameString = Annotated[str, BeforeValidator(_validate_table_identifier)]
