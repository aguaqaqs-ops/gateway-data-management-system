"""Owning vectors for conservative structure hiding and backend evidence."""
from __future__ import annotations

from contextlib import closing
from dataclasses import replace

import pytest

from gateway_backend.application.comparison_audit import ComparisonStructureAudit, publish_structure_audit
from gateway_backend.artifacts import InMemoryArtifactStore
from gateway_backend.capabilities.comparison.contracts import (
    ComparisonTableStatus, DetailedFactsResult,
    OrderedExtension, OrderedStatus, OrderedSummary, BlankExtension, BlankSummary,
)
from gateway_backend.capabilities.comparison.cache_codec import ComparisonCacheCodec, restore_table_fact, _neutral_fact
from gateway_backend.capabilities.comparison.production import compare_plan_native
from gateway_backend.capabilities.comparison.presentation import structure_change_is_audit_only, visible_table_fact
from gateway_backend.capabilities.comparison.task_input import TableTaskIdentity, build_table_task_identity
from gateway_backend.capabilities.comparison import native
from gateway_backend.capabilities.table_access import current_kernel_context
from tests.support.comparison_s3_c_inputs import plan
from tests.support.comparison_s3_e_live import canonical_bound, native_product
from tests.support.comparison_cache_inputs import complete_canonical_bound

pytestmark = pytest.mark.unit

_BEFORE = "CREATE TABLE t(id INT PRIMARY KEY,v INT,old TEXT); INSERT INTO t VALUES (1,10,'old');"
_COLUMN_CASES = (
    pytest.param("CREATE TABLE t(id INT PRIMARY KEY,v INT); INSERT INTO t VALUES (1,10);", True, id="removed"),
    pytest.param("CREATE TABLE t(id INT PRIMARY KEY,v INT,new TEXT); INSERT INTO t VALUES (1,10,'new');", True, id="added-and-removed"),
    pytest.param("CREATE TABLE t(id INT PRIMARY KEY,v INT,old TEXT,new TEXT); INSERT INTO t VALUES (1,10,'old','new');", True, id="added"),
    pytest.param("CREATE TABLE t(id INT PRIMARY KEY,v INT); INSERT INTO t VALUES (1,11);", False, id="shared-updated"),
    pytest.param("CREATE TABLE t(id INT PRIMARY KEY,v TEXT); INSERT INTO t VALUES (1,'10');", False, id="incompatible"),
    pytest.param("CREATE TABLE t(id INT,v INT PRIMARY KEY); INSERT INTO t VALUES (1,10);", False, id="key-changed"),
    pytest.param("CREATE TABLE t(id INT PRIMARY KEY,v INT); INSERT INTO t VALUES (2,10);", False, id="raw-add-delete"),
)


@pytest.mark.parametrize(("current", "hidden"), _COLUMN_CASES)
@pytest.mark.parametrize("update_only", (False, True))
def test_shared_values_must_be_proved_before_structure_is_hidden(current: str, hidden: bool, update_only: bool) -> None:
    from gateway_backend.capabilities.table_rules.contracts import TableArtifactScope
    scope = TableArtifactScope.UPDATE_ONLY if update_only else TableArtifactScope.ALL_CHANGES
    with closing(native_product(_BEFORE, current, artifact_scope=scope)) as product:
        assert isinstance(product.result, DetailedFactsResult) and product.result.facts is not None
        facts = product.result.facts
        table, = facts.tables
        assert structure_change_is_audit_only(table) is hidden
        assert facts.summary.changed_table_count == (0 if hidden else 1)
        if hidden:
            assert table.shared_value_equality == "NATIVE_SHARED_VALUES"
            assert table.schema_changes.before_only_columns or table.schema_changes.current_only_columns
            assert visible_table_fact(table).status is ComparisonTableStatus.UNCHANGED
        elif update_only and "VALUES (2," in current:
            assert table.row_added_count == table.row_deleted_count == 1
            assert table.suppressed_added_count == table.suppressed_deleted_count == 1


@pytest.mark.parametrize("key", ("PRIMARY KEY", ""))
def test_empty_bound_tables_need_no_guessed_row_key(key: str) -> None:
    with closing(native_product(f"CREATE TABLE t(id INT {key},old TEXT);", f"CREATE TABLE t(id INT {key},new TEXT);")) as product:
        assert isinstance(product.result, DetailedFactsResult) and product.result.facts is not None
        table, = product.result.facts.tables
        assert table.shared_value_equality == "BOUND_EMPTY_DESCRIPTORS"
        assert structure_change_is_audit_only(table)


def test_unknown_metadata_and_other_ordered_semantics_are_never_hidden() -> None:
    with closing(native_product(_BEFORE, "CREATE TABLE t(id INT PRIMARY KEY,v INT); INSERT INTO t VALUES (1,10);")) as product:
        assert isinstance(product.result, DetailedFactsResult) and product.result.facts is not None
        table, = product.result.facts.tables
        rejected = (
            replace(table, shared_value_equality=None),
            replace(table, content_changed=True),
            replace(table, status=ComparisonTableStatus.DEGRADED),
            replace(table, row_count_current=None),
            replace(table, diagnostics=("EFFECTIVE_KEY_MISSING",)),
            replace(table, ordered_extension=OrderedExtension(OrderedStatus.CHANGED, OrderedSummary(row_moved_count=1))),
            replace(table, ordered_extension=OrderedExtension(OrderedStatus.CHANGED, OrderedSummary(position_changed_count=1))),
            replace(table, blank_extension=BlankExtension(OrderedStatus.CHANGED, BlankSummary(blank_changed_count=1))),
        )
        assert all(not structure_change_is_audit_only(item) for item in rejected)


@pytest.mark.parametrize("ordered", (False, True))
def test_cache_restores_equality_and_current_pair_audit(ordered: bool) -> None:
    before = ("CREATE TABLE t(gid BIGINT,no INT,v INT,old TEXT); INSERT INTO t VALUES(1,1,10,'old');"
        if ordered else _BEFORE)
    current = ("CREATE TABLE t(gid BIGINT,no INT,v INT,new TEXT); INSERT INTO t VALUES(1,1,10,'new');"
        if ordered else "CREATE TABLE t(id INT PRIMARY KEY,v INT,new TEXT); INSERT INTO t VALUES(1,10,'new');")
    planned = plan(complete_canonical_bound(canonical_bound(before), ordered=ordered),
        complete_canonical_bound(canonical_bound(current), ordered=ordered), ordered=ordered)
    identity = build_table_task_identity(planned, planned.tasks[0], repository_id="r", artifact_scope="s")
    assert isinstance(identity, TableTaskIdentity)
    context = current_kernel_context()
    assert context is not None
    with closing(compare_plan_native(planned, retain_cache_candidates=True)) as cold:
        assert isinstance(cold.result, DetailedFactsResult) and cold.result.facts is not None
        facts = cold.result.facts
        table, = facts.tables
        assert structure_change_is_audit_only(table)
        payload = cold.encode_cache_candidate("t", identity, context)
    operation = native.begin_records_operation(native_budget_bytes=128 * 1024**2,
        cancel_probe=context.cancel_probe, deadline_monotonic=context.deadline_monotonic)
    handle = None
    try:
        restored, handle = ComparisonCacheCodec.restore(payload, identity, planned.tasks[0], operation, context)
        assert restored.shared_value_equality == table.shared_value_equality
        assert structure_change_is_audit_only(restored)
        store = InMemoryArtifactStore()
        for pair in ("cold-pair", "hot-pair"):
            ref = publish_structure_audit(replace(planned, pair_id=pair), replace(facts, tables=(replace(restored, table_fact_digest=table.table_fact_digest),)), store)
            assert ref is not None
            document = ComparisonStructureAudit.model_validate_json(store.locate(ref))
            assert document.pair_id == pair
            assert document.tables[0].raw_fact.schema_changes
            assert document.comparison_digest == facts.comparison_digest.value
    finally:
        if handle is not None:
            handle.close()
        operation.close()
        payload.close()


def test_cache_document_rejects_unknown_evidence_and_extra_fields() -> None:
    import json
    planned = plan(canonical_bound(_BEFORE), canonical_bound("CREATE TABLE t(id INT PRIMARY KEY,v INT); INSERT INTO t VALUES(1,10);"))
    with closing(compare_plan_native(planned)) as product:
        assert isinstance(product.result, DetailedFactsResult) and product.result.facts is not None
        raw = json.loads(_neutral_fact(product.result.facts.tables[0]))
        for patch in ({"shared_value_equality": "ASSUMED_ZERO"}, {"extra": 1}, {"row_added_count": False}):
            with pytest.raises(ValueError):
                restore_table_fact(json.dumps(raw | patch).encode(), planned.tasks[0])


def test_hidden_pair_is_consistent_and_audit_is_only_in_backend_ready_closure() -> None:
    import json
    from gateway_backend.application.pair_pipeline import run_history_pair_pipeline
    from gateway_backend.application.history.compare_jobs import _required_ready_refs
    from gateway_backend.application.checkpoints import prepare_ready_closure, load_ready_closure
    from gateway_backend.artifacts.store import put_with_built_ref
    from gateway_backend.artifacts.location import ArtifactLocation, build_artifact_id
    from gateway_backend.capabilities.surface_assembly import SurfaceChangeKind
    from gateway_backend.operations.worker import ExecutionControl
    from tests.support.table_rules import comparison_ruleset_for, standard_rule_record
    from tests.test_comparison_replacement import _artifact_bound

    store = InMemoryArtifactStore()
    result = run_history_pair_pipeline(pair_id="audit-pair",
        before=_artifact_bound(_BEFORE, store),
        current=_artifact_bound("CREATE TABLE t(id INT PRIMARY KEY,v INT); INSERT INTO t VALUES(1,10);", store),
        rule_set=comparison_ruleset_for(standard_rule_record("t")), store=store,
        control=ExecutionControl(), on_cancel=lambda: None, repository_id="replacement-fixture")
    surface = result.surface_result.surface
    assert surface is not None
    table, = surface.tables
    assert table.change_kind is SurfaceChangeKind.UNCHANGED
    assert not table.content_changed and table.schema_summary is None
    assert table.table_refs.current_table_ref is not None
    assert surface.summary.changed_table_count == 0
    assert surface.refs.risk_report_ref is None  # No schema or row risk was emitted.
    navigation = json.loads(store.locate(surface.projections[0].projection_ref))
    tabs = [tab for group in navigation["groups"] for item in group["items"] for tab in item["tabs"]]
    assert any(tab["table_id"] == "t" for tab in tabs)
    assert all(tab["facts"] is None or tab["facts"]["change_kind"] == "UNCHANGED" for tab in tabs)
    assert result.structure_audit_ref is not None
    assert result.structure_audit_ref not in result.surface_result.referenced_artifacts
    bundle = put_with_built_ref(store, b"bundle-placeholder",
        artifact_id=build_artifact_id(ArtifactLocation.EXPORT, "test-bundle", "audit"), media_type="application/octet-stream")
    refs = _required_ready_refs([result], bundle, ())
    assert result.structure_audit_ref in refs
    ready = prepare_ready_closure(store, refs, "test")
    assert result.structure_audit_ref in load_ready_closure(store, ready).artifact_refs()
    del store._artifacts[result.structure_audit_ref.artifact_id]
    with pytest.raises(ValueError):
        load_ready_closure(store, ready)


@pytest.mark.parametrize("change", ("moved", "position", "blank", "retained"))
def test_native_ordered_changes_are_not_hidden(change: str) -> None:
    before = "CREATE TABLE t(gid BIGINT,no INT,v INT,old TEXT); INSERT INTO t VALUES(1,1,10,'x'),(2,2,20,'x');"
    inserts = {
        "moved": "(2,1,20),(1,2,10)",
        "position": "(1,2,10),(2,3,20)",
        "blank": "(1,1,10),(NULL,2,NULL),(2,3,20)",
        "retained": "(1,1,11),(2,2,20)",
    }
    current = "CREATE TABLE t(gid BIGINT,no INT,v INT); INSERT INTO t VALUES" + inserts[change] + ";"
    with closing(native_product(before, current, ordered=True, compare_excluded_columns=("v",) if change == "retained" else ())) as product:
        assert isinstance(product.result, DetailedFactsResult) and product.result.facts is not None
        table, = product.result.facts.tables
        assert not structure_change_is_audit_only(table)


@pytest.mark.parametrize("key", ("PRIMARY KEY", ""))
@pytest.mark.parametrize("added", (False, True))
def test_browse_role_never_treats_default_zero_counts_as_equality(key: str, added: bool) -> None:
    from gateway_backend.capabilities.table_rules.contracts import TableStaticRole
    from tests.test_comparison_rule_roles import _plan
    before = canonical_bound(f"CREATE TABLE t(id INT {key},v INT,old TEXT); INSERT INTO t VALUES(1,10,'x');")
    current = canonical_bound(f"CREATE TABLE t(id INT {key},v INT{',old TEXT,new TEXT' if added else ''}); "
        + ("INSERT INTO t VALUES(1,10,'x','new');" if added else "INSERT INTO t VALUES(1,10);"))
    with closing(compare_plan_native(_plan(before, current, TableStaticRole.BROWSE_ONLY))) as product:
        assert isinstance(product.result, DetailedFactsResult) and product.result.facts is not None
        table, = product.result.facts.tables
        assert table.row_added_count == table.row_deleted_count == table.row_modified_count == 0
        # BROWSE_ONLY deliberately resolves no comparison key, even with a DDL
        # storage PK. Metadata/default zeros cannot stand in for a row proof.
        assert not structure_change_is_audit_only(table)
        assert visible_table_fact(table).status is ComparisonTableStatus.SCHEMA_ONLY_CHANGED


@pytest.mark.parametrize("rows", ("(1,10),(1,11)", "(NULL,10)", "(1,10)"))
def test_invalid_or_missing_comparison_keys_never_authorize_hiding(rows: str) -> None:
    before_rows = rows.replace(")", ",'x')")
    planned = plan(canonical_bound(f"CREATE TABLE t(id INT,v INT,old TEXT); INSERT INTO t VALUES{before_rows};"),
        canonical_bound(f"CREATE TABLE t(id INT,v INT); INSERT INTO t VALUES{rows};"))
    task, = planned.tasks
    assert task.policy is not None
    policy = replace(task.policy, effective_key_before=("missing",) if rows == "(1,10)" else ("id",),
        effective_key_current=("missing",) if rows == "(1,10)" else ("id",))
    with closing(compare_plan_native(replace(planned, tasks=(replace(task, policy=policy),)))) as product:
        assert isinstance(product.result, DetailedFactsResult) and product.result.facts is not None
        table, = product.result.facts.tables
        assert table.status is ComparisonTableStatus.DEGRADED
        assert not structure_change_is_audit_only(table)


def test_audit_bindings_reject_dropped_refs_incomplete_pairs_and_wrong_pair() -> None:
    from gateway_backend.application.comparison_audit import structure_audit_binding, verify_structure_audit_bindings
    planned = plan(canonical_bound(_BEFORE), canonical_bound("CREATE TABLE t(id INT PRIMARY KEY,v INT); INSERT INTO t VALUES(1,10);"))
    with closing(compare_plan_native(planned)) as product:
        assert isinstance(product.result, DetailedFactsResult) and product.result.facts is not None
        facts = product.result.facts
        store = InMemoryArtifactStore()
        ref = publish_structure_audit(planned, facts, store)
        assert ref is not None
        binding = structure_audit_binding(planned.pair_id, facts.comparison_digest.value, ref)
        verify_structure_audit_bindings(store, [binding], (ref,), [planned.pair_id])
        for bindings, refs, pairs in (
            ([binding], (), [planned.pair_id]),
            ([], (ref,), [planned.pair_id]),
            ([binding | {"pair_id": "wrong"}], (ref,), ["wrong"]),
            ([binding | {"comparison_digest": "wrong"}], (ref,), [planned.pair_id]),
        ):
            with pytest.raises(ValueError):
                verify_structure_audit_bindings(store, bindings, refs, pairs)


def test_audit_is_verified_before_hidden_success_is_returned() -> None:
    from gateway_backend.artifacts import ArtifactRef
    class BrokenAuditStore(InMemoryArtifactStore):
        def locate(self, ref: ArtifactRef) -> bytes:
            raw = super().locate(ref)
            return b"{}" if b"comparison-structure-audit" in raw else raw
    planned = plan(canonical_bound(_BEFORE), canonical_bound("CREATE TABLE t(id INT PRIMARY KEY,v INT); INSERT INTO t VALUES(1,10);"))
    with closing(compare_plan_native(planned)) as product:
        assert isinstance(product.result, DetailedFactsResult) and product.result.facts is not None
        with pytest.raises(ValueError):
            publish_structure_audit(planned, product.result.facts, BrokenAuditStore())
