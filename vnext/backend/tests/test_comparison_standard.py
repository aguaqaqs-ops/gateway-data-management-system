"""S3 standard comparison facts, records and digest contract tests."""

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path
from typing import cast

import pytest
from gateway_shared_kernel import NullScalar, raw_blob_digest

from gateway_backend.capabilities.comparison import (
    BoundSnapshotInput,
    ComparisonRequest,
    ComparisonFacts,
    ComparisonPlan,
    ComparisonRecordKind,
    SchemaChangeSource,
    ComparisonTableFact,
    ComparisonTableStatus,
    DetailedFactsResult,
    ComparisonStorageFacts,
    SchemaEvolution,
    compare_plan,
    plan_comparison,
)
from gateway_backend.artifacts import InMemoryArtifactStore
from gateway_backend.capabilities.risk_evaluation import (
    RiskEvaluationInput,
    RiskEvaluationStatus,
    RiskOptions,
    RiskReasonCode,
    RiskRulesetSnapshot,
    V1_RISK_RULE_SPECS,
    evaluate_risk,
)
from gateway_backend.capabilities.table_rules.contracts import (
    CanonicalKeyPolicy,
    ComparisonRuleSet,
    StorageRuleView,
    TableArtifactScope,
)
from gateway_backend.capabilities.table_rules.contracts import OrderedPolicy
from gateway_backend.capabilities.snapshot_materialization.contracts import (
    MaterializationPolicy,
    SnapshotTable,
    SnapshotTableReader,
    SnapshotTableSet,
)
from gateway_backend.capabilities.storage_projection import STORAGE_PROJECTION_VERSION
from tests.support.snapshot_materialization import materialize_sql
from tests.support.table_rules import comparison_ruleset_for, standard_rule_record

pytestmark = pytest.mark.unit
_S1B_GOLDEN = (
    Path(__file__).resolve().parents[2]
    / "fixtures"
    / "golden"
    / "comparison"
    / "s1b"
    / "semantic-results.json"
)


def _s1b_golden_case(name: str) -> dict[str, object]:
    document = json.loads(_S1B_GOLDEN.read_text(encoding="utf-8"))
    return document["cases"][name]


def _s1b_fact_projection(table: ComparisonTableFact) -> dict[str, object]:
    return {
        "status": table.status.value,
        "schema_evolution": table.schema_changes.schema_evolution.value,
        "before_only_columns": list(table.schema_changes.before_only_columns),
        "current_only_columns": list(table.schema_changes.current_only_columns),
        "selected_columns": list(table.schema_changes.selected_columns),
        "row_count_before": table.row_count_before,
        "row_count_current": table.row_count_current,
        "row_added_count": table.row_added_count,
        "row_deleted_count": table.row_deleted_count,
        "row_modified_count": table.row_modified_count,
        "content_changed": table.content_changed,
        "record_kinds": [record.record_kind.value for record in table.records],
        "changed_columns": [
            list(record.changed_columns)
            for record in table.records
            if record.record_kind is ComparisonRecordKind.ROW_MODIFIED
        ],
    }


def _assert_s1b_fact_golden(name: str, table: ComparisonTableFact) -> None:
    expected = _s1b_golden_case(name)
    actual = _s1b_fact_projection(table)
    assert {key: actual[key] for key in expected} == expected


class _CountingReader:
    def __init__(self, reader: object) -> None:
        self.reader = reader
        self.iterations = 0
        self.reopens = 0
        self.closes = 0

    def descriptor(self) -> object:
        return self.reader.descriptor()  # type: ignore[attr-defined]

    def iter_rows(self) -> object:
        self.iterations += 1
        return self.reader.iter_rows()  # type: ignore[attr-defined]

    def count_column_values(self, column_name: str) -> object:
        return self.reader.count_column_values(column_name)  # type: ignore[attr-defined]

    def close(self) -> None:
        self.closes += 1
        self.reader.close()  # type: ignore[attr-defined]

    def reopen(self) -> _CountingReader:
        self.reopens += 1
        return _CountingReader(self.reader.reopen())  # type: ignore[attr-defined]


class _BadReader:
    def __init__(self, descriptor: object) -> None:
        self._descriptor = descriptor

    def descriptor(self) -> object:
        return self._descriptor

    def iter_rows(self) -> object:
        yield ()

    def count_column_values(self, column_name: str) -> object:
        del column_name
        raise AssertionError("count_column_values must not be used by comparison core")

    def close(self) -> None:
        return None

    def reopen(self) -> _BadReader:
        return _BadReader(self._descriptor)


def _bound(sql: str) -> BoundSnapshotInput:
    result = materialize_sql(sql, policy=MaterializationPolicy.READERS_REQUIRED)
    assert result.snapshot is not None
    assert result.summary is not None
    assert result.table_set is not None
    return BoundSnapshotInput(result.snapshot, result.summary, result.table_set)


def _plan(
    before_sql: str,
    current_sql: str,
    *,
    rule_set: ComparisonRuleSet | None = None,
    scope: TableArtifactScope = TableArtifactScope.ALL_CHANGES,
) -> ComparisonPlan:
    before = _bound(before_sql)
    current = _bound(current_sql)
    request = ComparisonRequest(
        pair_id="standard-pair",
        before=before,
        current=current,
        rule_set=rule_set or comparison_ruleset_for(standard_rule_record("t", artifact_scope=scope)),
    )
    plan = plan_comparison(request)
    assert isinstance(plan, ComparisonPlan)
    return plan


def _facts(plan: ComparisonPlan) -> ComparisonFacts:
    result = compare_plan(plan)
    assert isinstance(result, DetailedFactsResult)
    assert result.facts is not None
    return result.facts


def _one_table(facts: ComparisonFacts) -> ComparisonTableFact:
    assert len(facts.tables) == 1
    return facts.tables[0]


def test_keyed_comparison_emits_added_deleted_modified_and_field_change() -> None:
    before = """
        CREATE TABLE t (id INT NOT NULL PRIMARY KEY, name VARCHAR(8) NULL);
        INSERT INTO t VALUES (1, 'a'), (2, 'b');
    """
    current = """
        CREATE TABLE t (id INT NOT NULL PRIMARY KEY, name VARCHAR(8) NULL);
        INSERT INTO t VALUES (1, 'z'), (3, 'c');
    """

    facts = _facts(_plan(before, current))
    table = _one_table(facts)

    assert facts.summary.status.value == "CHANGED"
    assert table.status is ComparisonTableStatus.MODIFIED
    assert (table.row_added_count, table.row_deleted_count, table.row_modified_count) == (1, 1, 1)
    kinds = [record.record_kind for record in table.records]
    assert kinds == [
        ComparisonRecordKind.ROW_ADDED,
        ComparisonRecordKind.ROW_DELETED,
        ComparisonRecordKind.ROW_MODIFIED,
    ]
    modified = table.records[-1]
    assert modified.changed_columns == ("name",)
    assert len(modified.field_changes) == 1
    assert modified.field_changes[0].column_name == "name"


def test_null_values_remain_typed_and_are_not_stringified() -> None:
    sql = """
        CREATE TABLE t (id INT NOT NULL PRIMARY KEY, note VARCHAR(8) NULL);
        INSERT INTO t VALUES (1, NULL);
    """
    result = _facts(_plan(sql, sql))
    table = _one_table(result)
    assert table.status is ComparisonTableStatus.UNCHANGED
    assert table.records == ()


def test_modified_null_value_is_retained_as_typed_null_in_field_change() -> None:
    before = "CREATE TABLE t (id INT NOT NULL PRIMARY KEY, note VARCHAR(8) NULL); INSERT INTO t VALUES (1, 'x');"
    current = "CREATE TABLE t (id INT NOT NULL PRIMARY KEY, note VARCHAR(8) NULL); INSERT INTO t VALUES (1, NULL);"

    table = _one_table(_facts(_plan(before, current)))
    assert table.row_modified_count == 1
    assert isinstance(table.records[0].field_changes[0].current_value, NullScalar)


def test_added_columns_compare_common_columns_without_schema_status_or_record() -> None:
    before = """
        CREATE TABLE t (id INT NOT NULL PRIMARY KEY, name VARCHAR(8) NULL);
        INSERT INTO t VALUES (1, 'a');
    """
    current = """
        CREATE TABLE t (
            id INT NOT NULL PRIMARY KEY,
            name VARCHAR(8) NULL,
            note TEXT NULL
        );
        INSERT INTO t VALUES (1, 'a', 'new');
    """

    table = _one_table(_facts(_plan(before, current)))
    _assert_s1b_fact_golden("added_columns_unchanged", table)
    assert table.status is ComparisonTableStatus.UNCHANGED
    assert table.schema_changes.schema_evolution is SchemaEvolution.COLUMNS_ADDED
    assert table.schema_changes.selected_columns == ("id", "name")
    assert table.schema_changes.current_only_columns == ("note",)
    assert table.row_modified_count == 0
    assert table.records == ()
    assert table.content_changed is False


def test_added_column_does_not_hide_changes_in_shared_columns() -> None:
    before = "CREATE TABLE t (id INT NOT NULL PRIMARY KEY, name VARCHAR(8) NULL); INSERT INTO t VALUES (1, 'before');"
    current = "CREATE TABLE t (id INT NOT NULL PRIMARY KEY, name VARCHAR(8) NULL, note TEXT NULL); INSERT INTO t VALUES (1, 'after', 'new');"

    table = _one_table(_facts(_plan(before, current)))
    _assert_s1b_fact_golden("added_columns_common_value_changed", table)

    assert table.status is ComparisonTableStatus.MODIFIED
    assert table.schema_changes.schema_evolution is SchemaEvolution.COLUMNS_ADDED
    assert table.row_modified_count == 1
    assert table.records[0].changed_columns == ("name",)
    assert all(record.record_kind is not ComparisonRecordKind.SCHEMA_CHANGE for record in table.records)


def test_enum_and_set_member_additions_are_columns_added() -> None:
    before = "CREATE TABLE t (id INT NOT NULL PRIMARY KEY, e ENUM('a', 'b') NULL, s SET('x', 'y') NULL); INSERT INTO t VALUES (1, 'a', 'x');"
    current = "CREATE TABLE t (id INT NOT NULL PRIMARY KEY, e ENUM('a', 'c', 'b') NULL, s SET('x', 'y', 'z') NULL); INSERT INTO t VALUES (1, 'a', 'x');"

    table = _one_table(_facts(_plan(before, current)))
    _assert_s1b_fact_golden("enum_set_members_added", table)

    assert table.status is ComparisonTableStatus.UNCHANGED
    assert table.schema_changes.schema_evolution is SchemaEvolution.COLUMNS_ADDED
    assert table.records == ()


def test_removed_column_is_classified_separately_from_incompatible_schema() -> None:
    before = "CREATE TABLE t (id INT NOT NULL PRIMARY KEY, name VARCHAR(8) NULL, note TEXT NULL); INSERT INTO t VALUES (1, 'same', 'old');"
    current = "CREATE TABLE t (id INT NOT NULL PRIMARY KEY, name VARCHAR(8) NULL); INSERT INTO t VALUES (1, 'same');"

    table = _one_table(_facts(_plan(before, current)))
    _assert_s1b_fact_golden("columns_removed", table)

    assert table.status is ComparisonTableStatus.SCHEMA_CHANGED
    assert table.schema_changes.schema_evolution is SchemaEvolution.COLUMNS_REMOVED


def test_compare_excluded_only_change_is_visible_without_row_records() -> None:
    before = """
        CREATE TABLE t (
            id INT NOT NULL PRIMARY KEY,
            name VARCHAR(8) NULL,
            aux VARCHAR(8) NULL
        );
        INSERT INTO t VALUES (1, 'same', 'before');
    """
    current = """
        CREATE TABLE t (
            id INT NOT NULL PRIMARY KEY,
            name VARCHAR(8) NULL,
            aux VARCHAR(8) NULL
        );
        INSERT INTO t VALUES (1, 'same', 'current');
    """

    table = _one_table(
        _facts(
            _plan(
                before,
                current,
                rule_set=comparison_ruleset_for(
                    standard_rule_record("t", compare_excluded_columns=("aux",))
                ),
            )
        )
    )
    assert table.status is ComparisonTableStatus.UNCHANGED
    assert table.content_changed is True
    assert table.row_modified_count == 0
    assert table.records == ()


def test_incompatible_non_key_type_does_not_create_field_change() -> None:
    before = """
        CREATE TABLE t (id INT NOT NULL PRIMARY KEY, value INT NULL);
        INSERT INTO t VALUES (1, 1);
    """
    current = """
        CREATE TABLE t (id INT NOT NULL PRIMARY KEY, value BIGINT NULL);
        INSERT INTO t VALUES (1, 2);
    """

    table = _one_table(_facts(_plan(before, current)))
    assert table.status is ComparisonTableStatus.SCHEMA_CHANGED
    assert table.schema_changes.incompatible_columns == ("value",)
    assert table.row_modified_count == 0
    assert all(not record.field_changes for record in table.records)


def test_changed_effective_key_degrades_without_positional_fallback() -> None:
    before = """
        CREATE TABLE t (id INT NOT NULL PRIMARY KEY, value VARCHAR(8) NULL);
        INSERT INTO t VALUES (1, 'a');
    """
    current = """
        CREATE TABLE t (code INT NOT NULL PRIMARY KEY, value VARCHAR(8) NULL);
        INSERT INTO t VALUES (1, 'a');
    """

    table = _one_table(_facts(_plan(before, current)))
    assert table.status is ComparisonTableStatus.DEGRADED
    assert table.row_modified_count == 0
    assert [record.record_kind for record in table.records] == [ComparisonRecordKind.TABLE_DEGRADED]


def test_keyless_table_degrades_without_a_safe_effective_key() -> None:
    before = "CREATE TABLE t (value VARCHAR(8) NULL); INSERT INTO t VALUES ('a'), ('b');"
    current = "CREATE TABLE t (value VARCHAR(8) NULL); INSERT INTO t VALUES ('a'), ('c');"

    table = _one_table(_facts(_plan(before, current)))
    assert table.status is ComparisonTableStatus.DEGRADED
    assert table.row_added_count == 0
    assert table.row_deleted_count == 0
    assert all(record.record_kind is not ComparisonRecordKind.ROW_MODIFIED for record in table.records)


def test_raw_primary_key_fallback_compares_keyless_rows_as_a_multiset() -> None:
    before = _bound_with_fallback_facts(
        "CREATE TABLE t (value VARCHAR(8) NULL); INSERT INTO t VALUES ('a'), ('same'), ('same');",
        b"source-without-key",
    )
    unchanged = _bound_with_fallback_facts(
        "CREATE TABLE t (value VARCHAR(8) NULL); INSERT INTO t VALUES ('same'), ('a'), ('same');",
        b"source-without-key",
    )
    changed = _bound_with_fallback_facts(
        "CREATE TABLE t (value VARCHAR(8) NULL); INSERT INTO t VALUES ('a'), ('same'), ('other');",
        b"source-without-key",
    )

    unchanged_table = _one_table(_facts(_plan_from_bounds(before, unchanged)))
    changed_facts = _facts(_plan_from_bounds(before, changed))
    changed_table = _one_table(changed_facts)

    assert unchanged_table.status is ComparisonTableStatus.UNCHANGED
    assert changed_table.status is ComparisonTableStatus.MODIFIED
    assert (changed_table.row_added_count, changed_table.row_deleted_count) == (1, 1)
    assert changed_table.row_modified_count == 0
    assert not any("KEY_DEGRADED" in item for item in changed_table.diagnostics)
    assert all(
        record.record_kind in {ComparisonRecordKind.ROW_ADDED, ComparisonRecordKind.ROW_DELETED}
        for record in changed_table.records
    )
    risk = evaluate_risk(
        RiskEvaluationInput(
            comparison_facts=changed_facts,
            risk_ruleset=RiskRulesetSnapshot(rules=V1_RISK_RULE_SPECS),
            risk_options=RiskOptions(),
        ),
        artifact_store=InMemoryArtifactStore(),
    )
    assert risk.status is RiskEvaluationStatus.READY
    assert risk.risk_report is not None
    assert RiskReasonCode.KEY_DEGRADED not in risk.risk_report.tables[0].reason_codes


def test_keyless_table_addition_is_table_level_without_row_records() -> None:
    current = _bound_with_fallback_facts(
        "CREATE TABLE t (value VARCHAR(8) NULL); INSERT INTO t VALUES ('same'), ('same');",
        b"source-without-key",
    )

    table = _one_table(_facts(_plan_from_bounds(_bound(""), current)))
    _assert_s1b_fact_golden("whole_table_added", table)
    assert table.status is ComparisonTableStatus.ADDED_TABLE
    assert table.row_added_count == 0
    assert table.row_count_current == 2
    assert table.records == ()


def test_whole_table_deletion_is_table_level_without_row_records() -> None:
    before = _bound_with_fallback_facts(
        "CREATE TABLE t (value VARCHAR(8) NULL); INSERT INTO t VALUES ('same'), ('same');",
        b"source-deleted-table",
    )

    table = _one_table(_facts(_plan_from_bounds(before, _bound(""))))

    _assert_s1b_fact_golden("whole_table_deleted", table)
    assert table.status is ComparisonTableStatus.DELETED_TABLE
    assert table.row_deleted_count == 0
    assert table.row_count_before == 2
    assert table.records == ()


@pytest.mark.parametrize("primary_key_appears", (True, False), ids=("appears", "disappears"))
def test_raw_primary_key_appearance_or_disappearance_is_a_source_schema_change(
    primary_key_appears: bool,
) -> None:
    keyless_sql = "CREATE TABLE t (value VARCHAR(8) NULL); INSERT INTO t VALUES ('same');"
    keyed_sql = "CREATE TABLE t (id INT NOT NULL PRIMARY KEY, value VARCHAR(8) NULL); INSERT INTO t VALUES (1, 'same');"
    keyless = _bound_with_fallback_facts(keyless_sql, b"source-keyless")
    keyed = _bound_with_fallback_facts(keyed_sql, b"source-keyed")
    before, current = (keyless, keyed) if primary_key_appears else (keyed, keyless)

    table = _one_table(_facts(_plan_from_bounds(before, current)))

    assert table.status is ComparisonTableStatus.SCHEMA_CHANGED
    assert table.schema_changes.change_source is SchemaChangeSource.SOURCE_SCHEMA
    assert table.schema_changes.effective_compare_key_changed is False
    assert not any("KEY_DEGRADED" in item for item in table.diagnostics)


def test_update_only_suppresses_records_but_keeps_counts() -> None:
    before = "CREATE TABLE t (id INT NOT NULL PRIMARY KEY); INSERT INTO t VALUES (1);"
    current = "CREATE TABLE t (id INT NOT NULL PRIMARY KEY); INSERT INTO t VALUES (2);"

    table = _one_table(
        _facts(
            _plan(
                before,
                current,
                rule_set=comparison_ruleset_for(
                    standard_rule_record(
                        "t",
                        artifact_scope=TableArtifactScope.UPDATE_ONLY,
                    )
                ),
            )
        )
    )
    assert table.row_added_count == 1
    assert table.row_deleted_count == 1
    assert table.suppressed_added_count == 1
    assert table.suppressed_deleted_count == 1
    assert table.records == ()


def test_missing_tables_are_not_materialized_as_empty_tables() -> None:
    before = "CREATE TABLE before_table (id INT NOT NULL PRIMARY KEY); INSERT INTO before_table VALUES (1);"
    current = "CREATE TABLE current_table (id INT NOT NULL PRIMARY KEY); INSERT INTO current_table VALUES (1);"

    facts = _facts(_plan(before, current))
    assert [table.table_name for table in facts.tables] == ["before_table", "current_table"]
    assert [table.status for table in facts.tables] == [
        ComparisonTableStatus.DELETED_TABLE,
        ComparisonTableStatus.ADDED_TABLE,
    ]


def test_duplicate_effective_key_is_table_degraded_not_fake_update() -> None:
    before = "CREATE TABLE t (id INT NOT NULL PRIMARY KEY); INSERT INTO t VALUES (1);"
    current = """
        CREATE TABLE t (id INT NOT NULL PRIMARY KEY);
        INSERT INTO t VALUES (1), (1);
    """

    table = _one_table(_facts(_plan(before, current)))
    assert table.status is ComparisonTableStatus.DEGRADED
    assert table.row_added_count == 0
    assert table.row_deleted_count == 0
    assert table.row_modified_count == 0


def test_pair_and_table_early_exit_do_not_iterate_or_reopen_readers() -> None:
    sql = "CREATE TABLE t (id INT NOT NULL PRIMARY KEY); INSERT INTO t VALUES (1);"
    original = _bound(sql)
    assert original.table_set is not None
    wrapped_tables: list[SnapshotTable] = []
    counters: list[_CountingReader] = []
    for table in original.table_set.tables:
        assert table.reader is not None
        counter = _CountingReader(table.reader)
        counters.append(counter)
        wrapped_tables.append(replace(table, reader=cast(SnapshotTableReader, counter)))
    wrapped_set = SnapshotTableSet(
        snapshot_id=original.table_set.snapshot_id,
        snapshot_digest=original.table_set.snapshot_digest,
        table_ruleset_version=original.table_set.table_ruleset_version,
        tables=tuple(wrapped_tables),
        diagnostics=original.table_set.diagnostics,
    )
    descriptor = original.summary.tables[0]
    assert descriptor.raw_content_digest is not None
    storage_facts = (
        ComparisonStorageFacts(
            storage_rule_view=StorageRuleView(
                canonical_table=descriptor.table_name,
                canonical_key_policy=CanonicalKeyPolicy.DDL_PRIMARY_KEY_OR_KEYLESS,
                ordered_policy=OrderedPolicy.NONE,
                retained_columns=tuple(column.name for column in descriptor.columns),
                canonical_key_columns=descriptor.primary_key_columns,
            ),
            source_schema_digest=descriptor.business_schema_digest,
            canonical_schema_digest=descriptor.business_schema_digest,
            raw_content_digest=descriptor.raw_content_digest,
            storage_projection_version=STORAGE_PROJECTION_VERSION,
        ),
    )
    counted = BoundSnapshotInput(
        original.snapshot,
        original.summary,
        wrapped_set,
        storage_facts=storage_facts,
    )
    plan = plan_comparison(
        ComparisonRequest(
            pair_id="early-exit",
            before=counted,
            current=counted,
            rule_set=comparison_ruleset_for(),
        )
    )
    assert isinstance(plan, ComparisonPlan)
    result = compare_plan(plan)
    assert isinstance(result, DetailedFactsResult)
    assert result.status.value == "UNCHANGED"
    assert [(item.iterations, item.reopens) for item in counters] == [(0, 0)]


def test_table_early_exit_works_when_pair_snapshot_digests_differ() -> None:
    sql = "CREATE TABLE t (id INT NOT NULL PRIMARY KEY); INSERT INTO t VALUES (1);"
    before = _bound(sql)
    assert before.table_set is not None
    next_digest = raw_blob_digest(b"different-snapshot")
    current_snapshot = replace(before.snapshot, snapshot_digest=next_digest)
    current_summary = replace(before.summary, snapshot_digest=next_digest)
    current_set = replace(before.table_set, snapshot_digest=next_digest)
    current = BoundSnapshotInput(current_snapshot, current_summary, current_set)
    plan = _plan_from_bounds(before, current)

    facts = _facts(plan)
    assert facts.summary.status.value == "UNCHANGED"
    assert facts.tables[0].status is ComparisonTableStatus.UNCHANGED


def test_invalid_row_shape_is_degraded_and_never_treated_as_empty() -> None:
    sql = "CREATE TABLE t (id INT NOT NULL PRIMARY KEY); INSERT INTO t VALUES (1);"
    before = _bound(sql)
    current = _bound(sql.replace("VALUES (1)", "VALUES (2)"))
    assert current.table_set is not None
    current_table = current.table_set.tables[0]
    malformed = replace(
        current_table,
        reader=cast(SnapshotTableReader, _BadReader(current_table.descriptor)),
    )
    malformed_set = replace(current.table_set, tables=(malformed,))
    malformed_current = BoundSnapshotInput(current.snapshot, current.summary, malformed_set)

    table = _one_table(_facts(_plan_from_bounds(before, malformed_current)))
    assert table.status is ComparisonTableStatus.DEGRADED
    assert table.row_added_count == 0
    assert table.row_deleted_count == 0
    assert table.row_modified_count == 0
    assert table.diagnostics == ("ROW_SHAPE_MISMATCH",)


def test_facts_digest_is_deterministic_and_directional() -> None:
    before = "CREATE TABLE t (id INT NOT NULL PRIMARY KEY); INSERT INTO t VALUES (1);"
    current = "CREATE TABLE t (id INT NOT NULL PRIMARY KEY); INSERT INTO t VALUES (2);"

    first = _facts(_plan(before, current))
    second = _facts(_plan(before, current))
    reverse = _facts(_plan(current, before))

    assert first.comparison_digest == second.comparison_digest
    assert first.facts_core_digest == second.facts_core_digest
    assert first.comparison_digest != reverse.comparison_digest
    assert _one_table(first).row_added_count == _one_table(reverse).row_deleted_count
    assert _one_table(first).row_deleted_count == _one_table(reverse).row_added_count


def _plan_from_bounds(before: BoundSnapshotInput, current: BoundSnapshotInput) -> ComparisonPlan:
    plan = plan_comparison(
        ComparisonRequest(
            pair_id="standard-pair",
            before=before,
            current=current,
            rule_set=comparison_ruleset_for(),
        )
    )
    assert isinstance(plan, ComparisonPlan)
    return plan


def _bound_with_fallback_facts(sql: str, source_schema: bytes) -> BoundSnapshotInput:
    bound = _bound(sql)
    descriptor = bound.summary.tables[0]
    facts = ComparisonStorageFacts(
        storage_rule_view=StorageRuleView(
            canonical_table=descriptor.table_name,
            canonical_key_policy=CanonicalKeyPolicy.DDL_PRIMARY_KEY_OR_KEYLESS,
            ordered_policy=OrderedPolicy.NONE,
            retained_columns=tuple(column.name for column in descriptor.columns),
            canonical_key_columns=descriptor.primary_key_columns,
        ),
        source_schema_digest=raw_blob_digest(source_schema),
    )
    return replace(bound, storage_facts=(facts,))
