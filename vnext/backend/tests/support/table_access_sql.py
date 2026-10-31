"""Helpers for SQL parser tests. Not a production parser."""

from __future__ import annotations

import contextvars
import struct
from collections.abc import Iterator
from typing import Any

import pyarrow as pa
import pytest
from gateway_compute._native import _parse_sql_native
from gateway_backend.capabilities.table_access.contracts import (
    RESOURCE_BUDGETS,
    DiagnosticSeverity,
    DiagnosticSource,
    NeverCancel,
    ParseStatus,
    ParsedTable,
    ParseResult,
    ParserDiagnostic,
    ParserDiagnosticCode,
    ParserInvocationContext,
    ResourceBudgets,
    SqlLogicalType,
    SourceCell,
    SqlSetValue,
    SourceRow,
    SourceColumnDescriptor,
    SourceTableDescriptor,
    SqlParseRequest,
    SqlSourceInput,
    TableAccessError,
)
from gateway_shared_kernel import (
    BinaryScalar,
    BitScalar,
    BooleanScalar,
    DateScalar,
    DateTimeScalar,
    DecimalScalar,
    DeclaredType,
    DeclaredTypeKind,
    Float32Scalar,
    Float64Scalar,
    NullScalar,
    SignedIntegerScalar,
    StringScalar,
    TimeDurationScalar,
    TimestampScalar,
    UnsignedIntegerScalar,
)
from gateway_backend.capabilities.table_access.sql import parse_sql
from gateway_shared_kernel import DigestRef

_ZERO_DIGEST = DigestRef("sha256:" + "00" * 32)
_ACTIVE_IMPLEMENTATION: contextvars.ContextVar[str] = contextvars.ContextVar(
    "active_sql_parser_implementation", default="python"
)


@pytest.fixture(params=("python", "rust"), ids=("python", "rust"))
def dual_sql_implementation(request: pytest.FixtureRequest) -> Iterator[None]:
    token = _ACTIVE_IMPLEMENTATION.set(str(request.param))
    try:
        yield
    finally:
        _ACTIVE_IMPLEMENTATION.reset(token)


def current_sql_implementation() -> str:
    return _ACTIVE_IMPLEMENTATION.get()


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
    implementation: str | None = None,
) -> ParseResult:
    request = sql_request(sql, context)
    return parse_request_result(request, budgets=budgets, implementation=implementation)


def parse_request_result(
    request: SqlParseRequest,
    *,
    budgets: ResourceBudgets | None = None,
    implementation: str | None = None,
) -> ParseResult:
    selected = implementation or current_sql_implementation()
    if selected == "python":
        return parse_sql(request) if budgets is None else parse_sql(request, budgets=budgets)
    if selected != "rust":
        raise ValueError("implementation must be 'python' or 'rust'")
    envelope = _parse_sql_native(
        request.sql_utf8,
        request.context.cancel_requested,
        request.context.deadline_monotonic,
        1,
        budgets or RESOURCE_BUDGETS,
    )
    if envelope["kind"] == "error":
        raise RuntimeError(
            f"{envelope['code']} at {envelope['byte_offset']}: {envelope['message']}"
        )
    tables = tuple(_table_from_native(item, request, budgets or RESOURCE_BUDGETS) for item in envelope["tables"])
    diagnostics = tuple(
        ParserDiagnostic(
            code=ParserDiagnosticCode[item["code"]],
            severity=(
                DiagnosticSeverity.WARNING
                if item["code"] == ParserDiagnosticCode.PARSER_DIAGNOSTICS_TRUNCATED.value
                else DiagnosticSeverity.ERROR
            ),
            source=DiagnosticSource.SQL,
            byte_offset=item["byte_offset"],
            message=item["message"],
            table=item["table"],
            column=item["column"],
        )
        for item in envelope["diagnostics"]
    )
    return ParseResult(ParseStatus(envelope["status"]), tables, diagnostics)


def _table_from_native(
    value: dict[str, Any],
    request: SqlParseRequest,
    budgets: ResourceBudgets,
) -> ParsedTable:
    columns = tuple(
        SourceColumnDescriptor(
            display_name=column["display_name"],
            canonical_name=column["canonical_name"],
            ordinal=column["ordinal"],
            sql_type=column["sql_type"],
            logical_type=SqlLogicalType(column["logical_type"]),
            declared_type=_declared_type(column["declared_type"]),
            nullable=column["nullable"],
            enum_or_set_labels=(
                tuple(column["labels"]) if column["labels"] is not None else None
            ),
        )
        for column in value["columns"]
    )
    descriptor = SourceTableDescriptor(
        display_name=value["display_name"],
        canonical_name=value["canonical_name"],
        columns=columns,
        primary_key_canonical_names=tuple(value["primary_key"]),
        reader_ready=value["reader_ready"],
    )
    if not descriptor.reader_ready:
        return ParsedTable(descriptor, None)
    stream = value["arrow_stream"]
    if stream is None:
        raise RuntimeError("ready native table has no Arrow C Stream")
    table = stream.read_all()
    return ParsedTable(
        descriptor,
        _ArrowSqlTableReader(
            descriptor,
            table,
            request.context,
            request.sql_utf8,
            budgets,
        ),
    )


def _declared_type(value: dict[str, Any] | None) -> DeclaredType | None:
    if value is None:
        return None
    return DeclaredType(
        kind=DeclaredTypeKind(value["kind"]),
        bits=value.get("bits"),
        precision=value.get("precision"),
        scale=value.get("scale"),
        bit_width=value.get("bit_width"),
    )


class _ArrowSqlTableReader:
    def __init__(
        self,
        descriptor: SourceTableDescriptor,
        table: pa.Table,
        context: ParserInvocationContext,
        source: bytes,
        budgets: ResourceBudgets,
    ) -> None:
        self._descriptor = descriptor
        self._table = table
        self._context = context
        self._source = source
        self._budgets = budgets
        self._closed = False
        self._consumed = False
        self._stream_error: TableAccessError | None = None

    def descriptor(self) -> SourceTableDescriptor:
        self._require_open()
        return self._descriptor

    def iter_rows(self) -> Iterator[SourceRow]:
        self._require_open()
        if self._consumed:
            raise ValueError("table reader is single-consumer and non-rewind")
        self._consumed = True
        from gateway_backend.capabilities.table_access._parser_runtime import ParserHalt, ParserRuntime

        runtime = ParserRuntime(self._context, self._budgets)
        try:
            for batch in self._table.to_batches(max_chunksize=self._budgets.max_reader_batch_rows):
                for row_index in range(batch.num_rows):
                    runtime.checkpoint(row_index)
                    yield tuple(
                        _source_cell(batch.column(column_index)[row_index].as_py(), column)
                        for column_index, column in enumerate(self._descriptor.columns)
                    )
            runtime.checkpoint(len(self._source))
        except ParserHalt as halt:
            error = TableAccessError(halt.code, halt.message)
            self._stream_error = error
            raise error from halt

    def close(self) -> None:
        self._closed = True

    def reopen(self) -> _ArrowSqlTableReader:
        return _ArrowSqlTableReader(
            self._descriptor,
            self._table,
            self._context,
            self._source,
            self._budgets,
        )

    def _require_open(self) -> None:
        if self._closed:
            raise TableAccessError(ParserDiagnosticCode.READER_CLOSED, "reader is closed")
        if self._stream_error is not None:
            raise self._stream_error


def _source_cell(value: Any, column: SourceColumnDescriptor) -> SourceCell:
    if value is None:
        return NullScalar()
    if column.logical_type is SqlLogicalType.SET:
        text = str(value)
        return SqlSetValue(tuple(text.split(",")) if text else ())
    declared = column.declared_type
    if declared is None:
        raise RuntimeError("ready native column has no declared type")
    kind = declared.kind
    if kind is DeclaredTypeKind.BOOLEAN:
        return BooleanScalar(value)
    if kind is DeclaredTypeKind.SIGNED_INTEGER:
        return SignedIntegerScalar(str(value))
    if kind is DeclaredTypeKind.UNSIGNED_INTEGER:
        return UnsignedIntegerScalar(str(value))
    if kind is DeclaredTypeKind.DECIMAL:
        return DecimalScalar(str(value))
    if kind is DeclaredTypeKind.FLOAT32:
        return Float32Scalar(struct.pack(">f", float(value)).hex())
    if kind is DeclaredTypeKind.FLOAT64:
        return Float64Scalar(struct.pack(">d", float(value)).hex())
    if kind is DeclaredTypeKind.STRING:
        return StringScalar(str(value))
    if kind is DeclaredTypeKind.BINARY:
        return BinaryScalar(bytes(value))
    if kind is DeclaredTypeKind.BIT:
        return BitScalar(bytes(value))
    if kind is DeclaredTypeKind.DATE:
        return DateScalar(str(value))
    if kind is DeclaredTypeKind.DATETIME:
        return DateTimeScalar(str(value))
    if kind is DeclaredTypeKind.TIMESTAMP:
        return TimestampScalar(str(value))
    if kind is DeclaredTypeKind.TIME_DURATION:
        return TimeDurationScalar(str(value))
    raise RuntimeError(f"unsupported native declared type: {kind.value}")


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
