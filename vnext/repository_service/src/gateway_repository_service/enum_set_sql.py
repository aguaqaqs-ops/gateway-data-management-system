"""Bounded ENUM/SET SQL type parser and fail-closed value validation."""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum
from typing import Final

SQL_TYPE_MALFORMED_CODE: Final = "SQL_TYPE_MALFORMED"
SQL_VALUE_ILLEGAL_CODE: Final = "SQL_VALUE_ILLEGAL"

_MAX_ENUM_MEMBERS: Final = 65535
_MAX_SET_MEMBERS: Final = 64
_MAX_LABEL_SCALARS: Final = 255
_MAX_NORMALIZED_BYTES: Final = 64 * 1024

_COLLATE_MODIFIER = re.compile(r"\s+COLLATE\s+\S+", re.IGNORECASE)
_CHARACTER_SET_MODIFIER = re.compile(r"\s+CHARACTER\s+SET\s+\S+", re.IGNORECASE)
_LEADING_KEYWORD = re.compile(r"^(ENUM|SET)\b", re.IGNORECASE)


class SqlTypeMalformedError(ValueError):
    """Raised when an ENUM/SET spelling fails the closed v1 grammar."""

    code: str = SQL_TYPE_MALFORMED_CODE

    def __init__(self, message: str) -> None:
        super().__init__(message)


class SqlValueIllegalError(ValueError):
    """Raised when an ENUM/SET driver value cannot be proven legal."""

    code: str = SQL_VALUE_ILLEGAL_CODE

    def __init__(self, message: str) -> None:
        super().__init__(message)


class EnumSetSqlTypeKind(StrEnum):
    VALID = "valid"
    MALFORMED = "malformed"
    NOT_ENUM_SET = "not_enum_set"


@dataclass(frozen=True)
class EnumSetSqlType:
    kind: str
    labels: tuple[str, ...]
    normalized: str


def classify_enum_set_sql_type(
    sql_type: str,
) -> tuple[EnumSetSqlTypeKind, EnumSetSqlType | None]:
    """Classify ENUM/SET spellings into valid, malformed, or non-family."""

    stripped = _collapse_whitespace_outside_quotes(_strip_charset_collate(sql_type))
    rest = stripped.lstrip()
    match = _LEADING_KEYWORD.match(rest)
    if match is None:
        return EnumSetSqlTypeKind.NOT_ENUM_SET, None
    kind = match.group(1).upper()
    parsed = _parse_enum_set_body(kind, rest[match.end() :])
    if parsed is None:
        return EnumSetSqlTypeKind.MALFORMED, None
    return EnumSetSqlTypeKind.VALID, parsed


def parse_enum_value(sql_type: str | EnumSetSqlType, value: object) -> str | None:
    """Return the declared ENUM label, or None for SQL NULL."""

    parsed = _require_kind(sql_type, "ENUM")
    if value is None:
        return None
    if type(value) is not str:
        raise SqlValueIllegalError("ENUM value must be a Unicode string")
    for label in parsed.labels:
        if label == value:
            return label
    raise SqlValueIllegalError("ENUM value is not a declared label")


def parse_set_value(sql_type: str | EnumSetSqlType, value: object) -> list[str] | None:
    """Return declared SET members in declaration order, or None for SQL NULL."""

    parsed = _require_kind(sql_type, "SET")
    if value is None:
        return None
    members = _set_members_from_driver(value)
    seen: set[str] = set()
    label_set = set(parsed.labels)
    for member in members:
        if type(member) is not str:
            raise SqlValueIllegalError("SET member must be a Unicode string")
        if member not in label_set:
            raise SqlValueIllegalError("SET value contains an undeclared or empty member")
        if member in seen:
            raise SqlValueIllegalError("SET value contains duplicate members")
        seen.add(member)
    return [label for label in parsed.labels if label in seen]


def quote_sql_string(label: str) -> str:
    return "'" + label.replace("'", "''") + "'"


def _require_kind(sql_type: str | EnumSetSqlType, expected: str) -> EnumSetSqlType:
    if isinstance(sql_type, EnumSetSqlType):
        parsed = sql_type
    else:
        classification, classified = classify_enum_set_sql_type(sql_type)
        if classification != EnumSetSqlTypeKind.VALID or classified is None:
            raise SqlTypeMalformedError(f"invalid ENUM/SET SQL type spelling: {sql_type}")
        parsed = classified
    if parsed.kind != expected:
        raise SqlTypeMalformedError(
            f"expected {expected} SQL type, got {parsed.kind}"
        )
    return parsed


def _set_members_from_driver(value: object) -> list[object]:
    if type(value) is list:
        return list(value)
    if type(value) is str:
        if value == "":
            return []
        return list(value.split(","))
    raise SqlValueIllegalError("SET value must be a string list or comma-separated text")


def _strip_charset_collate(text: str) -> str:
    parts: list[str] = []
    for quoted, segment in _iter_single_quoted_segments(text):
        if quoted:
            parts.append(segment)
            continue
        segment = _CHARACTER_SET_MODIFIER.sub("", segment)
        segment = _COLLATE_MODIFIER.sub("", segment)
        parts.append(segment)
    return "".join(parts)


def _collapse_whitespace_outside_quotes(text: str) -> str:
    parts: list[str] = []
    for quoted, segment in _iter_single_quoted_segments(text):
        if quoted:
            parts.append(segment)
        else:
            parts.append(" ".join(segment.split()))
    return "".join(parts)


def _iter_single_quoted_segments(text: str) -> list[tuple[bool, str]]:
    segments: list[tuple[bool, str]] = []
    index = 0
    length = len(text)
    while index < length:
        if text[index] == "'":
            start = index
            index += 1
            while index < length:
                if text[index] == "'":
                    if index + 1 < length and text[index + 1] == "'":
                        index += 2
                        continue
                    index += 1
                    segments.append((True, text[start:index]))
                    break
                index += 1
            else:
                segments.append((True, text[start:]))
            continue
        start = index
        while index < length and text[index] != "'":
            index += 1
        segments.append((False, text[start:index]))
    return segments


def _parse_enum_set_body(kind: str, body: str) -> EnumSetSqlType | None:
    index = _skip_ws(body, 0)
    if index >= len(body) or body[index] != "(":
        return None
    index += 1
    index = _skip_ws(body, index)
    if index < len(body) and body[index] == ")":
        return None
    labels: list[str] = []
    while True:
        label, index = _parse_sql_string(body, index)
        if label is None:
            return None
        labels.append(label)
        index = _skip_ws(body, index)
        if index >= len(body):
            return None
        if body[index] == ",":
            index += 1
            index = _skip_ws(body, index)
            if index < len(body) and body[index] == ")":
                return None
            continue
        if body[index] == ")":
            index += 1
            break
        return None
    if body[index:].strip():
        return None
    return _validated_enum_set(kind, tuple(labels))


def _parse_sql_string(text: str, index: int) -> tuple[str | None, int]:
    if index >= len(text) or text[index] != "'":
        return None, index
    index += 1
    chars: list[str] = []
    while index < len(text):
        if text[index] == "'":
            if index + 1 < len(text) and text[index + 1] == "'":
                chars.append("'")
                index += 2
                continue
            return "".join(chars), index + 1
        chars.append(text[index])
        index += 1
    return None, index


def _skip_ws(text: str, index: int) -> int:
    while index < len(text) and text[index].isspace():
        index += 1
    return index


def _validated_enum_set(kind: str, labels: tuple[str, ...]) -> EnumSetSqlType | None:
    if kind == "ENUM":
        if not 1 <= len(labels) <= _MAX_ENUM_MEMBERS:
            return None
        for label in labels:
            if label and not 1 <= len(label) <= _MAX_LABEL_SCALARS:
                return None
            if not label:
                continue
    elif kind == "SET":
        if not 1 <= len(labels) <= _MAX_SET_MEMBERS:
            return None
        for label in labels:
            if not 1 <= len(label) <= _MAX_LABEL_SCALARS:
                return None
            if "," in label:
                return None
    else:
        return None
    seen: set[bytes] = set()
    for label in labels:
        encoded = label.encode("utf-8")
        if encoded in seen:
            return None
        seen.add(encoded)
    normalized = f"{kind}({','.join(quote_sql_string(label) for label in labels)})"
    if len(normalized.encode("utf-8")) > _MAX_NORMALIZED_BYTES:
        return None
    return EnumSetSqlType(kind, labels, normalized)
