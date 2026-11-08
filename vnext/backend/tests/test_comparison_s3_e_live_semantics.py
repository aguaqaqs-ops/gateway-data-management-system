"""Business assertions retained on the live comparison route."""

from __future__ import annotations

from contextlib import closing
from dataclasses import replace

import pyarrow as pa
import pytest
from gateway_shared_kernel import raw_blob_digest

from gateway_backend.artifacts import InMemoryArtifactStore
from gateway_backend.capabilities.comparison import (
    BoundSnapshotInput, ComparisonFacts, ComparisonPlan, ComparisonRecordKind, ComparisonRequest,
    ComparisonStorageFacts, ComparisonTableStatus, DetailedFactsResult,
    OrderedTableProcessingMode, SchemaChangeSource, SchemaEvolution, plan_comparison,
)
from gateway_backend.capabilities.comparison.production import compare_plan_native
from gateway_backend.capabilities.risk_evaluation import (
    RiskEvaluationInput, RiskEvaluationStatus, RiskOptions, RiskReasonCode,
    RiskRulesetSnapshot, V1_RISK_RULE_SPECS, evaluate_risk,
)
from gateway_backend.capabilities.snapshot_materialization import (
    ArrowSnapshotTableReader, snapshot_table_from_arrow,
)
from gateway_backend.capabilities.snapshot_materialization.canonical_store import canonical_comparison_profile
from gateway_backend.capabilities.table_rules.contracts import (
    CanonicalKeyPolicy, OrderedPolicy, STORAGE_PROJECTION_VERSION, StorageRuleView,
)
from tests.support.comparison_s3_e_live import canonical_bound, native_product
from tests.support.repository_ref_materialization import canonical_schema_digest_for_descriptor
from tests.support.table_rules import comparison_ruleset_for, fallback_record

pytestmark = pytest.mark.unit

_ENUM_SET_CASES = (
    pytest.param("ENUM", "'a','b'", "'A','b'", "'b'", True,
                 SchemaEvolution.INCOMPATIBLE, id="enum-case-with-added-column"),
    pytest.param("SET", "'x','y'", "'x','z'", "'x'", True,
                 SchemaEvolution.INCOMPATIBLE, id="set-rename-with-added-column"),
    pytest.param("ENUM", "'a','b'", "'A','b'", "'b'", False,
                 SchemaEvolution.INCOMPATIBLE, id="enum-case-without-added-column"),
    pytest.param("SET", "'x','y'", "'x','z'", "'x'", False,
                 SchemaEvolution.INCOMPATIBLE, id="set-rename-without-added-column"),
    pytest.param("ENUM", "'a','c'", "'a','b','c'", "'c'", True,
                 SchemaEvolution.COLUMNS_ADDED, id="enum-add-in-middle"),
    pytest.param("SET", "'x','z'", "'x','y','z'", "'x'", True,
                 SchemaEvolution.COLUMNS_ADDED, id="set-add-in-middle"),
)


def _facts(before: str, current: str) -> ComparisonFacts:
    product = native_product(before, current)
    try:
        assert isinstance(product.result, DetailedFactsResult)
        assert product.result.facts is not None
        return product.result.facts
    finally:
        product.close()


def _fallback_source(sql: str) -> BoundSnapshotInput:
    source = canonical_bound(sql)
    descriptor = source.summary.tables[0]
    facts = ComparisonStorageFacts(
        storage_rule_view=StorageRuleView(
            canonical_table=descriptor.table_name,
            canonical_key_policy=CanonicalKeyPolicy.DDL_PRIMARY_KEY_OR_KEYLESS,
            ordered_policy=OrderedPolicy.NONE,
            retained_columns=tuple(column.name for column in descriptor.columns),
            canonical_key_columns=descriptor.primary_key_columns,
        ),
        source_schema_digest=descriptor.business_schema_digest,
    )
    return replace(source, storage_facts=(facts,))


@pytest.mark.parametrize(
    ("type_name", "old_labels", "new_labels", "value", "add_note", "evolution"),
    _ENUM_SET_CASES,
)
def test_enum_set_label_spelling_changes_schema_and_risk(
    type_name: str, old_labels: str, new_labels: str, value: str,
    add_note: bool, evolution: SchemaEvolution,
) -> None:
    before = (
        f"CREATE TABLE t (id INT PRIMARY KEY, state {type_name}({old_labels}) NULL);"
        f" INSERT INTO t VALUES (1,{value});"
    )
    note = ", note TEXT NULL" if add_note else ""
    note_value = ", 'new'" if add_note else ""
    current = (
        f"CREATE TABLE t (id INT PRIMARY KEY, state {type_name}({new_labels}) NULL{note});"
        f" INSERT INTO t VALUES (1,{value}{note_value});"
    )
    facts = _facts(before, current)
    table, = facts.tables
    assert table.schema_changes.schema_evolution is evolution
    assert table.schema_changes.current_only_columns == (("note",) if add_note else ())
    if evolution is SchemaEvolution.INCOMPATIBLE:
        assert table.status is ComparisonTableStatus.SCHEMA_CHANGED
        assert table.schema_changes.incompatible_columns == ("state",)
    else:
        assert table.status is ComparisonTableStatus.UNCHANGED
        assert table.schema_changes.incompatible_columns == ()
    risk = evaluate_risk(
        RiskEvaluationInput(
            comparison_facts=facts,
            risk_ruleset=RiskRulesetSnapshot(rules=V1_RISK_RULE_SPECS),
            risk_options=RiskOptions(),
        ),
        artifact_store=InMemoryArtifactStore(),
    )
    assert risk.status is RiskEvaluationStatus.READY
    assert risk.risk_report is not None
    if evolution is SchemaEvolution.INCOMPATIBLE:
        assert RiskReasonCode.SCHEMA_CHANGED in risk.risk_report.tables[0].reason_codes
        assert risk.risk_report.tables[0].risk_level.value == "MEDIUM_HIGH"
    else:
        assert risk.risk_report.tables == ()


@pytest.mark.parametrize(
    ("rows", "changed"),
    (
        ("(2,'b','y'),(1,'a','x')", False),
        ("(2,'b','x'),(1,'a','y')", True),
    ),
    ids=("added-column-physical-reorder", "excluded-values-swap-association"),
)
def test_standard_added_column_preserves_shared_row_association(
    rows: str, changed: bool,
) -> None:
    before = (
        "CREATE TABLE t (id INT PRIMARY KEY, name VARCHAR(8), secret VARCHAR(8));"
        " INSERT INTO t VALUES (1,'a','x'),(2,'b','y');"
    )
    added_rows = rows.replace(")", ",'z')")
    current = (
        "CREATE TABLE t (id INT PRIMARY KEY, name VARCHAR(8), secret VARCHAR(8),"
        " added VARCHAR(8));"
        f" INSERT INTO t VALUES {added_rows};"
    )
    product = native_product(before, current, compare_excluded_columns=("secret",))
    try:
        assert isinstance(product.result, DetailedFactsResult)
        assert product.result.facts is not None
        table, = product.result.facts.tables
        assert table.schema_changes.schema_evolution is SchemaEvolution.COLUMNS_ADDED
        assert table.status is ComparisonTableStatus.UNCHANGED
        assert table.content_changed is changed
        assert table.row_modified_count == 0
        assert product.handles["t"].family_summary("STANDARD")[0] == 0
    finally:
        product.close()


@pytest.mark.parametrize(
    ("current_rows", "changed"),
    (
        ("(2,'b','y'),(1,'a','x')", False),
        ("(2,'b','x'),(1,'a','y')", True),
    ),
    ids=("keyless-physical-reorder", "keyless-excluded-association"),
)
def test_keyless_added_column_uses_shared_row_multiset(
    current_rows: str, changed: bool,
) -> None:
    before = _fallback_source(
        "CREATE TABLE t (name VARCHAR(8), secret VARCHAR(8));"
        " INSERT INTO t VALUES ('a','x'),('b','y');",
    )
    rows_with_added = current_rows.replace(")", ",'new')")
    current = _fallback_source(
        "CREATE TABLE t (name VARCHAR(8), secret VARCHAR(8), added VARCHAR(8));"
        f" INSERT INTO t VALUES {rows_with_added};",
    )
    planned = plan_comparison(ComparisonRequest(
        pair_id="s3-e-keyless-added-association", before=before, current=current,
        rule_set=comparison_ruleset_for(replace(
            fallback_record(), compare_excluded_columns=("secret",),
        )),
    ))
    assert isinstance(planned, ComparisonPlan)
    product = compare_plan_native(planned)
    try:
        assert isinstance(product.result, DetailedFactsResult)
        assert product.result.facts is not None
        table, = product.result.facts.tables
        assert table.schema_changes.schema_evolution is SchemaEvolution.COLUMNS_ADDED
        assert table.status is ComparisonTableStatus.UNCHANGED
        assert table.content_changed is changed
        assert (table.row_added_count, table.row_deleted_count, table.row_modified_count) == (0, 0, 0)
        assert product.handles["t"].family_summary("STANDARD")[0] == 0
    finally:
        product.close()


def test_excluded_value_change_is_visible_without_row_record() -> None:
    schema = "CREATE TABLE t (id INT PRIMARY KEY, name VARCHAR(8), aux VARCHAR(8));"
    before = schema + " INSERT INTO t VALUES (1,'same','before');"
    current = schema + " INSERT INTO t VALUES (1,'same','current');"
    product = native_product(before, current, compare_excluded_columns=("aux",))
    try:
        assert isinstance(product.result, DetailedFactsResult)
        assert product.result.facts is not None
        table, = product.result.facts.tables
        assert table.status is ComparisonTableStatus.UNCHANGED
        assert table.content_changed
        assert table.row_modified_count == 0
        assert product.handles["t"].family_summary("STANDARD")[0] == 0
    finally:
        product.close()


def test_removed_column_is_distinct_from_incompatible_schema() -> None:
    before = (
        "CREATE TABLE t (id INT PRIMARY KEY, name VARCHAR(8), note TEXT);"
        " INSERT INTO t VALUES (1,'same','old');"
    )
    current = (
        "CREATE TABLE t (id INT PRIMARY KEY, name VARCHAR(8));"
        " INSERT INTO t VALUES (1,'same');"
    )
    table, = _facts(before, current).tables
    assert table.status is ComparisonTableStatus.SCHEMA_CHANGED
    assert table.schema_changes.schema_evolution is SchemaEvolution.COLUMNS_REMOVED
    assert table.schema_changes.before_only_columns == ("note",)


def test_incompatible_non_key_type_has_no_value_change_record() -> None:
    before = "CREATE TABLE t (id INT PRIMARY KEY, value INT); INSERT INTO t VALUES (1,1);"
    current = "CREATE TABLE t (id INT PRIMARY KEY, value BIGINT); INSERT INTO t VALUES (1,2);"
    product = native_product(before, current)
    try:
        assert isinstance(product.result, DetailedFactsResult)
        assert product.result.facts is not None
        table, = product.result.facts.tables
        assert table.status is ComparisonTableStatus.SCHEMA_CHANGED
        assert table.schema_changes.incompatible_columns == ("value",)
        assert table.row_modified_count == 0
        assert product.handles["t"].family_summary("STANDARD")[0] == 0
    finally:
        product.close()


def test_changed_effective_key_degrades_without_positional_match() -> None:
    before = "CREATE TABLE t (id INT PRIMARY KEY, value TEXT); INSERT INTO t VALUES (1,'a');"
    current = "CREATE TABLE t (code INT PRIMARY KEY, value TEXT); INSERT INTO t VALUES (1,'a');"
    product = native_product(before, current)
    try:
        assert isinstance(product.result, DetailedFactsResult)
        assert product.result.facts is not None
        table, = product.result.facts.tables
        assert table.status is ComparisonTableStatus.DEGRADED
        assert table.row_modified_count == 0
        assert tuple(record.record_kind for record in table.records) == (
            ComparisonRecordKind.TABLE_DEGRADED,
        )
        assert product.handles == {}
    finally:
        product.close()


def test_raw_primary_key_appearance_is_a_source_schema_change() -> None:
    keyless = _fallback_source(
        "CREATE TABLE t (value VARCHAR(8)); INSERT INTO t VALUES ('same');",
    )
    keyed = _fallback_source(
        "CREATE TABLE t (id INT PRIMARY KEY, value VARCHAR(8));"
        " INSERT INTO t VALUES (1,'same');",
    )

    planned = plan_comparison(ComparisonRequest(
        pair_id="s3-e-primary-key-appearance",
        before=keyless, current=keyed,
        rule_set=comparison_ruleset_for(fallback_record()),
    ))
    assert isinstance(planned, ComparisonPlan)
    product = compare_plan_native(planned)
    try:
        assert isinstance(product.result, DetailedFactsResult)
        assert product.result.facts is not None
        table, = product.result.facts.tables
        assert table.status is ComparisonTableStatus.SCHEMA_CHANGED
        assert table.schema_changes.change_source is SchemaChangeSource.SOURCE_SCHEMA
        assert not table.schema_changes.effective_compare_key_changed
        assert not any("KEY_DEGRADED" in diagnostic for diagnostic in table.diagnostics)
    finally:
        product.close()


def test_equal_canonical_storage_short_circuits_table_read_across_snapshots() -> None:
    source = canonical_bound(
        "CREATE TABLE t (id INT PRIMARY KEY, value TEXT); INSERT INTO t VALUES (1,'same');"
    )
    descriptor = source.summary.tables[0]
    assert descriptor.raw_content_digest is not None
    storage_fact = ComparisonStorageFacts(
        storage_rule_view=StorageRuleView(
            canonical_table=descriptor.table_name,
            canonical_key_policy=CanonicalKeyPolicy.DDL_PRIMARY_KEY_OR_KEYLESS,
            ordered_policy=OrderedPolicy.NONE,
            retained_columns=tuple(column.name for column in descriptor.columns),
            canonical_key_columns=descriptor.primary_key_columns,
        ),
        source_schema_digest=descriptor.business_schema_digest,
        canonical_schema_digest=canonical_schema_digest_for_descriptor(descriptor),
        raw_content_digest=descriptor.raw_content_digest,
        storage_projection_version=STORAGE_PROJECTION_VERSION,
    )
    before = replace(source, storage_facts=(storage_fact,))
    other_digest = raw_blob_digest(b"another snapshot with the same canonical table")
    assert before.table_set is not None
    current = replace(
        before,
        snapshot=replace(before.snapshot, snapshot_digest=other_digest),
        summary=replace(before.summary, snapshot_digest=other_digest),
        table_set=replace(before.table_set, snapshot_digest=other_digest),
    )
    planned = plan_comparison(ComparisonRequest(
        pair_id="s3-e-table-short-circuit", before=before, current=current,
        rule_set=comparison_ruleset_for(),
    ))
    assert isinstance(planned, ComparisonPlan)
    product = compare_plan_native(planned)
    try:
        assert isinstance(product.result, DetailedFactsResult)
        assert product.result.facts is not None
        table, = product.result.facts.tables
        assert table.status is ComparisonTableStatus.UNCHANGED
        assert product.metrics is not None
        assert product.metrics.native_calls == 0
        assert product.metrics.input_reads == 0
    finally:
        product.close()


def test_malformed_canonical_row_shape_degrades_instead_of_appearing_empty() -> None:
    schema = "CREATE TABLE t (id INT PRIMARY KEY, value TEXT);"
    before = canonical_bound(schema + " INSERT INTO t VALUES (1,'before');")
    current = canonical_bound(schema + " INSERT INTO t VALUES (1,'after');")
    assert current.table_set is not None
    original = current.table_set.tables[0]
    assert isinstance(original.reader, ArrowSnapshotTableReader)
    with closing(original.reader.reopen()) as isolated:
        with closing(isolated.arrow_stream()) as stream:
            backing = stream.read_all()
    profile, indices = canonical_comparison_profile(
        original.descriptor, backing.schema, metadata_budget_bytes=1024 * 1024,
    )
    profiled = pa.Table.from_arrays([backing.column(index) for index in indices], schema=profile)
    malformed = profiled.drop_columns("value")
    replacement = snapshot_table_from_arrow(
        original.descriptor, malformed, original.reader.source_descriptor(),
        ordered=original.ordered_metadata,
    )
    current = replace(
        current, table_set=replace(current.table_set, tables=(replacement,)),
    )
    planned = plan_comparison(ComparisonRequest(
        pair_id="s3-e-malformed-canonical-row", before=before, current=current,
        rule_set=comparison_ruleset_for(),
    ))
    assert isinstance(planned, ComparisonPlan)
    product = compare_plan_native(planned)
    try:
        assert isinstance(product.result, DetailedFactsResult)
        assert product.result.facts is not None
        table, = product.result.facts.tables
        assert table.status is ComparisonTableStatus.DEGRADED
        assert (table.row_added_count, table.row_deleted_count, table.row_modified_count) == (0, 0, 0)
        assert table.diagnostics == ("ROW_SHAPE_MISMATCH",)
        assert product.handles == {}
    finally:
        product.close()


def test_comparison_digest_is_repeatable_and_directional() -> None:
    schema = "CREATE TABLE t (id INT PRIMARY KEY);"
    before = schema + " INSERT INTO t VALUES (1);"
    current = schema + " INSERT INTO t VALUES (2);"
    first = _facts(before, current)
    repeat = _facts(before, current)
    reverse = _facts(current, before)
    assert first.comparison_digest == repeat.comparison_digest
    assert first.facts_core_digest == repeat.facts_core_digest
    assert first.comparison_digest != reverse.comparison_digest
    assert first.tables[0].row_added_count == reverse.tables[0].row_deleted_count
    assert first.tables[0].row_deleted_count == reverse.tables[0].row_added_count


def test_blank_position_renumber_keeps_occupancy_without_records() -> None:
    before = (
        "CREATE TABLE t (gid BIGINT NULL, no INT NULL, value VARCHAR(8));"
        " INSERT INTO t VALUES (1,1,'a'),(NULL,2,'x'),(NULL,3,'y'),(2,100,'b');"
    )
    current = (
        "CREATE TABLE t (gid BIGINT NULL, no INT NULL, value VARCHAR(8));"
        " INSERT INTO t VALUES (1,1,'a'),(NULL,20,'x'),(NULL,30,'y'),(2,100,'b');"
    )
    product = native_product(before, current, ordered=True)
    try:
        assert isinstance(product.result, DetailedFactsResult)
        assert product.result.facts is not None
        table, = product.result.facts.tables
        assert table.blank_extension is not None
        assert (table.blank_extension.before_occupancy_digest
                == table.blank_extension.current_occupancy_digest)
        assert table.blank_extension.blank_summary.blank_changed_count == 0
        assert all(product.handles["t"].family_summary(family)[0] == 0 for family in (
            "STANDARD", "ORDERED", "BLANK",
        ))
    finally:
        product.close()


def test_blank_interval_shift_emits_delete_and_insert_without_move_pairing() -> None:
    before = (
        "CREATE TABLE t (gid BIGINT NULL, no INT NULL, value VARCHAR(8));"
        " INSERT INTO t VALUES (1,1,'a'),(NULL,2,'x'),(2,3,'b');"
    )
    current = (
        "CREATE TABLE t (gid BIGINT NULL, no INT NULL, value VARCHAR(8));"
        " INSERT INTO t VALUES (1,1,'a'),(2,2,'b'),(NULL,3,'x');"
    )
    product = native_product(before, current, ordered=True)
    try:
        assert isinstance(product.result, DetailedFactsResult)
        assert product.result.facts is not None
        table, = product.result.facts.tables
        assert table.blank_extension is not None
        assert table.ordered_extension is not None
        assert table.blank_extension.blank_summary.interval_deleted_count == 1
        assert table.blank_extension.blank_summary.interval_inserted_count == 1
        assert table.ordered_extension.ordered_summary.row_moved_count == 0
        assert product.handles["t"].family_summary("STANDARD")[0] == 0
        with closing(product.handles["t"].record_batches("BLANK")) as reader:
            kinds = tuple(sorted(row["record_kind"] for batch in reader for row in batch.to_pylist()))
        assert kinds == ("BLANK_DELETE_INTERVAL", "BLANK_INSERT_INTERVAL")
    finally:
        product.close()


def test_absolute_order_renumber_is_a_position_shift_without_records() -> None:
    schema = "CREATE TABLE t (gid BIGINT NULL, no INT NULL, value VARCHAR(8));"
    before = schema + " INSERT INTO t VALUES (1,1,'a'),(2,2,'b');"
    current = schema + " INSERT INTO t VALUES (1,10,'a'),(2,20,'b');"
    product = native_product(before, current, ordered=True)
    try:
        assert isinstance(product.result, DetailedFactsResult)
        assert product.result.facts is not None
        table, = product.result.facts.tables
        assert table.ordered_extension is not None
        summary = table.ordered_extension.ordered_summary
        assert table.row_modified_count == 0
        assert summary.row_moved_count == 0
        assert summary.position_changed_count == 2
        assert table.ordered_extension.table_processing_mode is OrderedTableProcessingMode.SHIFT_REPAIRED
        assert product.handles["t"].family_summary("STANDARD")[0] == 0
        assert product.handles["t"].family_summary("ORDERED")[0] == 0
    finally:
        product.close()


@pytest.mark.parametrize(
    ("before_rows", "current_rows", "mode", "kinds"),
    (
        ("(1,1,'a'),(2,2,'b')", "(1,1,'z'),(2,2,'b')",
         OrderedTableProcessingMode.LOCAL_PATCH, {"ORDERED_ROW_MODIFIED"}),
        ("(1,1,'a'),(NULL,2,'x')", "(1,1,'a'),(NULL,2,'x'),(2,3,'b')",
         OrderedTableProcessingMode.TAIL_SEGMENT, {"ORDERED_ROW_ADDED"}),
    ),
    ids=("local-content-patch", "tail-append-after-blank"),
)
def test_ordered_public_processing_modes_have_live_batch_records(
    before_rows: str, current_rows: str,
    mode: OrderedTableProcessingMode, kinds: set[str],
) -> None:
    schema = "CREATE TABLE t (gid BIGINT NULL, no INT NULL, value VARCHAR(8));"
    product = native_product(
        schema + f" INSERT INTO t VALUES {before_rows};",
        schema + f" INSERT INTO t VALUES {current_rows};",
        ordered=True,
    )
    try:
        assert isinstance(product.result, DetailedFactsResult)
        assert product.result.facts is not None
        table, = product.result.facts.tables
        assert table.ordered_extension is not None
        assert table.ordered_extension.table_processing_mode is mode
        with closing(product.handles["t"].record_batches("ORDERED")) as reader:
            actual = {row["record_kind"] for batch in reader for row in batch.to_pylist()}
        assert actual == kinds
    finally:
        product.close()


def test_ordered_identity_change_emits_add_delete_without_positional_fallback() -> None:
    schema = "CREATE TABLE t (gid BIGINT NULL, no INT NULL, value VARCHAR(8));"
    before = schema + " INSERT INTO t VALUES (1,1,'a'),(2,2,'b');"
    current = schema + " INSERT INTO t VALUES (9,1,'a'),(2,2,'b');"
    product = native_product(before, current, ordered=True)
    try:
        assert isinstance(product.result, DetailedFactsResult)
        assert product.result.facts is not None
        table, = product.result.facts.tables
        assert table.row_modified_count == 0
        with closing(product.handles["t"].record_batches("ORDERED")) as reader:
            kinds = {row["record_kind"] for batch in reader for row in batch.to_pylist()}
        assert kinds == {"ORDERED_ROW_ADDED", "ORDERED_ROW_DELETED"}
    finally:
        product.close()


def test_missing_order_key_degrades_ordered_replay() -> None:
    schema = "CREATE TABLE t (gid BIGINT NULL, no INT NULL, value VARCHAR(8));"
    before = schema + " INSERT INTO t VALUES (1,NULL,'a');"
    current = schema + " INSERT INTO t VALUES (1,1,'a');"
    product = native_product(before, current, ordered=True)
    try:
        assert isinstance(product.result, DetailedFactsResult)
        assert product.result.facts is not None
        table, = product.result.facts.tables
        assert table.status is ComparisonTableStatus.DEGRADED
        assert "ORDER_KEY_MISSING" in table.diagnostics
        assert table.ordered_extension is not None
        assert table.ordered_extension.replay_guarantee.value == "UNSUPPORTED"
        assert product.handles == {}
    finally:
        product.close()


def test_ordered_excluded_value_change_is_visible_without_row_record() -> None:
    schema = "CREATE TABLE t (gid BIGINT NULL, no INT NULL, value VARCHAR(8));"
    before = schema + " INSERT INTO t VALUES (1,1,'a'),(2,2,'b');"
    current = schema + " INSERT INTO t VALUES (1,1,'z'),(2,2,'b');"
    product = native_product(before, current, ordered=True, compare_excluded_columns=("value",))
    try:
        assert isinstance(product.result, DetailedFactsResult)
        assert product.result.facts is not None
        table, = product.result.facts.tables
        assert table.status is ComparisonTableStatus.UNCHANGED
        assert table.content_changed
        assert table.row_modified_count == 0
        assert table.ordered_extension is not None
        assert product.handles["t"].family_summary("ORDERED")[0] == 0
    finally:
        product.close()
