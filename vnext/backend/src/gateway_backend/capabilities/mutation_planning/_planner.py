"""Storage mutation planner and eligibility engine."""

from __future__ import annotations

from dataclasses import dataclass

from gateway_backend.artifacts import ArtifactStorePort
from gateway_backend.capabilities.mutation_planning._artifacts import (
    MutationArtifactError,
    publish_change_set_closure,
)
from gateway_backend.capabilities.mutation_planning._changeset import (
    TableMutationDecision,
    build_change_set_closure,
)
from gateway_backend.capabilities.mutation_planning._digest import key_bytes_for_ordering
from gateway_backend.capabilities.mutation_planning.contracts import (
    MutationFailureCode,
    MutationPlanStatus,
    MutationPlanningRequest,
    MutationPlanningResult,
    MutationPolicy,
    MutationTableSnapshot,
    MutationThresholdPolicy,
    StorageMutationPlan,
    TableMutationKind,
    TableMutationSummary,
    compute_mutation_plan_identity_digest,
)
from gateway_backend.capabilities.storage_projection.contracts import (
    CanonicalKeyPolicy,
    OrderedPolicy,
    StorageRuleView,
)

_CONFIRMATION_REASON = "DESTRUCTIVE_TABLE_DELETION"


@dataclass(frozen=True, slots=True)
class _PlannerState:
    request: MutationPlanningRequest
    before_by_name: dict[str, MutationTableSnapshot]
    after_by_name: dict[str, MutationTableSnapshot]
    table_names: tuple[str, ...]


def plan_storage_mutation(
    request: MutationPlanningRequest,
    *,
    artifact_store: ArtifactStorePort | None = None,
) -> MutationPlanningResult:
    context = request.planning_input.context
    if context is not None:
        if context.cancellation_requested() or context.deadline_expired():
            return _failed(MutationFailureCode.FAILED)
    state = _planner_state(request)
    if not state.table_names:
        return _noop_result(request)
    if _all_tables_unchanged(state):
        return _noop_result(request)
    if _has_unsupported_renderer_values(state):
        return _failed(MutationFailureCode.TARGET_CAPABILITY_UNSUPPORTED)
    decisions = tuple(_decision_for_table(state, name) for name in state.table_names)
    summaries = tuple(decision.summary for decision in decisions)
    requires_confirmation = any(
        decision.summary.before_row_count > 0 and decision.summary.after_row_count == 0
        for decision in decisions
        if decision.operation is not TableMutationKind.NOOP
    )
    identity = compute_mutation_plan_identity_digest(request.planning_input)
    if requires_confirmation and not request.destructive_confirmation_granted:
        plan = StorageMutationPlan(
            mutation_plan_identity_digest=identity,
            plan_status=MutationPlanStatus.CONFIRMATION_REQUIRED,
            table_summaries=summaries,
            planning_input=request.planning_input,
            requires_confirmation=True,
            confirmation_reason=_confirmation_reason(decisions),
            failure_code=MutationFailureCode.CONFIRMATION_REQUIRED,
        )
        return MutationPlanningResult(
            status=MutationPlanStatus.CONFIRMATION_REQUIRED,
            plan=plan,
            failure_code=MutationFailureCode.CONFIRMATION_REQUIRED,
        )
    if all(decision.operation is TableMutationKind.NOOP for decision in decisions):
        return _noop_result(request)
    plan = StorageMutationPlan(
        mutation_plan_identity_digest=identity,
        plan_status=MutationPlanStatus.READY,
        table_summaries=summaries,
        planning_input=request.planning_input,
    )
    closure = build_change_set_closure(plan, request, decisions)
    published = None
    if artifact_store is not None:
        try:
            published = publish_change_set_closure(artifact_store, closure)
        except MutationArtifactError:
            return _failed(MutationFailureCode.RESOURCE_EXCEEDED)
    return MutationPlanningResult(
        status=MutationPlanStatus.READY,
        plan=plan,
        change_set_closure=closure,
        published_closure=published,
    )


def _planner_state(request: MutationPlanningRequest) -> _PlannerState:
    before_by_name = {item.manifest_table.name: item for item in request.before_tables}
    after_by_name = {item.manifest_table.name: item for item in request.after_tables}
    names = sorted(set(before_by_name) | set(after_by_name))
    return _PlannerState(
        request=request,
        before_by_name=before_by_name,
        after_by_name=after_by_name,
        table_names=tuple(names),
    )


def _noop_result(request: MutationPlanningRequest) -> MutationPlanningResult:
    identity = compute_mutation_plan_identity_digest(request.planning_input)
    plan = StorageMutationPlan(
        mutation_plan_identity_digest=identity,
        plan_status=MutationPlanStatus.NOOP,
        table_summaries=(),
        planning_input=request.planning_input,
    )
    return MutationPlanningResult(status=MutationPlanStatus.NOOP, plan=plan)


def _failed(code: MutationFailureCode) -> MutationPlanningResult:
    return MutationPlanningResult(status=MutationPlanStatus.FAILED, failure_code=code)


def _all_tables_unchanged(state: _PlannerState) -> bool:
    for name in state.table_names:
        before = state.before_by_name.get(name)
        after = state.after_by_name.get(name)
        if before is None or after is None:
            return False
        if not _table_projection_unchanged(before, after):
            return False
        if _row_diff_counts(before, after)[0] != 0:
            return False
    return True


def _decision_for_table(state: _PlannerState, table_name: str) -> TableMutationDecision:
    before = state.before_by_name.get(table_name)
    after = state.after_by_name.get(table_name)
    before_count = 0 if before is None else len(before.rows)
    after_count = 0 if after is None else len(after.rows)
    if before is None or after is None:
        summary = TableMutationSummary(
            canonical_table=table_name,
            operation=TableMutationKind.REBUILD_TABLE,
            changed_row_count=before_count + after_count,
            before_row_count=before_count,
            after_row_count=after_count,
        )
        return TableMutationDecision(
            canonical_table=table_name,
            operation=TableMutationKind.REBUILD_TABLE,
            summary=summary,
            before_snapshot=before,
            after_snapshot=after,
        )
    if not _table_projection_unchanged(before, after):
        changed, _, _ = _row_diff_counts(before, after)
        summary = TableMutationSummary(
            canonical_table=table_name,
            operation=TableMutationKind.REBUILD_TABLE,
            changed_row_count=max(changed, before_count + after_count),
            before_row_count=before_count,
            after_row_count=after_count,
        )
        return TableMutationDecision(
            canonical_table=table_name,
            operation=TableMutationKind.REBUILD_TABLE,
            summary=summary,
            before_snapshot=before,
            after_snapshot=after,
        )
    changed, inserts, deletes = _row_diff_counts(before, after)
    if changed == 0:
        summary = TableMutationSummary(
            canonical_table=table_name,
            operation=TableMutationKind.NOOP,
            changed_row_count=0,
            before_row_count=before_count,
            after_row_count=after_count,
        )
        return TableMutationDecision(
            canonical_table=table_name,
            operation=TableMutationKind.NOOP,
            summary=summary,
            before_snapshot=before,
            after_snapshot=after,
        )
    operation = _operation_kind(
        state.request.planning_input.mutation_policy,
        threshold_policy=state.request.planning_input.threshold_policy,
        before=before,
        after=after,
        changed_row_count=changed,
        before_row_count=before_count,
        after_row_count=after_count,
    )
    summary = TableMutationSummary(
        canonical_table=table_name,
        operation=operation,
        changed_row_count=changed,
        before_row_count=before_count,
        after_row_count=after_count,
    )
    return TableMutationDecision(
        canonical_table=table_name,
        operation=operation,
        summary=summary,
        before_snapshot=before,
        after_snapshot=after,
    )


def _operation_kind(
    policy: MutationPolicy,
    *,
    threshold_policy: MutationThresholdPolicy,
    before: MutationTableSnapshot,
    after: MutationTableSnapshot,
    changed_row_count: int,
    before_row_count: int,
    after_row_count: int,
) -> TableMutationKind:
    if policy is MutationPolicy.REBUILD_ALWAYS:
        return TableMutationKind.REBUILD_TABLE
    if before_row_count == 0 and after_row_count > 0:
        return TableMutationKind.REBUILD_TABLE
    if not _patch_eligible(
        before,
        after,
        changed_row_count=changed_row_count,
        before_row_count=before_row_count,
        after_row_count=after_row_count,
        threshold=threshold_policy,
    ):
        return TableMutationKind.REBUILD_TABLE
    return TableMutationKind.PATCH_DML


def _patch_eligible(
    before: MutationTableSnapshot,
    after: MutationTableSnapshot,
    *,
    changed_row_count: int,
    before_row_count: int,
    after_row_count: int,
    threshold: MutationThresholdPolicy,
) -> bool:
    if before_row_count == 0:
        return False
    if not _keyed_patchable(before.storage_view) or not _keyed_patchable(after.storage_view):
        return False
    if changed_row_count > threshold.max_patch_changed_rows:
        return False
    max_rows = max(before_row_count, after_row_count, 1)
    if changed_row_count * 100 > max_rows * 5:
        return False
    return True


def _keyed_patchable(view: StorageRuleView) -> bool:
    if view.canonical_key_policy in {
        CanonicalKeyPolicy.NONE,
        CanonicalKeyPolicy.EXPLICIT_KEYLESS,
    }:
        return False
    if view.ordered_policy is not OrderedPolicy.NONE:
        return False
    return bool(view.canonical_key_columns)


def _table_projection_unchanged(
    before: MutationTableSnapshot,
    after: MutationTableSnapshot,
) -> bool:
    before_table = before.manifest_table
    after_table = after.manifest_table
    if before_table.canonical_schema_digest != after_table.canonical_schema_digest:
        return False
    if before_table.canonical_key_columns != after_table.canonical_key_columns:
        return False
    if before_table.retained_columns != after_table.retained_columns:
        return False
    return _storage_views_compatible(before.storage_view, after.storage_view)


def _storage_views_compatible(left: StorageRuleView, right: StorageRuleView) -> bool:
    return (
        left.canonical_key_policy == right.canonical_key_policy
        and left.ordered_policy == right.ordered_policy
        and left.retained_columns == right.retained_columns
        and left.canonical_key_columns == right.canonical_key_columns
        and left.dropped_columns == right.dropped_columns
        and left.structural_columns == right.structural_columns
    )


def _row_diff_counts(
    before: MutationTableSnapshot,
    after: MutationTableSnapshot,
) -> tuple[int, int, int]:
    before_rows = {key_bytes_for_ordering(row.key): row for row in before.rows}
    after_rows = {key_bytes_for_ordering(row.key): row for row in after.rows}
    changed = 0
    inserts = 0
    deletes = 0
    for key, before_row in before_rows.items():
        after_row = after_rows.get(key)
        if after_row is None:
            deletes += 1
            changed += 1
            continue
        if before_row.row_digest != after_row.row_digest:
            changed += 1
    for key in after_rows:
        if key not in before_rows:
            inserts += 1
            changed += 1
    return changed, inserts, deletes


def _has_unsupported_renderer_values(state: _PlannerState) -> bool:
    for snapshot in (*state.before_by_name.values(), *state.after_by_name.values()):
        for row in snapshot.rows:
            for _, cell in (*row.key.columns, *row.image.columns):
                if cell.get("kind") == "source-literal-anomaly":
                    return True
    return False


def _confirmation_reason(decisions: tuple[TableMutationDecision, ...]) -> str:
    tables = sorted(
        decision.canonical_table
        for decision in decisions
        if decision.summary.before_row_count > 0 and decision.summary.after_row_count == 0
    )
    return f"{_CONFIRMATION_REASON}:{','.join(tables)}"
