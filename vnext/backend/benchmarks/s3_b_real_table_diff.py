"""Replacement-period B t1–t4 by-table differential; E removes this tool.

It checks every accepted package SHA before materialization. Each pair is
materialized once, then old fixed Python table behavior is compared with the
native locator probe only for dual-side row-kernel tasks. It does not run an
HTTP, Compose, Preview, Submit, or History journey. Output contains no cells
or row identities. The metadata_only count includes Python-owned non-record
roles; their COLUMNS_ADDED branch can inspect shared rows without row records.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import uuid
from dataclasses import asdict
from pathlib import Path
from typing import Any

from gateway_backend.artifacts.store import InMemoryArtifactStore, put_with_built_ref
from gateway_backend.application import preview_jobs
from gateway_backend.bootstrap.compute_kernel import initialize_compute_kernel
from gateway_backend.capabilities.comparison import (
    BoundSnapshotInput, ComparisonPlan, ComparisonRequest, ComparisonTableFact,
    TableComparisonTask, plan_comparison,
)
from gateway_backend.capabilities.comparison import standard as frozen_standard
from gateway_backend.capabilities.comparison.row_encoding import _can_table_early_exit
from gateway_backend.capabilities.table_access import (
    KernelExecutionContext, NeverCancel, OperationMemoryBudget, kernel_execution_scope,
)
from gateway_backend.capabilities.table_rules import (
    comparison_rule_set, migrated_table_ruleset_snapshot,
)
from gateway_backend.capabilities.table_rules.contracts import ComparisonRuleSet
from gateway_backend.domain.workspace.models import SourceArtifactBinding
from gateway_backend.operations.contracts import OperationDiagnosticSide
from tests.test_comparison_s3_b_differential import (
    _expected_standard, _fixed_reference, _frames, _identity, _interval_view,
    _probe_interval_view, _probe_task, _project_record,
)

_PACKAGES = {
    "rd-t1-a-v1": (107115, "42794011d74b6c906e35bc5c79610fc0305020ae966f8f0df4449337b95ea8b2"),
    "rd-t1-a-v2": (107066, "4019737fc8fe35e90792dcef722537bf09338110ace8cc09f35e004cc7095bd0"),
    "rd-t2-b-v1": (1247459, "acd1b5e6f92083c3a6d53e9996be0bf46f520ae7fdea94d8449069748a3817c0"),
    "rd-t2-b-v2": (1197404, "c66e3921c7774a38bfeb2f407c24a39209225e962f593ec88d17db0d85fcba98"),
    "rd-t3-c-v1": (3356815, "c34e266c458d9b2cfb630fec56fa7c893113e11b56f768710aecebb0715eec7e"),
    "rd-t3-c-v2": (3370171, "658422efd2583963cc04bdff6e88e2b733d33396bdd92ff5b3635dc00cffc28d"),
    "rd-t4-d-v1": (5597503, "95408cc3cfd5bee4f7e53ab1b556e58c3335535b16e8791059029e59d5da1675"),
    "rd-t4-d-v2": (5596595, "5a7cd54d9b996be55c34b7bb766eb01ad5c1b7c4fa9bd1e72f5c4741baee3611"),
}
_STEMS = {"t1": "rd-t1-a", "t2": "rd-t2-b", "t3": "rd-t3-c", "t4": "rd-t4-d"}
_ROW_KINDS = {"ROW_ADDED", "ROW_DELETED", "ROW_MODIFIED", "TABLE_DEGRADED"}
_KERNEL_THREADS = 1
_KERNEL_MEMORY_BUDGET_BYTES = 24 * 1024**3


def _materialize_package(package_bytes: bytes, store: InMemoryArtifactStore) -> BoundSnapshotInput:
    ref = put_with_built_ref(
        store,
        package_bytes,
        artifact_id=f"s3-b-{uuid.uuid4().hex}",
        media_type="application/gzip",
    )
    binding = SourceArtifactBinding(
        artifact_id=ref.artifact_id,
        media_type=ref.media_type,
        size_bytes=ref.size_bytes,
        raw_sha256=ref.raw_sha256.value,
    )
    bound, *_ = preview_jobs._materialize_uploaded_side(
        binding,
        store,
        migrated_table_ruleset_snapshot(),
        repository_id="s3-b-real-table-diff",
        export_cache=None,
        side=OperationDiagnosticSide.MODIFIED,
    )
    return bound


def _close_bound(bound: BoundSnapshotInput) -> None:
    if bound.table_set is None:
        return
    for table in bound.table_set.tables:
        for reader in (table.reader, table.batch_reader):
            if reader is not None:
                reader.close()


def _validated_packages(root: Path) -> dict[str, bytes]:
    document = json.loads((root / "datasets.json").read_text(encoding="utf-8"))
    items = document.get("datasets")
    if not isinstance(items, list):
        raise ValueError("datasets.json has no datasets array")
    manifests = {
        item["dataset_id"]: item for item in items
        if isinstance(item, dict) and isinstance(item.get("dataset_id"), str)
    }
    if set(manifests) != set(_PACKAGES):
        raise ValueError("dataset identity set differs from accepted eight packages")
    packages: dict[str, bytes] = {}
    for dataset_id, (size, digest) in _PACKAGES.items():
        files = manifests[dataset_id].get("files")
        if not isinstance(files, list) or len(files) != 1 or not isinstance(files[0], dict):
            raise ValueError(f"{dataset_id}: manifest package shape differs")
        manifest = files[0]
        if int(manifest["bytes"]) != size or manifest["sha256"] != digest:
            raise ValueError(f"{dataset_id}: datasets.json differs from accepted P5 S4 identity")
        path = root / "packages" / f"{dataset_id}.tar.gz"
        if path.stat().st_size != size:
            raise ValueError(f"{dataset_id}: package size differs")
        raw = path.read_bytes()
        if hashlib.sha256(raw).hexdigest() != digest:
            raise ValueError(f"{dataset_id}: package SHA differs")
        packages[dataset_id] = raw
    return packages


def _standard_row_view(actual: dict[str, Any]) -> list[dict[str, object]]:
    return [
        _project_record(actual["records"][index])
        for index in actual["facts_order"]
    ]


def _check_standard(
    task: TableComparisonTask, fact: ComparisonTableFact, actual: dict[str, Any],
) -> None:
    if (
        actual["row_added_count"], actual["row_deleted_count"], actual["row_modified_count"],
        actual["suppressed_added_count"], actual["suppressed_deleted_count"],
    ) != (
        fact.row_added_count, fact.row_deleted_count, fact.row_modified_count,
        fact.suppressed_added_count, fact.suppressed_deleted_count,
    ):
        raise AssertionError("standard table counts differ")
    expected = [
        _expected_standard(record, task.before_descriptor, task.current_descriptor)
        for record in fact.records if record.record_kind.value in _ROW_KINDS
    ]
    if _standard_row_view(actual) != expected:
        raise AssertionError("standard table row records or canonical frames differ")
    if (
        fact.schema_changes.schema_evolution.value == "COLUMNS_ADDED"
        and fact.status.value == "UNCHANGED"
    ):
        if actual["ignored_shared_content_changed"] != fact.content_changed:
            raise AssertionError("standard shared excluded content differs")


def _check_ordered(
    task: TableComparisonTask, fact: ComparisonTableFact, actual: dict[str, Any],
) -> None:
    extension = fact.ordered_extension
    blank = fact.blank_extension
    if extension is None or blank is None:
        raise AssertionError("ordered table lacks extension")
    if actual.get("unchanged") is True:
        if fact.status.value != "UNCHANGED" or actual["row_count"] != fact.row_count_current:
            raise AssertionError("unchanged ordered summary differs")
        if any(asdict(extension.ordered_summary).values()) or any(asdict(blank.blank_summary).values()):
            raise AssertionError("frozen unchanged ordered summary has nonzero counts")
        if actual["records"] != []:
            raise AssertionError("unchanged ordered emitted records")
    else:
        if actual["status"] != fact.status.value:
            raise AssertionError("ordered table status differs")
        if (
            actual["row_added_count"], actual["row_deleted_count"], actual["row_modified_count"],
            actual["suppressed_added_count"], actual["suppressed_deleted_count"],
        ) != (
            fact.row_added_count, fact.row_deleted_count, fact.row_modified_count,
            fact.suppressed_added_count, fact.suppressed_deleted_count,
        ):
            raise AssertionError("ordered table counts differ")
        if actual["content_changed"] != fact.content_changed:
            raise AssertionError("ordered shared content differs")
        if actual["ordered_summary"] != asdict(extension.ordered_summary):
            raise AssertionError("ordered summary counts differ")
        if actual["blank_summary"] != asdict(blank.blank_summary):
            raise AssertionError("blank summary counts differ")
        standard = [
            _project_record(actual["standard_records"][index])
            for index in actual["standard_facts_order"]
        ]
        expected_standard = [
            _expected_standard(record, task.before_descriptor, task.current_descriptor)
            for record in fact.records if record.record_kind.value in _ROW_KINDS
        ]
        if standard != expected_standard:
            raise AssertionError("ordered standard records or frames differ")
        rows = [actual["ordered_records"][index] for index in actual["ordered_facts_order"]]
        expected_rows = [
            (
                record.record_kind.value, record.semantic_kind.value,
                record.entity_key_kind.value, _identity(record.row_identity),
                record.before_position, record.current_position, list(record.changed_columns),
                _frames(record.before_values, task.before_descriptor),
                _frames(record.current_values, task.current_descriptor),
            )
            for record in extension.records
        ]
        if [
            (
                row["kind"], row["semantic_kind"], row["entity_key_kind"],
                row["row_identity"], row["before_position"], row["current_position"],
                row["changed_columns"], row["before_frames"], row["current_frames"],
            )
            for row in rows
        ] != expected_rows:
            raise AssertionError("ordered row records or canonical frames differ")
        if [
            (
                row["kind"], row["entity_key_kind"], _probe_interval_view(row["interval"]),
                row["before_occupancy"], row["current_occupancy"],
            )
            for row in actual["blank_records"]
        ] != [
            (
                record.record_kind.value, record.entity_key_kind.value,
                _interval_view(record.interval),
                record.before_occupancy, record.current_occupancy,
            )
            for record in blank.records
        ]:
            raise AssertionError("blank intervals or private keys differ")
    for label, reference in (
        ("before_ordered_digest", extension.before_ordered_digest),
        ("current_ordered_digest", extension.current_ordered_digest),
        ("before_occupancy_digest", blank.before_occupancy_digest),
        ("current_occupancy_digest", blank.current_occupancy_digest),
    ):
        if actual[label] != _identity(reference):
            raise AssertionError(f"{label} differs")


def _run_tier(
    tier: str, stem: str, packages: dict[str, bytes], rules: ComparisonRuleSet,
) -> dict[str, int]:
    store = InMemoryArtifactStore()
    before = _materialize_package(packages[f"{stem}-v1"], store)
    current = _materialize_package(packages[f"{stem}-v2"], store)
    try:
        plan = plan_comparison(ComparisonRequest(
            pair_id=f"s3-b-{tier}-by-table",
            before=before, current=current, rule_set=rules,
        ))
        if not isinstance(plan, ComparisonPlan):
            raise AssertionError(f"{tier}: comparison planning failed")
        checked = 0
        metadata_only = 0
        non_record_role = 0
        unchanged = 0
        for task in plan.tasks:
            fact = frozen_standard._compare_task_safely(task)
            if fact.status.value == "DEGRADED":
                old_fact = {
                    "status": fact.status.value,
                    "diagnostics": fact.diagnostics,
                    "row_count_before": fact.row_count_before,
                    "row_count_current": fact.row_count_current,
                    "record_kinds": [item.record_kind.value for item in fact.records],
                }
                raise AssertionError(
                    f"{tier}/{task.table_name}: frozen Python predegraded: {old_fact!r}"
                )
            if task.policy is not None and task.policy.comparison_role in {
                "BROWSE_ONLY", "SNAPSHOT_ONLY",
            }:
                # The frozen Python non-record role owns this table's facts.
                metadata_only += 1
                non_record_role += 1
                continue
            if task.before_table is None or task.current_table is None or task.policy is None:
                metadata_only += 1
                continue
            assert task.before_descriptor is not None and task.current_descriptor is not None
            ordered = task.policy.ordered_policy is not None
            if not ordered and _can_table_early_exit(
                task.before_descriptor, task.current_descriptor, task.policy,
            ):
                unchanged += 1
                continue
            actual = _probe_task(task, fact, ordered=ordered)
            try:
                if ordered:
                    _check_ordered(task, fact, actual)
                else:
                    _check_standard(task, fact, actual)
            except AssertionError as exc:
                raise AssertionError(f"{tier}/{task.table_name}: {exc}") from exc
            checked += 1
        return {
            "planned_tables": len(plan.tasks),
            "row_kernel_checked": checked,
            "metadata_only": metadata_only,
            "python_owned_non_record_role": non_record_role,
            "predegraded": 0,
            "standard_early_exit": unchanged,
        }
    finally:
        _close_bound(before)
        _close_bound(current)


def run(root: Path) -> dict[str, Any]:
    _fixed_reference()
    packages = _validated_packages(root)
    rules = comparison_rule_set(migrated_table_ruleset_snapshot())
    report: dict[str, Any] = {"input_verified": sorted(packages), "tiers": {}}
    for tier, stem in _STEMS.items():
        with kernel_execution_scope(
            KernelExecutionContext(
                OperationMemoryBudget(_KERNEL_MEMORY_BUDGET_BYTES),
                NeverCancel(),
                _KERNEL_THREADS,
            ),
            new_operation=True,
        ):
            report["tiers"][tier] = _run_tier(tier, stem, packages, rules)
    return report


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    args = parser.parse_args()
    initialize_compute_kernel(_KERNEL_THREADS)
    print(json.dumps(run(args.root.resolve()), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
