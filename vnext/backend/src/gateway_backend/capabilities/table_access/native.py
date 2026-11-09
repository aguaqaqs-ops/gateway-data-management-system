"""Production Table Access Arrow adapter; ordinary rows are borrowed on demand."""

from __future__ import annotations

import struct
from collections.abc import Iterator, Callable
from types import SimpleNamespace
from typing import Any, cast

import pyarrow as pa
from gateway_compute._native import _parse_sql_native
from gateway_shared_kernel import (
    BinaryScalar, BitScalar, BooleanScalar, DateScalar, DateTimeScalar, DecimalScalar,
    DeclaredType, DeclaredTypeKind, Float32Scalar, Float64Scalar, NullScalar,
    SignedIntegerScalar, StringScalar, TimeDurationScalar, TimestampScalar, UnsignedIntegerScalar,
)

from gateway_backend.capabilities.table_access.contracts import (
    RESOURCE_BUDGETS, DiagnosticSeverity, DiagnosticSource, ParsedTable, ParseResult,
    ParseStatus, ParserDiagnostic, ParserDiagnosticCode, ResourceBudgets,
    SourceCell, SourceColumnDescriptor, SourceRow, SourceTableDescriptor,
    SqlLogicalType, SqlParseRequest, SqlSetValue, TableAccessError,
)
from gateway_backend.capabilities.table_access.kernel import (
    KernelExecutionContext, KernelMemoryLimit, current_kernel_context, merge_kernel_control,
)


class _ArrowLifetime:
    def __init__(self, close: Callable[[], None] | None) -> None:
        self.borrowers = 0
        self._close = close

    def release(self) -> None:
        self.borrowers -= 1
        if self.borrowers == 0 and self._close is not None:
            self._close()
            self._close = None


class ArrowSourceTableReader:
    """Reopenable Arrow backing with single-consumer row/stream views."""

    def __init__(self, descriptor: SourceTableDescriptor, table: pa.Table,
                 context: KernelExecutionContext, *, close: Callable[[], None] | None = None,
                 lifetime: _ArrowLifetime | None = None) -> None:
        self._descriptor = descriptor
        self._table: pa.Table | None = table
        self._context = context
        self._reservation = context.memory.retain_arrow(table)
        metadata_bytes = 4096 + sum(512 + (len(c.canonical_name) + len(c.display_name) + len(c.sql_type)) * 16
                                    + sum(len(label) * 16 + 128 for label in c.enum_or_set_labels or ())
                                    for c in descriptor.columns)
        try:
            context.memory.retain_metadata(descriptor, metadata_bytes)
        except BaseException:
            self._reservation.close()
            raise
        self._closed = False
        self._consumed = False
        self._lifetime = lifetime or _ArrowLifetime(close)
        self._lifetime.borrowers += 1
        try:
            context.memory.retain_metadata(self, 512)
            context.resources.callback(self.close)
        except BaseException:
            self.close()
            raise

    @property
    def execution_context(self) -> KernelExecutionContext:
        return self._context

    def descriptor(self) -> SourceTableDescriptor:
        self._require_open()
        return self._descriptor

    @property
    def row_count(self) -> int:
        self._require_open()
        assert self._table is not None
        return int(self._table.num_rows)

    @property
    def logical_size_bytes(self) -> int:
        self._require_open()
        assert self._table is not None
        return int(self._table.nbytes)

    @property
    def arrow_schema(self) -> pa.Schema:
        self._require_open()
        assert self._table is not None
        return self._table.schema

    @property
    def arrow_batch_count_upper(self) -> int:
        """Each distinct chunk boundary can add at most one output batch."""
        self._require_open()
        assert self._table is not None
        return 1 + sum(max(0, len(column.chunks) - 1) for column in self._table.columns)

    def arrow_stream(self) -> pa.RecordBatchReader:
        self._require_open()
        assert self._table is not None
        if self._consumed:
            raise ValueError("table reader is single-consumer and non-rewind")
        self._consumed = True
        table = self._table
        def batches() -> Iterator[pa.RecordBatch]:
            for batch in table.to_batches():
                self._context.checkpoint()
                yield batch
            self._context.checkpoint()
        return pa.RecordBatchReader.from_batches(table.schema, batches())

    def iter_rows(self) -> Iterator[SourceRow]:
        with self.arrow_stream() as stream:
            for batch in stream:
                self._context.checkpoint()
                for index in range(batch.num_rows):
                    if index % 1024 == 0:
                        self._context.checkpoint()
                    yield tuple(source_cell_from_arrow(batch.column(i)[index].as_py(), column)
                                for i, column in enumerate(self._descriptor.columns))
        self._context.checkpoint()

    def reopen(self) -> ArrowSourceTableReader:
        self._require_open()
        assert self._table is not None
        return ArrowSourceTableReader(self._descriptor, self._table, self._context, lifetime=self._lifetime)

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        self._table = None
        self._reservation.close()
        self._lifetime.release()

    def _require_open(self) -> None:
        if self._closed:
            raise TableAccessError(ParserDiagnosticCode.READER_CLOSED, "reader is closed")


def source_descriptor_from_arrow(value: dict[str, Any]) -> SourceTableDescriptor:
    return SourceTableDescriptor(
        display_name=value["display_name"], canonical_name=value["canonical_name"],
        primary_key_canonical_names=tuple(value["primary_key"]), reader_ready=value["reader_ready"],
        columns=tuple(SourceColumnDescriptor(
            display_name=c["display_name"], canonical_name=c["canonical_name"], ordinal=c["ordinal"],
            sql_type=c["sql_type"], logical_type=SqlLogicalType(c["logical_type"]),
            declared_type=None if c["declared_type"] is None else DeclaredType(
                **{**c["declared_type"], "kind": DeclaredTypeKind(c["declared_type"]["kind"])}),
            nullable=c["nullable"], enum_or_set_labels=None if c["labels"] is None else tuple(c["labels"]),
        ) for c in value["columns"]),
    )


def source_arrow_metadata(source: SourceTableDescriptor, stream: pa.RecordBatchReader) -> dict[str, Any]:
    return {
        "canonical_name": source.canonical_name, "display_name": source.display_name,
        "primary_key": list(source.primary_key_canonical_names), "reader_ready": source.reader_ready,
        "arrow_stream": stream,
        "columns": [{
            "canonical_name": c.canonical_name, "display_name": c.display_name, "ordinal": c.ordinal,
            "sql_type": c.sql_type, "logical_type": c.logical_type.value, "nullable": c.nullable,
            "labels": None if c.enum_or_set_labels is None else list(c.enum_or_set_labels),
            "declared_type": None if c.declared_type is None else {
                "kind": c.declared_type.kind.value, "bits": c.declared_type.bits,
                "precision": c.declared_type.precision, "scale": c.declared_type.scale,
                "bit_width": c.declared_type.bit_width,
            },
        } for c in source.columns],
    }


def parse_arrow_sql(request: SqlParseRequest, *, budgets: ResourceBudgets = RESOURCE_BUDGETS) -> ParseResult:
    context = current_kernel_context()
    if context is None:
        raise ValueError("production SQL parsing requires an operation kernel context")
    context = merge_kernel_control(context, request.context.cancel_requested, request.context.deadline_monotonic)
    context.checkpoint()
    # An upstream source read can hold the identical bytes; shared backing counts once.
    with context.memory.reserve(len(request.sql_utf8), backing=("python-bytes", id(request.sql_utf8))):
        local = SimpleNamespace(**{name: getattr(budgets, name) for name in budgets.__dataclass_fields__},
                                max_live_bytes=context.memory.available_bytes)
        context.memory.record_stage_admission("sql-parser", context.memory.available_bytes)
        envelope = cast(dict[str, Any], _parse_sql_native(
            request.sql_utf8, context.cancel_probe, context.deadline_monotonic, context.threads, local))
        context.checkpoint()
        if envelope["kind"] != "result":
            raise TableAccessError(ParserDiagnosticCode(envelope["code"]), envelope["message"])
        diagnostics = tuple(ParserDiagnostic(
            code=ParserDiagnosticCode(item["code"]), severity=DiagnosticSeverity.WARNING
            if item["code"] == ParserDiagnosticCode.PARSER_DIAGNOSTICS_TRUNCATED.value else DiagnosticSeverity.ERROR,
            source=DiagnosticSource.SQL, byte_offset=item["byte_offset"], message=item["message"],
            table=item["table"], column=item["column"],
        ) for item in envelope["diagnostics"])
        if any(d.code is ParserDiagnosticCode.RESOURCE_LIMIT_EXCEEDED and d.message == "max_live_bytes exceeded"
               for d in diagnostics):
            raise KernelMemoryLimit("SQL parser operation memory reservation exceeded")
        tables: list[ParsedTable] = []
        try:
            for item in envelope["tables"]:
                source = source_descriptor_from_arrow(item)
                stream = item["arrow_stream"]
                if stream is None:
                    tables.append(ParsedTable(source, None))
                    continue
                with stream:
                    table = stream.read_all()
                tables.append(ParsedTable(source, ArrowSourceTableReader(source, table, context)))
            context.checkpoint()
            return ParseResult(ParseStatus(envelope["status"]), tuple(tables), diagnostics,
                configuration_generated_time=envelope["configuration_generated_time"])
        except BaseException:
            for table in tables:
                if table.reader is not None:
                    table.reader.close()
            raise
        finally:
            for item in envelope["tables"]:
                if item["arrow_stream"] is not None:
                    item["arrow_stream"].close()


def source_cell_from_arrow(value: Any, column: SourceColumnDescriptor) -> SourceCell:
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

