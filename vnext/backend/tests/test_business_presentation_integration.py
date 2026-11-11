"""Real cache/degradation/physical-file inputs feed the public presentation path."""
from __future__ import annotations

import json
from contextlib import closing
from pathlib import Path
from typing import Any

import pyarrow as pa
import pyarrow.parquet as pq  # type: ignore[import-untyped]
import pytest

import gateway_backend.application.pair_pipeline as pipeline
from gateway_backend.artifacts import InMemoryArtifactStore, put_with_built_ref
from gateway_backend.capabilities.business_navigation import validate_navigation
from gateway_backend.capabilities.comparison import ComparisonRequest
from gateway_backend.capabilities.risk_evaluation.contracts import RiskExecutionPolicy, RiskEvaluationResult
from gateway_backend.capabilities.risk_evaluation import evaluate_risk as original_evaluate
from gateway_backend.capabilities.surface_assembly import SurfaceAssemblyStatus
from gateway_backend.operations.worker import ExecutionControl
from tests.support.comparison_cache_inputs import complete_canonical_bound
from tests.support.comparison_s3_e_live import canonical_bound
from tests.support.table_rules import comparison_ruleset_for, standard_rule_record


def _navigation(result: pipeline.PreviewPairPipelineResult, store: InMemoryArtifactStore) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    assert result.surface_result.status is SurfaceAssemblyStatus.READY
    surface = result.surface_result.surface
    assert surface is not None
    projection, = surface.projections
    document = validate_navigation(json.loads(store.locate(projection.projection_ref)), replacement=False)
    diagnostics = [] if projection.diagnostics_ref is None else json.loads(store.locate(projection.diagnostics_ref))["diagnostics"]
    return document, diagnostics


@pytest.mark.parametrize("limit", ("artifact", "table", "pair"))
def test_real_risk_degradation_replays_into_public_whole_table_facts_fallback(
    limit: str, monkeypatch: pytest.MonkeyPatch,
) -> None:
    ddl = ("CREATE TABLE device(gid BIGINT PRIMARY KEY,dev_addr INT,description TEXT);"
        "CREATE TABLE device_cfg(id BIGINT PRIMARY KEY,gid BIGINT,note TEXT);")
    registry = "INSERT INTO device VALUES (7,49,'A'),(8,50,'B');"
    before = complete_canonical_bound(canonical_bound(ddl + registry + "INSERT INTO device_cfg VALUES(1,7,'old'),(2,8,'old');"))
    current = complete_canonical_bound(canonical_bound(ddl + registry + "INSERT INTO device_cfg VALUES(1,7,'new'),(2,8,'new');"))
    rules = comparison_ruleset_for(standard_rule_record("device"), standard_rule_record("device_cfg"))
    requests = tuple(ComparisonRequest(pair_id=pair_id, before=before, current=current, rule_set=rules)
        for pair_id in ("baseline_to_initial", "initial_to_modified"))
    session = pipeline.declare_pair_comparison_session(requests)
    assert session is not None
    policy = RiskExecutionPolicy()
    def evaluate(*args: Any, **kwargs: Any) -> RiskEvaluationResult:
        return original_evaluate(*args, **kwargs, execution_policy=policy)
    monkeypatch.setattr(pipeline, "evaluate_risk", evaluate)
    cache_hits = 0
    original_lookup = session.risk_lookup
    def lookup(task_key: str, risk_key: str) -> tuple[object, ...] | None:
        nonlocal cache_hits
        found = original_lookup(task_key, risk_key)
        if found is not None:
            cache_hits += 1
        return found
    monkeypatch.setattr(session, "risk_lookup", lookup)
    store = InMemoryArtifactStore()
    with closing(session):
        warm = pipeline.run_preview_pair_pipeline(pair_id="baseline_to_initial", view_id="baseline_to_initial",
            before=before, current=current, store=store, control=ExecutionControl(), on_cancel=lambda: pytest.fail("cancel"),
            rule_set=rules, assess_identity=False, repository_id="replacement-fixture", dedup_session=session)
        warm_document, _ = _navigation(warm, store)
        warm_tabs = [tab for item in warm_document["groups"][1]["items"] for tab in item["tabs"] if tab["table_id"] == "device_cfg"]
        assert len(warm_tabs) == 2 and all(tab["facts"]["basis"] == "EXACT" for tab in warm_tabs)
        assert all(tab["facts"]["table_scope"] is None for tab in warm_tabs)
        policy = (RiskExecutionPolicy(max_annotation_artifact_bytes_per_table=1) if limit == "artifact" else
            RiskExecutionPolicy(max_annotations_per_table=1) if limit == "table" else
            RiskExecutionPolicy(max_annotations_per_pair=1))
        replay = pipeline.run_preview_pair_pipeline(pair_id="initial_to_modified", before=before, current=current,
            store=store, control=ExecutionControl(), on_cancel=lambda: pytest.fail("cancel"),
            rule_set=rules, assess_identity=False, repository_id="replacement-fixture", dedup_session=session)
        replay_document, replay_diagnostics = _navigation(replay, store)
        assert cache_hits > 0 and session.hits > 0
    cold = pipeline.run_preview_pair_pipeline(pair_id="initial_to_modified", before=before, current=current,
        store=store, control=ExecutionControl(), on_cancel=lambda: pytest.fail("cancel"),
        rule_set=rules, assess_identity=False, repository_id="replacement-fixture")
    assert _navigation(cold, store) == (replay_document, replay_diagnostics)
    tabs = [tab for item in replay_document["groups"][1]["items"] for tab in item["tabs"] if tab["table_id"] == "device_cfg"]
    assert len(tabs) == 2
    for tab in tabs:
        assert tab["facts"]["basis"] == "TABLE_FALLBACK"
        assert tab["facts"]["change_kind"] is None and tab["facts"]["risk_level"] is None
        assert tab["facts"]["before_row_count"] == tab["facts"]["current_row_count"] == 1
        expected_scope = None if limit == "artifact" else {"change": False, "risk_level": "UNKNOWN"}
        assert tab["facts"]["table_scope"] == expected_scope
    unavailable = [d for d in replay_diagnostics if d["code"] == "DEVICE_TAB_FACTS_UNAVAILABLE"]
    assert len(unavailable) == 1 and unavailable[0]["params"]["reason"] == "RISK_ATTRIBUTION_UNAVAILABLE"


def test_history_locator_follows_reordered_export_cache_file_through_shared_bundle(
    tmp_path: Path, db_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    from gateway_shared_kernel import raw_blob_digest
    from gateway_backend.artifacts.location import ArtifactLocation, build_artifact_id
    from gateway_backend.artifacts.snapshot_table_export_cache import SnapshotTableArtifactCacheKey
    from gateway_backend.capabilities.snapshot_materialization import export_snapshot_table_parquet, ArrowSnapshotTableReader
    from gateway_backend.capabilities.snapshot_materialization.artifact import row_layout_digest_of
    from gateway_backend.capabilities.snapshot_materialization import client_parquet
    from gateway_backend.application.preview_jobs import surface_artifact_closure
    from gateway_backend.capabilities.bundle_assembly import (
        BUNDLE_CONTRACT_VERSION, BundleAssemblyInput, BundleAssemblyStatus, BundleInput,
        BundlePairInput, BundleProfile, assemble_bundle, validate_bundle,
    )
    from gateway_backend.infrastructure.control_db.database import ControlDbUnitOfWork
    from gateway_backend.infrastructure.control_db.snapshot_export_cache import ControlDbSnapshotTableExportCache
    from gateway_backend.artifacts import artifact_ref_from_dict
    from tests.support.artifact_layout import open_test_store

    ddl = "CREATE TABLE marker(id BIGINT PRIMARY KEY,stage INT); CREATE TABLE t(id BIGINT PRIMARY KEY,note TEXT);"
    sources = [complete_canonical_bound(canonical_bound(ddl +
        "INSERT INTO t VALUES(1,'" + ("old" if stage == 0 else "new") + "'),(2,'same'),(3,'same');"
        f"INSERT INTO marker VALUES(1,{stage});")) for stage in range(3)]
    store = open_test_store(tmp_path / "artifacts")
    cache = ControlDbSnapshotTableExportCache(lambda: ControlDbUnitOfWork(db_path))
    for source in sources:
        assert source.table_set is not None
        for table in source.table_set.tables:
            export_snapshot_table_parquet(table, store=store, repository_id="replacement-fixture", export_cache=cache)
    assert sources[1].table_set is not None
    target = next(t for t in sources[1].table_set.tables if t.descriptor.table_name == "t")
    assert isinstance(target.reader, ArrowSnapshotTableReader)
    key = SnapshotTableArtifactCacheKey(row_layout_digest_of(target.descriptor,
        target.reader.source_descriptor().columns, target.ordered_metadata), "replacement-fixture")
    original = cache.lookup_many((key,))[key]
    exported = pq.read_table(pa.BufferReader(store.locate(original))).take(pa.array([2, 1, 0], type=pa.int64()))
    sink = pa.BufferOutputStream()
    pq.write_table(exported, sink, row_group_size=1)
    raw = sink.getvalue().to_pybytes()
    reordered = put_with_built_ref(store, raw, artifact_id=build_artifact_id(
        ArtifactLocation.EXPORT, "test-reordered-cache", raw_blob_digest(raw).value), media_type=original.media_type)
    cache.store_many(((key, reordered),))
    def forbid_writer(*args: Any, **kwargs: Any) -> Any:
        pytest.fail("all exact export identities were prefilled; required cache hit must not rewrite")
    monkeypatch.setattr(client_parquet, "_export_batches", forbid_writer)
    rules = comparison_ruleset_for(standard_rule_record("t"), standard_rule_record("marker"))
    pairs = []
    for index, pair_id in enumerate(("left_to_middle", "middle_to_right")):
        result = pipeline.run_history_pair_pipeline(pair_id=pair_id, before=sources[index], current=sources[index + 1],
            store=store, control=ExecutionControl(), on_cancel=lambda: pytest.fail("cancel"),
            rule_set=rules, repository_id="replacement-fixture", export_cache=cache)
        surface = result.surface_result.surface
        assert surface is not None
        surface_table = next(t for t in surface.tables if t.table_name == "t")
        assert surface_table.table_refs.current_table_ref == reordered
        if index == 0:
            assert surface_table.row_locator_ref is not None
            row, = pq.read_table(pa.BufferReader(store.locate(surface_table.row_locator_ref))).to_pylist()
            assert row["before_row_index"] == 0 and row["current_row_index"] == 2
        else:
            assert surface_table.row_locator_ref is None
            assert surface_table.table_refs.before_table_ref == reordered
        closure = surface_artifact_closure(surface, pair_id, result.records_closure,
            before=sources[index], current=sources[index + 1], include_all_tables=True,
            store=store, repository_id="replacement-fixture", export_cache=cache)
        pairs.append(BundlePairInput(pair_id, index, index + 1, result.surface_result, closure))
    assembled = assemble_bundle(BundleAssemblyInput(bundle_contract_version=BUNDLE_CONTRACT_VERSION,
        bundle_profile=BundleProfile.MULTI_PAIR, inputs=tuple(BundleInput(i, f"node{i}", f"Node {i}") for i in range(3)),
        pairs=tuple(pairs)), source_store=store)
    assert assembled.status is BundleAssemblyStatus.READY and assembled.bundle is not None
    validate_bundle(assembled.bundle, store)
    manifest = json.loads(store.locate(assembled.bundle.manifest_ref))
    table_entries = [entry for entry in manifest["closure_entries"] if entry["kind"] == "SNAPSHOT_TABLE"
        and any(binding["table_name"] == "t" and binding["pair_id"] == "left_to_middle" and binding["side"] == "current"
                for binding in entry["table_bindings"])]
    assert len(table_entries) == 1
    shared = table_entries[0]
    assert shared["shared"] and len(shared["table_bindings"]) == 3
    assert store.locate(artifact_ref_from_dict(shared["artifact_ref"])) == raw
    locator_entry, = [e for e in manifest["closure_entries"] if e["kind"] == "ROW_LOCATOR" and e["pair_id"] == "left_to_middle"
        and e["logical_path"].endswith("/t.parquet")]
    locator, = pq.read_table(pa.BufferReader(store.locate(artifact_ref_from_dict(locator_entry["artifact_ref"])))).to_pylist()
    assert locator["current_row_index"] == 2


@pytest.mark.parametrize("error_kind", ("value", "io", "arrow", "uncoded-standard"))
def test_actual_exception_becomes_stable_code_in_downloadable_records(
    error_kind: str, monkeypatch: pytest.MonkeyPatch,
) -> None:
    from gateway_backend.capabilities.comparison import native
    from gateway_backend.capabilities.comparison.errors import StandardComparisonError
    from gateway_backend.application.preview_jobs import surface_artifact_closure
    from gateway_backend.capabilities.bundle_assembly import (
        BUNDLE_CONTRACT_VERSION, BundleAssemblyInput, BundleAssemblyStatus, BundleInput,
        BundlePairInput, BundleProfile, assemble_bundle, validate_bundle,
    )
    from gateway_backend.artifacts import artifact_ref_from_dict

    ddl = "CREATE TABLE t(id BIGINT PRIMARY KEY,note TEXT);"
    before = complete_canonical_bound(canonical_bound(ddl + "INSERT INTO t VALUES(1,'old');"))
    current = complete_canonical_bound(canonical_bound(ddl + "INSERT INTO t VALUES(1,'new');"))
    errors = {"value": ValueError, "io": OSError, "arrow": pa.ArrowInvalid, "uncoded-standard": StandardComparisonError}
    def fail_native(*args: Any, **kwargs: Any) -> Any:
        raise errors[error_kind]("private detail that must never enter a public artifact")
    monkeypatch.setattr(native, "compare_records_batches", fail_native)
    store = InMemoryArtifactStore()
    result = pipeline.run_preview_pair_pipeline(pair_id="initial_to_modified", before=before, current=current,
        store=store, control=ExecutionControl(), on_cancel=lambda: pytest.fail("cancel"),
        rule_set=comparison_ruleset_for(standard_rule_record("t")), assess_identity=False,
        repository_id="replacement-fixture")
    surface = result.surface_result.surface
    assert surface is not None
    table, = surface.tables
    assert table.diagnostics.diagnostics_summary == ("COMPARISON_INTERNAL_ERROR",)
    assert table.row_locator_ref is None
    closure = surface_artifact_closure(surface, result.pair_id, result.records_closure,
        before=before, current=current, store=store, repository_id="replacement-fixture")
    assembled = assemble_bundle(BundleAssemblyInput(bundle_contract_version=BUNDLE_CONTRACT_VERSION,
        bundle_profile=BundleProfile.SINGLE_PAIR, inputs=(BundleInput(0,"before","Before"), BundleInput(1,"current","Current")),
        pairs=(BundlePairInput(result.pair_id,0,1,result.surface_result,closure),)), source_store=store)
    assert assembled.status is BundleAssemblyStatus.READY and assembled.bundle is not None
    validate_bundle(assembled.bundle, store)
    manifest = json.loads(store.locate(assembled.bundle.manifest_ref))
    entries = [entry for entry in manifest["closure_entries"] if entry["kind"] == "RECORDS"]
    assert len(entries) == 1
    record, = pq.read_table(pa.BufferReader(store.locate(artifact_ref_from_dict(entries[0]["artifact_ref"])))).to_pylist()
    assert record["record_kind"] == "TABLE_DEGRADED"
    assert record["diagnostics"] == ["COMPARISON_INTERNAL_ERROR"]
    assert "private detail" not in json.dumps(record)
