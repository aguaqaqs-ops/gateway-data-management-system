"""SnapshotTableReader wrapping a reopenable R2 TableReader."""

from __future__ import annotations

from collections.abc import Iterator
from typing import Protocol, runtime_checkable

from gateway_backend.capabilities.snapshot_materialization._digest import cell_count_key
from gateway_backend.capabilities.snapshot_materialization.contracts import (
    SnapshotColumnValueCounts,
    SnapshotTableDescriptor,
)
from gateway_backend.capabilities.table_access.contracts import (
    ParserDiagnosticCode,
    SourceRow,
    SourceTableDescriptor,
    TableAccessError,
    TableReader,
)


@runtime_checkable
class ReopenableTableReader(Protocol):
    def descriptor(self) -> SourceTableDescriptor:
        """Return the frozen source descriptor."""

    def iter_rows(self) -> Iterator[SourceRow]:
        """Yield positional rows once."""

    def close(self) -> None:
        """Idempotent close."""

    def reopen(self) -> TableReader:
        """Open an independent source reader."""


def as_reopenable(reader: TableReader) -> ReopenableTableReader | None:
    if isinstance(reader, ReopenableTableReader):
        return reader
    return None


class BoundSnapshotTableReader:
    def __init__(
        self,
        descriptor: SnapshotTableDescriptor,
        source: ReopenableTableReader,
    ) -> None:
        if type(descriptor) is not SnapshotTableDescriptor:
            raise ValueError("descriptor must be SnapshotTableDescriptor")
        self._descriptor = descriptor
        self._source = source
        self._closed = False
        self._consumed = False

    def descriptor(self) -> SnapshotTableDescriptor:
        self._require_open()
        return self._descriptor

    def source_descriptor(self) -> SourceTableDescriptor:
        self._require_open()
        return self._source.descriptor()

    def iter_rows(self) -> Iterator[SourceRow]:
        self._require_open()
        if self._consumed:
            raise ValueError("table reader is single-consumer and non-rewind")
        self._consumed = True
        yield from self._source.iter_rows()

    def count_column_values(self, column_name: str) -> SnapshotColumnValueCounts:
        self._require_open()
        columns = {column.name: index for index, column in enumerate(self._descriptor.columns)}
        if column_name not in columns:
            raise ValueError("column_name must be a descriptor column")
        index = columns[column_name]
        source_columns = self._source.descriptor().columns
        counts: dict[str | None, int] = {}
        total = 0
        isolated = as_reopenable(self._source.reopen())
        if isolated is None:
            raise ValueError("count_column_values requires a reopenable source reader")
        try:
            for row in isolated.iter_rows():
                key = cell_count_key(source_columns[index], row[index])
                counts[key] = counts.get(key, 0) + 1
                total += 1
        finally:
            isolated.close()
        ordered = tuple(sorted(counts.items(), key=lambda item: (item[0] is None, item[0] or "")))
        return SnapshotColumnValueCounts(
            column_name=column_name,
            counts=ordered,
            total_row_count=total,
        )

    def close(self) -> None:
        self._closed = True
        self._source.close()

    def reopen(self) -> BoundSnapshotTableReader:
        reopened = as_reopenable(self._source.reopen())
        if reopened is None:
            raise ValueError("source reader cannot reopen")
        return BoundSnapshotTableReader(self._descriptor, reopened)

    def _require_open(self) -> None:
        if self._closed:
            raise TableAccessError(ParserDiagnosticCode.READER_CLOSED, "reader is closed")
