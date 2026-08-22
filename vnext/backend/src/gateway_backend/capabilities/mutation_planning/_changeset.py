"""ChangeSet closure construction from planner decisions."""

from __future__ import annotations

from dataclasses import dataclass

from gateway_backend.capabilities.mutation_planning._digest import key_bytes_for_ordering
from gateway_backend.capabilities.mutation_planning.contracts import (
    CANONICAL_ENCODING_VERSION,
    CHANGE_SET_ARTIFACT_CONTRACT_VERSION,
    CHANGE_SET_MANIFEST_CONTRACT_VERSION,
    MUTATION_CONTRACT_VERSION,
    ChangeSetClosure,
    ChangeSetManifest,
    ChangeSetMutation,
    MutationPlanningRequest,
    MutationTableSnapshot,
    RowMutationOperation,
    StorageMutationPlan,
    TableMutationKind,
    TableMutationSummary,
    compute_change_set_digest,
    validate_change_set_ordering,
)


@dataclass(frozen=True, slots=True)
class TableMutationDecision:
    canonical_table: str
    operation: TableMutationKind
    summary: TableMutationSummary
    before_snapshot: MutationTableSnapshot | None
    after_snapshot: MutationTableSnapshot | None


def build_change_set_closure(
    plan: StorageMutationPlan,
    request: MutationPlanningRequest,
    decisions: tuple[TableMutationDecision, ...],
) -> ChangeSetClosure:
    mutations: list[ChangeSetMutation] = []
    for decision in decisions:
        if decision.operation is TableMutationKind.NOOP:
            continue
        mutations.extend(_mutations_for_table(decision))
    ordered = tuple(mutations)
    validate_change_set_ordering(ordered)
    binding = request.planning_input.projection_binding
    renderer = request.planning_input.renderer_capability
    summaries = tuple(decision.summary for decision in decisions)
    change_set_digest = compute_change_set_digest(ordered)
    manifest = ChangeSetManifest(
        manifest_contract_version=CHANGE_SET_MANIFEST_CONTRACT_VERSION,
        artifact_contract_version=CHANGE_SET_ARTIFACT_CONTRACT_VERSION,
        mutation_contract_version=MUTATION_CONTRACT_VERSION,
        canonical_encoding_version=CANONICAL_ENCODING_VERSION,
        source_identity_digest=request.planning_input.source_identity.source_identity_digest,
        base_repository_ref_digest=request.planning_input.repository_base.base_repository_ref_digest,
        target_identity=renderer,
        storage_projection_digest=binding,
        table_ruleset_digest=binding.table_ruleset_digest,
        mutation_policy=request.planning_input.mutation_policy,
        threshold_policy=request.planning_input.threshold_policy,
        table_summaries=summaries,
        change_set_digest=change_set_digest,
        renderer_capability=renderer,
    )
    return ChangeSetClosure(manifest=manifest, mutations=ordered)


def _mutations_for_table(decision: TableMutationDecision) -> tuple[ChangeSetMutation, ...]:
    table = decision.canonical_table
    if decision.operation is TableMutationKind.REBUILD_TABLE:
        return _rebuild_mutations(table, decision.before_snapshot, decision.after_snapshot)
    if decision.operation is TableMutationKind.PATCH_DML:
        return _patch_mutations(table, decision.before_snapshot, decision.after_snapshot)
    return ()


def _rebuild_mutations(
    table: str,
    before: MutationTableSnapshot | None,
    after: MutationTableSnapshot | None,
) -> tuple[ChangeSetMutation, ...]:
    mutations: list[ChangeSetMutation] = []
    if before is not None:
        for row in before.rows:
            mutations.append(
                ChangeSetMutation(
                    canonical_table=table,
                    operation=RowMutationOperation.DELETE,
                    canonical_storage_key=row.key,
                    before_row_digest=row.row_digest,
                )
            )
    if after is not None:
        for row in after.rows:
            mutations.append(
                ChangeSetMutation(
                    canonical_table=table,
                    operation=RowMutationOperation.INSERT,
                    canonical_storage_key=row.key,
                    after_image=row.image,
                )
            )
    return tuple(mutations)


def _patch_mutations(
    table: str,
    before: MutationTableSnapshot | None,
    after: MutationTableSnapshot | None,
) -> tuple[ChangeSetMutation, ...]:
    before_rows = (
        {}
        if before is None
        else {key_bytes_for_ordering(row.key): row for row in before.rows}
    )
    after_rows = (
        {}
        if after is None
        else {key_bytes_for_ordering(row.key): row for row in after.rows}
    )
    mutations: list[ChangeSetMutation] = []
    for key in sorted(before_rows.keys()):
        before_row = before_rows[key]
        after_row = after_rows.get(key)
        if after_row is None:
            mutations.append(
                ChangeSetMutation(
                    canonical_table=table,
                    operation=RowMutationOperation.DELETE,
                    canonical_storage_key=before_row.key,
                    before_row_digest=before_row.row_digest,
                )
            )
            continue
        if before_row.row_digest != after_row.row_digest:
            mutations.append(
                ChangeSetMutation(
                    canonical_table=table,
                    operation=RowMutationOperation.UPDATE,
                    canonical_storage_key=before_row.key,
                    before_row_digest=before_row.row_digest,
                    after_image=after_row.image,
                )
            )
    for key in sorted(after_rows.keys()):
        if key not in before_rows:
            after_row = after_rows[key]
            mutations.append(
                ChangeSetMutation(
                    canonical_table=table,
                    operation=RowMutationOperation.INSERT,
                    canonical_storage_key=after_row.key,
                    after_image=after_row.image,
                )
            )
    return tuple(mutations)
