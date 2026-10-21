"""Measure S5/DC32 production capabilities against the real dump packages.

This is an external diagnostic runner. It stores only bounded timing, count, digest, and
throughput facts in its JSON result; input rows and SQL text never enter the result document.
The caller supplies a private artifact scratch directory and a private output file outside Git.
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import io
import json
import os
import resource
import subprocess
import tarfile
import tempfile
import time
import uuid
from collections.abc import Callable, Mapping, Sequence
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from types import ModuleType
from typing import Any, Iterator, cast

import blake3
import pyarrow as pa
import pyarrow.ipc as pa_ipc
from gateway_shared_kernel import DigestRef, raw_blob_digest

from gateway_backend.artifacts.store import InMemoryArtifactStore, put_with_built_ref
from gateway_backend.artifacts.types import ArtifactRef
from gateway_backend.application import pair_pipeline, preview_jobs
from gateway_backend.application.submission.contracts import (
    PrepareImportBuildInput,
)
from gateway_backend.application.submission.import_builder import (
    resolve_canonical_snapshot_bindings,
)
from gateway_backend.capabilities.comparison import BoundSnapshotInput
from gateway_backend.capabilities.risk_evaluation import _engine as risk_engine
from gateway_backend.capabilities.snapshot_materialization import (
    MaterializationPolicy,
    MaterializationStage,
    SnapshotMaterializationStatus,
)
from gateway_backend.capabilities.snapshot_materialization import materialize as snapshot_materialize
from gateway_backend.capabilities.snapshot_materialization import artifact as snapshot_artifact
from gateway_backend.capabilities.storage_projection import project as storage_project
from gateway_backend.capabilities.storage_projection import package as storage_package
from gateway_backend.capabilities.comparison import standard as comparison_standard
from gateway_backend.capabilities.comparison import ordered as comparison_ordered
from gateway_backend.capabilities.surface_assembly import _assembly as surface_assembly
from gateway_backend.capabilities.mutation_planning import import_replay
from gateway_backend.infrastructure.repository_write import import_publication
from gateway_backend.domain.submission.models import BuilderMutationPolicy
from gateway_backend.domain.workspace.models import SourceArtifactBinding
from gateway_backend.operations.worker import ExecutionControl
from gateway_backend.capabilities.table_rules import (
    comparison_rule_set,
    migrated_table_ruleset_snapshot,
    resolve_comparison_rule_view,
)


_BACKEND_ROOT = Path(__file__).resolve().parents[1]
_REPO_ROOT = _BACKEND_ROOT.parents[1]
_DATASET_TIERS = ("t1", "t2", "t3", "t4")


@dataclass(slots=True)
class MeasurementRecorder:
    scenario: str
    stages: list[dict[str, Any]] = field(default_factory=list)
    per_table: dict[tuple[str, str], dict[str, Any]] = field(default_factory=dict)
    outputs: dict[str, Any] = field(default_factory=dict)

    def measure(
        self,
        stage: str,
        action: Callable[..., Any],
        *args: Any,
        table_name: str | None = None,
        **kwargs: Any,
    ) -> Any:
        wall_started = time.perf_counter()
        cpu_started = time.thread_time()
        result: Any = None
        failed = False
        try:
            result = action(*args, **kwargs)
            return result
        except BaseException:
            failed = True
            raise
        finally:
            metric = {
                "stage": stage,
                "wall_seconds": round(time.perf_counter() - wall_started, 6),
                "thread_cpu_seconds": round(time.thread_time() - cpu_started, 6),
                "failed": failed,
            }
            if table_name is None:
                self.stages.append(metric)
            else:
                table_metric = self.per_table.setdefault(
                    (table_name, stage),
                    {
                        "table_name": table_name,
                        "stage": stage,
                        "wall_seconds": 0.0,
                        "thread_cpu_seconds": 0.0,
                        "invocations": 0,
                    },
                )
                table_metric["wall_seconds"] += metric["wall_seconds"]
                table_metric["thread_cpu_seconds"] += metric["thread_cpu_seconds"]
                table_metric["invocations"] += 1
                if failed:
                    table_metric["failed"] = True


class ScratchArtifactStore(InMemoryArtifactStore):
    """Keep the capability ArtifactStore contract while timing content writes."""

    def __init__(self) -> None:
        super().__init__()
        self.write_wall_seconds = 0.0
        self.write_thread_cpu_seconds = 0.0
        self.write_count = 0
        self.write_bytes = 0

    def put(self, raw_bytes: bytes, ref: ArtifactRef) -> ArtifactRef:
        wall_started = time.perf_counter()
        cpu_started = time.thread_time()
        result = super().put(raw_bytes, ref)
        self.write_wall_seconds += time.perf_counter() - wall_started
        self.write_thread_cpu_seconds += time.thread_time() - cpu_started
        self.write_count += 1
        self.write_bytes += len(raw_bytes)
        return result


@contextmanager
def _patched(
    recorder: MeasurementRecorder,
    patches: Sequence[tuple[ModuleType, str, str, Callable[[tuple[Any, ...], Mapping[str, Any]], str | None] | None]],
) -> Iterator[None]:
    originals: list[tuple[ModuleType, str, Callable[..., Any]]] = []
    for module, name, stage, table_resolver in patches:
        original = cast(Callable[..., Any], getattr(module, name))
        originals.append((module, name, original))

        def measured(
            *args: Any,
            __original: Callable[..., Any] = original,
            __stage: str = stage,
            __table_resolver: Callable[[tuple[Any, ...], Mapping[str, Any]], str | None] | None = table_resolver,
            **kwargs: Any,
        ) -> Any:
            table_name = None if __table_resolver is None else __table_resolver(args, kwargs)
            return recorder.measure(__stage, __original, *args, table_name=table_name, **kwargs)

        setattr(module, name, measured)
    try:
        yield
    finally:
        for module, name, original in reversed(originals):
            setattr(module, name, original)


def _named_arg(index: int, name: str) -> Callable[[tuple[Any, ...], Mapping[str, Any]], str | None]:
    def resolve(args: tuple[Any, ...], kwargs: Mapping[str, Any]) -> str | None:
        if name in kwargs and type(kwargs[name]) is str:
            return cast(str, kwargs[name])
        if len(args) <= index:
            return None
        value = args[index]
        if type(value) is str:
            return value
        if hasattr(value, "canonical_table"):
            return cast(str, value.canonical_table)
        if hasattr(value, "table_name"):
            return cast(str, value.table_name)
        if hasattr(value, "descriptor"):
            descriptor = value.descriptor
            return cast(str, getattr(descriptor, "table_name", "")) or None
        return None

    return resolve


def _capability_patches() -> tuple[
    tuple[ModuleType, str, str, Callable[[tuple[Any, ...], Mapping[str, Any]], str | None] | None], ...
]:
    return (
        (preview_jobs, "stage_source_package", "source_package_staging", None),
        (preview_jobs, "parse_sql", "sql_parse", None),
        (preview_jobs, "parse_xml", "xml_parse", None),
        (preview_jobs, "materialize_business_snapshot", "business_materialization", None),
        (preview_jobs, "project_canonical_table_set", "canonical_projection_and_table_digest", None),
        (preview_jobs, "materialize_projected_snapshot", "canonical_artifact_write", None),
        (preview_jobs, "publish_canonicalization_manifest", "canonical_artifact_write", None),
        (
            snapshot_materialize,
            "_materialize_table",
            "business_materialization",
            lambda args, _kwargs: cast(str, args[1].descriptor.canonical_name),
        ),
        (
            storage_project,
            "_project_table",
            "canonical_projection_and_table_digest",
            lambda args, _kwargs: cast(str, args[1].canonical_table),
        ),
        (
            snapshot_artifact,
            "publish_snapshot_table_artifact",
            "artifact_write",
            lambda args, _kwargs: cast(str, args[0].descriptor.table_name),
        ),
        (pair_pipeline, "plan_comparison", "comparison_planning", None),
        (pair_pipeline, "compare_plan", "comparison", None),
        (
            comparison_standard,
            "_compare_task_safely",
            "comparison",
            lambda args, _kwargs: cast(str, args[0].table_name),
        ),
        (
            comparison_ordered,
            "compare_ordered_task",
            "comparison",
            lambda args, _kwargs: cast(str, args[0].table_name),
        ),
        (pair_pipeline, "evaluate_risk", "risk_evaluation", None),
        (
            risk_engine,
            "_evaluate_table",
            "risk_evaluation",
            lambda args, _kwargs: cast(str, args[0].table_fact.table_name),
        ),
        (pair_pipeline, "assemble_surface", "surface_assembly", None),
        (
            surface_assembly,
            "_project_table",
            "surface_assembly",
            lambda args, _kwargs: cast(str, args[1].table_name),
        ),
    )


def _dataset_index(root: Path) -> dict[str, dict[str, Any]]:
    value = json.loads((root / "datasets.json").read_text(encoding="utf-8"))
    records = value.get("datasets") if isinstance(value, dict) else None
    if not isinstance(records, list):
        raise ValueError("datasets.json is invalid")
    result: dict[str, dict[str, Any]] = {}
    for item in records:
        if isinstance(item, dict) and type(item.get("dataset_id")) is str:
            result[cast(str, item["dataset_id"])] = cast(dict[str, Any], item)
    return result


def _dataset_path(root: Path, item: Mapping[str, Any]) -> Path:
    files = item.get("files")
    if not isinstance(files, list) or len(files) != 1 or not isinstance(files[0], Mapping):
        raise ValueError("dataset package descriptor is invalid")
    if files[0].get("path") != "package.tar.gz":
        raise ValueError("dataset package descriptor has an unexpected package path")
    package_path = (root / "packages" / f"{item['dataset_id']}.tar.gz").resolve()
    if not package_path.is_relative_to((root / "packages").resolve()):
        raise ValueError("dataset package path escapes the package root")
    return package_path


def _measure_hashes(package: bytes, sql_bytes: bytes) -> dict[str, Any]:
    payloads = {"compressed_package": package, "uncompressed_sql": sql_bytes}
    algorithms: dict[str, Callable[[bytes], bytes]] = {
        "existing_raw_blob_digest": lambda data: bytes.fromhex(
            raw_blob_digest(data).value.removeprefix("sha256:")
        ),
        "sha256": lambda data: hashlib.sha256(data).digest(),
        "blake2b_256": lambda data: hashlib.blake2b(data, digest_size=32).digest(),
        "blake3_256": lambda data: blake3.blake3(data).digest(),
    }
    output: dict[str, Any] = {}
    for payload_name, payload in payloads.items():
        for algorithm, digest in algorithms.items():
            wall_started = time.perf_counter()
            cpu_started = time.thread_time()
            result = digest(payload)
            wall_seconds = time.perf_counter() - wall_started
            cpu_seconds = time.thread_time() - cpu_started
            output[f"{payload_name}:{algorithm}"] = {
                "bytes": len(payload),
                "wall_seconds": round(wall_seconds, 6),
                "thread_cpu_seconds": round(cpu_seconds, 6),
                "mib_per_second": _rate_mib(len(payload), wall_seconds),
                "result_prefix": result.hex()[:12],
            }
    return output


def _rate_mib(size: int, seconds: float) -> float | None:
    if seconds <= 0:
        return None
    return round(size / (1024 * 1024) / seconds, 3)


def _append_table_costs(
    target: list[dict[str, Any]],
    *,
    scenario: str,
    recorder: MeasurementRecorder,
    table_facts: Mapping[str, Any],
) -> None:
    stages: tuple[str, ...]
    if "submit_prepare" in scenario:
        stages = (
            "schema_sql_rendering",
            "mutation_planning_and_replay",
            "artifact_write",
        )
        phase = "submit_prepare"
    elif "preview" in scenario or "history" in scenario:
        stages = ("comparison", "risk_evaluation", "surface_assembly", "artifact_write")
        phase = "pair_pipeline"
    else:
        stages = (
            "business_materialization",
            "canonical_projection_and_table_digest",
            "artifact_write",
        )
        phase = "materialization_and_projection"
    for table_name, raw_facts in table_facts.items():
        facts = cast(dict[str, Any], raw_facts)
        for stage in stages:
            measured = recorder.per_table.get((table_name, stage), {})
            produced_records = (
                facts.get("record_count", 0)
                if phase == "pair_pipeline"
                else facts.get("row_count", 0)
                if stage != "schema_sql_rendering"
                else 0
            )
            target.append(
                {
                    "scenario": scenario,
                    "phase": phase,
                    "table_name": table_name,
                    "stage": stage,
                    "wall_seconds": round(float(measured.get("wall_seconds", 0.0)), 6),
                    "thread_cpu_seconds": round(
                        float(measured.get("thread_cpu_seconds", 0.0)), 6
                    ),
                    "invocations": int(measured.get("invocations", 0)),
                    "measured": bool(measured),
                    "output_record_count": int(produced_records),
                    "row_count": facts.get("row_count"),
                    "column_count": facts.get("column_count"),
                    "comparison_role": facts.get("comparison_role"),
                    "ordered": facts.get("ordered"),
                    "record_count": facts.get("record_count", 0),
                    "changed": facts.get("changed"),
                }
            )


def _extract_required_sql(package: bytes) -> bytes:
    with gzip.GzipFile(fileobj=io.BytesIO(package)) as compressed:
        expanded = compressed.read()
    with tarfile.open(fileobj=io.BytesIO(expanded), mode="r:") as archive:
        matches = [member for member in archive.getmembers() if member.name == "sql/dbcfg.sql"]
        if len(matches) != 1 or not matches[0].isfile():
            raise ValueError("real dump does not contain exactly one required SQL member")
        stream = archive.extractfile(matches[0])
        if stream is None:
            raise ValueError("required SQL member cannot be read")
        return stream.read()


def _measure_existing_sql_parser(sql_bytes: bytes) -> dict[str, Any]:
    from gateway_backend.capabilities.table_access.contracts import (
        NeverCancel,
        PARSER_INPUT_CONTRACT_VERSION,
        ParserInvocationContext,
        SqlParseRequest,
        SqlSourceInput,
    )
    from gateway_backend.capabilities.table_access.sql import parse_sql

    digest = raw_blob_digest(sql_bytes)
    context = ParserInvocationContext(NeverCancel())
    request = SqlParseRequest(
        source=SqlSourceInput(
            document_content_digest=digest,
            sql_source_digest=digest,
            parser_input_contract_version=PARSER_INPUT_CONTRACT_VERSION,
            encoding="utf-8",
            source_size_bytes=len(sql_bytes),
        ),
        sql_utf8=sql_bytes,
        context=context,
    )
    wall_started = time.perf_counter()
    cpu_started = time.thread_time()
    parsed = parse_sql(request)
    wall = time.perf_counter() - wall_started
    cpu = time.thread_time() - cpu_started
    del parsed
    return {
        "input_bytes": len(sql_bytes),
        "wall_seconds": round(wall, 6),
        "thread_cpu_seconds": round(cpu, 6),
        "mib_per_second": _rate_mib(len(sql_bytes), wall),
        "parser": "gateway_backend.capabilities.table_access.sql.parse_sql",
    }


def _table_facts(bound: BoundSnapshotInput) -> dict[str, dict[str, Any]]:
    manifest_tables: dict[str, Any] = {}
    for fact in bound.storage_facts:
        manifest_tables[fact.storage_rule_view.canonical_table] = fact.storage_rule_view
    active_rules = comparison_rule_set(migrated_table_ruleset_snapshot())
    result: dict[str, dict[str, Any]] = {}
    for descriptor in bound.summary.tables:
        table_name = descriptor.table_name
        view = resolve_comparison_rule_view(
            active_rules,
            table_name,
            primary_key_columns=descriptor.primary_key_columns,
        )
        storage = manifest_tables.get(table_name)
        result[table_name] = {
            "row_count": descriptor.row_count,
            "column_count": len(descriptor.columns),
            "comparison_role": None if view is None else view.comparison_role.value,
            "ordered": bool(storage is not None and storage.ordered_policy.value != "NONE"),
            "record_count": 0,
            "changed": None,
        }
    return result


def _snapshot_package(
    *,
    dataset_id: str,
    package: bytes,
    store: ScratchArtifactStore,
    recorder: MeasurementRecorder,
) -> tuple[BoundSnapshotInput, ArtifactRef, DigestRef]:
    package_ref = put_with_built_ref(
        store,
        package,
        artifact_id=f"s5-source-{uuid.uuid4().hex}",
        media_type="application/gzip",
    )
    binding = SourceArtifactBinding(
        artifact_id=package_ref.artifact_id,
        media_type=package_ref.media_type,
        size_bytes=package_ref.size_bytes,
        raw_sha256=package_ref.raw_sha256.value,
    )
    ruleset = migrated_table_ruleset_snapshot()
    writes_before = (
        store.write_wall_seconds,
        store.write_thread_cpu_seconds,
        store.write_count,
        store.write_bytes,
    )
    with _patched(recorder, _capability_patches()):
        bound, manifest_ref, manifest_digest = preview_jobs._materialize_uploaded_side(
            binding,
            store,
            ruleset,
        )
    recorder.stages.append(
        {
            "stage": "artifact_write",
            "wall_seconds": round(store.write_wall_seconds - writes_before[0], 6),
            "thread_cpu_seconds": round(
                store.write_thread_cpu_seconds - writes_before[1], 6
            ),
            "artifact_count": store.write_count - writes_before[2],
            "bytes_written": store.write_bytes - writes_before[3],
            "failed": False,
            "measurement_scope": "ArtifactStore.put calls within this materialization",
        }
    )
    if bound.table_set is None or bound.summary.row_count_total is None:
        raise RuntimeError(f"{dataset_id}: production Preview materialization returned incomplete facts")
    recorder.outputs.update(
        {
            "dataset_id": dataset_id,
            "snapshot_digest": bound.snapshot.snapshot_digest.value,
            "canonicalization_manifest_digest": manifest_digest.value,
            "table_count": bound.summary.table_count,
            "row_count_total": bound.summary.row_count_total,
            "tables": _table_facts(bound),
            "artifact_store_write_count": store.write_count - writes_before[2],
            "artifact_store_write_bytes": store.write_bytes - writes_before[3],
            "artifact_store_write_wall_seconds": round(
                store.write_wall_seconds - writes_before[0], 6
            ),
            "artifact_store_write_thread_cpu_seconds": round(
                store.write_thread_cpu_seconds - writes_before[1], 6
            ),
        }
    )
    return bound, manifest_ref, manifest_digest


def _empty_baseline(store: ScratchArtifactStore) -> BoundSnapshotInput:
    # Reuse a real production materialization with an empty SQL document, not a hand-built
    # comparison DTO. This represents the repository's accepted empty initial commit.
    from gateway_backend.capabilities.composite_signal.contracts import empty_composite_logic_source
    from gateway_backend.capabilities.snapshot_materialization.compose import materialize_business_snapshot
    from gateway_backend.capabilities.snapshot_materialization.contracts import (
        BusinessSnapshotMaterializationRequest,
        SqlSnapshotMaterializationRequest,
    )
    from gateway_backend.capabilities.table_access.contracts import (
        NeverCancel,
        PARSER_INPUT_CONTRACT_VERSION,
        ParserInvocationContext,
        SqlParseRequest,
        SqlSourceInput,
    )
    from gateway_backend.capabilities.table_access.sql import parse_sql

    empty = b""
    digest = raw_blob_digest(empty)
    context = ParserInvocationContext(NeverCancel())
    parsed = parse_sql(
        SqlParseRequest(
            source=SqlSourceInput(
                document_content_digest=digest,
                sql_source_digest=digest,
                parser_input_contract_version=PARSER_INPUT_CONTRACT_VERSION,
                encoding="utf-8",
                source_size_bytes=0,
            ),
            sql_utf8=empty,
            context=context,
        )
    )
    ruleset = migrated_table_ruleset_snapshot()
    materialized = materialize_business_snapshot(
        BusinessSnapshotMaterializationRequest(
            sql=SqlSnapshotMaterializationRequest(
                parse_result=parsed,
                sql_source_digest=digest,
                ruleset=ruleset,
                table_ruleset_version=ruleset.table_ruleset_version,
                materialization_stage=MaterializationStage.FINAL,
                policy=MaterializationPolicy.READERS_REQUIRED,
                context=context,
                artifact_store=store,
            ),
            logic=empty_composite_logic_source(),
        )
    )
    if (
        materialized.status is not SnapshotMaterializationStatus.COMPLETE
        or materialized.snapshot is None
        or materialized.summary is None
        or materialized.table_set is None
    ):
        raise RuntimeError("empty initial baseline materialization failed")
    return BoundSnapshotInput(
        materialized.snapshot,
        materialized.summary,
        materialized.table_set,
    )


def _pair_measurement(
    *,
    recorder: MeasurementRecorder,
    store: ScratchArtifactStore,
    scenario: str,
    before: BoundSnapshotInput,
    current: BoundSnapshotInput,
    history: bool = False,
) -> dict[str, Any]:
    with _patched(recorder, _capability_patches()):
        writes_before = (
            store.write_wall_seconds,
            store.write_thread_cpu_seconds,
            store.write_count,
            store.write_bytes,
        )
        records_closure: Any
        if history:
            history_result = pair_pipeline.run_history_pair_pipeline(
                pair_id=scenario.replace("_", "-"),
                before=before,
                current=current,
                rule_set=comparison_rule_set(migrated_table_ruleset_snapshot()),
                store=store,
                control=ExecutionControl(),
                on_cancel=lambda: None,
            )
            facts = history_result.surface_result.surface
            records_closure = history_result.records_closure
            output: dict[str, Any] = {
                "record_count": history_result.record_count,
                "comparison_digest": history_result.comparison_digest,
                "risk_digest": history_result.risk_digest,
                "surface_digest": history_result.surface_digest,
            }
        else:
            preview_result = pair_pipeline.run_preview_pair_pipeline(
                pair_id=scenario.replace("_", "-"),
                before=before,
                current=current,
                store=store,
                control=ExecutionControl(),
                on_cancel=lambda: None,
            )
            facts = preview_result.surface_result.surface
            records_closure = preview_result.records_closure
            output = {
                "comparison_digest": preview_result.comparison_digest,
                "risk_digest": preview_result.risk_digest,
                "surface_digest": preview_result.surface_digest,
                "identity_status": (
                    None
                    if preview_result.identity_assessment is None
                    else preview_result.identity_assessment.status.value
                ),
            }
    recorder.stages.append(
        {
            "stage": "artifact_write",
            "wall_seconds": round(store.write_wall_seconds - writes_before[0], 6),
            "thread_cpu_seconds": round(
                store.write_thread_cpu_seconds - writes_before[1], 6
            ),
            "artifact_count": store.write_count - writes_before[2],
            "bytes_written": store.write_bytes - writes_before[3],
            "failed": False,
            "measurement_scope": "ArtifactStore.put calls within this pair pipeline",
        }
    )
    if facts is None:
        raise RuntimeError(f"{scenario}: capability pipeline did not produce a surface")
    table_details = _table_facts(current)
    surface_by_name = {item.table_name: item for item in facts.tables}
    closure = records_closure
    records_by_name: dict[str, int] = {}
    if closure is not None:
        for entry in closure.records:
            records_by_name[entry.table_name] = (
                records_by_name.get(entry.table_name, 0) + entry.record_count
            )
    for name, record in table_details.items():
        table = surface_by_name.get(name)
        if table is not None:
            record["changed"] = table.content_changed
            record["record_count"] = records_by_name.get(name, 0)
    for table_cost in recorder.per_table.values():
        facts_for_table = table_details.get(cast(str, table_cost["table_name"]))
        if facts_for_table is not None:
            table_cost.update(facts_for_table)
    output["tables"] = table_details
    return output


def _submit_measurement(
    *,
    recorder: MeasurementRecorder,
    store: ScratchArtifactStore,
    bound: BoundSnapshotInput,
    manifest_ref: ArtifactRef,
    manifest_digest: DigestRef,
    submit_id: str,
    expected_parent: str,
    removed_tables: tuple[str, ...] = (),
    table_facts: Mapping[str, Any] | None = None,
) -> tuple[dict[str, Any], bytes]:
    if bound.table_set is None:
        raise RuntimeError("submit measurement requires canonical table artifacts")
    closure_ref = preview_jobs._publish_canonical_table_set_closure(bound, store)
    operation_refs: dict[str, ArtifactRef] = {
        closure_ref.artifact_id: closure_ref,
        manifest_ref.artifact_id: manifest_ref,
    }
    for table in bound.table_set.tables:
        if table.artifact is None:
            raise RuntimeError(f"{table.descriptor.table_name}: canonical artifact missing")
        artifact = table.artifact
        operation_refs[artifact.manifest_ref.artifact_id] = artifact.manifest_ref
        for ref in artifact.manifest.row_file_refs:
            operation_refs[ref.artifact_id] = ref
    bindings, _resolved_refs = resolve_canonical_snapshot_bindings(
        operation_artifact_refs=tuple(operation_refs[key] for key in sorted(operation_refs)),
        canonical_table_set_closure_ref=closure_ref.artifact_id,
        canonical_table_set_closure_digest=closure_ref.raw_sha256.value,
        canonicalization_manifest_ref=manifest_ref.artifact_id,
        canonicalization_manifest_digest=manifest_digest.value,
        read_artifact=store.locate,
    )
    build_input = PrepareImportBuildInput(
        submit_attempt_id=submit_id,
        builder_mutation_policy=BuilderMutationPolicy.REBUILD_ALWAYS,
        canonical_table_set_closure_ref=closure_ref,
        canonical_table_set_closure_digest=closure_ref.raw_sha256.value,
        canonicalization_manifest_ref=manifest_ref,
        canonicalization_manifest_digest=manifest_digest.value,
        expected_parent_commit_id=expected_parent,
        removed_tables=removed_tables,
        source_artifact_digest=bound.snapshot.snapshot_digest.value,
        repository_base_digest="sha256:" + "00" * 32,
        snapshot_tables=bindings,
    )
    adapter = import_publication.SubmitImportPublicationAdapter()
    patches = _capability_patches() + (
        (import_replay, "plan_storage_mutation", "mutation_planning_and_replay", None),
        (import_replay, "render_change_set_replay", "mutation_planning_and_replay", None),
        (
            import_publication,
            "_keyed_rows_from_frozen_artifact",
            "mutation_planning_and_replay",
            lambda args, kwargs: cast(
                str,
                kwargs["manifest_table"].name
                if "manifest_table" in kwargs
                else args[2].name,
            ),
        ),
        (
            import_publication,
            "render_repository_import_schema_replay_sql",
            "schema_sql_rendering",
            None,
        ),
        (
            import_publication,
            "build_import_mutation_snapshots",
            "mutation_planning_and_replay",
            None,
        ),
        (import_publication, "render_import_mutation_dml", "mutation_planning_and_replay", None),
    )
    writes_before = (
        store.write_wall_seconds,
        store.write_thread_cpu_seconds,
        store.write_count,
        store.write_bytes,
    )
    with _patched(recorder, patches):
        started = time.perf_counter()
        publication = adapter.build_and_publish(build_input=build_input, store=store)
        package = adapter.read_back_package(checkpoint=publication.checkpoint, store=store)
        total_wall = time.perf_counter() - started
    recorder.stages.append(
        {
            "stage": "artifact_write",
            "wall_seconds": round(store.write_wall_seconds - writes_before[0], 6),
            "thread_cpu_seconds": round(
                store.write_thread_cpu_seconds - writes_before[1], 6
            ),
            "artifact_count": store.write_count - writes_before[2],
            "bytes_written": store.write_bytes - writes_before[3],
            "failed": False,
            "measurement_scope": "ArtifactStore.put calls within Submit prepare/publish",
        }
    )
    _manifest_bytes, replay_sql = storage_package.unpack_repository_import_entries(package)
    import_input = storage_package.validate_repository_import_package(package)
    schema_columns = sum(len(table.columns) for table in import_input.tables)
    return {
        "package_sha256": publication.checkpoint.package_raw_sha256,
        "package_bytes": len(package),
        "replay_sql_bytes": len(replay_sql),
        "schema_table_count": len(import_input.tables),
        "schema_column_count": schema_columns,
        "manifest_digest": import_input.canonicalization_manifest_digest.value,
        "tables": dict(table_facts) if table_facts is not None else _table_facts(bound),
        "build_and_readback_wall_seconds": round(total_wall, 6),
        "mutation_planning_and_replay_measured_wall_seconds": round(
            sum(
                item["wall_seconds"]
                for item in recorder.stages
                if item["stage"] == "mutation_planning_and_replay"
            ),
            6,
        ),
    }, replay_sql


def _measure_direct_dolt_import(replay_sql: bytes, scratch: Path) -> dict[str, Any]:
    repo = scratch / "direct-dolt-import"
    home = scratch / "direct-dolt-home"
    repo.mkdir(mode=0o700)
    home.mkdir(mode=0o700)
    (home / ".dolt").mkdir(mode=0o700)
    config_path = home / ".dolt" / "config_global.json"
    config_path.write_text(
        json.dumps({"versioncheck.disabled": "true", "metrics.disabled": "true"}),
        encoding="utf-8",
    )
    os.chmod(config_path, 0o600)
    environment = os.environ.copy()
    environment["HOME"] = str(home)
    sql_path = scratch / "direct-dolt-replay.sql"
    sql_descriptor = os.open(sql_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(sql_descriptor, "wb") as sql_file:
        sql_file.write(replay_sql)
        sql_file.flush()
        os.fsync(sql_file.fileno())

    def run_command(
        command: Sequence[str],
        *,
        stdin_path: Path | None = None,
    ) -> dict[str, Any]:
        child_cpu_before = resource.getrusage(resource.RUSAGE_CHILDREN)
        wall_started = time.perf_counter()
        input_context = stdin_path.open("rb") if stdin_path is not None else _NullInput()
        with input_context as input_stream:
            completed = subprocess.run(
                command,
                cwd=repo,
                env=environment,
                stdin=None if stdin_path is None else input_stream,
                check=False,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=6 * 60 * 60,
            )
        wall = time.perf_counter() - wall_started
        child_cpu_after = resource.getrusage(resource.RUSAGE_CHILDREN)
        cpu = (child_cpu_after.ru_utime + child_cpu_after.ru_stime) - (
            child_cpu_before.ru_utime + child_cpu_before.ru_stime
        )
        if completed.returncode != 0:
            raise RuntimeError(
                f"direct Dolt command failed ({Path(command[1]).name}, exit={completed.returncode})"
            )
        return {
            "wall_seconds": round(wall, 6),
            "child_cpu_seconds": round(cpu, 6),
            "exit_code": completed.returncode,
        }

    init = run_command(
        ("dolt", "init", "--name=S5 measurement", "--email=s5-measurement@example.invalid")
    )
    import_result = run_command(("dolt", "sql", "-b"), stdin_path=sql_path)
    add_result = run_command(("dolt", "add", "-A"))
    commit_result = run_command(("dolt", "commit", "-m", "S5 direct import measurement"))
    sql_path.unlink(missing_ok=True)
    return {
        "dataset_id": "rd-t4-d-v1",
        "package_replay_sql_bytes": len(replay_sql),
        "temporary_repository": True,
        "offline_dolt_home": True,
        "init": init,
        "import_sql": import_result,
        "stage_tables": add_result,
        "commit": commit_result,
    }


class _NullInput:
    def __enter__(self) -> None:
        return None

    def __exit__(self, _type: object, _value: object, _traceback: object) -> None:
        return None


def _standalone_decompression(package: bytes) -> dict[str, Any]:
    import gzip
    import io
    import tarfile

    wall_started = time.perf_counter()
    cpu_started = time.thread_time()
    expanded_bytes = 0
    with gzip.GzipFile(fileobj=io.BytesIO(package)) as stream:
        expanded = stream.read()
    with tarfile.open(fileobj=io.BytesIO(expanded), mode="r:") as archive:
        for member in archive.getmembers():
            if member.isfile():
                handle = archive.extractfile(member)
                if handle is not None:
                    expanded_bytes += len(handle.read())
    wall = time.perf_counter() - wall_started
    return {
        "compressed_bytes": len(package),
        "expanded_file_bytes": expanded_bytes,
        "wall_seconds": round(wall, 6),
        "thread_cpu_seconds": round(time.thread_time() - cpu_started, 6),
        "mib_per_second": _rate_mib(expanded_bytes, wall),
    }


def _arrow_basic_operations(row_count: int, output_dir: Path) -> dict[str, Any]:
    rows = max(1, row_count)
    table = pa.table(
        {
            "id": pa.array(range(rows), type=pa.int64()),
            "value": pa.array((index * 17 for index in range(rows)), type=pa.int64()),
        }
    )
    arrow_path = output_dir / "arrow-roundtrip.tmp"
    fd = os.open(arrow_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    os.close(fd)
    wall_started = time.perf_counter()
    cpu_started = time.thread_time()
    with pa.OSFile(str(arrow_path), "wb") as sink:
        with pa_ipc.new_file(sink, table.schema) as writer:
            writer.write_table(table)
    write_wall = time.perf_counter() - wall_started
    write_cpu = time.thread_time() - cpu_started
    file_bytes = arrow_path.stat().st_size
    wall_started = time.perf_counter()
    cpu_started = time.thread_time()
    checksum = hashlib.sha256()
    with pa.memory_map(str(arrow_path), "r") as source:
        mapped = pa_ipc.open_file(source).read_all()
        for column in mapped.columns:
            for chunk in column.chunks:
                for buffer in chunk.buffers():
                    if buffer is not None:
                        checksum.update(memoryview(buffer))
    mmap_wall = time.perf_counter() - wall_started
    mmap_cpu = time.thread_time() - cpu_started
    wall_started = time.perf_counter()
    cpu_started = time.thread_time()
    converted = [column.to_pylist() for column in mapped.columns]
    python_wall = time.perf_counter() - wall_started
    python_cpu = time.thread_time() - cpu_started
    arrow_path.unlink(missing_ok=True)
    return {
        "workload": "synthetic_two_int64_columns_at_real_row_count",
        "rows": rows,
        "columns": 2,
        "ipc_file_bytes": file_bytes,
        "ipc_write": {
            "wall_seconds": round(write_wall, 6),
            "thread_cpu_seconds": round(write_cpu, 6),
            "mib_per_second": _rate_mib(file_bytes, write_wall),
        },
        "ipc_mmap_read_and_buffer_scan": {
            "wall_seconds": round(mmap_wall, 6),
            "thread_cpu_seconds": round(mmap_cpu, 6),
            "mib_per_second": _rate_mib(file_bytes, mmap_wall),
            "sha256_prefix": checksum.hexdigest()[:12],
        },
        "arrow_to_python": {
            "wall_seconds": round(python_wall, 6),
            "thread_cpu_seconds": round(python_cpu, 6),
            "rows_materialized": len(converted[0]),
            "mib_per_second": _rate_mib(file_bytes, python_wall),
        },
    }


def _private_json(path: Path, value: Mapping[str, Any]) -> None:
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    os.chmod(path.parent, 0o700)
    temporary = path.with_name(path.name + ".tmp")
    descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
        json.dump(value, stream, sort_keys=True, separators=(",", ":"))
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())
    os.chmod(temporary, 0o600)
    temporary.replace(path)


def run(root: Path, output: Path, scratch_parent: Path, dataset_ids: tuple[str, ...]) -> dict[str, Any]:
    index = _dataset_index(root)
    run_id = output.stem
    scratch = Path(tempfile.mkdtemp(prefix=f"{run_id}-artifacts-", dir=scratch_parent))
    os.chmod(scratch, 0o700)
    scenario_results: list[dict[str, Any]] = []
    package_cache: dict[str, bytes] = {}
    bounds: dict[str, tuple[BoundSnapshotInput, ArtifactRef, DigestRef]] = {}
    stores: dict[str, ScratchArtifactStore] = {}
    artifact_store = ScratchArtifactStore()
    stage_table_costs: list[dict[str, Any]] = []
    basic: dict[str, Any] = {}
    submit_table_facts: dict[str, Mapping[str, Any]] = {}
    try:
        for dataset_id in dataset_ids:
            item = index.get(dataset_id)
            if item is None:
                raise ValueError(f"unknown dataset: {dataset_id}")
            package = _dataset_path(root, item).read_bytes()
            package_cache[dataset_id] = package
            recorder = MeasurementRecorder(dataset_id)
            store = artifact_store
            stores[dataset_id] = store
            bound, manifest_ref, manifest_digest = _snapshot_package(
                dataset_id=dataset_id,
                package=package,
                store=store,
                recorder=recorder,
            )
            bounds[dataset_id] = (bound, manifest_ref, manifest_digest)
            _append_table_costs(
                stage_table_costs,
                scenario=dataset_id,
                recorder=recorder,
                table_facts=cast(Mapping[str, Any], recorder.outputs["tables"]),
            )
            scenario_results.append(
                {
                    "scenario": dataset_id,
                    "kind": "materialize_and_project",
                    "stages": recorder.stages,
                    "summary": recorder.outputs,
                }
            )
            if dataset_id == "rd-t4-d-v1":
                sql_bytes = _extract_required_sql(package)
                basic["package_decompression"] = _standalone_decompression(package)
                basic["hash_algorithms"] = _measure_hashes(package, sql_bytes)
                basic["existing_sql_parse"] = _measure_existing_sql_parser(sql_bytes)
                basic["arrow_ipc_and_conversion"] = _arrow_basic_operations(
                    bound.summary.row_count_total or 1,
                    scratch,
                )

        for tier in _DATASET_TIERS:
            v1_id = f"rd-{tier}-" + {"t1": "a", "t2": "b", "t3": "c", "t4": "d"}[tier] + "-v1"
            v2_id = v1_id.removesuffix("v1") + "v2"
            if v1_id not in bounds or v2_id not in bounds:
                continue
            v1, _v1_manifest, _v1_digest = bounds[v1_id]
            v2, _v2_manifest, _v2_digest = bounds[v2_id]
            if tier == "t4":
                recorder = MeasurementRecorder("t4_v1_preview")
                first_preview = _pair_measurement(
                    recorder=recorder,
                    store=stores[v1_id],
                    scenario="t4_v1_preview",
                    before=_empty_baseline(stores[v1_id]),
                    current=v1,
                )
                submit_table_facts[v1_id] = cast(
                    Mapping[str, Any], first_preview["tables"]
                )
                _append_table_costs(
                    stage_table_costs,
                    scenario="t4_v1_preview",
                    recorder=recorder,
                    table_facts=cast(Mapping[str, Any], first_preview["tables"]),
                )
                scenario_results.append(
                    {
                        "scenario": "t4_v1_preview",
                        "kind": "preview_pair_pipeline",
                        "stages": recorder.stages,
                        "summary": first_preview,
                    }
                )

                repeat_recorder = MeasurementRecorder("t4_repeat_v1_materialize")
                repeated, _repeat_manifest_ref, _repeat_manifest_digest = _snapshot_package(
                    dataset_id="rd-t4-d-repeat-v1",
                    package=package_cache[v1_id],
                    store=stores[v1_id],
                    recorder=repeat_recorder,
                )
                _append_table_costs(
                    stage_table_costs,
                    scenario="t4_repeat_v1_materialize",
                    recorder=repeat_recorder,
                    table_facts=cast(Mapping[str, Any], repeat_recorder.outputs["tables"]),
                )
                scenario_results.append(
                    {
                        "scenario": "t4_repeat_v1_materialize",
                        "kind": "materialize_and_project",
                        "stages": repeat_recorder.stages,
                        "summary": repeat_recorder.outputs,
                    }
                )

                recorder = MeasurementRecorder("t4_repeat_v1_preview")
                repeated_preview = _pair_measurement(
                    recorder=recorder,
                    store=stores[v1_id],
                    scenario="t4_repeat_v1_preview",
                    before=v1,
                    current=repeated,
                )
                _append_table_costs(
                    stage_table_costs,
                    scenario="t4_repeat_v1_preview",
                    recorder=recorder,
                    table_facts=cast(Mapping[str, Any], repeated_preview["tables"]),
                )
                scenario_results.append(
                    {
                        "scenario": "t4_repeat_v1_preview",
                        "kind": "preview_pair_pipeline",
                        "stages": recorder.stages,
                        "summary": repeated_preview,
                    }
                )

                recorder = MeasurementRecorder("t4_v2_preview")
                v2_preview = _pair_measurement(
                    recorder=recorder,
                    store=stores[v2_id],
                    scenario="t4_v2_preview",
                    before=v1,
                    current=v2,
                )
                submit_table_facts[v2_id] = cast(Mapping[str, Any], v2_preview["tables"])
                _append_table_costs(
                    stage_table_costs,
                    scenario="t4_v2_preview",
                    recorder=recorder,
                    table_facts=cast(Mapping[str, Any], v2_preview["tables"]),
                )
                scenario_results.append(
                    {
                        "scenario": "t4_v2_preview",
                        "kind": "preview_pair_pipeline",
                        "stages": recorder.stages,
                        "summary": v2_preview,
                    }
                )
            else:
                baseline = v1
                current = v2
                scenario = f"{tier}_v2_preview"
                recorder = MeasurementRecorder(scenario)
                result = _pair_measurement(
                    recorder=recorder,
                    store=stores[v2_id],
                    scenario=scenario,
                    before=baseline,
                    current=current,
                )
                submit_table_facts[v2_id] = cast(Mapping[str, Any], result["tables"])
                _append_table_costs(
                    stage_table_costs,
                    scenario=scenario,
                    recorder=recorder,
                    table_facts=cast(Mapping[str, Any], result["tables"]),
                )
                scenario_results.append(
                    {
                        "scenario": scenario,
                        "kind": "preview_pair_pipeline",
                        "stages": recorder.stages,
                        "summary": result,
                    }
                )
            if tier == "t4":
                # The new change freezes T1 artifacts. The actual submit prepare capability path
                # consumes those same refs and schema facts without re-projecting source rows.
                for dataset_id in (v1_id, v2_id):
                    bound_current, manifest_ref, manifest_digest = bounds[dataset_id]
                    recorder = MeasurementRecorder(f"{dataset_id}_submit_prepare")
                    result, replay_sql = _submit_measurement(
                        recorder=recorder,
                        store=stores[dataset_id],
                        bound=bound_current,
                        manifest_ref=manifest_ref,
                        manifest_digest=manifest_digest,
                        submit_id=f"s5-{dataset_id}-submit",
                        expected_parent="0" * 64,
                        table_facts=submit_table_facts.get(dataset_id),
                    )
                    if dataset_id == v1_id:
                        basic["direct_dolt_import_and_commit"] = _measure_direct_dolt_import(
                            replay_sql,
                            scratch,
                        )
                    _append_table_costs(
                        stage_table_costs,
                        scenario=recorder.scenario,
                        recorder=recorder,
                        table_facts=cast(Mapping[str, Any], result["tables"]),
                    )
                    scenario_results.append(
                        {
                            "scenario": recorder.scenario,
                            "kind": "submit_prepare",
                            "stages": recorder.stages,
                            "summary": result,
                        }
                    )
                recorder = MeasurementRecorder("t4_history")
                history = _pair_measurement(
                    recorder=recorder,
                    store=stores[v1_id],
                    scenario="t4_history",
                    before=v1,
                    current=v2,
                    history=True,
                )
                _append_table_costs(
                    stage_table_costs,
                    scenario="t4_history",
                    recorder=recorder,
                    table_facts=cast(Mapping[str, Any], history["tables"]),
                )
                scenario_results.append(
                    {
                        "scenario": "t4_history",
                        "kind": "history_pair_pipeline",
                        "stages": recorder.stages,
                        "summary": history,
                    }
                )

        return {
            "schema_version": "s5-dc32-capability-measurement/v1",
            "run_id": run_id,
            "head": subprocess.run(
                ["git", "rev-parse", "HEAD"],
                cwd=_REPO_ROOT,
                check=True,
                capture_output=True,
                text=True,
                timeout=10,
            ).stdout.strip(),
            "dataset_ids": list(dataset_ids),
            "basic_operations": basic,
            "scenarios": scenario_results,
            "per_table_stage_costs": stage_table_costs,
            "privacy": "no row values, row identifiers, SQL text, or credentials recorded",
        }
    finally:
        import shutil

        shutil.rmtree(scratch)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--real-dump-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--scratch-parent", type=Path, required=True)
    parser.add_argument(
        "--dataset",
        action="append",
        dest="datasets",
        help="dataset id; defaults to all t1-t4 v1/v2 packages",
    )
    arguments = parser.parse_args(argv)
    root = arguments.real_dump_root.resolve()
    output = arguments.output.resolve()
    scratch_parent = arguments.scratch_parent.resolve()
    dataset_ids = tuple(
        arguments.datasets
        or tuple(f"rd-{tier}-{letter}-v{version}" for tier, letter in (("t1", "a"), ("t2", "b"), ("t3", "c"), ("t4", "d")) for version in (1, 2))
    )
    result = run(root, output, scratch_parent, dataset_ids)
    _private_json(output, result)
    print(
        json.dumps(
            {
                "output": str(output),
                "run_id": output.stem,
                "scenario_count": len(result["scenarios"]),
                "table_measurement_count": len(result["per_table_stage_costs"]),
                "head": result["head"],
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
