"""Finite existing-input B/A/store FULL component calibration, not a benchmark gate."""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import resource
import socket
import tarfile
from contextlib import ExitStack
from dataclasses import replace
from pathlib import Path
from typing import Any

import pyarrow as pa
from gateway_compute._native import _init_kernel_native, _parse_sql_native
from gateway_shared_kernel import DeclaredType, DeclaredTypeKind, DigestRef

from gateway_backend.artifacts.canonical_table_store import CanonicalTableKey
from gateway_backend.artifacts.types import ArtifactRef
from gateway_backend.artifacts.location import ArtifactLocation
from gateway_backend.infrastructure.artifact_store.layout import ArtifactStoreLayout

from gateway_backend.capabilities.snapshot_materialization._digest import compare_schema_digest
from gateway_backend.capabilities.snapshot_materialization._ruleset import compare_key_index, effective_key_columns
from gateway_backend.capabilities.snapshot_materialization.canonical_store import CanonicalTableStore, canonical_table_key
from gateway_backend.capabilities.snapshot_materialization.contracts import (
    MaterializationStage, ROW_MATERIALIZATION_PROFILE, SnapshotColumnDescriptor, SnapshotTableDescriptor,
)
from gateway_backend.capabilities.snapshot_materialization.native import catalog_from_arrow_result, filter_arrow_catalog, materialize_arrow_table
from gateway_backend.capabilities.storage_projection.native import project_arrow_table
from gateway_backend.capabilities.storage_projection.view import derive_storage_rule_view
from gateway_backend.capabilities.table_access.contracts import NeverCancel, SourceColumnDescriptor, SourceTableDescriptor, SqlLogicalType
from gateway_backend.capabilities.table_rules import resolve_table_rule
from gateway_backend.capabilities.table_rules.registry import migrated_table_ruleset_snapshot
from gateway_backend.infrastructure.artifact_store.local_store import LocalArtifactStore
from gateway_backend.infrastructure.control_db.database import ControlDbUnitOfWork, initialize_control_db

ROOT = Path("/home/dev/gateway-real-dumps")
BUSINESS = {
    "max_columns": 2048, "max_batches": 4096, "max_rows": 10_000_000,
    "max_metadata_bytes": 16 * 1024**2, "max_input_bytes": 1024**3,
    "max_live_bytes": 4 * 1024**3, "max_output_bytes": 1024**3,
    "max_diagnostic_bytes": 512 * 1024,
}
IPC = {
    "max_columns": 2048, "max_input_batches": 4096, "max_rows": 10_000_000,
    "max_descriptor_bytes": 16 * 1024**2, "max_input_bytes": 1024**3,
    "max_output_bytes": 1024**3, "max_codec_peak_bytes": 4 * 1024**3,
}


def sample_memory(label: str) -> dict[str, Any]:
    status = {}
    for line in Path("/proc/self/status").read_text().splitlines():
        key, _, value = line.partition(":")
        if key in ("VmRSS", "RssAnon", "RssFile", "VmHWM"):
            status[key] = int(value.strip().split()[0]) * 1024
    cg = Path("/sys/fs/cgroup")
    return {
        "label": label, "process": status,
        "ru_maxrss_bytes": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * 1024,
        "node_cgroup_current_bytes": int((cg / "memory.current").read_text()) if (cg / "memory.current").exists() else None,
        "node_cgroup_stat": {line.split()[0]: int(line.split()[1]) for line in (cg / "memory.stat").read_text().splitlines() if line.split()[0] in ("anon", "file", "file_mapped")} if (cg / "memory.stat").exists() else {},
    }


def read_input(dataset_id: str) -> tuple[bytes, bytes, dict[str, Any]]:
    manifest = json.loads((ROOT / "datasets.json").read_bytes())
    dataset = next(item for item in manifest["datasets"] if item["dataset_id"] == dataset_id)
    expected = dataset["files"][0]
    path = ROOT / "packages" / (dataset_id + ".tar.gz")
    if path.stat().st_size != expected["bytes"] or path.stat().st_size > 8 * 1024**2:
        raise ValueError("existing package size differs from fixed manifest")
    package = path.read_bytes()
    if hashlib.sha256(package).hexdigest() != expected["sha256"]:
        raise ValueError("existing package SHA differs from fixed manifest")
    sql = None
    xml_bytes = 0
    with tarfile.open(fileobj=io.BytesIO(package), mode="r|gz") as archive:
        seen = set()
        for member in archive:
            name = member.name.lstrip("/")
            if name in seen or name not in ("sql/dbcfg.sql", "comps/logic/logics.xml") or not member.isfile() or not 0 <= member.size <= 512 * 1024**2:
                raise ValueError("existing package has an unexpected member")
            seen.add(name)
            source = archive.extractfile(member)
            if source is None:
                raise ValueError("existing member is unavailable")
            with source:
                if name == "sql/dbcfg.sql":
                    sql = source.read(member.size + 1)
                    if len(sql) != member.size:
                        raise ValueError("SQL length differs from archive header")
                else:
                    xml_bytes = member.size
    if sql is None:
        raise ValueError("existing SQL member is missing")
    return package, sql, {"dataset": dataset_id, "package_bytes": len(package), "package_sha256": expected["sha256"], "sql_bytes": len(sql), "sql_sha256": hashlib.sha256(sql).hexdigest(), "xml_bytes": xml_bytes}


def source_descriptor(table: dict[str, Any]) -> SourceTableDescriptor:
    return SourceTableDescriptor(
        display_name=table["display_name"], canonical_name=table["canonical_name"],
        primary_key_canonical_names=tuple(table["primary_key"]), reader_ready=True,
        columns=tuple(SourceColumnDescriptor(
            display_name=c["display_name"], canonical_name=c["canonical_name"], ordinal=c["ordinal"],
            sql_type=c["sql_type"], logical_type=SqlLogicalType(c["logical_type"]), nullable=c["nullable"],
            declared_type=None if c["declared_type"] is None else DeclaredType(**{**c["declared_type"], "kind": DeclaredTypeKind(c["declared_type"]["kind"])}),
            enum_or_set_labels=None if c["labels"] is None else tuple(c["labels"]),
        ) for c in table["columns"]),
    )


def main() -> int:
    _init_kernel_native(1)
    parser = argparse.ArgumentParser()
    parser.add_argument("--pair", required=True, choices=("rd-t1-a", "rd-t3-c", "rd-t4-d"))
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--artifacts", required=True, type=Path)
    args = parser.parse_args()
    if args.artifacts.exists() or args.output.exists():
        raise ValueError("calibration output paths must be new")
    args.artifacts.mkdir(parents=True)
    db = args.artifacts / "control.sqlite"
    initialize_control_db(db)
    roots = {location.value: args.artifacts / "objects" / location.value for location in ArtifactLocation}
    for path in roots.values():
        path.mkdir(parents=True)
    local = LocalArtifactStore(ArtifactStoreLayout(**roots), staging_max_bytes=4 * 1024**3)
    store = CanonicalTableStore(local, repository_id="capacity-component", budgets=IPC)
    rules = migrated_table_ruleset_snapshot()
    compare_index = compare_key_index(rules)
    retained_inputs: list[tuple[bytes, bytes]] = []
    retained_parser: list[pa.Table] = []
    retained_canonical: list[pa.Table] = []
    retained_filter: list[pa.Table] = []
    retained_catalog = []
    refs: dict[str, tuple[ArtifactRef, SnapshotTableDescriptor]] = {}
    measurements = [sample_memory("start")]
    reports = []
    for side in ("v1", "v2"):
        package, sql, report = read_input(args.pair + "-" + side)
        retained_inputs.append((package, sql))
        parsed: dict[str, Any] = _parse_sql_native(sql, NeverCancel(), None, 1)
        if parsed.get("kind") != "result" or parsed.get("status") != "COMPLETE":
            raise RuntimeError("existing input did not parse completely")
        tables = []
        metadata_by_name = {}
        for metadata in parsed["tables"]:
            stream = metadata["arrow_stream"]
            if stream is None:
                raise RuntimeError("existing table has no READY parser stream")
            try:
                arrays = stream.read_all()
            finally:
                stream.close()
            retained_parser.append(arrays)
            metadata["arrow_stream"] = pa.RecordBatchReader.from_batches(arrays.schema, arrays.to_batches())
            metadata_by_name[metadata["canonical_name"]] = metadata
        current_parser_tables = retained_parser[-len(parsed["tables"]):]
        report["parser_tables"] = [{
            "index": index, "rows": table.num_rows, "columns": table.num_columns,
            "buffers": table.get_total_buffer_size(),
            "largest_column_buffers": max((column.get_total_buffer_size() for column in table.columns), default=0),
        } for index, table in enumerate(current_parser_tables)]
        filtered = filter_arrow_catalog(metadata_by_name, cancel_probe=NeverCancel(), budgets=BUSINESS, deadline_monotonic=None, pool_threads=1)
        if filtered["output"] is None:
            raise RuntimeError("existing catalog filtering failed")
        for item in filtered["output"]["tables"]:
            with item["arrow_stream"] as stream:
                filtered_table = stream.read_all()
                retained_filter.append(filtered_table)
            item["arrow_stream"] = pa.RecordBatchReader.from_batches(filtered_table.schema, filtered_table.to_batches())
        retained_catalog.append(catalog_from_arrow_result(filtered, budgets=BUSINESS, cancel_probe=NeverCancel(), deadline_monotonic=None))
        for index, (metadata, arrays) in enumerate(zip(parsed["tables"], retained_parser[-len(parsed["tables"]):], strict=True)):
            source = source_descriptor(metadata)
            keys = effective_key_columns(source, compare_index)
            metadata["arrow_stream"].close()
            metadata["arrow_stream"] = pa.RecordBatchReader.from_batches(arrays.schema, arrays.to_batches())
            materialized = materialize_arrow_table(metadata, effective_compare_key_columns=keys, stage=MaterializationStage.FINAL, cancel_probe=NeverCancel(), budgets=BUSINESS, deadline_monotonic=None, pool_threads=1)
            if materialized["output"] is None:
                raise RuntimeError(f"existing SQL materialization failed at table index {index}")
            descriptor = SnapshotTableDescriptor(
                table_name=source.canonical_name, display_table_name=source.display_name,
                columns=tuple(SnapshotColumnDescriptor(c.canonical_name, c.display_name, c.nullable, c.sql_type) for c in source.columns),
                primary_key_columns=source.primary_key_canonical_names, compare_key_columns=keys,
                row_count=arrays.num_rows, materialization_stage=MaterializationStage.FINAL,
                compare_schema_digest=compare_schema_digest(source.canonical_name, tuple(c.canonical_name for c in source.columns), keys),
                table_ruleset_version=rules.table_ruleset_version, row_materialization_profile=ROW_MATERIALIZATION_PROFILE,
                scalar_encoding_version=1, raw_content_digest=DigestRef(materialized["output"]["raw_content_digest"]),
            )
            record = resolve_table_rule(rules, descriptor.table_name, primary_key_columns=descriptor.primary_key_columns).record
            view = derive_storage_rule_view(record, descriptor)
            if view is None:
                materialized["output"]["tables"][0]["arrow_stream"].close()
                continue
            try:
                projected = project_arrow_table(materialized["output"]["tables"][0], descriptor, view, canonicalized_input=False, cancel_probe=NeverCancel(), budgets=BUSINESS, deadline_monotonic=None, pool_threads=1)
            except BaseException:
                failure = {
                    "phase": "canonical-projection", "side": side, "table_index": index,
                    "rows": arrays.num_rows, "source_columns": arrays.num_columns,
                    "retained_columns": len(view.retained_columns), "canonical_key_columns": len(view.canonical_key_columns),
                    "parser_buffers": arrays.get_total_buffer_size(),
                    "column_buffer_bytes": [column.get_total_buffer_size() for column in arrays.columns],
                    "logical_types": [column["logical_type"] for column in metadata["columns"]],
                    "local_budgets": BUSINESS, "memory": sample_memory("projection-failure"),
                }
                args.output.with_suffix(".failure.json").write_text(json.dumps(failure, indent=2) + "\n")
                raise
            if projected["output"] is None:
                raise RuntimeError(f"existing canonical projection failed at table index {index}")
            output = projected["output"]["tables"][0]
            with output["arrow_stream"] as stream:
                canonical = stream.read_all()
            retained_canonical.append(canonical)
            bound = replace(descriptor, columns=tuple(SnapshotColumnDescriptor(c["canonical_name"], c["display_name"], c["nullable"], c["sql_type"]) for c in output["columns"]), primary_key_columns=tuple(output["primary_key"]), row_count=canonical.num_rows, raw_content_digest=DigestRef(projected["output"]["raw_content_digest"]))
            key = canonical_table_key(store.repository_id, bound)
            with ControlDbUnitOfWork(db, artifact_borrow=local.read_session) as uow:
                ref = uow.canonical_tables.lookup(key)
            hit = ref is not None
            if ref is None:
                def protect(key: CanonicalTableKey, ref: ArtifactRef) -> None:
                    with ControlDbUnitOfWork(db, artifact_borrow=local.read_session) as uow:
                        uow.canonical_tables.register(key, ref)
                with pa.RecordBatchReader.from_batches(canonical.schema, canonical.to_batches()) as stream:
                    ref = store.put(stream, bound, before_write=protect)
            refs[ref.artifact_id] = (ref, bound)
            tables.append({"index": index, "rows": canonical.num_rows, "columns": canonical.num_columns, "parser_buffers": arrays.get_total_buffer_size(), "canonical_buffers": canonical.get_total_buffer_size(), "ipc_bytes": ref.size_bytes, "content_hit": hit})
        report["tables"] = tables
        reports.append(report)
        measurements.append(sample_memory(side + "-complete-retained"))
    unique_mapping_bytes = sum(ref.size_bytes for ref, _ in refs.values())
    with ExitStack() as handles:
        borrowed_tables = []
        for ref, bound in refs.values():
            handle = handles.enter_context(store.open(ref, bound))
            stream = handles.enter_context(handle.borrow_stream())
            borrowed_tables.append(stream.read_all())
        measurements.append(sample_memory("both-sides-with-active-mappings"))
        del borrowed_tables
    measurements.append(sample_memory("mappings-closed-other-facts-retained"))
    result = {
        "kind": "B-A-store-FULL-components", "hostname": socket.gethostname(),
        "scope": "existing inputs only; all parser/canonical/filter arrays and both sides retained; no operation worker or production M claim",
        "local_budgets": {"business": BUSINESS, "ipc": IPC}, "inputs": reports,
        "parser_buffer_bytes": sum(t.get_total_buffer_size() for t in retained_parser),
        "canonical_buffer_bytes": sum(t.get_total_buffer_size() for t in retained_canonical),
        "filter_buffer_bytes": sum(t.get_total_buffer_size() for t in retained_filter),
        "filtered_python_fact_count": sum(len(c.devices) + len(c.points) for c in retained_catalog),
        "unique_active_mapping_bytes": unique_mapping_bytes,
        "max_atomic_staging_ipc_bytes": max((ref.size_bytes for ref, _ in refs.values()), default=0),
        "artifact_disk_bytes": sum(p.stat().st_size for p in local.artifact_root.rglob("*") if p.is_file()),
        "memory": measurements,
    }
    args.output.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps({"output": str(args.output), "output_sha256": hashlib.sha256(args.output.read_bytes()).hexdigest(), "ru_maxrss_bytes": result["memory"][-1]["ru_maxrss_bytes"]}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
