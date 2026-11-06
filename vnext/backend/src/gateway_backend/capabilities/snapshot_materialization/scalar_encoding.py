"""Small Repository catalog metadata mapping shared by the real Arrow readers."""

from __future__ import annotations

from dataclasses import dataclass
from gateway_shared_kernel import DeclaredType, DeclaredTypeKind, canonicalize_identifier
from gateway_backend.capabilities.snapshot_materialization.sql_declared_types import declared_type_for_sql_spelling
from gateway_backend.capabilities.snapshot_materialization.contracts import (
    RepositoryColumn, SqlDeclaredTypeMappingError, enum_set_labels_for_sql_spelling,
)
from gateway_backend.capabilities.table_access.contracts import SourceColumnDescriptor, SqlLogicalType

_STRING_TYPE = DeclaredType(kind=DeclaredTypeKind.STRING)


@dataclass(frozen=True, slots=True)
class MappedRepositoryColumn:
    source: SourceColumnDescriptor
    unknown_family: bool


def map_repository_column(column: RepositoryColumn) -> MappedRepositoryColumn:
    canonical = canonicalize_identifier(column.name)
    display = column.display_name if column.display_name is not None else column.name
    nullable = True if column.nullable is None else column.nullable
    spelling = column.scalar_type if column.scalar_type is not None else column.raw_type
    enum_set = None
    if spelling:
        try:
            enum_set = enum_set_labels_for_sql_spelling(spelling)
        except SqlDeclaredTypeMappingError:
            enum_set = None
    if enum_set is not None and enum_set[0] == "SET":
        source = SourceColumnDescriptor(
            display_name=display,
            canonical_name=canonical,
            ordinal=column.ordinal,
            sql_type=spelling if spelling else "UNKNOWN",
            logical_type=SqlLogicalType.SET,
            declared_type=None,
            nullable=nullable,
            enum_or_set_labels=enum_set[1],
        )
        return MappedRepositoryColumn(source=source, unknown_family=False)
    declared, unknown = _declared_type_for(spelling)
    if enum_set is not None and enum_set[0] == "ENUM":
        source = SourceColumnDescriptor(
            display_name=display,
            canonical_name=canonical,
            ordinal=column.ordinal,
            sql_type=spelling if spelling else "UNKNOWN",
            logical_type=SqlLogicalType.ENUM,
            declared_type=declared,
            nullable=nullable,
            enum_or_set_labels=enum_set[1],
        )
        return MappedRepositoryColumn(source=source, unknown_family=unknown)
    source = SourceColumnDescriptor(
        display_name=display,
        canonical_name=canonical,
        ordinal=column.ordinal,
        sql_type=spelling if spelling else "UNKNOWN",
        logical_type=SqlLogicalType.STANDARD,
        declared_type=declared,
        nullable=nullable,
    )
    return MappedRepositoryColumn(source=source, unknown_family=unknown)


def _declared_type_for(spelling: str | None) -> tuple[DeclaredType, bool]:
    if spelling is None or spelling == "":
        return _STRING_TYPE, True
    try:
        return declared_type_for_sql_spelling(spelling), False
    except SqlDeclaredTypeMappingError:
        return _STRING_TYPE, True


