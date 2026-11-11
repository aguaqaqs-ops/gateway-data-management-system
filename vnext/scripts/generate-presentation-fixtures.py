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
from dataclasses import dataclass
from datetime import UTC, datetime
import hashlib
import importlib
import json
from pathlib import Path, PurePosixPath
import subprocess
import tempfile
from typing import Any, Iterator
from unittest.mock import patch

from gateway_compute._native import _init_kernel_native
from gateway_shared_kernel import raw_blob_digest
from gateway_shared_kernel.jcs import canonicalize_json_value
from gateway_backend.application.pair_pipeline import run_history_pair_pipeline, run_preview_pair_pipeline
from gateway_backend.application.preview_jobs import _comparison_storage_facts, surface_artifact_closure
from gateway_backend.artifacts import InMemoryArtifactStore, artifact_ref_from_dict
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
from gateway_backend.capabilities.table_presentation.metadata import PresentationMetadata
from gateway_backend.capabilities.table_rules import TABLE_RULESET_VERSION, comparison_rule_set, migrated_table_ruleset_snapshot
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


def generate_bundle(root: Path, scenario: dict[str, Any], inputs: dict[str, bytes]) -> dict[str, Any]:
    store = InMemoryArtifactStore()
    sources = [materialize(inputs[node["sql"]], inputs[node["xml"]], store) for node in scenario["nodes"]]
    pair_inputs = []
    for pair in scenario["pairs"]:
        before_index, current_index = pair["before"], pair["current"]
        before, current = sources[before_index], sources[current_index]
        common = dict(pair_id=pair["id"], before=before.bound, current=current.bound,
            store=store, control=ExecutionControl(), on_cancel=lambda: None,
            repository_id=REPOSITORY, before_presentation=before.presentation,
            current_presentation=current.presentation)
        history = scenario["flow"] == "HISTORY"
        if history:
            result = run_history_pair_pipeline(**common, rule_set=comparison_rule_set(migrated_table_ruleset_snapshot()))
        else:
            result = run_preview_pair_pipeline(**common, view_id=pair["id"])
        surface = result.surface_result.surface
        if surface is None or len([p for p in surface.projections if p.projection_kind == "BUSINESS_NAVIGATION"]) != 1:
            raise ValueError("production pair did not publish exactly one navigation")
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
    # Preserve real typed documents/Parquet for consumers; no normalization or
    # post-publication rewriting of opaque IDs, navigation or locator bytes.
    return {"scenario": scenario["id"], "output": scenario["output"],
        "flow": scenario["flow"], "operation_result": result.status.value,
        "submit_result": None, "coverage": scenario["coverage"],
        "inputs": {name: hashlib.sha256(inputs[name]).hexdigest()
            for name in sorted({node[k] for node in scenario["nodes"] for k in ("sql", "xml")})},
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
    with fixed_fixture_inputs(), tempfile.TemporaryDirectory(prefix="presentation-fixtures-") as temporary:
        scratch = ScratchSpace(Path(temporary), max_bytes=2 * 1024**3)
        for scenario in manifest["scenarios"]:
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
        "scenarios": records}
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
