"""Resolve comparison requests into deterministic table work."""

from __future__ import annotations

from gateway_shared_kernel import canonicalize_identifier

from gateway_backend.capabilities.comparison.contracts import (
    ArtifactScope,
    BlankRowPolicy,
    ComparisonPlan,
    ComparisonRequest,
    ComparisonStorageFacts,
    _ComparisonTablePolicy,
    FailedResult,
    KeylessPolicy,
    OrderedTablePolicy,
    TableComparisonTask,
    BoundSnapshotInput,
)
from gateway_backend.capabilities.snapshot_materialization.contracts import (
    SnapshotTable,
    SnapshotTableDescriptor,
)
from gateway_backend.capabilities.table_rules import resolve_comparison_rule_view
from gateway_backend.capabilities.table_rules.contracts import (
    CanonicalKeyPolicy,
    ComparisonRole,
    ComparisonRuleView,
    TableArtifactScope,
)


def plan_comparison(request: ComparisonRequest) -> ComparisonPlan | FailedResult:
    """Plan a pair using the caller's runtime ComparisonRuleSet."""
    if type(request) is not ComparisonRequest:
        raise TypeError("request must be ComparisonRequest")
    before_descriptors = _descriptor_map(request.before)
    current_descriptors = _descriptor_map(request.current)
    before_tables = _table_map(request.before)
    current_tables = _table_map(request.current)
    before_storage = _storage_view_map(request.before)
    current_storage = _storage_view_map(request.current)
    tasks: list[TableComparisonTask] = []

    for table_name in sorted(before_descriptors.keys() | current_descriptors.keys()):
        before_descriptor = before_descriptors.get(table_name)
        current_descriptor = current_descriptors.get(table_name)
        before_view = _rule_view(request, table_name, before_descriptor)
        current_view = _rule_view(request, table_name, current_descriptor)
        if before_view is None and current_view is None:
            continue
        active_view = current_view or before_view
        assert active_view is not None
        policy = _comparison_policy(
            active_view,
            before_view=before_view,
            current_view=current_view,
            before_descriptor=before_descriptor,
            current_descriptor=current_descriptor,
            storage_facts_before=before_storage.get(table_name),
            storage_facts_current=current_storage.get(table_name),
        )
        tasks.append(
            TableComparisonTask(
                table_name=table_name,
                before_descriptor=before_descriptor,
                current_descriptor=current_descriptor,
                before_table=before_tables.get(table_name),
                current_table=current_tables.get(table_name),
                artifact_scope=_artifact_scope(active_view),
                policy=policy,
            )
        )

    return ComparisonPlan(
        pair_id=request.pair_id,
        before=request.before,
        current=request.current,
        rule_set=request.rule_set,
        mode=request.mode,
        tasks=tuple(tasks),
        options=request.options,
        contract_versions=request.contract_versions,
    )


def _rule_view(
    request: ComparisonRequest,
    table_name: str,
    descriptor: SnapshotTableDescriptor | None,
) -> ComparisonRuleView | None:
    primary_key = () if descriptor is None else descriptor.primary_key_columns
    return resolve_comparison_rule_view(
        request.rule_set,
        table_name,
        primary_key_columns=primary_key,
    )


def _comparison_policy(
    view: ComparisonRuleView,
    *,
    before_view: ComparisonRuleView | None,
    current_view: ComparisonRuleView | None,
    before_descriptor: SnapshotTableDescriptor | None,
    current_descriptor: SnapshotTableDescriptor | None,
    storage_facts_before: ComparisonStorageFacts | None,
    storage_facts_current: ComparisonStorageFacts | None,
) -> _ComparisonTablePolicy:
    keyless_fallback = (
        view.comparison_role is ComparisonRole.STANDARD
        and storage_facts_before is not None
        and storage_facts_current is not None
        and storage_facts_before.storage_rule_view.canonical_key_policy
        is CanonicalKeyPolicy.DDL_PRIMARY_KEY_OR_KEYLESS
        and storage_facts_current.storage_rule_view.canonical_key_policy
        is CanonicalKeyPolicy.DDL_PRIMARY_KEY_OR_KEYLESS
    )
    ordered_policy = None
    if view.comparison_role is ComparisonRole.ORDERED:
        ordered = view.ordered
        assert ordered is not None
        ordered_identity_columns = {
            *ordered.stable_key_candidates,
            *ordered.row_identity_key,
            ordered.position_column,
        }
        ordered_policy = OrderedTablePolicy(
            policy_id="ordered-runtime-v1",
            policy_version=view.comparison_rule_digest.value,
            order_key=(ordered.position_column,),
            row_identity_key=ordered.row_identity_key or None,
            stable_key_candidates=ordered.stable_key_candidates,
            value_columns=_shared_columns(
                before_descriptor,
                current_descriptor,
                excluded=set(view.compare_excluded_columns) | ordered_identity_columns,
            ),
            blank_row_policy=BlankRowPolicy(ordered.blank_row_policy),
            move_policy="STABLE_KEY_RELATIVE_ORDER_V1",
            ambiguity_policy="DEGRADE_ON_AMBIGUITY",
            tail_change_policy="INTERVAL_OR_ROW_V1",
            table_processing_mode_policy="ORDERED_MODE_V1",
        )
    return _ComparisonTablePolicy(
        table_name=view.canonical_table,
        compare_excluded_columns=view.compare_excluded_columns,
        keyless_policy=(
            KeylessPolicy.FULL_ROW_DIGEST_SET_DIFF
            if keyless_fallback
            else KeylessPolicy.DEGRADE_NO_COMPARE_KEY
        ),
        allow_keyless_key_transition=keyless_fallback,
        policy_version=view.comparison_rule_digest.value,
        ordered_policy=ordered_policy,
        effective_key_before=() if before_view is None else before_view.effective_key_columns,
        effective_key_current=() if current_view is None else current_view.effective_key_columns,
        comparison_role=view.comparison_role.value,
        storage_facts_before=storage_facts_before,
        storage_facts_current=storage_facts_current,
    )


def _artifact_scope(view: ComparisonRuleView) -> ArtifactScope:
    return (
        ArtifactScope.UPDATE_ONLY
        if view.artifact_scope is TableArtifactScope.UPDATE_ONLY
        else ArtifactScope.ALL_CHANGES
    )


def _shared_columns(
    before: SnapshotTableDescriptor | None,
    current: SnapshotTableDescriptor | None,
    *,
    excluded: set[str],
) -> tuple[str, ...]:
    before_names = set() if before is None else {
        canonicalize_identifier(column.name) for column in before.columns
    }
    current_names = set() if current is None else {
        canonicalize_identifier(column.name) for column in current.columns
    }
    names = before_names & current_names if before is not None and current is not None else before_names | current_names
    return tuple(sorted(names - excluded))


def _descriptor_map(bound: BoundSnapshotInput) -> dict[str, SnapshotTableDescriptor]:
    return {
        canonicalize_identifier(table.table_name): table
        for table in bound.summary.tables
    }


def _table_map(bound: BoundSnapshotInput) -> dict[str, SnapshotTable]:
    table_set = bound.table_set
    if table_set is None:
        return {}
    return {
        canonicalize_identifier(table.descriptor.table_name): table
        for table in table_set.tables
    }


def _storage_view_map(bound: BoundSnapshotInput) -> dict[str, ComparisonStorageFacts]:
    return {item.storage_rule_view.canonical_table: item for item in bound.storage_facts}
