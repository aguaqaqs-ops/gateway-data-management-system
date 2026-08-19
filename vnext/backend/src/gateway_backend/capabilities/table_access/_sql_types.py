"""Dump-side SQL type normalization. Independent of Repository converters."""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum

from gateway_shared_kernel import DeclaredType, DeclaredTypeKind

from gateway_backend.capabilities.table_access.contracts import (
    ParserDiagnosticCode,
    SqlLogicalType,
)

_MAX_ENUM_MEMBERS = 65535
_MAX_SET_MEMBERS = 64
_MAX_LABEL_SCALARS = 255

_COLLATE_MODIFIER = re.compile(r"\s+COLLATE\s+\S+", re.IGNORECASE)
_CHARACTER_SET_MODIFIER = re.compile(r"\s+CHARACTER\s+SET\s+\S+", re.IGNORECASE)
_LEADING_ENUM_SET = re.compile(r"^(ENUM|SET)\b", re.IGNORECASE)
_INTEGER_DISPLAY = re.compile(
    r"^(TINYINT|SMALLINT|MEDIUMINT|INT|BIGINT)\(\d+\)(\s+UNSIGNED)?$",
    re.IGNORECASE,
)
_FLOAT_DISPLAY = re.compile(r"^(FLOAT|DOUBLE)(?:\(\d+(?:\s*,\s*\d+)?\))?$", re.IGNORECASE)
_DECIMAL = re.compile(r"^DECIMAL\((\d+)(?:,(\d+))?\)$")
_BIT = re.compile(r"^BIT\((\d+)\)$")
_SIZED_CHAR = re.compile(r"^(CHAR|VARCHAR)\(\d+\)$")
_SIZED_BIN = re.compile(r"^(BINARY|VARBINARY)\(\d+\)$")
_TEMPORAL_BASE = frozenset({"TIME", "DATETIME", "TIMESTAMP"})
_TEMPORAL_LIKE = re.compile(r"^(TIME|DATETIME|TIMESTAMP)(?:\(|$|\s)")
_ASCII_TYPE = re.compile(r"^[\x20-\x7E]+$")

_INTEGER_BITS = {
    "TINYINT": 8,
    "SMALLINT": 16,
    "MEDIUMINT": 24,
    "INT": 32,
    "BIGINT": 64,
}
_TEXT_TYPES = frozenset({"CHAR", "VARCHAR", "TINYTEXT", "TEXT", "MEDIUMTEXT", "LONGTEXT"})
_BLOB_TYPES = frozenset({"BINARY", "VARBINARY", "TINYBLOB", "BLOB", "MEDIUMBLOB", "LONGBLOB"})
_ZEROFILL = re.compile(r"\bZEROFILL\b", re.IGNORECASE)


class EnumSetKind(StrEnum):
    VALID = "valid"
    MALFORMED = "malformed"
    NOT_ENUM_SET = "not_enum_set"


@dataclass(frozen=True, slots=True)
class EnumSetType:
    kind: str
    labels: tuple[str, ...]
    normalized: str


@dataclass(frozen=True, slots=True)
class MappedSqlType:
    sql_type: str
    logical_type: SqlLogicalType
    declared_type: DeclaredType | None
    enum_or_set_labels: tuple[str, ...] | None
    error: ParserDiagnosticCode | None


def map_sql_type(raw_type: str, *, max_enum_set_bytes: int) -> MappedSqlType:
    if type(raw_type) is not str or raw_type == "":
        return _unknown("")
    stripped = _strip_charset_collate(raw_type)
    family, parsed = classify_enum_set_sql_type(stripped, max_enum_set_bytes=max_enum_set_bytes)
    if family is EnumSetKind.MALFORMED:
        return MappedSqlType(
            sql_type=_bounded_unknown_spelling(stripped),
            logical_type=SqlLogicalType.UNKNOWN,
            declared_type=None,
            enum_or_set_labels=None,
            error=ParserDiagnosticCode.SQL_TYPE_MALFORMED,
        )
    if family is EnumSetKind.VALID and parsed is not None:
        if parsed.kind == "ENUM":
            return MappedSqlType(
                sql_type=parsed.normalized,
                logical_type=SqlLogicalType.ENUM,
                declared_type=DeclaredType(kind=DeclaredTypeKind.STRING),
                enum_or_set_labels=parsed.labels,
                error=None,
            )
        return MappedSqlType(
            sql_type=parsed.normalized,
            logical_type=SqlLogicalType.SET,
            declared_type=None,
            enum_or_set_labels=parsed.labels,
            error=None,
        )
    collapsed = " ".join(_ZEROFILL.sub(" ", stripped).split())
    if collapsed == "":
        return _unknown("")
    if not _ASCII_TYPE.fullmatch(collapsed):
        return MappedSqlType(
            sql_type=_bounded_unknown_spelling(stripped),
            logical_type=SqlLogicalType.UNKNOWN,
            declared_type=None,
            enum_or_set_labels=None,
            error=ParserDiagnosticCode.SQL_TYPE_MALFORMED,
        )
    upper = collapsed.upper()
    upper = _strip_integer_display(upper)
    if upper == "INTEGER":
        upper = "INT"
    elif upper == "INTEGER UNSIGNED":
        upper = "INT UNSIGNED"
    elif upper == "BOOL":
        upper = "BOOLEAN"
    known = _map_known(upper)
    if known is not None:
        return known
    if _is_malformed_known_family(upper):
        return MappedSqlType(
            sql_type=upper,
            logical_type=SqlLogicalType.UNKNOWN,
            declared_type=None,
            enum_or_set_labels=None,
            error=ParserDiagnosticCode.SQL_TYPE_MALFORMED,
        )
    return _unknown(upper)


def classify_enum_set_sql_type(
    sql_type: str, *, max_enum_set_bytes: int
) -> tuple[EnumSetKind, EnumSetType | None]:
    stripped = _collapse_whitespace_outside_quotes(_strip_charset_collate(sql_type))
    rest = stripped.lstrip()
    match = _LEADING_ENUM_SET.match(rest)
    if match is None:
        return EnumSetKind.NOT_ENUM_SET, None
    kind = match.group(1).upper()
    parsed = _parse_enum_set_body(kind, rest[match.end() :], max_enum_set_bytes=max_enum_set_bytes)
    if parsed is None:
        return EnumSetKind.MALFORMED, None
    return EnumSetKind.VALID, parsed


def quote_sql_string(label: str) -> str:
    return "'" + label.replace("'", "''") + "'"


def _map_known(upper: str) -> MappedSqlType | None:
    if upper == "BOOLEAN":
        return _standard(upper, DeclaredType(kind=DeclaredTypeKind.BOOLEAN))
    if upper in _INTEGER_BITS:
        return _standard(
            upper,
            DeclaredType(kind=DeclaredTypeKind.SIGNED_INTEGER, bits=_INTEGER_BITS[upper]),
        )
    if upper.endswith(" UNSIGNED"):
        base = upper.removesuffix(" UNSIGNED")
        if base in _INTEGER_BITS:
            return _standard(
                upper,
                DeclaredType(kind=DeclaredTypeKind.UNSIGNED_INTEGER, bits=_INTEGER_BITS[base]),
            )
    float_match = _FLOAT_DISPLAY.fullmatch(upper)
    if float_match is not None:
        name = float_match.group(1)
        if name == "FLOAT":
            return _standard("FLOAT", DeclaredType(kind=DeclaredTypeKind.FLOAT32))
        return _standard("DOUBLE", DeclaredType(kind=DeclaredTypeKind.FLOAT64))
    decimal_match = _DECIMAL.fullmatch(upper)
    if decimal_match is not None:
        precision = int(decimal_match.group(1))
        scale = int(decimal_match.group(2) or "0")
        if not (1 <= precision <= 65 and 0 <= scale <= 30 and scale <= precision):
            return None
        return _standard(
            f"DECIMAL({precision},{scale})",
            DeclaredType(kind=DeclaredTypeKind.DECIMAL, precision=precision, scale=scale),
        )
    bit_match = _BIT.fullmatch(upper)
    if bit_match is not None:
        width = int(bit_match.group(1))
        if not 1 <= width <= 64:
            return None
        return _standard(f"BIT({width})", DeclaredType(kind=DeclaredTypeKind.BIT, bit_width=width))
    if upper == "DATE":
        return _standard(upper, DeclaredType(kind=DeclaredTypeKind.DATE))
    temporal = _map_temporal(upper)
    if temporal is not None:
        return temporal
    if upper in _TEXT_TYPES or _SIZED_CHAR.fullmatch(upper) is not None:
        return _standard(upper, DeclaredType(kind=DeclaredTypeKind.STRING))
    if upper in _BLOB_TYPES or _SIZED_BIN.fullmatch(upper) is not None:
        return _standard(upper, DeclaredType(kind=DeclaredTypeKind.BINARY))
    if upper == "JSON":
        return MappedSqlType(
            sql_type="JSON",
            logical_type=SqlLogicalType.JSON,
            declared_type=DeclaredType(kind=DeclaredTypeKind.STRING),
            enum_or_set_labels=None,
            error=None,
        )
    return None


def _map_temporal(upper: str) -> MappedSqlType | None:
    if upper in _TEMPORAL_BASE:
        return _temporal_mapped(upper, None)
    for kind in ("TIME", "DATETIME", "TIMESTAMP"):
        prefix = f"{kind}("
        if not upper.startswith(prefix) or not upper.endswith(")"):
            continue
        inner = upper[len(prefix) : -1]
        if not inner or not inner.isdigit() or (len(inner) > 1 and inner[0] == "0"):
            return None
        fsp = int(inner)
        if not 0 <= fsp <= 6:
            return None
        return _temporal_mapped(kind, fsp)
    return None


def _temporal_mapped(kind: str, fsp: int | None) -> MappedSqlType:
    sql_type = kind if fsp is None else f"{kind}({fsp})"
    if kind == "TIME":
        declared = DeclaredType(kind=DeclaredTypeKind.TIME_DURATION)
    elif kind == "TIMESTAMP":
        declared = DeclaredType(kind=DeclaredTypeKind.TIMESTAMP)
    else:
        declared = DeclaredType(kind=DeclaredTypeKind.DATETIME)
    return _standard(sql_type, declared)


def _is_malformed_known_family(upper: str) -> bool:
    if upper.startswith("DECIMAL") or upper.startswith("BIT("):
        return True
    if _TEMPORAL_LIKE.match(upper) is not None:
        return True
    if _LEADING_ENUM_SET.match(upper) is not None:
        return True
    return False


def _standard(sql_type: str, declared: DeclaredType) -> MappedSqlType:
    return MappedSqlType(
        sql_type=sql_type,
        logical_type=SqlLogicalType.STANDARD,
        declared_type=declared,
        enum_or_set_labels=None,
        error=None,
    )


def _unknown(sql_type: str) -> MappedSqlType:
    return MappedSqlType(
        sql_type=_bounded_unknown_spelling(sql_type) or "UNKNOWN",
        logical_type=SqlLogicalType.UNKNOWN,
        declared_type=None,
        enum_or_set_labels=None,
        error=ParserDiagnosticCode.UNKNOWN_SQL_TYPE,
    )


def _bounded_unknown_spelling(sql_type: str) -> str:
    collapsed = " ".join(sql_type.split())
    if collapsed == "":
        return "UNKNOWN"
    if _ASCII_TYPE.fullmatch(collapsed) is None:
        return "UNKNOWN"
    return collapsed.upper()


def _strip_integer_display(upper: str) -> str:
    match = _INTEGER_DISPLAY.fullmatch(upper)
    if match is None:
        return upper
    suffix = match.group(2) or ""
    return f"{match.group(1).upper()}{suffix.upper()}"


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


def _parse_enum_set_body(kind: str, body: str, *, max_enum_set_bytes: int) -> EnumSetType | None:
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
    return _validated_enum_set(kind, tuple(labels), max_enum_set_bytes=max_enum_set_bytes)


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


def _validated_enum_set(
    kind: str, labels: tuple[str, ...], *, max_enum_set_bytes: int
) -> EnumSetType | None:
    if kind == "ENUM":
        if not 1 <= len(labels) <= _MAX_ENUM_MEMBERS:
            return None
        for label in labels:
            if label and not 1 <= len(label) <= _MAX_LABEL_SCALARS:
                return None
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
    if len(normalized.encode("utf-8")) > max_enum_set_bytes:
        return None
    return EnumSetType(kind, labels, normalized)
