"""SQL dump parser owned by the Table Access capability."""

from __future__ import annotations

from gateway_backend.capabilities.table_access._parser_runtime import ParserHalt, ParserRuntime
from gateway_backend.capabilities.table_access._sql_reader import SqlTableReader
from gateway_backend.capabilities.table_access._sql_scan import ByteCursor, iter_statements
from gateway_backend.capabilities.table_access._sql_statements import (
    TableBuild,
    classify_statement,
    parse_boilerplate,
    parse_create_table,
    parse_insert,
)
from gateway_backend.capabilities.table_access.contracts import (
    RESOURCE_BUDGETS,
    ParsedTable,
    ParseResult,
    ParseStatus,
    ParserDiagnosticCode,
    ResourceBudgets,
    SourceTableDescriptor,
    SqlLogicalType,
    SqlParseRequest,
)

__all__ = ["SqlTableReader", "parse_sql"]


def parse_sql(
    request: SqlParseRequest,
    *,
    budgets: ResourceBudgets = RESOURCE_BUDGETS,
) -> ParseResult:
    if type(request) is not SqlParseRequest:
        raise ValueError("request must be SqlParseRequest")
    if type(budgets) is not ResourceBudgets:
        raise ValueError("budgets must be ResourceBudgets")
    runtime = ParserRuntime(request.context, budgets)
    tables: dict[str, TableBuild] = {}
    source_rows = 0
    try:
        runtime.checkpoint(0)
        if len(request.sql_utf8) > budgets.max_sql_source_bytes:
            runtime.resource_exceeded("max_sql_source_bytes", 0)
        for span in iter_statements(request.sql_utf8, runtime):
            runtime.checkpoint(span.start)
            cursor = ByteCursor(request.sql_utf8, span.start, span.end)
            kind = classify_statement(cursor, runtime)
            if kind == "empty":
                continue
            if kind == "create":
                parse_create_table(cursor, runtime, tables)
                continue
            if kind == "insert":
                source_rows += parse_insert(cursor, runtime, tables, source_rows)
                continue
            parse_boilerplate(kind, cursor, runtime)
    except ParserHalt as halt:
        runtime.record_halt(halt)
        return ParseResult(
            status=ParseStatus.FAILED,
            tables=(),
            diagnostics=runtime.finish_diagnostics(),
        )
    return _assemble(request.sql_utf8, tables, runtime, budgets)


def _assemble(
    source: bytes,
    tables: dict[str, TableBuild],
    runtime: ParserRuntime,
    budgets: ResourceBudgets,
) -> ParseResult:
    parsed: list[ParsedTable] = []
    for table in tables.values():
        if not table.columns:
            runtime.add_diagnostic(
                ParserDiagnosticCode.MALFORMED_SQL,
                "CREATE TABLE requires columns",
                table.create_offset,
                table=table.display_name,
            )
            table.failed = True
        unknown = table.unknown or any(
            column.logical_type is SqlLogicalType.UNKNOWN for column in table.columns
        )
        ready = not table.failed and not unknown and not runtime.document_failed
        descriptor = SourceTableDescriptor(
            display_name=table.display_name,
            canonical_name=table.canonical_name,
            columns=tuple(table.columns),
            primary_key_canonical_names=tuple(table.pk),
            reader_ready=ready,
        )
        reader = None
        if ready:
            reader = SqlTableReader(
                descriptor,
                source,
                tuple(table.spans),
                runtime.context,
                budgets,
            )
        parsed.append(ParsedTable(descriptor, reader))
    diagnostics = runtime.finish_diagnostics()
    ready_count = sum(1 for item in parsed if item.reader is not None)
    if ready_count == len(parsed):
        status = ParseStatus.COMPLETE
    elif ready_count == 0:
        status = ParseStatus.FAILED
    else:
        status = ParseStatus.PARTIAL
    return ParseResult(status=status, tables=tuple(parsed), diagnostics=diagnostics)
