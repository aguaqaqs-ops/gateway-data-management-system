"""Allowlisted SQL dump statements."""

from __future__ import annotations

from dataclasses import dataclass, field

from gateway_backend.capabilities.table_access._parser_runtime import ParserHalt, ParserRuntime
from gateway_backend.capabilities.table_access._sql_scan import ByteCursor
from gateway_backend.capabilities.table_access._sql_types import map_sql_type
from gateway_backend.capabilities.table_access._sql_values import (
    LiteralError,
    SqlLiteral,
    literal_to_cell,
    parse_literal,
)
from gateway_backend.capabilities.table_access.contracts import (
    ParserDiagnosticCode,
    SourceCell,
    SourceColumnDescriptor,
    SourceRow,
    SqlLogicalType,
)

_CONSTRAINT_HEADS = (
    "primary",
    "key",
    "index",
    "unique",
    "foreign",
    "check",
    "constraint",
    "fulltext",
    "spatial",
)
_ALLOWED_SET_NAMES = frozenset(
    {
        "names",
        "time_zone",
        "unique_checks",
        "foreign_key_checks",
        "sql_mode",
        "sql_notes",
        "collation_connection",
        "collation_database",
        "collation_server",
    }
)
_TABLE_OPTIONS = frozenset(
    {
        "engine",
        "charset",
        "collate",
        "auto_increment",
        "comment",
        "row_format",
        "stats_persistent",
        "checksum",
        "delay_key_write",
        "key_block_size",
        "max_rows",
        "min_rows",
        "avg_row_length",
        "pack_keys",
        "default",
        "character",
        "data",
        "index",
        "tablespace",
        "compression",
        "encryption",
        "union",
        "insert_method",
        "connection",
        "password",
        "stats_auto_recalc",
        "stats_sample_pages",
    }
)


@dataclass
class TupleSpan:
    start: int
    end: int
    ordinals: tuple[int, ...]


@dataclass
class TableBuild:
    display_name: str
    canonical_name: str
    columns: list[SourceColumnDescriptor] = field(default_factory=list)
    pk: list[str] = field(default_factory=list)
    create_offset: int = 0
    failed: bool = False
    unknown: bool = False
    spans: list[TupleSpan] = field(default_factory=list)
    row_count: int = 0


def classify_statement(cursor: ByteCursor, runtime: ParserRuntime) -> str:
    saved = cursor.pos
    cursor.skip_ws_and_comments(runtime)
    if cursor.at_end():
        return "empty"
    for keyword in (
        "create",
        "insert",
        "replace",
        "drop",
        "set",
        "lock",
        "unlock",
        "alter",
        "use",
        "delimiter",
        "update",
        "delete",
        "truncate",
        "rename",
        "call",
        "start",
        "begin",
        "commit",
        "rollback",
        "savepoint",
        "trigger",
        "create",
    ):
        cursor.pos = saved
        if cursor.try_keyword(keyword, runtime):
            cursor.pos = saved
            return keyword
    cursor.pos = saved
    return "unknown"


def parse_create_table(
    cursor: ByteCursor, runtime: ParserRuntime, tables: dict[str, TableBuild]
) -> None:
    offset = cursor.pos
    if not cursor.try_keyword("create", runtime):
        runtime.fail_document(
            ParserDiagnosticCode.MALFORMED_SQL, "expected CREATE TABLE", offset
        )
    if not cursor.try_keyword("table", runtime):
        runtime.fail_document(
            ParserDiagnosticCode.UNSUPPORTED_STATEMENT,
            "CREATE statement is not in the source dump allowlist",
            offset,
        )
    saved = cursor.pos
    if not (
        cursor.try_keyword("if", runtime)
        and cursor.try_keyword("not", runtime)
        and cursor.try_keyword("exists", runtime)
    ):
        cursor.pos = saved
    display, canonical = cursor.parse_table_name(runtime)
    if canonical in tables:
        existing = tables[canonical]
        existing.failed = True
        existing.spans.clear()
        code = (
            ParserDiagnosticCode.DUPLICATE_TABLE
            if existing.display_name == display
            else ParserDiagnosticCode.CANONICAL_IDENTIFIER_COLLISION
        )
        runtime.add_diagnostic(code, f"duplicate table {display}", offset, table=display)
        _skip_create_remainder(cursor, runtime)
        return
    if len(tables) >= runtime.budgets.max_tables_per_source:
        runtime.resource_exceeded("max_tables_per_source", offset)
    table = TableBuild(display_name=display, canonical_name=canonical, create_offset=offset)
    body_start, body_end = cursor.take_balanced_paren(runtime)
    _parse_table_items(cursor.data, body_start + 1, body_end - 1, runtime, table)
    _skip_table_options(cursor, runtime)
    cursor.skip_ws_and_comments(runtime)
    if not cursor.at_end():
        runtime.fail_document(
            ParserDiagnosticCode.MALFORMED_SQL,
            "unexpected tokens after CREATE TABLE",
            cursor.pos,
        )
    tables[canonical] = table


def parse_insert(
    cursor: ByteCursor, runtime: ParserRuntime, tables: dict[str, TableBuild], source_rows: int
) -> int:
    offset = cursor.pos
    if not cursor.try_keyword("insert", runtime):
        runtime.fail_document(ParserDiagnosticCode.MALFORMED_SQL, "expected INSERT", offset)
    if cursor.try_keyword("ignore", runtime):
        runtime.fail_document(
            ParserDiagnosticCode.UNSUPPORTED_STATEMENT,
            "INSERT IGNORE is not in the source dump allowlist",
            offset,
        )
    if not cursor.try_keyword("into", runtime):
        runtime.fail_document(
            ParserDiagnosticCode.MALFORMED_SQL, "expected INSERT INTO", offset
        )
    _display, canonical = cursor.parse_table_name(runtime)
    table = tables.get(canonical)
    if table is None:
        runtime.fail_document(
            ParserDiagnosticCode.MALFORMED_SQL,
            "INSERT targets an unknown table",
            offset,
        )
    cursor.skip_ws_and_comments(runtime)
    if cursor.try_keyword("set", runtime):
        runtime.fail_document(
            ParserDiagnosticCode.UNSUPPORTED_STATEMENT,
            "INSERT ... SET is not in the source dump allowlist",
            offset,
        )
    if cursor.try_keyword("select", runtime):
        runtime.fail_document(
            ParserDiagnosticCode.UNSUPPORTED_STATEMENT,
            "INSERT ... SELECT is not in the source dump allowlist",
            offset,
        )
    ordinals: tuple[int, ...]
    if cursor.peek() == ord("("):
        ordinals = _parse_insert_columns(cursor, runtime, table)
    else:
        ordinals = tuple(range(len(table.columns)))
    if not cursor.try_keyword("values", runtime):
        runtime.fail_document(
            ParserDiagnosticCode.INCOMPLETE_INSERT
            if cursor.try_keyword("select", runtime)
            else ParserDiagnosticCode.MALFORMED_SQL,
            "INSERT must use VALUES with complete columns",
            cursor.pos,
        )
    return _parse_value_tuples(cursor, runtime, table, ordinals, source_rows)


def parse_boilerplate(kind: str, cursor: ByteCursor, runtime: ParserRuntime) -> None:
    offset = cursor.pos
    if kind == "replace":
        runtime.fail_document(
            ParserDiagnosticCode.UNSUPPORTED_STATEMENT,
            "REPLACE is not in the source dump allowlist",
            offset,
        )
    if kind == "drop":
        _parse_drop_table(cursor, runtime)
        return
    if kind == "set":
        _parse_set(cursor, runtime)
        return
    if kind == "lock":
        _parse_lock(cursor, runtime)
        return
    if kind == "unlock":
        if not cursor.try_keyword("unlock", runtime) or not cursor.try_keyword("tables", runtime):
            runtime.fail_document(
                ParserDiagnosticCode.MALFORMED_SQL, "expected UNLOCK TABLES", offset
            )
        _expect_end(cursor, runtime)
        return
    if kind == "alter":
        _parse_alter_keys(cursor, runtime)
        return
    if kind in {"use", "delimiter"}:
        runtime.fail_document(
            ParserDiagnosticCode.UNSUPPORTED_STATEMENT,
            f"{kind.upper()} is not in the source dump allowlist",
            offset,
        )
    runtime.fail_document(
        ParserDiagnosticCode.UNSUPPORTED_STATEMENT,
        f"{kind.upper()} is not in the source dump allowlist",
        offset,
    )


def _parse_table_items(
    data: bytes, start: int, end: int, runtime: ParserRuntime, table: TableBuild
) -> None:
    for item_start, item_end in _split_top_level(data, start, end, runtime):
        item = ByteCursor(data, item_start, item_end)
        item.skip_ws_and_comments(runtime)
        if item.at_end():
            runtime.fail_document(
                ParserDiagnosticCode.MALFORMED_SQL, "empty table item", item_start
            )
        if _is_constraint_item(item, runtime):
            _parse_constraint(item, runtime, table)
        else:
            _parse_column(item, runtime, table)
        item.skip_ws_and_comments(runtime)
        if not item.at_end():
            runtime.fail_document(
                ParserDiagnosticCode.MALFORMED_SQL,
                "unexpected tokens in table item",
                item.pos,
            )


def _parse_column(cursor: ByteCursor, runtime: ParserRuntime, table: TableBuild) -> None:
    offset = cursor.pos
    display, canonical = cursor.parse_identifier(runtime)
    for existing in table.columns:
        if existing.canonical_name == canonical:
            code = (
                ParserDiagnosticCode.DUPLICATE_COLUMN
                if existing.display_name == display
                else ParserDiagnosticCode.CANONICAL_IDENTIFIER_COLLISION
            )
            runtime.add_diagnostic(
                code, f"duplicate column {display}", offset, table=table.display_name, column=display
            )
            table.failed = True
            table.spans.clear()
            _skip_column_remainder(cursor, runtime)
            return
    if len(table.columns) >= runtime.budgets.max_columns_per_table:
        runtime.resource_exceeded("max_columns_per_table", offset)
    type_sql = _parse_column_type(cursor, runtime)
    mapped = map_sql_type(type_sql, max_enum_set_bytes=runtime.budgets.max_enum_set_sql_type_bytes)
    nullable = True
    inline_pk = False
    while not cursor.at_end():
        cursor.skip_ws_and_comments(runtime)
        if cursor.at_end():
            break
        attr_offset = cursor.pos
        if cursor.try_keyword("generated", runtime):
            runtime.fail_document(
                ParserDiagnosticCode.UNSUPPORTED_STATEMENT,
                "GENERATED columns are not in the source dump allowlist",
                attr_offset,
            )
        if cursor.try_keyword("virtual", runtime) or cursor.try_keyword("stored", runtime):
            runtime.fail_document(
                ParserDiagnosticCode.UNSUPPORTED_STATEMENT,
                "GENERATED columns are not in the source dump allowlist",
                attr_offset,
            )
        if cursor.try_keyword("not", runtime):
            if not cursor.try_keyword("null", runtime):
                runtime.fail_document(
                    ParserDiagnosticCode.MALFORMED_SQL, "expected NOT NULL", attr_offset
                )
            nullable = False
            continue
        if cursor.try_keyword("null", runtime):
            nullable = True
            continue
        if cursor.try_keyword("default", runtime):
            _skip_default(cursor, runtime)
            continue
        if cursor.try_keyword("on", runtime):
            if not cursor.try_keyword("update", runtime):
                runtime.fail_document(
                    ParserDiagnosticCode.MALFORMED_SQL, "expected ON UPDATE", attr_offset
                )
            _skip_default(cursor, runtime)
            continue
        if cursor.try_keyword("auto_increment", runtime):
            continue
        if cursor.try_keyword("comment", runtime):
            _skip_default(cursor, runtime)
            continue
        if cursor.try_keyword("primary", runtime):
            if not cursor.try_keyword("key", runtime):
                runtime.fail_document(
                    ParserDiagnosticCode.MALFORMED_SQL, "expected PRIMARY KEY", attr_offset
                )
            inline_pk = True
            nullable = False
            continue
        if cursor.try_keyword("unique", runtime):
            cursor.try_keyword("key", runtime)
            continue
        if cursor.try_keyword("references", runtime):
            _skip_column_remainder(cursor, runtime)
            break
        if cursor.try_keyword("constraint", runtime):
            runtime.fail_document(
                ParserDiagnosticCode.MALFORMED_SQL,
                "unexpected CONSTRAINT on column",
                attr_offset,
            )
        break
    column = SourceColumnDescriptor(
        display_name=display,
        canonical_name=canonical,
        ordinal=len(table.columns),
        sql_type=mapped.sql_type,
        logical_type=mapped.logical_type,
        declared_type=mapped.declared_type,
        nullable=nullable,
        enum_or_set_labels=mapped.enum_or_set_labels,
    )
    table.columns.append(column)
    if mapped.error is not None:
        runtime.add_diagnostic(
            mapped.error,
            f"column type {mapped.sql_type}",
            offset,
            table=table.display_name,
            column=display,
        )
        table.failed = True
        if mapped.logical_type is SqlLogicalType.UNKNOWN:
            table.unknown = True
        table.spans.clear()
    if inline_pk:
        _add_pk(table, (canonical,), offset, runtime)


def _parse_column_type(cursor: ByteCursor, runtime: ParserRuntime) -> str:
    cursor.skip_ws_and_comments(runtime)
    start = cursor.pos
    if cursor.at_end():
        runtime.fail_document(ParserDiagnosticCode.MALFORMED_SQL, "expected column type", start)
    _consume_type_name(cursor, runtime)
    cursor.skip_ws_and_comments(runtime)
    if cursor.peek() == ord("("):
        cursor.take_balanced_paren(runtime)
    while True:
        cursor.skip_ws_and_comments(runtime)
        saved = cursor.pos
        if cursor.try_keyword("unsigned", runtime) or cursor.try_keyword("zerofill", runtime):
            continue
        if cursor.try_keyword("character", runtime):
            if not cursor.try_keyword("set", runtime):
                cursor.pos = saved
                break
            _skip_name_or_string(cursor, runtime)
            continue
        if cursor.try_keyword("collate", runtime):
            _skip_name_or_string(cursor, runtime)
            continue
        cursor.pos = saved
        break
    raw = _strip_sql_comments(cursor.data[start:cursor.pos])
    try:
        return raw.decode("utf-8").strip()
    except UnicodeDecodeError as exc:
        raise ParserHalt(
            ParserDiagnosticCode.MALFORMED_SQL, "column type is not UTF-8", start
        ) from exc


def _strip_sql_comments(raw: bytes) -> bytes:
    output = bytearray()
    index = 0
    quote: int | None = None
    while index < len(raw):
        byte = raw[index]
        if quote is not None:
            output.append(byte)
            if byte == ord("\\") and quote == ord("'") and index + 1 < len(raw):
                index += 1
                output.append(raw[index])
            elif byte == quote:
                if index + 1 < len(raw) and raw[index + 1] == quote:
                    index += 1
                    output.append(raw[index])
                else:
                    quote = None
            index += 1
            continue
        if byte in {ord("'"), ord('"'), ord("`")}:
            quote = byte
            output.append(byte)
            index += 1
            continue
        if raw.startswith(b"/*", index):
            end = raw.find(b"*/", index + 2)
            if end < 0:
                output.extend(raw[index:])
                break
            output.append(ord(" "))
            index = end + 2
            continue
        if byte == ord("#") or (
            raw.startswith(b"--", index)
            and (index + 2 == len(raw) or raw[index + 2] in b" \t\r\n\x00")
        ):
            output.append(ord(" "))
            while index < len(raw) and raw[index] not in {ord("\n"), ord("\r")}:
                index += 1
            continue
        output.append(byte)
        index += 1
    return bytes(output)


def _consume_type_name(cursor: ByteCursor, runtime: ParserRuntime) -> None:
    cursor.parse_identifier(runtime)
    cursor.skip_ws_and_comments(runtime)
    saved = cursor.pos
    if cursor.try_keyword("precision", runtime):
        return
    cursor.pos = saved
    if cursor.try_keyword("varying", runtime):
        return


def _parse_constraint(cursor: ByteCursor, runtime: ParserRuntime, table: TableBuild) -> None:
    offset = cursor.pos
    if cursor.try_keyword("constraint", runtime):
        saved = cursor.pos
        if not (
            cursor.try_keyword("primary", runtime)
            or cursor.try_keyword("unique", runtime)
            or cursor.try_keyword("foreign", runtime)
            or cursor.try_keyword("check", runtime)
        ):
            cursor.parse_identifier(runtime)
        else:
            cursor.pos = saved
    if cursor.try_keyword("primary", runtime):
        if not cursor.try_keyword("key", runtime):
            runtime.fail_document(
                ParserDiagnosticCode.MALFORMED_SQL, "expected PRIMARY KEY", offset
            )
        names = _parse_index_columns(cursor, runtime)
        _add_pk(table, names, offset, runtime)
        return
    if (
        cursor.try_keyword("unique", runtime)
        or cursor.try_keyword("key", runtime)
        or cursor.try_keyword("index", runtime)
        or cursor.try_keyword("fulltext", runtime)
        or cursor.try_keyword("spatial", runtime)
        or cursor.try_keyword("foreign", runtime)
        or cursor.try_keyword("check", runtime)
    ):
        _skip_column_remainder(cursor, runtime)
        return
    runtime.fail_document(
        ParserDiagnosticCode.MALFORMED_SQL, "unsupported table constraint", offset
    )


def _parse_index_columns(cursor: ByteCursor, runtime: ParserRuntime) -> tuple[str, ...]:
    start, end = cursor.take_balanced_paren(runtime)
    names: list[str] = []
    inner = ByteCursor(cursor.data, start + 1, end - 1)
    while True:
        inner.skip_ws_and_comments(runtime)
        if inner.at_end():
            break
        _display, canonical = inner.parse_identifier(runtime)
        names.append(canonical)
        inner.skip_ws_and_comments(runtime)
        if inner.peek() == ord("("):
            inner.take_balanced_paren(runtime)
        inner.skip_ws_and_comments(runtime)
        if inner.peek() == ord(","):
            inner.pos += 1
            continue
        if inner.at_end():
            break
        runtime.fail_document(
            ParserDiagnosticCode.MALFORMED_SQL, "malformed key column list", inner.pos
        )
    if not names:
        runtime.fail_document(
            ParserDiagnosticCode.MALFORMED_SQL, "primary key requires columns", start
        )
    return tuple(names)


def _add_pk(
    table: TableBuild, names: tuple[str, ...], offset: int, runtime: ParserRuntime
) -> None:
    if table.pk:
        runtime.add_diagnostic(
            ParserDiagnosticCode.DUPLICATE_PRIMARY_KEY,
            "duplicate primary key",
            offset,
            table=table.display_name,
        )
        table.failed = True
        table.spans.clear()
        return
    seen: set[str] = set()
    columns = {column.canonical_name for column in table.columns}
    for name in names:
        if name in seen:
            runtime.add_diagnostic(
                ParserDiagnosticCode.DUPLICATE_PRIMARY_KEY,
                "duplicate primary key column",
                offset,
                table=table.display_name,
                column=name,
            )
            table.failed = True
            table.spans.clear()
            return
        seen.add(name)
        if name not in columns:
            runtime.add_diagnostic(
                ParserDiagnosticCode.MALFORMED_SQL,
                "primary key must reference a column",
                offset,
                table=table.display_name,
                column=name,
            )
            table.failed = True
            table.spans.clear()
            return
    table.pk = list(names)


def _parse_insert_columns(
    cursor: ByteCursor, runtime: ParserRuntime, table: TableBuild
) -> tuple[int, ...]:
    start, end = cursor.take_balanced_paren(runtime)
    inner = ByteCursor(cursor.data, start + 1, end - 1)
    ordinals: list[int] = []
    seen: set[str] = set()
    index_by_name = {column.canonical_name: column.ordinal for column in table.columns}
    while True:
        inner.skip_ws_and_comments(runtime)
        if inner.at_end():
            break
        display, canonical = inner.parse_identifier(runtime)
        if canonical in seen:
            runtime.add_diagnostic(
                ParserDiagnosticCode.DUPLICATE_COLUMN,
                f"duplicate column {display}",
                inner.pos,
                table=table.display_name,
                column=display,
            )
            table.failed = True
            table.spans.clear()
        seen.add(canonical)
        if canonical not in index_by_name:
            runtime.add_diagnostic(
                ParserDiagnosticCode.ROW_SHAPE_MISMATCH,
                f"INSERT column {display} is not in the table",
                inner.pos,
                table=table.display_name,
                column=display,
            )
            table.failed = True
            table.spans.clear()
            ordinals.append(0)
        else:
            ordinals.append(index_by_name[canonical])
        inner.skip_ws_and_comments(runtime)
        if inner.peek() == ord(","):
            inner.pos += 1
            continue
        if inner.at_end():
            break
        runtime.fail_document(
            ParserDiagnosticCode.MALFORMED_SQL, "malformed INSERT column list", inner.pos
        )
    expected = {column.canonical_name for column in table.columns}
    if seen != expected:
        runtime.add_diagnostic(
            ParserDiagnosticCode.INCOMPLETE_INSERT,
            "INSERT column list must include every column",
            start,
            table=table.display_name,
        )
        table.failed = True
        table.spans.clear()
    return tuple(ordinals)


def _parse_value_tuples(
    cursor: ByteCursor,
    runtime: ParserRuntime,
    table: TableBuild,
    ordinals: tuple[int, ...],
    source_rows: int,
) -> int:
    added = 0
    while True:
        runtime.checkpoint(cursor.pos)
        cursor.skip_ws_and_comments(runtime)
        tuple_start = cursor.pos
        start, end = cursor.take_balanced_paren(runtime)
        size = end - start
        if size > runtime.budgets.max_insert_tuple_bytes:
            runtime.resource_exceeded("max_insert_tuple_bytes", tuple_start)
        try:
            values = _parse_tuple_values(cursor.data, start + 1, end - 1, runtime)
        except LiteralError as exc:
            if exc.code is ParserDiagnosticCode.MALFORMED_SQL:
                runtime.fail_document(exc.code, exc.message, exc.byte_offset)
            runtime.add_diagnostic(
                exc.code, exc.message, exc.byte_offset, table=table.display_name
            )
            table.failed = True
            table.spans.clear()
            values = None
        if values is not None and len(values) != len(ordinals):
            runtime.add_diagnostic(
                ParserDiagnosticCode.ROW_SHAPE_MISMATCH,
                "INSERT tuple width does not match columns",
                tuple_start,
                table=table.display_name,
            )
            table.failed = True
            table.spans.clear()
        elif values is not None and not table.failed:
            row_cells: list[object | None] = [None] * len(table.columns)
            try:
                for value_index, literal in enumerate(values):
                    ordinal = ordinals[value_index]
                    row_cells[ordinal] = literal_to_cell(
                        literal, table.columns[ordinal], runtime, tuple_start
                    )
            except LiteralError as exc:
                runtime.add_diagnostic(
                    exc.code, exc.message, exc.byte_offset, table=table.display_name
                )
                table.failed = True
                table.spans.clear()
            else:
                if table.row_count >= runtime.budgets.max_rows_per_table:
                    runtime.resource_exceeded("max_rows_per_table", tuple_start)
                if source_rows + added >= runtime.budgets.max_rows_per_source:
                    runtime.resource_exceeded("max_rows_per_source", tuple_start)
                table.spans.append(TupleSpan(start=start, end=end, ordinals=ordinals))
                table.row_count += 1
                added += 1
        cursor.skip_ws_and_comments(runtime)
        if cursor.try_keyword("on", runtime):
            runtime.fail_document(
                ParserDiagnosticCode.UNSUPPORTED_STATEMENT,
                "ON DUPLICATE KEY UPDATE is not in the source dump allowlist",
                cursor.pos,
            )
        if cursor.peek() == ord(","):
            cursor.pos += 1
            continue
        break
    _expect_end(cursor, runtime)
    return added


def _parse_tuple_values(
    data: bytes, start: int, end: int, runtime: ParserRuntime
) -> list[SqlLiteral]:
    cursor = ByteCursor(data, start, end)
    values: list[SqlLiteral] = []
    while True:
        cursor.skip_ws_and_comments(runtime)
        if cursor.at_end():
            if values:
                runtime.fail_document(
                    ParserDiagnosticCode.MALFORMED_SQL, "trailing comma in VALUES", cursor.pos
                )
            break
        values.append(parse_literal(cursor, runtime))
        cursor.skip_ws_and_comments(runtime)
        if cursor.peek() == ord(","):
            cursor.pos += 1
            continue
        if cursor.at_end():
            break
        runtime.fail_document(
            ParserDiagnosticCode.MALFORMED_SQL, "malformed VALUES tuple", cursor.pos
        )
    return values


def parse_tuple_cells(
    data: bytes,
    span: TupleSpan,
    columns: tuple[SourceColumnDescriptor, ...],
    runtime: ParserRuntime,
) -> SourceRow:
    values = _parse_tuple_values(data, span.start + 1, span.end - 1, runtime)
    if len(values) != len(span.ordinals):
        raise LiteralError(
            ParserDiagnosticCode.ROW_SHAPE_MISMATCH,
            "INSERT tuple width does not match columns",
            span.start,
        )
    row: list[SourceCell | None] = [None] * len(columns)
    for value_index, literal in enumerate(values):
        ordinal = span.ordinals[value_index]
        row[ordinal] = literal_to_cell(literal, columns[ordinal], runtime, span.start)
    cells: list[SourceCell] = []
    for cell in row:
        if cell is None:
            raise LiteralError(
                ParserDiagnosticCode.ROW_SHAPE_MISMATCH,
                "INSERT tuple is missing a column",
                span.start,
            )
        cells.append(cell)
    return tuple(cells)


def _parse_drop_table(cursor: ByteCursor, runtime: ParserRuntime) -> None:
    offset = cursor.pos
    if not cursor.try_keyword("drop", runtime) or not cursor.try_keyword("table", runtime):
        runtime.fail_document(ParserDiagnosticCode.MALFORMED_SQL, "expected DROP TABLE", offset)
    if not cursor.try_keyword("if", runtime) or not cursor.try_keyword("exists", runtime):
        runtime.fail_document(
            ParserDiagnosticCode.UNSUPPORTED_STATEMENT,
            "DROP TABLE without IF EXISTS is not in the source dump allowlist",
            offset,
        )
    cursor.parse_table_name(runtime)
    while True:
        cursor.skip_ws_and_comments(runtime)
        if cursor.peek() == ord(","):
            cursor.pos += 1
            cursor.parse_table_name(runtime)
            continue
        break
    _expect_end(cursor, runtime)


def _parse_set(cursor: ByteCursor, runtime: ParserRuntime) -> None:
    offset = cursor.pos
    if not cursor.try_keyword("set", runtime):
        runtime.fail_document(ParserDiagnosticCode.MALFORMED_SQL, "expected SET", offset)
    cursor.skip_ws_and_comments(runtime)
    if cursor.try_keyword("names", runtime):
        _skip_set_rhs(cursor, runtime)
        while cursor.peek() == ord(","):
            cursor.pos += 1
            _parse_one_set_assignment(cursor, runtime)
        _expect_end(cursor, runtime)
        return
    _parse_one_set_assignment(cursor, runtime)
    while True:
        cursor.skip_ws_and_comments(runtime)
        if cursor.peek() == ord(","):
            cursor.pos += 1
            _parse_one_set_assignment(cursor, runtime)
            continue
        break
    _expect_end(cursor, runtime)


def _parse_one_set_assignment(cursor: ByteCursor, runtime: ParserRuntime) -> None:
    offset = cursor.pos
    name = _parse_set_lhs(cursor, runtime)
    if not _allowed_set_name(name):
        runtime.fail_document(
            ParserDiagnosticCode.UNSUPPORTED_STATEMENT,
            f"SET {name} is not in the source dump allowlist",
            offset,
        )
    cursor.skip_ws_and_comments(runtime)
    if cursor.peek() != ord("="):
        runtime.fail_document(ParserDiagnosticCode.MALFORMED_SQL, "expected '=' in SET", cursor.pos)
    cursor.pos += 1
    _skip_set_rhs(cursor, runtime)


def _parse_set_lhs(cursor: ByteCursor, runtime: ParserRuntime) -> str:
    cursor.skip_ws_and_comments(runtime)
    start = cursor.pos
    if cursor.peek() == ord("@"):
        cursor.pos += 1
        if cursor.peek() == ord("@"):
            cursor.pos += 1
    display, canonical = cursor.parse_identifier(runtime)
    del display
    prefix = cursor.data[start:cursor.pos].decode("ascii", "ignore")
    if prefix.startswith("@@") or prefix.startswith("@"):
        return prefix
    return canonical


def _allowed_set_name(name: str) -> bool:
    if name.lower() == "@saved_cs_client":
        return True
    lowered = name.lower().lstrip("@")
    if lowered.startswith("old_"):
        return True
    if lowered.startswith("character_set_"):
        return True
    if lowered.startswith("collation_"):
        return True
    return lowered in _ALLOWED_SET_NAMES


def _skip_set_rhs(cursor: ByteCursor, runtime: ParserRuntime) -> None:
    cursor.skip_ws_and_comments(runtime)
    saved = cursor.pos
    try:
        parse_literal(cursor, runtime)
        return
    except LiteralError:
        cursor.pos = saved
    if cursor.peek() == ord("@"):
        cursor.pos += 1
        if cursor.peek() == ord("@"):
            cursor.pos += 1
        cursor.parse_identifier(runtime)
        return
    if cursor.peek() is not None:
        cursor.parse_identifier(runtime)
        cursor.skip_ws_and_comments(runtime)
        if cursor.peek() == ord("("):
            cursor.take_balanced_paren(runtime)
        return
    runtime.fail_document(ParserDiagnosticCode.MALFORMED_SQL, "expected SET value", cursor.pos)


def _parse_lock(cursor: ByteCursor, runtime: ParserRuntime) -> None:
    offset = cursor.pos
    if not cursor.try_keyword("lock", runtime) or not cursor.try_keyword("tables", runtime):
        runtime.fail_document(ParserDiagnosticCode.MALFORMED_SQL, "expected LOCK TABLES", offset)
    while True:
        cursor.parse_table_name(runtime)
        cursor.skip_ws_and_comments(runtime)
        if cursor.try_keyword("as", runtime):
            cursor.parse_identifier(runtime)
        cursor.try_keyword("read", runtime) or cursor.try_keyword("write", runtime)
        cursor.try_keyword("local", runtime)
        cursor.skip_ws_and_comments(runtime)
        if cursor.peek() == ord(","):
            cursor.pos += 1
            continue
        break
    _expect_end(cursor, runtime)


def _parse_alter_keys(cursor: ByteCursor, runtime: ParserRuntime) -> None:
    offset = cursor.pos
    if not cursor.try_keyword("alter", runtime) or not cursor.try_keyword("table", runtime):
        runtime.fail_document(ParserDiagnosticCode.MALFORMED_SQL, "expected ALTER TABLE", offset)
    cursor.parse_table_name(runtime)
    if cursor.try_keyword("disable", runtime) or cursor.try_keyword("enable", runtime):
        if cursor.try_keyword("keys", runtime):
            _expect_end(cursor, runtime)
            return
    runtime.fail_document(
        ParserDiagnosticCode.UNSUPPORTED_STATEMENT,
        "ALTER TABLE statement is not in the source dump allowlist",
        offset,
    )


def _skip_table_options(cursor: ByteCursor, runtime: ParserRuntime) -> None:
    while not cursor.at_end():
        cursor.skip_ws_and_comments(runtime)
        if cursor.at_end() or cursor.peek() == ord(";"):
            return
        saved = cursor.pos
        matched = False
        for option in _TABLE_OPTIONS:
            cursor.pos = saved
            if cursor.try_keyword(option, runtime):
                matched = True
                break
        if not matched:
            cursor.pos = saved
            return
        cursor.skip_ws_and_comments(runtime)
        if cursor.peek() == ord("="):
            cursor.pos += 1
            _skip_set_rhs(cursor, runtime)
        elif cursor.try_keyword("character", runtime):
            cursor.try_keyword("set", runtime)
            cursor.skip_ws_and_comments(runtime)
            if cursor.peek() == ord("="):
                cursor.pos += 1
            _skip_name_or_string(cursor, runtime)
        elif cursor.try_keyword("set", runtime) or cursor.try_keyword("charset", runtime):
            cursor.skip_ws_and_comments(runtime)
            if cursor.peek() == ord("="):
                cursor.pos += 1
            _skip_name_or_string(cursor, runtime)
        else:
            saved_rhs = cursor.pos
            try:
                _skip_name_or_string(cursor, runtime)
            except ParserHalt:
                cursor.pos = saved_rhs


def _skip_name_or_string(cursor: ByteCursor, runtime: ParserRuntime) -> None:
    cursor.skip_ws_and_comments(runtime)
    saved = cursor.pos
    try:
        parse_literal(cursor, runtime)
        return
    except LiteralError:
        cursor.pos = saved
    cursor.parse_identifier(runtime)


def _skip_default(cursor: ByteCursor, runtime: ParserRuntime) -> None:
    cursor.skip_ws_and_comments(runtime)
    saved = cursor.pos
    try:
        parse_literal(cursor, runtime)
        return
    except LiteralError:
        cursor.pos = saved
    if cursor.peek() == ord("("):
        cursor.take_balanced_paren(runtime)
        return
    cursor.parse_identifier(runtime)
    cursor.skip_ws_and_comments(runtime)
    if cursor.peek() == ord("("):
        cursor.take_balanced_paren(runtime)


def _skip_column_remainder(cursor: ByteCursor, runtime: ParserRuntime) -> None:
    while not cursor.at_end():
        runtime.checkpoint(cursor.pos)
        if cursor.peek() == ord("("):
            cursor.take_balanced_paren(runtime)
            continue
        cursor.pos += 1


def _skip_create_remainder(cursor: ByteCursor, runtime: ParserRuntime) -> None:
    cursor.skip_ws_and_comments(runtime)
    if cursor.peek() == ord("("):
        cursor.take_balanced_paren(runtime)
    _skip_table_options(cursor, runtime)


def _expect_end(cursor: ByteCursor, runtime: ParserRuntime) -> None:
    cursor.skip_ws_and_comments(runtime)
    if not cursor.at_end():
        runtime.fail_document(
            ParserDiagnosticCode.MALFORMED_SQL,
            "unexpected tokens after statement",
            cursor.pos,
        )


def _is_constraint_item(cursor: ByteCursor, runtime: ParserRuntime) -> bool:
    saved = cursor.pos
    for head in _CONSTRAINT_HEADS:
        cursor.pos = saved
        if cursor.try_keyword(head, runtime):
            cursor.pos = saved
            return True
    cursor.pos = saved
    return False


def _split_top_level(
    data: bytes, start: int, end: int, runtime: ParserRuntime
) -> list[tuple[int, int]]:
    cursor = ByteCursor(data, start, end)
    items: list[tuple[int, int]] = []
    item_start = start
    depth = 0
    quote: int | None = None
    escape = False
    while cursor.pos < end:
        runtime.checkpoint(cursor.pos)
        byte = data[cursor.pos]
        if quote is not None:
            if escape:
                escape = False
                cursor.pos += 1
                continue
            if byte == ord("\\") and quote == ord("'"):
                escape = True
                cursor.pos += 1
                continue
            if byte == quote:
                nxt = cursor.pos + 1
                if quote in {ord("'"), ord("`")} and nxt < end and data[nxt] == quote:
                    cursor.pos += 2
                    continue
                quote = None
            cursor.pos += 1
            continue
        if byte in {ord("'"), ord("`")}:
            quote = byte
            cursor.pos += 1
            continue
        if byte == ord("("):
            depth += 1
        elif byte == ord(")"):
            depth -= 1
        elif byte == ord(",") and depth == 0:
            items.append((item_start, cursor.pos))
            cursor.pos += 1
            item_start = cursor.pos
            continue
        cursor.pos += 1
    items.append((item_start, end))
    return items
