"""Measure the four V5b Preview/Submit segments without product instrumentation.

The runner is intentionally separate from the broad S5 pass. It writes only bounded
timing/count/table-name facts to a private JSON output and leaves its private artifact
store in place for owner cleanup.
"""

from __future__ import annotations

import argparse
import json
import socket
import subprocess
import sys
import time
from collections.abc import Callable, Iterator, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, TypeVar, cast

import s5_dc32_capability_measurement as s5
from gateway_shared_kernel import DigestRef

_BACKEND_ROOT = Path(__file__).resolve().parents[1]
_REPO_ROOT = _BACKEND_ROOT.parents[1]
if str(_BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT))

from gateway_backend.application import pair_pipeline, preview_jobs, submit_jobs  # noqa: E402
from gateway_backend.application.checkpoints import (  # noqa: E402
    StepCheckpointEnvelope,
    load_checkpoint_envelope,
    load_ready_closure,
    prepare_ready_closure,
    prepare_step_checkpoint,
    put_checkpoint_state_artifact,
)
from gateway_backend.application.submission.contracts import (  # noqa: E402
    PREPARE_IMPORT_CHECKPOINT_SCHEMA,
    PrepareImportCheckpoint,
    SnapshotTableBinding,
    SUBMIT_JOB_CONTRACT_VERSION,
)
from gateway_backend.application.submission.import_builder import (  # noqa: E402
    derive_removed_tables,
    pin_prepare_import_artifacts,
    resolve_canonical_snapshot_bindings,
)
from gateway_backend.artifacts.serialize import artifact_ref_to_dict  # noqa: E402
from gateway_backend.artifacts.store import put_with_built_ref  # noqa: E402
from gateway_backend.artifacts.types import ArtifactRef  # noqa: E402
from gateway_backend.capabilities.bundle_assembly import (  # noqa: E402
    BUNDLE_CONTRACT_VERSION,
    BundleAssemblyContext,
    BundleAssemblyInput,
    BundleInput,
    BundlePairInput,
    BundleProfile,
    BundleRefScope,
    BundleAssemblyStatus,
    assemble_bundle,
    validate_bundle,
)
from gateway_backend.capabilities.comparison import open_records_closure  # noqa: E402
from gateway_backend.capabilities.snapshot_materialization import (  # noqa: E402
    CanonicalBinding,
    MaterializationPolicy,
    MaterializationStage,
    RepositoryRef,
    RepositoryRefMaterializationRequest,
    SnapshotMaterializationStatus,
    materialize_repository_ref,
    open_snapshot_table_artifact,
)
from gateway_backend.capabilities.table_access.contracts import (  # noqa: E402
    NeverCancel,
    ParserInvocationContext,
)
from gateway_backend.capabilities.table_rules import migrated_table_ruleset_snapshot  # noqa: E402
from gateway_backend.capabilities.table_rules.contracts import TABLE_RULESET_VERSION  # noqa: E402
from gateway_backend.domain.submission.models import (  # noqa: E402
    BackendArtifactRef,
    BuilderMutationPolicy,
)
from gateway_backend.infrastructure.artifact_store.local_store import (  # noqa: E402
    LocalArtifactStore,
)
from gateway_backend.infrastructure.control_db.database import (  # noqa: E402
    ControlDbUnitOfWork,
    initialize_control_db,
)
from gateway_backend.infrastructure.repository_read import (  # noqa: E402
    HttpRepositoryParentCatalogPort,
    build_http_repository_provider_factory,
)
from gateway_backend.infrastructure.repository_write.import_publication import (  # noqa: E402
    _keyed_rows_from_frozen_artifact,
)
from gateway_backend.operations.worker import ExecutionControl  # noqa: E402

_T = TypeVar("_T")


@dataclass(slots=True)
class SegmentMeter:
    stages: list[dict[str, Any]] = field(default_factory=list)

    def measure(self, stage: str, action: Callable[..., _T], *args: Any, **kwargs: Any) -> _T:
        wall_started = time.perf_counter()
        cpu_started = time.thread_time()
        failed = False
        try:
            return action(*args, **kwargs)
        except BaseException:
            failed = True
            raise
        finally:
            self.stages.append(
                {
                    "stage": stage,
                    "wall_seconds": round(time.perf_counter() - wall_started, 6),
                    "thread_cpu_seconds": round(time.thread_time() - cpu_started, 6),
                    "failed": failed,
                }
            )

    def record(
        self,
        stage: str,
        *,
        wall_seconds: float,
        thread_cpu_seconds: float,
        **facts: Any,
    ) -> None:
        self.stages.append(
            {
                "stage": stage,
                "wall_seconds": round(wall_seconds, 6),
                "thread_cpu_seconds": round(thread_cpu_seconds, 6),
                **facts,
            }
        )


class FileMeasurementArtifactStore(s5.ScratchArtifactStore):
    """Keep the S5 counter interface while measuring the local production store path."""

    def __init__(self, artifact_root: Path) -> None:
        super().__init__()
        artifact_root.mkdir(mode=0o700, parents=True, exist_ok=False)
        artifact_root.chmod(0o700)
        self._local = LocalArtifactStore(artifact_root)
        self._local.artifact_root.chmod(0o700)
        self.read_wall_seconds = 0.0
        self.read_thread_cpu_seconds = 0.0
        self.read_count = 0
        self.read_bytes = 0

    def put(self, raw_bytes: bytes, ref: ArtifactRef) -> ArtifactRef:
        wall_started = time.perf_counter()
        cpu_started = time.thread_time()
        result = self._local.put(raw_bytes, ref)
        self.write_wall_seconds += time.perf_counter() - wall_started
        self.write_thread_cpu_seconds += time.thread_time() - cpu_started
        self.write_count += 1
        self.write_bytes += len(raw_bytes)
        return result

    def locate(self, ref: ArtifactRef) -> bytes:
        wall_started = time.perf_counter()
        cpu_started = time.thread_time()
        result = self._local.locate(ref)
        self.read_wall_seconds += time.perf_counter() - wall_started
        self.read_thread_cpu_seconds += time.thread_time() - cpu_started
        self.read_count += 1
        self.read_bytes += len(result)
        return result

    def io_stats(self) -> dict[str, float | int]:
        return {
            "write_wall_seconds": self.write_wall_seconds,
            "write_thread_cpu_seconds": self.write_thread_cpu_seconds,
            "write_count": self.write_count,
            "write_bytes": self.write_bytes,
            "read_wall_seconds": self.read_wall_seconds,
            "read_thread_cpu_seconds": self.read_thread_cpu_seconds,
            "read_count": self.read_count,
            "read_bytes": self.read_bytes,
        }


def _io_delta(
    before: Mapping[str, float | int], after: Mapping[str, float | int]
) -> dict[str, float | int]:
    return {key: after[key] - before[key] for key in before}


@dataclass(slots=True)
class RepositoryReadMetrics:
    stages: list[dict[str, Any]] = field(default_factory=list)
    per_table: dict[str, dict[str, float | int]] = field(default_factory=dict)
    catalog_table_count: int = 0

    def measure(
        self,
        stage: str,
        action: Callable[..., _T],
        *args: Any,
        **kwargs: Any,
    ) -> _T:
        wall_started = time.perf_counter()
        cpu_started = time.thread_time()
        try:
            result = action(*args, **kwargs)
        except BaseException:
            self.stages.append(
                {
                    "stage": stage,
                    "wall_seconds": round(time.perf_counter() - wall_started, 6),
                    "thread_cpu_seconds": round(time.thread_time() - cpu_started, 6),
                    "failed": True,
                }
            )
            raise
        self.stages.append(
            {
                "stage": stage,
                "wall_seconds": round(time.perf_counter() - wall_started, 6),
                "thread_cpu_seconds": round(time.thread_time() - cpu_started, 6),
                "failed": False,
            }
        )
        return result

    def record_table_stream(self, name: str, *, wall: float, cpu: float, rows: int) -> None:
        item = self.per_table.setdefault(
            name,
            {"wall_seconds": 0.0, "thread_cpu_seconds": 0.0, "row_count": 0, "calls": 0},
        )
        item["wall_seconds"] = float(item["wall_seconds"]) + wall
        item["thread_cpu_seconds"] = float(item["thread_cpu_seconds"]) + cpu
        item["row_count"] = int(item["row_count"]) + rows
        item["calls"] = int(item["calls"]) + 1

    def record_table_open(self, name: str, *, wall: float, cpu: float) -> None:
        item = self.per_table.setdefault(
            name,
            {"wall_seconds": 0.0, "thread_cpu_seconds": 0.0, "row_count": 0, "calls": 0},
        )
        item["open_wall_seconds"] = float(item.get("open_wall_seconds", 0.0)) + wall
        item["open_thread_cpu_seconds"] = (
            float(item.get("open_thread_cpu_seconds", 0.0)) + cpu
        )


class TimedRepositoryReader:
    def __init__(self, reader: Any, metrics: RepositoryReadMetrics, table_name: str) -> None:
        self._reader = reader
        self._metrics = metrics
        self._table_name = table_name

    def catalog_table(self) -> Any:
        return self._reader.catalog_table()

    def column_order(self) -> tuple[str, ...]:
        return self._reader.column_order()

    def stream_rows(self) -> Iterator[tuple[object | None, ...]]:
        iterator = iter(self._reader.stream_rows())
        wall_total = 0.0
        cpu_total = 0.0
        row_count = 0
        try:
            while True:
                wall_started = time.perf_counter()
                cpu_started = time.thread_time()
                try:
                    row = next(iterator)
                except StopIteration:
                    break
                finally:
                    wall_total += time.perf_counter() - wall_started
                    cpu_total += time.thread_time() - cpu_started
                row_count += 1
                yield row
        finally:
            self._metrics.record_table_stream(
                self._table_name,
                wall=wall_total,
                cpu=cpu_total,
                rows=row_count,
            )

    def close(self) -> None:
        self._reader.close()


class TimedRepositorySession:
    def __init__(self, session: Any, metrics: RepositoryReadMetrics) -> None:
        self._session = session
        self._metrics = metrics

    def pinned_commit_hash(self) -> str:
        return self._session.pinned_commit_hash()

    def get_catalog(self) -> Any:
        catalog = self._metrics.measure("repository_service_catalog_read", self._session.get_catalog)
        self._metrics.catalog_table_count = len(catalog.tables)
        return catalog

    def open_table_reader(self, table_name: str) -> TimedRepositoryReader:
        wall_started = time.perf_counter()
        cpu_started = time.thread_time()
        try:
            reader = self._session.open_table_reader(table_name)
        finally:
            self._metrics.record_table_open(
                table_name,
                wall=time.perf_counter() - wall_started,
                cpu=time.thread_time() - cpu_started,
            )
        return TimedRepositoryReader(reader, self._metrics, table_name)

    def export_table_artifact(self, table_name: str, export_format: str) -> None:
        self._session.export_table_artifact(table_name, export_format)

    def close(self) -> None:
        self._metrics.measure("repository_service_session_close", self._session.close)


class TimedRepositoryProvider:
    def __init__(self, provider: Any, metrics: RepositoryReadMetrics) -> None:
        self._provider = provider
        self._metrics = metrics

    def open_ref(self, repository_ref: Any, timeout_policy: Any) -> TimedRepositorySession:
        session = self._metrics.measure(
            "repository_service_open_ref",
            self._provider.open_ref,
            repository_ref,
            timeout_policy,
        )
        return TimedRepositorySession(session, self._metrics)


def _unique_refs(refs: Sequence[ArtifactRef]) -> tuple[ArtifactRef, ...]:
    by_id: dict[str, ArtifactRef] = {}
    for ref in refs:
        existing = by_id.get(ref.artifact_id)
        if existing is not None and existing != ref:
            raise ValueError("one artifact id resolved to multiple references")
        by_id[ref.artifact_id] = ref
    return tuple(by_id[key] for key in sorted(by_id))


def _table_artifact_refs(bound: Any) -> tuple[ArtifactRef, ...]:
    if bound.table_set is None:
        raise RuntimeError("canonical snapshot table set is missing")
    refs: list[ArtifactRef] = []
    for table in bound.table_set.tables:
        if table.artifact is None:
            raise RuntimeError("canonical snapshot artifact is missing")
        refs.extend((table.artifact.manifest_ref, *table.artifact.manifest.row_file_refs))
    return _unique_refs(refs)


def _canonical_binding(bound: Any, ruleset: Any) -> CanonicalBinding:
    if ruleset.ruleset_digest is None:
        raise RuntimeError("runtime table ruleset digest is missing")
    views = tuple(
        sorted(
            (fact.storage_rule_view for fact in bound.storage_facts),
            key=lambda item: item.canonical_table.encode("utf-8"),
        )
    )
    return CanonicalBinding(
        storage_projection_version=ruleset.storage_projection_version,
        ruleset_id=ruleset.ruleset_id,
        ruleset_version=ruleset.ruleset_version,
        ruleset_digest=ruleset.ruleset_digest,
        tables=views,
    )


def _measure_repository_materialization(
    *,
    store: FileMeasurementArtifactStore,
    repository_id: str,
    commit_id: str,
    bearer_token: str,
    base_url: str,
    canonical_source: Any,
) -> tuple[dict[str, Any], Any, RepositoryReadMetrics]:
    ruleset = migrated_table_ruleset_snapshot()
    binding = _canonical_binding(canonical_source, ruleset)
    read_metrics = RepositoryReadMetrics()
    provider_factory = build_http_repository_provider_factory(
        base_url=base_url,
        bearer_token=bearer_token,
        timeout_seconds=900.0,
    )
    provider = TimedRepositoryProvider(provider_factory(repository_id, commit_id), read_metrics)
    request = RepositoryRefMaterializationRequest(
        repository_ref=RepositoryRef(repository_id=repository_id, ref=commit_id),
        provider=provider,
        ruleset=ruleset,
        canonical_binding=binding,
        table_ruleset_version=TABLE_RULESET_VERSION,
        materialization_stage=MaterializationStage.FINAL,
        policy=MaterializationPolicy.ARTIFACTS_REQUIRED,
        context=ParserInvocationContext(NeverCancel()),
        artifact_store=store,
    )
    before_io = store.io_stats()
    wall_started = time.perf_counter()
    cpu_started = time.thread_time()
    result = materialize_repository_ref(request)
    if result.status is not SnapshotMaterializationStatus.COMPLETE or result.table_set is None:
        first = result.diagnostics[0] if result.diagnostics else None
        raise RuntimeError(
            "RepositoryRef materialization did not complete"
            if first is None
            else f"RepositoryRef materialization failed with {first.code.value}"
        )
    baseline_bound = preview_jobs._bound_from_materialization(
        result,
        label="V5b Repository baseline",
        canonical_binding=binding,
    )
    total_wall = time.perf_counter() - wall_started
    total_cpu = time.thread_time() - cpu_started
    materialize_io = _io_delta(before_io, store.io_stats())
    refs: list[ArtifactRef] = []
    table_rows: list[dict[str, Any]] = []
    for table in result.table_set.tables:
        if table.artifact is None:
            raise RuntimeError("materialized Repository table has no artifact")
        refs.extend((table.artifact.manifest_ref, *table.artifact.manifest.row_file_refs))
        table_rows.append(
            {
                "table_name": table.descriptor.table_name,
                "row_count": table.descriptor.row_count,
                "column_count": len(table.descriptor.columns),
            }
        )
    unique_artifact_refs = _unique_refs(refs)
    readback_before = store.io_stats()
    readback_wall_started = time.perf_counter()
    readback_cpu_started = time.thread_time()
    readback_bytes = 0
    for ref in unique_artifact_refs:
        readback_bytes += len(store.locate(ref))
    readback_wall = time.perf_counter() - readback_wall_started
    readback_cpu = time.thread_time() - readback_cpu_started
    readback_io = _io_delta(readback_before, store.io_stats())

    rs_wall = sum(float(item["wall_seconds"]) for item in read_metrics.stages)
    rs_cpu = sum(float(item["thread_cpu_seconds"]) for item in read_metrics.stages)
    rs_wall += sum(
        float(item["wall_seconds"]) + float(item.get("open_wall_seconds", 0.0))
        for item in read_metrics.per_table.values()
    )
    rs_cpu += sum(
        float(item["thread_cpu_seconds"])
        + float(item.get("open_thread_cpu_seconds", 0.0))
        for item in read_metrics.per_table.values()
    )
    write_wall = float(materialize_io["write_wall_seconds"])
    write_cpu = float(materialize_io["write_thread_cpu_seconds"])
    internal_read_wall = float(materialize_io["read_wall_seconds"])
    internal_read_cpu = float(materialize_io["read_thread_cpu_seconds"])
    python_wall = total_wall - rs_wall - write_wall - internal_read_wall
    python_cpu = total_cpu - rs_cpu - write_cpu - internal_read_cpu
    summary = {
        "scenario": "t4_v1_repository_ref_materialization",
        "total_wall_seconds": round(total_wall, 6),
        "total_thread_cpu_seconds": round(total_cpu, 6),
        "repository_reads": {
            "stages": read_metrics.stages,
            "per_table": [
                {
                    "table_name": name,
                    **{
                        key: round(value, 6) if isinstance(value, float) else value
                        for key, value in facts.items()
                    },
                }
                for name, facts in sorted(read_metrics.per_table.items())
            ],
            "table_count": read_metrics.catalog_table_count,
            "wall_seconds": round(rs_wall, 6),
            "thread_cpu_seconds": round(rs_cpu, 6),
        },
        "python_materialize_and_digest_residual": {
            "wall_seconds": round(python_wall, 6),
            "thread_cpu_seconds": round(python_cpu, 6),
            "relation": "inclusive minus measured Repository and ArtifactStore calls",
        },
        "artifact_write_during_materialization": materialize_io,
        "artifact_read_during_materialization": {
            "wall_seconds": round(internal_read_wall, 6),
            "thread_cpu_seconds": round(internal_read_cpu, 6),
            "read_count": materialize_io["read_count"],
            "read_bytes": materialize_io["read_bytes"],
        },
        "artifact_readback_validation": {
            "wall_seconds": round(readback_wall, 6),
            "thread_cpu_seconds": round(readback_cpu, 6),
            "artifact_count": len(unique_artifact_refs),
            "bytes_read": readback_bytes,
            "store_io": readback_io,
        },
        "table_count": len(table_rows),
        "row_count_total": sum(item["row_count"] for item in table_rows),
        "tables": table_rows,
    }
    return summary, baseline_bound, read_metrics


def _measure_bundle(
    *,
    scenario: str,
    before: Any,
    current: Any,
    store: FileMeasurementArtifactStore,
) -> tuple[dict[str, Any], Any, tuple[ArtifactRef, ...]]:
    recorder = s5.MeasurementRecorder(scenario)
    pair_id = scenario.replace("_", "-")
    patches = s5._capability_patches() + (
        (pair_pipeline, "publish_records_closure", "records_closure_generation", None),
    )
    pair_io_before = store.io_stats()
    with s5._patched(recorder, patches):
        pair_result = recorder.measure(
            "pair_pipeline_including_records_closure",
            pair_pipeline.run_preview_pair_pipeline,
            pair_id=pair_id,
            before=before,
            current=current,
            store=store,
            control=ExecutionControl(),
            on_cancel=lambda: None,
        )
    pair_io = _io_delta(pair_io_before, store.io_stats())
    surface = pair_result.surface_result.surface
    if surface is None or pair_result.records_closure is None:
        raise RuntimeError("Preview pair pipeline did not produce surface and records closure")
    closure_meter = SegmentMeter()
    surface_closure = closure_meter.measure(
        "surface_artifact_closure_generation",
        preview_jobs.surface_artifact_closure,
        surface,
        pair_id,
        pair_result.records_closure,
        before=before,
        current=current,
    )
    request = BundleAssemblyInput(
        bundle_contract_version=BUNDLE_CONTRACT_VERSION,
        bundle_profile=BundleProfile.SINGLE_PAIR,
        inputs=(
            BundleInput(0, "before", "Before", snapshot_digest=before.snapshot.snapshot_digest),
            BundleInput(1, "current", "Current", snapshot_digest=current.snapshot.snapshot_digest),
        ),
        pairs=(BundlePairInput(pair_id, 0, 1, pair_result.surface_result, surface_closure),),
        ref_scope=BundleRefScope.BUNDLE_RELATIVE,
    )
    before_bundle_io = store.io_stats()
    bundle_result = recorder.measure(
        "assemble_bundle",
        assemble_bundle,
        request,
        source_store=store,
        context=BundleAssemblyContext(),
    )
    bundle_io = _io_delta(before_bundle_io, store.io_stats())
    if bundle_result.status is not BundleAssemblyStatus.READY or bundle_result.bundle is None:
        diagnostic = bundle_result.diagnostics[0] if bundle_result.diagnostics else "unknown"
        raise RuntimeError(f"bundle assembly failed: {diagnostic}")
    bundle = bundle_result.bundle
    validate_bundle_seconds_before = time.perf_counter()
    validate_bundle_cpu_before = time.thread_time()
    validate_bundle(bundle, store)
    validate_wall = time.perf_counter() - validate_bundle_seconds_before
    validate_cpu = time.thread_time() - validate_bundle_cpu_before
    closure_ref = surface.refs.records_closure_ref
    if closure_ref is None:
        raise RuntimeError("Preview surface has no records closure ref")
    records_before = time.perf_counter()
    records_cpu_before = time.thread_time()
    reopened_records = open_records_closure(store, closure_ref)
    records_readback_wall = time.perf_counter() - records_before
    records_readback_cpu = time.thread_time() - records_cpu_before
    output_refs = _unique_refs(
        (
            *bundle_result.referenced_artifacts,
            bundle.manifest_ref,
            bundle.artifact_closure_ref,
            *_table_artifact_refs(before),
            *_table_artifact_refs(current),
        )
    )
    recorded = [stage for stage in recorder.stages]
    record_generation = next(
        (stage for stage in recorded if stage["stage"] == "records_closure_generation"),
        None,
    )
    if record_generation is None:
        raise RuntimeError("records closure generation timing was not captured")
    return (
        {
            "scenario": scenario,
            "pair_pipeline_including_records_closure": next(
                stage for stage in recorded if stage["stage"] == "pair_pipeline_including_records_closure"
            ),
            "pair_artifact_store_io": pair_io,
            "surface_artifact_closure_generation": closure_meter.stages,
            "records_closure_generation": record_generation,
            "assemble_bundle": next(stage for stage in recorded if stage["stage"] == "assemble_bundle"),
            "bundle_artifact_store_io": bundle_io,
            "bundle_explicit_readback_validation": {
                "wall_seconds": round(validate_wall, 6),
                "thread_cpu_seconds": round(validate_cpu, 6),
            },
            "records_closure_full_readback_validation": {
                "wall_seconds": round(records_readback_wall, 6),
                "thread_cpu_seconds": round(records_readback_cpu, 6),
                "closure_entry_count": len(reopened_records.records),
                "record_count": sum(item.record_count for item in reopened_records.records),
            },
            "table_count": current.summary.table_count,
            "row_count_total": current.summary.row_count_total,
            "table_record_counts": [
                {"table_name": entry.table_name, "record_count": entry.record_count}
                for entry in reopened_records.records
            ],
            "bundle_artifact_count": bundle.summary.artifact_count,
            "ready_ref_count": len(output_refs),
            "capability_stages": recorded,
        },
        bundle,
        output_refs,
    )


def _measure_submit_build_inputs(
    *,
    store: FileMeasurementArtifactStore,
    current: Any,
    manifest_ref: ArtifactRef,
    manifest_digest: DigestRef,
    ready_refs: tuple[ArtifactRef, ...],
    repository_id: str,
    parent_commit_id: str,
    bearer_token: str,
    base_url: str,
) -> tuple[
    dict[str, Any],
    tuple[SnapshotTableBinding, ...],
    tuple[ArtifactRef, ...],
    tuple[str, ...],
    ArtifactRef,
]:
    from gateway_backend.capabilities.storage_projection import canonicalization_manifest_from_bytes

    meter = SegmentMeter()
    ready_ref = meter.measure(
        "prepare_preview_ready_closure",
        prepare_ready_closure,
        store,
        ready_refs,
        preview_jobs.PREVIEW_JOB_CONTRACT_VERSION,
    )
    before_ready_load_io = store.io_stats()
    loaded_ready = meter.measure("load_ready_closure_and_verify_refs", load_ready_closure, store, ready_ref)
    ready_load_io = _io_delta(before_ready_load_io, store.io_stats())

    canonical_closure_ref = meter.measure(
        "publish_frozen_canonical_table_set_closure",
        preview_jobs._publish_canonical_table_set_closure,
        current,
        store,
    )
    operation_refs = _unique_refs(
        (
            *ready_refs,
            *loaded_ready.artifact_refs(),
            canonical_closure_ref,
            manifest_ref,
            *_table_artifact_refs(current),
        )
    )
    before_resolve_io = store.io_stats()
    snapshot_tables, canonical_refs = meter.measure(
        "resolve_frozen_canonical_snapshot_bindings",
        resolve_canonical_snapshot_bindings,
        operation_artifact_refs=operation_refs,
        canonical_table_set_closure_ref=canonical_closure_ref.artifact_id,
        canonical_table_set_closure_digest=canonical_closure_ref.raw_sha256.value,
        canonicalization_manifest_ref=manifest_ref.artifact_id,
        canonicalization_manifest_digest=manifest_digest.value,
        read_artifact=store.locate,
    )
    resolve_io = _io_delta(before_resolve_io, store.io_stats())

    parent_catalog = HttpRepositoryParentCatalogPort(
        base_url=base_url,
        bearer_token=bearer_token,
        timeout_seconds=900.0,
    )
    parent_names = meter.measure(
        "query_parent_commit_table_names",
        parent_catalog.get_table_names,
        repository_id=repository_id,
        commit_id=parent_commit_id,
    )
    removed_tables = derive_removed_tables(
        parent_table_names=parent_names,
        snapshot_tables=snapshot_tables,
    )

    before_manifest_load_io = store.io_stats()
    frozen_manifest = meter.measure(
        "load_frozen_canonical_manifest_for_row_verification",
        lambda: canonicalization_manifest_from_bytes(store.locate(manifest_ref)),
    )
    manifest_load_io = _io_delta(before_manifest_load_io, store.io_stats())
    frozen_tables = {table.name: table for table in frozen_manifest.tables}
    resolved_refs = {ref.artifact_id: ref for ref in canonical_refs}
    per_table_reads: list[dict[str, Any]] = []
    row_read_wall = 0.0
    row_read_cpu = 0.0
    total_rows = 0
    for binding in snapshot_tables:
        table_ref = resolved_refs.get(binding.artifact_id)
        frozen_table = frozen_tables.get(binding.table_name)
        if table_ref is None or frozen_table is None:
            raise RuntimeError("frozen canonical table binding is incomplete")
        open_wall_started = time.perf_counter()
        open_cpu_started = time.thread_time()
        table = open_snapshot_table_artifact(store, table_ref)
        open_wall = time.perf_counter() - open_wall_started
        open_cpu = time.thread_time() - open_cpu_started
        reader = table.reader
        if reader is None:
            raise RuntimeError("frozen canonical table artifact has no reader")
        rows_wall_started = time.perf_counter()
        rows_cpu_started = time.thread_time()
        keyed_rows = _keyed_rows_from_frozen_artifact(
            reader,
            descriptor=table.descriptor,
            manifest_table=frozen_table,
        )
        rows_wall = time.perf_counter() - rows_wall_started
        rows_cpu = time.thread_time() - rows_cpu_started
        reader.close()
        table_rows = len(keyed_rows)
        total_rows += table_rows
        row_read_wall += open_wall + rows_wall
        row_read_cpu += open_cpu + rows_cpu
        per_table_reads.append(
            {
                "table_name": binding.table_name,
                "row_count": table_rows,
                "column_count": len(table.descriptor.columns),
                "artifact_open_verify_wall_seconds": round(open_wall, 6),
                "artifact_open_verify_thread_cpu_seconds": round(open_cpu, 6),
                "keyed_row_decode_wall_seconds": round(rows_wall, 6),
                "keyed_row_decode_thread_cpu_seconds": round(rows_cpu, 6),
            }
        )
    meter.record(
        "read_verify_frozen_rows_table_by_table",
        wall_seconds=row_read_wall,
        thread_cpu_seconds=row_read_cpu,
        table_count=len(per_table_reads),
        row_count_total=total_rows,
    )

    return (
        {
            "stages": meter.stages,
            "ready_closure_load_store_io": ready_load_io,
            "frozen_binding_resolution_store_io": resolve_io,
            "frozen_manifest_load_store_io": manifest_load_io,
            "parent_table_count": len(parent_names),
            "parent_table_names": list(parent_names),
            "snapshot_table_count": len(snapshot_tables),
            "removed_table_count": len(removed_tables),
            "removed_table_names": list(removed_tables),
            "frozen_row_table_count": len(per_table_reads),
            "frozen_row_count_total": total_rows,
            "frozen_table_reads": per_table_reads,
            "ready_closure_ref_count": len(loaded_ready.outputs),
        },
        snapshot_tables,
        canonical_refs,
        removed_tables,
        canonical_closure_ref,
    )


def _measure_checkpoints_and_pins(
    *,
    store: FileMeasurementArtifactStore,
    db_path: Path,
    v1_bundle: Any,
    v1_ready_refs: tuple[ArtifactRef, ...],
    v1_manifest_digest: DigestRef,
    v2_ready_refs: tuple[ArtifactRef, ...],
    v2_manifest_ref: ArtifactRef,
    v2_manifest_digest: DigestRef,
    parent_commit_id: str,
    canonical_closure_ref: ArtifactRef,
    removed_tables: tuple[str, ...],
    canonical_refs: tuple[ArtifactRef, ...],
) -> dict[str, Any]:
    from gateway_backend.application.submission.job_payload import (
        SUBMIT_JOB_KIND,
        SUBMIT_STEP_PREPARE,
    )

    output: dict[str, Any] = {}
    preview_ready_ref = prepare_ready_closure(
        store,
        v1_ready_refs,
        preview_jobs.PREVIEW_JOB_CONTRACT_VERSION,
    )
    preview_state_ref = put_checkpoint_state_artifact(
        store,
        {
            "document_type": preview_jobs.PREVIEW_ASSEMBLE_STATE_DOCUMENT_TYPE,
            "contract_version": preview_jobs.PREVIEW_ASSEMBLE_STATE_CONTRACT_VERSION,
            preview_jobs._JOB_STATE_ASSEMBLE: {
                "pair_ids": ["v5b-preview-pair"],
                "default_view": "initial_to_modified",
                "input_completeness": "DELTA",
                "digests": {
                    "source_digest": v1_manifest_digest.value,
                    "input_digest": v1_manifest_digest.value,
                    "snapshot_digest": v1_bundle.pairs[0].surface_digest.value,
                    "comparison_digest": v1_bundle.pairs[0].comparison_digest.value,
                    "risk_digest": v1_bundle.pairs[0].risk_evaluation_digest.value
                    if v1_bundle.pairs[0].risk_evaluation_digest is not None
                    else "sha256:" + "00" * 32,
                    "surface_digest": v1_bundle.pairs[0].surface_digest.value,
                    "bundle_digest": v1_bundle.bundle_digest.value,
                },
                "required_refs": [artifact_ref_to_dict(ref) for ref in v1_ready_refs],
            },
        },
        artifact_id_prefix="v5b-preview-assemble-state",
    )
    preview_job_state = {
        preview_jobs._JOB_STATE_ASSEMBLE_REF: artifact_ref_to_dict(preview_state_ref),
        preview_jobs._JOB_STATE_READY_CLOSURE: preview_ready_ref.artifact_id,
        preview_jobs._JOB_STATE_READY_CLOSURE_REF: artifact_ref_to_dict(preview_ready_ref),
        preview_jobs._JOB_STATE_BUNDLE_ARTIFACT: v1_bundle.manifest_ref.artifact_id,
        preview_jobs._JOB_STATE_BUNDLE_DIGEST: v1_bundle.bundle_digest.value,
    }
    preview_envelope = StepCheckpointEnvelope(
        job_kind=preview_jobs.PREVIEW_JOB_KIND,
        step_name=preview_jobs.PREVIEW_STEP_ASSEMBLE,
        operation_id="v5b-preview-checkpoint-probe",
        job_contract_version=preview_jobs.PREVIEW_JOB_CONTRACT_VERSION,
        checkpoint_generation=1,
        prior_output_refs=(),
        job_state=preview_job_state,
    )
    preview_checkpoint_meter = SegmentMeter()
    preview_checkpoint_ref = preview_checkpoint_meter.measure(
        "preview_checkpoint_serialize_verify_and_publish",
        prepare_step_checkpoint,
        store,
        preview_envelope,
    )
    preview_checkpoint_meter.measure(
        "preview_checkpoint_readback_decode",
        load_checkpoint_envelope,
        store,
        preview_checkpoint_ref,
    )

    initialize_control_db(db_path)
    db_path.chmod(0o600)
    preview_deps = preview_jobs.PreviewRuntimeDependencies(
        artifact_store=store,
        repository_provider_factory=lambda _repository_id, _commit_id: None,
        baseline_head_read=cast(Any, lambda **_kwargs: None),
        control_transaction_factory=lambda: ControlDbUnitOfWork(db_path),
    )
    preview_pin_refs = _unique_refs(
        (
            preview_checkpoint_ref,
            preview_state_ref,
            preview_ready_ref,
            *v1_ready_refs,
        )
    )
    preview_checkpoint_meter.measure(
        "preview_artifact_pin_transaction",
        preview_jobs._pin_preview_refs,
        preview_deps,
        preview_pin_refs,
        owner_kind="preview-checkpoint",
        owner_id="v5b-preview-checkpoint-probe",
        intent="assemble-checkpoint",
    )
    output["preview"] = {
        "stages": preview_checkpoint_meter.stages,
        "serialized_checkpoint_bytes": preview_checkpoint_ref.size_bytes,
        "pinned_artifact_count": len(preview_pin_refs),
    }

    placeholder_package = put_with_built_ref(
        store,
        b"v5b-submit-checkpoint-probe",
        artifact_id="v5b-submit-import-package-probe",
        media_type="application/vnd.gateway.repository-import+tar",
    )
    manifest_backend_ref = BackendArtifactRef(
        artifact_id=v2_manifest_ref.artifact_id,
        media_type=v2_manifest_ref.media_type,
        size_bytes=v2_manifest_ref.size_bytes,
        raw_sha256=v2_manifest_ref.raw_sha256.value,
    )
    package_backend_ref = BackendArtifactRef(
        artifact_id=placeholder_package.artifact_id,
        media_type=placeholder_package.media_type,
        size_bytes=placeholder_package.size_bytes,
        raw_sha256=placeholder_package.raw_sha256.value,
    )
    submit_checkpoint = PrepareImportCheckpoint(
        schema_version=PREPARE_IMPORT_CHECKPOINT_SCHEMA,
        attempt_id="v5b-submit-checkpoint-probe",
        canonical_table_set_closure_ref=canonical_closure_ref.artifact_id,
        canonical_table_set_closure_digest=canonical_closure_ref.raw_sha256.value,
        input_canonicalization_manifest_ref=v2_manifest_ref.artifact_id,
        input_canonicalization_manifest_digest=v2_manifest_digest.value,
        expected_parent_commit_id=parent_commit_id,
        removed_tables=removed_tables,
        canonicalization_manifest_ref=manifest_backend_ref,
        canonicalization_manifest_digest=v2_manifest_digest.value,
        backend_import_artifact_ref=package_backend_ref,
        package_raw_size=placeholder_package.size_bytes,
        package_raw_sha256=placeholder_package.raw_sha256.value,
        builder_mutation_policy=BuilderMutationPolicy.REBUILD_ALWAYS,
    )
    submit_job_state = submit_jobs._job_state_for_prepare(submit_checkpoint)
    submit_envelope = StepCheckpointEnvelope(
        job_kind=SUBMIT_JOB_KIND,
        step_name=SUBMIT_STEP_PREPARE,
        operation_id="v5b-submit-checkpoint-probe",
        job_contract_version=SUBMIT_JOB_CONTRACT_VERSION,
        checkpoint_generation=1,
        prior_output_refs=(),
        job_state=submit_job_state,
    )
    submit_checkpoint_meter = SegmentMeter()
    submit_checkpoint_ref = submit_checkpoint_meter.measure(
        "submit_checkpoint_serialize_verify_and_publish",
        prepare_step_checkpoint,
        store,
        submit_envelope,
    )
    submit_checkpoint_meter.measure(
        "submit_checkpoint_readback_decode",
        load_checkpoint_envelope,
        store,
        submit_checkpoint_ref,
    )
    submit_pin_refs = _unique_refs((
        *canonical_refs,
        *v2_ready_refs,
    ))

    def pin_submit_artifacts() -> None:
        with ControlDbUnitOfWork(db_path) as unit_of_work:
            pin_prepare_import_artifacts(
                unit_of_work,
                submit_attempt_id="v5b-submit-checkpoint-probe",
                manifest_ref=manifest_backend_ref,
                package_ref=package_backend_ref,
                existing_snapshot_refs=submit_pin_refs,
            )

    submit_checkpoint_meter.measure(
        "submit_artifact_pin_transaction",
        pin_submit_artifacts,
    )
    output["submit"] = {
        "stages": submit_checkpoint_meter.stages,
        "serialized_checkpoint_bytes": submit_checkpoint_ref.size_bytes,
        "pinned_artifact_count": len(submit_pin_refs) + 2,
        "package_ref_is_probe_payload": True,
    }
    return output


def run(
    *,
    real_dump_root: Path,
    output_path: Path,
    scratch_path: Path,
    repository_id: str,
    baseline_commit_id: str,
    bearer_token_file: Path,
    repository_service_url: str,
) -> dict[str, Any]:
    output_path = output_path.resolve()
    scratch_path = scratch_path.resolve()
    if output_path.is_relative_to(_REPO_ROOT) or scratch_path.is_relative_to(_REPO_ROOT):
        raise ValueError("V5b output and scratch paths must be outside the worktree")
    if output_path == scratch_path or output_path.is_relative_to(scratch_path):
        raise ValueError("V5b output must be outside the artifact scratch directory")
    if output_path.exists():
        raise ValueError("V5b output path already exists")
    if not real_dump_root.is_dir():
        raise ValueError("real dump root is unavailable")
    if not bearer_token_file.is_file():
        raise ValueError("Repository Service bearer-token file is unavailable")
    output_path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    output_path.parent.chmod(0o700)
    if scratch_path.exists():
        raise ValueError("V5b artifact scratch path already exists")
    scratch_path.mkdir(mode=0o700, parents=True, exist_ok=False)
    scratch_path.chmod(0o700)
    artifact_root = scratch_path / "artifacts"
    store = FileMeasurementArtifactStore(artifact_root)
    start_time = time.time()
    start_wall = time.perf_counter()
    start_cpu = time.thread_time()
    head = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=_REPO_ROOT,
        check=True,
        capture_output=True,
        text=True,
        timeout=10,
    ).stdout.strip()
    result: dict[str, Any] = {
        "schema_version": "p6-v5b-segment-measurement/v1",
        "hostname": socket.gethostname(),
        "head": head,
        "started_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(start_time)),
        "status": "RUNNING",
        "segments": [],
        "privacy": "counts, table names, and timings only; no row values, SQL, credentials, repository ids, or commit ids",
    }

    def checkpoint(status: str, failure_type: str | None = None) -> None:
        result["status"] = status
        if failure_type is not None:
            result["failure_type"] = failure_type
        if status in {"PASS", "FAILED"}:
            result["ended_at_utc"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
            result["end_head"] = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                cwd=_REPO_ROOT,
                check=True,
                capture_output=True,
                text=True,
                timeout=10,
            ).stdout.strip()
        else:
            result["updated_at_utc"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        result["wall_seconds"] = round(time.perf_counter() - start_wall, 6)
        result["thread_cpu_seconds"] = round(time.thread_time() - start_cpu, 6)
        result["artifact_store_totals"] = store.io_stats()
        s5._private_json(output_path, result)

    try:
        bearer_token = bearer_token_file.read_text(encoding="utf-8").strip()
        if not bearer_token:
            raise ValueError("Repository Service bearer-token file is empty")
        dataset_index = s5._dataset_index(real_dump_root)
        v1_item = dataset_index.get("rd-t4-d-v1")
        v2_item = dataset_index.get("rd-t4-d-v2")
        if v1_item is None or v2_item is None:
            raise ValueError("t4 v1/v2 dataset descriptors are unavailable")
        v1_package = s5._dataset_path(real_dump_root, v1_item).read_bytes()
        v2_package = s5._dataset_path(real_dump_root, v2_item).read_bytes()
        v1_recorder = s5.MeasurementRecorder("v5b_t4_v1_package")
        v1_bound, _v1_manifest_ref, v1_manifest_digest = s5._snapshot_package(
            dataset_id="rd-t4-d-v1",
            package=v1_package,
            store=store,
            recorder=v1_recorder,
        )
        materialization, repository_baseline, _repository_reads = (
            _measure_repository_materialization(
                store=store,
                repository_id=repository_id,
                commit_id=baseline_commit_id,
                bearer_token=bearer_token,
                base_url=repository_service_url,
                canonical_source=v1_bound,
            )
        )
        result["segments"].append(materialization)
        checkpoint("RUNNING")

        v2_recorder = s5.MeasurementRecorder("v5b_t4_v2_package")
        v2_bound, v2_manifest_ref, v2_manifest_digest = s5._snapshot_package(
            dataset_id="rd-t4-d-v2",
            package=v2_package,
            store=store,
            recorder=v2_recorder,
        )
        empty_baseline = s5._empty_baseline(store)
        v1_bundle_metrics, v1_bundle, v1_ready_refs = _measure_bundle(
            scenario="t4_v1_preview_bundle",
            before=empty_baseline,
            current=v1_bound,
            store=store,
        )
        v2_bundle_metrics, _v2_bundle, v2_ready_refs = _measure_bundle(
            scenario="t4_v2_preview_bundle",
            before=repository_baseline,
            current=v2_bound,
            store=store,
        )
        result["segments"].append(
            {
                "scenario": "t4_preview_bundle_assembly",
                "v1": v1_bundle_metrics,
                "v2": v2_bundle_metrics,
                "package_materialization": {
                    "v1_table_count": v1_bound.summary.table_count,
                    "v1_row_count_total": v1_bound.summary.row_count_total,
                    "v1_stages": v1_recorder.stages,
                    "v2_table_count": v2_bound.summary.table_count,
                    "v2_row_count_total": v2_bound.summary.row_count_total,
                    "v2_stages": v2_recorder.stages,
                },
            }
        )
        checkpoint("RUNNING")

        (
            submit_inputs,
            _,
            canonical_refs,
            removed_tables,
            canonical_closure_ref,
        ) = _measure_submit_build_inputs(
            store=store,
            current=v2_bound,
            manifest_ref=v2_manifest_ref,
            manifest_digest=v2_manifest_digest,
            ready_refs=v2_ready_refs,
            repository_id=repository_id,
            parent_commit_id=baseline_commit_id,
            bearer_token=bearer_token,
            base_url=repository_service_url,
        )
        result["segments"].append(
            {
                "scenario": "t4_submit_prepare_build_input_resolution",
                **submit_inputs,
            }
        )
        checkpoint("RUNNING")

        db_path = scratch_path / "checkpoint-pinning.sqlite3"
        checkpoint_metrics = _measure_checkpoints_and_pins(
            store=store,
            db_path=db_path,
            v1_bundle=v1_bundle,
            v1_ready_refs=v1_ready_refs,
            v1_manifest_digest=v1_manifest_digest,
            v2_ready_refs=v2_ready_refs,
            v2_manifest_ref=v2_manifest_ref,
            v2_manifest_digest=v2_manifest_digest,
            parent_commit_id=baseline_commit_id,
            canonical_closure_ref=canonical_closure_ref,
            removed_tables=removed_tables,
            canonical_refs=canonical_refs,
        )
        result["segments"].append(
            {
                "scenario": "preview_and_submit_checkpoint_serialization_and_pin",
                **checkpoint_metrics,
            }
        )
        checkpoint("PASS")
        return result
    except BaseException as error:
        checkpoint("FAILED", type(error).__name__)
        raise


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--real-dump-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--scratch", type=Path, required=True)
    parser.add_argument("--repository-id", required=True)
    parser.add_argument("--baseline-commit", required=True)
    parser.add_argument("--bearer-token-file", type=Path, required=True)
    parser.add_argument("--repository-service-url", default="http://127.0.0.1:8000")
    args = parser.parse_args(argv)
    result = run(
        real_dump_root=args.real_dump_root.resolve(),
        output_path=args.output,
        scratch_path=args.scratch,
        repository_id=args.repository_id,
        baseline_commit_id=args.baseline_commit,
        bearer_token_file=args.bearer_token_file,
        repository_service_url=args.repository_service_url,
    )
    print(
        json.dumps(
            {
                "event": "v5b_segments_complete",
                "status": result["status"],
                "segment_count": len(result["segments"]),
                "output": str(args.output),
            },
            sort_keys=True,
        ),
        flush=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
