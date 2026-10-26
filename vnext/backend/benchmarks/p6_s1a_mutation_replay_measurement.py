"""Measure S1a mutation replay paths against an isolated t4 Repository parent.

The runner writes only table names, counts, timings, branch labels, and hash equality
facts. Replay SQL is piped into the Repository Service container and is never saved.
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import socket
import statistics
import subprocess
import sys
import time
import uuid
from collections import Counter
from dataclasses import replace
from pathlib import Path
from typing import Any, Sequence

import s5_dc32_capability_measurement as s5
import s5_v5b_segment_measurement as v5b
from gateway_shared_kernel import DigestRef
from gateway_shared_kernel import raw_blob_digest

_BACKEND_ROOT = Path(__file__).resolve().parents[1]
_REPO_ROOT = _BACKEND_ROOT.parents[1]
if str(_BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT))

from gateway_backend.capabilities.mutation_planning import (  # noqa: E402
    MutationPolicy,
    MutationTableSnapshot,
    RowMutationOperation,
    TableMutationKind,
    plan_import_mutation,
    render_planned_import_mutation_dml,
)
from gateway_backend.capabilities.mutation_planning._digest import (  # noqa: E402
    key_bytes_for_ordering,
    row_digest_from_image,
)
from gateway_backend.capabilities.mutation_planning.contracts import (  # noqa: E402
    CanonicalStorageKey,
    MutationKeyedRow,
    PersistedRowImage,
)
from gateway_backend.capabilities.snapshot_materialization import (  # noqa: E402
    open_snapshot_table_artifact,
)
from gateway_backend.capabilities.storage_projection import (  # noqa: E402
    CanonicalizationManifest,
    CanonicalizationManifestTable,
)
from gateway_backend.capabilities.storage_projection._digest import (  # noqa: E402
    compute_manifest_digest,
)
from gateway_backend.capabilities.storage_projection.contracts import (  # noqa: E402
    PACKAGE_VERSION,
    ProjectionResult,
    ProjectionStatus,
    RepositoryImportArtifactInput,
    RepositoryImportColumn,
    RepositoryImportTable,
)
from gateway_backend.capabilities.storage_projection.import_replay import (  # noqa: E402
    render_repository_import_schema_replay_sql,
)
from gateway_backend.capabilities.storage_projection.package import (  # noqa: E402
    canonicalization_manifest_from_bytes,
)
from gateway_backend.capabilities.table_rules import (  # noqa: E402
    migrated_table_ruleset_snapshot,
)
from gateway_backend.capabilities.table_rules.contracts import (  # noqa: E402
    OrderedPolicy,
)
from gateway_backend.infrastructure.repository_write.import_publication import (  # noqa: E402
    _changed_table_names,
    _keyed_rows_from_frozen_artifact,
)

_INSERT_ROW_LIMIT = 256
_INSERT_BYTE_LIMIT = 4 * 1024 * 1024


def _manifest_from_ref(store: Any, ref: Any) -> CanonicalizationManifest:
    manifest = canonicalization_manifest_from_bytes(store.locate(ref))
    if manifest.manifest_digest is None:
        raise RuntimeError("canonical manifest digest is missing")
    return manifest


def _bound_tables(bound: Any) -> dict[str, Any]:
    if bound.table_set is None:
        raise RuntimeError("canonical snapshot table set is missing")
    return {table.descriptor.table_name: table for table in bound.table_set.tables}


def _bound_views(bound: Any) -> dict[str, Any]:
    return {fact.storage_rule_view.canonical_table: fact.storage_rule_view for fact in bound.storage_facts}


def _mutation_snapshots(
    store: Any,
    bound: Any,
    manifest: CanonicalizationManifest,
    table_names: Sequence[str],
) -> tuple[MutationTableSnapshot, ...]:
    bound_by_name = _bound_tables(bound)
    views = _bound_views(bound)
    manifest_by_name = {item.name: item for item in manifest.tables}
    snapshots: list[MutationTableSnapshot] = []
    for name in sorted(set(table_names), key=lambda item: item.encode("utf-8")):
        table = bound_by_name.get(name)
        manifest_table = manifest_by_name.get(name)
        view = views.get(name)
        if table is None or table.artifact is None or manifest_table is None or view is None:
            raise RuntimeError("mutation snapshot binding is incomplete")
        opened = open_snapshot_table_artifact(store, table.artifact.manifest_ref)
        reader = opened.reader
        if reader is None:
            raise RuntimeError("canonical table artifact has no reader")
        try:
            rows = _keyed_rows_from_frozen_artifact(
                reader,
                descriptor=table.descriptor,
                manifest_table=manifest_table,
            )
        finally:
            reader.close()
        snapshots.append(
            MutationTableSnapshot(
                manifest_table=manifest_table,
                storage_view=view,
                rows=rows,
            )
        )
    return tuple(snapshots)


def _import_input(
    bound: Any,
    manifest: CanonicalizationManifest,
    table_names: Sequence[str],
) -> RepositoryImportArtifactInput:
    if manifest.manifest_digest is None:
        raise RuntimeError("canonical manifest digest is missing")
    tables = _bound_tables(bound)
    manifest_tables = {item.name: item for item in manifest.tables}
    import_tables: list[RepositoryImportTable] = []
    for name in sorted(set(table_names), key=lambda item: item.encode("utf-8")):
        table = tables.get(name)
        manifest_table = manifest_tables.get(name)
        if table is None or manifest_table is None:
            raise RuntimeError("RepositoryImport table binding is incomplete")
        descriptor = table.descriptor
        columns = tuple(
            RepositoryImportColumn(
                name=column.name,
                sql_type=column.scalar_type,
                nullable=column.nullable,
            )
            for column in descriptor.columns
        )
        import_tables.append(
            RepositoryImportTable(
                name=name,
                columns=columns,
                primary_key=descriptor.primary_key_columns,
                row_count=manifest_table.canonical_row_count,
            )
        )
    return RepositoryImportArtifactInput(
        package_version=PACKAGE_VERSION,
        canonicalization_manifest_digest=manifest.manifest_digest,
        tables=tuple(import_tables),
    )


def _projection_result(
    manifest: CanonicalizationManifest,
    import_input: RepositoryImportArtifactInput,
) -> ProjectionResult:
    return ProjectionResult(
        status=ProjectionStatus.COMPLETE,
        tables=(),
        omitted_diagnostic_count=0,
        manifest=manifest,
        import_input=import_input,
    )


def _empty_manifest(manifest: CanonicalizationManifest) -> CanonicalizationManifest:
    empty = replace(manifest, tables=(), manifest_digest=None)
    return replace(empty, manifest_digest=compute_manifest_digest(empty))


def _plan(
    *,
    after_manifest: CanonicalizationManifest,
    after_input: RepositoryImportArtifactInput,
    before_manifest: CanonicalizationManifest,
    before_snapshots: tuple[MutationTableSnapshot, ...],
    after_snapshots: tuple[MutationTableSnapshot, ...],
    repository_base_digest: DigestRef,
    policy: MutationPolicy,
) -> Any:
    result = plan_import_mutation(
        _projection_result(after_manifest, after_input),
        after_snapshots,
        repository_base_digest=repository_base_digest,
        before_manifest=before_manifest,
        before_snapshots=before_snapshots,
        mutation_policy=policy,
    )
    if result.plan is None or result.change_set_closure is None:
        raise RuntimeError("mutation planner did not produce a ready plan")
    return result


def _sql_for_plan(
    *,
    planned: Any,
    import_input: RepositoryImportArtifactInput,
    removed_tables: tuple[str, ...],
) -> tuple[bytes, tuple[str, ...]]:
    rebuild_tables = tuple(
        sorted(
            (
                summary.canonical_table
                for summary in planned.plan.table_summaries
                if summary.operation is TableMutationKind.REBUILD_TABLE
            ),
            key=lambda item: item.encode("utf-8"),
        )
    )
    rebuild_names = set(rebuild_tables)
    schema_input = replace(
        import_input,
        tables=tuple(table for table in import_input.tables if table.name in rebuild_names),
    )
    schema_sql = render_repository_import_schema_replay_sql(
        schema_input,
        removed_tables=removed_tables,
    )
    dml = render_planned_import_mutation_dml(planned, rebuild_tables=rebuild_tables)
    return schema_sql + dml, rebuild_tables


def _insert_statement_metrics(sql_bytes: bytes) -> dict[str, int]:
    statements: list[bytes] = []
    start = 0
    quote: int | None = None
    escaped = False
    for index, byte in enumerate(sql_bytes):
        if escaped:
            escaped = False
            continue
        if quote == ord("'") and byte == ord("\\"):
            escaped = True
            continue
        if quote is not None:
            if byte == quote:
                quote = None
            continue
        if byte in (ord("'"), ord("`")):
            quote = byte
        elif byte == ord(";"):
            statements.append(sql_bytes[start : index + 1].strip())
            start = index + 1
    if sql_bytes[start:].strip():
        statements.append(sql_bytes[start:].strip())

    row_counts: list[int] = []
    byte_counts: list[int] = []
    for statement in statements:
        if not statement.startswith(b"INSERT INTO "):
            continue
        marker = statement.find(b" VALUES ")
        if marker < 0:
            raise RuntimeError("rendered INSERT has no VALUES clause")
        values = statement[marker + len(b" VALUES ") :]
        depth = 0
        quote = None
        escaped = False
        row_count = 0
        for byte in values:
            if escaped:
                escaped = False
                continue
            if quote == ord("'") and byte == ord("\\"):
                escaped = True
                continue
            if quote is not None:
                if byte == quote:
                    quote = None
                continue
            if byte in (ord("'"), ord("`")):
                quote = byte
            elif byte == ord("("):
                if depth == 0:
                    row_count += 1
                depth += 1
            elif byte == ord(")"):
                depth -= 1
                if depth < 0:
                    raise RuntimeError("rendered INSERT has unbalanced parentheses")
        if depth != 0:
            raise RuntimeError("rendered INSERT has unbalanced parentheses")
        row_counts.append(row_count)
        byte_counts.append(len(statement))
    return {
        "insert_statement_count": len(row_counts),
        "insert_row_count": sum(row_counts),
        "max_insert_rows_per_statement": max(row_counts, default=0),
        "max_insert_statement_bytes": max(byte_counts, default=0),
    }


def _dolt_exec(
    *,
    container: str,
    repository_path: str,
    arguments: Sequence[str],
    stdin: bytes | None = None,
) -> bytes:
    command = ["docker", "exec"]
    if stdin is not None:
        command.append("-i")
    command.extend(("-w", repository_path, container, "/usr/local/bin/dolt", *arguments))
    result = subprocess.run(
        command,
        input=stdin,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
        timeout=3600,
    )
    if result.returncode != 0:
        raise RuntimeError(f"Dolt command failed in measurement phase ({result.returncode})")
    return result.stdout


def _read_hashes(
    *,
    container: str,
    repository_path: str,
    table_names: Sequence[str],
) -> dict[str, str]:
    queries = []
    for name in table_names:
        literal = "'" + name.replace("'", "''") + "'"
        queries.append(
            f"SELECT {literal} AS table_name, DOLT_HASHOF_TABLE({literal}) AS table_hash"
        )
    if not queries:
        return {}
    result = _dolt_exec(
        container=container,
        repository_path=repository_path,
        arguments=("sql", "--result-format=csv"),
        stdin=(" UNION ALL ".join(queries) + ";\n").encode("utf-8"),
    ).decode("utf-8")
    rows = csv.DictReader(io.StringIO(result))
    hashes = {
        row["table_name"]: row["table_hash"]
        for row in rows
        if row.get("table_name") and row.get("table_hash")
    }
    if set(hashes) != set(table_names):
        raise RuntimeError("Dolt did not return a hash for every requested table")
    return hashes


def _replay_branch(
    *,
    container: str,
    repository_path: str,
    base_commit: str,
    sql_bytes: bytes,
    table_names: Sequence[str],
    label: str,
) -> dict[str, Any]:
    branch = f"p6s1a-measure-{label}-{uuid.uuid4().hex[:8]}"
    _dolt_exec(
        container=container,
        repository_path=repository_path,
        arguments=("branch", branch, base_commit),
    )
    _dolt_exec(
        container=container,
        repository_path=repository_path,
        arguments=("checkout", branch),
    )
    replay_started = time.perf_counter()
    _dolt_exec(
        container=container,
        repository_path=repository_path,
        arguments=("sql", "--result-format=csv"),
        stdin=sql_bytes,
    )
    replay_seconds = time.perf_counter() - replay_started
    add_started = time.perf_counter()
    _dolt_exec(
        container=container,
        repository_path=repository_path,
        arguments=("add", "--all"),
    )
    add_seconds = time.perf_counter() - add_started
    commit_started = time.perf_counter()
    _dolt_exec(
        container=container,
        repository_path=repository_path,
        arguments=(
            "commit",
            "--allow-empty",
            "--message",
            "Phase 6 S1a replay measurement",
            "--author=Gateway Repository Service <repository@gateway.invalid>",
        ),
    )
    commit_seconds = time.perf_counter() - commit_started
    hashes = _read_hashes(
        container=container,
        repository_path=repository_path,
        table_names=table_names,
    )
    _dolt_exec(
        container=container,
        repository_path=repository_path,
        arguments=("checkout", "main"),
    )
    return {
        "branch": branch,
        "replay_seconds": round(replay_seconds, 6),
        "dolt_add_seconds": round(add_seconds, 6),
        "commit_seconds": round(commit_seconds, 6),
        "total_seconds": round(replay_seconds + add_seconds + commit_seconds, 6),
        "hashes": hashes,
    }


def _changed_row_count(
    before: MutationTableSnapshot,
    after: MutationTableSnapshot,
) -> int:
    before_by_key = {key_bytes_for_ordering(row.key): row for row in before.rows}
    after_by_key = {key_bytes_for_ordering(row.key): row for row in after.rows}
    inserted = after_by_key.keys() - before_by_key.keys()
    deleted = before_by_key.keys() - after_by_key.keys()
    updated = sum(
        before_by_key[key].row_digest != after_by_key[key].row_digest
        for key in before_by_key.keys() & after_by_key.keys()
    )
    return len(inserted) + len(deleted) + updated


def _synthetic_one_percent_target(
    before: MutationTableSnapshot,
    after: MutationTableSnapshot,
) -> tuple[MutationTableSnapshot, dict[str, int]]:
    current_changes = _changed_row_count(before, after)
    target_changes = int(max(len(before.rows), len(after.rows), 1) * 0.01)
    if target_changes <= current_changes:
        raise RuntimeError("t4 v2 sample already exceeds the one-percent target")
    before_by_key = {key_bytes_for_ordering(row.key): row for row in before.rows}
    changed_keys = {
        key_bytes_for_ordering(row.key)
        for row in after.rows
        if key_bytes_for_ordering(row.key) not in before_by_key
        or before_by_key[key_bytes_for_ordering(row.key)].row_digest != row.row_digest
    }
    candidates = [
        row
        for row in after.rows
        if key_bytes_for_ordering(row.key) not in changed_keys
    ]
    candidates.sort(key=lambda row: key_bytes_for_ordering(row.key))
    extra_changes = target_changes - current_changes
    if len(candidates) < extra_changes:
        raise RuntimeError("t4 v2 table has too few unchanged rows for one-percent sample")
    value_column = next(
        (
            name
            for name in after.manifest_table.structural_columns
            if name not in after.storage_view.canonical_key_columns
            and any(column == name for column, _cell in candidates[0].image.columns)
        ),
        None,
    )
    if value_column is None:
        value_column = next(
            (
                name
                for name, cell in candidates[0].image.columns
                if name not in after.storage_view.canonical_key_columns
                and cell.get("kind") in {"signed-integer", "unsigned-integer"}
            ),
            None,
        )
    if value_column is None:
        raise RuntimeError("ordered t4 v2 table has no mutable non-key integer column")

    candidate_keys = {
        key_bytes_for_ordering(row.key) for row in candidates[:extra_changes]
    }
    changed_rows: list[MutationKeyedRow] = []
    changed_row_keys: set[bytes] = set()
    for row in after.rows:
        key = key_bytes_for_ordering(row.key)
        if key not in candidate_keys:
            changed_rows.append(row)
            continue
        cells = dict(row.image.columns)
        cell = cells[value_column]
        if cell.get("kind") not in {"signed-integer", "unsigned-integer"}:
            raise RuntimeError("synthetic ordered value column is not an integer")
        value = int(str(cell["decimal"])) + 1_000_000
        cells[value_column] = {"kind": cell["kind"], "decimal": str(value)}
        image = PersistedRowImage(
            columns=tuple((name, cells[name]) for name, _old in row.image.columns)
        )
        changed_rows.append(
            MutationKeyedRow(
                key=row.key,
                image=image,
                row_digest=row_digest_from_image(
                    image,
                    retained_columns=after.manifest_table.retained_columns,
                ),
            )
        )
        changed_row_keys.add(key)
    changed_rows.sort(key=lambda row: (key_bytes_for_ordering(row.key), row.row_digest.value))
    synthetic = replace(after, rows=tuple(changed_rows))
    measured_changes = _changed_row_count(before, synthetic)
    if measured_changes != target_changes:
        raise RuntimeError("synthetic t4 target did not reach the one-percent row count")
    return synthetic, {
        "parent_row_count": len(before.rows),
        "target_row_count": len(synthetic.rows),
        "actual_t4_v2_changed_row_count": current_changes,
        "synthetic_changed_row_count": measured_changes,
        "synthetic_extra_changed_row_count": len(changed_row_keys),
    }


def _mutation_counts(planned: Any) -> dict[str, int]:
    counts = Counter(mutation.operation.value for mutation in planned.change_set_closure.mutations)
    return {
        "insert_rows": counts[RowMutationOperation.INSERT.value],
        "update_rows": counts[RowMutationOperation.UPDATE.value],
        "delete_rows": counts[RowMutationOperation.DELETE.value],
    }


def run(
    *,
    real_dump_root: Path,
    output_path: Path,
    scratch_path: Path,
    repository_id: str,
    baseline_commit: str,
    target_commit: str,
    bearer_token_file: Path,
    repository_service_url: str,
    repository_service_container: str,
) -> dict[str, Any]:
    output_path = output_path.resolve()
    scratch_path = scratch_path.resolve()
    if output_path.is_relative_to(_REPO_ROOT) or scratch_path.is_relative_to(_REPO_ROOT):
        raise ValueError("measurement output and scratch paths must be outside the worktree")
    if output_path.exists() or scratch_path.exists():
        raise ValueError("measurement output or scratch path already exists")
    if not real_dump_root.is_dir() or not bearer_token_file.is_file():
        raise ValueError("t4 inputs or Repository Service credentials are unavailable")
    scratch_path.mkdir(mode=0o700, parents=True, exist_ok=False)
    scratch_path.chmod(0o700)
    store = v5b.FileMeasurementArtifactStore(scratch_path / "artifacts")
    start_wall = time.perf_counter()
    started_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    head = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=_REPO_ROOT,
        check=True,
        capture_output=True,
        text=True,
        timeout=10,
    ).stdout.strip()
    output_path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    output_path.parent.chmod(0o700)
    try:
        bearer = bearer_token_file.read_text(encoding="utf-8").strip()
        if not bearer:
            raise ValueError("Repository Service bearer token is empty")
        dataset_index = s5._dataset_index(real_dump_root)
        v1_item = dataset_index.get("rd-t4-d-v1")
        v2_item = dataset_index.get("rd-t4-d-v2")
        if v1_item is None or v2_item is None:
            raise ValueError("t4 v1/v2 packages are unavailable")
        v1_package = s5._dataset_path(real_dump_root, v1_item).read_bytes()
        v2_package = s5._dataset_path(real_dump_root, v2_item).read_bytes()
        v1_bound, v1_manifest_ref, _v1_digest = s5._snapshot_package(
            dataset_id="rd-t4-d-v1",
            package=v1_package,
            store=store,
            recorder=s5.MeasurementRecorder("p6_s1a_v1_package"),
        )
        v2_bound, v2_manifest_ref, _v2_digest = s5._snapshot_package(
            dataset_id="rd-t4-d-v2",
            package=v2_package,
            store=store,
            recorder=s5.MeasurementRecorder("p6_s1a_v2_package"),
        )
        v1_manifest = _manifest_from_ref(store, v1_manifest_ref)
        v2_manifest = _manifest_from_ref(store, v2_manifest_ref)
        full_materialization, parent_bound, _reads = v5b._measure_repository_materialization(
            store=store,
            repository_id=repository_id,
            commit_id=baseline_commit,
            bearer_token=bearer,
            base_url=repository_service_url,
            canonical_source=v1_bound,
        )

        changed_names = _changed_table_names(
            v1_manifest,
            v2_manifest,
            parent_is_initial=False,
        )
        before_changed = _mutation_snapshots(
            store,
            parent_bound,
            v1_manifest,
            changed_names,
        )
        after_changed = _mutation_snapshots(
            store,
            v2_bound,
            v2_manifest,
            changed_names,
        )
        after_all = _mutation_snapshots(
            store,
            v2_bound,
            v2_manifest,
            tuple(table.name for table in v2_manifest.tables),
        )
        import_all = _import_input(
            v2_bound,
            v2_manifest,
            tuple(table.name for table in v2_manifest.tables),
        )
        projection = _projection_result(v2_manifest, import_all)
        parent_digest = v1_manifest.manifest_digest
        if parent_digest is None:
            raise RuntimeError("t4 v1 manifest digest is missing")
        adaptive = plan_import_mutation(
            projection,
            after_changed,
            repository_base_digest=parent_digest,
            before_manifest=v1_manifest,
            before_snapshots=before_changed,
            mutation_policy=MutationPolicy.ADAPTIVE_PATCH,
        )
        adaptive_sql, adaptive_rebuild_tables = _sql_for_plan(
            planned=adaptive,
            import_input=import_all,
            removed_tables=tuple(
                sorted(
                    {table.name for table in v1_manifest.tables}
                    - {table.name for table in v2_manifest.tables},
                    key=lambda item: item.encode("utf-8"),
                )
            ),
        )
        empty_parent = _empty_manifest(v1_manifest)
        full_rebuild = plan_import_mutation(
            projection,
            after_all,
            repository_base_digest=parent_digest,
            before_manifest=empty_parent,
            before_snapshots=(),
            mutation_policy=MutationPolicy.REBUILD_ALWAYS,
        )
        full_names = tuple(table.name for table in v2_manifest.tables)
        full_sql, full_rebuild_tables = _sql_for_plan(
            planned=full_rebuild,
            import_input=import_all,
            removed_tables=tuple(
                sorted(
                    {table.name for table in v1_manifest.tables}
                    - {table.name for table in v2_manifest.tables},
                    key=lambda item: item.encode("utf-8"),
                )
            ),
        )

        repository_key = uuid.UUID(repository_id).hex
        repository_path = f"/var/lib/gateway/repository/versioned/{repository_key}"
        current_ref = _dolt_exec(
            container=repository_service_container,
            repository_path=repository_path,
            arguments=("symbolic-ref", "--short", "HEAD"),
        ).decode("utf-8").strip()
        if current_ref != "main":
            raise RuntimeError("Repository Service main ref is not checked out")
        current_head = _dolt_exec(
            container=repository_service_container,
            repository_path=repository_path,
            arguments=("rev-parse", "main"),
        ).decode("utf-8").strip()
        if current_head != target_commit:
            raise RuntimeError("Repository Service main ref is not at t4 v2 target")
        target_names = tuple(table.name for table in v2_manifest.tables)
        actual_hashes = _read_hashes(
            container=repository_service_container,
            repository_path=repository_path,
            table_names=target_names,
        )
        adaptive_replay = _replay_branch(
            container=repository_service_container,
            repository_path=repository_path,
            base_commit=baseline_commit,
            sql_bytes=adaptive_sql,
            table_names=target_names,
            label="t4-v2-adaptive",
        )
        full_replay = _replay_branch(
            container=repository_service_container,
            repository_path=repository_path,
            base_commit=baseline_commit,
            sql_bytes=full_sql,
            table_names=target_names,
            label="t4-v2-full-rebuild",
        )
        adaptive_hash_equal = adaptive_replay.pop("hashes") == actual_hashes
        full_hash_equal = full_replay.pop("hashes") == actual_hashes
        if not adaptive_hash_equal or not full_hash_equal:
            raise RuntimeError("t4 v2 table hashes differ across replay paths")

        ordered_candidates = [
            snapshot
            for snapshot in after_changed
            if snapshot.storage_view.ordered_policy is OrderedPolicy.GID_NO_V1
            and len(snapshot.rows) >= 1000
        ]
        if not ordered_candidates:
            raise RuntimeError("t4 v2 has no large changed GID_NO_V1 table")
        sample_after = sorted(
            ordered_candidates,
            key=lambda item: item.manifest_table.name.encode("utf-8"),
        )[0]
        table_name = sample_after.manifest_table.name
        sample_before = next(
            item
            for item in before_changed
            if item.manifest_table.name == table_name
        )
        synthetic_after, synthetic_counts = _synthetic_one_percent_target(
            sample_before,
            sample_after,
        )
        sample_import = _import_input(v2_bound, v2_manifest, (table_name,))
        sample_projection = _projection_result(v2_manifest, sample_import)
        sample_adaptive = plan_import_mutation(
            sample_projection,
            (synthetic_after,),
            repository_base_digest=parent_digest,
            before_manifest=v1_manifest,
            before_snapshots=(sample_before,),
            mutation_policy=MutationPolicy.ADAPTIVE_PATCH,
        )
        sample_rebuild = plan_import_mutation(
            sample_projection,
            (synthetic_after,),
            repository_base_digest=parent_digest,
            before_manifest=v1_manifest,
            before_snapshots=(sample_before,),
            mutation_policy=MutationPolicy.REBUILD_ALWAYS,
        )
        if sample_adaptive.plan is None or sample_rebuild.plan is None:
            raise RuntimeError("one-percent mutation plans are incomplete")
        if sample_adaptive.plan.table_summaries[0].operation is not TableMutationKind.PATCH_DML:
            raise RuntimeError("one-percent sample did not select PATCH_DML")
        sample_adaptive_sql, _sample_patch_rebuilds = _sql_for_plan(
            planned=sample_adaptive,
            import_input=sample_import,
            removed_tables=(),
        )
        sample_rebuild_sql, _sample_rebuild_tables = _sql_for_plan(
            planned=sample_rebuild,
            import_input=sample_import,
            removed_tables=(),
        )
        sample_hashes: list[dict[str, Any]] = []
        for repetition in range(3):
            ordered_sql = (
                (("patch", sample_adaptive_sql), ("rebuild", sample_rebuild_sql))
                if repetition % 2 == 0
                else (("rebuild", sample_rebuild_sql), ("patch", sample_adaptive_sql))
            )
            measured: dict[str, dict[str, Any]] = {}
            for label, sql in ordered_sql:
                measured[label] = _replay_branch(
                    container=repository_service_container,
                    repository_path=repository_path,
                    base_commit=baseline_commit,
                    sql_bytes=sql,
                    table_names=(table_name,),
                    label=f"one-percent-{label}",
                )
            patch_hashes = measured["patch"].pop("hashes")
            rebuild_hashes = measured["rebuild"].pop("hashes")
            sample_hash_equal = patch_hashes == rebuild_hashes
            if not sample_hash_equal:
                raise RuntimeError("one-percent patch and rebuild table hashes differ")
            sample_hashes.append(
                {
                    "repetition": repetition + 1,
                    "hash_equal": sample_hash_equal,
                    "patch": measured["patch"],
                    "rebuild": measured["rebuild"],
                }
            )
        median_patch_seconds = statistics.median(
            item["patch"]["total_seconds"] for item in sample_hashes
        )
        median_rebuild_seconds = statistics.median(
            item["rebuild"]["total_seconds"] for item in sample_hashes
        )

        main_after = _dolt_exec(
            container=repository_service_container,
            repository_path=repository_path,
            arguments=("rev-parse", "main"),
        ).decode("utf-8").strip()
        if main_after != target_commit:
            raise RuntimeError("measurement changed Repository Service main ref")

        result = {
            "schema_version": "p6-s1a-mutation-replay-measurement/v1",
            "hostname": socket.gethostname(),
            "head": head,
            "started_at_utc": started_at,
            "ended_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "status": "PASS",
            "baseline_materialization": full_materialization,
            "t4_v2_changed_table_count": len(changed_names),
            "t4_v2_changed_tables": list(changed_names),
            "adaptive_plan": {
                "rebuild_table_count": len(adaptive_rebuild_tables),
                "rebuild_tables": list(adaptive_rebuild_tables),
                "mutation_counts": _mutation_counts(adaptive),
                "replay_sql_bytes": len(adaptive_sql),
                "insert_batch_rules": {
                    "max_rows": _INSERT_ROW_LIMIT,
                    "max_bytes": _INSERT_BYTE_LIMIT,
                    **_insert_statement_metrics(adaptive_sql),
                },
            },
            "full_rebuild_plan": {
                "rebuild_table_count": len(full_rebuild_tables),
                "mutation_counts": _mutation_counts(full_rebuild),
                "replay_sql_bytes": len(full_sql),
                "insert_batch_rules": {
                    "max_rows": _INSERT_ROW_LIMIT,
                    "max_bytes": _INSERT_BYTE_LIMIT,
                    **_insert_statement_metrics(full_sql),
                },
            },
            "t4_v2_hash_equivalence": {
                "table_count": len(target_names),
                "adaptive_tables_equal_current": len(target_names) if adaptive_hash_equal else 0,
                "full_rebuild_tables_equal_current": len(target_names) if full_hash_equal else 0,
                "adaptive_equals_full_rebuild": adaptive_hash_equal and full_hash_equal,
                "adaptive_replay": adaptive_replay,
                "full_rebuild_replay": full_replay,
            },
            "one_percent_sample": {
                "table_name": table_name,
                **synthetic_counts,
                "change_ratio": synthetic_counts["synthetic_changed_row_count"]
                / max(synthetic_counts["parent_row_count"], synthetic_counts["target_row_count"]),
                "adaptive_operation": sample_adaptive.plan.table_summaries[0].operation.value,
                "adaptive_mutation_counts": _mutation_counts(sample_adaptive),
                "rebuild_mutation_counts": _mutation_counts(sample_rebuild),
                "adaptive_sql_bytes": len(sample_adaptive_sql),
                "rebuild_sql_bytes": len(sample_rebuild_sql),
                "adaptive_insert_batch_rules": {
                    "max_rows": _INSERT_ROW_LIMIT,
                    "max_bytes": _INSERT_BYTE_LIMIT,
                    **_insert_statement_metrics(sample_adaptive_sql),
                },
                "rebuild_insert_batch_rules": {
                    "max_rows": _INSERT_ROW_LIMIT,
                    "max_bytes": _INSERT_BYTE_LIMIT,
                    **_insert_statement_metrics(sample_rebuild_sql),
                },
                "repetitions": sample_hashes,
                "median_patch_total_seconds": median_patch_seconds,
                "median_rebuild_total_seconds": median_rebuild_seconds,
            },
            "branch_refs_left_for_owner": [
                adaptive_replay["branch"],
                full_replay["branch"],
                *[
                    item[label]["branch"]
                    for item in sample_hashes
                    for label in ("patch", "rebuild")
                ],
            ],
            "repository_main_unchanged": True,
            "privacy": "table names, counts, timings, branch refs, and hash equality only",
            "wall_seconds": round(time.perf_counter() - start_wall, 6),
        }
        if median_patch_seconds >= median_rebuild_seconds:
            raise RuntimeError("one-percent patch replay was not faster than table rebuild")
        _write_result(output_path, result)
        return result
    except BaseException as exc:
        failure = {
            "schema_version": "p6-s1a-mutation-replay-measurement/v1",
            "hostname": socket.gethostname(),
            "head": head,
            "started_at_utc": started_at,
            "ended_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "status": "FAILED",
            "failure_type": type(exc).__name__,
            "wall_seconds": round(time.perf_counter() - start_wall, 6),
            "privacy": "table names, counts, timings, branch refs, and hash equality only",
        }
        _write_result(output_path, failure)
        raise


def _write_result(path: Path, result: dict[str, Any]) -> None:
    path.write_text(json.dumps(result, sort_keys=True, separators=(",", ":")) + "\n")
    path.chmod(0o600)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--real-dump-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--scratch", type=Path, required=True)
    parser.add_argument("--repository-id", required=True)
    parser.add_argument("--baseline-commit", required=True)
    parser.add_argument("--target-commit", required=True)
    parser.add_argument("--bearer-token-file", type=Path, required=True)
    parser.add_argument("--repository-service-url", required=True)
    parser.add_argument("--repository-service-container", required=True)
    args = parser.parse_args(argv)
    result = run(
        real_dump_root=args.real_dump_root.resolve(),
        output_path=args.output,
        scratch_path=args.scratch,
        repository_id=args.repository_id,
        baseline_commit=args.baseline_commit,
        target_commit=args.target_commit,
        bearer_token_file=args.bearer_token_file,
        repository_service_url=args.repository_service_url,
        repository_service_container=args.repository_service_container,
    )
    print(
        json.dumps(
            {
                "event": "s1a_mutation_replay_complete",
                "status": result["status"],
                "changed_table_count": result["t4_v2_changed_table_count"],
                "hash_table_count": result["t4_v2_hash_equivalence"]["table_count"],
                "one_percent_table": result["one_percent_sample"]["table_name"],
                "output": str(args.output),
            },
            sort_keys=True,
        ),
        flush=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
