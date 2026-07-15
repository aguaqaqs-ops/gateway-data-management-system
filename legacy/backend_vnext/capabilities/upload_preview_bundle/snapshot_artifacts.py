from __future__ import annotations

from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, replace
import os
from pathlib import Path, PurePosixPath
from time import perf_counter

import polars as pl

from ...core.digests import DigestRef
from ...core.scalar_encoding import parquet_scalar_value_normalizer
from ...formal_upload_benchmark import benchmark_elapsed_ms
from ..snapshot_materialization import SnapshotTable, SnapshotTableDescriptor, SnapshotTableSet
from ..surface_assembly import ComparisonSurface, SurfaceTableRefs
from .artifacts import bundle_artifact_path
from .assembler import BundleArtifact


@dataclass(frozen=True)
class PreviewSnapshotArtifacts:
    artifacts: tuple[BundleArtifact, ...]
    table_count: int
    row_count: int
    logical_table_count: int
    export_task_count: int
    deduped_table_count: int
    logical_row_count: int
    exported_row_count: int
    deduped_row_count: int
    snapshot_ref_reuse_count: int
    size_bytes: int
    worker_count: int
    parallel_enabled: bool
    export_strategy: str
    worker_config: str | None
    worker_config_invalid: bool
    top_slow_tables: tuple[dict[str, object], ...]
    cache_dry_run_enabled: bool
    exact_cache_eligible_table_count: int
    exact_cache_ineligible_table_count: int
    exact_cache_miss_reasons: dict[str, int]
    fast_candidate_eligible_table_count: int
    fast_candidate_ineligible_table_count: int
    fast_candidate_miss_reasons: dict[str, int]
    fast_candidate_key_reuse_count: int
    fast_candidate_reused_row_count: int
    fast_candidate_reused_size_bytes: int
    top_fast_candidate_reuse_groups: tuple[dict[str, object], ...]
    fast_snapshot_ref_dedupe_count: int
    fast_snapshot_ref_deduped_row_count: int
    fast_snapshot_ref_deduped_estimated_size_bytes: int
    fast_snapshot_ref_dedupe_groups: tuple[dict[str, object], ...]


@dataclass(frozen=True)
class PreviewSnapshotFastRefDedupe:
    surface: ComparisonSurface
    dedupe_count: int
    deduped_row_count: int
    groups: tuple[dict[str, object], ...]


@dataclass(frozen=True)
class _PreviewSnapshotExportTask:
    order_index: int
    table_name: str
    ref: str
    path: Path
    table: SnapshotTable


@dataclass(frozen=True)
class _PreviewSnapshotExportResult:
    order_index: int
    table_name: str
    ref: str
    path: Path
    row_count: int
    size_bytes: int
    duration_ms: int


@dataclass(frozen=True)
class _PreviewSnapshotExportWorkerStrategy:
    worker_count: int
    parallel_enabled: bool
    export_strategy: str
    worker_config: str | None
    worker_config_invalid: bool


@dataclass(frozen=True)
class _PreviewSnapshotCacheDryRun:
    exact_cache_eligible_table_count: int
    exact_cache_ineligible_table_count: int
    exact_cache_miss_reasons: dict[str, int]
    fast_candidate_eligible_table_count: int
    fast_candidate_ineligible_table_count: int
    fast_candidate_miss_reasons: dict[str, int]
    fast_candidate_key_reuse_count: int
    fast_candidate_reused_row_count: int
    fast_candidate_reused_size_bytes: int
    top_fast_candidate_reuse_groups: tuple[dict[str, object], ...]


def visible_preview_table_aliases(
    table_aliases: tuple[dict[str, object], ...],
    *,
    view_id: str,
    visible_table_names: set[str],
) -> tuple[dict[str, object], ...]:
    """Keep only aliases whose display endpoints are present in the preview view."""

    return tuple(
        dict(alias)
        for alias in table_aliases
        if alias.get("pair_id") in {None, view_id}
        and alias.get("logical_table_name") in visible_table_names
        and alias.get("canonical_table_name") in visible_table_names
    )


def with_preview_snapshot_table_refs(
    surface: ComparisonSurface,
    *,
    before_table_set: SnapshotTableSet,
    current_table_set: SnapshotTableSet,
    table_aliases: tuple[dict[str, object], ...] = (),
) -> ComparisonSurface:
    """Bind upload-preview table refs to real bundle-local snapshot artifacts."""

    alias_targets = _preview_snapshot_alias_targets(table_aliases)
    rewritten_tables = []
    for table in surface.tables:
        table_name = table.table_name
        current_table_name = _preview_snapshot_ref_source_table_name(
            side="current",
            table_name=table_name,
            alias_targets=alias_targets,
            table_set=current_table_set,
        )
        current_ref = (
            _preview_snapshot_table_ref("current", current_table_name)
            if current_table_name is not None
            else None
        )
        before_table_name = None
        if current_ref is None:
            before_table_name = _preview_snapshot_ref_source_table_name(
                side="before",
                table_name=table_name,
                alias_targets=alias_targets,
                table_set=before_table_set,
            )
        before_ref = (
            _preview_snapshot_table_ref("before", before_table_name)
            if before_table_name is not None
            else None
        )
        rewritten_tables.append(
            replace(
                table,
                table_refs=SurfaceTableRefs(
                    before_table_ref=before_ref,
                    current_table_ref=current_ref,
                    browse_table_ref=current_ref or before_ref,
                ),
            )
        )
    return replace(surface, tables=tuple(rewritten_tables))


def with_preview_snapshot_fast_candidate_refs(
    surface: ComparisonSurface,
    *,
    before_table_set: SnapshotTableSet,
    current_table_set: SnapshotTableSet,
) -> PreviewSnapshotFastRefDedupe:
    """Reuse bundle-local snapshot refs for same-side fast candidate duplicate tables."""

    canonical_by_side_and_key: dict[tuple[str, str], tuple[str, str, SnapshotTable]] = {}
    group_members: dict[tuple[str, str], list[dict[str, object]]] = {}
    rewritten_tables = []
    dedupe_count = 0
    deduped_row_count = 0
    for table in surface.tables:
        side, ref, snapshot_table = _preview_snapshot_selected_table(
            table,
            before_table_set=before_table_set,
            current_table_set=current_table_set,
        )
        if side is None or ref is None or snapshot_table is None:
            rewritten_tables.append(table)
            continue
        fast_key = _preview_snapshot_fast_candidate_key(snapshot_table.descriptor)
        if fast_key is None:
            rewritten_tables.append(table)
            continue
        group_key = (side, fast_key)
        existing = canonical_by_side_and_key.get(group_key)
        if existing is None:
            canonical_by_side_and_key[group_key] = (table.table_name, ref, snapshot_table)
            group_members[group_key] = [
                {
                    "table_name": table.table_name,
                    "ref": ref,
                    "row_count": snapshot_table.descriptor.row_count,
                    "canonical": True,
                }
            ]
            rewritten_tables.append(table)
            continue
        canonical_table_name, canonical_ref, _canonical_table = existing
        if ref == canonical_ref:
            rewritten_tables.append(table)
            continue
        dedupe_count += 1
        deduped_row_count += snapshot_table.descriptor.row_count
        group_members[group_key].append(
            {
                "table_name": table.table_name,
                "ref": ref,
                "row_count": snapshot_table.descriptor.row_count,
                "canonical": False,
            }
        )
        rewritten_tables.append(
            replace(
                table,
                table_refs=_replace_preview_snapshot_selected_ref(
                    table.table_refs,
                    side=side,
                    canonical_ref=canonical_ref,
                ),
            )
        )

    groups = []
    for (side, fast_key), members in group_members.items():
        if len(members) < 2:
            continue
        canonical_member = members[0]
        reused_members = members[1:]
        groups.append(
            {
                "side": side,
                "key_digest": fast_key,
                "canonical_table_name": canonical_member["table_name"],
                "canonical_ref": canonical_member["ref"],
                "table_names": [member["table_name"] for member in members],
                "refs": [member["ref"] for member in members],
                "table_count": len(members),
                "deduped_table_count": len(reused_members),
                "row_count": sum(int(member["row_count"]) for member in members),
                "deduped_row_count": sum(int(member["row_count"]) for member in reused_members),
            }
        )
    ordered_groups = tuple(
        sorted(
            groups,
            key=lambda group: (
                int(group["deduped_row_count"]),
                int(group["deduped_table_count"]),
                str(group["key_digest"]),
            ),
            reverse=True,
        )
    )
    return PreviewSnapshotFastRefDedupe(
        surface=replace(surface, tables=tuple(rewritten_tables)),
        dedupe_count=dedupe_count,
        deduped_row_count=deduped_row_count,
        groups=ordered_groups,
    )


def preview_snapshot_table_artifacts(
    *,
    surface: ComparisonSurface,
    before_table_set: SnapshotTableSet,
    current_table_set: SnapshotTableSet,
    bundle_root: Path,
    fast_ref_dedupe: PreviewSnapshotFastRefDedupe | None = None,
) -> PreviewSnapshotArtifacts:
    """Write only the surface-selected snapshot side directly into the bundle."""

    tasks: list[_PreviewSnapshotExportTask] = []
    exported_refs: set[str] = set()
    logical_table_count = 0
    logical_row_count = 0
    for order_index, table in enumerate(surface.tables):
        _side, ref, snapshot_table = _preview_snapshot_selected_table(
            table,
            before_table_set=before_table_set,
            current_table_set=current_table_set,
        )
        if ref is None or snapshot_table is None:
            continue
        logical_table_count += 1
        logical_row_count += snapshot_table.descriptor.row_count
        if ref in exported_refs:
            continue
        exported_refs.add(ref)
        path = bundle_artifact_path(bundle_root, ref)
        tasks.append(
            _PreviewSnapshotExportTask(
                order_index=order_index,
                table_name=snapshot_table.descriptor.table_name,
                ref=ref,
                path=path,
                table=snapshot_table,
            )
        )
    exported_row_count = sum(task.table.descriptor.row_count for task in tasks)
    strategy = _preview_snapshot_export_worker_strategy(
        table_count=len(tasks),
        row_count=exported_row_count,
    )
    results = _run_preview_snapshot_export_tasks(tasks, strategy=strategy)
    cache_dry_run = _preview_snapshot_cache_dry_run(tasks, results)
    artifacts = [BundleArtifact.file(result.ref, result.path) for result in results]
    size_bytes = sum(result.size_bytes for result in results)
    deduped_table_count = logical_table_count - len(results)
    deduped_row_count = logical_row_count - exported_row_count
    fast_ref_dedupe_count = 0 if fast_ref_dedupe is None else fast_ref_dedupe.dedupe_count
    fast_ref_deduped_row_count = (
        0 if fast_ref_dedupe is None else fast_ref_dedupe.deduped_row_count
    )
    fast_ref_dedupe_groups = tuple() if fast_ref_dedupe is None else fast_ref_dedupe.groups
    fast_ref_deduped_estimated_size_bytes = _estimated_snapshot_deduped_size_bytes(
        groups=fast_ref_dedupe_groups,
        results=results,
    )
    return PreviewSnapshotArtifacts(
        artifacts=tuple(artifacts),
        table_count=logical_table_count,
        row_count=logical_row_count,
        logical_table_count=logical_table_count,
        export_task_count=len(results),
        deduped_table_count=deduped_table_count,
        logical_row_count=logical_row_count,
        exported_row_count=exported_row_count,
        deduped_row_count=deduped_row_count,
        snapshot_ref_reuse_count=deduped_table_count,
        size_bytes=size_bytes,
        worker_count=strategy.worker_count,
        parallel_enabled=strategy.parallel_enabled,
        export_strategy=strategy.export_strategy,
        worker_config=strategy.worker_config,
        worker_config_invalid=strategy.worker_config_invalid,
        top_slow_tables=_preview_snapshot_top_slow_tables(results),
        cache_dry_run_enabled=True,
        exact_cache_eligible_table_count=cache_dry_run.exact_cache_eligible_table_count,
        exact_cache_ineligible_table_count=cache_dry_run.exact_cache_ineligible_table_count,
        exact_cache_miss_reasons=cache_dry_run.exact_cache_miss_reasons,
        fast_candidate_eligible_table_count=cache_dry_run.fast_candidate_eligible_table_count,
        fast_candidate_ineligible_table_count=cache_dry_run.fast_candidate_ineligible_table_count,
        fast_candidate_miss_reasons=cache_dry_run.fast_candidate_miss_reasons,
        fast_candidate_key_reuse_count=cache_dry_run.fast_candidate_key_reuse_count,
        fast_candidate_reused_row_count=cache_dry_run.fast_candidate_reused_row_count,
        fast_candidate_reused_size_bytes=cache_dry_run.fast_candidate_reused_size_bytes,
        top_fast_candidate_reuse_groups=cache_dry_run.top_fast_candidate_reuse_groups,
        fast_snapshot_ref_dedupe_count=fast_ref_dedupe_count,
        fast_snapshot_ref_deduped_row_count=fast_ref_deduped_row_count,
        fast_snapshot_ref_deduped_estimated_size_bytes=fast_ref_deduped_estimated_size_bytes,
        fast_snapshot_ref_dedupe_groups=fast_ref_dedupe_groups,
    )


def _preview_snapshot_alias_targets(
    table_aliases: tuple[dict[str, object], ...],
) -> dict[str, str]:
    targets: dict[str, str] = {}
    for alias in table_aliases:
        logical_table_name = alias.get("logical_table_name")
        canonical_table_name = alias.get("canonical_table_name")
        if not isinstance(logical_table_name, str) or not logical_table_name:
            continue
        if not isinstance(canonical_table_name, str) or not canonical_table_name:
            continue
        targets[logical_table_name] = canonical_table_name
    return targets


def _preview_snapshot_ref_source_table_name(
    *,
    side: str,
    table_name: str,
    alias_targets: dict[str, str],
    table_set: SnapshotTableSet,
) -> str | None:
    if table_name not in table_set.tables:
        return None
    canonical_table_name = alias_targets.get(table_name)
    if canonical_table_name is not None and canonical_table_name in table_set.tables:
        return canonical_table_name
    return table_name


def _preview_snapshot_selected_table(
    table,
    *,
    before_table_set: SnapshotTableSet,
    current_table_set: SnapshotTableSet,
) -> tuple[str | None, str | None, SnapshotTable | None]:
    current_ref = table.table_refs.current_table_ref
    if current_ref is not None:
        current_table = _preview_snapshot_table_for_ref(current_table_set, current_ref)
        if current_table is not None:
            return "current", current_ref, current_table
    before_ref = table.table_refs.before_table_ref
    if before_ref is not None:
        before_table = _preview_snapshot_table_for_ref(before_table_set, before_ref)
        if before_table is not None:
            return "before", before_ref, before_table
    return None, None, None


def _replace_preview_snapshot_selected_ref(
    table_refs: SurfaceTableRefs,
    *,
    side: str,
    canonical_ref: str,
) -> SurfaceTableRefs:
    if side == "current":
        return replace(table_refs, current_table_ref=canonical_ref, browse_table_ref=canonical_ref)
    if side == "before":
        return replace(table_refs, before_table_ref=canonical_ref, browse_table_ref=canonical_ref)
    raise ValueError("snapshot table side must be before or current")


def _preview_snapshot_table_for_ref(
    table_set: SnapshotTableSet,
    ref: str,
) -> SnapshotTable | None:
    table_name = _preview_snapshot_ref_table_name(ref)
    if table_name is None:
        return None
    return table_set.tables.get(table_name)


_SNAPSHOT_EXPORT_WORKERS_ENV = "BACKEND_VNEXT_UPLOAD_PREVIEW_SNAPSHOT_EXPORT_WORKERS"
_SNAPSHOT_EXPORT_DEFAULT_MAX_WORKERS = 1
_SNAPSHOT_EXPORT_PARALLEL_MIN_TABLES = 8
_SNAPSHOT_EXPORT_PARALLEL_MIN_ROWS = 20_000
_SNAPSHOT_EXPORT_ALLOWED_FORCED_WORKERS = {1, 2, 4}
_SNAPSHOT_PARQUET_WRITER_CONTRACT_VERSION = "backend-vnext/upload-preview-snapshot-parquet/v1"


def _preview_snapshot_export_worker_strategy(
    *,
    table_count: int,
    row_count: int,
) -> _PreviewSnapshotExportWorkerStrategy:
    raw_config = os.getenv(_SNAPSHOT_EXPORT_WORKERS_ENV)
    worker_config = raw_config.strip() if raw_config is not None else None
    if table_count <= 0:
        return _PreviewSnapshotExportWorkerStrategy(
            worker_count=0,
            parallel_enabled=False,
            export_strategy="serial",
            worker_config=worker_config or None,
            worker_config_invalid=False,
        )
    if worker_config:
        try:
            forced_workers = int(worker_config)
        except ValueError:
            forced_workers = 0
        if forced_workers in _SNAPSHOT_EXPORT_ALLOWED_FORCED_WORKERS:
            return _PreviewSnapshotExportWorkerStrategy(
                worker_count=forced_workers,
                parallel_enabled=forced_workers > 1,
                export_strategy="forced_parallel" if forced_workers > 1 else "serial",
                worker_config=worker_config,
                worker_config_invalid=False,
            )
        adaptive_workers = _adaptive_preview_snapshot_export_workers(
            table_count=table_count,
            row_count=row_count,
        )
        return _PreviewSnapshotExportWorkerStrategy(
            worker_count=adaptive_workers,
            parallel_enabled=adaptive_workers > 1,
            export_strategy="adaptive_parallel" if adaptive_workers > 1 else "serial",
            worker_config=worker_config,
            worker_config_invalid=True,
        )
    adaptive_workers = _adaptive_preview_snapshot_export_workers(
        table_count=table_count,
        row_count=row_count,
    )
    return _PreviewSnapshotExportWorkerStrategy(
        worker_count=adaptive_workers,
        parallel_enabled=adaptive_workers > 1,
        export_strategy="adaptive_parallel" if adaptive_workers > 1 else "serial",
        worker_config=None,
        worker_config_invalid=False,
    )


def _adaptive_preview_snapshot_export_workers(*, table_count: int, row_count: int) -> int:
    if table_count < _SNAPSHOT_EXPORT_PARALLEL_MIN_TABLES:
        return 1
    if row_count < _SNAPSHOT_EXPORT_PARALLEL_MIN_ROWS:
        return 1
    return max(1, min(_SNAPSHOT_EXPORT_DEFAULT_MAX_WORKERS, os.cpu_count() or 1))


def _run_preview_snapshot_export_tasks(
    tasks: list[_PreviewSnapshotExportTask],
    *,
    strategy: _PreviewSnapshotExportWorkerStrategy,
) -> tuple[_PreviewSnapshotExportResult, ...]:
    if not tasks:
        return ()
    if strategy.worker_count <= 1:
        results = [_write_preview_snapshot_export_task(task) for task in tasks]
        return tuple(sorted(results, key=lambda result: result.order_index))
    results: list[_PreviewSnapshotExportResult] = []
    with ThreadPoolExecutor(max_workers=strategy.worker_count) as executor:
        futures = [executor.submit(_write_preview_snapshot_export_task, task) for task in tasks]
        for future in as_completed(futures):
            results.append(future.result())
    return tuple(sorted(results, key=lambda result: result.order_index))


def _write_preview_snapshot_export_task(
    task: _PreviewSnapshotExportTask,
) -> _PreviewSnapshotExportResult:
    started_at = perf_counter()
    _write_snapshot_table_parquet(task.path, task.table)
    return _PreviewSnapshotExportResult(
        order_index=task.order_index,
        table_name=task.table_name,
        ref=task.ref,
        path=task.path,
        row_count=task.table.descriptor.row_count,
        size_bytes=task.path.stat().st_size,
        duration_ms=benchmark_elapsed_ms(started_at),
    )


def _preview_snapshot_top_slow_tables(
    results: tuple[_PreviewSnapshotExportResult, ...],
    *,
    limit: int = 10,
) -> tuple[dict[str, object], ...]:
    return tuple(
        {
            "table_name": result.table_name,
            "row_count": result.row_count,
            "size_bytes": result.size_bytes,
            "duration_ms": result.duration_ms,
        }
        for result in sorted(
            results,
            key=lambda result: (result.duration_ms, result.row_count, result.table_name),
            reverse=True,
        )[:limit]
    )


def _estimated_snapshot_deduped_size_bytes(
    *,
    groups: tuple[dict[str, object], ...],
    results: tuple[_PreviewSnapshotExportResult, ...],
) -> int:
    result_by_ref = {result.ref: result for result in results}
    total = 0
    for group in groups:
        canonical_ref = group.get("canonical_ref")
        canonical_result = result_by_ref.get(canonical_ref) if isinstance(canonical_ref, str) else None
        if canonical_result is None or canonical_result.row_count <= 0:
            continue
        total += round(
            canonical_result.size_bytes
            * int(group.get("deduped_row_count") or 0)
            / canonical_result.row_count
        )
    return int(total)


def _preview_snapshot_cache_dry_run(
    tasks: list[_PreviewSnapshotExportTask],
    results: tuple[_PreviewSnapshotExportResult, ...],
    *,
    top_group_limit: int = 10,
) -> _PreviewSnapshotCacheDryRun:
    exact_miss_reasons: Counter[str] = Counter()
    fast_miss_reasons: Counter[str] = Counter()
    exact_eligible = 0
    exact_ineligible = 0
    fast_eligible = 0
    fast_ineligible = 0
    fast_groups: dict[tuple[str, str], list[_PreviewSnapshotExportTask]] = {}

    for task in tasks:
        descriptor = task.table.descriptor
        if descriptor.row_layout_digest is None:
            exact_ineligible += 1
            exact_miss_reasons["missing_row_layout_digest"] += 1
        else:
            exact_eligible += 1
            exact_miss_reasons["cache_store_not_configured"] += 1

        fast_key = _preview_snapshot_fast_candidate_key(descriptor)
        if fast_key is None:
            fast_ineligible += 1
            fast_miss_reasons["missing_fast_row_digest"] += 1
        else:
            side = _preview_snapshot_ref_side(task.ref)
            if side is None:
                fast_ineligible += 1
                fast_miss_reasons["invalid_snapshot_ref_side"] += 1
                continue
            fast_eligible += 1
            fast_groups.setdefault((side, fast_key), []).append(task)

    result_by_ref = {result.ref: result for result in results}
    reuse_group_payloads: list[dict[str, object]] = []
    fast_reuse_count = 0
    fast_reused_row_count = 0
    fast_reused_size_bytes = 0
    for (side, fast_key), group in fast_groups.items():
        ordered_group = sorted(group, key=lambda task: task.order_index)
        if len(ordered_group) == 1:
            fast_miss_reasons["unique_fast_candidate_key"] += 1
            continue
        reused_tasks = ordered_group[1:]
        reused_results = [result_by_ref[task.ref] for task in reused_tasks if task.ref in result_by_ref]
        group_results = [result_by_ref[task.ref] for task in ordered_group if task.ref in result_by_ref]
        reused_row_count = sum(task.table.descriptor.row_count for task in reused_tasks)
        reused_size_bytes = sum(result.size_bytes for result in reused_results)
        saved_duration_ms = sum(result.duration_ms for result in reused_results)
        fast_reuse_count += len(reused_tasks)
        fast_reused_row_count += reused_row_count
        fast_reused_size_bytes += reused_size_bytes
        reuse_group_payloads.append(
            {
                "key_digest": fast_key,
                "side": side,
                "table_names": [task.table_name for task in ordered_group],
                "refs": [task.ref for task in ordered_group],
                "table_count": len(ordered_group),
                "reused_table_count": len(reused_tasks),
                "row_count": sum(task.table.descriptor.row_count for task in ordered_group),
                "reused_row_count": reused_row_count,
                "size_bytes": sum(result.size_bytes for result in group_results),
                "reused_size_bytes": reused_size_bytes,
                "potential_saved_duration_ms": saved_duration_ms,
            }
        )

    top_groups = tuple(
        sorted(
            reuse_group_payloads,
            key=lambda group: (
                int(group["potential_saved_duration_ms"]),
                int(group["reused_row_count"]),
                str(group["key_digest"]),
            ),
            reverse=True,
        )[:top_group_limit]
    )
    return _PreviewSnapshotCacheDryRun(
        exact_cache_eligible_table_count=exact_eligible,
        exact_cache_ineligible_table_count=exact_ineligible,
        exact_cache_miss_reasons=dict(sorted(exact_miss_reasons.items())),
        fast_candidate_eligible_table_count=fast_eligible,
        fast_candidate_ineligible_table_count=fast_ineligible,
        fast_candidate_miss_reasons=dict(sorted(fast_miss_reasons.items())),
        fast_candidate_key_reuse_count=fast_reuse_count,
        fast_candidate_reused_row_count=fast_reused_row_count,
        fast_candidate_reused_size_bytes=fast_reused_size_bytes,
        top_fast_candidate_reuse_groups=top_groups,
    )


def _preview_snapshot_fast_candidate_key(descriptor: SnapshotTableDescriptor) -> str | None:
    if descriptor.fast_row_digest is None:
        return None
    return DigestRef.from_payload(
        {
            "cache_key_kind": "upload_preview_snapshot_parquet_fast_candidate",
            "fast_row_digest": descriptor.fast_row_digest.to_payload(),
            "columns": [
                {
                    "name": column.name,
                    "scalar_type": column.scalar_type,
                    "nullable": column.nullable,
                }
                for column in descriptor.columns
            ],
            "row_count": descriptor.row_count,
            "row_materialization_profile": descriptor.row_materialization_profile,
            "scalar_encoding_version": descriptor.scalar_encoding_version,
            "parquet_writer_contract_version": _SNAPSHOT_PARQUET_WRITER_CONTRACT_VERSION,
        }
    ).to_payload()


def _preview_snapshot_table_ref(side: str, table_name: str) -> str:
    if side not in {"before", "current"}:
        raise ValueError("snapshot table side must be before or current")
    return f"tables/{side}/{table_name}.parquet"


def _preview_snapshot_ref_table_name(ref: str) -> str | None:
    path = PurePosixPath(ref)
    if path.suffix != ".parquet":
        return None
    parts = path.parts
    if len(parts) == 5 and parts[0] == "pairs" and parts[2] == "tables":
        parts = parts[2:]
    if len(parts) != 3 or parts[0] != "tables" or parts[1] not in {"before", "current"}:
        return None
    table_name = path.stem
    return table_name or None


def _preview_snapshot_ref_side(ref: str) -> str | None:
    path = PurePosixPath(ref)
    parts = path.parts
    if len(parts) == 5 and parts[0] == "pairs" and parts[2] == "tables":
        parts = parts[2:]
    if len(parts) != 3 or parts[0] != "tables" or parts[1] not in {"before", "current"}:
        return None
    return parts[1]


def _write_snapshot_table_parquet(path: Path, table: SnapshotTable) -> None:
    columns = table.descriptor.columns
    column_names = [column.name for column in columns]
    column_values: list[list[object]] = [[] for _ in columns]
    normalizers = [parquet_scalar_value_normalizer(column.scalar_type) for column in columns]
    for row in table.reader.iter_rows():
        for value, values, normalize_value in zip(row, column_values, normalizers):
            values.append(normalize_value(value))
    columns_by_name = dict(zip(column_names, column_values))
    if any(columns_by_name.values()):
        frame = pl.DataFrame(columns_by_name, strict=False).select(column_names)
    else:
        frame = pl.DataFrame(schema={column.name: pl.Null for column in columns})
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = path.with_name(f"{path.name}.tmp")
    frame.write_parquet(temporary_path)
    temporary_path.replace(path)


__all__ = [
    "PreviewSnapshotArtifacts",
    "PreviewSnapshotFastRefDedupe",
    "preview_snapshot_table_artifacts",
    "visible_preview_table_aliases",
    "with_preview_snapshot_fast_candidate_refs",
    "with_preview_snapshot_table_refs",
]
