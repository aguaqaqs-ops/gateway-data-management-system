"""Channel classification depends on the actual side's table comment."""

import pytest
from contextlib import closing
from dataclasses import replace

from gateway_backend.capabilities.table_rules import (
    CanonicalKeyPolicy, ComparisonRole, OrderedPolicy, comparison_rule_set, is_ordered_reference_table,
    migrated_table_ruleset_snapshot, parse_channel_table_name, resolve_comparison_rule_view,
    resolve_table_rule,
)
from gateway_backend.capabilities.storage_projection.view import derive_storage_rule_view
from tests.support.storage_projection import int_column, table_input
from tests.support.comparison_cache_inputs import complete_canonical_bound
from tests.support.comparison_s3_e_live import canonical_bound
from gateway_backend.capabilities.comparison import (
    ComparisonPlan, ComparisonRequest, ComparisonTableStatus, DetailedFactsResult, plan_comparison,
)
from gateway_backend.capabilities.comparison.production import compare_plan_native
from gateway_backend.capabilities.comparison.task_input import NotCacheable, TableTaskIdentity, build_table_task_identity


@pytest.mark.parametrize(("name", "expected"), [
    ("b01_n002_x", (1, "n", 2, "x")),
    ("B12_C34_foo_bar", (12, "c", 34, "foo_bar")),
    ("b9007199254740992_n1_x", None),
    ("b1_c9007199254740992_x", None),
    ("b1_n1_", None),
    ("b-1_n1_x", None),
])
def test_channel_name_bounds_and_normalization(name: str, expected: tuple[int, str, int, str] | None) -> None:
    parsed = parse_channel_table_name(name)
    assert (None if parsed is None else (parsed.board, parsed.kind, parsed.channel_no, parsed.suffix)) == expected


@pytest.mark.parametrize(("name", "comment", "ordered"), [
    ("b12_c34_any", "串口引用表", True),
    ("b1_n2_custom", "引用表", True),
    ("b1_n2_iec104_syx_list", None, False),
    ("b1_n2_iec104_syx_list", "普通表", False),
    ("b9007199254740992_n2_x", "引用表", False),
    ("other", "引用表", False),
])
def test_reference_rule_requires_actual_comment(name: str, comment: str | None, ordered: bool) -> None:
    assert is_ordered_reference_table(name, comment) is ordered
    view = resolve_comparison_rule_view(comparison_rule_set(migrated_table_ruleset_snapshot()),
        name, table_comment=comment)
    assert view is not None
    assert (view.comparison_role is ComparisonRole.ORDERED) is ordered


@pytest.mark.parametrize("columns", [("gid",), ("no",), ("value",)])
def test_reference_table_missing_ordered_columns_keeps_ddl_storage(columns: tuple[str, ...]) -> None:
    _, binding = table_input("b12_c34_custom", columns=tuple(int_column(c) for c in columns),
        primary_key_columns=(columns[0],), rows=())
    record = resolve_table_rule(migrated_table_ruleset_snapshot(), binding.descriptor.table_name,
        table_comment="引用表", primary_key_columns=binding.descriptor.primary_key_columns).record
    view = derive_storage_rule_view(record, binding.descriptor)
    assert view is not None
    assert view.canonical_key_policy is CanonicalKeyPolicy.DDL_PRIMARY_KEY_OR_KEYLESS
    assert view.ordered_policy is OrderedPolicy.NONE
    assert view.retained_columns == columns
    assert view.canonical_key_columns == (columns[0],)


def test_same_rows_reference_classification_flip_degrades_and_cannot_reuse_comparison() -> None:
    ddl = "CREATE TABLE b1_c2_custom (id INT PRIMARY KEY, value INT)"
    before = complete_canonical_bound(canonical_bound(ddl + " COMMENT='普通'; INSERT INTO b1_c2_custom VALUES (1, 2);"))
    current = complete_canonical_bound(canonical_bound(ddl + " COMMENT='引用表'; INSERT INTO b1_c2_custom VALUES (1, 2);"))
    rules = comparison_rule_set(migrated_table_ruleset_snapshot())
    plan = plan_comparison(ComparisonRequest(pair_id="classification-flip", before=before, current=current, rule_set=rules))
    assert isinstance(plan, ComparisonPlan)
    task, = plan.tasks
    assert task.before_descriptor is not None and task.current_descriptor is not None
    assert task.before_descriptor.raw_content_digest == task.current_descriptor.raw_content_digest
    assert task.policy is not None and task.policy.rule_digest_before != task.policy.rule_digest_current
    identity = build_table_task_identity(plan, task, repository_id="reference-test", artifact_scope=task.artifact_scope.value)
    ordinary_plan = plan_comparison(ComparisonRequest(pair_id="ordinary", before=before,
        current=replace(current, presentation=before.presentation), rule_set=rules))
    assert isinstance(ordinary_plan, ComparisonPlan)
    ordinary_task, = ordinary_plan.tasks
    ordinary_identity = build_table_task_identity(ordinary_plan, ordinary_task,
        repository_id="reference-test", artifact_scope=ordinary_task.artifact_scope.value)
    assert (isinstance(identity, NotCacheable) or isinstance(ordinary_identity, NotCacheable)
            or (isinstance(identity, TableTaskIdentity) and isinstance(ordinary_identity, TableTaskIdentity)
                and identity.task_digest != ordinary_identity.task_digest))
    with closing(compare_plan_native(plan)) as product:
        assert isinstance(product.result, DetailedFactsResult) and product.result.facts is not None
        fact, = product.result.facts.tables
        assert fact.status is ComparisonTableStatus.DEGRADED
        assert "ORDERED_REQUIRED_COLUMN_MISSING" in fact.diagnostics
        assert fact.ordered_extension is not None
        assert fact.ordered_extension.replay_guarantee.value == "UNSUPPORTED"


def test_reference_transition_rejects_unverified_ordered_provenance() -> None:
    ddl = "CREATE TABLE b1_n2_custom (gid INT PRIMARY KEY, no INT, value INT)"
    before = complete_canonical_bound(canonical_bound(ddl + " COMMENT='普通'; INSERT INTO b1_n2_custom VALUES (1, 1, 2);"))
    current = complete_canonical_bound(canonical_bound(ddl + " COMMENT='引用表'; INSERT INTO b1_n2_custom VALUES (1, 1, 2);"))
    plan = plan_comparison(ComparisonRequest(pair_id="unverified", before=before, current=current,
        rule_set=comparison_rule_set(migrated_table_ruleset_snapshot())))
    assert isinstance(plan, ComparisonPlan)
    with closing(compare_plan_native(plan)) as product:
        assert isinstance(product.result, DetailedFactsResult) and product.result.facts is not None
        fact, = product.result.facts.tables
        assert fact.status is ComparisonTableStatus.DEGRADED
        assert "ORDERED_INPUT_NOT_CANONICAL" in fact.diagnostics
        assert fact.ordered_extension is not None
        assert fact.ordered_extension.replay_guarantee.value == "UNSUPPORTED"


def test_label_only_comment_changes_keep_comparison_cache_identity() -> None:
    ddl = "CREATE TABLE b1_n2_custom (id INT PRIMARY KEY, value INT)"
    before = complete_canonical_bound(canonical_bound(ddl + " COMMENT='旧标签'; INSERT INTO b1_n2_custom VALUES (1, 2);"))
    current = complete_canonical_bound(canonical_bound(ddl + " COMMENT='新标签'; INSERT INTO b1_n2_custom VALUES (1, 3);"))
    rules = comparison_rule_set(migrated_table_ruleset_snapshot())
    changed_label = plan_comparison(ComparisonRequest(pair_id="label-change", before=before, current=current, rule_set=rules))
    unchanged_label = plan_comparison(ComparisonRequest(pair_id="same-label", before=before,
        current=replace(current, presentation=before.presentation), rule_set=rules))
    assert isinstance(changed_label, ComparisonPlan) and isinstance(unchanged_label, ComparisonPlan)
    first, = changed_label.tasks
    second, = unchanged_label.tasks
    first_identity = build_table_task_identity(changed_label, first,
        repository_id="reference-test", artifact_scope=first.artifact_scope.value)
    second_identity = build_table_task_identity(unchanged_label, second,
        repository_id="reference-test", artifact_scope=second.artifact_scope.value)
    assert isinstance(first_identity, TableTaskIdentity) and isinstance(second_identity, TableTaskIdentity)
    assert first_identity.task_digest == second_identity.task_digest
