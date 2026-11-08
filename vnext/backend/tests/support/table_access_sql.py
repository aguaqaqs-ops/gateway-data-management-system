"""Helpers for SQL parser tests. Not a production parser."""

from __future__ import annotations

import struct
from collections.abc import Iterator
from typing import Any

import pyarrow as pa
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
    return parse_request_result(request, budgets=budgets)


def parse_request_result(
    request: SqlParseRequest,
    *,
    budgets: ResourceBudgets | None = None,
) -> ParseResult:
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
    tables = tuple(_table_from_native(item) for item in envelope["tables"])
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


def _table_from_native(value: dict[str, Any]) -> ParsedTable:
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
        _NativeFixtureReader(descriptor, table),
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


class _NativeFixtureReader:
    def __init__(
        self,
        descriptor: SourceTableDescriptor,
        table: pa.Table,
    ) -> None:
        self._descriptor = descriptor
        self._table = table

    def descriptor(self) -> SourceTableDescriptor:
        return self._descriptor

    def iter_rows(self) -> Iterator[SourceRow]:
        for batch in self._table.to_batches():
            for row_index in range(batch.num_rows):
                yield tuple(
                    _source_cell(batch.column(column_index)[row_index].as_py(), column)
                    for column_index, column in enumerate(self._descriptor.columns)
                )

    def close(self) -> None:
        # The parser test adapter has no product-reader lifecycle to manage.
        return None


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
