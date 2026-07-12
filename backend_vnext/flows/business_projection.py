from __future__ import annotations

from collections.abc import Iterable

from ..capabilities.business_projection import (
    BusinessProjectionAssembler,
    BusinessProjectionInput,
    BusinessProjectionResult,
    BusinessProjectionTable,
)
from ..capabilities.comparison.models import ComparisonComputeInput
from ..capabilities.snapshot_materialization.models import SnapshotTable, SnapshotTableSet
from ..capabilities.surface_assembly import ComparisonSurface
from ..core.identifiers import canonical_identifier


DEFAULT_PROJECTION_ROW_TABLE_NAMES: tuple[str, ...] = ("net_cfg", "device", "app_cfg")


def assemble_business_projection_for_surface(
    *,
    comparison_input: ComparisonComputeInput,
    comparison_surface: ComparisonSurface,
    projection_assembler: BusinessProjectionAssembler | None = None,
    row_table_names: Iterable[str] = DEFAULT_PROJECTION_ROW_TABLE_NAMES,
) -> BusinessProjectionResult:
    request = build_business_projection_input_for_surface(
        comparison_input=comparison_input,
        comparison_surface=comparison_surface,
        row_table_names=row_table_names,
    )
    return (projection_assembler or BusinessProjectionAssembler()).assemble(request)


def build_business_projection_input_for_surface(
    *,
    comparison_input: ComparisonComputeInput,
    comparison_surface: ComparisonSurface,
    row_table_names: Iterable[str] = DEFAULT_PROJECTION_ROW_TABLE_NAMES,
) -> BusinessProjectionInput:
    if not isinstance(comparison_input, ComparisonComputeInput):
        raise TypeError("comparison_input must be a ComparisonComputeInput")
    if not isinstance(comparison_surface, ComparisonSurface):
        raise TypeError("comparison_surface must be a ComparisonSurface")

    visible_table_names = tuple(table.table_name for table in comparison_surface.tables)
    row_table_set = {
        canonical_identifier(table_name)
        for table_name in row_table_names
        if canonical_identifier(table_name)
    }
    return BusinessProjectionInput(
        before_tables=_projection_tables_from_table_set(
            comparison_input.before.table_set_ref,
            row_table_names=row_table_set,
        ),
        current_tables=_projection_tables_from_table_set(
            comparison_input.current.table_set_ref,
            row_table_names=row_table_set,
        ),
        surface_table_names=visible_table_names,
    )


def _projection_tables_from_table_set(
    table_set: SnapshotTableSet | None,
    *,
    row_table_names: set[str],
) -> tuple[BusinessProjectionTable, ...]:
    if table_set is None:
        return ()
    return tuple(
        _projection_table_from_snapshot_table(
            table,
            load_rows=table_name in row_table_names,
        )
        for table_name, table in sorted(table_set.tables.items())
    )


def _projection_table_from_snapshot_table(
    table: SnapshotTable,
    *,
    load_rows: bool,
) -> BusinessProjectionTable:
    descriptor = table.descriptor
    columns = tuple(column.name for column in descriptor.columns)
    rows = ()
    if load_rows:
        rows = tuple(
            dict(zip(columns, row, strict=False))
            for row in table.reader.iter_rows()
        )
    return BusinessProjectionTable(
        table_name=descriptor.table_name,
        columns=columns,
        rows=rows,
        display_name=descriptor.display_table_name,
        rows_loaded=load_rows,
    )


__all__ = [
    "DEFAULT_PROJECTION_ROW_TABLE_NAMES",
    "assemble_business_projection_for_surface",
    "build_business_projection_input_for_surface",
]
