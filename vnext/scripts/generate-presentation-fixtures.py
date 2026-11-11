#!/usr/bin/env python3
"""Generate FE presentation bundles using the current backend production owners.

Run in a clean committed checkout on a dedicated offline test node. No frontend
module, navigation payload, comparison oracle, or fixture-only wire flag is used.
The only substituted inputs are opaque allocation and wall-clock time. They are
scoped to this standalone process and never used by a fresh production journey.
"""
from __future__ import annotations

import argparse
from contextlib import ExitStack, contextmanager
from dataclasses import dataclass, replace
from datetime import UTC, datetime
import hashlib
import base64
import importlib
import json
from pathlib import Path, PurePosixPath
import subprocess
import tempfile
from typing import Any, Iterator
from unittest.mock import patch

import pyarrow as pa
import pyarrow.parquet as pq

from gateway_compute._native import _init_kernel_native
from gateway_shared_kernel import raw_blob_digest
from gateway_shared_kernel.jcs import canonicalize_json_value
from gateway_backend.application.pair_pipeline import run_history_pair_pipeline, run_preview_pair_pipeline
from gateway_backend.application.preview_jobs import _comparison_storage_facts, surface_artifact_closure
from gateway_backend.artifacts import InMemoryArtifactStore, artifact_ref_from_dict, put_with_built_ref
from gateway_backend.artifacts.location import ArtifactLocation, build_artifact_id
from presentation_fixture_submit import run_comment_only_submit
from gateway_backend.artifacts.scratch import scratch_scope
from gateway_backend.capabilities.bundle_assembly import (
    BUNDLE_CONTRACT_VERSION, BundleAssemblyInput, BundleInput, BundlePairInput,
    BundleProfile, BundleRefScope, assemble_bundle,
)
from gateway_backend.capabilities.bundle_assembly.transport import read_bundle_transport_metadata
from gateway_backend.capabilities.comparison import BoundSnapshotInput
from gateway_backend.capabilities.composite_signal import present_composite_logic_source
from gateway_backend.capabilities.snapshot_materialization import (
    BusinessSnapshotMaterializationRequest, MaterializationPolicy, MaterializationStage,
    SqlSnapshotMaterializationRequest, materialize_business_snapshot, materialize_canonical_snapshot,
)
from gateway_backend.capabilities.storage_projection import project_canonical_arrow_table_set
from gateway_backend.capabilities.table_access import (
    KernelExecutionContext, NeverCancel, OperationMemoryBudget, PARSER_INPUT_CONTRACT_VERSION,
    ParserInvocationContext, SqlParseRequest, SqlSourceInput, XmlParseRequest, XmlSourceInput,
    kernel_execution_scope, parse_arrow_sql, parse_xml,
)
from gateway_backend.capabilities.surface_assembly import compute_surface_digest, surface_digest_payload
from gateway_backend.capabilities.table_presentation.metadata import PresentationMetadata
from gateway_backend.capabilities.table_rules import TABLE_RULESET_VERSION, comparison_rule_set, migrated_table_ruleset_snapshot
from gateway_backend.capabilities.table_rules.contracts import table_ruleset_document, table_ruleset_from_document
from gateway_backend.infrastructure.artifact_store.scratch import ScratchSpace
from gateway_backend.operations.worker import ExecutionControl

REPOSITORY = "presentation-fixture-repository"
FROZEN_TIME = "2026-11-11T00:00:00Z"
ALLOCATOR_MODULES = (
    "snapshot_materialization.materialize", "snapshot_materialization.compose",
    "snapshot_materialization.artifact", "storage_projection.publish",
)


class FixtureClock(datetime):
    @classmethod
    def now(cls, tz: Any = None) -> datetime:
        value = datetime(2026, 11, 11, tzinfo=UTC)
        return value if tz is None else value.astimezone(tz)


@contextmanager
def fixed_fixture_inputs() -> Iterator[None]:
    counter = 0

    def token_hex(size: int = 32) -> str:
        nonlocal counter
        counter += 1
        return hashlib.shake_256(f"be-b-presentation-fixture-v1:{counter}".encode()).hexdigest(size)

    with ExitStack() as stack:
        # All owners import the standard secrets module. Patch its allocation
        # once, and each owner's locally imported datetime separately.
        stack.enter_context(patch("secrets.token_hex", token_hex))
        for name in ALLOCATOR_MODULES:
            module = importlib.import_module("gateway_backend.capabilities." + name)
            if hasattr(module, "datetime"):
                stack.enter_context(patch.object(module, "datetime", FixtureClock))
        yield


@dataclass(frozen=True)
class MaterializedInput:
    bound: BoundSnapshotInput
    presentation: PresentationMetadata


def materialize(sql: bytes, xml: bytes, store: InMemoryArtifactStore) -> MaterializedInput:
    invocation = ParserInvocationContext(NeverCancel())
    sql_digest, xml_digest = raw_blob_digest(sql), raw_blob_digest(xml)
    parsed = parse_arrow_sql(SqlParseRequest(
        source=SqlSourceInput(sql_digest, sql_digest, PARSER_INPUT_CONTRACT_VERSION, "utf-8", len(sql)),
        sql_utf8=sql, context=invocation,
    ))
    xml_parsed = parse_xml(XmlParseRequest(
        source=XmlSourceInput(xml_digest, xml_digest, PARSER_INPUT_CONTRACT_VERSION, "utf-8", len(xml)),
        xml_utf8=xml, context=invocation,
    ))
    rules = migrated_table_ruleset_snapshot()
    raw = materialize_business_snapshot(BusinessSnapshotMaterializationRequest(
        sql=SqlSnapshotMaterializationRequest(parsed, sql_digest, rules, TABLE_RULESET_VERSION,
            MaterializationStage.FINAL, MaterializationPolicy.READERS_REQUIRED, invocation),
        logic=present_composite_logic_source(xml), xml=xml_parsed,
    ))
    if raw.snapshot is None or raw.table_set is None or raw.status.value != "COMPLETE":
        raise ValueError(f"business materialization failed: {raw.diagnostics!r}")
    projected = project_canonical_arrow_table_set(raw.table_set, rules, presentation=raw.presentation)
    if projected.manifest is None or projected.status.value != "COMPLETE":
        raise ValueError(f"canonical projection failed: {projected.diagnostics!r}")
    try:
        result = materialize_canonical_snapshot(raw.snapshot, projected.tables,
            artifact_store=store, context=invocation, repository_id=REPOSITORY)
    finally:
        for table in (*raw.table_set.tables, *projected.tables):
            if table.reader is not None:
                table.reader.close()
            if table.batch_reader is not None:
                table.batch_reader.close()
    if result.snapshot is None or result.summary is None or result.table_set is None or result.status.value != "COMPLETE":
        raise ValueError(f"canonical publication failed: {result.diagnostics!r}")
    return MaterializedInput(BoundSnapshotInput(result.snapshot, result.summary, result.table_set,
        _comparison_storage_facts(projected.manifest)), projected.manifest.presentation)


def write_member(root: Path, name: str, data: bytes) -> None:
    path = PurePosixPath(name)
    if path.is_absolute() or not path.parts or any(p in {"", ".", ".."} for p in path.parts):
        raise ValueError(f"invalid output member: {name}")
    destination = root.joinpath(*path.parts)
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists() and destination.read_bytes() != data:
        raise ValueError(f"output member collision: {name}")
    destination.write_bytes(data)


def validate_scenario_assertions(surface: Any, store: InMemoryArtifactStore, expected: dict[str, Any]) -> None:
    projection = next(p for p in surface.projections if p.projection_kind == "BUSINESS_NAVIGATION")
    navigation = json.loads(store.locate(projection.projection_ref))
    diagnostics = [] if projection.diagnostics_ref is None else json.loads(store.locate(projection.diagnostics_ref))["diagnostics"]
    codes = {d["code"] for d in diagnostics}
    if not set(expected.get("required_codes", [])).issubset(codes) or set(expected.get("forbidden_codes", [])) & codes:
        raise AssertionError("scenario navigation diagnostic codes disagree")
    for wanted in expected.get("required_diagnostics", []):
        if not any(d["code"] == wanted["code"] and d["side"] == wanted["side"]
            and d["target"]["table_id"] == wanted["table_id"] and d["params"].get("reason") == wanted["reason"] for d in diagnostics):
            raise AssertionError(f"missing scenario diagnostic: {wanted}")
    tabs = [tab for group in navigation["groups"] for item in group["items"] for tab in item["tabs"]]
    for kind, basis in (("fallback_tables", "TABLE_FALLBACK"), ("exact_tables", "EXACT")):
        for table in expected.get(kind, []):
            facts = [tab["facts"] for tab in tabs if tab["table_id"] == table and tab["row_filter"] is not None]
            if not facts or any(fact is None or fact["basis"] != basis for fact in facts):
                raise AssertionError(f"scenario {table} did not publish {basis} facts")
    tables = {t.table_id: t for t in surface.tables}
    for name in expected.get("before_alias_tables", []):
        refs = tables[name].table_refs
        if refs.before_table_ref is None or refs.before_table_ref != refs.current_table_ref:
            raise AssertionError("unchanged table did not alias current into logical before")
    for name in expected.get("changed_tables", []):
        if tables[name].change_kind.value in {"UNCHANGED", "BUSINESS_EQUIVALENT"}:
            raise AssertionError("expected changed table")
    for name in expected.get("unchanged_tables", []):
        if tables[name].change_kind.value not in {"UNCHANGED", "BUSINESS_EQUIVALENT"}:
            raise AssertionError("expected unchanged table")
    for name, columns in expected.get("before_only_columns", {}).items():
        found = {c.name for c in tables[name].columns if c.present_in == "BEFORE"}
        if not set(columns).issubset(found):
            raise AssertionError("before-only surface column missing")
    for name, minimum in expected.get("locator_min_rows", {}).items():
        ref = tables[name].row_locator_ref
        if ref is None or pq.ParquetFile(pa.BufferReader(store.locate(ref))).metadata.num_rows < minimum:
            raise AssertionError("locator omitted keyless occurrences")


def generate_bundle(root: Path, scenario: dict[str, Any], inputs: dict[str, bytes]) -> dict[str, Any]:
    store = InMemoryArtifactStore()
    sources = [materialize(inputs[node["sql"]], inputs[node["xml"]], store) for node in scenario["nodes"]]
    pair_inputs = []
    golden = {kind: [] for kind in ("navigation", "navigation-diagnostics", "row-location", "surface", "bundle")}
    for pair in scenario["pairs"]:
        before_index, current_index = pair["before"], pair["current"]
        before, current = sources[before_index], sources[current_index]
        common = dict(pair_id=pair["id"], before=before.bound, current=current.bound,
            store=store, control=ExecutionControl(), on_cancel=lambda: None,
            repository_id=REPOSITORY, before_presentation=before.presentation,
            current_presentation=current.presentation)
        rules = migrated_table_ruleset_snapshot()
        exclusions = scenario.get("comparison_exclusions", {})
        if exclusions:
            document = table_ruleset_document(rules)
            for rule in document["rules"]:
                if rule["selector"]["kind"] == "EXACT" and rule["selector"]["value"] in exclusions:
                    rule["compare_excluded_columns"] = exclusions[rule["selector"]["value"]]
            rules = table_ruleset_from_document(document)
        common["rule_set"] = comparison_rule_set(rules)
        history = scenario["flow"] == "HISTORY"
        if history:
            result = run_history_pair_pipeline(**common)
        else:
            result = run_preview_pair_pipeline(**common, view_id=pair["id"])
        surface = result.surface_result.surface
        if surface is None or len([p for p in surface.projections if p.projection_kind == "BUSINESS_NAVIGATION"]) != 1:
            raise ValueError("production pair did not publish exactly one navigation")
        validate_scenario_assertions(surface, store, scenario.get("assertions", {}))
        label = {"scenario": scenario["id"], "pair_id": pair["id"]}
        for projection in surface.projections:
            if projection.projection_kind == "BUSINESS_NAVIGATION":
                golden["navigation"].append({**label, "document": json.loads(store.locate(projection.projection_ref))})
                golden["navigation-diagnostics"].append({**label, "document": None if projection.diagnostics_ref is None
                    else json.loads(store.locate(projection.diagnostics_ref))})
        physical_tables = []
        physical_changes = []
        for table in surface.tables:
            refs = table.table_refs
            rewritten = {}
            for field in ("before_table_ref", "current_table_ref", "browse_table_ref"):
                ref = getattr(refs, field)
                if ref is None:
                    continue
                array = pq.read_table(pa.BufferReader(store.locate(ref)))
                array = array.take(pa.array(list(reversed(range(array.num_rows))), type=pa.int64()))
                sink = pa.BufferOutputStream()
                pq.write_table(array, sink, row_group_size=1, compression="NONE")
                raw = sink.getvalue().to_pybytes()
                changed = replace(ref, artifact_id=build_artifact_id(ArtifactLocation.EXPORT, "fixture-physical-variant",
                    [table.table_id, field, raw_blob_digest(raw).value]), raw_sha256=raw_blob_digest(raw), size_bytes=len(raw))
                rewritten[field] = changed
                physical_changes.append({"table_id": table.table_id, "side_ref": field,
                    "original_sha256": ref.raw_sha256.value, "rewritten_sha256": changed.raw_sha256.value,
                    "row_count": array.num_rows, "rewrite": "reverse-file-row-order; row-group=1; compression=NONE"})
            locator = table.row_locator_ref
            if locator is not None:
                raw = store.locate(locator)
                file = pq.ParquetFile(pa.BufferReader(raw))
                rows = [{**row, "row_identity": row["row_identity"].hex()} for row in file.read().to_pylist()]
                golden["row-location"].append({**label, "table_id": table.table_id,
                    "raw_sha256": locator.raw_sha256.value, "schema": str(file.schema_arrow),
                    "rows": rows, "parquet_base64": base64.b64encode(raw).decode("ascii")})
                variant_rows = file.read().to_pylist()
                for row in variant_rows:
                    for side, field in (("before", "before_table_ref"), ("current", "current_table_ref")):
                        if row[side + "_row_index"] is not None and field in rewritten:
                            original = getattr(refs, field)
                            count = pq.ParquetFile(pa.BufferReader(store.locate(original))).metadata.num_rows
                            row[side + "_row_index"] = count - 1 - row[side + "_row_index"]
                sink = pa.BufferOutputStream()
                pq.write_table(pa.Table.from_pylist(variant_rows, schema=file.schema_arrow), sink,
                    row_group_size=1, compression="NONE")
                variant_raw = sink.getvalue().to_pybytes()
                locator = replace(locator, artifact_id=build_artifact_id(ArtifactLocation.EXPORT,
                    "fixture-locator-variant", [table.table_id, raw_blob_digest(variant_raw).value]),
                    raw_sha256=raw_blob_digest(variant_raw), size_bytes=len(variant_raw))
                physical_changes.append({"table_id": table.table_id, "kind": "ROW_LOCATOR",
                    "rewritten_sha256": locator.raw_sha256.value,
                    "rewrite": "indices follow reversed snapshot file order; row-group=1; compression=NONE"})
            physical_tables.append(replace(table, table_refs=replace(refs, **rewritten), row_locator_ref=locator))
        physical_digest = compute_surface_digest(replace(surface, tables=tuple(physical_tables)))
        if physical_digest != surface.surface_digest:
            raise ValueError("table/locator physical encoding affected surface semantic digest")
        golden["surface"].append({**label, "document": surface.to_document(),
            "semantic_preimage": surface_digest_payload(surface), "surface_digest": surface.surface_digest.value,
            "physical_variant_digest": physical_digest.value, "physical_variants": physical_changes,
            "locator_ref_exclusion_checked": True})
        closure = surface_artifact_closure(surface, pair["id"], result.records_closure,
            before=before.bound, current=current.bound, include_all_tables=history,
            store=store, repository_id=REPOSITORY)
        pair_inputs.append(BundlePairInput(pair["id"], before_index, current_index, result.surface_result, closure))
    result = assemble_bundle(BundleAssemblyInput(
        bundle_contract_version=BUNDLE_CONTRACT_VERSION,
        bundle_profile=BundleProfile.MULTI_PAIR if len(pair_inputs) > 1 else BundleProfile.SINGLE_PAIR,
        inputs=tuple(BundleInput(i, node["role"], node["label"], snapshot_digest=source.bound.snapshot.snapshot_digest)
            for i, (node, source) in enumerate(zip(scenario["nodes"], sources, strict=True))),
        pairs=tuple(pair_inputs), ref_scope=BundleRefScope.BUNDLE_RELATIVE,
    ), source_store=store)
    if result.bundle is None or result.manifest_ref is None or result.artifact_closure_ref is None:
        raise ValueError(f"bundle assembly failed: {result.diagnostics!r}")
    manifest_raw = store.locate(result.manifest_ref)
    transport = read_bundle_transport_metadata(manifest_raw)
    closure_raw = store.locate(result.artifact_closure_ref)
    if transport.expected_closure_bytes != closure_raw:
        raise ValueError("production transport closure mismatch")
    manifest = json.loads(manifest_raw)
    outputs: dict[str, bytes] = {"manifest.json": manifest_raw, "artifact-closure.json": closure_raw}
    for entry in manifest["closure_entries"]:
        ref = artifact_ref_from_dict(entry["artifact_ref"])
        outputs[entry["logical_path"]] = store.locate(ref)
    destination = root / scenario["output"]
    for name, data in sorted(outputs.items()):
        write_member(destination, name, data)
    golden["bundle"].append({"scenario": scenario["id"], "manifest": manifest,
        "artifact_closure": json.loads(closure_raw)})
    for kind, values in golden.items():
        write_member(root, f"golden/{kind}/{scenario['id']}.json", canonicalize_json_value(values))
    submit_result = None
    if "comment-only-preview" in scenario["coverage"]:
        sql = inputs[scenario["nodes"][-1]["sql"]]
        source_ref = put_with_built_ref(store, sql,
            artifact_id=build_artifact_id(ArtifactLocation.DURABLE, "fixture-upload", raw_blob_digest(sql).value),
            media_type="application/sql")
        submit_result = run_comment_only_submit(before=sources[0], current=sources[-1], store=store,
            manifest_ref=result.manifest_ref, closure_ref=result.artifact_closure_ref,
            surface=pair_inputs[-1].surface_result.surface, bundle_digest=manifest["bundle_digest"],
            source_ref=source_ref, sql_source_digest=raw_blob_digest(sql).value,
            repository_id=REPOSITORY, rules_digest=migrated_table_ruleset_snapshot().ruleset_digest)
    # Preserve real typed documents/Parquet for consumers; no normalization or
    # post-publication rewriting of opaque IDs, navigation or locator bytes.
    return {"scenario": scenario["id"], "output": scenario["output"],
        "flow": scenario["flow"], "operation_result": result.status.value,
        "submit_result": submit_result, "coverage": scenario["coverage"],
        "inputs": {name: hashlib.sha256(inputs[name]).hexdigest()
            for name in sorted({node[k] for node in scenario["nodes"] for k in ("sql", "xml")})},
        "assertions": scenario.get("assertions", {}), "assertions_result": "PASS",
        "comparison_exclusions": scenario.get("comparison_exclusions", {}),
        "bundle_digest": manifest["bundle_digest"],
        "logical_paths": sorted(entry["logical_path"] for entry in manifest["closure_entries"]),
        "manifest_fields": sorted(manifest),
        "members": {name: hashlib.sha256(data).hexdigest() for name, data in sorted(outputs.items())}}


def generate(input_root: Path, output_root: Path) -> None:
    if not input_root.is_absolute() or not output_root.is_absolute():
        raise ValueError("input-root and output-root must be absolute")
    repository = Path(__file__).resolve().parents[2]
    if output_root.resolve().is_relative_to(repository):
        raise ValueError("output-root must be outside the checkout")
    if subprocess.check_output(["git", "status", "--porcelain"], cwd=repository).strip():
        raise ValueError("fixture generation requires a clean committed checkout")
    commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=repository, text=True).strip()
    if output_root.exists() and (not output_root.is_dir() or any(output_root.iterdir())):
        raise ValueError("output-root must be an empty directory")
    manifest = json.loads((input_root / "manifest.json").read_bytes())
    inputs = {}
    for entry in manifest["files"]:
        path = PurePosixPath(entry["path"])
        if path.is_absolute() or any(p in {"", ".", ".."} for p in path.parts):
            raise ValueError("input manifest path must be normalized and relative")
        raw = (input_root / path).read_bytes()
        if hashlib.sha256(raw).hexdigest() != entry["sha256"]:
            raise ValueError(f"input SHA256 mismatch: {path}")
        inputs[entry["path"]] = raw
    output_root.mkdir(parents=True, exist_ok=True)
    _init_kernel_native(1)
    records = []
    rejected_sources = []
    with fixed_fixture_inputs(), tempfile.TemporaryDirectory(prefix="presentation-fixtures-") as temporary:
        scratch = ScratchSpace(Path(temporary), max_bytes=2 * 1024**3)
        for source in manifest.get("rejected_source_inputs", []):
            with kernel_execution_scope(KernelExecutionContext(OperationMemoryBudget(8 * 1024**3), NeverCancel(), 1)):
                with scratch.session(owner="operation:presentation-fixture-rejection") as session, scratch_scope(session):
                    try:
                        materialize(inputs[source["sql"]], inputs[source["xml"]], InMemoryArtifactStore())
                    except ValueError as exc:
                        message = str(exc)
                        if source["expected_code"] not in message or source["expected_table"] not in message:
                            raise
                        rejected_sources.append({**source, "actual_result": "FAILED", "actual_message": message})
                    else:
                        raise ValueError("frozen source no longer reproduces its documented projection rejection")
        for scenario in manifest["scenarios"]:
            print("scenario=" + scenario["id"], flush=True)
            with kernel_execution_scope(KernelExecutionContext(OperationMemoryBudget(8 * 1024**3), NeverCancel(), 1)):
                with scratch.session(owner="operation:presentation-fixture") as session, scratch_scope(session):
                    records.append(generate_bundle(output_root, scenario, inputs))
    reference = output_root / manifest["root_bundle_source"]
    for path in sorted(reference.rglob("*")):
        if path.is_file():
            write_member(output_root / "backend", path.relative_to(reference).as_posix(), path.read_bytes())
    for required in manifest["required_output_directories"]:
        if not (output_root / required / "manifest.json").is_file():
            raise ValueError(f"required bundle missing: {required}")
    for retired in manifest["retired_output_directories"]:
        if (output_root / retired).exists():
            raise ValueError(f"retired output generated: {retired}")
    index = {"format": "backend-presentation-fixtures/v1", "generator_commit": commit,
        "vnext_tree": subprocess.check_output(["git", "rev-parse", "HEAD:vnext"], cwd=repository, text=True).strip(),
        "input_manifest_sha256": hashlib.sha256((input_root / "manifest.json").read_bytes()).hexdigest(),
        "fixture_only_controls": {"wall_clock_utc": FROZEN_TIME,
            "opaque_allocator": "secrets.token_hex: SHAKE256(be-b-presentation-fixture-v1:<global-call-ordinal>)",
            "allocator_owners": list(ALLOCATOR_MODULES), "repository_id": REPOSITORY,
            "pair_and_view_ids": "current flow contract; no operation ID prefix",
            "kernel_threads": 1, "memory_budget_bytes": 8 * 1024**3},
        "rejected_frozen_sources": rejected_sources, "scenarios": records}
    write_member(output_root, "index.json", canonicalize_json_value(index))
    print(json.dumps({"generator_commit": commit, "scenario_count": len(records), "index_sha256":
        hashlib.sha256((output_root / "index.json").read_bytes()).hexdigest()}, sort_keys=True))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-root", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    arguments = parser.parse_args()
    generate(arguments.input_root, arguments.output_root)


if __name__ == "__main__":
    main()
