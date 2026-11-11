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


@pytest.mark.parametrize("changed_cfg", (False, True))
def test_real_pair_device_gid_change_keeps_unchanged_cfg_before_and_locator_context(changed_cfg: bool) -> None:
    ddl = ("CREATE TABLE device(gid BIGINT PRIMARY KEY,dev_addr INT,description TEXT);"
        "CREATE TABLE device_cfg(id BIGINT PRIMARY KEY,gid BIGINT,note TEXT);")
    before = complete_canonical_bound(canonical_bound(ddl +
        "INSERT INTO device VALUES (7,49,'old device'); INSERT INTO device_cfg VALUES(1,7,'old');"))
    current = complete_canonical_bound(canonical_bound(ddl +
        "INSERT INTO device VALUES (8,49,'current device'); INSERT INTO device_cfg VALUES(1,7,'" +
        ("new" if changed_cfg else "old") + "');"))
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
    closure = surface_artifact_closure(surface, result.pair_id, result.records_closure,
        before=before, current=current, store=store, repository_id="replacement-fixture")
    bundle = assemble_bundle(BundleAssemblyInput(bundle_contract_version=BUNDLE_CONTRACT_VERSION,
        bundle_profile=BundleProfile.SINGLE_PAIR,
        inputs=(BundleInput(0,"before","Before"), BundleInput(1,"current","Current")),
        pairs=(BundlePairInput(result.pair_id,0,1,result.surface_result,closure),)), source_store=store)
    assert bundle.status is BundleAssemblyStatus.READY and bundle.bundle is not None
    validate_bundle(bundle.bundle, store)
    kinds = {entry["kind"] for entry in bundle.bundle.to_document()["closure_entries"]}
    assert "PROJECTION" in kinds
    if changed_cfg:
        assert "ROW_LOCATOR" in kinds
