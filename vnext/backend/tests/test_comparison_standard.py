"""S3 standard comparison facts, records and digest contract tests."""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import cast

import pytest
from gateway_shared_kernel import DigestRef, NullScalar, raw_blob_digest

from gateway_backend.capabilities.comparison import (
    ArtifactScope,
    BoundSnapshotInput,
    ComparisonFacts,
    ComparisonPlan,
    ComparisonRecordKind,
    ComparisonTablePolicy,
    ComparisonTableFact,
    ComparisonTableStatus,
    DetailedFactsResult,
    IdentityStatus,
    KeylessPolicy,
    PairRole,
    PairViewKind,
    bind_pair_input,
    compare_plan,
    plan_pair,
)
from gateway_backend.capabilities.snapshot_materialization.contracts import (
    MaterializationPolicy,
    SnapshotTable,
    SnapshotTableReader,
    SnapshotTableSet,
)
from tests.support.snapshot_materialization import materialize_sql

pytestmark = pytest.mark.unit


@dataclass(frozen=True, slots=True)
class _Assessment:
    before_snapshot_digest: DigestRef
    current_snapshot_digest: DigestRef
    status: IdentityStatus = IdentityStatus.SAME_PROJECT
    schema_version: str = "project-identity-assessment/v1"
    rule_version: str = "version-manager-overlap/v1"
    comparable_columns: tuple[str, ...] = ()
    before_row_count: int = 0
    current_row_count: int = 0
    before_distinct_entry_count: int = 0
    current_distinct_entry_count: int = 0
    matched_entry_count: int = 0
    before_entry_set_digest: DigestRef | None = None
    current_entry_set_digest: DigestRef | None = None
    assessment_digest: DigestRef = raw_blob_digest(b"comparison-assessment")
    diagnostics: tuple[object, ...] = ()
    requires_continuation_confirmation: bool = False
    requires_submit_confirmation: bool = False


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
        raise AssertionError("reopen must not be used by comparison core")


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
    scope: ArtifactScope = ArtifactScope.ALL_CHANGES,
    policies: tuple[ComparisonTablePolicy, ...] = (),
) -> ComparisonPlan:
    before = _bound(before_sql)
    current = _bound(current_sql)
    bound = bind_pair_input(
        pair_id="standard-pair",
        view_kind=PairViewKind.PAIR_COMPARISON,
        pair_role=PairRole.INITIAL_TO_MODIFIED,
        before=before,
        current=current,
        artifact_scope=scope,
        identity_assessment=_Assessment(
            before.snapshot.snapshot_digest,
            current.snapshot.snapshot_digest,
        ),
        table_policies=policies,
    )
    plan = plan_pair(bound)
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


def test_schema_alignment_uses_intersection_and_reports_current_only_columns() -> None:
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
    assert table.status is ComparisonTableStatus.SCHEMA_CHANGED
    assert table.schema_changes.selected_columns == ("id", "name")
    assert table.schema_changes.current_only_columns == ("note",)
    assert table.row_modified_count == 0
    assert [record.record_kind for record in table.records] == [ComparisonRecordKind.SCHEMA_CHANGE]


def test_ignored_only_change_is_schema_only_and_does_not_modify_rows() -> None:
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
                policies=(ComparisonTablePolicy("t", ignored_columns=("aux",)),),
            )
        )
    )
    assert table.status is ComparisonTableStatus.SCHEMA_ONLY_CHANGED
    assert table.row_modified_count == 0
    assert [record.record_kind for record in table.records] == [ComparisonRecordKind.SCHEMA_CHANGE]


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


@pytest.mark.parametrize(
    "policy, expected_status, expected_added, expected_deleted",
    (
        (
            KeylessPolicy.DEGRADE_NO_COMPARE_KEY,
            ComparisonTableStatus.DEGRADED,
            0,
            0,
        ),
        (
            KeylessPolicy.FULL_ROW_DIGEST_SET_DIFF,
            ComparisonTableStatus.MODIFIED,
            1,
            1,
        ),
    ),
)
def test_keyless_policy_is_explicit_and_deterministic(
    policy: KeylessPolicy,
    expected_status: ComparisonTableStatus,
    expected_added: int,
    expected_deleted: int,
) -> None:
    before = "CREATE TABLE t (value VARCHAR(8) NULL); INSERT INTO t VALUES ('a'), ('b');"
    current = "CREATE TABLE t (value VARCHAR(8) NULL); INSERT INTO t VALUES ('a'), ('c');"

    table = _one_table(
        _facts(
            _plan(
                before,
                current,
                policies=(ComparisonTablePolicy("t", keyless_policy=policy),),
            )
        )
    )
    assert table.status is expected_status
    assert table.row_added_count == expected_added
    assert table.row_deleted_count == expected_deleted
    assert all(record.record_kind is not ComparisonRecordKind.ROW_MODIFIED for record in table.records)


def test_update_only_suppresses_records_but_keeps_counts() -> None:
    before = "CREATE TABLE t (id INT NOT NULL PRIMARY KEY); INSERT INTO t VALUES (1);"
    current = "CREATE TABLE t (id INT NOT NULL PRIMARY KEY); INSERT INTO t VALUES (2);"

    table = _one_table(_facts(_plan(before, current, scope=ArtifactScope.UPDATE_ONLY)))
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
    counted = BoundSnapshotInput(original.snapshot, original.summary, wrapped_set)
    bound = bind_pair_input(
        pair_id="early-exit",
        view_kind=PairViewKind.PAIR_COMPARISON,
        pair_role=PairRole.INITIAL_TO_MODIFIED,
        before=counted,
        current=counted,
        artifact_scope=ArtifactScope.ALL_CHANGES,
        identity_assessment=_Assessment(
            counted.snapshot.snapshot_digest,
            counted.snapshot.snapshot_digest,
        ),
    )
    plan = plan_pair(bound)
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
    bound = bind_pair_input(
        pair_id="standard-pair",
        view_kind=PairViewKind.PAIR_COMPARISON,
        pair_role=PairRole.INITIAL_TO_MODIFIED,
        before=before,
        current=current,
        artifact_scope=ArtifactScope.ALL_CHANGES,
        identity_assessment=_Assessment(
            before.snapshot.snapshot_digest,
            current.snapshot.snapshot_digest,
        ),
    )
    plan = plan_pair(bound)
    assert isinstance(plan, ComparisonPlan)
    return plan
