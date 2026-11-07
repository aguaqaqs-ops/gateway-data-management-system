"""Comparison facts for table roles that do not emit row records."""

from __future__ import annotations

import pytest
from unittest.mock import patch

from gateway_backend.capabilities.comparison import (
    BoundSnapshotInput,
    ComparisonPlan,
    ComparisonRequest,
    ComparisonTableFact,
    ComparisonTableStatus,
    DetailedFactsResult,
    compare_plan,
    comparison_python_memory_upper,
    plan_comparison,
)
from gateway_backend.capabilities.comparison.contracts import SchemaEvolution
from gateway_backend.capabilities.snapshot_materialization import ArrowSnapshotTableReader
from gateway_backend.capabilities.snapshot_materialization.contracts import MaterializationPolicy
from gateway_backend.capabilities.table_access import (
    KernelExecutionContext, KernelMemoryLimit, NeverCancel, OperationMemoryBudget, kernel_execution_scope,
)
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
            canonical_key_policy=CanonicalKeyPolicy.DDL_PRIMARY_KEY_OR_KEYLESS,
            ordered_policy=OrderedPolicy.NONE,
        )
    )


def _plan(
    before: BoundSnapshotInput,
    current: BoundSnapshotInput,
    role: TableStaticRole,
) -> ComparisonPlan:
    request = ComparisonRequest(
        pair_id="role-pair",
        before=before,
        current=current,
        rule_set=_rules(role),
    )
    plan = plan_comparison(request)
    assert isinstance(plan, ComparisonPlan)
    return plan


def _fact(
    before: BoundSnapshotInput,
    current: BoundSnapshotInput,
    role: TableStaticRole,
) -> ComparisonTableFact:
    result = compare_plan(_plan(before, current, role))
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
    before = _bound(
        "CREATE TABLE t (id INT NOT NULL PRIMARY KEY, value INT); "
        "INSERT INTO t VALUES (1, 10);"
    )
    current = _bound(
        "CREATE TABLE t (id INT NOT NULL PRIMARY KEY, value INT, note VARCHAR(8)); "
        "INSERT INTO t VALUES (1, 10, 'x');"
    )

    table = _fact(before, current, role)

    assert table.status is ComparisonTableStatus.UNCHANGED
    assert table.content_changed is False
    assert table.schema_changes.schema_evolution is SchemaEvolution.COLUMNS_ADDED
    assert table.schema_changes.current_only_columns == ("note",)
    assert table.records == ()


@pytest.mark.parametrize(
    "role",
    (TableStaticRole.BROWSE_ONLY, TableStaticRole.SNAPSHOT_ONLY),
)
def test_non_record_roles_still_show_shared_data_changes_with_added_column(
    role: TableStaticRole,
) -> None:
    before = _bound(
        "CREATE TABLE t (id INT NOT NULL PRIMARY KEY, value INT); "
        "INSERT INTO t VALUES (1, 10);"
    )
    current = _bound(
        "CREATE TABLE t (id INT NOT NULL PRIMARY KEY, value INT, note VARCHAR(8)); "
        "INSERT INTO t VALUES (1, 11, 'x');"
    )

    table = _fact(before, current, role)

    assert table.status is ComparisonTableStatus.UNCHANGED
    assert table.content_changed is True
    assert table.schema_changes.schema_evolution is SchemaEvolution.COLUMNS_ADDED
    assert table.records == ()


@pytest.mark.parametrize("role", (TableStaticRole.BROWSE_ONLY, TableStaticRole.SNAPSHOT_ONLY))
@pytest.mark.parametrize("columns_added", (True, False), ids=("shared-row-comparison", "metadata-only"))
def test_non_record_roles_admit_row_growth_only_for_added_columns(
    role: TableStaticRole, columns_added: bool,
) -> None:
    admissions = []
    for row_count in (1, 256):
        context = KernelExecutionContext(OperationMemoryBudget(16 * 1024**2), NeverCancel(), 1)
        with kernel_execution_scope(context, new_operation=True):
            before_values = ",".join(f"({i},10)" for i in range(row_count))
            current_values = ",".join(
                f"({i},11,'x')" if columns_added else f"({i},11)" for i in range(row_count)
            )
            before = _bound(
                "CREATE TABLE t(id INT NOT NULL PRIMARY KEY,value INT);"
                f"INSERT INTO t VALUES {before_values};"
            )
            current = _bound(
                "CREATE TABLE t(id INT NOT NULL PRIMARY KEY,value INT"
                + (",note VARCHAR(8)" if columns_added else "")
                + f");INSERT INTO t VALUES {current_values};"
            )
            plan = _plan(before, current, role)
            with (
                patch.object(ArrowSnapshotTableReader, "iter_rows", side_effect=AssertionError("row read")) as rows,
                patch.object(ArrowSnapshotTableReader, "arrow_stream", side_effect=AssertionError("stream read")) as stream,
                context.memory.reserve(context.memory.available_bytes - 80 * 1024),
            ):
                upper = comparison_python_memory_upper(plan)
                admissions.append(upper)
                if columns_added:
                    with pytest.raises(KernelMemoryLimit):
                        with context.memory.reserve(upper):
                            compare_plan(plan)
                else:
                    with context.memory.reserve(upper):
                        assert isinstance(compare_plan(plan), DetailedFactsResult)
                rows.assert_not_called()
                stream.assert_not_called()
    if columns_added:
        assert admissions[1] > admissions[0]
    else:
        assert admissions[1] == admissions[0]
