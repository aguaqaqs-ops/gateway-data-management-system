from __future__ import annotations

from collections.abc import Sequence

from ..snapshot_materialization.canonical_storage import (
    logical_to_physical_table_map,
    physical_table_names_for_summary,
)
from ..snapshot_materialization.models import (
    SnapshotMaterializationResult,
    SnapshotTable,
)
from .providers import RepositoryImportPlanTable


def select_physical_snapshot_tables(
    result: SnapshotMaterializationResult,
    *,
    requested_tables: Sequence[str] | None = None,
) -> tuple[SnapshotTable, ...]:
    if result.table_set is None:
        raise ValueError("snapshot materialization result must include table_set")
    table_names = physical_table_names_for_summary(
        result.summary,
        requested_tables=requested_tables,
    )
    table_map = result.table_set.tables
    missing = sorted(table_name for table_name in table_names if table_name not in table_map)
    if missing:
        raise ValueError(f"physical table(s) not found in table_set: {missing}")
    return tuple(table_map[table_name] for table_name in table_names)


def build_physical_repository_import_plan_tables(
    result: SnapshotMaterializationResult,
) -> tuple[RepositoryImportPlanTable, ...]:
    return tuple(
        RepositoryImportPlanTable(
            table_name=table.descriptor.table_name,
            descriptor=table.descriptor,
        )
        for table in select_physical_snapshot_tables(result)
    )
