"""D production Arrow route against fixed comparison facts, not native output."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import ExitStack, closing
from dataclasses import replace
from threading import Event

import pyarrow as pa
import pytest
from gateway_shared_kernel import DigestRef, raw_blob_digest

from gateway_backend.artifacts import InMemoryArtifactStore
from gateway_backend.artifacts import ArtifactRef
from gateway_backend.application import pair_pipeline
from gateway_backend.application.pair_pipeline import run_preview_pair_pipeline
from gateway_backend.capabilities.comparison import (
    ArtifactScope, BoundSnapshotInput, ComparisonMode, ComparisonPlan, ComparisonRequest,
    ComparisonStorageFacts, ComparisonTableStatus, DetailedFactsResult, KeylessPolicy,
    compare_plan, plan_comparison,
)
from gateway_backend.capabilities.comparison.artifacts import (
    publish_records_closure, publish_records_closure_arrow,
)
from gateway_backend.capabilities.comparison.production import (
    ComparisonTaskSession, NativeComparison, _fresh_view_budget, _stream,
    compare_plan_native,
)
from gateway_backend.capabilities.risk_evaluation._facts import RiskRecordView
from gateway_backend.capabilities.risk_evaluation import (
    RiskEvaluationInput, RiskOptions, RiskRulesetSnapshot,
    V1_RISK_RULE_SPECS, evaluate_risk,
)
from gateway_backend.capabilities.snapshot_materialization import (
    ArrowSnapshotTableReader, open_snapshot_table_artifact, publish_canonical_tables,
    snapshot_table_from_arrow,
)
from gateway_backend.capabilities.snapshot_materialization._reader import BoundSnapshotTableReader
from gateway_backend.capabilities.snapshot_materialization.contracts import (
    ARTIFACT_COMPRESSION_ZSTD, ROW_FORMAT_PARQUET, ROW_MATERIALIZATION_PROFILE,
    SNAPSHOT_TABLE_ARTIFACT_CONTRACT_VERSION, SnapshotTable, SnapshotTableArtifact,
    SnapshotTableArtifactManifest,
)
from gateway_backend.capabilities.table_rules.contracts import (
    CanonicalKeyPolicy, OrderedPolicy, StorageRuleView, TableStaticRole,
)
from gateway_backend.capabilities.table_access import current_kernel_context, kernel_control_scope
from gateway_backend.operations.worker import ExecutionControl
from tests.support.comparison_s3_c_inputs import bound, canonical_stream, plan
from tests.support.snapshot_materialization import snapshot_table_as_arrow
from tests.support.table_rules import comparison_ruleset_for, fallback_record, standard_rule_record
from tests.test_comparison_replacement import _artifact_bound
from tests.test_comparison_rule_roles import _plan as role_plan

pytestmark = pytest.mark.unit


def _canonical_bound(source: BoundSnapshotInput) -> BoundSnapshotInput:
    assert source.table_set is not None
    tables = []
    for item in source.table_set.tables:
        assert isinstance(item.reader, BoundSnapshotTableReader)
        with closing(canonical_stream(item)) as stream:
            backing = stream.read_all()
        tables.append(snapshot_table_from_arrow(
            item.descriptor, backing, item.reader.source_descriptor(),
            ordered=item.ordered_metadata,
        ))
    return replace(source, table_set=replace(source.table_set, tables=tuple(tables)))


def _bit_artifact_bound(sql: str, store: InMemoryArtifactStore) -> BoundSnapshotInput:
    # The current storage projection excludes BIT; exercise the real canonical
    # writer from a test Arrow conversion of the business reader without
    # changing that frozen boundary or claiming a Preview BIT producer.
    source = bound(sql)
    assert source.table_set is not None and len(source.table_set.tables) == 1
    assert source.table_set.tables[0].descriptor.table_name == "t"
    table = snapshot_table_as_arrow(source.table_set.tables[0])
    published = publish_canonical_tables(
        (table,), snapshot_digest=source.snapshot.snapshot_digest,
        store=store, repository_id="replacement-fixture",
    )
    assert len(published) == 1 and published[0].artifact is not None
    return replace(source, table_set=replace(source.table_set, tables=published))


def test_fresh_and_persisted_canonical_bit_inputs_share_frozen_facts() -> None:
    store = InMemoryArtifactStore()
    before = _bit_artifact_bound(
        "CREATE TABLE t (id BIGINT PRIMARY KEY, bits BIT(9) NULL, note LONGTEXT NULL); "
        "INSERT INTO t VALUES (1, b'000000001', 'before'), (2, NULL, NULL);",
        store,
    )
    current = _bit_artifact_bound(
        "CREATE TABLE t (id BIGINT PRIMARY KEY, bits BIT(9) NULL, note LONGTEXT NULL); "
        "INSERT INTO t VALUES (1, b'100000001', 'after'), (2, NULL, NULL);",
        store,
    )
    assert before.table_set is not None and current.table_set is not None
    fresh = before.table_set.tables[0]
    assert isinstance(fresh.reader, ArrowSnapshotTableReader)
    assert fresh.reader.canonical_comparison_verified
    with closing(fresh.reader.reopen()) as reader:
        with closing(reader.arrow_stream()) as stream:
            assert not (stream.schema.metadata or {}).get(b"gdds.canonical_mapping_version")
            assert pa.types.is_binary(stream.schema.field("bits").type)

    old = compare_plan(plan(before, current))
    assert isinstance(old, DetailedFactsResult) and old.facts is not None
    expected = old.facts
    fresh_product = compare_plan_native(plan(before, current))
    try:
        assert isinstance(fresh_product.result, DetailedFactsResult)
        assert fresh_product.result.facts is not None
        assert fresh_product.result.facts.facts_core_digest == expected.facts_core_digest
        assert fresh_product.result.facts.comparison_digest == expected.comparison_digest
        assert fresh_product.result.facts.tables[0].row_modified_count == 1
    finally:
        fresh_product.close()

    # A fresh writer can also validate a LargeUtf8 business projection. The
    # comparison view keeps that physical offset width and borrows its buffers.
    with closing(fresh.reader.reopen()) as reader:
        with closing(reader.arrow_stream()) as stream:
            projected = stream.read_all()
    note_index = projected.schema.get_field_index("note")
    projected = projected.set_column(
        note_index, pa.field("note", pa.large_string(), nullable=True),
        projected.column(note_index).cast(pa.large_string()),
    )
    large_input = snapshot_table_from_arrow(
        fresh.descriptor, projected, fresh.reader.source_descriptor(),
        ordered=fresh.ordered_metadata,
    )
    large_fresh, = publish_canonical_tables(
        (large_input,), snapshot_digest=before.snapshot.snapshot_digest,
        store=store, repository_id="replacement-fixture",
    )
    assert isinstance(large_fresh.reader, ArrowSnapshotTableReader)
    assert large_fresh.reader.canonical_comparison_verified
    large_before = replace(before, table_set=replace(before.table_set, tables=(large_fresh,)))
    large_product = compare_plan_native(plan(large_before, current))
    try:
        assert isinstance(large_product.result, DetailedFactsResult)
        assert large_product.result.facts is not None
        assert large_product.result.facts.facts_core_digest == expected.facts_core_digest
    finally:
        large_product.close()

    opened = []
    for item in (before, current):
        assert item.table_set is not None
        artifact = item.table_set.tables[0].artifact
        assert artifact is not None
        table = open_snapshot_table_artifact(
            store, artifact.manifest_ref, repository_id="replacement-fixture",
            canonical_required=True,
        )
        assert isinstance(table.reader, ArrowSnapshotTableReader)
        assert not table.reader.canonical_comparison_verified
        with closing(table.reader.reopen()) as reader:
            with closing(reader.arrow_stream()) as stream:
                assert (stream.schema.metadata or {}).get(b"gdds.canonical_mapping_version") == b"1"
                assert pa.types.is_fixed_size_binary(stream.schema.field("bits").type)
        opened.append(replace(item, table_set=replace(item.table_set, tables=(table,))))
    persisted_product = compare_plan_native(plan(*opened))
    try:
        assert isinstance(persisted_product.result, DetailedFactsResult)
        assert persisted_product.result.facts is not None
        assert persisted_product.result.facts.facts_core_digest == expected.facts_core_digest
        assert persisted_product.result.facts.comparison_digest == expected.comparison_digest
    finally:
        persisted_product.close()


def test_fresh_profile_metadata_admission_releases_failed_reader() -> None:
    store = InMemoryArtifactStore()
    before = _artifact_bound(
        "CREATE TABLE t (id BIGINT PRIMARY KEY, value TEXT); "
        "INSERT INTO t VALUES (1, 'before');", store,
    )
    assert before.table_set is not None
    table = before.table_set.tables[0]
    assert isinstance(table.reader, ArrowSnapshotTableReader)
    assert table.reader.canonical_comparison_verified
    context = current_kernel_context()
    assert context is not None
    with context.memory.reserve(context.memory.available_bytes - 8192):
        retained = context.memory.used_bytes
        with pytest.raises(MemoryError):
            _stream(table)
        # The new reader wrapper's 512-byte metadata stays with the operation;
        # the failed profile allocation and Arrow backing borrower do not.
        assert context.memory.used_bytes == retained + 512


def test_fresh_high_bit_column_count_keeps_cold_native_phase_and_view_in_same_m() -> None:
    store = InMemoryArtifactStore()
    bit_columns = ", ".join(f"bit_{index} BIT(64) NULL" for index in range(128))
    before_values = ["1", *("b'1'" for _ in range(128))]
    current_values = before_values.copy()
    current_values[1] = "b'10'"

    def sql(values: list[str]) -> str:
        return (f"CREATE TABLE t (id BIGINT PRIMARY KEY, {bit_columns}); "
                f"INSERT INTO t VALUES ({', '.join(values)});")

    before = _bit_artifact_bound(sql(before_values), store)
    current = _bit_artifact_bound(sql(current_values), store)
    assert before.table_set is not None and current.table_set is not None
    before_table = before.table_set.tables[0]
    current_table = current.table_set.tables[0]
    assert _fresh_view_budget(before_table)[1] < 4 * 1024**2
    assert _fresh_view_budget(current_table)[1] < 4 * 1024**2

    old = compare_plan(plan(before, current))
    assert isinstance(old, DetailedFactsResult) and old.facts is not None
    product = compare_plan_native(plan(before, current))
    try:
        assert isinstance(product.result, DetailedFactsResult)
        assert product.result.facts is not None
        assert product.result.facts.facts_core_digest == old.facts.facts_core_digest
        assert product.result.facts.tables[0].row_modified_count == 1
        assert product.metrics is not None and product.metrics.native_calls == 1
        context = current_kernel_context()
        assert context is not None
        assert context.memory.high_water_bytes <= context.memory.limit_bytes
    finally:
        product.close()


def test_partial_canonical_metadata_is_rejected_after_fresh_publication() -> None:
    store = InMemoryArtifactStore()
    before = _artifact_bound(
        "CREATE TABLE t (id BIGINT PRIMARY KEY, value TEXT); "
        "INSERT INTO t VALUES (1, 'before');", store,
    )
    current = _artifact_bound(
        "CREATE TABLE t (id BIGINT PRIMARY KEY, value TEXT); "
        "INSERT INTO t VALUES (1, 'after');", store,
    )
    assert before.table_set is not None
    original = before.table_set.tables[0]
    assert isinstance(original.reader, ArrowSnapshotTableReader)
    with closing(original.reader.reopen()) as reader:
        with closing(reader.arrow_stream()) as stream:
            backing = stream.read_all()
    fields = list(backing.schema)
    fields[0] = fields[0].with_metadata({b"gdds.canonical_type": b"{}"})
    partial = pa.Table.from_arrays(
        [backing.column(index) for index in range(backing.num_columns)],
        schema=pa.schema(fields),
    )
    source = original.reader.source_descriptor()
    partial_input = snapshot_table_from_arrow(
        original.descriptor, partial, source, ordered=original.ordered_metadata,
    )
    published, = publish_canonical_tables(
        (partial_input,), snapshot_digest=before.snapshot.snapshot_digest,
        store=store, repository_id="replacement-fixture",
    )
    assert isinstance(published.reader, ArrowSnapshotTableReader)
    assert published.reader.canonical_comparison_verified
    changed = replace(before, table_set=replace(before.table_set, tables=(published,)))
    product = compare_plan_native(plan(changed, current))
    try:
        assert isinstance(product.result, DetailedFactsResult)
        assert product.result.facts is not None
        fact = product.result.facts.tables[0]
        assert fact.status is ComparisonTableStatus.DEGRADED
        assert fact.diagnostics == ("ValueError",)
        assert tuple(record.record_kind.value for record in fact.records) == ("TABLE_DEGRADED",)
    finally:
        product.close()


@pytest.mark.parametrize(
    ("before_sql", "current_sql", "record_kinds"),
    (
        (
            "CREATE TABLE t (id BIGINT PRIMARY KEY, note TEXT NULL); INSERT INTO t VALUES (1, 'before');",
            "CREATE TABLE t (id BIGINT PRIMARY KEY, note TEXT NULL); INSERT INTO t VALUES (1, NULL);",
            ("ROW_MODIFIED",),
        ),
        (
            "CREATE TABLE t (id BIGINT PRIMARY KEY, note TEXT NULL, obsolete TEXT NULL); "
            "INSERT INTO t VALUES (1, 'before', 'old');",
            "CREATE TABLE t (id BIGINT PRIMARY KEY, note TEXT NULL); "
            "INSERT INTO t VALUES (1, 'after');",
            ("ROW_MODIFIED", "SCHEMA_CHANGE"),
        ),
    ),
)
def test_production_standard_preserves_fixed_facts_and_facts_order_risk_view(
    before_sql: str, current_sql: str, record_kinds: tuple[str, ...],
) -> None:
    before = bound(before_sql)
    current = bound(current_sql)
    old = compare_plan(plan(before, current))
    assert isinstance(old, DetailedFactsResult) and old.facts is not None
    expected = old.facts

    native_plan = plan(_canonical_bound(before), _canonical_bound(current))
    product = compare_plan_native(native_plan)
    try:
        assert isinstance(product.result, DetailedFactsResult)
        actual = product.result.facts
        assert actual is not None
        assert actual.facts_core_digest == expected.facts_core_digest
        assert actual.comparison_digest == expected.comparison_digest
        assert actual.tables[0].table_fact_digest == expected.tables[0].table_fact_digest
        assert actual.tables[0].row_modified_count == 1
        handle = product.handles["t"]
        with closing(handle.risk_record_batches()) as reader:
            assert reader.schema.field("row_identity").type == pa.binary(32)
            assert reader.schema.field("changed_columns").type == pa.list_(pa.string())
        assert tuple(record.record_kind.value for record in RiskRecordView(handle)) == record_kinds
    finally:
        product.close()


def test_production_ordered_move_and_blank_match_frozen_facts_and_three_parquets() -> None:
    before = bound("""
        CREATE TABLE t (gid BIGINT NULL, no INT NULL, value VARCHAR(8) NULL);
        INSERT INTO t VALUES (1, 1, 'a'), (NULL, 2, 'x'), (2, 3, 'b'), (3, 4, 'c');
    """)
    current = bound("""
        CREATE TABLE t (gid BIGINT NULL, no INT NULL, value VARCHAR(8) NULL);
        INSERT INTO t VALUES (1, 1, 'a'), (3, 2, 'c'), (2, 3, 'b'), (NULL, 4, 'x');
    """)
    old = compare_plan(plan(before, current, ordered=True))
    assert isinstance(old, DetailedFactsResult) and old.facts is not None
    assert old.facts.tables[0].ordered_extension is not None
    assert old.facts.tables[0].blank_extension is not None
    old_store = InMemoryArtifactStore()
    old_published = publish_records_closure(old, old_store)
    assert isinstance(old_published, DetailedFactsResult)
    assert old_published.records_closure is not None
    blank_extension = old.facts.tables[0].blank_extension
    ordered_extension = old.facts.tables[0].ordered_extension
    assert blank_extension is not None and blank_extension.records
    assert ordered_extension is not None
    # Isolate the no-handle BLANK publication shape. Both writers consume the
    # same derived small facts, so the byte comparison tests the Arrow closure
    # writer's metadata path without using native output as expected bytes.
    blank_only_fact = replace(
        old.facts.tables[0], records=(),
        ordered_extension=replace(ordered_extension, records=()),
    )
    blank_only = replace(old, facts=replace(old.facts, tables=(blank_only_fact,)))
    blank_old_store = InMemoryArtifactStore()
    blank_new_store = InMemoryArtifactStore()
    blank_old = publish_records_closure(blank_only, blank_old_store)
    blank_new = publish_records_closure_arrow(blank_only, {}, blank_new_store)
    assert isinstance(blank_old, DetailedFactsResult)
    assert isinstance(blank_new, DetailedFactsResult)
    assert blank_old.records_closure is not None and blank_new.records_closure is not None
    assert len(blank_new.records_closure.records) == 1
    assert blank_new.records_closure.records[0].family.value == "BLANK"
    assert blank_new.records_closure.closure_manifest_digest == blank_old.records_closure.closure_manifest_digest
    assert blank_new_store.locate(blank_new.records_closure.records[0].records_ref) == blank_old_store.locate(
        blank_old.records_closure.records[0].records_ref
    )

    product = compare_plan_native(plan(
        _canonical_bound(before), _canonical_bound(current), ordered=True,
    ))
    try:
        assert isinstance(product.result, DetailedFactsResult)
        actual = product.result.facts
        assert actual is not None
        assert actual.facts_core_digest == old.facts.facts_core_digest
        assert actual.comparison_digest == old.facts.comparison_digest
        assert actual.tables[0].table_fact_digest == old.facts.tables[0].table_fact_digest
        assert actual.tables[0].ordered_extension is not None
        assert actual.tables[0].blank_extension is not None
        assert actual.tables[0].ordered_extension.ordered_summary == old.facts.tables[0].ordered_extension.ordered_summary
        assert actual.tables[0].blank_extension.blank_summary == old.facts.tables[0].blank_extension.blank_summary
        # This case has only ordered/blank movement, so row-target Risk does
        # not request a standard projection before the native phase seals.
        assert product.risk_handles == {}
        rules = RiskRulesetSnapshot(rules=V1_RISK_RULE_SPECS)
        old_risk = evaluate_risk(RiskEvaluationInput(
            comparison_facts=old.facts, risk_ruleset=rules, risk_options=RiskOptions(),
        ), artifact_store=InMemoryArtifactStore())
        new_risk = evaluate_risk(RiskEvaluationInput(
            comparison_facts=actual, risk_ruleset=rules, risk_options=RiskOptions(),
        ), artifact_store=InMemoryArtifactStore())
        assert old_risk.risk_evaluation is not None and new_risk.risk_evaluation is not None
        assert new_risk.risk_evaluation.risk_evaluation_digest == old_risk.risk_evaluation.risk_evaluation_digest
        new_store = InMemoryArtifactStore()
        new_published = publish_records_closure_arrow(
            product.result, product.handles, new_store,
        )
        assert isinstance(new_published, DetailedFactsResult)
        assert new_published.records_closure is not None
        old_entries = {
            entry.family: entry for entry in old_published.records_closure.records
        }
        new_entries = {
            entry.family: entry for entry in new_published.records_closure.records
        }
        assert set(new_entries) == set(old_entries)
        for family, old_entry in old_entries.items():
            new_entry = new_entries[family]
            assert new_entry.records_content_digest == old_entry.records_content_digest
            assert new_store.locate(new_entry.records_ref) == old_store.locate(old_entry.records_ref)
    finally:
        product.close()


def test_metadata_only_added_deleted_tables_replay_full_core_without_native_reads() -> None:
    before = bound("CREATE TABLE t (id INT PRIMARY KEY); INSERT INTO t VALUES (1);")
    current = bound("CREATE TABLE u (id INT PRIMARY KEY); INSERT INTO u VALUES (2);")
    old = compare_plan(plan(before, current))
    assert isinstance(old, DetailedFactsResult) and old.facts is not None
    product = compare_plan_native(plan(
        _canonical_bound(before), _canonical_bound(current),
    ))
    try:
        assert isinstance(product.result, DetailedFactsResult)
        assert product.result.facts is not None
        assert product.result.facts.facts_core_digest == old.facts.facts_core_digest
        assert product.result.facts.comparison_digest == old.facts.comparison_digest
        assert product.handles == {}
        assert product.metrics is not None
        assert product.metrics.native_calls == 0 and product.metrics.input_reads == 0
    finally:
        product.close()


@pytest.mark.parametrize("degrade_keyless", (False, True))
def test_source_key_transition_uses_the_keyless_policy(
    degrade_keyless: bool,
) -> None:
    before = _fallback_bound(
        "CREATE TABLE t (id BIGINT PRIMARY KEY, name TEXT); "
        "INSERT INTO t VALUES (1, 'old');"
    )
    current = _fallback_bound(
        "CREATE TABLE t (id BIGINT, name TEXT); "
        "INSERT INTO t VALUES (1, 'new');"
    )

    def transition_plan(left: BoundSnapshotInput, right: BoundSnapshotInput) -> ComparisonPlan:
        planned = plan_comparison(ComparisonRequest(
            pair_id="s3-d-source-key-transition", before=left, current=right,
            rule_set=comparison_ruleset_for(fallback_record()),
        ))
        assert isinstance(planned, ComparisonPlan)
        task = planned.tasks[0]
        assert task.policy is not None and task.policy.allow_keyless_key_transition
        assert task.policy.effective_key_before == ("id",)
        assert task.policy.effective_key_current == ()
        if degrade_keyless:
            task = replace(task, policy=replace(
                task.policy, keyless_policy=KeylessPolicy.DEGRADE_NO_COMPARE_KEY,
            ))
            planned = replace(planned, tasks=(task,))
        return planned

    old = compare_plan(transition_plan(before, current))
    assert isinstance(old, DetailedFactsResult) and old.facts is not None
    product = compare_plan_native(transition_plan(
        _canonical_bound(before), _canonical_bound(current),
    ))
    try:
        assert isinstance(product.result, DetailedFactsResult)
        actual = product.result.facts
        assert actual is not None
        assert actual.facts_core_digest == old.facts.facts_core_digest
        assert actual.comparison_digest == old.facts.comparison_digest
        assert actual.tables[0].table_fact_digest == old.facts.tables[0].table_fact_digest
        if degrade_keyless:
            assert actual.tables[0].status is ComparisonTableStatus.DEGRADED
    finally:
        product.close()


def test_keyless_degrade_policy_still_checks_reader_before_schema_record() -> None:
    before = _fallback_bound(
        "CREATE TABLE t (id BIGINT, name TEXT); INSERT INTO t VALUES (1, 'before');"
    )
    current = _fallback_bound(
        "CREATE TABLE t (id BIGINT, name TEXT); INSERT INTO t VALUES (1, 'after');"
    )

    def unavailable_plan(left: BoundSnapshotInput, right: BoundSnapshotInput) -> ComparisonPlan:
        planned = plan_comparison(ComparisonRequest(
            pair_id="s3-d-keyless-degrade-reader", before=left, current=right,
            rule_set=comparison_ruleset_for(fallback_record()),
        ))
        assert isinstance(planned, ComparisonPlan)
        task = planned.tasks[0]
        assert task.policy is not None and task.current_table is not None
        return replace(planned, tasks=(replace(
            task,
            policy=replace(task.policy, keyless_policy=KeylessPolicy.DEGRADE_NO_COMPARE_KEY),
            current_table=replace(task.current_table, reader=None, batch_reader=None),
        ),))

    old = compare_plan(unavailable_plan(before, current))
    assert isinstance(old, DetailedFactsResult) and old.facts is not None
    product = compare_plan_native(unavailable_plan(
        _canonical_bound(before), _canonical_bound(current),
    ))
    try:
        assert isinstance(product.result, DetailedFactsResult)
        actual = product.result.facts
        assert actual is not None
        assert actual.tables[0].diagnostics == ("TABLE_READER_UNAVAILABLE",)
        assert actual.facts_core_digest == old.facts.facts_core_digest
    finally:
        product.close()


@pytest.mark.parametrize("role", (TableStaticRole.BROWSE_ONLY, TableStaticRole.SNAPSHOT_ONLY))
def test_nonrecord_added_column_uses_shared_multiset_without_public_row_counts(
    role: TableStaticRole,
) -> None:
    before = bound(
        "CREATE TABLE t (id INT PRIMARY KEY, value INT); INSERT INTO t VALUES (1, 10);"
    )
    current = bound(
        "CREATE TABLE t (id INT PRIMARY KEY, value INT, note TEXT); "
        "INSERT INTO t VALUES (1, 11, 'new');"
    )
    old = compare_plan(role_plan(before, current, role))
    assert isinstance(old, DetailedFactsResult) and old.facts is not None
    product = compare_plan_native(role_plan(
        _canonical_bound(before), _canonical_bound(current), role,
    ))
    try:
        assert isinstance(product.result, DetailedFactsResult)
        actual = product.result.facts
        assert actual is not None
        fact = actual.tables[0]
        assert fact.status is ComparisonTableStatus.UNCHANGED
        assert fact.content_changed is True
        assert (fact.row_added_count, fact.row_deleted_count, fact.row_modified_count) == (0, 0, 0)
        assert (fact.suppressed_added_count, fact.suppressed_deleted_count) == (0, 0)
        assert actual.facts_core_digest == old.facts.facts_core_digest
        assert actual.comparison_digest == old.facts.comparison_digest
    finally:
        product.close()


def _fallback_bound(sql: str) -> BoundSnapshotInput:
    source = bound(sql)
    descriptor = source.summary.tables[0]
    return replace(source, storage_facts=(ComparisonStorageFacts(
        storage_rule_view=StorageRuleView(
            canonical_table=descriptor.table_name,
            canonical_key_policy=CanonicalKeyPolicy.DDL_PRIMARY_KEY_OR_KEYLESS,
            ordered_policy=OrderedPolicy.NONE,
            retained_columns=tuple(column.name for column in descriptor.columns),
            canonical_key_columns=descriptor.primary_key_columns,
        ),
        source_schema_digest=raw_blob_digest(b"s3-d-keyless-source"),
    ),))


def _keyless_update_only_plan(
    before: BoundSnapshotInput, current: BoundSnapshotInput,
) -> ComparisonPlan:
    planned = plan_comparison(ComparisonRequest(
        pair_id="s3-d-keyless-update-only", before=before, current=current,
        rule_set=comparison_ruleset_for(fallback_record()),
    ))
    assert isinstance(planned, ComparisonPlan)
    task = planned.tasks[0]
    assert task.policy is not None
    changed = replace(
        task, artifact_scope=ArtifactScope.UPDATE_ONLY,
        policy=replace(task.policy, compare_excluded_columns=("secret",)),
    )
    return replace(planned, tasks=(changed,))


def test_keyless_columns_added_update_only_keeps_suppressed_counts_and_status() -> None:
    before = _fallback_bound(
        "CREATE TABLE t (name TEXT, secret TEXT); INSERT INTO t VALUES ('a', 'x');"
    )
    current = _fallback_bound(
        "CREATE TABLE t (name TEXT, secret TEXT, added TEXT); "
        "INSERT INTO t VALUES ('b', 'y', 'z');"
    )
    old = compare_plan(_keyless_update_only_plan(before, current))
    assert isinstance(old, DetailedFactsResult) and old.facts is not None
    expected = old.facts
    native_plan = _keyless_update_only_plan(
        _canonical_bound(before), _canonical_bound(current),
    )
    product = compare_plan_native(native_plan)
    try:
        assert isinstance(product.result, DetailedFactsResult)
        actual = product.result.facts
        assert actual is not None
        fact = actual.tables[0]
        assert fact.status is ComparisonTableStatus.MODIFIED
        assert fact.content_changed is False
        assert (fact.row_added_count, fact.row_deleted_count) == (1, 1)
        assert (fact.suppressed_added_count, fact.suppressed_deleted_count) == (1, 1)
        assert actual.facts_core_digest == expected.facts_core_digest
        assert actual.comparison_digest == expected.comparison_digest
        assert fact.table_fact_digest == expected.tables[0].table_fact_digest
        rules = RiskRulesetSnapshot(rules=V1_RISK_RULE_SPECS)
        old_risk = evaluate_risk(RiskEvaluationInput(
            comparison_facts=expected, risk_ruleset=rules, risk_options=RiskOptions(),
        ), artifact_store=InMemoryArtifactStore())
        new_risk = evaluate_risk(RiskEvaluationInput(
            comparison_facts=actual, risk_ruleset=rules, risk_options=RiskOptions(),
        ), artifact_store=InMemoryArtifactStore())
        assert new_risk.risk_evaluation is not None and old_risk.risk_evaluation is not None
        assert new_risk.risk_evaluation.risk_evaluation_digest == old_risk.risk_evaluation.risk_evaluation_digest
    finally:
        product.close()


def test_full_pair_session_reuses_only_an_identical_declared_task() -> None:
    before = _canonical_bound(bound(
        "CREATE TABLE t (id BIGINT PRIMARY KEY, value TEXT); "
        "INSERT INTO t VALUES (1, 'before');"
    ))
    current = _canonical_bound(bound(
        "CREATE TABLE t (id BIGINT PRIMARY KEY, value TEXT); "
        "INSERT INTO t VALUES (1, 'after');"
    ))
    template = plan(before, current)
    first = replace(template, pair_id="baseline-to-initial")
    second = replace(template, pair_id="initial-to-modified")
    session = ComparisonTaskSession((first, second))
    context = current_kernel_context()
    assert context is not None
    first_result = compare_plan_native(first, session=session)
    try:
        assert isinstance(first_result.result, DetailedFactsResult)
        assert first_result.result.facts is not None
        first_core = first_result.result.facts.facts_core_digest
        assert first_result.task_keys is not None
        key = first_result.task_keys["t"]
        risk_charge = ExitStack()
        risk_charge.enter_context(context.memory.reserve(8192))
        assert session.risk_store(key, "risk-candidate", (), risk_charge)
        first_result.commit_cache()
    finally:
        first_result.close()
    assert session.calls == 1 and session.reads == 2 and session.hits == 0
    assert len(session.cached) == 1
    retained = context.memory.used_bytes
    session.risk_retire_last_uses({"t": key})
    assert context.memory.used_bytes == retained - 8192
    assert session.risk_candidates == {} and len(session.cached) == 1

    second_result = compare_plan_native(second, session=session)
    try:
        assert isinstance(second_result.result, DetailedFactsResult)
        assert second_result.result.facts is not None
        assert second_result.result.facts.facts_core_digest == first_core
        second_result.commit_cache()
    finally:
        second_result.close()
    assert session.calls == 1 and session.reads == 2 and session.hits == 1
    assert session.cached == {} and session.remaining_uses == {}


@pytest.mark.parametrize("row_change", ("modified", "added"))
def test_second_pair_writer_releases_optional_risk_retention_before_publication(
    monkeypatch: pytest.MonkeyPatch, row_change: str,
) -> None:
    store = InMemoryArtifactStore()
    before = _artifact_bound(
        "CREATE TABLE t (id BIGINT PRIMARY KEY, value TEXT); "
        "INSERT INTO t VALUES (1, 'before');", store,
    )
    current_sql = (
        "CREATE TABLE t (id BIGINT PRIMARY KEY, value TEXT); "
        + ("INSERT INTO t VALUES (1, 'after');" if row_change == "modified"
           else "INSERT INTO t VALUES (1, 'before'), (2, 'after');")
    )
    current = _artifact_bound(current_sql, store)
    assert before.table_set is not None and current.table_set is not None
    assert isinstance(before.table_set.tables[0].reader, ArrowSnapshotTableReader)
    assert isinstance(current.table_set.tables[0].reader, ArrowSnapshotTableReader)
    rules = comparison_ruleset_for(standard_rule_record("t"))
    first_plan = plan_comparison(ComparisonRequest(
        pair_id="writer-first", before=before, current=current, rule_set=rules,
    ))
    second_plan = plan_comparison(ComparisonRequest(
        pair_id="writer-second", before=before, current=current, rule_set=rules,
    ))
    assert isinstance(first_plan, ComparisonPlan) and isinstance(second_plan, ComparisonPlan)
    session = ComparisonTaskSession((first_plan, second_plan))
    assert tuple(session.remaining_uses.values()) == (2,)
    observed: list[tuple[ComparisonPlan, NativeComparison]] = []
    real_compare = pair_pipeline.compare_plan_native

    def observe_compare(
        planned: ComparisonPlan, *, session: ComparisonTaskSession | None = None,
    ) -> NativeComparison:
        result = real_compare(planned, session=session)
        observed.append((planned, result))
        return result

    monkeypatch.setattr(pair_pipeline, "compare_plan_native", observe_compare)
    first = run_preview_pair_pipeline(
        pair_id="writer-first", before=before, current=current,
        store=store, control=ExecutionControl(), on_cancel=lambda: None,
        rule_set=rules, assess_identity=False, dedup_session=session,
        repository_id="replacement-fixture",
    )
    assert first.records_closure is not None
    assert first.records_closure.records
    assert len(observed) == 1
    actual_plan, first_native = observed[0]
    assert isinstance(first_native.result, DetailedFactsResult)
    assert first_native.result.facts is not None
    first_fact = first_native.result.facts.tables[0]
    assert first_fact.status is ComparisonTableStatus.MODIFIED, (
        first_fact.status, first_fact.diagnostics,
        tuple(record.record_kind.value for record in first_fact.records),
        first_fact.row_added_count, first_fact.row_modified_count,
        None if first_native.metrics is None else first_native.metrics.native_calls,
    )
    assert (first_fact.row_added_count, first_fact.row_modified_count) == (
        (0, 1) if row_change == "modified" else (1, 0)
    )
    declared_key = session.declared_keys.get(("writer-first", "t"))
    assert declared_key is not None, (
        session.remaining_uses, session.calls, session.reads,
        first_fact.status, first_fact.diagnostics,
    )
    assert first_native.task_keys == {"t": declared_key}, (
        first_native.task_keys, first_native.consumed_keys,
        session.key_for(actual_plan, actual_plan.tasks[0]) == declared_key,
        session.calls, session.reads,
    )
    first_records = tuple(store.locate(entry.records_ref) for entry in first.records_closure.records)
    assert len(session.cached) == 1 and tuple(session.remaining_uses.values()) == (1,)
    assert len(session.risk_candidates) == 1
    context = current_kernel_context()
    assert context is not None
    _, optional_charges = next(iter(session.risk_candidates.values()))
    optional_charges.enter_context(context.memory.reserve(
        context.memory.available_bytes - 512 * 1024**2,
    ))
    evictions = 0
    original_evict = session.risk_evict_for_output

    def counted_evict() -> None:
        nonlocal evictions
        evictions += 1
        original_evict()

    monkeypatch.setattr(session, "risk_evict_for_output", counted_evict)
    second = run_preview_pair_pipeline(
        pair_id="writer-second", before=before, current=current,
        store=store, control=ExecutionControl(), on_cancel=lambda: None,
        rule_set=rules, assess_identity=False, dedup_session=session,
        repository_id="replacement-fixture",
    )
    assert evictions >= 1 and session.risk_candidates == {}
    assert second.records_closure is not None
    assert second.comparison_digest == first.comparison_digest
    assert second.risk_digest == first.risk_digest
    assert tuple((entry.family, entry.records_content_digest) for entry in second.records_closure.records) == tuple(
        (entry.family, entry.records_content_digest) for entry in first.records_closure.records
    )
    assert tuple(store.locate(entry.records_ref) for entry in second.records_closure.records) == first_records


def test_single_pair_declares_no_long_lived_comparison_result() -> None:
    before = _canonical_bound(bound(
        "CREATE TABLE t (id BIGINT PRIMARY KEY); INSERT INTO t VALUES (1);"
    ))
    current = _canonical_bound(bound(
        "CREATE TABLE t (id BIGINT PRIMARY KEY); INSERT INTO t VALUES (2);"
    ))
    single = plan(before, current)
    session = ComparisonTaskSession((single,))
    assert session.remaining_uses == {} and session.key_charges == {}
    product = compare_plan_native(single, session=session)
    try:
        product.commit_cache()
    finally:
        product.close()
    assert session.calls == 1 and session.reads == 2 and session.hits == 0
    assert session.cached == {}


def test_replacement_plans_declare_no_row_comparison_uses() -> None:
    before = _canonical_bound(bound(
        "CREATE TABLE t (id BIGINT PRIMARY KEY); INSERT INTO t VALUES (1);"
    ))
    current = _canonical_bound(bound(
        "CREATE TABLE t (id BIGINT PRIMARY KEY); INSERT INTO t VALUES (2);"
    ))
    template = replace(plan(before, current), mode=ComparisonMode.DATASET_REPLACEMENT)
    session = ComparisonTaskSession((
        replace(template, pair_id="replacement-first"),
        replace(template, pair_id="replacement-second"),
    ))
    assert session.remaining_uses == {}
    assert session.declared_keys == {}
    assert session.key_charges == {}


def test_large_optional_cache_key_safely_misses_without_changing_facts() -> None:
    before = _canonical_bound(bound(
        "CREATE TABLE t (id BIGINT PRIMARY KEY); INSERT INTO t VALUES (1);"
    ))
    current = _canonical_bound(bound(
        "CREATE TABLE t (id BIGINT PRIMARY KEY); INSERT INTO t VALUES (2);"
    ))
    template = replace(plan(before, current), options=(("large_optional_identity", "x" * 70_000),))
    first = replace(template, pair_id="large-key-first")
    second = replace(template, pair_id="large-key-second")
    session = ComparisonTaskSession((first, second))
    assert session.remaining_uses == {} and session.key_charges == {}
    baseline = compare_plan_native(first)
    candidate = compare_plan_native(first, session=session)
    try:
        assert isinstance(baseline.result, DetailedFactsResult)
        assert isinstance(candidate.result, DetailedFactsResult)
        assert baseline.result.facts is not None and candidate.result.facts is not None
        assert candidate.result.facts.facts_core_digest == baseline.result.facts.facts_core_digest
        assert candidate.result.facts.comparison_digest == baseline.result.facts.comparison_digest
        candidate.commit_cache()
        assert session.cached == {} and session.hits == 0
    finally:
        baseline.close()
        candidate.close()


def test_optional_cache_pressure_retries_after_releasing_failed_metadata_attempt() -> None:
    before = _canonical_bound(bound(
        "CREATE TABLE t (id BIGINT PRIMARY KEY); INSERT INTO t VALUES (1);"
    ))
    current = _canonical_bound(bound(
        "CREATE TABLE t (id BIGINT PRIMARY KEY); INSERT INTO t VALUES (2);"
    ))
    template = plan(before, current)
    first = replace(template, pair_id="pressure-first")
    second = replace(template, pair_id="pressure-second")
    context = current_kernel_context()
    assert context is not None
    reference = compare_plan_native(first)
    try:
        assert isinstance(reference.result, DetailedFactsResult)
        assert reference.result.facts is not None
        expected_core = reference.result.facts.facts_core_digest
    finally:
        reference.close()
    metadata_admissions = [
        item for item in context.memory.stage_admissions
        if item["stage"] == "comparison-metadata"
    ]
    assert metadata_admissions
    metadata_upper = int(metadata_admissions[-1]["temporary_limit_bytes"])
    retained_before = context.memory.used_bytes
    session = ComparisonTaskSession((first, second))
    assert session.key_charges
    # Charge optional operation-local retention from the real shared M so the
    # first attempt can admit metadata but has no native phase room. The
    # retry must release both this retention and its failed metadata charge.
    filler = context.memory.reserve(
        context.memory.available_bytes - metadata_upper,
    )
    session.key_charges["synthetic-optional-pressure"] = filler
    candidate = compare_plan_native(first, session=session)
    try:
        assert candidate.session is None
        assert isinstance(candidate.result, DetailedFactsResult)
        assert candidate.result.facts is not None
        assert candidate.result.facts.facts_core_digest == expected_core
    finally:
        candidate.close()
    # Reopening both Arrow readers retains two 512-byte source descriptors
    # through this operation. The failed attempt's metadata charge is gone.
    assert context.memory.used_bytes == retained_before + metadata_upper + 1024
    assert session.key_charges == {} and session.cached == {}


def _artifact_for(table: SnapshotTable, snapshot_digest: DigestRef) -> SnapshotTableArtifact:
    empty_digest = raw_blob_digest(b"")
    reference = ArtifactRef("s3-d-artifact", "application/octet-stream", 0, empty_digest)
    return SnapshotTableArtifact(
        manifest_ref=reference,
        manifest=SnapshotTableArtifactManifest(
            artifact_contract_version=SNAPSHOT_TABLE_ARTIFACT_CONTRACT_VERSION,
            snapshot_digest=snapshot_digest,
            table_name="t", descriptor=table.descriptor,
            row_file_refs=(reference,), row_format=ROW_FORMAT_PARQUET,
            compression=ARTIFACT_COMPRESSION_ZSTD,
            row_materialization_profile=ROW_MATERIALIZATION_PROFILE,
            artifact_content_digest=empty_digest, created_at="2026-11-08T00:00:00Z",
        ),
        row_layout_digest=empty_digest,
    )


def test_same_artifact_with_missing_reader_cannot_replay_a_cached_table() -> None:
    before = _canonical_bound(bound(
        "CREATE TABLE t (id BIGINT PRIMARY KEY, value TEXT); "
        "INSERT INTO t VALUES (1, 'before');"
    ))
    current = _canonical_bound(bound(
        "CREATE TABLE t (id BIGINT PRIMARY KEY, value TEXT); "
        "INSERT INTO t VALUES (1, 'after');"
    ))
    template = plan(before, current)
    table = template.tasks[0].current_table
    assert table is not None
    artifact = _artifact_for(table, current.snapshot.snapshot_digest)
    ready_table = replace(table, artifact=artifact)
    first = replace(template, pair_id="ready-reader", tasks=(replace(
        template.tasks[0], current_table=ready_table,
    ),))
    unavailable = replace(first, pair_id="missing-reader", tasks=(replace(
        first.tasks[0], current_table=replace(ready_table, reader=None, batch_reader=None),
    ),))
    old = compare_plan(unavailable)
    assert isinstance(old, DetailedFactsResult) and old.facts is not None
    session = ComparisonTaskSession((first, unavailable))
    assert session.remaining_uses == {}
    first_result = compare_plan_native(first, session=session)
    try:
        first_result.commit_cache()
    finally:
        first_result.close()
    second_result = compare_plan_native(unavailable, session=session)
    try:
        assert isinstance(second_result.result, DetailedFactsResult)
        actual = second_result.result.facts
        assert actual is not None
        assert actual.tables[0].status is ComparisonTableStatus.DEGRADED
        assert actual.tables[0].diagnostics == ("TABLE_READER_UNAVAILABLE",)
        assert actual.facts_core_digest == old.facts.facts_core_digest
        assert session.hits == 0
    finally:
        second_result.close()


def test_degraded_first_use_is_recomputed_for_the_next_same_key() -> None:
    before = _canonical_bound(bound(
        "CREATE TABLE t (id BIGINT PRIMARY KEY, value TEXT); "
        "INSERT INTO t VALUES (1, 'before');"
    ))
    current_sql = (
        "CREATE TABLE t (id BIGINT PRIMARY KEY, value TEXT); "
        "INSERT INTO t VALUES (1, 'after');"
    )
    failed_current = _canonical_bound(bound(current_sql))
    ready_current = _canonical_bound(bound(current_sql))
    failed = plan(before, failed_current)
    ready = plan(before, ready_current)
    failed_table = failed.tasks[0].current_table
    ready_table = ready.tasks[0].current_table
    assert failed_table is not None and ready_table is not None
    artifact = _artifact_for(failed_table, failed_current.snapshot.snapshot_digest)
    failed = replace(failed, pair_id="closed-first", tasks=(replace(
        failed.tasks[0], current_table=replace(failed_table, artifact=artifact),
    ),))
    ready = replace(ready, pair_id="ready-second", tasks=(replace(
        ready.tasks[0], current_table=replace(ready_table, artifact=artifact),
    ),))
    session = ComparisonTaskSession((failed, ready))
    assert len(session.remaining_uses) == 1
    assert failed.tasks[0].current_table is not None
    assert failed.tasks[0].current_table.reader is not None
    failed.tasks[0].current_table.reader.close()
    first_result = compare_plan_native(failed, session=session)
    try:
        assert isinstance(first_result.result, DetailedFactsResult)
        assert first_result.result.facts is not None
        assert first_result.result.facts.tables[0].status is ComparisonTableStatus.DEGRADED
        first_result.commit_cache()
    finally:
        first_result.close()
    assert session.cached == {}
    assert session.hits == 0
    second_result = compare_plan_native(ready, session=session)
    try:
        assert isinstance(second_result.result, DetailedFactsResult)
        assert second_result.result.facts is not None
        assert second_result.result.facts.tables[0].status is ComparisonTableStatus.MODIFIED
        assert second_result.metrics is not None
        assert second_result.metrics.native_calls == 1
        second_result.commit_cache()
    finally:
        second_result.close()
    assert session.hits == 0
    assert session.remaining_uses == {}


def test_cached_success_is_rechecked_when_the_same_reader_closes() -> None:
    before = _canonical_bound(bound(
        "CREATE TABLE t (id BIGINT PRIMARY KEY, value TEXT); "
        "INSERT INTO t VALUES (1, 'before');"
    ))
    current = _canonical_bound(bound(
        "CREATE TABLE t (id BIGINT PRIMARY KEY, value TEXT); "
        "INSERT INTO t VALUES (1, 'after');"
    ))
    template = plan(before, current)
    table = template.tasks[0].current_table
    assert table is not None and table.reader is not None
    artifact = _artifact_for(table, current.snapshot.snapshot_digest)
    task = replace(template.tasks[0], current_table=replace(table, artifact=artifact))
    first = replace(template, pair_id="ready-first", tasks=(task,))
    second = replace(template, pair_id="closed-second", tasks=(task,))
    session = ComparisonTaskSession((first, second))
    assert len(session.remaining_uses) == 1
    first_result = compare_plan_native(first, session=session)
    try:
        assert isinstance(first_result.result, DetailedFactsResult)
        assert first_result.result.facts is not None
        assert first_result.result.facts.tables[0].status is ComparisonTableStatus.MODIFIED
        first_result.commit_cache()
    finally:
        first_result.close()
    assert len(session.cached) == 1
    table.reader.close()
    expected = compare_plan(second)
    assert isinstance(expected, DetailedFactsResult) and expected.facts is not None
    second_result = compare_plan_native(second, session=session)
    try:
        assert isinstance(second_result.result, DetailedFactsResult)
        actual = second_result.result.facts
        assert actual is not None
        assert actual.tables[0].status is ComparisonTableStatus.DEGRADED
        assert actual.tables[0].diagnostics == ("TableAccessError",)
        assert actual.facts_core_digest == expected.facts.facts_core_digest
        assert actual.comparison_digest == expected.facts.comparison_digest
        assert session.calls == 1 and session.reads == 2 and session.hits == 0
        second_result.commit_cache()
    finally:
        second_result.close()
    assert session.cached == {} and session.remaining_uses == {}


def test_ordered_reader_failure_preserves_standard_ordered_and_blank_degradation() -> None:
    before = bound(
        "CREATE TABLE t (gid BIGINT, no BIGINT, name TEXT); "
        "INSERT INTO t VALUES (1, 1, 'before');"
    )
    current = bound(
        "CREATE TABLE t (gid BIGINT, no BIGINT, name TEXT); "
        "INSERT INTO t VALUES (1, 1, 'after');"
    )

    def missing_reader(planned: ComparisonPlan) -> ComparisonPlan:
        task = planned.tasks[0]
        assert task.current_table is not None
        return replace(planned, tasks=(replace(
            task, current_table=replace(task.current_table, reader=None, batch_reader=None),
        ),))

    old = compare_plan(missing_reader(plan(before, current, ordered=True)))
    assert isinstance(old, DetailedFactsResult) and old.facts is not None
    native_plan = missing_reader(plan(
        _canonical_bound(before), _canonical_bound(current), ordered=True,
    ))
    product = compare_plan_native(native_plan)
    try:
        assert isinstance(product.result, DetailedFactsResult)
        actual = product.result.facts
        assert actual is not None
        fact = actual.tables[0]
        assert fact.status is ComparisonTableStatus.DEGRADED
        assert fact.diagnostics == ("TABLE_READER_UNAVAILABLE",)
        assert fact.ordered_extension is not None and fact.blank_extension is not None
        assert fact.ordered_extension.ordered_summary.degraded_count == 1
        assert fact.blank_extension.blank_summary.degraded_count == 1
        assert actual.facts_core_digest == old.facts.facts_core_digest
        assert actual.comparison_digest == old.facts.comparison_digest
    finally:
        product.close()


@pytest.mark.parametrize("ordered", (False, True))
def test_closed_reader_is_an_ordinary_per_table_failure(
    ordered: bool,
) -> None:
    before_sql = (
        "CREATE TABLE t (gid BIGINT, no BIGINT, name TEXT); "
        "INSERT INTO t VALUES (1, 1, 'before');"
        if ordered else
        "CREATE TABLE t (id BIGINT PRIMARY KEY, name TEXT); "
        "INSERT INTO t VALUES (1, 'before');"
    )
    current_sql = before_sql.replace("before", "after")
    before = bound(before_sql)
    current = bound(current_sql)
    old_plan = plan(before, current, ordered=ordered)
    assert old_plan.tasks[0].current_table is not None
    assert old_plan.tasks[0].current_table.reader is not None
    old_plan.tasks[0].current_table.reader.close()
    old = compare_plan(old_plan)
    assert isinstance(old, DetailedFactsResult) and old.facts is not None
    native_plan = plan(
        _canonical_bound(bound(before_sql)),
        _canonical_bound(bound(current_sql)),
        ordered=ordered,
    )
    assert native_plan.tasks[0].current_table is not None
    assert native_plan.tasks[0].current_table.reader is not None
    native_plan.tasks[0].current_table.reader.close()
    product = compare_plan_native(native_plan)
    try:
        assert isinstance(product.result, DetailedFactsResult)
        actual = product.result.facts
        assert actual is not None
        assert actual.tables[0].status is ComparisonTableStatus.DEGRADED
        assert actual.tables[0].diagnostics == ("TableAccessError",)
        assert actual.tables[0].ordered_extension is None
        assert actual.tables[0].blank_extension is None
        assert actual.facts_core_digest == old.facts.facts_core_digest
    finally:
        product.close()


def test_duplicate_key_keeps_the_frozen_table_diagnostic() -> None:
    before = bound(
        "CREATE TABLE t (id INT NOT NULL PRIMARY KEY); INSERT INTO t VALUES (1);"
    )
    current = bound(
        "CREATE TABLE t (id INT NOT NULL PRIMARY KEY); INSERT INTO t VALUES (1), (1);"
    )
    old = compare_plan(plan(before, current))
    assert isinstance(old, DetailedFactsResult) and old.facts is not None
    assert old.facts.tables[0].diagnostics == ("DUPLICATE_EFFECTIVE_KEY:t",)
    product = compare_plan_native(plan(
        _canonical_bound(before), _canonical_bound(current),
    ))
    try:
        assert isinstance(product.result, DetailedFactsResult)
        actual = product.result.facts
        assert actual is not None
        assert actual.tables[0].diagnostics == ("DUPLICATE_EFFECTIVE_KEY:t",)
        assert actual.facts_core_digest == old.facts.facts_core_digest
        assert actual.comparison_digest == old.facts.comparison_digest
    finally:
        product.close()


@pytest.mark.parametrize("fresh", (False, True))
def test_reader_cancel_inside_arrow_stream_stops_before_table_degradation(
    monkeypatch: pytest.MonkeyPatch, fresh: bool,
) -> None:
    before_sql = (
        "CREATE TABLE t (id BIGINT PRIMARY KEY, value TEXT); "
        "INSERT INTO t VALUES (1, 'before');"
    )
    current_sql = (
        "CREATE TABLE t (id BIGINT PRIMARY KEY, value TEXT); "
        "INSERT INTO t VALUES (1, 'after');"
    )
    if fresh:
        store = InMemoryArtifactStore()
        before = _artifact_bound(before_sql, store)
        current = _artifact_bound(current_sql, store)
    else:
        before = _canonical_bound(bound(before_sql))
        current = _canonical_bound(bound(current_sql))
    planned = plan(before, current)
    stopped = Event()
    original = ArrowSnapshotTableReader.arrow_stream
    opens = 0

    def injected(reader: ArrowSnapshotTableReader) -> pa.RecordBatchReader:
        nonlocal opens
        opens += 1
        stream = original(reader)
        if opens != 2:
            return stream

        def batches() -> Iterator[pa.RecordBatch]:
            with closing(stream):
                for batch in stream:
                    yield batch
                stopped.set()
                raise RuntimeError("reader stopped during Arrow C Stream iteration")

        return pa.RecordBatchReader.from_batches(stream.schema, batches())

    monkeypatch.setattr(ArrowSnapshotTableReader, "arrow_stream", injected)
    # The inner call must stop; the control scope also checks the latched
    # probe on exit, so both checkpoints are inside the expected exception.
    with pytest.raises(InterruptedError):
        with kernel_control_scope(stopped, None):
            with pytest.raises(InterruptedError):
                compare_plan_native(planned)
    assert stopped.is_set()
