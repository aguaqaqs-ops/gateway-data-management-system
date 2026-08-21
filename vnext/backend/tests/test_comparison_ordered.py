"""S4 ordered comparison semantics."""

from __future__ import annotations

from dataclasses import dataclass, replace

import pytest
from gateway_shared_kernel import DigestRef, raw_blob_digest

from gateway_backend.capabilities.comparison import (
    ArtifactScope,
    BoundSnapshotInput,
    ComparisonFacts,
    ComparisonTableFact,
    ComparisonPlan,
    ComparisonTablePolicy,
    DetailedFactsResult,
    IdentityStatus,
    OrderedRecordKind,
    OrderedTablePolicy,
    PairRole,
    PairViewKind,
    bind_pair_input,
    compare_plan,
    plan_pair,
)
from gateway_backend.capabilities.snapshot_materialization.contracts import (
    BlankRowProvenance,
    MaterializationPolicy,
    SnapshotTableOrderedMetadata,
    SnapshotMaterializationStatus,
)
from tests.support.snapshot_materialization import materialize_sql
from tests.support.storage_projection import FakeSnapshotTableReader, int_cell, varchar_cell

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
    assessment_digest: DigestRef = raw_blob_digest(b"ordered-assessment")
    diagnostics: tuple[object, ...] = ()
    requires_continuation_confirmation: bool = False
    requires_submit_confirmation: bool = False


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
    policy: OrderedTablePolicy | None = None,
    scope: ArtifactScope = ArtifactScope.ALL_CHANGES,
) -> ComparisonPlan:
    before = _bound(before_sql)
    current = _bound(current_sql)
    bound = bind_pair_input(
        pair_id="ordered-pair",
        view_kind=PairViewKind.PAIR_COMPARISON,
        pair_role=PairRole.INITIAL_TO_MODIFIED,
        before=before,
        current=current,
        artifact_scope=scope,
        identity_assessment=_Assessment(
            before.snapshot.snapshot_digest,
            current.snapshot.snapshot_digest,
        ),
        table_policies=(
            ComparisonTablePolicy(
                table_name="t",
                ignored_columns=("no",),
                ordered_policy=policy or OrderedTablePolicy(),
            ),
        ),
    )
    planned = plan_pair(bound)
    assert isinstance(planned, ComparisonPlan)
    return planned


def _facts(plan: ComparisonPlan) -> ComparisonFacts:
    result = compare_plan(plan)
    assert isinstance(result, DetailedFactsResult)
    assert result.facts is not None
    return result.facts


def _table(facts: ComparisonFacts) -> ComparisonTableFact:
    assert len(facts.tables) == 1
    return facts.tables[0]


def _sql(rows: str, *, gid_type: str = "BIGINT") -> str:
    return f"""
        CREATE TABLE t (gid {gid_type} NULL, no INT NULL, value VARCHAR(8) NULL);
        INSERT INTO t VALUES {rows};
    """


def test_ordered_content_and_move_are_separate_records() -> None:
    before = _sql("(1, 1, 'a'), (2, 2, 'b')")
    current = _sql("(2, 1, 'b'), (1, 2, 'z')")

    table = _table(_facts(_plan(before, current)))
    assert table.row_modified_count == 1
    assert table.ordered_extension is not None
    kinds = [record.record_kind for record in table.ordered_extension.records]
    assert kinds.count(OrderedRecordKind.ROW_MODIFIED) == 1
    assert kinds.count(OrderedRecordKind.ROW_MOVED) == 2
    assert OrderedRecordKind.POSITION_CHANGED not in kinds
    assert table.ordered_extension.ordered_summary.position_changed_count == 2


def test_ordered_move_only_has_no_content_update() -> None:
    before = _sql("(1, 1, 'a'), (2, 2, 'b')")
    current = _sql("(2, 1, 'b'), (1, 2, 'a')")

    table = _table(_facts(_plan(before, current)))
    assert table.row_modified_count == 0
    assert table.ordered_extension is not None
    assert [record.record_kind for record in table.ordered_extension.records] == [
        OrderedRecordKind.ROW_MOVED,
        OrderedRecordKind.ROW_MOVED,
    ]


def test_ordered_absolute_renumber_is_position_change_not_move() -> None:
    before = _sql("(1, 1, 'a'), (2, 2, 'b')")
    current = _sql("(1, 10, 'a'), (2, 20, 'b')")

    extension = _table(_facts(_plan(before, current))).ordered_extension
    assert extension is not None
    assert [record.record_kind for record in extension.records] == [
        OrderedRecordKind.POSITION_CHANGED,
        OrderedRecordKind.POSITION_CHANGED,
    ]
    assert extension.ordered_summary.row_moved_count == 0
    assert extension.ordered_summary.position_changed_count == 2


def test_ordered_does_not_use_positional_fallback() -> None:
    before = _sql("(1, 1, 'a'), (2, 2, 'b')")
    current = _sql("(9, 1, 'a'), (2, 2, 'b')")

    table = _table(_facts(_plan(before, current)))
    assert table.ordered_extension is not None
    assert [record.record_kind for record in table.ordered_extension.records] == [
        OrderedRecordKind.ROW_ADDED,
        OrderedRecordKind.ROW_DELETED,
    ]
    assert table.row_modified_count == 0


def test_ordered_ignored_columns_do_not_trigger_content_change() -> None:
    before = _sql("(1, 1, 'a'), (2, 2, 'b')")
    current = _sql("(1, 1, 'z'), (2, 2, 'b')")
    policy = OrderedTablePolicy(value_columns=(), ignored_columns=("no", "value"))

    table = _table(_facts(_plan(before, current, policy=policy)))
    assert table.row_modified_count == 0
    assert table.ordered_extension is not None
    assert table.ordered_extension.records == ()


def test_update_only_suppresses_ordered_and_blank_insert_records() -> None:
    before = _sql("(1, 1, 'a')")
    current = _sql("(1, 1, 'a'), (NULL, 2, 'blank'), (2, 3, 'b')")

    table = _table(_facts(_plan(before, current, scope=ArtifactScope.UPDATE_ONLY)))
    assert table.records == ()
    assert table.suppressed_added_count == 1
    assert table.ordered_extension is not None
    assert table.ordered_extension.records == ()
    assert table.ordered_extension.ordered_summary.row_added_count == 1
    assert table.ordered_extension.status.value == "ORDERED_CHANGED"
    assert table.blank_extension is not None
    assert table.blank_extension.records == ()
    assert table.blank_extension.blank_summary.interval_inserted_count == 1
    assert table.blank_extension.status.value == "ORDERED_CHANGED"


@pytest.mark.parametrize(
    ("before", "current", "diagnostic"),
    (
        (_sql("(1, 1, 'a'), (2, 1, 'b')"), _sql("(1, 1, 'a')"), "ORDER_KEY_DUPLICATE"),
        (_sql("(1, 1, 'a'), (1, 2, 'b')"), _sql("(1, 1, 'a')"), "ROW_IDENTITY_DUPLICATE"),
        (_sql("(1, NULL, 'a')"), _sql("(1, 1, 'a')"), "ORDER_KEY_MISSING"),
    ),
)
def test_ordered_integrity_faults_degrade_without_records(
    before: str, current: str, diagnostic: str
) -> None:
    table = _table(_facts(_plan(before, current)))
    assert table.status.value == "DEGRADED"
    assert diagnostic in table.diagnostics
    assert table.ordered_extension is not None
    assert table.ordered_extension.replay_guarantee.value == "UNSUPPORTED"


def test_sql_reserved_pseudo_gid_is_rejected_at_materialization_boundary() -> None:
    result = materialize_sql(
        _sql("(4000000000, 1, 'a')"),
        policy=MaterializationPolicy.READERS_REQUIRED,
    )
    assert result.status is SnapshotMaterializationStatus.FAILED
    assert any(item.code.value == "RESERVED_PSEUDO_GID" for item in result.diagnostics)


def test_ordered_without_stable_key_never_infers_move() -> None:
    before = _sql("(1, 1, 'a'), (2, 2, 'b')")
    current = _sql("(2, 1, 'b'), (1, 2, 'a')")

    table = _table(_facts(_plan(before, current, policy=OrderedTablePolicy(row_identity_key=None))))
    assert table.status.value == "DEGRADED"
    assert table.ordered_extension is not None
    assert table.ordered_extension.records == ()


def test_ordered_missing_provenance_degrades_before_row_interpretation() -> None:
    before = _bound(_sql("(1, 1, 'a')"))
    current = _bound(_sql("(1, 1, 'a')"))
    assert before.table_set is not None
    assert current.table_set is not None
    before_table = replace(before.table_set.tables[0], ordered_metadata=None)
    before = replace(before, table_set=replace(before.table_set, tables=(before_table,)))

    bound = bind_pair_input(
        pair_id="missing-provenance",
        view_kind=PairViewKind.PAIR_COMPARISON,
        pair_role=PairRole.INITIAL_TO_MODIFIED,
        before=before,
        current=current,
        artifact_scope=ArtifactScope.ALL_CHANGES,
        identity_assessment=_Assessment(
            before.snapshot.snapshot_digest,
            current.snapshot.snapshot_digest,
        ),
        table_policies=(ComparisonTablePolicy("t", ignored_columns=("no",), ordered_policy=OrderedTablePolicy()),),
    )
    planned = plan_pair(bound)
    assert isinstance(planned, ComparisonPlan)
    table = _table(_facts(planned))
    assert table.status.value == "DEGRADED"
    assert table.diagnostics == ("BLANK_PROVENANCE_MISSING",)
    assert table.ordered_extension is not None
    assert table.ordered_extension.replay_guarantee.value == "UNSUPPORTED"


def test_ordered_facts_and_extension_digests_are_deterministic() -> None:
    before = _sql("(1, 1, 'a'), (2, 2, 'b')")
    current = _sql("(2, 1, 'b'), (1, 2, 'a')")

    first = _facts(_plan(before, current))
    second = _facts(_plan(before, current))
    assert first.facts_core_digest == second.facts_core_digest
    assert _table(first).table_fact_digest == _table(second).table_fact_digest


def test_canonical_pseudo_gid_requires_explicit_provenance() -> None:
    canonical = SnapshotTableOrderedMetadata(BlankRowProvenance.CANONICAL_PSEUDO_GID)
    before = _canonical_bound("old", canonical)
    current = _canonical_bound("new", canonical)
    bound = bind_pair_input(
        pair_id="canonical-pseudo",
        view_kind=PairViewKind.PAIR_COMPARISON,
        pair_role=PairRole.INITIAL_TO_MODIFIED,
        before=before,
        current=current,
        artifact_scope=ArtifactScope.ALL_CHANGES,
        identity_assessment=_Assessment(before.snapshot.snapshot_digest, current.snapshot.snapshot_digest),
        table_policies=(
            ComparisonTablePolicy(
                "t", ignored_columns=("no",), ordered_policy=OrderedTablePolicy()
            ),
        ),
    )
    planned = plan_pair(bound)
    assert isinstance(planned, ComparisonPlan)
    table = _table(_facts(planned))
    assert table.row_modified_count == 0
    assert table.blank_extension is not None
    assert table.blank_extension.records == ()


def _canonical_bound(value: str, metadata: SnapshotTableOrderedMetadata) -> BoundSnapshotInput:
    bound = _bound(_sql("(1, 1, 'seed')"))
    assert bound.table_set is not None
    source_table = bound.table_set.tables[0]
    reader = FakeSnapshotTableReader(
        source_table.descriptor,
        ((int_cell(4_000_000_000), int_cell(1), varchar_cell(value)),),
    )
    table = replace(source_table, reader=reader, ordered_metadata=metadata)
    return replace(bound, table_set=replace(bound.table_set, tables=(table,)))
