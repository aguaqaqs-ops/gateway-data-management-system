"""Runtime rule planning, alignment, schema provenance and non-record roles."""

from __future__ import annotations

from dataclasses import replace

import pytest
from gateway_shared_kernel import raw_blob_digest

from gateway_backend.capabilities.comparison import (
    BoundSnapshotInput,
    ComparisonRequest,
    ComparisonPlan,
    ComparisonStorageFacts,
    ComparisonFacts,
    ComparisonTableStatus,
    DetailedFactsResult,
    SchemaChangeSource,
    compare_plan,
    plan_comparison,
)
from gateway_backend.capabilities.snapshot_materialization.contracts import MaterializationPolicy
from gateway_backend.capabilities.table_rules.contracts import (
    CanonicalKeyPolicy,
    ComparisonRuleSet,
    DroppedColumn,
    OrderedPolicy,
    StorageRuleView,
)
from tests.support.snapshot_materialization import materialize_sql
from tests.support.table_rules import comparison_ruleset_for, standard_rule_record

pytestmark = pytest.mark.unit


def _bound(sql: str) -> BoundSnapshotInput:
    result = materialize_sql(sql, policy=MaterializationPolicy.READERS_REQUIRED)
    assert result.snapshot is not None
    assert result.summary is not None
    assert result.table_set is not None
    return BoundSnapshotInput(result.snapshot, result.summary, result.table_set)


def _request(
    before: BoundSnapshotInput,
    current: BoundSnapshotInput,
    rule_set: ComparisonRuleSet,
    *,
    pair_id: str = "plan-pair",
) -> ComparisonRequest:
    return ComparisonRequest(
        pair_id=pair_id,
        before=before,
        current=current,
        rule_set=rule_set,
    )


def _facts(request: ComparisonRequest) -> ComparisonFacts:
    plan = plan_comparison(request)
    assert isinstance(plan, ComparisonPlan)
    result = compare_plan(plan)
    assert isinstance(result, DetailedFactsResult)
    assert result.facts is not None
    return result.facts


def _storage_view(
    *,
    key_policy: CanonicalKeyPolicy = CanonicalKeyPolicy.DDL_PRIMARY_KEY,
    key_columns: tuple[str, ...] = (),
    dropped: tuple[str, ...] = (),
    structural: tuple[str, ...] = (),
    ordered: OrderedPolicy = OrderedPolicy.NONE,
) -> StorageRuleView:
    return StorageRuleView(
        canonical_table="t",
        canonical_key_policy=key_policy,
        ordered_policy=ordered,
        dropped_columns=tuple(DroppedColumn(name=name, reason=f"rule:{name}") for name in dropped),
        structural_columns=structural,
        canonical_key_columns=key_columns,
    )


def _with_storage_facts(
    bound: BoundSnapshotInput,
    view: StorageRuleView,
    source_schema: str,
) -> BoundSnapshotInput:
    return replace(
        bound,
        storage_facts=(
            ComparisonStorageFacts(
                storage_rule_view=view,
                source_schema_digest=raw_blob_digest(source_schema.encode()),
            ),
        ),
    )


def test_comparison_aligns_values_by_column_name_and_uses_runtime_effective_keys() -> None:
    before = _bound(
        "CREATE TABLE t (tenant INT NOT NULL, id INT NOT NULL, value VARCHAR(8), PRIMARY KEY (tenant, id)); "
        "INSERT INTO t VALUES (1, 2, 'old');"
    )
    current = _bound(
        "CREATE TABLE t (value VARCHAR(8), id INT NOT NULL, tenant INT NOT NULL, PRIMARY KEY (tenant, id)); "
        "INSERT INTO t VALUES ('new', 2, 1);"
    )
    request = _request(before, current, comparison_ruleset_for(standard_rule_record("t")))

    table = _facts(request).tables[0]

    assert table.schema_changes.selected_columns == ("id", "tenant", "value")
    assert table.schema_changes.effective_compare_key_before == ("tenant", "id")
    assert table.schema_changes.effective_compare_key_current == ("tenant", "id")
    assert table.status is ComparisonTableStatus.MODIFIED
    assert table.records[0].changed_columns == ("value",)


@pytest.mark.parametrize(
    ("before_sql", "current_sql", "before_view", "current_view", "before_source", "current_source", "expected"),
    (
        (
            "CREATE TABLE t (id INT NOT NULL PRIMARY KEY, value INT);",
            "CREATE TABLE t (id INT NOT NULL PRIMARY KEY, value INT, added INT);",
            _storage_view(),
            _storage_view(),
            "same-source",
            "changed-source",
            SchemaChangeSource.SOURCE_SCHEMA,
        ),
        (
            "CREATE TABLE t (id INT NOT NULL PRIMARY KEY, value INT, aux INT);",
            "CREATE TABLE t (id INT NOT NULL PRIMARY KEY, value INT);",
            _storage_view(),
            _storage_view(dropped=("aux",)),
            "same-source",
            "same-source",
            SchemaChangeSource.STORAGE_PROJECTION_POLICY,
        ),
        (
            "CREATE TABLE t (id INT NOT NULL PRIMARY KEY, value INT);",
            "CREATE TABLE t (code INT NOT NULL PRIMARY KEY, value INT);",
            _storage_view(key_policy=CanonicalKeyPolicy.EXPLICIT, key_columns=("id",)),
            _storage_view(key_policy=CanonicalKeyPolicy.EXPLICIT, key_columns=("code",)),
            "same-source",
            "same-source",
            SchemaChangeSource.STORAGE_PROJECTION_POLICY,
        ),
        (
            "CREATE TABLE t (id INT NOT NULL PRIMARY KEY, value INT, aux INT);",
            "CREATE TABLE t (code INT NOT NULL PRIMARY KEY, value INT);",
            _storage_view(key_policy=CanonicalKeyPolicy.EXPLICIT, key_columns=("id",)),
            _storage_view(key_policy=CanonicalKeyPolicy.EXPLICIT, key_columns=("code",), dropped=("aux",)),
            "source-before",
            "source-current",
            SchemaChangeSource.BOTH,
        ),
        (
            "CREATE TABLE t (id INT NOT NULL PRIMARY KEY, value INT);",
            "CREATE TABLE t (code INT NOT NULL PRIMARY KEY, value INT);",
            _storage_view(),
            _storage_view(),
            "source-before",
            "source-current",
            SchemaChangeSource.SOURCE_SCHEMA,
        ),
    ),
)
def test_schema_change_source_uses_only_persisted_rule_side_facts(
    before_sql: str,
    current_sql: str,
    before_view: StorageRuleView,
    current_view: StorageRuleView,
    before_source: str,
    current_source: str,
    expected: SchemaChangeSource,
) -> None:
    before = _with_storage_facts(_bound(before_sql), before_view, before_source)
    current = _with_storage_facts(_bound(current_sql), current_view, current_source)
    request = _request(before, current, comparison_ruleset_for(standard_rule_record("t")))

    table = _facts(request).tables[0]

    assert table.schema_changes.change_source is expected


def test_source_ddl_primary_key_change_does_not_masquerade_as_rule_change() -> None:
    before = _with_storage_facts(
        _bound("CREATE TABLE t (id INT NOT NULL PRIMARY KEY, value INT);"),
        _storage_view(key_columns=("id",)),
        "source-before",
    )
    current = _with_storage_facts(
        _bound("CREATE TABLE t (code INT NOT NULL PRIMARY KEY, value INT);"),
        _storage_view(key_columns=("code",)),
        "source-current",
    )

    table = _facts(_request(before, current, comparison_ruleset_for(standard_rule_record("t")))).tables[0]

    assert table.schema_changes.change_source is SchemaChangeSource.SOURCE_SCHEMA


def test_schema_change_source_is_unknown_without_both_persisted_storage_facts() -> None:
    before = _bound("CREATE TABLE t (id INT NOT NULL PRIMARY KEY, value INT);")
    current = _bound("CREATE TABLE t (id INT NOT NULL PRIMARY KEY, value INT, note TEXT);")

    table = _facts(_request(before, current, comparison_ruleset_for(standard_rule_record("t")))).tables[0]

    assert table.schema_changes.current_only_columns == ("note",)
    assert table.schema_changes.change_source is None
