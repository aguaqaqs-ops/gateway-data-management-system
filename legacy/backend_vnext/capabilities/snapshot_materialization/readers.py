from __future__ import annotations

from collections.abc import Iterator, Sequence
from dataclasses import dataclass, field
from typing import Protocol

from ...core.digests import DigestRef
from ...core.identifiers import canonical_identifier
from ...core.row_digests import stable_snapshot_rows_digest
from ...repository_server.ref_session import RepositoryRef, RepositoryTableAccessProvider
from .models import SnapshotTableDescriptor
from .sql_parser import ParsedInsertStatement, ParsedTableDefinition, _expand_insert_rows, _iter_expand_insert_rows


class SnapshotTableReader(Protocol):
    def descriptor(self) -> "SnapshotTableDescriptor":
        ...

    def iter_rows(self) -> Iterator[tuple[object, ...]]:
        ...

    def validate_content_digest(self, expected_content_digest: DigestRef | str) -> DigestRef:
        ...

    def close(self) -> None:
        ...


@dataclass(frozen=True, slots=True)
class InMemorySnapshotTableReader:
    _descriptor: "SnapshotTableDescriptor"
    _rows: tuple[tuple[object, ...], ...]
    _content_digest: DigestRef | None = field(default=None, repr=False)

    def __post_init__(self) -> None:
        rows = tuple(tuple(row) for row in self._rows)
        expected_width = len(self._descriptor.columns)
        for index, row in enumerate(rows):
            if len(row) != expected_width:
                raise ValueError(
                    f"row {index} has {len(row)} values but expected {expected_width}"
                )
        object.__setattr__(self, "_rows", rows)

    def descriptor(self) -> "SnapshotTableDescriptor":
        return self._descriptor

    def iter_rows(self) -> Iterator[tuple[object, ...]]:
        yield from self._rows

    def close(self) -> None:
        return None

    def validate_content_digest(self, expected_content_digest: DigestRef | str) -> DigestRef:
        expected = expected_content_digest
        if not isinstance(expected, DigestRef):
            expected = DigestRef.parse(str(expected))
        actual = self.content_digest
        if actual != expected:
            raise ValueError("content digest does not match rows")
        return actual

    @property
    def rows(self) -> tuple[tuple[object, ...], ...]:
        return self._rows

    @property
    def row_count(self) -> int:
        return len(self._rows)

    @property
    def content_digest(self) -> DigestRef:
        if self._content_digest is not None:
            return self._content_digest
        content_digest = stable_snapshot_rows_digest(self._rows, self._descriptor.columns)
        object.__setattr__(self, "_content_digest", content_digest)
        return content_digest


@dataclass(frozen=True, slots=True)
class LazySnapshotTableReader:
    _descriptor: "SnapshotTableDescriptor"
    _definition: ParsedTableDefinition
    _insert_statements: tuple[ParsedInsertStatement, ...]
    _rows: tuple[tuple[object, ...], ...] | None = field(default=None, repr=False)
    _content_digest: DigestRef | None = field(default=None, repr=False)

    def __post_init__(self) -> None:
        if not isinstance(self._definition, ParsedTableDefinition):
            raise TypeError("_definition must be a ParsedTableDefinition")
        if not isinstance(self._insert_statements, tuple):
            object.__setattr__(self, "_insert_statements", tuple(self._insert_statements))
        for insert in self._insert_statements:
            if not isinstance(insert, ParsedInsertStatement):
                raise TypeError("_insert_statements must contain ParsedInsertStatement values")
        if self._descriptor.table_name != self._definition.table_name:
            raise ValueError("reader definition must match descriptor table name")
        expected_columns = tuple(column.name for column in self._descriptor.columns)
        definition_columns = tuple(column.name for column in self._definition.columns)
        if expected_columns != definition_columns:
            raise ValueError("reader definition columns must match descriptor columns")
        if self._rows is not None:
            rows = tuple(tuple(row) for row in self._rows)
            expected_width = len(expected_columns)
            for index, row in enumerate(rows):
                if len(row) != expected_width:
                    raise ValueError(
                        f"row {index} has {len(row)} values but expected {expected_width}"
                    )
            object.__setattr__(self, "_rows", rows)

    def descriptor(self) -> "SnapshotTableDescriptor":
        return self._descriptor

    def iter_rows(self) -> Iterator[tuple[object, ...]]:
        if self._rows is not None:
            yield from self._rows
            return
        for insert in self._insert_statements:
            yield from _iter_expand_insert_rows(insert, self._definition)

    def close(self) -> None:
        return None

    def validate_content_digest(self, expected_content_digest: DigestRef | str) -> DigestRef:
        expected = expected_content_digest
        if not isinstance(expected, DigestRef):
            expected = DigestRef.parse(str(expected))
        actual = self.content_digest
        if actual != expected:
            raise ValueError("content digest does not match rows")
        return actual

    @property
    def rows(self) -> tuple[tuple[object, ...], ...]:
        rows = self._rows
        if rows is not None:
            return rows
        materialized_rows: list[tuple[object, ...]] = []
        for insert in self._insert_statements:
            materialized_rows.extend(_expand_insert_rows(insert, self._definition))
        rows = tuple(materialized_rows)
        object.__setattr__(self, "_rows", rows)
        return rows

    @property
    def row_count(self) -> int:
        return self._descriptor.row_count

    @property
    def content_digest(self) -> DigestRef:
        if self._content_digest is not None:
            return self._content_digest
        content_digest = stable_snapshot_rows_digest(self.rows, self._descriptor.columns)
        object.__setattr__(self, "_content_digest", content_digest)
        return content_digest


@dataclass(frozen=True, slots=True)
class RepositoryRefLazySnapshotTableReader:
    _descriptor: "SnapshotTableDescriptor"
    _repository_table_access_provider: RepositoryTableAccessProvider
    _repository_ref: RepositoryRef
    _table_name: str
    _rows: tuple[tuple[object, ...], ...] | None = field(default=None, repr=False)
    _content_digest: DigestRef | None = field(default=None, repr=False)

    def __post_init__(self) -> None:
        if not isinstance(self._descriptor, SnapshotTableDescriptor):
            raise TypeError("_descriptor must be a SnapshotTableDescriptor")
        if not isinstance(self._repository_table_access_provider, RepositoryTableAccessProvider):
            raise TypeError(
                "_repository_table_access_provider must be a RepositoryTableAccessProvider"
            )
        if not isinstance(self._repository_ref, RepositoryRef):
            raise TypeError("_repository_ref must be a RepositoryRef")
        if not isinstance(self._table_name, str) or not self._table_name.strip():
            raise ValueError("_table_name must be a non-empty string")
        object.__setattr__(self, "_table_name", canonical_identifier(self._table_name))
        if self._descriptor.table_name != self._table_name:
            raise ValueError("reader table name must match descriptor table name")

    def descriptor(self) -> "SnapshotTableDescriptor":
        return self._descriptor

    def iter_rows(self) -> Iterator[tuple[object, ...]]:
        yield from self.rows

    def close(self) -> None:
        return None

    def validate_content_digest(self, expected_content_digest: DigestRef | str) -> DigestRef:
        expected = expected_content_digest
        if not isinstance(expected, DigestRef):
            expected = DigestRef.parse(str(expected))
        actual = self.content_digest
        if actual != expected:
            raise ValueError("content digest does not match rows")
        return actual

    @property
    def rows(self) -> tuple[tuple[object, ...], ...]:
        rows = self._rows
        if rows is not None:
            return rows
        session = self._repository_table_access_provider.open_ref(self._repository_ref)
        try:
            reader = session.open_table_reader(self._table_name)
            try:
                rows = tuple(tuple(row) for row in reader.stream_rows())
            finally:
                reader.close()
        finally:
            session.close()
        object.__setattr__(self, "_rows", rows)
        return rows

    @property
    def row_count(self) -> int:
        return self._descriptor.row_count

    @property
    def content_digest(self) -> DigestRef:
        if self._content_digest is not None:
            return self._content_digest
        content_digest = stable_snapshot_rows_digest(self.rows, self._descriptor.columns)
        object.__setattr__(self, "_content_digest", content_digest)
        return content_digest
