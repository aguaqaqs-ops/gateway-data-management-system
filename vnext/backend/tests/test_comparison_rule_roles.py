"""Comparison facts for table roles that do not emit row records."""

from __future__ import annotations

import pytest

from gateway_backend.capabilities.comparison import (
    BoundSnapshotInput,
    ComparisonPlan,
    ComparisonRequest,
    ComparisonTableFact,
    ComparisonTableStatus,
    DetailedFactsResult,
    compare_plan,
    plan_comparison,
)
from gateway_backend.capabilities.snapshot_materialization.contracts import MaterializationPolicy
from gateway_backend.capabilities.table_rules.contracts import (
    CanonicalKeyPolicy,
    ComparisonRuleSet,
    OrderedPolicy,
    SelectorPrecedenceClass,
    TableRuleRecord,
    TableRuleSelector,
    TableRuleSelectorKind,
    TableStaticRole,
    TableStorageDisposition,
)
from tests.support.snapshot_materialization import materialize_sql
from tests.support.table_rules import comparison_ruleset_for

pytestmark = pytest.mark.unit


def _bound(sql: str) -> BoundSnapshotInput:
    result = materialize_sql(sql, policy=MaterializationPolicy.READERS_REQUIRED)
    assert result.snapshot is not None
    assert result.summary is not None
    assert result.table_set is not None
    return BoundSnapshotInput(result.snapshot, result.summary, result.table_set)


def _rules(role: TableStaticRole) -> ComparisonRuleSet:
    precedence = {
        TableStaticRole.BROWSE_ONLY: SelectorPrecedenceClass.BROWSE_ONLY,
        TableStaticRole.SNAPSHOT_ONLY: SelectorPrecedenceClass.SNAPSHOT_ONLY,
    }[role]
    return comparison_ruleset_for(
        TableRuleRecord(
            selector=TableRuleSelector(
                kind=(
                    TableRuleSelectorKind.REGEX
                    if role is TableStaticRole.SNAPSHOT_ONLY
                    else TableRuleSelectorKind.EXACT
                ),
                value="^t$" if role is TableStaticRole.SNAPSHOT_ONLY else "t",
            ),
            precedence_class=precedence,
            static_role=role,
            table_storage=TableStorageDisposition.PROJECT,
            canonical_key_policy=CanonicalKeyPolicy.DDL_PRIMARY_KEY,
            ordered_policy=OrderedPolicy.NONE,
        )
    )


def _fact(
    before: BoundSnapshotInput,
    current: BoundSnapshotInput,
    role: TableStaticRole,
) -> ComparisonTableFact:
    request = ComparisonRequest(
        pair_id="role-pair",
        before=before,
        current=current,
        rule_set=_rules(role),
    )
    plan = plan_comparison(request)
    assert isinstance(plan, ComparisonPlan)
    result = compare_plan(plan)
    assert isinstance(result, DetailedFactsResult)
    assert result.facts is not None
    return next(table for table in result.facts.tables if table.table_name == "t")


@pytest.mark.parametrize(
    "role",
    (TableStaticRole.BROWSE_ONLY, TableStaticRole.SNAPSHOT_ONLY),
)
def test_non_record_roles_publish_content_change_facts_without_row_records(
    role: TableStaticRole,
) -> None:
    before = _bound("CREATE TABLE t (id INT NOT NULL PRIMARY KEY, value INT); INSERT INTO t VALUES (1, 10);")
    current = _bound("CREATE TABLE t (id INT NOT NULL PRIMARY KEY, value INT); INSERT INTO t VALUES (1, 11);")

    table = _fact(before, current, role)

    assert table.status is ComparisonTableStatus.UNCHANGED
    assert (table.row_count_before, table.row_count_current) == (1, 1)
    assert table.content_changed is True
    assert table.records == ()


@pytest.mark.parametrize(
    "role",
    (TableStaticRole.BROWSE_ONLY, TableStaticRole.SNAPSHOT_ONLY),
)
def test_non_record_roles_keep_table_existence_facts_without_row_records(
    role: TableStaticRole,
) -> None:
    before = _bound("CREATE TABLE other (id INT NOT NULL PRIMARY KEY);")
    current = _bound("CREATE TABLE t (id INT NOT NULL PRIMARY KEY, value INT); INSERT INTO t VALUES (1, 10);")

    table = _fact(before, current, role)

    assert table.status is ComparisonTableStatus.ADDED_TABLE
    assert (table.row_count_before, table.row_count_current) == (None, 1)
    assert table.content_changed is True
    assert table.records == ()


@pytest.mark.parametrize(
    "role",
    (TableStaticRole.BROWSE_ONLY, TableStaticRole.SNAPSHOT_ONLY),
)
def test_non_record_roles_keep_schema_facts_visible(
    role: TableStaticRole,
) -> None:
    before = _bound("CREATE TABLE t (id INT NOT NULL PRIMARY KEY, value INT);")
    current = _bound("CREATE TABLE t (id INT NOT NULL PRIMARY KEY, value INT, note VARCHAR(8));")

    table = _fact(before, current, role)

    assert table.status is ComparisonTableStatus.SCHEMA_ONLY_CHANGED
    assert table.content_changed is True
    assert table.schema_changes.current_only_columns == ("note",)
    assert table.records == ()
