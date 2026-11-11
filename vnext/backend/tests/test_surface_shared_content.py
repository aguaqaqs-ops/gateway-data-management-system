"""Shared client exports preserve distinct source provenance in each Surface side."""

from __future__ import annotations

import json
from contextlib import ExitStack
from dataclasses import replace
from pathlib import Path

import pytest

from gateway_backend.artifacts import InMemoryArtifactStore
from gateway_backend.artifacts.location import ArtifactLocation, build_artifact_id
from gateway_backend.capabilities.bundle_assembly import (
    BundleArtifactBinding, BundleArtifactClosure, BundleArtifactKind, BundleAssemblyStatus,
    BundlePairInput, assemble_bundle,
)
from gateway_backend.capabilities.comparison.contracts import ComparisonTableFact, ComparisonTableStatus
from gateway_backend.capabilities.snapshot_materialization import (
    export_snapshot_table_parquet, publish_canonical_tables,
)
from gateway_backend.capabilities.snapshot_materialization.contracts import MaterializationPolicy
from gateway_backend.capabilities.storage_projection import project_canonical_arrow_table_set
from gateway_backend.capabilities.storage_projection._digest import compute_storage_rule_digest
from gateway_backend.capabilities.storage_projection.view import derive_storage_rule_view
from gateway_backend.capabilities.surface_assembly import (
    SurfaceArtifactIndexEntry, SurfaceAssemblyStatus, SurfaceTableContentBindings,
    SurfaceTableRefs, TableContentBinding, assemble_surface, compute_surface_digest,
)
from gateway_backend.capabilities.table_rules import migrated_table_ruleset_snapshot, resolve_table_rule
from tests.support.snapshot_materialization import materialize_sql
from tests.test_bundle_assembly import _request as bundle_request
from tests.test_surface_assembly import _content_binding, _digest, _facts, _ref, _request

pytestmark = pytest.mark.unit
_PROJECTED_SQL_INPUTS = (
    "CREATE TABLE net_cfg (no INT, board INT NOT NULL, link_no INT NOT NULL, PRIMARY KEY(board,link_no));"
    "INSERT INTO net_cfg VALUES (99,1,2);",
    "CREATE TABLE net_cfg (board INT NOT NULL, link_no INT NOT NULL, PRIMARY KEY(board,link_no));"
    "INSERT INTO net_cfg VALUES (1,2);",
)


@pytest.mark.parametrize("distinct_source_refs", (False, True))
def test_dropped_source_column_preserves_provenance_for_a_shared_export(distinct_source_refs: bool) -> None:
    ruleset = migrated_table_ruleset_snapshot()
    store = InMemoryArtifactStore()
    sql_inputs = _PROJECTED_SQL_INPUTS
    bindings = []
    descriptors = []
    refs = []
    with ExitStack() as resources:
        for sql in sql_inputs:
            raw = materialize_sql(sql, policy=MaterializationPolicy.READERS_REQUIRED, ruleset=ruleset)
            assert raw.table_set is not None and raw.snapshot is not None
            for table in raw.table_set.tables:
                if table.reader is not None:
                    resources.callback(table.reader.close)
                if table.batch_reader is not None:
                    resources.callback(table.batch_reader.close)
            projected = project_canonical_arrow_table_set(raw.table_set, ruleset)
            assert projected.manifest is not None and len(projected.tables) == 1
            table = publish_canonical_tables(projected.tables, snapshot_digest=raw.snapshot.snapshot_digest,
                store=store, repository_id="shared-surface-test")[0]
            if table.reader is not None:
                resources.callback(table.reader.close)
            if table.batch_reader is not None:
                resources.callback(table.batch_reader.close)
            manifest = projected.manifest.tables[0]
            record = resolve_table_rule(ruleset, "net_cfg", primary_key_columns=table.descriptor.primary_key_columns).record
            view = derive_storage_rule_view(record, raw.table_set.tables[0].descriptor)
            assert view is not None
            assert manifest.source_schema_digest is not None
            assert manifest.canonical_schema_digest is not None and manifest.content_digest is not None
            bindings.append(TableContentBinding(table.descriptor.business_schema_digest, manifest.content_digest,
                table.descriptor.row_count, manifest.source_schema_digest, manifest.canonical_schema_digest,
                compute_storage_rule_digest(view), projected.manifest.storage_projection_version))
            descriptors.append(table.descriptor)
            refs.append(export_snapshot_table_parquet(table, store=store, repository_id="shared-surface-test"))
        before, current = bindings
        assert before.source_schema_digest != current.source_schema_digest
        assert before.exported_content_identity() == current.exported_content_identity()
        assert refs[0] == refs[1]
        if distinct_source_refs:
            # Staging may contain two opaque refs with identical actual Parquet
            # bytes. Bundle content dedup rewrites both to its single shared ref.
            refs[1] = replace(refs[1], artifact_id=build_artifact_id(ArtifactLocation.EXPORT,
                "shared-surface-test", "second-staging-ref"))
            store.put(store.locate(refs[0]), refs[1])
        table_refs = SurfaceTableRefs(before_table_ref=refs[0], current_table_ref=refs[1])
        content = SurfaceTableContentBindings(before, current)
        fact = ComparisonTableFact(table_name="net_cfg", status=ComparisonTableStatus.UNCHANGED,
            before_descriptor=descriptors[0], current_descriptor=descriptors[1])
        request = replace(_request(_facts(fact)), table_artifacts=(SurfaceArtifactIndexEntry(
            "net_cfg", table_refs, table_content_bindings=content),))
        surface = assemble_surface(request)
        assert surface.status is SurfaceAssemblyStatus.READY and surface.surface is not None
        original_digest = compute_surface_digest(surface.surface)
        closure = BundleArtifactClosure(tuple(BundleArtifactBinding(ref,
            f"pairs/pair/tables/{side}/net_cfg.parquet", BundleArtifactKind.SNAPSHOT_TABLE,
            pair_id="pair", table_name="net_cfg") for side, ref in zip(("before", "current"), refs, strict=True)))
        bundle = assemble_bundle(bundle_request((BundlePairInput("pair", 0, 1, surface, closure),)), source_store=store)
        assert bundle.status is BundleAssemblyStatus.READY and bundle.bundle is not None
        exported = json.loads(store.locate(bundle.bundle.pairs[0].surface_ref))
        table_doc = exported["tables"][0]
        assert table_doc["table_refs"]["before_table_ref"] == table_doc["table_refs"]["current_table_ref"]
        assert table_doc["table_content_bindings"] == content.to_document()
        assert exported["surface_digest"] == original_digest.value
        entries = json.loads(store.locate(bundle.bundle.artifact_closure_ref))["closure_entries"]
        snapshots = [entry for entry in entries if entry["kind"] == "SNAPSHOT_TABLE"]
        assert len(snapshots) == 1 and snapshots[0]["shared"] is True
        assert {entry["side"] for entry in snapshots[0]["table_bindings"]} == {"before", "current"}


@pytest.mark.parametrize("field", ("business_schema_digest", "raw_content_digest", "row_count", "canonical_schema_digest"))
def test_shared_export_rejects_different_canonical_payload(field: str) -> None:
    first = _content_binding("same")
    second = replace(first,
        business_schema_digest=_digest("different") if field == "business_schema_digest" else first.business_schema_digest,
        raw_content_digest=_digest("different") if field == "raw_content_digest" else first.raw_content_digest,
        row_count=4 if field == "row_count" else first.row_count,
        canonical_schema_digest=_digest("different") if field == "canonical_schema_digest" else first.canonical_schema_digest)
    ref = _ref("shared-table")
    with pytest.raises(ValueError, match="incompatible"):
        SurfaceArtifactIndexEntry("net_cfg", SurfaceTableRefs(ref, ref),
            table_content_bindings=SurfaceTableContentBindings(first, second))


def test_shared_export_retains_each_sides_derivation_provenance() -> None:
    first = _content_binding("same")
    second = replace(first, source_schema_digest=_digest("other-source"),
        storage_rule_digest=_digest("other-rule"), storage_projection_version="another-projection")
    ref = _ref("shared-table")
    content = SurfaceTableContentBindings(first, second)
    SurfaceArtifactIndexEntry("net_cfg", SurfaceTableRefs(ref, ref), table_content_bindings=content)
    assert content.to_document()["before"] == first.to_document()
    assert content.to_document()["current"] == second.to_document()


def test_history_preserves_distinct_frozen_source_schemas_for_shared_rows(tmp_path: Path) -> None:
    from gateway_backend.application.history.compare_jobs import (
        HISTORY_COMPARE_STEP_ASSEMBLE, history_compare_step_id, history_compare_assemble_state_from_checkpoint,
    )
    from gateway_backend.application.checkpoints import load_checkpoint_envelope
    from gateway_backend.operations import OperationStatus
    from gateway_backend.infrastructure.control_db.database import ControlDbUnitOfWork
    from tests.support.canonical_metadata import CatalogCommitCanonicalMetadataPort, metadata_for_catalog
    from tests.support.history_compare_job_harness import (
        build_history_compare_harness, run_full_history_compare_job, REPOSITORY_ID,
    )
    from tests.support.http_workspace_harness import BASELINE_HEAD
    from gateway_backend.capabilities.snapshot_materialization.contracts import RepositoryColumn
    from tests.support.repository_ref_materialization import (
        FakeRepositoryTableAccessProvider, catalog_table, make_catalog,
    )
    ruleset = migrated_table_ruleset_snapshot()
    sql_inputs = _PROJECTED_SQL_INPUTS
    commits = (BASELINE_HEAD.business_baseline_commit_id, "commit-without-source-no")
    providers = {}
    metadata = {}
    source_digests = []
    with ExitStack() as resources:
        for sql, commit in zip(sql_inputs, commits, strict=True):
            raw = materialize_sql(sql, policy=MaterializationPolicy.READERS_REQUIRED, ruleset=ruleset)
            assert raw.table_set is not None
            projected = project_canonical_arrow_table_set(raw.table_set, ruleset)
            assert projected.manifest is not None
            for table in (*raw.table_set.tables, *projected.tables):
                if table.reader is not None:
                    resources.callback(table.reader.close)
                if table.batch_reader is not None:
                    resources.callback(table.batch_reader.close)
            table = projected.tables[0]
            catalog = make_catalog((catalog_table("net_cfg", tuple(RepositoryColumn(
                name=column.name, ordinal=index, scalar_type=column.scalar_type, nullable=column.nullable)
                for index, column in enumerate(table.descriptor.columns)),
                primary_key=table.descriptor.primary_key_columns, row_count=1),),
                repository_id=REPOSITORY_ID, ref=commit, commit=commit)
            rows = {"net_cfg": ((1, 2),)}
            providers[commit] = FakeRepositoryTableAccessProvider(catalog=catalog, rows=rows, current_commit=commit)
            metadata[REPOSITORY_ID, commit] = metadata_for_catalog(catalog, rows_by_table=rows,
                manifest_override=projected.manifest)
            source_digests.append(projected.manifest.tables[0].source_schema_digest)
        assert source_digests[0] != source_digests[1]
        harness = build_history_compare_harness(tmp_path, custom_providers=providers,
            node_specs=((BASELINE_HEAD.business_baseline_node_id, commits[0]), ("bn-without-no", commits[1])),
            commit_metadata_port=CatalogCommitCanonicalMetadataPort(metadata))
        run_full_history_compare_job(harness)
        with ControlDbUnitOfWork(harness.db_path, read_only=True) as uow:
            assert uow.operations.get_operation(harness.operation_id).status is OperationStatus.SUCCEEDED
            step = uow.operations.get_step(history_compare_step_id(harness.operation_id, HISTORY_COMPARE_STEP_ASSEMBLE))
        assert step.checkpoint_ref is not None
        envelope = load_checkpoint_envelope(harness.artifact_store, step.checkpoint_ref)
        from gateway_backend.artifacts import artifact_ref_from_dict
        from gateway_backend.capabilities.bundle_assembly import BUNDLE_MANIFEST_MEDIA_TYPE
        _state_ref, state = history_compare_assemble_state_from_checkpoint(envelope.job_state, harness.artifact_store)
        required_refs = state["required_refs"]
        assert isinstance(required_refs, list)
        bundle_ref = next(ref for item in required_refs
            if (ref := artifact_ref_from_dict(item)).media_type == BUNDLE_MANIFEST_MEDIA_TYPE)
        bundle = json.loads(harness.artifact_store.locate(bundle_ref))
        surface_ref = next(entry["artifact_ref"] for entry in bundle["closure_entries"]
            if entry["kind"] == "SURFACE")
        surface = json.loads(harness.artifact_store.locate(artifact_ref_from_dict(surface_ref)))
        projected_table = next(t for t in surface["tables"] if t["table_name"] == "net_cfg")
        assert projected_table["table_refs"]["before_table_ref"] == projected_table["table_refs"]["current_table_ref"]
        side_bindings = projected_table["table_content_bindings"]
        assert [side_bindings[side]["source_schema_digest"] for side in ("before", "current")] == [
            digest.value for digest in source_digests if digest is not None]
