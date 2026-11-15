"""Published pair evidence, rather than manufactured navigation, reaches a bundle."""
from __future__ import annotations

import json
from dataclasses import replace
from typing import Any

import pyarrow as pa
import pyarrow.parquet as pq  # type: ignore[import-untyped]
import pytest

from gateway_shared_kernel import raw_blob_digest
from gateway_backend.application.pair_pipeline import run_history_pair_pipeline, run_preview_pair_pipeline
from gateway_backend.application.preview_jobs import surface_artifact_closure
from gateway_backend.artifacts import InMemoryArtifactStore
from gateway_backend.capabilities.bundle_assembly import (
    BUNDLE_CONTRACT_VERSION, BundleAssemblyInput, BundleAssemblyStatus, BundleInput,
    BundlePairInput, BundleProfile, assemble_bundle, validate_bundle,
)
from gateway_backend.capabilities.business_navigation import validate_navigation
from gateway_backend.capabilities.surface_assembly import SurfaceAssemblyStatus
from gateway_backend.operations.worker import ExecutionControl
from tests.support.comparison_cache_inputs import complete_canonical_bound
from tests.support.comparison_s3_e_live import canonical_bound
from tests.support.table_rules import comparison_ruleset_for, ordered_record, standard_rule_record


def test_preview_ordered_swap_publishes_movement_risk() -> None:
    schema = "CREATE TABLE t (gid BIGINT NULL, no INT NULL, value VARCHAR(8));"
    before = complete_canonical_bound(canonical_bound(schema + " INSERT INTO t VALUES (1,1,'a'),(2,2,'b');"))
    current = complete_canonical_bound(canonical_bound(schema + " INSERT INTO t VALUES (1,2,'a'),(2,1,'b');"))
    store = InMemoryArtifactStore()
    result = run_preview_pair_pipeline(
        pair_id="initial_to_modified", before=before, current=current, store=store,
        control=ExecutionControl(), on_cancel=lambda: pytest.fail("unexpected cancellation"),
        rule_set=comparison_ruleset_for(ordered_record(r"^t$")),
        assess_identity=False, repository_id="replacement-fixture",
    )
    assert result.surface_result.status is SurfaceAssemblyStatus.READY
    surface = result.surface_result.surface
    assert surface is not None
    table, = surface.tables
    assert table.ordered_extension is not None
    assert table.risk_refs.risk_level is not None
    assert table.risk_refs.risk_level.value == "MEDIUM_HIGH"
    assert table.risk_refs.reason_codes == ("ORDERED_MOVE",)
    assert table.risk_refs.annotation_count == 1


def test_preview_uses_identical_current_device_when_baseline_reader_is_omitted() -> None:
    ddl = ("CREATE TABLE device(gid BIGINT PRIMARY KEY,dev_addr INT,description TEXT);"
           "CREATE TABLE device_cfg(id BIGINT PRIMARY KEY,gid BIGINT,note TEXT);")
    devices = "INSERT INTO device VALUES (7,49,'device');"
    before = complete_canonical_bound(canonical_bound(ddl + devices +
        "INSERT INTO device_cfg VALUES(1,7,'old');"))
    current = complete_canonical_bound(canonical_bound(ddl + devices +
        "INSERT INTO device_cfg VALUES(1,7,'new');"))
    assert before.table_set is not None
    before = replace(before, table_set=replace(before.table_set,
        tables=tuple(t for t in before.table_set.tables if t.descriptor.table_name != "device")))
    store = InMemoryArtifactStore()
    result = run_preview_pair_pipeline(pair_id="initial_to_modified", before=before, current=current,
        store=store, control=ExecutionControl(), on_cancel=lambda: pytest.fail("unexpected cancellation"),
        rule_set=comparison_ruleset_for(standard_rule_record("device"), standard_rule_record("device_cfg")),
        assess_identity=False, repository_id="replacement-fixture")
    assert result.surface_result.status is SurfaceAssemblyStatus.READY
    surface = result.surface_result.surface
    assert surface is not None
    projection, = surface.projections
    navigation = validate_navigation(json.loads(store.locate(projection.projection_ref)), replacement=False)
    item = next(item for item in navigation["groups"][1]["items"] if item["item_key"] == "device:addr:49")
    tab = next(tab for tab in item["tabs"] if tab["table_id"] == "device_cfg")
    assert tab["row_filter"] == {"before": {"column": "gid", "values": [7]},
                                 "current": {"column": "gid", "values": [7]}}
    assert tab["facts"]["before_row_count"] == tab["facts"]["current_row_count"] == 1


@pytest.mark.parametrize(("changed_cfg", "schema_added"), ((False, False), (True, False), (False, True)))
def test_real_pair_device_gid_change_keeps_unchanged_cfg_before_and_locator_context(changed_cfg: bool, schema_added: bool) -> None:
    ddl = ("CREATE TABLE device(gid BIGINT PRIMARY KEY,dev_addr INT,description TEXT);"
        "CREATE TABLE device_cfg(id BIGINT PRIMARY KEY,gid BIGINT,note TEXT);")
    before = complete_canonical_bound(canonical_bound(ddl +
        "INSERT INTO device VALUES (7,49,'old device'); INSERT INTO device_cfg VALUES(1,7,'old');"))
    current_ddl = ddl.replace("note TEXT);", "note TEXT,extra TEXT);") if schema_added else ddl
    current = complete_canonical_bound(canonical_bound(current_ddl +
        "INSERT INTO device VALUES (8,49,'current device'); INSERT INTO device_cfg VALUES(1,7,'" +
        ("new" if changed_cfg else "old") + ("','added" if schema_added else "") + "');"))
    store = InMemoryArtifactStore()
    result = run_preview_pair_pipeline(pair_id="initial_to_modified", before=before, current=current,
        store=store, control=ExecutionControl(), on_cancel=lambda: pytest.fail("unexpected cancellation"),
        rule_set=comparison_ruleset_for(standard_rule_record("device"), standard_rule_record("device_cfg")),
        assess_identity=False, repository_id="replacement-fixture")
    assert result.surface_result.status is SurfaceAssemblyStatus.READY
    surface = result.surface_result.surface
    assert surface is not None
    projection, = surface.projections
    assert projection.projection_id == "business_navigation" and projection.projection_kind == "BUSINESS_NAVIGATION"
    payload = store.locate(projection.projection_ref)
    assert projection.projection_digest == raw_blob_digest(payload)
    navigation = validate_navigation(json.loads(payload), replacement=False)
    items: list[dict[str, Any]] = navigation["groups"][1]["items"]
    device = next(item for item in items if item["item_key"] == "device:addr:49")
    tab = next(tab for tab in device["tabs"] if tab["table_id"] == "device_cfg")
    assert tab["row_filter"] == {"before": {"column": "gid", "values": [7]}, "current": {"column": "gid", "values": [8]}}
    assert tab["facts"]["before_row_count"] == 1 and tab["facts"]["current_row_count"] == 0
    assert tab["facts"]["basis"] == "EXACT"
    cfg = next(table for table in surface.tables if table.table_name == "device_cfg")
    assert (cfg.row_locator_ref is not None) is changed_cfg
    if changed_cfg:
        assert cfg.row_locator_ref is not None and cfg.table_refs.before_table_ref is None
        row, = pq.read_table(pa.BufferReader(store.locate(cfg.row_locator_ref))).to_pylist()
        assert row["before_row_index"] is None and row["current_row_index"] == 0
        assert json.loads(row["before_filter_context_json"]) == {"gid": 7}
        assert row["current_filter_context_json"] is None
    else:
        assert tab["facts"]["change_kind"] == "UNCHANGED"
    if schema_added:
        from gateway_backend.application.comparison_audit import ComparisonStructureAudit
        assert result.structure_audit_ref is not None
        audit = ComparisonStructureAudit.model_validate_json(store.locate(result.structure_audit_ref))
        hidden, = audit.tables
        assert hidden.table_name == "device_cfg"
        assert hidden.equality_evidence == "NATIVE_SHARED_VALUES"
        raw = hidden.raw_fact
        assert raw.row_count_before == raw.row_count_current == 1
        assert raw.row_added_count == raw.row_deleted_count == raw.row_modified_count == 0
        assert raw.suppressed_added_count == raw.suppressed_deleted_count == 0
        assert raw.schema_changes.current_only_columns == ("extra",)
        assert raw.schema_changes.effective_compare_key_before == raw.schema_changes.effective_compare_key_current == ("id",)
        assert tab["facts"]["table_scope"] is None
        assert cfg.change_kind.value == "UNCHANGED" and cfg.risk_refs.risk_level is None
        assert not tab["empty"]
    closure = surface_artifact_closure(surface, result.pair_id, result.records_closure,
        before=before, current=current, store=store, repository_id="replacement-fixture")
    bundle = assemble_bundle(BundleAssemblyInput(bundle_contract_version=BUNDLE_CONTRACT_VERSION,
        bundle_profile=BundleProfile.SINGLE_PAIR,
        inputs=(BundleInput(0,"before","Before"), BundleInput(1,"current","Current")),
        pairs=(BundlePairInput(result.pair_id,0,1,result.surface_result,closure),)), source_store=store)
    assert bundle.status is BundleAssemblyStatus.READY and bundle.bundle is not None
    validate_bundle(bundle.bundle, store)
    closure_document = json.loads(store.locate(bundle.bundle.artifact_closure_ref))
    kinds = {entry["kind"] for entry in closure_document["closure_entries"]}
    assert "PROJECTION" in kinds
    if changed_cfg:
        assert "ROW_LOCATOR" in kinds


@pytest.mark.parametrize("missing_side", ("BEFORE", "CURRENT"))
def test_physical_filter_column_absence_does_not_become_rule_exclusion(missing_side: str) -> None:
    device_sql = ("CREATE TABLE device(gid BIGINT PRIMARY KEY,dev_addr INT,description TEXT);"
        "INSERT INTO device VALUES (7,49,'device');")
    absent = device_sql + "CREATE TABLE device_cfg(id BIGINT PRIMARY KEY,note TEXT); INSERT INTO device_cfg VALUES(1,'old');"
    present = device_sql + "CREATE TABLE device_cfg(id BIGINT PRIMARY KEY,gid BIGINT,note TEXT); INSERT INTO device_cfg VALUES(1,7,'new');"
    before_sql, current_sql = (absent, present) if missing_side == "BEFORE" else (present, absent)
    before = complete_canonical_bound(canonical_bound(before_sql))
    current = complete_canonical_bound(canonical_bound(current_sql))
    store = InMemoryArtifactStore()
    result = run_preview_pair_pipeline(pair_id="initial_to_modified", before=before, current=current,
        store=store, control=ExecutionControl(), on_cancel=lambda: pytest.fail("unexpected cancellation"),
        rule_set=comparison_ruleset_for(standard_rule_record("device"), standard_rule_record("device_cfg")),
        assess_identity=False, repository_id="replacement-fixture")
    surface = result.surface_result.surface
    assert surface is not None
    projection, = surface.projections
    navigation = validate_navigation(json.loads(store.locate(projection.projection_ref)), replacement=False)
    tabs = [tab for item in navigation["groups"][1]["items"] for tab in item["tabs"] if tab["table_id"] == "device_cfg"]
    assert len(tabs) == 1 and tabs[0]["row_filter"] is not None
    assert tabs[0]["facts"][missing_side.lower() + "_row_count"] is None
    assert tabs[0]["facts"]["basis"] == "TABLE_FALLBACK"
    assert projection.diagnostics_ref is not None
    diagnostics = json.loads(store.locate(projection.diagnostics_ref))["diagnostics"]
    assert not any(d["code"] == "DEVICE_FILTER_VALUE_UNSUPPORTED" for d in diagnostics)
    assert any(d["code"] == "DEVICE_TAB_COUNT_UNKNOWN" and d["side"] == missing_side for d in diagnostics)
    assert any(d["code"] == "DEVICE_TAB_FACTS_UNAVAILABLE" and d["params"]["reason"] == "RECORDS_UNAVAILABLE" for d in diagnostics)


@pytest.mark.parametrize("source_key_transition", (False, True))
def test_keyless_added_identity_column_uses_one_whole_table_under_final_reordering(source_key_transition: bool) -> None:
    from dataclasses import replace
    from gateway_backend.capabilities.table_rules.contracts import CanonicalKeyPolicy
    from gateway_backend.capabilities.snapshot_materialization import export_snapshot_table_parquet
    from tests.support.table_rules import fallback_record
    from tests.test_row_location import _rewrite

    device = ("CREATE TABLE device(gid BIGINT PRIMARY KEY,dev_addr INT,description TEXT);"
        "INSERT INTO device VALUES(7,49,'device7'),(8,50,'device8');")
    def source(sql: str) -> Any:
        bound = complete_canonical_bound(canonical_bound(sql))
        return replace(bound, storage_facts=tuple(replace(fact, storage_rule_view=replace(fact.storage_rule_view,
            canonical_key_policy=CanonicalKeyPolicy.DDL_PRIMARY_KEY_OR_KEYLESS))
            if fact.storage_rule_view.canonical_table == "device_cfg" else fact for fact in bound.storage_facts))
    before_ddl = "CREATE TABLE device_cfg(id BIGINT" + (" PRIMARY KEY" if source_key_transition else "") + ",note TEXT);"
    before = source(device + before_ddl + " INSERT INTO device_cfg VALUES(1,'same');")
    current = source(device + "CREATE TABLE device_cfg(id BIGINT,gid BIGINT,note TEXT); INSERT INTO device_cfg VALUES(1,7,'same'),(1,8,'same');")
    store = InMemoryArtifactStore()
    exports = {bound.snapshot.snapshot_id: {table.descriptor.table_name: export_snapshot_table_parquet(table,
        store=store, repository_id="replacement-fixture") for table in bound.table_set.tables} for bound in (before, current)}
    original = exports[current.snapshot.snapshot_id]["device_cfg"]
    results = []
    for reverse in (False, True):
        exports[current.snapshot.snapshot_id]["device_cfg"] = _rewrite(store, original) if reverse else original
        result = run_preview_pair_pipeline(pair_id="initial_to_modified", before=before, current=current,
            store=store, control=ExecutionControl(), on_cancel=lambda: pytest.fail("cancel"),
            rule_set=comparison_ruleset_for(standard_rule_record("device"), fallback_record()),
            assess_identity=False, repository_id="replacement-fixture", table_exports=exports)
        surface = result.surface_result.surface
        assert surface is not None
        projection, = surface.projections
        document = validate_navigation(json.loads(store.locate(projection.projection_ref)), replacement=False)
        tabs = [tab for item in document["groups"][1]["items"] for tab in item["tabs"] if tab["table_id"] == "device_cfg"]
        print("KEYLESS_MISSING_GID", json.dumps({"reversed": reverse, "comparison_digest": result.comparison_digest,
            "surface_digest": result.surface_digest, "tabs": tabs}, ensure_ascii=False))
        results.append((result, document, tabs))
    for result, document, tabs in results:
        assert len(tabs) == 1 and tabs[0]["row_filter"] is None and tabs[0]["facts"] is None
        surface = result.surface_result.surface
        assert surface is not None
        projection, = surface.projections
        assert projection.diagnostics_ref is not None
        diagnostics = json.loads(store.locate(projection.diagnostics_ref))["diagnostics"]
        excluded = [d for d in diagnostics if d["code"] == "DEVICE_FILTER_VALUE_UNSUPPORTED"]
        assert len(excluded) == 1 and excluded[0]["side"] == "CURRENT"
        assert excluded[0]["params"] == {"identity_column": "gid", "reason": "IDENTITY_EXCLUDED"}
        assert not any(d["code"] in {"DEVICE_TAB_FACTS_UNAVAILABLE", "DEVICE_ROWS_UNASSIGNED"} for d in diagnostics)
        table = next(table for table in surface.tables if table.table_name == "device_cfg")
        if source_key_transition:
            # Dropping the source key also changes id nullability. The existing
            # keyless fallback publishes a table-level record without a locator.
            assert table.table_status.value == "DEGRADED"
            assert table.diagnostics.diagnostics_summary == (
                "CURRENT_ONLY_COLUMNS", "INCOMPATIBLE_SELECTED_COLUMNS",
                "KEYLESS_FALLBACK", "SOURCE_PRIMARY_KEY_CHANGED")
            assert table.row_locator_ref is None
        else:
            assert table.row_locator_ref is not None
            rows = pq.read_table(pa.BufferReader(store.locate(table.row_locator_ref))).to_pylist()
            assert all(row["before_filter_context_json"] is None and row["current_filter_context_json"] is None for row in rows)
    assert results[0][0].comparison_digest == results[1][0].comparison_digest
    assert results[0][0].surface_digest == results[1][0].surface_digest
    assert results[0][1] == results[1][1]


def _materialize_business_pair_input(sql: str, store: InMemoryArtifactStore) -> Any:
    """Exercise the upload's business/catalog and canonical gates before the pair."""
    from gateway_backend.application.preview_jobs import _comparison_storage_facts
    from gateway_backend.capabilities.comparison import BoundSnapshotInput
    from gateway_backend.capabilities.snapshot_materialization import (
        MaterializationPolicy, materialize_canonical_snapshot,
    )
    from gateway_backend.capabilities.storage_projection import project_canonical_arrow_table_set
    from gateway_backend.capabilities.table_access import NeverCancel, ParserInvocationContext
    from gateway_backend.capabilities.table_rules import migrated_table_ruleset_snapshot
    from tests.support.snapshot_materialization import materialize_business

    rules = migrated_table_ruleset_snapshot()
    raw = materialize_business(sql, "<Logic_Set />", ruleset=rules,
                               policy=MaterializationPolicy.READERS_REQUIRED)
    assert raw.status.value == "COMPLETE", raw.diagnostics
    assert raw.snapshot is not None and raw.table_set is not None
    projected = project_canonical_arrow_table_set(raw.table_set, rules, presentation=raw.presentation)
    assert projected.status.value == "COMPLETE", projected.diagnostics
    assert projected.manifest is not None
    try:
        canonical = materialize_canonical_snapshot(raw.snapshot, projected.tables,
            artifact_store=store, context=ParserInvocationContext(NeverCancel()), repository_id="replacement-fixture")
    finally:
        for table in (*raw.table_set.tables, *projected.tables):
            if table.reader is not None:
                table.reader.close()
            if table.batch_reader is not None:
                table.batch_reader.close()
    assert canonical.status.value == "COMPLETE", canonical.diagnostics
    assert canonical.snapshot is not None and canonical.summary is not None and canonical.table_set is not None
    return BoundSnapshotInput(canonical.snapshot, canonical.summary, canonical.table_set,
                              _comparison_storage_facts(projected.manifest))


APP_DIAGNOSTIC_CASES = (
    ("INT", "1", "'absent'", "APP_TABLE_NOT_FOUND", "1"),
    ("VARCHAR(16)", "'one'", "'absent'", "APP_TABLE_NOT_FOUND", "one"),
    ("INT", "1", "''", "APP_TABLE_CFG_MISSING", "1"),
    ("INT", "1", "'app_cfg'", "APP_TABLE_CFG_DUPLICATE", "1"),
    ("INT", "1", "'cfg_target'", None, "1"),
)


@pytest.mark.parametrize("replacement", [False, True])
@pytest.mark.parametrize("name_type,name_value,target,code,expected_name", APP_DIAGNOSTIC_CASES)
def test_business_materialized_nontext_app_labels_do_not_break_pair_diagnostics(
    name_type: str, name_value: str, target: str, code: str | None, expected_name: str | None, replacement: bool,
) -> None:
    from gateway_backend.capabilities.table_rules import comparison_rule_set, migrated_table_ruleset_snapshot
    sql = (f"CREATE TABLE app_cfg(app_name {name_type} PRIMARY KEY,table_cfg TEXT);"
           f"INSERT INTO app_cfg VALUES({name_value},{target});")
    if code is None:
        sql += "CREATE TABLE cfg_target(gid BIGINT PRIMARY KEY,value TEXT);INSERT INTO cfg_target VALUES(1,'x');"
    store = InMemoryArtifactStore()
    identity = "CREATE TABLE version_manager(project_id VARCHAR(32) PRIMARY KEY);"
    before = _materialize_business_pair_input(sql + identity + "INSERT INTO version_manager VALUES('left');", store)
    current = _materialize_business_pair_input(sql + identity +
        ("INSERT INTO version_manager VALUES('right');" if replacement else "INSERT INTO version_manager VALUES('left');"), store)
    result = run_preview_pair_pipeline(pair_id="initial_to_modified", before=before, current=current,
        store=store, control=ExecutionControl(), on_cancel=lambda: pytest.fail("unexpected cancellation"),
        rule_set=comparison_rule_set(migrated_table_ruleset_snapshot()),
        assess_identity=True, repository_id="replacement-fixture")
    assert result.surface_result.status is SurfaceAssemblyStatus.READY
    surface = result.surface_result.surface
    assert surface is not None
    projection, = surface.projections
    navigation = validate_navigation(json.loads(store.locate(projection.projection_ref)), replacement=replacement)
    grouped = (list(navigation["replacement_sides"].values()) if replacement else [navigation["groups"]])
    assert all(any(tab["table_id"] == "app_cfg" and tab["row_filter"] is None
                   for item in groups[3]["items"] for tab in item["tabs"]) for groups in grouped)
    if code is None:
        assert projection.diagnostics_ref is None
        assert all(next(item for item in groups[3]["items"] if item["item_key"] == "global:cfg_target")["label"] == expected_name
                   for groups in grouped)
    else:
        assert projection.diagnostics_ref is not None
        diagnostics = json.loads(store.locate(projection.diagnostics_ref))["diagnostics"]
        selected = [d for d in diagnostics if d["code"] == code]
        assert {d["side"] for d in selected} == {"BEFORE", "CURRENT"}
        assert all(d["params"]["app_name"] == expected_name for d in selected)


@pytest.mark.parametrize("replacement", [False, True])
@pytest.mark.parametrize("board,link", [
    (9007199254740991, 1), (9007199254740992, 1), (1, 9007199254740992),
])
def test_business_materialized_unclaimed_table_name_keeps_safe_channel_domain(
    board: int, link: int, replacement: bool,
) -> None:
    from gateway_backend.capabilities.table_rules import comparison_rule_set, migrated_table_ruleset_snapshot
    name = f"b{board}_n{link}_sg_cfg"
    sql = f"CREATE TABLE {name}(gid BIGINT PRIMARY KEY,value TEXT);INSERT INTO {name} VALUES(1,'x');"
    store = InMemoryArtifactStore()
    identity = "CREATE TABLE version_manager(project_id VARCHAR(32) PRIMARY KEY);"
    before = _materialize_business_pair_input(sql + identity + "INSERT INTO version_manager VALUES('left');", store)
    current = _materialize_business_pair_input(sql + identity +
        ("INSERT INTO version_manager VALUES('right');" if replacement else "INSERT INTO version_manager VALUES('left');"), store)
    result = run_preview_pair_pipeline(pair_id="initial_to_modified", before=before, current=current,
        store=store, control=ExecutionControl(), on_cancel=lambda: pytest.fail("unexpected cancellation"),
        rule_set=comparison_rule_set(migrated_table_ruleset_snapshot()),
        assess_identity=True, repository_id="replacement-fixture")
    assert result.surface_result.status is SurfaceAssemblyStatus.READY
    surface = result.surface_result.surface
    assert surface is not None
    projection, = surface.projections
    navigation = validate_navigation(json.loads(store.locate(projection.projection_ref)), replacement=replacement)
    grouped = (list(navigation["replacement_sides"].values()) if replacement else [navigation["groups"]])
    for groups in grouped:
        item = next(item for item in groups[4]["items"] if item["item_key"] == f"table:{name}")
        assert item["tabs"][0]["table_id"] == name and item["tabs"][0]["row_filter"] is None
    diagnostics = [] if projection.diagnostics_ref is None else json.loads(store.locate(projection.diagnostics_ref))["diagnostics"]
    channels = [d for d in diagnostics if d["code"] == "CHANNEL_TABLE_UNCLAIMED"]
    if board <= 9007199254740991 and link <= 9007199254740991:
        assert len(channels) == (2 if replacement else 1)
        assert all(d["params"] == {"board": board, "link_no": link} for d in channels)
        assert {d["side"] for d in channels} == ({"BEFORE", "CURRENT"} if replacement else {None})
    else:
        assert channels == []


@pytest.mark.parametrize("flow", ("preview", "history"))
@pytest.mark.parametrize("empty_baseline", (False, True))
def test_new_table_risk_distinguishes_empty_baseline_from_incremental_addition(
    flow: str, empty_baseline: bool,
) -> None:
    existing = "CREATE TABLE existing(id INT PRIMARY KEY);"
    before = complete_canonical_bound(canonical_bound("" if empty_baseline else existing))
    current = complete_canonical_bound(canonical_bound(
        "CREATE TABLE added(id INT PRIMARY KEY); INSERT INTO added VALUES(1);"
        "CREATE TABLE app_cfg(app_name TEXT,enable TEXT,table_cfg TEXT);"
        "INSERT INTO app_cfg VALUES('JMS','0:NO','jms_cfg');" + existing))
    store = InMemoryArtifactStore()
    run = run_preview_pair_pipeline if flow == "preview" else run_history_pair_pipeline
    result = run(pair_id="baseline_to_modified", before=before, current=current,
        store=store, control=ExecutionControl(), on_cancel=lambda: pytest.fail("unexpected cancellation"),
        rule_set=comparison_ruleset_for(standard_rule_record("existing"), standard_rule_record("added"), standard_rule_record("app_cfg")),
        repository_id="replacement-fixture")
    surface = result.surface_result.surface
    assert surface is not None
    added = next(t for t in surface.tables if t.table_id == "added")
    assert added.change_kind.value == "ADDED"
    assert added.risk_refs.risk_level == (None if empty_baseline else "LOW")
    if empty_baseline:
        assert all(t.risk_refs.risk_level is None for t in surface.tables)
    projection, = surface.projections
    assert projection.diagnostics_ref is None
