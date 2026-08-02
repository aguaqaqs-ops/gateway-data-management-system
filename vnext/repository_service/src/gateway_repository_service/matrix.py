"""Unified P2-R1 formal runner and diagnostic measurement helpers."""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import os
import platform
import signal
import subprocess
import tempfile
import re
import uuid
from collections import Counter
from functools import lru_cache
from pathlib import Path
from typing import Callable, Iterable, TextIO, cast

from gateway_repository_service.fixtures import (
    Fixture,
    ScaleWorkload,
    Workload,
    generate_fixture,
    generate_scale_fixture,
)
from gateway_repository_service.process import (
    MEMORY_SUBJECTS,
    WINDOW_NAMES,
    parse_dolt_version,
    load_cgroup_topology,
    preflight_cgroup,
)
from gateway_repository_service.publication import atomic_publish_file
from gateway_repository_service.settings import RepositoryServiceSettings
from gateway_repository_service.workflow import (
    Candidate,
    WorkflowMeasurement,
    run_workflow,
    run_workflow_isolated,
)


NORMAL_WORKLOADS = (
    Workload.W0,
    Workload.W1,
    Workload.W2,
    Workload.W3_1,
    Workload.W3_10,
)
SCALE_WORKLOADS = tuple(ScaleWorkload)
ROW_BOUNDS = (256, 1024)
BYTE_BOUND = 4 * 1024 * 1024
EXPECTED_SAMPLE_KINDS = ("warmup", *(f"measured-{index}" for index in range(1, 6)))


class MatrixInterrupted(RuntimeError):
    """Raised so a stopped target can persist a terminal raw status."""


def _handle_matrix_signal(signum: int, _frame: object) -> None:
    raise MatrixInterrupted(f"matrix interrupted by signal {signum}")


def run_matrix(
    settings: RepositoryServiceSettings,
    output: Path,
    *,
    data_root: Path | None = None,
    workloads: Iterable[Workload] = NORMAL_WORKLOADS,
    measured_runs: int = 5,
    diagnostic: bool = False,
    image_digest: str | None = None,
    build_revision: str | None = None,
    cache_condition: str | None = None,
) -> dict[str, object]:
    """Run the only formal P2-R1 matrix.

    A formal invocation always collects the normal 60 records and scaling 72
    records before publishing one raw stream, one summary, and one report.
    Subsets are intentionally diagnostic-only and can never select a provider.
    """

    selected = tuple(workloads)
    if measured_runs != 5:
        raise ValueError("formal P2-R1 requires exactly five measured runs")
    if not diagnostic and selected != NORMAL_WORKLOADS:
        raise ValueError("workload subsets are diagnostic-only")
    target_container = os.environ.get("GATEWAY_P2R1_TARGET_CONTAINER") == "1"
    if not diagnostic or target_container:
        topology = load_cgroup_topology(settings.cgroup_layout)
        cgroup_input = (
            topology.samples
            if topology is not None
            else settings.cgroup_root or Path("/sys/fs/cgroup")
        )
        sample_root = (
            preflight_cgroup(cgroup_input, topology)
            if topology is not None
            else preflight_cgroup(cgroup_input)
        )
        if topology is not None and sample_root != topology.samples:
            raise RuntimeError("cgroup preflight returned a non-topology sample root")
        if isinstance(sample_root, Path):
            settings = settings.model_copy(update={"cgroup_root": sample_root})
    output.parent.mkdir(parents=True, exist_ok=True)
    _ensure_artifacts_absent(output)
    raw_handle = _reserve_raw(output) if not diagnostic else None
    records: list[dict[str, object]] = []
    written_records = 0
    status_written = False
    contexts_cleaned = False
    storage_baselines: dict[str, int] = {}
    fixture_context = tempfile.TemporaryDirectory(prefix="gateway-p2r1-fixtures-")
    root_context = (
        tempfile.TemporaryDirectory(prefix="gateway-p2r1-target-")
        if data_root is None
        else None
    )
    def persist_record(record: dict[str, object]) -> None:
        nonlocal written_records
        if raw_handle is None:
            return
        _observe_storage_record(record, storage_baselines)
        raw_handle.write(json.dumps(record, sort_keys=True) + "\n")
        raw_handle.flush()
        os.fsync(raw_handle.fileno())
        written_records += 1

    def persist_status(error: BaseException) -> None:
        nonlocal status_written
        if raw_handle is None or status_written:
            return
        raw_handle.write(
            json.dumps(
                {
                    "record_type": "run_status",
                    "status": "incomplete",
                    "p2_r1_exit": "no-go",
                    "selected_provider": None,
                    "error": type(error).__name__,
                    "records_written": written_records,
                },
                sort_keys=True,
            )
            + "\n"
        )
        raw_handle.flush()
        os.fsync(raw_handle.fileno())
        status_written = True

    try:
        fixture_root = Path(fixture_context.name)
        probe_root = data_root if data_root is not None else Path(root_context.name)  # type: ignore[union-attr]
        normal_workloads = selected if diagnostic else NORMAL_WORKLOADS
        records.extend(
            _collect_normal_records(
                settings,
                fixture_root,
                probe_root,
                normal_workloads,
                measured_runs,
                isolated=not diagnostic or target_container,
                image_digest=image_digest,
                build_revision=build_revision,
                cache_condition=cache_condition,
                record_sink=persist_record,
            )
        )
        if not diagnostic:
            records.extend(
                _collect_scaling_records(
                    settings,
                    fixture_root,
                    probe_root,
                    measured_runs,
                    image_digest=image_digest,
                    build_revision=build_revision,
                    cache_condition=cache_condition,
                    isolated=True,
                    record_sink=persist_record,
                )
            )
    except BaseException as exc:
        persist_status(exc)
        raise

    try:
        fixture_context.cleanup()
        if root_context is not None:
            root_context.cleanup()
        contexts_cleaned = True
        if diagnostic:
            _annotate_storage(records)
            summary_records = records
        else:
            if raw_handle is None:
                raise RuntimeError("formal matrix raw handle was not reserved")
            raw_handle.flush()
            os.fsync(raw_handle.fileno())
            persisted_records = _read_raw_records(output)
            expected_records = [dict(record) for record in records]
            _annotate_storage(expected_records)
            if persisted_records != expected_records:
                raise RuntimeError("persisted raw records differ from in-memory records")
            summary_records = [dict(record) for record in persisted_records]
            _annotate_storage(summary_records)
        summary = _summarize(summary_records, settings)
        summary["decision_kind"] = "diagnostic" if diagnostic else "formal"
        summary["formal_decision"] = not diagnostic
        if diagnostic:
            summary["p2_r1_exit"] = "no-go"
            summary["round_exit"] = "diagnostic-no-go"
            summary["next_round_ready"] = False
            summary["p2_r2_ready"] = False
            summary["selected_provider"] = None
        if diagnostic:
            _write_artifacts(output, summary_records, summary)
        else:
            _publish_summary_report(output, summary)
        return summary
    except BaseException as exc:
        persist_status(exc)
        raise
    finally:
        try:
            if not contexts_cleaned:
                fixture_context.cleanup()
                if root_context is not None:
                    root_context.cleanup()
        except BaseException as exc:
            persist_status(exc)
            raise
        finally:
            if raw_handle is not None:
                raw_handle.close()


def _collect_normal_records(
    settings: RepositoryServiceSettings,
    fixture_root: Path,
    probe_root: Path,
    workloads: tuple[Workload, ...],
    measured_runs: int,
    *,
    isolated: bool,
    image_digest: str | None,
    build_revision: str | None,
    cache_condition: str | None,
    record_sink: Callable[[dict[str, object]], None] | None = None,
) -> list[dict[str, object]]:
    records: list[dict[str, object]] = []
    metadata = _measurement_metadata(
        settings, image_digest=image_digest, build_revision=build_revision, cache_condition=cache_condition
    )
    for candidate in Candidate:
        for workload in workloads:
            fixture = generate_fixture(fixture_root, workload)
            base_fixture = (
                generate_fixture(fixture_root, Workload.W1)
                if workload in {Workload.W3_1, Workload.W3_10}
                else None
            )
            for sample_kind in EXPECTED_SAMPLE_KINDS[: measured_runs + 1]:
                workflow_runner = run_workflow_isolated if isolated else run_workflow
                measurement = workflow_runner(
                    settings,
                    candidate,
                    fixture,
                    sample_kind=sample_kind,
                    run_unknown_reject=workload == Workload.W0,
                    base_fixture=base_fixture,
                    root_parent=probe_root,
                )
                record = _record(
                        fixture,
                        measurement,
                        probe_root,
                        matrix_kind="normal",
                        row_bound=settings.record_batch_rows,
                        metadata=metadata,
                    )
                records.append(record)
                if record_sink is not None:
                    record_sink(record)
    return records


def _collect_scaling_records(
    settings: RepositoryServiceSettings,
    fixture_root: Path,
    probe_root: Path,
    measured_runs: int,
    *,
    isolated: bool = True,
    image_digest: str | None,
    build_revision: str | None,
    cache_condition: str | None,
    record_sink: Callable[[dict[str, object]], None] | None = None,
) -> list[dict[str, object]]:
    records: list[dict[str, object]] = []
    metadata = _measurement_metadata(
        settings, image_digest=image_digest, build_revision=build_revision, cache_condition=cache_condition
    )
    for candidate in Candidate:
        for scale in SCALE_WORKLOADS:
            fixture = generate_scale_fixture(fixture_root, scale)
            for bound in ROW_BOUNDS:
                bound_settings = settings.model_copy(
                    update={"record_batch_rows": bound, "record_batch_bytes": BYTE_BOUND}
                )
                for sample_kind in EXPECTED_SAMPLE_KINDS[: measured_runs + 1]:
                    workflow_runner = run_workflow_isolated if isolated else run_workflow
                    measurement = workflow_runner(
                        bound_settings,
                        candidate,
                        fixture,
                        sample_kind=sample_kind,
                        run_unknown_reject=False,
                        root_parent=probe_root,
                    )
                    record = _record(
                            fixture,
                            measurement,
                            probe_root,
                            matrix_kind="scaling",
                            row_bound=bound,
                            metadata=metadata,
                        )
                    records.append(record)
                    if record_sink is not None:
                        record_sink(record)
    return records


def _record(
    fixture: Fixture,
    measurement: WorkflowMeasurement,
    filesystem_path: Path,
    *,
    matrix_kind: str,
    row_bound: int,
    metadata: dict[str, object] | None = None,
) -> dict[str, object]:
    data = measurement.as_dict()
    data.update(
        {
            "dataset_id": fixture.dataset_id,
            "synthetic": fixture.synthetic,
            "package_bytes": fixture.package_bytes,
            "fixture_rows": fixture.rows,
            "python_version": platform.python_version(),
            "cpu_count": os.cpu_count(),
            "filesystem_type": _filesystem_type(filesystem_path),
            "volume_backend": os.environ.get("GATEWAY_P2R1_VOLUME_BACKEND", "unknown"),
            "memory_limit_bytes": _memory_limit_bytes(),
            "methodology_version": metadata.get(
                "measurement_methodology_version", "unknown"
            )
            if metadata is not None
            else "unknown",
            "matrix_kind": matrix_kind,
            "record_batch_row_bound": row_bound,
            "record_batch_byte_bound": BYTE_BOUND,
            "cache_state": "warmup"
            if measurement.sample_kind == "warmup"
            else "warm",
        }
    )
    if metadata is not None:
        data.update(metadata)
    data.update(_storage_fields(data))
    data["bounded_stream_record_gate"] = _record_bounded_gate(data)
    return data


def _ensure_artifacts_absent(output: Path) -> None:
    targets = (output, output.with_suffix(".summary.json"), output.with_suffix(".md"))
    existing = [str(path) for path in targets if path.exists()]
    if existing:
        raise FileExistsError("P2-R1 artifacts already exist: " + ", ".join(existing))


def _reserve_raw(output: Path) -> TextIO:
    """Reserve the raw stream before any fixture work can consume matrix time."""

    return output.open("x", encoding="utf-8")


def _publish_summary_report(output: Path, summary: dict[str, object]) -> None:
    summary_path = output.with_suffix(".summary.json")
    report_path = output.with_suffix(".md")
    staged: list[tuple[Path, Path]] = []
    try:
        for target, content in (
            (summary_path, json.dumps(summary, indent=2, sort_keys=True) + "\n"),
            (report_path, _markdown(summary)),
        ):
            temporary = target.with_name(f".{target.name}.{uuid.uuid4().hex}.tmp")
            with temporary.open("x", encoding="utf-8") as handle:
                handle.write(content)
                handle.flush()
                os.fsync(handle.fileno())
            staged.append((temporary, target))
        for temporary, target in staged:
            atomic_publish_file(temporary, target)
    finally:
        for temporary, _ in staged:
            temporary.unlink(missing_ok=True)


def _write_artifacts(
    output: Path, records: list[dict[str, object]], summary: dict[str, object]
) -> None:
    with output.open("x", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record, sort_keys=True) + "\n")
    _publish_summary_report(output, summary)


def _filesystem_type(path: Path = Path(".")) -> str:
    result = subprocess.run(
        ["stat", "-f", "-c", "%T", str(path)], capture_output=True, text=True, check=False
    )
    return result.stdout.strip() or "unknown"


def _memory_limit_bytes() -> int | None:
    path = Path("/sys/fs/cgroup/memory.max")
    if not path.is_file():
        return None
    value = path.read_text(encoding="utf-8").strip()
    return None if value == "max" else int(value)


@lru_cache(maxsize=8)
def _actual_dolt_version(binary: str) -> str | None:
    result = subprocess.run(
        [binary, "version"], capture_output=True, check=False, timeout=10
    )
    return parse_dolt_version(result.stdout.decode("utf-8", errors="replace"))


def _distribution_version(name: str) -> str | None:
    try:
        return importlib.metadata.version(name)
    except importlib.metadata.PackageNotFoundError:
        return None


def _measurement_metadata(
    settings: RepositoryServiceSettings,
    *,
    image_digest: str | None,
    build_revision: str | None,
    cache_condition: str | None,
) -> dict[str, object]:
    actual_dolt = _actual_dolt_version(str(settings.dolt_binary))
    actual_driver = _distribution_version("mysql-connector-python")
    actual_pyarrow = _distribution_version("pyarrow")
    verified_image = os.environ.get("GATEWAY_P2R1_IMAGE_DIGEST")
    verified_revision = os.environ.get("GATEWAY_P2R1_BUILD_REVISION")
    verified_cache = os.environ.get("GATEWAY_P2R1_CACHE_CONDITION")
    verified_lock = os.environ.get("GATEWAY_P2R1_LOCK_SHA256")
    verified_tree = os.environ.get("GATEWAY_P2R1_SOURCE_TREE_SHA256")
    manifest = _load_provenance_manifest()
    provenance_flag = os.environ.get("GATEWAY_P2R1_PROVENANCE_VERIFIED") == "1"
    provenance_verified = provenance_flag and manifest is not None
    cli_matches_verified = (
        not provenance_verified
        or (image_digest in (None, verified_image))
        and (build_revision in (None, verified_revision))
        and (cache_condition in (None, verified_cache))
    )
    resolved_image = verified_image if provenance_verified else image_digest or verified_image
    resolved_revision = verified_revision if provenance_verified else build_revision or verified_revision
    resolved_cache = verified_cache if provenance_verified else cache_condition or verified_cache
    lock_path = Path(__file__).resolve().parents[2] / "uv.lock"
    actual_lock = hashlib.sha256(lock_path.read_bytes()).hexdigest() if lock_path.is_file() else None
    valid_image = bool(
        isinstance(resolved_image, str)
        and re.fullmatch(r"sha256:[0-9a-f]{64}", resolved_image)
    )
    valid_revision = bool(
        isinstance(resolved_revision, str)
        and re.fullmatch(r"[0-9a-f]{40,64}", resolved_revision)
    )
    valid_cache = resolved_cache in {
        "retained-dependency-cache",
        "cold-dependencies",
    }
    manifest_valid = bool(
        manifest is not None
        and manifest.get("manifest_version") == "p2-r1-provenance-v2"
        and manifest.get("image_digest") == resolved_image
        and manifest.get("build_revision") == resolved_revision
        and manifest.get("lock_sha256") == actual_lock
        and manifest.get("dolt_version") == settings.dolt_version
        and manifest.get("mysql_connector_version") == settings.mysql_connector_version
        and manifest.get("pyarrow_version") == actual_pyarrow
        and manifest.get("cache_condition") == resolved_cache
        and manifest.get("source_tree_sha256") == verified_tree
        and isinstance(manifest.get("source_tree_sha256"), str)
        and re.fullmatch(r"sha256:[0-9a-f]{64}", str(manifest.get("source_tree_sha256")))
        is not None
    )
    return {
        "dolt_actual_version": actual_dolt,
        "dolt_expected_version": settings.dolt_version,
        "mysql_connector_actual_version": actual_driver,
        "mysql_connector_expected_version": settings.mysql_connector_version,
        "pyarrow_actual_version": actual_pyarrow,
        "image_digest": resolved_image or "unknown",
        "build_revision": resolved_revision or "unknown",
        "cache_condition": resolved_cache or "unknown",
        "lock_sha256": actual_lock,
        "declared_lock_sha256": verified_lock,
        "provenance_verified": provenance_verified,
        "provenance_manifest": manifest if manifest is not None else {},
        "provenance_manifest_valid": manifest_valid,
        "measurement_methodology_version": settings.measurement_methodology_version,
        "metadata_complete": bool(
            actual_dolt == settings.dolt_version
            and actual_driver == settings.mysql_connector_version
            and actual_pyarrow is not None
            and valid_image
            and valid_revision
            and valid_cache
            and provenance_verified
            and manifest_valid
            and cli_matches_verified
            and actual_lock is not None
            and verified_lock == actual_lock
        ),
    }


def _load_provenance_manifest() -> dict[str, object] | None:
    path_value = os.environ.get("GATEWAY_P2R1_PROVENANCE_MANIFEST")
    if not path_value:
        return None
    try:
        value = json.loads(Path(path_value).read_text(encoding="utf-8"))
    except (OSError, ValueError, json.JSONDecodeError):
        return None
    return cast(dict[str, object], value) if isinstance(value, dict) else None


def _storage_fields(record: dict[str, object]) -> dict[str, object]:
    workload = str(record.get("workload", ""))
    change_ratio: float | None = None
    if workload == Workload.W3_1.value:
        change_ratio = 0.01
    elif workload == Workload.W3_10.value:
        change_ratio = 0.10
    before = record.get("logical_bytes_before")
    after = record.get("logical_bytes_after")
    allocated_before = record.get("allocated_bytes_before")
    allocated_after = record.get("allocated_bytes_after")
    logical_delta = after - before if isinstance(after, int) and isinstance(before, int) else None
    allocated_delta = (
        allocated_after - allocated_before
        if isinstance(allocated_after, int) and isinstance(allocated_before, int)
        else None
    )
    return {
        "change_ratio": change_ratio,
        "logical_delta_bytes": logical_delta,
        "allocated_delta_bytes": allocated_delta,
        "quiesce_status": "quiesced"
        if record.get("storage_quiesced") is True
        else "unavailable",
        "w1_full_commit_logical_bytes": None,
        "logical_delta_vs_w1_full_ratio": None,
        "full_rewrite_observed": None,
        "full_rewrite_explanation": "pending W1 comparison"
        if change_ratio is not None
        else None,
        "storage_evidence_status": "pending" if change_ratio is not None else "not_applicable",
    }


def _observe_storage_record(record: dict[str, object], full_by_candidate: dict[str, int]) -> None:
    """Annotate one record before raw publication using already observed W1 evidence."""

    candidate = str(record.get("candidate"))
    if (
        record.get("workload") == Workload.W1.value
        and str(record.get("sample_kind", "")).startswith("measured-")
        and isinstance(record.get("logical_delta_bytes"), int)
        and int(cast(int, record["logical_delta_bytes"])) > 0
    ):
        full_by_candidate[candidate] = max(
            full_by_candidate.get(candidate, 0), cast(int, record["logical_delta_bytes"])
        )
    if record.get("change_ratio") is None:
        return
    full = full_by_candidate.get(candidate)
    delta = record.get("logical_delta_bytes")
    record["w1_full_commit_logical_bytes"] = full
    if full is None or not isinstance(delta, int) or full <= 0:
        record["storage_evidence_status"] = "inconclusive"
        record["full_rewrite_explanation"] = "missing positive W1 full-commit baseline"
        return
    ratio = delta / full
    record["logical_delta_vs_w1_full_ratio"] = ratio
    record["full_rewrite_observed"] = ratio >= 1.0
    record["full_rewrite_explanation"] = (
        "logical delta is at least the W1 full-commit delta"
        if ratio >= 1.0
        else "logical delta is below the W1 full-commit delta"
    )
    record["storage_evidence_status"] = (
        "available"
        if record.get("quiesce_status") == "quiesced"
        and isinstance(record.get("allocated_delta_bytes"), int)
        and delta > 0
        and int(cast(int, record["allocated_delta_bytes"])) > 0
        else "inconclusive"
    )


def _annotate_storage(records: list[dict[str, object]]) -> None:
    full_by_candidate: dict[str, int] = {}
    for record in records:
        _observe_storage_record(record, full_by_candidate)


def _read_raw_records(output: Path) -> list[dict[str, object]]:
    records: list[dict[str, object]] = []
    with output.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, 1):
            if not line.strip():
                continue
            value = json.loads(line)
            if not isinstance(value, dict):
                raise ValueError(f"raw record {line_number} is not an object")
            if value.get("record_type") == "run_status":
                continue
            records.append(cast(dict[str, object], value))
    return records


def run_scaling_diagnostic(
    settings: RepositoryServiceSettings,
    output: Path,
    *,
    data_root: Path | None = None,
    measured_runs: int = 5,
    image_digest: str | None = None,
    build_revision: str | None = None,
    cache_condition: str | None = None,
) -> dict[str, object]:
    """Run scaling records as diagnostic-only evidence."""

    if measured_runs != 5:
        raise ValueError("P2-R1 requires exactly five measured runs")
    _ensure_artifacts_absent(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    records: list[dict[str, object]] = []
    fixture_context = tempfile.TemporaryDirectory(prefix="gateway-p2r1-scaling-fixtures-")
    root_context = (
        tempfile.TemporaryDirectory(prefix="gateway-p2r1-scaling-target-")
        if data_root is None
        else None
    )
    try:
        fixture_root = Path(fixture_context.name)
        probe_root = data_root if data_root is not None else Path(root_context.name)  # type: ignore[union-attr]
        records = _collect_scaling_records(
            settings,
            fixture_root,
            probe_root,
            measured_runs,
            image_digest=image_digest,
            build_revision=build_revision,
            cache_condition=cache_condition,
            isolated=False,
        )
    finally:
        fixture_context.cleanup()
        if root_context is not None:
            root_context.cleanup()
    _annotate_storage(records)
    summary = _summarize([], settings, scaling_records=records)
    summary.update(
        {
            "decision_kind": "diagnostic",
            "formal_decision": False,
            "p2_r1_exit": "no-go",
            "round_exit": "diagnostic-no-go",
            "selected_provider": None,
            "next_round_ready": False,
            "p2_r2_ready": False,
        }
    )
    _write_artifacts(output, records, summary)
    return summary


def _coverage(
    records: list[dict[str, object]], matrix_kind: str
) -> tuple[bool, str, dict[str, int]]:
    expected: set[tuple[str, ...]] = set()
    actual_keys: list[tuple[str, ...]] = []
    if matrix_kind == "normal":
        expected = {
            (candidate.value, workload.value, sample)
            for candidate in Candidate
            for workload in NORMAL_WORKLOADS
            for sample in EXPECTED_SAMPLE_KINDS
        }
        actual_keys = [
            (str(row.get("candidate")), str(row.get("workload")), str(row.get("sample_kind")))
            for row in records
            if row.get("matrix_kind", "normal") == "normal"
        ]
    else:
        expected = {
            (candidate.value, scale.value, str(bound), sample)
            for candidate in Candidate
            for scale in SCALE_WORKLOADS
            for bound in ROW_BOUNDS
            for sample in EXPECTED_SAMPLE_KINDS
        }
        actual_keys = [
            (
                str(row.get("candidate")),
                str(row.get("workload")),
                str(row.get("record_batch_row_bound")),
                str(row.get("sample_kind")),
            )
            for row in records
            if row.get("matrix_kind") == "scaling"
        ]
    actual = set(actual_keys)
    counts = Counter(actual_keys)
    duplicate_count = sum(count - 1 for count in counts.values() if count > 1)
    missing_count = len(expected - actual)
    extra_count = len(actual - expected)
    complete = actual == expected and duplicate_count == 0
    return complete, "complete" if complete else "missing/duplicate/extra sample keys", {
        "expected": len(expected),
        "actual": len(actual),
        "missing": missing_count,
        "duplicates": duplicate_count,
        "extra": extra_count,
    }


def _failure_counts(records: list[dict[str, object]]) -> dict[str, int]:
    return {
        "execution_errors": sum(1 for row in records if row.get("error") not in (None, "")),
        "correctness_failures": sum(1 for row in records if row.get("correctness") is not True),
        "performance_excluded_warmups": sum(
            1 for row in records if row.get("sample_kind") == "warmup"
        ),
    }


def _sample_failures(records: list[dict[str, object]]) -> int:
    counts = _failure_counts(records)
    return counts["execution_errors"] + counts["correctness_failures"]


def _summarize(
    records: list[dict[str, object]],
    settings: RepositoryServiceSettings,
    *,
    scaling_records: list[dict[str, object]] | None = None,
) -> dict[str, object]:
    all_records = [*records, *(scaling_records or [])]
    normal_records = [
        row for row in all_records if row.get("matrix_kind", "normal") == "normal"
    ]
    scaling_rows = [row for row in all_records if row.get("matrix_kind") == "scaling"]
    _annotate_storage(all_records)
    normal_complete, normal_reason, normal_counts = _coverage(normal_records, "normal")
    scaling_complete, scaling_reason, scaling_counts = _coverage(scaling_rows, "scaling")
    candidate_matrix: dict[str, dict[str, object]] = {}
    for candidate in Candidate:
        normal_candidate = [
            row for row in normal_records if row.get("candidate") == candidate.value
        ]
        measured = [
            row for row in normal_candidate if str(row.get("sample_kind", "")).startswith("measured-")
        ]
        workflow = bool(normal_candidate) and all(
            row.get("correctness") is True for row in normal_candidate
        )
        safety_rows = [row for row in measured if row.get("workload") in {"W0", "W1", "W2"}]
        safety = bool(safety_rows) and all(
            isinstance(row.get("import_seconds"), (int, float))
            and float(cast(float, row["import_seconds"])) <= settings.import_timeout_seconds
            for row in safety_rows
        )
        w1 = [
            float(cast(int | float, row["import_seconds"]))
            for row in measured
            if row.get("workload") == Workload.W1.value
            and isinstance(row.get("import_seconds"), (int, float))
        ]
        max_import = max(w1) if w1 else None
        capacity = 4 * 86400 * 0.70 / max_import if max_import else 0.0
        w3_rows = [
            row
            for row in normal_candidate
            if row.get("workload") in {Workload.W3_1.value, Workload.W3_10.value}
        ]
        w3_storage = bool(w3_rows) and all(
            row.get("storage_evidence_status") == "available"
            and row.get("quiesce_status") == "quiesced"
            and isinstance(row.get("w1_full_commit_logical_bytes"), int)
            and isinstance(row.get("logical_delta_vs_w1_full_ratio"), (int, float))
            and isinstance(row.get("logical_delta_bytes"), int)
            and int(cast(int, row["logical_delta_bytes"])) > 0
            and isinstance(row.get("allocated_delta_bytes"), int)
            and int(cast(int, row["allocated_delta_bytes"])) > 0
            for row in w3_rows
        )
        bounded_status, bounded_reason, bounded_ratios = _bounded_stream_gate(
            candidate.value, scaling_rows
        )
        candidate_rows = [row for row in all_records if row.get("candidate") == candidate.value]
        failure_counts = _failure_counts(candidate_rows)
        metadata_complete = bool(candidate_rows) and all(
            row.get("metadata_complete") is True for row in candidate_rows
        )
        raw_gate_consistent = all(
            bool(row.get("bounded_stream_record_gate")) == _record_bounded_gate(row)
            and _raw_bounded_gate(row) == _record_bounded_gate(row)
            for row in candidate_rows
            if "hard_gates" in row
        )
        hard_gate = (
            normal_complete
            and scaling_complete
            and _sample_failures(candidate_rows) == 0
            and workflow
            and safety
            and capacity >= 1000
            and w3_storage
            and metadata_complete
            and raw_gate_consistent
            and bounded_status == "pass"
        )
        candidate_matrix[candidate.value] = {
            "workloads": sorted({str(row.get("workload")) for row in normal_candidate}),
            "matrix_coverage_complete": normal_complete,
            "workflow": workflow,
            "safety_limit": safety,
            "max_w1_import_seconds": max_import,
            "capacity_projection_imports_per_day": capacity,
            "capacity_gate": capacity >= 1000,
            "w3_storage_recorded": w3_storage,
            "w3_full_commit_ratios": sorted(
                {
                    float(cast(int | float, row["logical_delta_vs_w1_full_ratio"]))
                    for row in w3_rows
                    if isinstance(row.get("logical_delta_vs_w1_full_ratio"), (int, float))
                }
            ),
            "metadata_complete": metadata_complete,
            **failure_counts,
            "raw_gate_consistent": raw_gate_consistent,
            "bounded_stream_gate": bounded_status == "pass",
            "bounded_stream_status": bounded_status,
            "bounded_stream_reason": bounded_reason,
            "bounded_stream_ratios": bounded_ratios,
            "hard_gate": hard_gate,
            "result": "pass" if hard_gate else "fail",
        }
    a_pass = bool(candidate_matrix[Candidate.A.value]["hard_gate"])
    b_pass = bool(candidate_matrix[Candidate.B.value]["hard_gate"])
    selected = Candidate.A.value if a_pass else Candidate.B.value if b_pass else None
    outcome = "go" if selected is not None else "no-go"
    failure_counts = _failure_counts(all_records)
    return {
        "round": "P2-R1",
        "measurement_outcome": outcome,
        "proposed_provider": selected,
        "selected_provider": selected,
        "p2_r1_exit": outcome,
        "next_round_ready": selected is not None,
        "p2_r2_ready": selected is not None,
        "selection_reason": "simplicity-first: Candidate A selected when all hard gates pass"
        if selected == Candidate.A.value
        else "Candidate A failed and Candidate B passed"
        if selected == Candidate.B.value
        else "coverage, failure, or hard gate prevented provider selection",
        "round_exit": outcome,
        "candidate_matrix": candidate_matrix,
        "records": len(normal_records),
        "normal_records": len(normal_records),
        "scaling_records": len(scaling_rows),
        "sample_failures": _sample_failures(all_records),
        **failure_counts,
        "coverage": {
            "normal": {"complete": normal_complete, "reason": normal_reason, **normal_counts},
            "scaling": {"complete": scaling_complete, "reason": scaling_reason, **scaling_counts},
            "complete": normal_complete and scaling_complete,
        },
        "methodology": {
            "version": settings.measurement_methodology_version,
            "same_shape_scales": [scale.value for scale in SCALE_WORKLOADS],
            "row_bounds": list(ROW_BOUNDS),
            "byte_bound": BYTE_BOUND,
            "plateau_windows": list(WINDOW_NAMES),
            "memory_subjects": list(MEMORY_SUBJECTS),
            "bounded_ratio_limit": 1.5,
            "bounded_peak_semantics": "baseline_adjusted_delta",
            "absolute_plateau_preserved": True,
            "connector_fetch_row_bound": settings.connector_fetch_row_bound,
            "connector_fetch_semantics": "width_aware_at_most_configured_bound",
            "w2_role": "wide-row-boundary-only; excluded from total-size scaling gate",
            "w3_role": "storage-observation-only; quiesced measurement; no fixed ratio hard gate",
            "oversized_single_row": "allowed as a separate batch and recorded",
        },
        "measurement_environment": {
            "dolt_version": settings.dolt_version,
            "dolt_actual_versions": sorted(
                {str(row.get("dolt_actual_version")) for row in all_records}
            ),
            "mysql_connector_versions": sorted(
                {str(row.get("mysql_connector_actual_version")) for row in all_records}
            ),
            "image_digests": sorted({str(row.get("image_digest")) for row in all_records}),
            "build_revisions": sorted({str(row.get("build_revision")) for row in all_records}),
            "python_version": platform.python_version(),
            "cpu_count": os.cpu_count(),
            "filesystem": _filesystem_type(),
            "environment_class": "development-equivalent-smoke",
            "production_environment_assessed": False,
        },
        "decision_scope": "current_measurement_environment_only",
        "production_retest_required": True,
    }


def _bounded_stream_gate(
    candidate: str, records: list[dict[str, object]]
) -> tuple[str, str, dict[str, float]]:
    candidate_rows = [row for row in records if row.get("candidate") == candidate]
    expected = {
        (scale.value, bound, sample)
        for scale in SCALE_WORKLOADS
        for bound in ROW_BOUNDS
        for sample in EXPECTED_SAMPLE_KINDS
    }
    actual = {
        (
            str(row.get("workload")),
            int(cast(int, row["record_batch_row_bound"])),
            str(row.get("sample_kind")),
        )
        for row in candidate_rows
        if isinstance(row.get("record_batch_row_bound"), int)
    }
    if actual != expected or len(candidate_rows) != len(actual):
        return "inconclusive", "incomplete, duplicate, or unexpected scaling sample coverage", {}
    if _sample_failures(candidate_rows):
        return "inconclusive", "scaling failure sample retained", {}
    if any(not _record_bounded_gate(row) for row in candidate_rows):
        return "inconclusive", "per-workflow subject/window coverage unavailable", {}
    ratios: dict[str, float] = {}
    measured = [
        row for row in candidate_rows if str(row.get("sample_kind", "")).startswith("measured-")
    ]
    for bound in ROW_BOUNDS:
        for subject in MEMORY_SUBJECTS:
            for window in WINDOW_NAMES:
                scale_peaks: dict[str, float] = {}
                for scale in SCALE_WORKLOADS:
                    scale_values = [
                        _plateau_value(row, subject, window)
                        for row in measured
                        if row.get("record_batch_row_bound") == bound
                        and row.get("workload") == scale.value
                    ]
                    if len(scale_values) != 5:
                        return "inconclusive", "missing scale plateau evidence", ratios
                    scale_peak = max(scale_values)
                    scale_peaks[scale.value] = scale_peak
                    ratios[f"bound_{bound}_{subject}_{window}_{scale.value}"] = scale_peak
                values = list(scale_peaks.values())
                if not values:
                    return "inconclusive", f"missing {subject}/{window} evidence", ratios
                if min(values) == 0:
                    if max(values) == 0:
                        ratio = 1.0
                    else:
                        return (
                            "inconclusive",
                            f"zero/positive mixed {subject}/{window} evidence",
                            ratios,
                        )
                else:
                    ratio = max(values) / min(values)
                key = f"bound_{bound}_{subject}_{window}_ratio"
                ratios[key] = ratio
                if ratio > 1.5:
                    return "fail", f"{subject}/{window} ratio exceeded 1.5", ratios
    return "pass", "all subject/window plateaus within 1.5x", ratios


def _plateau_value(record: dict[str, object], subject: str, window: str) -> float:
    plateau = record.get("plateau_peaks")
    if not isinstance(plateau, dict):
        return 0.0
    subject_value = plateau.get(subject)
    if not isinstance(subject_value, dict):
        return 0.0
    value = subject_value.get(window)
    return float(value) if isinstance(value, (int, float)) else 0.0


def _record_bounded_gate(record: dict[str, object]) -> bool:
    evidence = record.get("memory_evidence")
    if not isinstance(evidence, dict) or evidence.get("coverage") != "available":
        return False
    if evidence.get("baseline_coverage") is not True:
        return False
    if evidence.get("cgroup_stat_coverage") is not True:
        return False
    plateau = record.get("plateau_peaks")
    if not isinstance(plateau, dict):
        return False
    absolute = record.get("plateau_peaks_absolute")
    if not isinstance(absolute, dict):
        return False
    complete = all(
        isinstance(plateau.get(subject), dict)
        and all(
            isinstance(plateau[subject].get(window), (int, float))
            and float(plateau[subject][window]) >= 0
            for window in WINDOW_NAMES
        )
        for subject in MEMORY_SUBJECTS
    )
    absolute_complete = all(
        isinstance(absolute.get(subject), dict)
        and all(
            isinstance(absolute[subject].get(window), (int, float))
            and float(absolute[subject][window]) > 0
            for window in WINDOW_NAMES
        )
        for subject in MEMORY_SUBJECTS
    )
    if not complete or not absolute_complete:
        return False
    fetch_bound = evidence.get("connector_fetch_payload_bound_ok")
    return fetch_bound is not False


def _raw_bounded_gate(record: dict[str, object]) -> bool:
    gates = record.get("hard_gates")
    return bool(gates.get("bounded_stream")) if isinstance(gates, dict) else False


def _markdown(summary: dict[str, object]) -> str:
    matrix = summary["candidate_matrix"]
    assert isinstance(matrix, dict)
    lines = [
        "# P2-R1 Provider Feasibility Decision",
        "",
        f"- p2_r1_exit: `{summary['p2_r1_exit']}`",
        f"- selected_provider: `{summary['selected_provider']}`",
        f"- next_round_ready: `{summary['next_round_ready']}`",
        f"- p2_r2_ready: `{summary['p2_r2_ready']}`",
        f"- decision_kind: `{summary.get('decision_kind', 'formal')}`",
        "",
        "| Candidate | Workflow | 60m safety | W1 max import (s) | Capacity projection | Hard gate |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for name, result in matrix.items():
        assert isinstance(result, dict)
        lines.append(
            f"| {name} | {result['workflow']} | {result['safety_limit']} | "
            f"{result['max_w1_import_seconds']} | {float(result['capacity_projection_imports_per_day']):.2f} | "
            f"{result['hard_gate']} |"
        )
    lines.extend(
        [
            "",
            "Normal and same-shape scaling coverage are required together for a formal decision.",
            "All workloads are deterministic synthetic fixtures; results are feasibility measurements, not production SLOs.",
            "W3 is storage evidence measured after provider shutdown and filesystem quiesce; it has no fixed ratio hard gate.",
            "",
        ]
    )
    return "\n".join(lines)


def main() -> None:
    signal.signal(signal.SIGTERM, _handle_matrix_signal)
    signal.signal(signal.SIGINT, _handle_matrix_signal)
    parser = argparse.ArgumentParser(description="Run the P2-R1 Dolt provider matrix")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--data-root", type=Path)
    parser.add_argument("--runs", type=int, default=5)
    parser.add_argument("--image-digest")
    parser.add_argument("--build-revision")
    parser.add_argument("--cache-condition")
    parser.add_argument("--diagnostic", action="store_true")
    parser.add_argument("--workloads", nargs="+", choices=[workload.value for workload in Workload])
    args = parser.parse_args()
    if args.workloads and not args.diagnostic:
        parser.error("--workloads is diagnostic-only; add --diagnostic")
    workloads = (
        tuple(Workload(value) for value in args.workloads)
        if args.workloads
        else NORMAL_WORKLOADS
    )
    summary = run_matrix(
        RepositoryServiceSettings(),
        args.output,
        data_root=args.data_root,
        workloads=workloads,
        measured_runs=args.runs,
        diagnostic=args.diagnostic,
        image_digest=args.image_digest,
        build_revision=args.build_revision,
        cache_condition=args.cache_condition,
    )
    print(json.dumps(summary, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
