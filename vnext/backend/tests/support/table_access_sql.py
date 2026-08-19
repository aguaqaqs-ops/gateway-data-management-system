"""Helpers for SQL parser tests. Not a production parser."""

from __future__ import annotations

from gateway_backend.capabilities.table_access.contracts import (
    RESOURCE_BUDGETS,
    NeverCancel,
    ParseResult,
    ParserInvocationContext,
    ResourceBudgets,
    SourceRow,
    SqlParseRequest,
    SqlSourceInput,
)
from gateway_backend.capabilities.table_access.sql import parse_sql
from gateway_shared_kernel import DigestRef

_ZERO_DIGEST = DigestRef("sha256:" + "00" * 32)


def sql_request(
    sql: str | bytes,
    context: ParserInvocationContext | None = None,
) -> SqlParseRequest:
    if type(sql) is str:
        data = sql.encode("utf-8")
    elif type(sql) is bytes:
        data = sql
    else:
        raise ValueError("sql must be str or bytes")
    return SqlParseRequest(
        source=SqlSourceInput(
            document_content_digest=_ZERO_DIGEST,
            sql_source_digest=_ZERO_DIGEST,
            parser_input_contract_version=1,
            encoding="utf-8",
            source_size_bytes=len(data),
        ),
        sql_utf8=data,
        context=context or ParserInvocationContext(NeverCancel()),
    )


def parse_text(
    sql: str | bytes,
    *,
    context: ParserInvocationContext | None = None,
    budgets: ResourceBudgets | None = None,
) -> ParseResult:
    request = sql_request(sql, context)
    if budgets is None:
        return parse_sql(request)
    return parse_sql(request, budgets=budgets)


def consumed_rows(result: ParseResult) -> tuple[tuple[SourceRow, ...], ...]:
    rows: list[tuple[SourceRow, ...]] = []
    for table in result.tables:
        if table.reader is None:
            rows.append(())
            continue
        rows.append(tuple(table.reader.iter_rows()))
    return tuple(rows)


def tiny_budgets(**overrides: int) -> ResourceBudgets:
    values = {field: getattr(RESOURCE_BUDGETS, field) for field in RESOURCE_BUDGETS.__dataclass_fields__}
    values.update(overrides)
    return ResourceBudgets(**values)
