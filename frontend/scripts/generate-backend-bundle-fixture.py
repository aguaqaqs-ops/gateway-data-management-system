#!/usr/bin/env python3
"""Generate committed frontend bundle artifacts through backend production code."""

from __future__ import annotations

import argparse
import hashlib
import json
from dataclasses import replace
from pathlib import Path, PurePosixPath

from gateway_backend.application.pair_pipeline import run_preview_pair_pipeline
from gateway_backend.application.preview_jobs import surface_artifact_closure
from gateway_backend.artifacts import (
    InMemoryArtifactStore,
    artifact_ref_from_dict,
    put_with_built_ref,
)
from gateway_backend.capabilities.bundle_assembly import (
    BUNDLE_CONTRACT_VERSION,
    BundleAssemblyInput,
    BundleInput,
    BundlePairInput,
    BundleProfile,
    BundleRefScope,
    assemble_bundle,
)
from gateway_backend.capabilities.comparison import BoundSnapshotInput
from gateway_backend.capabilities.snapshot_materialization import (
    MaterializationPolicy,
    MaterializationStage,
    SqlSnapshotMaterializationRequest,
    materialize_sql_snapshot,
)
from gateway_backend.capabilities.surface_assembly import (
    compute_surface_digest,
    validate_surface,
    validate_surface_artifacts,
)
from gateway_backend.capabilities.surface_assembly.contracts import SurfaceProjectionRef
from gateway_backend.capabilities.table_access.contracts import (
    NeverCancel,
    ParserInvocationContext,
    SqlParseRequest,
    SqlSourceInput,
)
from gateway_backend.capabilities.table_access.sql import parse_sql
from gateway_backend.capabilities.table_rules import (
    TABLE_RULESET_VERSION,
    comparison_rule_set,
    migrated_table_ruleset_snapshot,
)
from gateway_backend.operations.worker import ExecutionControl
from gateway_shared_kernel import DigestRef, raw_blob_digest
from gateway_shared_kernel.jcs import canonicalize_json_value


PAIR_ID = "initial_to_modified_fixture_for_backend_digest_cross_implementation"
BEFORE_SQL = """CREATE TABLE device (
  dev_addr INT NOT NULL,
  description VARCHAR(128),
  PRIMARY KEY (dev_addr)
);
INSERT INTO device VALUES (1, '线路保护装置 A');
INSERT INTO device VALUES (2, '测控装置');
"""
CURRENT_SQL = """CREATE TABLE device (
  dev_addr INT NOT NULL,
  description VARCHAR(128),
  model VARCHAR(64),
  PRIMARY KEY (dev_addr)
);
INSERT INTO device VALUES (1, '线路保护装置 A', '保护装置');
INSERT INTO device VALUES (2, '测控装置', '测控装置');
INSERT INTO device VALUES (3, '直流屏', '电源设备');
"""


def _materialize(sql: str, store: InMemoryArtifactStore) -> BoundSnapshotInput:
    raw = sql.encode("utf-8")
    digest = raw_blob_digest(raw)
    control = ParserInvocationContext(NeverCancel())
    parsed = parse_sql(
        SqlParseRequest(
            source=SqlSourceInput(
                document_content_digest=digest,
                sql_source_digest=digest,
                parser_input_contract_version=1,
                encoding="utf-8",
                source_size_bytes=len(raw),
            ),
            sql_utf8=raw,
            context=control,
        )
    )
    ruleset = migrated_table_ruleset_snapshot()
    result = materialize_sql_snapshot(
        SqlSnapshotMaterializationRequest(
            parse_result=parsed,
            sql_source_digest=digest,
            ruleset=ruleset,
            table_ruleset_version=TABLE_RULESET_VERSION,
            materialization_stage=MaterializationStage.FINAL,
            policy=MaterializationPolicy.ARTIFACTS_REQUIRED,
            context=control,
            artifact_store=store,
        )
    )
    if result.status.value != "COMPLETE" or result.snapshot is None or result.summary is None or result.table_set is None:
        diagnostics = [item.message for item in result.diagnostics]
        raise RuntimeError(f"backend snapshot materialization failed: {diagnostics}")
    return BoundSnapshotInput(result.snapshot, result.summary, result.table_set)


def _write_member(root: Path, logical_path: str, data: bytes) -> Path:
    path = PurePosixPath(logical_path)
    if path.is_absolute() or not path.parts or any(part in {"", ".", ".."} for part in path.parts):
        raise ValueError(f"backend emitted an invalid logical path: {logical_path}")
    destination = root.joinpath(*path.parts)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(data)
    return destination


def generate(output_root: Path, navigation_path: Path) -> None:
    if output_root.exists() and any(output_root.iterdir()):
        raise ValueError(f"output directory must be empty: {output_root}")
    output_root.mkdir(parents=True, exist_ok=True)

    store = InMemoryArtifactStore()
    before = _materialize(BEFORE_SQL, store)
    current = _materialize(CURRENT_SQL, store)
    ruleset = migrated_table_ruleset_snapshot()
    pair = run_preview_pair_pipeline(
        pair_id=PAIR_ID,
        before=before,
        current=current,
        store=store,
        control=ExecutionControl(),
        on_cancel=lambda: None,
        view_id=PAIR_ID,
        rule_set=comparison_rule_set(ruleset),
        assess_identity=False,
    )

    navigation = json.loads(navigation_path.read_bytes())
    groups = navigation.get("groups") if isinstance(navigation, dict) else None
    if not isinstance(groups, list):
        raise ValueError("business navigation input must contain a groups array")
    navigation_bytes = canonicalize_json_value(navigation)
    navigation_ref = put_with_built_ref(
        store,
        navigation_bytes,
        artifact_id=f"fixture-navigation-{hashlib.sha256(navigation_bytes).hexdigest()[:32]}",
        media_type="application/json",
    )
    source_surface = pair.surface_result.surface
    if source_surface is None:
        raise RuntimeError("backend surface assembly returned no surface")
    projection = SurfaceProjectionRef(
        projection_id="business-navigation",
        projection_kind="BUSINESS_NAVIGATION",
        projection_ref=navigation_ref,
        projection_digest=navigation_ref.raw_sha256,
        projection_summary=(("group_count", str(len(groups))),),
    )
    surface = replace(
        source_surface,
        projections=tuple(sorted((*source_surface.projections, projection), key=lambda item: item.projection_id)),
        surface_digest=DigestRef("sha256:" + "00" * 32),
    )
    surface = replace(surface, surface_digest=compute_surface_digest(surface))
    validate_surface(surface)
    validate_surface_artifacts(surface, store)
    surface_result = replace(pair.surface_result, surface=surface)
    artifact_closure = surface_artifact_closure(
        surface,
        PAIR_ID,
        pair.records_closure,
        before=before,
        current=current,
        include_all_tables=True,
    )
    assembled = assemble_bundle(
        BundleAssemblyInput(
            bundle_contract_version=BUNDLE_CONTRACT_VERSION,
            bundle_profile=BundleProfile.SINGLE_PAIR,
            inputs=(
                BundleInput(0, "BEFORE", "基线组态", snapshot_digest=before.snapshot.snapshot_digest),
                BundleInput(1, "CURRENT", "上传组态", snapshot_digest=current.snapshot.snapshot_digest),
            ),
            pairs=(BundlePairInput(PAIR_ID, 0, 1, surface_result, artifact_closure),),
            ref_scope=BundleRefScope.BUNDLE_RELATIVE,
        ),
        source_store=store,
    )
    if assembled.bundle is None or assembled.manifest_ref is None or assembled.artifact_closure_ref is None:
        raise RuntimeError(f"backend bundle assembly failed: {assembled.diagnostics}")

    manifest_bytes = store.locate(assembled.manifest_ref)
    closure_bytes = store.locate(assembled.artifact_closure_ref)
    manifest = json.loads(manifest_bytes)
    closure = json.loads(closure_bytes)
    (output_root / "manifest.json").write_bytes(manifest_bytes)
    (output_root / "artifact-closure.json").write_bytes(closure_bytes)

    semantic_entries = manifest["closure"]["entries"]
    physical_entries = manifest["closure_entries"]
    if len(semantic_entries) != len(physical_entries):
        raise RuntimeError("backend manifest semantic and physical closure counts differ")
    written: list[tuple[str, bytes]] = [("manifest.json", manifest_bytes), ("artifact-closure.json", closure_bytes)]
    for semantic, physical in zip(semantic_entries, physical_entries, strict=True):
        logical_path = semantic["logical_path"]
        if physical["logical_path"] != logical_path:
            raise RuntimeError("backend manifest closure order differs")
        ref = artifact_ref_from_dict(physical["artifact_ref"])
        data = store.locate(ref)
        _write_member(output_root, logical_path, data)
        written.append((logical_path, data))

    if closure.get("bundle_digest") != manifest.get("bundle_digest"):
        raise RuntimeError("backend manifest and artifact closure bundle digests differ")
    print(f"bundle_digest={manifest['bundle_digest']}")
    print(f"closure_manifest_digest={manifest['closure_manifest_digest']}")
    print(f"bundle_manifest_digest={closure['bundle_manifest_digest']}")
    print(f"closure_product_count={len(semantic_entries)}")
    for logical_path, data in written:
        print(f"artifact_sha256={logical_path} sha256:{hashlib.sha256(data).hexdigest()}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--navigation", type=Path, required=True)
    arguments = parser.parse_args()
    generate(arguments.output_root, arguments.navigation)


if __name__ == "__main__":
    main()
