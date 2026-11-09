"""The single table-level mutation threshold shared by both planning paths."""

from __future__ import annotations

from decimal import Decimal

from gateway_backend.capabilities.mutation_planning.contracts import (
    MutationPolicy,
    MutationThresholdPolicy,
    TableMutationKind,
)
from gateway_backend.capabilities.storage_projection.contracts import (
    CanonicalKeyPolicy, OrderedPolicy, StorageRuleView,
)


def storage_views_compatible(left: StorageRuleView, right: StorageRuleView) -> bool:
    return (
        left.canonical_key_policy == right.canonical_key_policy
        and left.ordered_policy == right.ordered_policy
        and left.retained_columns == right.retained_columns
        and left.canonical_key_columns == right.canonical_key_columns
        and left.dropped_columns == right.dropped_columns
        and left.structural_columns == right.structural_columns
    )


def keyed_patchable(view: StorageRuleView) -> bool:
    return (
        view.canonical_key_policy not in {CanonicalKeyPolicy.NONE, CanonicalKeyPolicy.EXPLICIT_KEYLESS}
        and view.ordered_policy in {OrderedPolicy.NONE, OrderedPolicy.GID_NO_V1}
        and bool(view.canonical_key_columns)
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
