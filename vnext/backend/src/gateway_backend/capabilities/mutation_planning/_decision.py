"""The single table-level mutation threshold shared by both planning paths."""

from __future__ import annotations

from decimal import Decimal

from gateway_backend.capabilities.mutation_planning.contracts import (
    MutationPolicy,
    MutationThresholdPolicy,
    TableMutationKind,
)


def choose_mutation_kind(
    *, policy: MutationPolicy, threshold: MutationThresholdPolicy,
    patchable: bool, before_rows: int, after_rows: int, changed_rows: int,
) -> TableMutationKind:
    if changed_rows == 0:
        return TableMutationKind.NOOP
    if policy is MutationPolicy.REBUILD_ALWAYS or before_rows == 0 or not patchable:
        return TableMutationKind.REBUILD_TABLE
    if changed_rows > threshold.max_patch_changed_rows:
        return TableMutationKind.REBUILD_TABLE
    numerator, denominator = Decimal(threshold.max_patch_change_ratio).as_integer_ratio()
    if changed_rows * denominator > max(before_rows, after_rows, 1) * numerator:
        return TableMutationKind.REBUILD_TABLE
    return TableMutationKind.PATCH_DML
