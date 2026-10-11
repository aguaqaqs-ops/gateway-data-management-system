"""Authoritative SQL column spelling to Shared Kernel DeclaredType mapping."""

from __future__ import annotations

import re

from gateway_shared_kernel import DeclaredType, DeclaredTypeKind

_TYPE_TOKEN = re.compile(r"^([A-Z]+)(?:\(([^)]*)\))?(?:\s+(UNSIGNED))?(?:\s+ZEROFILL)?.*$")
_INTEGER_BITS = {
    "TINYINT": 8,
    "SMALLINT": 16,
    "MEDIUMINT": 24,
    "INT": 32,
    "INTEGER": 32,
    "BIGINT": 64,
}
_TEXT_TYPES = frozenset(
    {"CHAR", "VARCHAR", "TINYTEXT", "TEXT", "MEDIUMTEXT", "LONGTEXT", "JSON", "ENUM", "SET"}
)
_BINARY_TYPES = frozenset(
    {"BINARY", "VARBINARY", "TINYBLOB", "BLOB", "MEDIUMBLOB", "LONGBLOB"}
)
_INTEGER_DISPLAY = re.compile(
    r"^(TINYINT|SMALLINT|MEDIUMINT|INT|INTEGER|BIGINT)\(\d+\)(?:\s+(UNSIGNED|ZEROFILL))?$"
)
_FLOAT_DISPLAY = re.compile(r"^(FLOAT|DOUBLE|REAL)\(\d+(?:\s*,\s*\d+)?\)$")
_ZERO_FSP = re.compile(r"^(TIME|DATETIME|TIMESTAMP)\(0+\)$")
_DECIMAL_NORMALIZED = re.compile(r"^DECIMAL\(\s*(\d+)(?:\s*,\s*(\d+))?\s*\)$")
_BIT_NORMALIZED = re.compile(r"^BIT\(\s*(\d+)\s*\)$")


class SqlDeclaredTypeMappingError(ValueError):
    """Raised when a SQL spelling cannot be mapped to a DeclaredType."""


def normalize_sql_type_spelling(spelling: str) -> str:
    """Return the stable catalog spelling used in canonical descriptors."""

    if type(spelling) is not str or spelling.strip() == "":
        raise SqlDeclaredTypeMappingError("SQL type spelling must be non-empty")
    token = _uppercase_and_collapse_outside_quotes(spelling.strip())
    if token.endswith(" ZEROFILL"):
        token = token.removesuffix(" ZEROFILL")
        if not token.endswith(" UNSIGNED"):
            token += " UNSIGNED"
    enum_set_match = re.match(r"^(ENUM|SET)\s*\(", token)
    if enum_set_match is not None:
        kind = enum_set_match.group(1)
        labels = _parse_enum_set_labels(token[enum_set_match.end() :], spelling)
        _validate_enum_set_labels(kind, labels, spelling)
        return f"{kind}({','.join(_quote_sql_label(label) for label in labels)})"
    integer_match = _INTEGER_DISPLAY.fullmatch(token)
    if integer_match is not None:
        base, modifier = integer_match.groups()
        base = "INT" if base == "INTEGER" else base
        return f"{base} UNSIGNED" if modifier in {"UNSIGNED", "ZEROFILL"} else base
    float_match = _FLOAT_DISPLAY.fullmatch(token)
    if float_match is not None:
        base = float_match.group(1)
        return "DOUBLE" if base == "REAL" else base
    zero_fsp_match = _ZERO_FSP.fullmatch(token)
    if zero_fsp_match is not None:
        return zero_fsp_match.group(1)
    decimal_match = _DECIMAL_NORMALIZED.fullmatch(token)
    if decimal_match is not None:
        return f"DECIMAL({decimal_match.group(1)},{decimal_match.group(2) or '0'})"
    bit_match = _BIT_NORMALIZED.fullmatch(token)
    if bit_match is not None:
        return f"BIT({bit_match.group(1)})"
    if token == "INTEGER":
        return "INT"
    if token == "INTEGER UNSIGNED":
        return "INT UNSIGNED"
    return token


def _decimal_args(args: str | None) -> tuple[int, int]:
    if args is None or args.strip() == "":
        return (10, 0)
    parts = [item.strip() for item in args.split(",")]
    if len(parts) == 1:
        if not parts[0]:
            return (10, 0)
        return (int(parts[0]), 0)
    if len(parts) >= 2:
        precision = int(parts[0]) if parts[0] else 10
        scale = int(parts[1]) if parts[1] else 0
        return (precision, scale)
    raise SqlDeclaredTypeMappingError(f"unsupported DECIMAL argument spelling: {args!r}")


def _bit_width(args: str | None) -> int:
    try:
        return int(args or "1")
    except ValueError as exc:
        raise SqlDeclaredTypeMappingError(f"unsupported BIT argument spelling: {args!r}") from exc


def declared_type_for_sql_spelling(spelling: str) -> DeclaredType:
    """Map one SQL column type spelling to the canonical DeclaredType."""

    token = normalize_sql_type_spelling(spelling)
    match = _TYPE_TOKEN.match(token)
    if match is None:
        raise SqlDeclaredTypeMappingError(f"unsupported SQL type spelling: {spelling}")
    base, args, unsigned = match.groups()
    try:
        if base in {"BOOLEAN", "BOOL"}:
            return DeclaredType(kind=DeclaredTypeKind.BOOLEAN)
        if base in _INTEGER_BITS:
            return DeclaredType(
                kind=(
                    DeclaredTypeKind.UNSIGNED_INTEGER
                    if unsigned
                    else DeclaredTypeKind.SIGNED_INTEGER
                ),
                bits=_INTEGER_BITS[base],
            )
        if base == "FLOAT":
            return DeclaredType(kind=DeclaredTypeKind.FLOAT32)
        if base in {"DOUBLE", "REAL"}:
            return DeclaredType(kind=DeclaredTypeKind.FLOAT64)
        if base == "DECIMAL":
            precision, scale = _decimal_args(args)
            return DeclaredType(
                kind=DeclaredTypeKind.DECIMAL,
                precision=precision,
                scale=scale,
            )
        if base == "BIT":
            return DeclaredType(kind=DeclaredTypeKind.BIT, bit_width=_bit_width(args))
        if base == "DATE":
            return DeclaredType(kind=DeclaredTypeKind.DATE)
        if base == "DATETIME":
            return DeclaredType(kind=DeclaredTypeKind.DATETIME)
        if base == "TIMESTAMP":
            return DeclaredType(kind=DeclaredTypeKind.TIMESTAMP)
        if base == "TIME":
            return DeclaredType(kind=DeclaredTypeKind.TIME_DURATION)
        if base in _TEXT_TYPES:
            return DeclaredType(kind=DeclaredTypeKind.STRING)
        if base in _BINARY_TYPES:
            return DeclaredType(kind=DeclaredTypeKind.BINARY)
    except (ValueError, IndexError) as exc:
        raise SqlDeclaredTypeMappingError(
            f"unsupported SQL type spelling: {spelling}"
        ) from exc
    raise SqlDeclaredTypeMappingError(f"unsupported SQL type spelling: {spelling}")


def enum_set_labels_for_sql_spelling(spelling: str) -> tuple[str, tuple[str, ...]] | None:
    normalized = normalize_sql_type_spelling(spelling)
    match = re.match(r"^(ENUM|SET)\(", normalized)
    if match is None:
        if normalized.startswith(("ENUM", "SET")):
            raise SqlDeclaredTypeMappingError(f"malformed ENUM/SET SQL type spelling: {spelling}")
        return None
    kind = match.group(1)
    labels = _parse_enum_set_labels(normalized[match.end() :], spelling)
    _validate_enum_set_labels(kind, labels, spelling)
    return kind, labels


def try_declared_type_for_sql_spelling(spelling: str) -> DeclaredType | None:
    try:
        return declared_type_for_sql_spelling(spelling)
    except SqlDeclaredTypeMappingError:
        return None


def _uppercase_and_collapse_outside_quotes(value: str) -> str:
    output: list[str] = []
    quote: str | None = None
    pending_space = False
    index = 0
    while index < len(value):
        char = value[index]
        if quote is not None:
            output.append(char)
            if char == quote:
                if index + 1 < len(value) and value[index + 1] == quote:
                    output.append(value[index + 1])
                    index += 1
                else:
                    quote = None
        elif char in {"'", '"'}:
            if pending_space and output:
                output.append(" ")
            pending_space = False
            quote = char
            output.append(char)
        elif char.isspace():
            pending_space = True
        else:
            if pending_space and output:
                output.append(" ")
            pending_space = False
            output.append(char.upper())
        index += 1
    return "".join(output).strip()


def _parse_enum_set_labels(body: str, spelling: str) -> tuple[str, ...]:
    labels: list[str] = []
    cursor = 0
    while True:
        while cursor < len(body) and body[cursor].isspace():
            cursor += 1
        if cursor >= len(body):
            raise SqlDeclaredTypeMappingError(f"malformed ENUM/SET SQL type spelling: {spelling}")
        if body[cursor] == ")":
            if labels or cursor != len(body) - 1:
                raise SqlDeclaredTypeMappingError(f"malformed ENUM/SET SQL type spelling: {spelling}")
            break
        if body[cursor] != "'":
            raise SqlDeclaredTypeMappingError(f"malformed ENUM/SET SQL type spelling: {spelling}")
        cursor += 1
        label: list[str] = []
        while cursor < len(body):
            char = body[cursor]
            if char == "'":
                if cursor + 1 < len(body) and body[cursor + 1] == "'":
                    label.append("'")
                    cursor += 2
                    continue
                cursor += 1
                break
            label.append(char)
            cursor += 1
        else:
            raise SqlDeclaredTypeMappingError(f"malformed ENUM/SET SQL type spelling: {spelling}")
        labels.append("".join(label))
        while cursor < len(body) and body[cursor].isspace():
            cursor += 1
        if cursor < len(body) and body[cursor] == ",":
            cursor += 1
            continue
        if cursor < len(body) and body[cursor] == ")" and cursor == len(body) - 1:
            break
        raise SqlDeclaredTypeMappingError(f"malformed ENUM/SET SQL type spelling: {spelling}")
    if not labels:
        raise SqlDeclaredTypeMappingError(f"malformed ENUM/SET SQL type spelling: {spelling}")
    return tuple(labels)


def _validate_enum_set_labels(kind: str, labels: tuple[str, ...], spelling: str) -> None:
    if kind == "SET" and (
        any(label == "" or "," in label for label in labels) or len(labels) > 64
    ):
        raise SqlDeclaredTypeMappingError(f"malformed SET SQL type spelling: {spelling}")
    if kind == "ENUM" and len(labels) > 65535:
        raise SqlDeclaredTypeMappingError(f"malformed ENUM SQL type spelling: {spelling}")
    if any(len(label) > 255 for label in labels):
        raise SqlDeclaredTypeMappingError(f"malformed ENUM/SET SQL type spelling: {spelling}")
    if len(labels) != len(set(labels)):
        raise SqlDeclaredTypeMappingError("ENUM/SET labels must not repeat")


def _quote_sql_label(label: str) -> str:
    return "'" + label.replace("'", "''") + "'"
