"""Deferred SQL table reader. Re-parses INSERT tuple spans from source bytes."""

from __future__ import annotations

from collections.abc import Iterator

from gateway_backend.capabilities.table_access._parser_runtime import ParserHalt, ParserRuntime
from gateway_backend.capabilities.table_access._sql_statements import TupleSpan, parse_tuple_cells
from gateway_backend.capabilities.table_access._sql_values import LiteralError
from gateway_backend.capabilities.table_access.contracts import (
    RESOURCE_BUDGETS,
    ParserDiagnosticCode,
    ParserInvocationContext,
    ResourceBudgets,
    SourceRow,
    SourceTableDescriptor,
    TableAccessError,
)


class SqlTableReader:
    def __init__(
        self,
        descriptor: SourceTableDescriptor,
        source: bytes,
        spans: tuple[TupleSpan, ...],
        context: ParserInvocationContext,
        budgets: ResourceBudgets = RESOURCE_BUDGETS,
    ) -> None:
        if type(descriptor) is not SourceTableDescriptor:
            raise ValueError("descriptor must be SourceTableDescriptor")
        if not descriptor.reader_ready:
            raise ValueError("SQL reader requires reader_ready")
        if type(source) is not bytes:
            raise ValueError("source must be bytes")
        if type(spans) is not tuple:
            raise ValueError("spans must be a tuple")
        if type(context) is not ParserInvocationContext:
            raise ValueError("context must be ParserInvocationContext")
        if type(budgets) is not ResourceBudgets:
            raise ValueError("budgets must be ResourceBudgets")
        self._descriptor = descriptor
        self._source = source
        self._spans = spans
        self._context = context
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
        runtime = ParserRuntime(self._context, self._budgets)
        batch_rows = 0
        batch_bytes = 0
        columns = self._descriptor.columns
        for span in self._spans:
            if type(span) is not TupleSpan:
                error = TableAccessError(
                    ParserDiagnosticCode.MALFORMED_SQL,
                    "reader span is invalid",
                )
                self._stream_error = error
                raise error
            try:
                runtime.checkpoint(span.start)
                row = parse_tuple_cells(self._source, span, columns, runtime)
            except LiteralError as exc:
                error = TableAccessError(exc.code, exc.message)
                self._stream_error = error
                raise error from exc
            except ParserHalt as halt:
                error = TableAccessError(halt.code, halt.message)
                self._stream_error = error
                raise error from halt
            row_bytes = span.end - span.start
            if (
                batch_rows >= self._budgets.max_reader_batch_rows
                or batch_bytes + row_bytes > self._budgets.max_reader_batch_bytes
            ):
                batch_rows = 0
                batch_bytes = 0
                try:
                    runtime.checkpoint(span.start)
                except ParserHalt as halt:
                    error = TableAccessError(halt.code, halt.message)
                    self._stream_error = error
                    raise error from halt
            batch_rows += 1
            batch_bytes += row_bytes
            yield row
        # EOF is the reader's successful completion commit point.
        try:
            runtime.checkpoint(len(self._source))
        except ParserHalt as halt:
            error = TableAccessError(halt.code, halt.message)
            self._stream_error = error
            raise error from halt

    def close(self) -> None:
        self._closed = True

    def reopen(self) -> SqlTableReader:
        return SqlTableReader(
            self._descriptor,
            self._source,
            self._spans,
            self._context,
            self._budgets,
        )

    def _require_open(self) -> None:
        if self._closed:
            raise TableAccessError(ParserDiagnosticCode.READER_CLOSED, "reader is closed")
        if self._stream_error is not None:
            raise self._stream_error
