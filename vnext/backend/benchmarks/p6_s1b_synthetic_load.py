"""Build private synthetic 2x-t4 and W4 SQL inputs for Phase 6 measurements.

The generated SQL contains copied source data and must stay in a protected
scratch directory. The command output contains only table names and row counts.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import re
from collections.abc import Callable, Iterable, Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from gateway_shared_kernel import DigestRef, DeclaredTypeKind
from gateway_shared_kernel.types import (
    BinaryScalar,
    BitScalar,
    BooleanScalar,
    DateScalar,
    DateTimeScalar,
    DecimalScalar,
    Float32Scalar,
    Float64Scalar,
    NullScalar,
    SignedIntegerScalar,
    StringScalar,
    TimeDurationScalar,
    TimestampScalar,
    UnsignedIntegerScalar,
)

from gateway_backend.capabilities.table_access._parser_runtime import ParserRuntime
from gateway_backend.capabilities.table_access._sql_scan import (
    ByteCursor,
    SqlStatementSpan,
    iter_statements,
)
from gateway_backend.capabilities.table_access._sql_statements import (
    TableBuild,
    _parse_insert_columns,
    _split_top_level,
    classify_statement,
)
from gateway_backend.capabilities.table_access._sql_values import parse_literal
from gateway_backend.capabilities.table_access.contracts import (
    NeverCancel,
    ParseStatus,
    ParserInvocationContext,
    SqlSourceInput,
    SourceColumnDescriptor,
    SourceRow,
    SourceTableDescriptor,
    SqlLogicalType,
    SqlSetValue,
    SqlParseRequest,
)
from gateway_backend.capabilities.table_access.sql import parse_sql
from gateway_backend.capabilities.table_rules import (
    migrated_table_ruleset_snapshot,
    resolve_table_rule,
)

_RENAME_HEADS = re.compile(
    rb"(?m)^(CREATE TABLE (?:IF NOT EXISTS )?|INSERT INTO |DROP TABLE IF EXISTS |"
    rb"/\*!\d+ ALTER TABLE )`((?:``|[^`])+)`"
)
_LOCK_LINE = re.compile(rb"(?m)^LOCK TABLES .*?;$")
_BACKTICKED_IDENTIFIER = re.compile(rb"`((?:``|[^`])+)`")
_LENGTH = re.compile(r"\b(?:VAR)?CHAR\s*\(\s*(\d+)\s*\)", re.IGNORECASE)
_BINARY_TYPE = re.compile(r"\b(?:BINARY|VARBINARY|BLOB)\b", re.IGNORECASE)
_BASE62 = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
_MAX_IDENTIFIER_BYTES = 64


@dataclass(frozen=True, slots=True)
class CellSpan:
    start: int
    end: int


@dataclass(frozen=True, slots=True)
class RowTuple:
    table_name: str
    row_index: int
    statement: SqlStatementSpan
    start: int
    end: int
    cells: tuple[CellSpan, ...]
    values: SourceRow


@dataclass(frozen=True, slots=True)
class InsertStatement:
    table_name: str
    span: SqlStatementSpan
    rows: tuple[RowTuple, ...]


@dataclass(frozen=True, slots=True)
class ParsedInput:
    raw: bytes
    descriptors: dict[str, SourceTableDescriptor]
    rows: dict[str, tuple[SourceRow, ...]]
    statements: tuple[InsertStatement, ...]
    rows_by_table: dict[str, tuple[RowTuple, ...]]


def _runtime() -> ParserRuntime:
    return ParserRuntime(ParserInvocationContext(NeverCancel()))


def _parse_request(raw: bytes) -> SqlParseRequest:
    return SqlParseRequest(
        source=SqlSourceInput(
            document_content_digest=DigestRef("sha256:" + "00" * 32),
            sql_source_digest=DigestRef("sha256:" + "00" * 32),
            parser_input_contract_version=1,
            encoding="utf-8",
            source_size_bytes=len(raw),
        ),
        sql_utf8=raw,
        context=ParserInvocationContext(NeverCancel()),
    )


def _parse_input(raw: bytes) -> ParsedInput:
    parsed = parse_sql(_parse_request(raw))
    if parsed.status is not ParseStatus.COMPLETE:
        codes = ",".join(item.code.value for item in parsed.diagnostics)
        raise ValueError(f"source SQL is not complete ({codes})")
    descriptors: dict[str, SourceTableDescriptor] = {}
    rows: dict[str, tuple[SourceRow, ...]] = {}
    for table in parsed.tables:
        descriptor = table.descriptor
        if table.reader is None:
            raise ValueError(f"table {descriptor.canonical_name} has no readable rows")
        descriptors[descriptor.canonical_name] = descriptor
        rows[descriptor.canonical_name] = tuple(table.reader.iter_rows())

    runtime = _runtime()
    table_row_indexes = {name: 0 for name in descriptors}
    statements: list[InsertStatement] = []
    grouped: dict[str, list[RowTuple]] = {name: [] for name in descriptors}
    for span in iter_statements(raw, runtime):
        cursor = ByteCursor(raw, span.start, span.end)
        if classify_statement(cursor, runtime) != "insert":
            continue
        if not cursor.try_keyword("insert", runtime):
            raise AssertionError("statement classifier lost INSERT")
        cursor.try_keyword("ignore", runtime)
        if not cursor.try_keyword("into", runtime):
            raise ValueError("unsupported INSERT shape")
        _display, table_name = cursor.parse_table_name(runtime)
        descriptor = descriptors.get(table_name)
        if descriptor is None:
            raise ValueError(f"INSERT table {table_name} has no CREATE TABLE")
        build = TableBuild(
            display_name=descriptor.display_name,
            canonical_name=descriptor.canonical_name,
            columns=list(descriptor.columns),
            pk=list(descriptor.primary_key_canonical_names),
        )
        cursor.skip_ws_and_comments(runtime)
        ordinals = (
            _parse_insert_columns(cursor, runtime, build)
            if cursor.peek() == ord("(")
            else tuple(range(len(descriptor.columns)))
        )
        if not cursor.try_keyword("values", runtime):
            raise ValueError(f"INSERT table {table_name} has no VALUES clause")
        statement_rows: list[RowTuple] = []
        while True:
            cursor.skip_ws_and_comments(runtime)
            if cursor.peek() != ord("("):
                break
            tuple_start, tuple_end = cursor.take_balanced_paren(runtime)
            parts = _split_top_level(raw, tuple_start + 1, tuple_end - 1, runtime)
            if len(parts) != len(ordinals):
                raise ValueError(f"INSERT table {table_name} has a row width mismatch")
            row_index = table_row_indexes[table_name]
            if row_index >= len(rows[table_name]):
                raise ValueError(f"INSERT table {table_name} has more rows than parsed")
            values = rows[table_name][row_index]
            cell_spans: list[CellSpan | None] = [None] * len(descriptor.columns)
            for value_index, (part_start, part_end) in enumerate(parts):
                cell_cursor = ByteCursor(raw, part_start, part_end)
                cell_cursor.skip_ws_and_comments(runtime)
                value_start = cell_cursor.pos
                parse_literal(cell_cursor, runtime)
                value_end = cell_cursor.pos
                column_index = ordinals[value_index]
                cell_spans[column_index] = CellSpan(value_start, value_end)
            if any(item is None for item in cell_spans):
                raise ValueError(f"INSERT table {table_name} does not cover every column")
            row_tuple = RowTuple(
                table_name=table_name,
                row_index=row_index,
                statement=span,
                start=tuple_start,
                end=tuple_end,
                cells=tuple(item for item in cell_spans if item is not None),
                values=values,
            )
            statement_rows.append(row_tuple)
            grouped[table_name].append(row_tuple)
            table_row_indexes[table_name] += 1
        statements.append(InsertStatement(table_name, span, tuple(statement_rows)))
    for table_name, table_rows in rows.items():
        if table_row_indexes[table_name] != len(table_rows):
            raise ValueError(f"INSERT rows for table {table_name} could not be located")
    return ParsedInput(
        raw=raw,
        descriptors=descriptors,
        rows=rows,
        statements=tuple(statements),
        rows_by_table={name: tuple(items) for name, items in grouped.items()},
    )


def _protected_columns(descriptor: SourceTableDescriptor) -> tuple[str, ...]:
    snapshot = migrated_table_ruleset_snapshot()
    resolved = resolve_table_rule(
        snapshot,
        descriptor.canonical_name,
        primary_key_columns=descriptor.primary_key_canonical_names,
    )
    record = resolved.record
    key_columns = resolved.decision.compare_key_columns or descriptor.primary_key_canonical_names
    return tuple(
        dict.fromkeys(
            (
                *descriptor.primary_key_canonical_names,
                *key_columns,
                *record.stable_key_candidates,
                *record.structural_columns,
                *((record.position_column,) if record.position_column is not None else ()),
            )
        )
    )


def _mutator_for(
    descriptor: SourceTableDescriptor,
    rows: tuple[SourceRow, ...],
) -> tuple[int, Callable[[object], bytes]] | None:
    protected = set(_protected_columns(descriptor))
    for index, column in enumerate(descriptor.columns):
        if column.canonical_name in protected:
            continue
        mutator = _cell_mutator(column, tuple(row[index] for row in rows))
        if mutator is not None:
            return index, mutator
    return None


def _cell_mutator(
    column: SourceColumnDescriptor,
    cells: tuple[object, ...],
) -> Callable[[object], bytes] | None:
    if column.logical_type is SqlLogicalType.ENUM and len(column.enum_or_set_labels or ()) > 1:
        labels = column.enum_or_set_labels or ()
        if all(isinstance(cell, (StringScalar, NullScalar)) for cell in cells):
            def mutate_enum(cell: object) -> bytes:
                current = cell.text if isinstance(cell, StringScalar) else None
                selected = next((label for label in labels if label != current), labels[0])
                return _sql_string_literal(selected)

            return mutate_enum
    if column.logical_type is SqlLogicalType.SET and column.enum_or_set_labels:
        labels = column.enum_or_set_labels
        if all(isinstance(cell, (SqlSetValue, NullScalar)) for cell in cells):
            def mutate_set(cell: object) -> bytes:
                current = cell.members if isinstance(cell, SqlSetValue) else ()
                selected = () if current else labels
                return _sql_string_literal(",".join(selected))

            return mutate_set
    if column.logical_type is SqlLogicalType.JSON and all(
        isinstance(cell, (StringScalar, NullScalar)) for cell in cells
    ):
        def mutate_json(cell: object) -> bytes:
            if isinstance(cell, NullScalar):
                return _sql_string_literal("false")
            value = json.loads(cell.text)
            return _sql_string_literal("false" if value is None else "null")

        return mutate_json
    if column.logical_type is SqlLogicalType.STANDARD and column.declared_type is not None:
        kind = column.declared_type.kind
        if kind is DeclaredTypeKind.STRING and not column.enum_or_set_labels:
            length = _LENGTH.search(column.sql_type)
            if length is None or int(length.group(1)) >= 1:
                if all(isinstance(cell, (StringScalar, NullScalar)) for cell in cells):
                    return lambda cell: (
                        _sql_string_literal("x")
                        if isinstance(cell, NullScalar)
                        or isinstance(cell, StringScalar) and cell.text == ""
                        else b"''"
                    )
        if kind in {DeclaredTypeKind.SIGNED_INTEGER, DeclaredTypeKind.UNSIGNED_INTEGER}:
            if all(
                isinstance(cell, (SignedIntegerScalar, UnsignedIntegerScalar, NullScalar))
                for cell in cells
            ):
                return lambda cell: (
                    b"1"
                    if isinstance(cell, NullScalar) or int(cell.decimal) == 0
                    else b"0"
                )
        if kind is DeclaredTypeKind.BOOLEAN and all(
            isinstance(cell, (BooleanScalar, NullScalar)) for cell in cells
        ):
            return lambda cell: (
                b"TRUE" if isinstance(cell, NullScalar) or not cell.value else b"FALSE"
            )
        if kind is DeclaredTypeKind.DECIMAL and all(
            isinstance(cell, (DecimalScalar, NullScalar)) for cell in cells
        ):
            scale = column.declared_type.scale or 0
            one = b"0." + b"0" * (scale - 1) + b"1" if scale > 0 else b"1"
            return lambda cell: one if isinstance(cell, NullScalar) or cell.decimal == "0" else b"0"
        if kind is DeclaredTypeKind.FLOAT32 and all(
            isinstance(cell, (Float32Scalar, NullScalar)) for cell in cells
        ):
            return lambda cell: b"1" if isinstance(cell, NullScalar) or cell.bits_hex == "00000000" else b"0"
        if kind is DeclaredTypeKind.FLOAT64 and all(
            isinstance(cell, (Float64Scalar, NullScalar)) for cell in cells
        ):
            return lambda cell: b"1" if isinstance(cell, NullScalar) or cell.bits_hex == "0000000000000000" else b"0"
        if kind is DeclaredTypeKind.BIT and all(
            isinstance(cell, (BitScalar, NullScalar)) for cell in cells
        ):
            return lambda cell: b"1" if isinstance(cell, NullScalar) or not any(cell.raw_bytes) else b"0"
        if kind is DeclaredTypeKind.BINARY and _BINARY_TYPE.search(column.sql_type):
            if all(isinstance(cell, (BinaryScalar, NullScalar)) for cell in cells):
                return lambda cell: b"x'00'" if isinstance(cell, NullScalar) or not cell.raw_bytes else b"x''"
        if kind is DeclaredTypeKind.DATE and all(
            isinstance(cell, (DateScalar, NullScalar)) for cell in cells
        ):
            return lambda cell: (
                b"'2000-01-01'"
                if isinstance(cell, NullScalar) or cell.text != "2000-01-01"
                else b"'2000-01-02'"
            )
        if kind in {DeclaredTypeKind.DATETIME, DeclaredTypeKind.TIMESTAMP} and all(
            isinstance(cell, (DateTimeScalar, TimestampScalar, NullScalar))
            for cell in cells
        ):
            return lambda cell: (
                b"'2000-01-02 00:00:00'"
                if isinstance(cell, NullScalar) or not cell.text.startswith("2000-01-02T")
                else b"'2000-01-01 00:00:00'"
            )
        if kind is DeclaredTypeKind.TIME_DURATION and all(
            isinstance(cell, (TimeDurationScalar, NullScalar)) for cell in cells
        ):
            return lambda cell: (
                b"'00:00:01'"
                if isinstance(cell, NullScalar) or cell.text != "00:00:01"
                else b"'00:00:02'"
            )
    return None


def _sql_string_literal(value: str) -> bytes:
    escaped = value.encode("utf-8").replace(b"\\", b"\\\\").replace(b"'", b"\\'")
    return b"'" + escaped + b"'"


def _replace_cells(raw: bytes, row: RowTuple, replacements: dict[int, bytes]) -> bytes:
    base = row.start
    out = bytearray(raw[row.start : row.end])
    for index, value in sorted(replacements.items(), key=lambda item: row.cells[item[0]].start, reverse=True):
        span = row.cells[index]
        out[span.start - base : span.end - base] = value
    return bytes(out)


def _apply_statement_rows(
    raw: bytes,
    statement: InsertStatement,
    *,
    replacements_by_row: dict[int, dict[int, bytes]],
    deleted_rows: set[int] | None = None,
    appended_rows: dict[int, tuple[bytes, ...]] | None = None,
) -> bytes:
    deleted = deleted_rows or set()
    appended = appended_rows or {}
    if not statement.rows:
        return raw[statement.span.start : statement.span.end]
    emitted: list[bytes] = []
    for row in statement.rows:
        if row.row_index in deleted:
            continue
        emitted.append(_replace_cells(raw, row, replacements_by_row.get(row.row_index, {})))
        emitted.extend(appended.get(row.row_index, ()))
    if not emitted:
        return b""
    first = statement.rows[0]
    last = statement.rows[-1]
    prefix = raw[statement.span.start : first.start]
    suffix = raw[last.end : statement.span.end]
    return prefix + b",\n".join(emitted) + suffix


def _rewrite_input(
    parsed: ParsedInput,
    *,
    replacements_by_table: dict[str, dict[int, dict[int, bytes]]],
    deleted_by_table: dict[str, set[int]] | None = None,
    appended_by_table: dict[str, dict[int, tuple[bytes, ...]]] | None = None,
    append_empty_tables: dict[str, bytes] | None = None,
) -> bytes:
    deleted = deleted_by_table or {}
    appended = appended_by_table or {}
    pieces: list[bytes] = []
    offset = 0
    for statement in parsed.statements:
        pieces.append(parsed.raw[offset : statement.span.start])
        pieces.append(
            _apply_statement_rows(
                parsed.raw,
                statement,
                replacements_by_row=replacements_by_table.get(statement.table_name, {}),
                deleted_rows=deleted.get(statement.table_name),
                appended_rows=appended.get(statement.table_name),
            )
        )
        offset = statement.span.end
    pieces.append(parsed.raw[offset:])
    output = b"".join(pieces)
    extras = append_empty_tables or {}
    if extras:
        if output and not output.endswith(b"\n"):
            output += b"\n"
        output += b"\n".join(extras.values()) + b"\n"
    return output


def _renamed_second_copy(raw: bytes, descriptors: dict[str, SourceTableDescriptor], suffix: str) -> bytes:
    if len(suffix.encode("utf-8")) > _MAX_IDENTIFIER_BYTES:
        raise ValueError("table-name suffix exceeds the identifier byte limit")
    names: dict[str, str] = {}
    renamed: set[str] = set()
    for table_name, descriptor in descriptors.items():
        candidate = descriptor.display_name + suffix
        if len(candidate.encode("utf-8")) > _MAX_IDENTIFIER_BYTES:
            stem = descriptor.display_name
            while len((stem + suffix).encode("utf-8")) > _MAX_IDENTIFIER_BYTES:
                stem = stem[:-1]
            candidate = stem + suffix
        canonical = candidate.lower()
        if canonical in renamed:
            raise ValueError("table-name suffix produces a collision")
        renamed.add(canonical)
        names[descriptor.display_name] = candidate

    def replace(match: re.Match[bytes]) -> bytes:
        old = match.group(2).replace(b"``", b"`").decode("utf-8")
        new = names.get(old)
        if new is None:
            return match.group(0)
        return match.group(1) + b"`" + new.replace("`", "``").encode("utf-8") + b"`"

    result, count = _RENAME_HEADS.subn(replace, raw)
    reverse_names = {old: new for old, new in names.items()}

    def replace_lock(match: re.Match[bytes]) -> bytes:
        def replace_identifier(identifier_match: re.Match[bytes]) -> bytes:
            old = identifier_match.group(1).replace(b"``", b"`").decode("utf-8")
            new = reverse_names.get(old)
            if new is None:
                return identifier_match.group(0)
            return b"`" + new.replace("`", "``").encode("utf-8") + b"`"

        return _BACKTICKED_IDENTIFIER.sub(replace_identifier, match.group(0))

    result = _LOCK_LINE.sub(replace_lock, result)
    if count < len(descriptors):
        raise ValueError("not all table names could be renamed")
    return result


def make_2x(source: Path, output: Path, suffix: str) -> dict[str, Any]:
    original = source.read_bytes()
    parsed = _parse_input(original)
    perturbations: dict[str, dict[int, dict[int, bytes]]] = {}
    changed_rows = 0
    changed_tables = 0
    empty_tables = 0
    for table_name, descriptor in parsed.descriptors.items():
        rows = parsed.rows[table_name]
        if not rows:
            empty_tables += 1
            continue
        chosen = _mutator_for(descriptor, rows)
        if chosen is None:
            raise ValueError(f"table {table_name} has no safe non-key field to perturb")
        column_index, mutate = chosen
        row_changes = {
            row_index: {column_index: mutate(row[column_index])}
            for row_index, row in enumerate(rows)
        }
        perturbations[table_name] = row_changes
        changed_rows += len(rows)
        changed_tables += 1
    second = _rewrite_input(parsed, replacements_by_table=perturbations)
    second = _renamed_second_copy(second, parsed.descriptors, suffix)
    joined = original + (b"" if original.endswith(b"\n") else b"\n") + second
    _validate_output(joined)
    _write_private(output, joined)
    return {
        "table_count": len(parsed.descriptors),
        "nonempty_table_count": sum(bool(rows) for rows in parsed.rows.values()),
        "perturbed_table_count": changed_tables,
        "perturbed_row_count": changed_rows,
        "empty_table_count": empty_tables,
        "output_table_count": len(parsed.descriptors) * 2,
        "output_row_count": sum(map(len, parsed.rows.values())) * 2,
    }


def _fresh_key_replacement(
    descriptor: SourceTableDescriptor,
    rows: tuple[SourceRow, ...],
    row: SourceRow,
) -> tuple[int, bytes, object | None]:
    snapshot = migrated_table_ruleset_snapshot()
    resolved = resolve_table_rule(
        snapshot,
        descriptor.canonical_name,
        primary_key_columns=descriptor.primary_key_canonical_names,
    )
    key_names = resolved.decision.compare_key_columns or descriptor.primary_key_canonical_names
    if not key_names:
        index, literal = _require_mutable_for_keyless(descriptor, rows, row)
        return index, literal, None
    indexes = {column.canonical_name: column.ordinal for column in descriptor.columns}
    key_indexes = tuple(indexes[name] for name in key_names if name in indexes)
    if len(key_indexes) != len(key_names):
        raise ValueError(f"table {descriptor.canonical_name} has an unresolved synthetic key")
    occupied = {tuple(values[index] for index in key_indexes) for values in rows}
    old_key = tuple(row[index] for index in key_indexes)
    for key_index in key_indexes:
        column = descriptor.columns[key_index]
        for candidate in _fresh_values(column, (values[key_index] for values in rows)):
            candidate_key = tuple(candidate if index == key_index else value for index, value in zip(key_indexes, old_key, strict=True))
            if candidate_key not in occupied:
                return key_index, _sql_literal_for_fresh(column, candidate), candidate
    raise ValueError(f"table {descriptor.canonical_name} has no safe fresh key")


def _require_mutable_for_keyless(
    descriptor: SourceTableDescriptor,
    rows: tuple[SourceRow, ...],
    row: SourceRow,
) -> tuple[int, bytes]:
    chosen = _mutator_for(descriptor, rows)
    if chosen is None:
        raise ValueError(f"table {descriptor.canonical_name} has no safe keyless row change")
    index, mutate = chosen
    return index, mutate(row[index])


def _fresh_values(
    column: SourceColumnDescriptor,
    occupied_values: Iterable[object],
) -> Iterator[object]:
    occupied = set(occupied_values)
    declared_type = column.declared_type
    kind = None if declared_type is None else declared_type.kind
    if kind in {DeclaredTypeKind.SIGNED_INTEGER, DeclaredTypeKind.UNSIGNED_INTEGER}:
        assert declared_type is not None
        bits = declared_type.bits or 64
        limit = 1 << bits
        if kind is DeclaredTypeKind.SIGNED_INTEGER:
            minimum, maximum = -(limit // 2), limit // 2 - 1
            candidates: Iterable[int] = range(
                0,
                min(maximum + 1, len(occupied) + 2),
            )
            candidates = (
                *candidates,
                *range(-1, max(minimum - 1, -len(occupied) - 2), -1),
            )
        else:
            maximum = limit - 1
            candidates = range(0, min(maximum + 1, len(occupied) + 2))
        for candidate in candidates:
            value = str(candidate)
            if not any(getattr(item, "decimal", None) == value for item in occupied):
                yield (
                    UnsignedIntegerScalar(value)
                    if kind is DeclaredTypeKind.UNSIGNED_INTEGER
                    else SignedIntegerScalar(value)
                )
    elif kind is DeclaredTypeKind.STRING and column.logical_type in {
        SqlLogicalType.STANDARD,
        SqlLogicalType.ENUM,
    }:
        if column.logical_type is SqlLogicalType.ENUM:
            for label in column.enum_or_set_labels or ():
                scalar = StringScalar(label)
                if scalar not in occupied:
                    yield scalar
            return
        maximum = _LENGTH.search(column.sql_type)
        width = 64 if maximum is None else max(1, int(maximum.group(1)))
        for length in range(1, min(width, 8) + 1):
            for value in _base62_values(length):
                scalar = StringScalar(value)
                if scalar not in occupied:
                    yield scalar
    elif kind is DeclaredTypeKind.BIT:
        assert declared_type is not None
        width = declared_type.bit_width or 1
        byte_width = (width + 7) // 8
        for value in range(min(1 << width, len(occupied) + 2)):
            scalar = BitScalar(value.to_bytes(byte_width, "big"))
            if scalar not in occupied:
                yield scalar
    elif kind is DeclaredTypeKind.BINARY:
        fixed = re.search(r"\bBINARY\s*\(\s*(\d+)\s*\)", column.sql_type, re.IGNORECASE)
        maximum = _LENGTH.search(column.sql_type)
        max_bytes = (
            int(fixed.group(1))
            if fixed is not None
            else 64 if maximum is None else max(1, int(maximum.group(1)))
        )
        for value in range(len(occupied) + 2):
            minimum_width = max(1, (value.bit_length() + 7) // 8)
            if minimum_width > max_bytes:
                break
            raw = value.to_bytes(
                max_bytes if fixed is not None else minimum_width,
                "big",
            )
            scalar = BinaryScalar(raw)
            if scalar not in occupied:
                yield scalar


def _base62_values(length: int) -> Iterator[str]:
    total = len(_BASE62) ** length
    for number in range(total):
        chars = ["a"] * length
        current = number
        for position in range(length - 1, -1, -1):
            chars[position] = _BASE62[current % len(_BASE62)]
            current //= len(_BASE62)
        yield "".join(chars)


def _sql_literal_for_fresh(column: SourceColumnDescriptor, scalar: object) -> bytes:
    if isinstance(scalar, StringScalar):
        return _sql_string_literal(scalar.text)
    if isinstance(scalar, (SignedIntegerScalar, UnsignedIntegerScalar)):
        return scalar.decimal.encode("ascii")
    if isinstance(scalar, BitScalar):
        return str(int.from_bytes(scalar.raw_bytes, "big")).encode("ascii")
    if isinstance(scalar, BinaryScalar):
        return b"x'" + scalar.raw_bytes.hex().encode("ascii") + b"'"
    raise ValueError(f"column {column.canonical_name} has no SQL key rendering")


def _write_private(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor = os.open(
        path,
        os.O_WRONLY | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0),
        0o600,
    )
    try:
        os.fchmod(descriptor, 0o600)
        os.ftruncate(descriptor, 0)
        with os.fdopen(descriptor, "wb", closefd=False) as handle:
            handle.write(content)
    finally:
        os.close(descriptor)


def _validate_output(raw: bytes) -> None:
    parsed = _parse_input(raw)
    del parsed


def _make_w4(source: Path, output: Path, rate: float) -> dict[str, Any]:
    raw = source.read_bytes()
    parsed = _parse_input(raw)
    replacements: dict[str, dict[int, dict[int, bytes]]] = {}
    deleted: dict[str, set[int]] = {}
    appended: dict[str, dict[int, tuple[bytes, ...]]] = {}
    empty_rows: dict[str, bytes] = {}
    rows_after: dict[str, int] = {}
    summaries: list[dict[str, object]] = []

    for table_name, descriptor in parsed.descriptors.items():
        rows = parsed.rows[table_name]
        indexed_rows = parsed.rows_by_table[table_name]
        if not rows:
            literal_row = _default_row(descriptor)
            empty_rows[table_name] = (
                b"INSERT INTO `"
                + descriptor.display_name.replace("`", "``").encode("utf-8")
                + b"` VALUES ("
                + b", ".join(literal_row)
                + b");"
            )
            rows_after[table_name] = 1
            summaries.append(
                {"table": table_name, "before": 0, "inserted": 1, "deleted": 0, "updated": 0, "after": 1}
            )
            continue
        mutation = _mutator_for(descriptor, rows)
        if mutation is None:
            raise ValueError(f"table {table_name} has no safe non-key field for W4")
        mutation_column, mutate = mutation
        operation_count = min(len(rows), max(1, math.ceil(len(rows) * rate)))
        insert_count = operation_count // 3
        delete_count = operation_count // 3
        update_count = operation_count - insert_count - delete_count
        order = tuple(range(len(rows)))
        deleted_indexes = set(order[:delete_count])
        update_indexes = set(order[delete_count : delete_count + update_count])
        insert_sources = order[delete_count + update_count : delete_count + update_count + insert_count]
        if insert_count and not insert_sources:
            insert_sources = tuple(index for index in reversed(order) if index not in deleted_indexes)[:insert_count]
        table_replacements: dict[int, dict[int, bytes]] = {}
        table_appended: dict[int, tuple[bytes, ...]] = {}
        by_row_index = {item.row_index: item for item in indexed_rows}
        for row_index in update_indexes:
            row = rows[row_index]
            table_replacements[row_index] = {mutation_column: mutate(row[mutation_column])}
        ordered_rule = resolve_table_rule(
            migrated_table_ruleset_snapshot(),
            descriptor.canonical_name,
            primary_key_columns=descriptor.primary_key_canonical_names,
        ).record
        position_index: int | None = None
        next_position: int | None = None
        if ordered_rule.position_column is not None and update_indexes:
            position_index = next(
                column.ordinal
                for column in descriptor.columns
                if column.canonical_name == ordered_rule.position_column
            )
            positions = [
                int(getattr(row[position_index], "decimal"))
                for row in rows
                if hasattr(row[position_index], "decimal")
            ]
            if len(positions) != len(rows):
                raise ValueError(f"ordered table {table_name} has a non-numeric position")
            next_position = max(positions, default=0) + 1
            moved_row = min(update_indexes)
            table_replacements.setdefault(moved_row, {})[position_index] = str(next_position).encode("ascii")
            next_position += 1
        elif ordered_rule.position_column is not None:
            position_index = next(
                column.ordinal
                for column in descriptor.columns
                if column.canonical_name == ordered_rule.position_column
            )
            positions = [
                int(getattr(row[position_index], "decimal"))
                for row in rows
                if hasattr(row[position_index], "decimal")
            ]
            if len(positions) != len(rows):
                raise ValueError(f"ordered table {table_name} has a non-numeric position")
            next_position = max(positions, default=0) + 1
        working_rows = list(rows)
        for source_index in insert_sources:
            source_row = rows[source_index]
            source_tuple = by_row_index[source_index]
            clone = _replace_cells(raw, source_tuple, {})
            clone_changes: dict[int, bytes] = {}
            key_index, key_literal, fresh_key = _fresh_key_replacement(
                descriptor,
                tuple(working_rows),
                source_row,
            )
            if key_index >= 0:
                clone_changes[key_index] = key_literal
                if fresh_key is not None:
                    synthetic_row = list(source_row)
                    synthetic_row[key_index] = fresh_key
                    working_rows.append(tuple(synthetic_row))
            clone_changes[mutation_column] = mutate(source_row[mutation_column])
            if position_index is not None:
                assert next_position is not None
                clone_changes[position_index] = str(next_position).encode("ascii")
                next_position += 1
            for index, value in sorted(clone_changes.items(), key=lambda item: source_tuple.cells[item[0]].start, reverse=True):
                span = source_tuple.cells[index]
                local_start = span.start - source_tuple.start
                local_end = span.end - source_tuple.start
                clone = clone[:local_start] + value + clone[local_end:]
            table_appended[source_index] = (*table_appended.get(source_index, ()), clone)
        replacements[table_name] = table_replacements
        deleted[table_name] = deleted_indexes
        appended[table_name] = table_appended
        after_count = len(rows) - len(deleted_indexes) + len(insert_sources)
        rows_after[table_name] = after_count
        summaries.append(
            {
                "table": table_name,
                "before": len(rows),
                "inserted": len(insert_sources),
                "deleted": len(deleted_indexes),
                "updated": len(update_indexes),
                "after": after_count,
            }
        )

    transformed = _rewrite_input(
        parsed,
        replacements_by_table=replacements,
        deleted_by_table=deleted,
        appended_by_table=appended,
        append_empty_tables=empty_rows,
    )
    _validate_output(transformed)
    _write_private(output, transformed)
    return {
        "table_count": len(parsed.descriptors),
        "before_row_count": sum(map(len, parsed.rows.values())),
        "after_row_count": sum(rows_after.values()),
        "changed_table_count": len(parsed.descriptors),
        "tables": summaries,
    }


def _json_nesting_depth(value: object) -> int:
    maximum = 0
    pending: list[tuple[object, int]] = [(value, 0)]
    while pending:
        current, parent_depth = pending.pop()
        if isinstance(current, dict):
            depth = parent_depth + 1
            maximum = max(maximum, depth)
            pending.extend((child, depth) for child in current.values())
        elif isinstance(current, list):
            depth = parent_depth + 1
            maximum = max(maximum, depth)
            pending.extend((child, depth) for child in current)
    return maximum


def _json_text_nesting_depth(text: str) -> int:
    depth = 0
    maximum = 0
    in_string = False
    escaped = False
    for character in text:
        if in_string:
            if escaped:
                escaped = False
            elif character == "\\":
                escaped = True
            elif character == '"':
                in_string = False
            continue
        if character == '"':
            in_string = True
        elif character in "[{":
            depth += 1
            maximum = max(maximum, depth)
        elif character in "]}" and depth > 0:
            depth -= 1
    return maximum


def _json_depth(source: Path) -> dict[str, object]:
    raw = source.read_bytes()
    runtime = _runtime()
    create_statements = b"\n".join(
        raw[span.start : span.end]
        for span in iter_statements(raw, runtime)
        if classify_statement(ByteCursor(raw, span.start, span.end), runtime) == "create"
    )
    parsed = parse_sql(_parse_request(create_statements))
    descriptors = {
        table.descriptor.canonical_name: table.descriptor for table in parsed.tables
    }
    if not descriptors:
        raise ValueError("source SQL has no readable table descriptors")
    depth_counts: dict[int, int] = {}
    json_value_count = 0
    for span in iter_statements(raw, runtime):
        cursor = ByteCursor(raw, span.start, span.end)
        if classify_statement(cursor, runtime) != "insert":
            continue
        if not cursor.try_keyword("insert", runtime):
            raise AssertionError("statement classifier lost INSERT")
        cursor.try_keyword("ignore", runtime)
        if not cursor.try_keyword("into", runtime):
            raise ValueError("unsupported INSERT shape")
        _display, table_name = cursor.parse_table_name(runtime)
        descriptor = descriptors.get(table_name)
        if descriptor is None:
            raise ValueError(f"INSERT table {table_name} has no CREATE TABLE")
        build = TableBuild(
            display_name=descriptor.display_name,
            canonical_name=descriptor.canonical_name,
            columns=list(descriptor.columns),
            pk=list(descriptor.primary_key_canonical_names),
        )
        cursor.skip_ws_and_comments(runtime)
        ordinals = (
            _parse_insert_columns(cursor, runtime, build)
            if cursor.peek() == ord("(")
            else tuple(range(len(descriptor.columns)))
        )
        if not cursor.try_keyword("values", runtime):
            raise ValueError(f"INSERT table {table_name} has no VALUES clause")
        while True:
            cursor.skip_ws_and_comments(runtime)
            if cursor.peek() != ord("("):
                break
            tuple_start, tuple_end = cursor.take_balanced_paren(runtime)
            parts = _split_top_level(raw, tuple_start + 1, tuple_end - 1, runtime)
            if len(parts) != len(ordinals):
                raise ValueError(f"INSERT table {table_name} has a row width mismatch")
            for part_index, (part_start, part_end) in enumerate(parts):
                column = descriptor.columns[ordinals[part_index]]
                if column.logical_type is not SqlLogicalType.JSON:
                    continue
                cell_cursor = ByteCursor(raw, part_start, part_end)
                literal = parse_literal(cell_cursor, runtime)
                if literal.is_null:
                    continue
                if literal.text is not None:
                    text = literal.text
                elif literal.raw is not None:
                    text = literal.raw.decode("utf-8")
                else:
                    raise ValueError(f"table {table_name} has an unsupported JSON literal")
                depth = _json_text_nesting_depth(text)
                if depth <= 100:
                    value = json.loads(text, parse_constant=_reject_json_constant)
                    if _contains_unpaired_surrogate(value):
                        raise ValueError(f"table {table_name} contains an unpaired JSON surrogate")
                    depth = _json_nesting_depth(value)
                depth_counts[depth] = depth_counts.get(depth, 0) + 1
                json_value_count += 1
    return {
        "json_value_count": json_value_count,
        "maximum_nesting_depth": max(depth_counts, default=0),
        "depth_counts": {str(key): depth_counts[key] for key in sorted(depth_counts)},
    }


def _reject_json_constant(token: str) -> None:
    raise ValueError(f"non-standard JSON constant: {token}")


def _default_row(descriptor: SourceTableDescriptor) -> tuple[bytes, ...]:
    literals: list[bytes] = []
    protected = set(_protected_columns(descriptor))
    record = resolve_table_rule(
        migrated_table_ruleset_snapshot(),
        descriptor.canonical_name,
        primary_key_columns=descriptor.primary_key_canonical_names,
    ).record
    for column in descriptor.columns:
        if column.nullable and column.canonical_name not in protected:
            literals.append(b"NULL")
            continue
        if column.canonical_name == record.position_column:
            literals.append(b"1")
            continue
        if column.logical_type is SqlLogicalType.ENUM:
            assert column.enum_or_set_labels
            literals.append(_sql_literal_for_fresh(column, StringScalar(column.enum_or_set_labels[0])))
        elif column.logical_type is SqlLogicalType.SET:
            literals.append(b"''")
        elif column.logical_type is SqlLogicalType.JSON:
            literals.append(b"'{}'")
        elif column.declared_type is None:
            raise ValueError(f"table {descriptor.canonical_name} has an unknown column type")
        elif column.declared_type.kind in {
            DeclaredTypeKind.SIGNED_INTEGER,
            DeclaredTypeKind.UNSIGNED_INTEGER,
            DeclaredTypeKind.DECIMAL,
            DeclaredTypeKind.FLOAT32,
            DeclaredTypeKind.FLOAT64,
            DeclaredTypeKind.BOOLEAN,
        }:
            literals.append(b"0")
        elif column.declared_type.kind is DeclaredTypeKind.BIT:
            literals.append(b"0")
        elif column.declared_type.kind is DeclaredTypeKind.STRING:
            literals.append(b"''")
        elif column.declared_type.kind is DeclaredTypeKind.BINARY:
            fixed_binary = re.search(r"\bBINARY\s*\(\s*(\d+)\s*\)", column.sql_type, re.IGNORECASE)
            binary_size = 0 if fixed_binary is None else int(fixed_binary.group(1))
            literals.append(b"x'" + b"00" * binary_size + b"'")
        elif column.declared_type.kind is DeclaredTypeKind.DATE:
            literals.append(b"'2000-01-01'")
        elif column.declared_type.kind in {DeclaredTypeKind.DATETIME, DeclaredTypeKind.TIMESTAMP}:
            literals.append(b"'2000-01-01 00:00:00'")
        elif column.declared_type.kind is DeclaredTypeKind.TIME_DURATION:
            literals.append(b"'00:00:00'")
        else:
            raise ValueError(f"table {descriptor.canonical_name} has no synthetic row default")
    return tuple(literals)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    make = commands.add_parser("make-2x")
    make.add_argument("--source", required=True)
    make.add_argument("--output", required=True)
    make.add_argument("--suffix", default="__x2")
    w4 = commands.add_parser("make-w4")
    w4.add_argument("--source", required=True)
    w4.add_argument("--output", required=True)
    w4.add_argument("--rate", type=float, choices=(0.1, 1.0), default=0.1)
    depth = commands.add_parser("json-depth")
    depth.add_argument("--source", required=True, help="private SQL dump path")
    args = parser.parse_args(argv)

    if args.command == "make-2x":
        summary = make_2x(Path(args.source), Path(args.output), args.suffix)
    elif args.command == "make-w4":
        summary = _make_w4(Path(args.source), Path(args.output), args.rate)
    else:
        summary = _json_depth(Path(args.source))
    print(json.dumps(summary, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
