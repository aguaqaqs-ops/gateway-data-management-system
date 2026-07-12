from __future__ import annotations

from collections.abc import Iterable, Iterator, Sequence
from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable

from .catalog import RepositoryTableCatalogTable


@runtime_checkable
class RepositoryTableReader(Protocol):
    @property
    def catalog_table(self) -> RepositoryTableCatalogTable: ...

    @property
    def column_order(self) -> tuple[str, ...]: ...

    def stream_rows(self) -> Iterator[tuple[object | None, ...]]: ...

    def close(self) -> None: ...


@dataclass(slots=True)
class TupleRepositoryTableReader:
    catalog_table: RepositoryTableCatalogTable
    rows: Sequence[Sequence[object | None]] = field(default_factory=tuple)
    _closed: bool = field(default=False, init=False, repr=False)

    def __post_init__(self) -> None:
        if not isinstance(self.catalog_table, RepositoryTableCatalogTable):
            raise TypeError("catalog_table must be a RepositoryTableCatalogTable")
        normalized_rows: list[tuple[object | None, ...]] = []
        column_count = len(self.catalog_table.columns)
        for row in self.rows:
            if isinstance(row, (str, bytes, bytearray)):
                raise TypeError("rows must be sequences of row values, not text")
            if not isinstance(row, Sequence):
                raise TypeError("rows must be sequences of row values")
            row_tuple = tuple(row)
            if len(row_tuple) != column_count:
                raise ValueError("row length must match catalog column count")
            normalized_rows.append(row_tuple)
        self.rows = tuple(normalized_rows)
        self._closed = False

    @property
    def column_order(self) -> tuple[str, ...]:
        return self.catalog_table.column_order

    def stream_rows(self) -> Iterator[tuple[object | None, ...]]:
        if self._closed:
            raise RuntimeError("reader is closed")
        yield from self.rows

    def iter_rows(self) -> Iterator[tuple[object | None, ...]]:
        return self.stream_rows()

    def close(self) -> None:
        self._closed = True

    @property
    def closed(self) -> bool:
        return self._closed
