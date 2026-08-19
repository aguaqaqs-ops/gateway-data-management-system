"""SQL dump literals mapped to Shared Kernel typed scalars."""

from __future__ import annotations

import json
from dataclasses import dataclass

from gateway_shared_kernel import (
    CanonicalEncodingError,
    DeclaredTypeKind,
    NullScalar,
    RawLogicalLiteral,
    Utf8LogicalLiteral,
    normalize_logical_literal,
)

from gateway_backend.capabilities.table_access._parser_runtime import ParserRuntime
from gateway_backend.capabilities.table_access._sql_scan import ByteCursor, is_digit, is_hex
from gateway_backend.capabilities.table_access.contracts import (
    SourceCell,
    SourceColumnDescriptor,
    SqlLogicalType,
    SqlSetValue,
    ParserDiagnosticCode,
)

_STRING_ESCAPES = {
    ord("\\"): b"\\",
    ord("'"): b"'",
    ord('"'): b'"',
    ord("n"): b"\n",
    ord("r"): b"\r",
    ord("t"): b"\t",
    ord("0"): b"\x00",
    ord("Z"): b"\x1a",
    ord("b"): b"\b",
}


@dataclass(frozen=True, slots=True)
class SqlLiteral:
    is_null: bool = False
    text: str | None = None
    raw: bytes | None = None
    is_number: bool = False


class LiteralError(Exception):
    def __init__(self, code: ParserDiagnosticCode, message: str, byte_offset: int) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.byte_offset = byte_offset


def parse_literal(cursor: ByteCursor, runtime: ParserRuntime) -> SqlLiteral:
    cursor.skip_ws_and_comments(runtime)
    start = cursor.pos
    byte = cursor.peek()
    if byte is None:
        raise LiteralError(ParserDiagnosticCode.MALFORMED_SQL, "expected literal", start)
    if _try_keyword_literal(cursor, runtime, "null"):
        return SqlLiteral(is_null=True)
    if _try_keyword_literal(cursor, runtime, "true"):
        return SqlLiteral(text="true")
    if _try_keyword_literal(cursor, runtime, "false"):
        return SqlLiteral(text="false")
    if _try_keyword_literal(cursor, runtime, "default"):
        raise LiteralError(
            ParserDiagnosticCode.INCOMPLETE_INSERT,
            "DEFAULT in VALUES is not derived by the source dump parser",
            start,
        )
    if byte == ord("'") or byte in {ord("x"), ord("X"), ord("b"), ord("B")} or (
        byte == ord("0") and _hex_or_bit_prefix(cursor)
    ):
        return _parse_quoted_or_prefixed(cursor, runtime)
    if byte in {ord("+"), ord("-")} or is_digit(byte) or byte == ord("."):
        return _parse_number(cursor, runtime)
    raise LiteralError(
        ParserDiagnosticCode.MALFORMED_SQL,
        "unsupported SQL value expression",
        start,
    )


def literal_to_cell(
    literal: SqlLiteral,
    column: SourceColumnDescriptor,
    runtime: ParserRuntime,
    byte_offset: int,
) -> SourceCell:
    if literal.is_null:
        if not column.nullable:
            raise LiteralError(
                ParserDiagnosticCode.SQL_VALUE_ILLEGAL,
                "NULL is not allowed for a NOT NULL column",
                byte_offset,
            )
        return NullScalar()
    if column.logical_type is SqlLogicalType.UNKNOWN or column.declared_type is None:
        if column.logical_type is SqlLogicalType.SET:
            return _set_value(literal, column, byte_offset)
        raise LiteralError(
            ParserDiagnosticCode.SQL_VALUE_ILLEGAL,
            "value supplied for a non-ready column",
            byte_offset,
        )
    if column.logical_type is SqlLogicalType.ENUM:
        return _enum_value(literal, column, byte_offset)
    if column.logical_type is SqlLogicalType.JSON:
        text = _require_text(literal, byte_offset)
        try:
            json.loads(text)
        except (TypeError, ValueError) as exc:
            raise LiteralError(
                ParserDiagnosticCode.SQL_VALUE_ILLEGAL,
                "JSON value is not well-formed",
                byte_offset,
            ) from exc
        return _normalize_text(column, text, byte_offset)
    declared = column.declared_type
    if declared.kind is DeclaredTypeKind.BINARY:
        raw = _require_bytes(literal, byte_offset)
        _check_field_bytes(raw, runtime, byte_offset)
        try:
            return normalize_logical_literal(declared, RawLogicalLiteral(raw_bytes=raw)).typed_value
        except CanonicalEncodingError as exc:
            raise LiteralError(
                ParserDiagnosticCode.SQL_VALUE_ILLEGAL, str(exc), byte_offset
            ) from exc
    if declared.kind is DeclaredTypeKind.BIT:
        raw = _bit_bytes(literal, declared.bit_width or 1, byte_offset)
        _check_field_bytes(raw, runtime, byte_offset)
        try:
            return normalize_logical_literal(declared, RawLogicalLiteral(raw_bytes=raw)).typed_value
        except CanonicalEncodingError as exc:
            raise LiteralError(
                ParserDiagnosticCode.SQL_VALUE_ILLEGAL, str(exc), byte_offset
            ) from exc
    text = _logical_text(literal, declared.kind, byte_offset)
    _check_field_bytes(text.encode("utf-8"), runtime, byte_offset)
    return _normalize_text(column, text, byte_offset)


def _normalize_text(
    column: SourceColumnDescriptor, text: str, byte_offset: int
) -> SourceCell:
    declared = column.declared_type
    if declared is None:
        raise LiteralError(
            ParserDiagnosticCode.SQL_VALUE_ILLEGAL,
            "value supplied for a non-ready column",
            byte_offset,
        )
    try:
        return normalize_logical_literal(declared, Utf8LogicalLiteral(text=text)).typed_value
    except CanonicalEncodingError as exc:
        raise LiteralError(ParserDiagnosticCode.SQL_VALUE_ILLEGAL, str(exc), byte_offset) from exc


def _enum_value(
    literal: SqlLiteral, column: SourceColumnDescriptor, byte_offset: int
) -> SourceCell:
    text = _require_text(literal, byte_offset)
    labels = column.enum_or_set_labels or ()
    if text not in labels:
        raise LiteralError(
            ParserDiagnosticCode.SQL_VALUE_ILLEGAL,
            "ENUM value is not a declared label",
            byte_offset,
        )
    return _normalize_text(column, text, byte_offset)


def _set_value(
    literal: SqlLiteral, column: SourceColumnDescriptor, byte_offset: int
) -> SqlSetValue:
    text = _require_text(literal, byte_offset)
    labels = column.enum_or_set_labels or ()
    label_set = set(labels)
    if text == "":
        return SqlSetValue(())
    members = text.split(",")
    seen: set[str] = set()
    for member in members:
        if member not in label_set:
            raise LiteralError(
                ParserDiagnosticCode.SQL_VALUE_ILLEGAL,
                "SET value contains an undeclared or empty member",
                byte_offset,
            )
        if member in seen:
            raise LiteralError(
                ParserDiagnosticCode.SQL_VALUE_ILLEGAL,
                "SET value contains duplicate members",
                byte_offset,
            )
        seen.add(member)
    return SqlSetValue(tuple(label for label in labels if label in seen))


def _logical_text(literal: SqlLiteral, kind: DeclaredTypeKind, byte_offset: int) -> str:
    text = _require_text(literal, byte_offset)
    if kind is DeclaredTypeKind.DATETIME:
        return _sql_datetime_to_canonical(text, timestamp=False)
    if kind is DeclaredTypeKind.TIMESTAMP:
        return _sql_datetime_to_canonical(text, timestamp=True)
    return text


def _sql_datetime_to_canonical(text: str, *, timestamp: bool) -> str:
    converted = text.strip()
    if " " in converted and "T" not in converted:
        converted = converted.replace(" ", "T", 1)
    if timestamp and not converted.endswith("Z"):
        converted = f"{converted}Z"
    return converted


def _require_text(literal: SqlLiteral, byte_offset: int) -> str:
    if literal.text is not None:
        return literal.text
    if literal.raw is not None:
        try:
            return literal.raw.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise LiteralError(
                ParserDiagnosticCode.SQL_VALUE_ILLEGAL,
                "binary literal is not UTF-8 text",
                byte_offset,
            ) from exc
    raise LiteralError(ParserDiagnosticCode.SQL_VALUE_ILLEGAL, "expected a text literal", byte_offset)


def _require_bytes(literal: SqlLiteral, byte_offset: int) -> bytes:
    if literal.raw is not None:
        return literal.raw
    if literal.text is not None:
        return literal.text.encode("utf-8")
    raise LiteralError(
        ParserDiagnosticCode.SQL_VALUE_ILLEGAL, "expected a binary literal", byte_offset
    )


def _bit_bytes(literal: SqlLiteral, bit_width: int, byte_offset: int) -> bytes:
    expected = (bit_width + 7) // 8
    if literal.raw is not None and not literal.is_number:
        raw = literal.raw
        if len(raw) == expected:
            return raw
        value = int.from_bytes(raw, "big")
        return value.to_bytes(expected, "big")
    text = _require_text(literal, byte_offset)
    if all(ch in "01" for ch in text) and text != "":
        value = int(text, 2)
    else:
        try:
            value = int(text, 10)
        except ValueError as exc:
            raise LiteralError(
                ParserDiagnosticCode.SQL_VALUE_ILLEGAL,
                "BIT literal is not convertible",
                byte_offset,
            ) from exc
    return value.to_bytes(expected, "big")


def _check_field_bytes(payload: bytes, runtime: ParserRuntime, byte_offset: int) -> None:
    if len(payload) > runtime.budgets.max_field_bytes:
        runtime.resource_exceeded("max_field_bytes", byte_offset)


def _try_keyword_literal(cursor: ByteCursor, runtime: ParserRuntime, keyword: str) -> bool:
    saved = cursor.pos
    if cursor.try_keyword(keyword, runtime):
        return True
    cursor.pos = saved
    return False


def _hex_or_bit_prefix(cursor: ByteCursor) -> bool:
    if cursor.pos + 1 >= cursor.end:
        return False
    nxt = cursor.data[cursor.pos + 1]
    return nxt in {ord("x"), ord("X"), ord("b"), ord("B")}


def _parse_number(cursor: ByteCursor, runtime: ParserRuntime) -> SqlLiteral:
    start = cursor.pos
    if cursor.peek() in {ord("+"), ord("-")}:
        cursor.pos += 1
    digits = 0
    while cursor.peek() is not None and is_digit(cursor.peek() or 0):
        digits += 1
        cursor.pos += 1
    if cursor.peek() == ord("."):
        cursor.pos += 1
        while cursor.peek() is not None and is_digit(cursor.peek() or 0):
            digits += 1
            cursor.pos += 1
    if cursor.peek() in {ord("e"), ord("E")}:
        cursor.pos += 1
        if cursor.peek() in {ord("+"), ord("-")}:
            cursor.pos += 1
        exp = 0
        while cursor.peek() is not None and is_digit(cursor.peek() or 0):
            exp += 1
            cursor.pos += 1
        if exp == 0:
            raise LiteralError(
                ParserDiagnosticCode.MALFORMED_SQL, "malformed numeric literal", start
            )
    if digits == 0:
        raise LiteralError(ParserDiagnosticCode.MALFORMED_SQL, "malformed numeric literal", start)
    runtime.checkpoint(cursor.pos)
    text = cursor.data[start:cursor.pos].decode("ascii")
    return SqlLiteral(text=text, is_number=True)


def _parse_quoted_or_prefixed(cursor: ByteCursor, runtime: ParserRuntime) -> SqlLiteral:
    start = cursor.pos
    byte = cursor.peek()
    if byte in {ord("x"), ord("X")} and cursor.pos + 1 < cursor.end and cursor.data[cursor.pos + 1] == ord("'"):
        cursor.pos += 1
        body = _parse_quoted_bytes(cursor, runtime, hex_mode=True)
        return SqlLiteral(raw=body)
    if byte == ord("0") and cursor.pos + 1 < cursor.end and cursor.data[cursor.pos + 1] in {
        ord("x"),
        ord("X"),
    }:
        cursor.pos += 2
        hex_start = cursor.pos
        while cursor.peek() is not None and is_hex(cursor.peek() or 0):
            cursor.pos += 1
        if cursor.pos == hex_start:
            raise LiteralError(ParserDiagnosticCode.MALFORMED_SQL, "malformed hex literal", start)
        hex_text = cursor.data[hex_start:cursor.pos].decode("ascii")
        if len(hex_text) % 2 == 1:
            hex_text = f"0{hex_text}"
        return SqlLiteral(raw=bytes.fromhex(hex_text))
    if byte in {ord("b"), ord("B")} and cursor.pos + 1 < cursor.end and cursor.data[cursor.pos + 1] == ord("'"):
        cursor.pos += 1
        body = _parse_quoted_bytes(cursor, runtime, hex_mode=False)
        bits = body.decode("ascii")
        if bits and not all(ch in "01" for ch in bits):
            raise LiteralError(ParserDiagnosticCode.MALFORMED_SQL, "malformed bit literal", start)
        return SqlLiteral(text=bits, raw=_bit_string_to_bytes(bits))
    if byte == ord("0") and cursor.pos + 1 < cursor.end and cursor.data[cursor.pos + 1] in {
        ord("b"),
        ord("B"),
    }:
        cursor.pos += 2
        bit_start = cursor.pos
        while cursor.peek() in {ord("0"), ord("1")}:
            cursor.pos += 1
        if cursor.pos == bit_start:
            raise LiteralError(ParserDiagnosticCode.MALFORMED_SQL, "malformed bit literal", start)
        bits = cursor.data[bit_start:cursor.pos].decode("ascii")
        return SqlLiteral(text=bits, raw=_bit_string_to_bytes(bits))
    if byte == ord("'"):
        raw = _parse_quoted_bytes(cursor, runtime, hex_mode=False)
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise LiteralError(
                ParserDiagnosticCode.SQL_VALUE_ILLEGAL,
                "string literal is not strict UTF-8",
                start,
            ) from exc
        return SqlLiteral(text=text, raw=raw)
    raise LiteralError(ParserDiagnosticCode.MALFORMED_SQL, "expected literal", start)


def _parse_quoted_bytes(cursor: ByteCursor, runtime: ParserRuntime, *, hex_mode: bool) -> bytes:
    start = cursor.pos
    if cursor.peek() != ord("'"):
        raise LiteralError(ParserDiagnosticCode.MALFORMED_SQL, "expected quoted literal", start)
    cursor.pos += 1
    chunks: list[bytes] = []
    while cursor.pos < cursor.end:
        runtime.checkpoint(cursor.pos)
        byte = cursor.data[cursor.pos]
        if byte == ord("'"):
            nxt = cursor.pos + 1
            if nxt < cursor.end and cursor.data[nxt] == ord("'"):
                chunks.append(b"'")
                cursor.pos += 2
                continue
            cursor.pos += 1
            raw = b"".join(chunks)
            if hex_mode:
                try:
                    text = raw.decode("ascii")
                except UnicodeDecodeError as exc:
                    raise LiteralError(
                        ParserDiagnosticCode.MALFORMED_SQL, "hex literal is not ASCII", start
                    ) from exc
                if len(text) % 2 == 1:
                    text = f"0{text}"
                try:
                    return bytes.fromhex(text)
                except ValueError as exc:
                    raise LiteralError(
                        ParserDiagnosticCode.MALFORMED_SQL, "malformed hex literal", start
                    ) from exc
            return raw
        if byte == ord("\\") and not hex_mode:
            cursor.pos += 1
            if cursor.pos >= cursor.end:
                raise LiteralError(ParserDiagnosticCode.MALFORMED_SQL, "unclosed string", start)
            esc = cursor.data[cursor.pos]
            chunks.append(_STRING_ESCAPES.get(esc, bytes([esc])))
            cursor.pos += 1
            continue
        chunks.append(bytes([byte]))
        cursor.pos += 1
    raise LiteralError(ParserDiagnosticCode.MALFORMED_SQL, "unclosed string", start)


def _bit_string_to_bytes(bits: str) -> bytes:
    if bits == "":
        return b"\x00"
    value = int(bits, 2)
    length = max(1, (len(bits) + 7) // 8)
    return value.to_bytes(length, "big")
