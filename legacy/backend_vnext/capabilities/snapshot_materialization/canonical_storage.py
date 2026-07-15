from __future__ import annotations

from collections.abc import Sequence

from ...core.identifiers import canonical_identifier
from .models import (
    SnapshotMaterializationStage,
    SnapshotSummary,
    SnapshotTableDescriptor,
)


def logical_to_physical_table_map(summary: SnapshotSummary) -> dict[str, str]:
    """Return the repository physical table that backs each logical summary table."""

    descriptors = tuple(summary.tables)
    table_names = {descriptor.table_name for descriptor in descriptors}
    mapping = {descriptor.table_name: descriptor.table_name for descriptor in descriptors}
    if summary.materialization_stage != SnapshotMaterializationStage.FINAL.value:
        return mapping

    grouped: dict[str, list[SnapshotTableDescriptor]] = {}
    for descriptor in descriptors:
        if descriptor.canonical_artifact_ref is None:
            continue
        grouped.setdefault(descriptor.canonical_artifact_ref, []).append(descriptor)

    for group in grouped.values():
        if not group:
            continue
        canonical_table = sorted(
            group,
            key=lambda descriptor: (
                descriptor.table_name.casefold(),
                descriptor.table_name,
            ),
        )[0].table_name
        if canonical_table not in table_names:
            continue
        for descriptor in group:
            mapping[descriptor.table_name] = canonical_table
    return mapping


def physical_table_names_for_summary(
    summary: SnapshotSummary,
    *,
    requested_tables: Sequence[str] | None = None,
) -> tuple[str, ...]:
    logical_to_physical = logical_to_physical_table_map(summary)
    if not requested_tables:
        return tuple(sorted(set(logical_to_physical.values())))

    summary_table_names = set(logical_to_physical)
    selected: set[str] = set()
    for value in requested_tables:
        logical_name = canonical_identifier(value)
        if not logical_name:
            continue
        if logical_name not in summary_table_names:
            raise ValueError(f"requested table not found: {value}")
        selected.add(logical_to_physical[logical_name])
    return tuple(sorted(selected))
