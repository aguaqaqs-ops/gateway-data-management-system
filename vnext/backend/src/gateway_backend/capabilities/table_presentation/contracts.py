"""Frozen SQL comments. These values never participate in canonical identity."""

from __future__ import annotations

from collections.abc import Mapping, Iterable
from dataclasses import dataclass
from typing import Any, Protocol


def normalize_comment(value: str | None) -> str | None:
    if value is None:
        return None
    if type(value) is not str or "\x00" in value:
        raise ValueError("comment must be a string without NUL or null")
    return value if value.strip() else None


@dataclass(frozen=True, slots=True)
class ColumnPresentation:
    name: str
    comment: str | None

    def __post_init__(self) -> None:
        _name(self.name)
        object.__setattr__(self, "comment", normalize_comment(self.comment))


@dataclass(frozen=True, slots=True)
class TablePresentation:
    table_name: str
    comment: str | None
    columns: tuple[ColumnPresentation, ...]

    def __post_init__(self) -> None:
        _name(self.table_name)
        object.__setattr__(self, "comment", normalize_comment(self.comment))
        if type(self.columns) is not tuple or any(type(c) is not ColumnPresentation for c in self.columns):
            raise ValueError("presentation columns must be a tuple of ColumnPresentation")
        if len({c.name for c in self.columns}) != len(self.columns):
            raise ValueError("presentation columns must not repeat names")


@dataclass(frozen=True, slots=True)
class PresentationMetadata:
    tables: tuple[TablePresentation, ...] = ()

    def __post_init__(self) -> None:
        if type(self.tables) is not tuple or any(type(t) is not TablePresentation for t in self.tables):
            raise ValueError("presentation tables must be a tuple of TablePresentation")
        names = [t.table_name for t in self.tables]
        if names != sorted(set(names), key=lambda name: name.encode("utf-8")):
            raise ValueError("presentation tables must have unique names in UTF-8 order")

    def project(self, tables: Iterable[tuple[str, tuple[str, ...]]]) -> PresentationMetadata:
        source = {t.table_name: t for t in self.tables}
        output = []
        for name, columns in sorted(tables, key=lambda t: t[0].encode("utf-8")):
            table = source.get(name)
            comments = {} if table is None else {c.name: c.comment for c in table.columns}
            output.append(TablePresentation(name, None if table is None else table.comment,
                tuple(ColumnPresentation(c, comments.get(c)) for c in columns)))
        return PresentationMetadata(tuple(output))

    def require_coverage(self, tables: Mapping[str, tuple[str, ...]]) -> None:
        if {t.table_name: tuple(c.name for c in t.columns) for t in self.tables} != dict(tables):
            raise ValueError("presentation must cover exactly the canonical tables and columns in DDL order")

    def to_document(self) -> dict[str, object]:
        return {"tables": [{"table_name": t.table_name, "comment": t.comment,
            "columns": [{"name": c.name, "comment": c.comment} for c in t.columns]} for t in self.tables]}

    @classmethod
    def from_document(cls, value: object) -> PresentationMetadata:
        document = _object(value, {"tables"})
        if type(document["tables"]) is not list:
            raise ValueError("presentation tables must be an array")
        tables = []
        for raw in document["tables"]:
            table = _object(raw, {"table_name", "comment", "columns"})
            if type(table["columns"]) is not list:
                raise ValueError("presentation columns must be an array")
            columns = []
            for item in table["columns"]:
                column = _object(item, {"name", "comment"})
                columns.append(ColumnPresentation(column["name"], column["comment"]))
            tables.append(TablePresentation(table["table_name"], table["comment"], tuple(columns)))
        return cls(tuple(tables))


def _object(value: object, keys: set[str]) -> dict[str, Any]:
    if type(value) is not dict or set(value) != keys:
        raise ValueError("presentation object fields are invalid")
    return value


def _name(value: str) -> None:
    if type(value) is not str or not value or "\x00" in value:
        raise ValueError("presentation name must be a nonempty string without NUL")


class PresentationColumn(Protocol):
    """Read-only canonical descriptor fields consumed by the presentation owner."""
    @property
    def name(self) -> str: ...
    @property
    def scalar_type(self) -> str | None: ...
    @property
    def nullable(self) -> bool: ...


@dataclass(frozen=True, slots=True)
class PresentedColumn:
    name: str
    display_name: str
    scalar_type: str | None
    nullable: bool
    present_in: str
    pinned: bool
    display_order: int
