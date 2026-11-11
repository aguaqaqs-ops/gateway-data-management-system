"""Published pair evidence, rather than manufactured navigation, reaches a bundle."""
from __future__ import annotations

import json
from typing import Any

import pyarrow as pa
import pyarrow.parquet as pq  # type: ignore[import-untyped]
import pytest

from gateway_shared_kernel import raw_blob_digest
from gateway_backend.application.pair_pipeline import run_preview_pair_pipeline
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
from tests.support.table_rules import comparison_ruleset_for, standard_rule_record


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
        assert tab["facts"]["table_scope"]["change"] is True
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
            print("KEYLESS_KEY_TRANSITION", table.table_status, table.diagnostics.diagnostics_summary)
            # A source key transition is an incompatible schema change, so its
            # table-level record does not publish a row locator.
            assert table.table_status.value == "SCHEMA_CHANGED"
            assert table.row_locator_ref is None
        else:
            assert table.row_locator_ref is not None
            rows = pq.read_table(pa.BufferReader(store.locate(table.row_locator_ref))).to_pylist()
            assert all(row["before_filter_context_json"] is None and row["current_filter_context_json"] is None for row in rows)
    assert results[0][0].comparison_digest == results[1][0].comparison_digest
    assert results[0][0].surface_digest == results[1][0].surface_digest
    assert results[0][1] == results[1][1]
