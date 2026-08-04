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
from gateway_repository_service.storage import StorageLayout, StorageLayoutError
from gateway_repository_service.filesystem import storage_root_identity
from gateway_repository_service.workflow import (
    Candidate,
    W3_STORAGE_SNAPSHOT_ORDER,
    WorkflowMeasurement,
    run_offline_discard_diagnostic,
    run_offline_discard_workflow_isolated,
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
V8_BYTE_BOUND = 1 * 1024 * 1024
V8_METHODOLOGY = "p2-r1-audit-corrective-v8"
V8_MEMORY_LIMIT_BYTES = 8 * 1024 * 1024 * 1024
EXPECTED_SAMPLE_KINDS = ("warmup", *(f"measured-{index}" for index in range(1, 6)))
STORAGE_LAYOUT_VERSION = "p2-r1-storage-layout-v1"
STORAGE_IDENTITY_PATTERN = re.compile(r"sha256:[0-9a-f]{64}")
W3_DELTA_STAGE_PAIRS = {
    "base_restart_delta": (
        "base_post_commit_close",
        "base_post_restart_validation",
    ),
    "delta_commit_delta": (
        "base_post_restart_validation",
        "delta_post_commit_close",
    ),
    "delta_restart_delta": (
        "delta_post_commit_close",
        "delta_post_restart_validation",
    ),
    "comparable_delta": (
        "base_post_restart_validation",
        "delta_post_restart_validation",
    ),
}


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
    restart_before_stream: bool = False,
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
    if restart_before_stream and not diagnostic:
        raise ValueError("pre-stream restart is diagnostic-only")
    target_container = os.environ.get("GATEWAY_P2R1_TARGET_CONTAINER") == "1"
    probe_data_root = _resolve_probe_data_root(settings, data_root, target_container)
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
    storage_baselines: dict[str, int] = {}
    contexts_cleaned = False
    fixture_context = tempfile.TemporaryDirectory(prefix="gateway-p2r1-fixtures-")
    root_context = (
        tempfile.TemporaryDirectory(prefix="gateway-p2r1-target-")
        if probe_data_root is None
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
        probe_root = (
            probe_data_root
            if probe_data_root is not None
            else Path(root_context.name)  # type: ignore[union-attr]
        )
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
                restart_before_stream=restart_before_stream,
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
                    restart_before_stream=restart_before_stream,
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


def run_v8_matrix(
    settings: RepositoryServiceSettings,
    output: Path,
    *,
    data_root: Path | None = None,
    measured_runs: int = 5,
    image_digest: str | None = None,
    build_revision: str | None = None,
    cache_condition: str | None = None,
) -> dict[str, object]:
    """Run the versioned A-only v8 formal matrix.

    The legacy runner remains available for v7 diagnostics.  This entry point
    is deliberately explicit so a v7 command cannot silently produce a v8
    decision or change the candidate set.
    """

    if measured_runs != 5:
        raise ValueError("v8 formal requires exactly five measured runs")
    if os.environ.get("GATEWAY_P2R1_TARGET_CONTAINER") != "1":
        raise RuntimeError("v8 formal requires the verified target container")
    if settings.v8_measurement_methodology_version != V8_METHODOLOGY:
        raise RuntimeError("v8 methodology setting does not match the v8 contract")
    target_container = True
    v8_settings = settings.model_copy(
        update={
            "measurement_methodology_version": settings.v8_measurement_methodology_version,
            "record_batch_rows": 1024,
            "record_batch_bytes": settings.v8_record_batch_bytes,
        }
    )
    probe_data_root = _resolve_probe_data_root(v8_settings, data_root, target_container)
    topology = load_cgroup_topology(v8_settings.cgroup_layout)
    cgroup_input = topology.samples if topology is not None else v8_settings.cgroup_root
    if cgroup_input is None:
        raise RuntimeError("v8 formal requires delegated cgroup topology")
    sample_root = preflight_cgroup(
        cgroup_input,
        topology,
        memory_limit_bytes=V8_MEMORY_LIMIT_BYTES,
    )
    if topology is not None and sample_root != topology.samples:
        raise RuntimeError("v8 preflight returned a non-topology sample root")
    v8_settings = v8_settings.model_copy(update={"cgroup_root": sample_root})
    output.parent.mkdir(parents=True, exist_ok=True)
    _ensure_artifacts_absent(output)
    raw_handle = _reserve_raw(output)
    fixture_context = tempfile.TemporaryDirectory(prefix="gateway-p2r1-v8-fixtures-")
    root_context = tempfile.TemporaryDirectory(prefix="gateway-p2r1-v8-target-") if probe_data_root is None else None
    records: list[dict[str, object]] = []
    written_records = 0
    status_written = False
    storage_baselines: dict[str, int] = {}

    def persist_record(record: dict[str, object]) -> None:
        nonlocal written_records
        _observe_storage_record(record, storage_baselines)
        raw_handle.write(json.dumps(record, sort_keys=True) + "\n")
        raw_handle.flush()
        os.fsync(raw_handle.fileno())
        written_records += 1

    def persist_status(error: BaseException) -> None:
        nonlocal status_written
        if status_written:
            return
        raw_handle.write(
            json.dumps(
                {
                    "record_type": "run_status",
                    "status": "incomplete",
                    "formal_status": "no-go",
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
        probe_root = probe_data_root or Path(root_context.name)  # type: ignore[union-attr]
        records.extend(
            _collect_normal_records(
                v8_settings,
                fixture_root,
                probe_root,
                NORMAL_WORKLOADS,
                measured_runs,
                isolated=True,
                image_digest=image_digest,
                build_revision=build_revision,
                cache_condition=cache_condition,
                candidates=(Candidate.A,),
                byte_bound=V8_BYTE_BOUND,
                record_sink=persist_record,
            )
        )
        records.extend(
            _collect_scaling_records(
                v8_settings,
                fixture_root,
                probe_root,
                measured_runs,
                isolated=True,
                image_digest=image_digest,
                build_revision=build_revision,
                cache_condition=cache_condition,
                candidates=(Candidate.A,),
                byte_bound=V8_BYTE_BOUND,
                record_sink=persist_record,
            )
        )
        fixture_context.cleanup()
        if root_context is not None:
            root_context.cleanup()
        persisted = _read_raw_records(output)
        summary = _summarize_v8(persisted, v8_settings)
        _publish_v8_summary_report(output, summary)
        return summary
    except BaseException as exc:
        persist_status(exc)
        raise
    finally:
        fixture_context.cleanup()
        if root_context is not None:
            root_context.cleanup()
        raw_handle.close()


def run_reserved_b_w0_smoke(
    settings: RepositoryServiceSettings,
    output: Path,
    *,
    image_digest: str | None = None,
    build_revision: str | None = None,
    cache_condition: str | None = None,
) -> dict[str, object]:
    """Run exactly one diagnostic-only Candidate B W0 sample."""

    if os.environ.get("GATEWAY_P2R1_TARGET_CONTAINER") != "1":
        raise RuntimeError("reserved B smoke requires the verified target container")
    if settings.v8_measurement_methodology_version != V8_METHODOLOGY:
        raise RuntimeError("v8 methodology setting does not match the v8 contract")
    smoke_settings = settings.model_copy(
        update={
            "measurement_methodology_version": settings.v8_measurement_methodology_version,
            "record_batch_rows": 1024,
            "record_batch_bytes": settings.v8_record_batch_bytes,
        }
    )
    probe_root = _resolve_probe_data_root(smoke_settings, None, True)
    topology = load_cgroup_topology(smoke_settings.cgroup_layout)
    cgroup_input = topology.samples if topology is not None else smoke_settings.cgroup_root
    if cgroup_input is None:
        raise RuntimeError("reserved B smoke requires delegated cgroup topology")
    sample_root = preflight_cgroup(
        cgroup_input,
        topology,
        memory_limit_bytes=V8_MEMORY_LIMIT_BYTES,
    )
    smoke_settings = smoke_settings.model_copy(update={"cgroup_root": sample_root})
    _ensure_artifacts_absent(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    raw_handle = _reserve_raw(output)
    fixture_context = tempfile.TemporaryDirectory(prefix="gateway-p2r1-b-smoke-")
    root_context = tempfile.TemporaryDirectory(prefix="gateway-p2r1-b-smoke-root-") if probe_root is None else None
    written = 0

    def sink(record: dict[str, object]) -> None:
        nonlocal written
        raw_handle.write(json.dumps(record, sort_keys=True) + "\n")
        raw_handle.flush()
        os.fsync(raw_handle.fileno())
        written += 1

    try:
        fixture_root = Path(fixture_context.name)
        actual_root = probe_root or Path(root_context.name)  # type: ignore[union-attr]
        records = _collect_normal_records(
            smoke_settings,
            fixture_root,
            actual_root,
            (Workload.W0,),
            0,
            isolated=True,
            image_digest=image_digest,
            build_revision=build_revision,
            cache_condition=cache_condition,
            candidates=(Candidate.B,),
            byte_bound=V8_BYTE_BOUND,
            record_sink=sink,
        )
        summary = {
            "diagnostic_only": True,
            "formal_decision": False,
            "formal_status": "no-go",
            "selected_provider": None,
            "p2_r2_ready": False,
            "candidate_b_status": "reserved_not_evaluated",
            "records": len(records),
            "expected_records": 1,
            "candidate_matrix": {
                Candidate.B.value: {
                    "status": "reserved_not_evaluated",
                    "hard_gate": None,
                    "result": "not_evaluated",
                }
            },
            "raw_records_written": written,
            "methodology_version": smoke_settings.measurement_methodology_version,
        }
        _publish_v8_summary_report(output, summary)
        return summary
    finally:
        fixture_context.cleanup()
        if root_context is not None:
            root_context.cleanup()
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
    restart_before_stream: bool = False,
    candidates: tuple[Candidate, ...] | None = None,
    byte_bound: int | None = None,
    record_sink: Callable[[dict[str, object]], None] | None = None,
) -> list[dict[str, object]]:
    records: list[dict[str, object]] = []
    metadata = _measurement_metadata(
        settings, image_digest=image_digest, build_revision=build_revision, cache_condition=cache_condition
    )
    selected_candidates = tuple(Candidate) if candidates is None else candidates
    effective_byte_bound = BYTE_BOUND if byte_bound is None else byte_bound
    for candidate in selected_candidates:
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
                    restart_before_stream=restart_before_stream,
                )
                record = _record(
                        fixture,
                        cast(WorkflowMeasurement, measurement),
                        probe_root,
                        matrix_kind="normal",
                        row_bound=settings.record_batch_rows,
                        byte_bound=effective_byte_bound,
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
    candidates: tuple[Candidate, ...] | None = None,
    byte_bound: int | None = None,
    restart_before_stream: bool = False,
    record_sink: Callable[[dict[str, object]], None] | None = None,
) -> list[dict[str, object]]:
    records: list[dict[str, object]] = []
    metadata = _measurement_metadata(
        settings, image_digest=image_digest, build_revision=build_revision, cache_condition=cache_condition
    )
    selected_candidates = tuple(Candidate) if candidates is None else candidates
    effective_byte_bound = BYTE_BOUND if byte_bound is None else byte_bound
    for candidate in selected_candidates:
        for scale in SCALE_WORKLOADS:
            fixture = generate_scale_fixture(fixture_root, scale)
            for bound in ROW_BOUNDS:
                bound_settings = settings.model_copy(
                    update={
                        "record_batch_rows": bound,
                        "record_batch_bytes": effective_byte_bound,
                    }
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
                        restart_before_stream=restart_before_stream,
                    )
                    record = _record(
                            fixture,
                            cast(WorkflowMeasurement, measurement),
                            probe_root,
                            matrix_kind="scaling",
                            row_bound=bound,
                            byte_bound=effective_byte_bound,
                            metadata=metadata,
                        )
                    records.append(record)
                    if record_sink is not None:
                        record_sink(record)
    return records


def _support_envelope(fixture: Fixture) -> str:
    total_rows = fixture.rows
    max_table_rows = max(
        (table.row_count for table in fixture.expected_tables), default=0
    )
    package_bytes = fixture.package_bytes
    if (
        total_rows <= 100_000
        and max_table_rows <= 100_000
        and package_bytes <= 200 * 1024 * 1024
    ):
        return "validated"
    if (
        total_rows <= 1_000_000
        and max_table_rows <= 1_000_000
        and package_bytes <= 200 * 1024 * 1024
    ):
        return "controlled_preview"
    return "out_of_range"


def _record(
    fixture: Fixture,
    measurement: WorkflowMeasurement,
    filesystem_path: Path,
    *,
    matrix_kind: str,
    row_bound: int,
    byte_bound: int = BYTE_BOUND,
    metadata: dict[str, object] | None = None,
) -> dict[str, object]:
    data = measurement.as_dict()
    target_container = os.environ.get("GATEWAY_P2R1_TARGET_CONTAINER") == "1"
    storage_layout = _load_storage_layout() if target_container else None
    try:
        root_identity = storage_root_identity(filesystem_path)
    except OSError:
        root_identity = ""
    filesystem = _filesystem_type(filesystem_path)
    mount_verified = bool(
        storage_layout is not None
        and storage_layout.filesystem_type == filesystem
        and storage_layout.storage_root_identity == root_identity
        and storage_layout.data_root.resolve() == filesystem_path.resolve()
    )
    data.update(
        {
            "dataset_id": fixture.dataset_id,
            "synthetic": fixture.synthetic,
            "package_bytes": fixture.package_bytes,
            "fixture_rows": fixture.rows,
            "total_rows_at_commit": fixture.rows,
            "max_table_rows": max(
                (table.row_count for table in fixture.expected_tables), default=0
            ),
            "import_package_bytes": fixture.package_bytes,
            "support_envelope": _support_envelope(fixture),
            "python_version": platform.python_version(),
            "cpu_count": os.cpu_count(),
            "filesystem_type": filesystem,
            "volume_backend": storage_layout.mount_type
            if mount_verified and storage_layout is not None
            else ("unknown" if target_container else os.environ.get("GATEWAY_P2R1_VOLUME_BACKEND", "unknown")),
            "storage_root_identity": root_identity,
            "storage_mount_verified": mount_verified if target_container else False,
            "storage_layout_version": storage_layout.storage_layout_version
            if storage_layout is not None
            else None,
            "storage_volume_project": storage_layout.volume_project
            if storage_layout is not None
            else None,
            "memory_limit_bytes": _memory_limit_bytes(),
            "methodology_version": metadata.get(
                "measurement_methodology_version", "unknown"
            )
            if metadata is not None
            else "unknown",
            "matrix_kind": matrix_kind,
            "record_batch_row_bound": row_bound,
            "record_batch_byte_bound": byte_bound,
            "cache_state": "warmup"
            if measurement.sample_kind == "warmup"
            else "warm",
        }
    )
    if metadata is not None:
        data.update(metadata)
    memory_evidence = data.get("memory_evidence")
    if isinstance(memory_evidence, dict):
        data["memory_limit_bytes"] = memory_evidence.get(
            "memory_limit_bytes", data.get("memory_limit_bytes")
        )
        data["effective_memory_limit_bytes"] = memory_evidence.get(
            "effective_memory_limit_bytes"
        )
    data.update(_storage_fields(data))
    if data.get("methodology_version") == V8_METHODOLOGY:
        data["bounded_stream_record_gate"] = _v8_batch_contract_valid(data)
    else:
        data["bounded_stream_record_gate"] = _record_bounded_gate(data)
    return data


def _diagnostic_storage_metadata(
    filesystem_path: Path, *, target_container: bool
) -> dict[str, object]:
    """Attach the same storage provenance shape used by workflow records.

    The discard diagnostic has no ``WorkflowMeasurement`` to pass through
    ``_record``.  Keep its storage evidence explicit so target diagnostics
    cannot silently move back to an overlay or temporary filesystem.
    """

    try:
        root_identity = storage_root_identity(filesystem_path)
    except OSError:
        root_identity = ""
    filesystem = _filesystem_type(filesystem_path)
    storage_layout = _load_storage_layout() if target_container else None
    mount_verified = bool(
        target_container
        and storage_layout is not None
        and storage_layout.mount_type == "volume"
        and storage_layout.read_write
        and storage_layout.filesystem_type == filesystem
        and storage_layout.storage_root_identity == root_identity
        and storage_layout.data_root.resolve() == filesystem_path.resolve()
        and storage_layout.destination.resolve() == filesystem_path.resolve()
    )
    return {
        "filesystem_type": filesystem,
        "volume_backend": storage_layout.mount_type
        if mount_verified and storage_layout is not None
        else "unknown",
        "storage_root_identity": root_identity,
        "storage_mount_verified": mount_verified,
        "storage_layout_version": storage_layout.storage_layout_version
        if storage_layout is not None
        else None,
        "storage_volume_project": storage_layout.volume_project
        if storage_layout is not None
        else None,
    }


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


def _publish_v8_summary_report(output: Path, summary: dict[str, object]) -> None:
    summary_path = output.with_suffix(".summary.json")
    report_path = output.with_suffix(".md")
    staged: list[tuple[Path, Path]] = []
    try:
        for target, content in (
            (summary_path, json.dumps(summary, indent=2, sort_keys=True) + "\n"),
            (report_path, _markdown_v8(summary)),
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


def _markdown_v8(summary: dict[str, object]) -> str:
    matrix = cast(dict[str, dict[str, object]], summary["candidate_matrix"])
    candidate_a = matrix.get(
        Candidate.A.value,
        {
            "batch_safety_gate": "n/a",
            "scale_ratio_observation": "n/a",
            "capacity_advisory_status": "n/a",
            "hard_gate": None,
            "result": "not_evaluated",
        },
    )
    lines = [
        "# P2-R1 v8 Provider Feasibility Decision",
        "",
        f"- formal_status: `{summary['formal_status']}`",
        f"- selected_provider: `{summary['selected_provider']}`",
        "- candidate_b_status: `reserved_not_evaluated`",
        f"- p2_r2_ready: `{summary['p2_r2_ready']}`",
        f"- records: `{summary['records']}` / expected `66`",
        "",
        "| Candidate | Batch safety | Ratio observation | Capacity advisory | Hard gate | Result |",
        "|---|---:|---:|---:|---:|---:|",
        f"| {Candidate.A.value} | {candidate_a['batch_safety_gate']} | "
        f"{candidate_a['scale_ratio_observation']} | {candidate_a['capacity_advisory_status']} | "
        f"{candidate_a['hard_gate']} | {candidate_a['result']} |",
        f"| {Candidate.B.value} | n/a | n/a | n/a | null | not_evaluated |",
        "",
        "Ratio, absolute resource and capacity values are advisory in v8; safety, correctness, lifecycle, storage, provenance, batch and cleanup failures remain hard no-go conditions.",
    ]
    return "\n".join(lines) + "\n"


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


def _resolve_probe_data_root(
    settings: RepositoryServiceSettings,
    data_root: Path | None,
    target_container: bool,
) -> Path | None:
    """Select the storage root without measuring target overlay storage."""

    probe_root = data_root
    if probe_root is None and target_container:
        probe_root = settings.data_root
    if probe_root is None:
        return None
    if target_container:
        _validate_target_storage_root(probe_root)
    return probe_root


def _validate_target_storage_root(root: Path) -> None:
    """Require target measurements to use the launcher-verified named volume."""

    if not root.is_absolute():
        raise RuntimeError("target storage root must be absolute")
    storage_layout = _load_storage_layout()
    if storage_layout is None:
        raise RuntimeError("launcher storage layout manifest is missing")
    try:
        storage_layout.validate_root(
            root,
            project=os.environ.get("GATEWAY_P2R1_PROJECT_NAME"),
        )
    except StorageLayoutError as exc:
        raise RuntimeError(str(exc)) from exc


def _load_storage_layout() -> StorageLayout | None:
    path_value = os.environ.get("GATEWAY_P2R1_STORAGE_LAYOUT")
    if not path_value:
        return None
    try:
        return StorageLayout.load(Path(path_value))
    except StorageLayoutError:
        return None


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
    target_container = os.environ.get("GATEWAY_P2R1_TARGET_CONTAINER") == "1"
    storage_layout = _load_storage_layout() if target_container else None
    storage_manifest_valid = not target_container or storage_layout is not None
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
        "storage_manifest_valid": storage_manifest_valid,
        "storage_layout_version": storage_layout.storage_layout_version
        if storage_layout is not None
        else None,
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
            and storage_manifest_valid
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


def _valid_storage_identity(value: object) -> bool:
    return isinstance(value, str) and STORAGE_IDENTITY_PATTERN.fullmatch(value) is not None


def _valid_storage_file(value: object) -> bool:
    if not isinstance(value, dict):
        return False
    relative_path = value.get("relative_path")
    if not _valid_relative_path(relative_path):
        return False
    return (
        isinstance(relative_path, str)
        and isinstance(value.get("inode"), int)
        and isinstance(value.get("st_size"), int)
        and isinstance(value.get("st_blocks"), int)
        and isinstance(value.get("link_count"), int)
    )


def _valid_relative_path(value: object) -> bool:
    if not isinstance(value, str) or not value:
        return False
    relative = Path(value)
    return not relative.is_absolute() and relative != Path(".") and ".." not in relative.parts


def _storage_file_map(value: object) -> dict[str, dict[str, object]] | None:
    if not isinstance(value, list):
        return None
    result: dict[str, dict[str, object]] = {}
    for item in value:
        if not _valid_storage_file(item):
            return None
        entry = cast(dict[str, object], item)
        relative_path = cast(str, entry["relative_path"])
        if relative_path in result:
            return None
        result[relative_path] = entry
    return result


def _valid_changed_files(value: object) -> bool:
    if not isinstance(value, list):
        return False
    seen: set[str] = set()
    for item in value:
        if not isinstance(item, dict) or not isinstance(item.get("relative_path"), str):
            return False
        relative_path = cast(str, item["relative_path"])
        if not _valid_relative_path(relative_path):
            return False
        if relative_path in seen:
            return False
        seen.add(relative_path)
        before = item.get("before")
        after = item.get("after")
        if before is None and after is None:
            return False
        if before is not None and not _valid_storage_file(before):
            return False
        if after is not None and not _valid_storage_file(after):
            return False
    return True


def _w3_lifecycle_evidence_valid(record: dict[str, object]) -> bool:
    """Validate W3 lifecycle evidence from raw snapshots, not derived flags."""

    snapshots = record.get("storage_snapshots")
    deltas = record.get("storage_deltas")
    if not isinstance(snapshots, dict) or not isinstance(deltas, dict):
        return False
    if list(snapshots.keys()) != list(W3_STORAGE_SNAPSHOT_ORDER):
        return False
    if set(deltas.keys()) != set(W3_DELTA_STAGE_PAIRS):
        return False

    identities: set[str] = set()
    snapshot_values: dict[str, dict[str, object]] = {}
    snapshot_files: dict[str, dict[str, dict[str, object]]] = {}
    for stage in W3_STORAGE_SNAPSHOT_ORDER:
        snapshot = snapshots.get(stage)
        if not isinstance(snapshot, dict):
            return False
        snapshot_values[stage] = cast(dict[str, object], snapshot)
        if (
            snapshot.get("stage") != stage
            or snapshot.get("complete") is not True
            or snapshot.get("provider_closed") is not True
            or snapshot.get("server_reaped") is not True
            or snapshot.get("quiesce_status") != "quiesced"
        ):
            return False
        if not all(
            isinstance(snapshot.get(name), int)
            for name in ("logical_bytes", "allocated_bytes")
        ):
            return False
        files = _storage_file_map(snapshot.get("files"))
        if files is None:
            return False
        snapshot_files[stage] = files
        identity = snapshot.get("storage_root_identity")
        if not _valid_storage_identity(identity):
            return False
        identities.add(cast(str, identity))

    if len(identities) != 1:
        return False
    for name, (before_stage, after_stage) in W3_DELTA_STAGE_PAIRS.items():
        delta = deltas.get(name)
        if not isinstance(delta, dict):
            return False
        if (
            delta.get("before_stage") != before_stage
            or delta.get("after_stage") != after_stage
            or not isinstance(delta.get("logical_delta_bytes"), int)
            or not isinstance(delta.get("allocated_delta_bytes"), int)
            or delta.get("logical_delta_bytes")
            != cast(int, snapshot_values[after_stage]["logical_bytes"])
            - cast(int, snapshot_values[before_stage]["logical_bytes"])
            or delta.get("allocated_delta_bytes")
            != cast(int, snapshot_values[after_stage]["allocated_bytes"])
            - cast(int, snapshot_values[before_stage]["allocated_bytes"])
            or delta.get("allocated_delta_semantics") != "signed_net_allocated_blocks"
            or delta.get("physical_reclamation_observed")
            != (cast(int, delta.get("allocated_delta_bytes")) < 0)
            or not _valid_changed_files(delta.get("changed_files"))
        ):
            return False
        before_files = snapshot_files[before_stage]
        after_files = snapshot_files[after_stage]
        expected_changed_files = [
            {
                "relative_path": relative_path,
                "before": before_files.get(relative_path),
                "after": after_files.get(relative_path),
            }
            for relative_path in sorted(set(before_files) | set(after_files))
            if before_files.get(relative_path) != after_files.get(relative_path)
        ]
        if delta.get("changed_files") != expected_changed_files:
            return False
    return True


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
    raw_deltas = record.get("storage_deltas")
    deltas = raw_deltas if isinstance(raw_deltas, dict) else {}
    comparable = deltas.get("comparable_delta")
    if isinstance(comparable, dict):
        comparable_logical = comparable.get("logical_delta_bytes")
        comparable_allocated = comparable.get("allocated_delta_bytes")
        if isinstance(comparable_logical, int):
            logical_delta = comparable_logical
        if isinstance(comparable_allocated, int):
            allocated_delta = comparable_allocated
    snapshots = record.get("storage_snapshots")
    lifecycle_valid = _w3_lifecycle_evidence_valid(record)
    snapshot_complete = lifecycle_valid
    snapshot_order = (
        list(snapshots.keys()) if isinstance(snapshots, dict) else []
    )
    w3_lifecycle_complete = lifecycle_valid
    physical_reclamation = (
        isinstance(allocated_delta, int) and allocated_delta < 0
    )
    return {
        "change_ratio": change_ratio,
        "logical_delta_bytes": logical_delta,
        "allocated_delta_bytes": allocated_delta,
        "allocated_delta_semantics": "signed_net_allocated_blocks",
        "physical_reclamation_observed": physical_reclamation,
        "quiesce_status": "quiesced"
        if record.get("storage_quiesced") is True
        else "unavailable",
        "w1_full_commit_logical_bytes": None,
        "logical_delta_vs_w1_full_ratio": None,
        "full_rewrite_observed": None,
        "full_rewrite_explanation": "pending W1 comparison"
        if change_ratio is not None
        else None,
        "storage_snapshots": snapshots if isinstance(snapshots, dict) else {},
        "storage_deltas": deltas,
        "storage_snapshot_order": snapshot_order,
        "storage_snapshot_complete": snapshot_complete,
        "storage_lifecycle_complete": w3_lifecycle_complete,
        "base_restart_delta": deltas.get("base_restart_delta"),
        "delta_commit_delta": deltas.get("delta_commit_delta"),
        "delta_restart_delta": deltas.get("delta_restart_delta"),
        "comparable_delta": comparable,
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
    derived_storage = _storage_fields(record)
    for key in (
        "storage_snapshots",
        "storage_deltas",
        "storage_snapshot_order",
        "storage_snapshot_complete",
        "storage_lifecycle_complete",
        "base_restart_delta",
        "delta_commit_delta",
        "delta_restart_delta",
        "comparable_delta",
        "allocated_delta_semantics",
        "physical_reclamation_observed",
    ):
        record.setdefault(key, derived_storage[key])
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
        and record.get("storage_snapshot_complete") is True
        and record.get("storage_lifecycle_complete") is True
        and _w3_lifecycle_evidence_valid(record)
        and record.get("storage_mount_verified") is True
        else "inconclusive"
    )


def _annotate_storage(records: list[dict[str, object]]) -> None:
    full_by_candidate: dict[str, int] = {}
    for record in records:
        _observe_storage_record(record, full_by_candidate)


def _candidate_storage_provenance(
    records: list[dict[str, object]], candidate: str
) -> tuple[bool, str]:
    candidate_rows = [
        row
        for row in records
        if row.get("candidate") == candidate
        and row.get("matrix_kind", "normal") in {"normal", "scaling"}
    ]
    if not candidate_rows:
        return False, "candidate has no measurement records"
    identities: set[str] = set()
    for row in candidate_rows:
        if row.get("storage_mount_verified") is not True:
            return False, "storage mount is not verified for every record"
        if row.get("volume_backend") != "volume":
            return False, "storage backend is not a verified named volume"
        filesystem_type = row.get("filesystem_type")
        if not isinstance(filesystem_type, str) or filesystem_type.lower() in {"", "unknown", "overlayfs"}:
            return False, "storage filesystem is unavailable or overlayfs"
        identity = row.get("storage_root_identity")
        if not _valid_storage_identity(identity):
            return False, "storage root identity is invalid"
        identities.add(cast(str, identity))
        if row.get("storage_layout_version") != STORAGE_LAYOUT_VERSION:
            return False, "storage layout version is invalid"
    if len(identities) != 1:
        return False, "storage root identity is inconsistent"
    return True, "complete"


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
    candidates: tuple[Candidate, ...] = (Candidate.B,),
    restart_before_stream: bool = False,
) -> dict[str, object]:
    """Run scaling records as diagnostic-only evidence."""

    if measured_runs != 5:
        raise ValueError("P2-R1 requires exactly five measured runs")
    target_container = os.environ.get("GATEWAY_P2R1_TARGET_CONTAINER") == "1"
    probe_data_root = _resolve_probe_data_root(settings, data_root, target_container)
    isolated = target_container
    if target_container:
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
        settings = settings.model_copy(update={"cgroup_root": sample_root})
    _ensure_artifacts_absent(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    records: list[dict[str, object]] = []
    fixture_context = tempfile.TemporaryDirectory(prefix="gateway-p2r1-scaling-fixtures-")
    root_context = (
        tempfile.TemporaryDirectory(prefix="gateway-p2r1-scaling-target-")
        if probe_data_root is None
        else None
    )
    try:
        fixture_root = Path(fixture_context.name)
        probe_root = (
            probe_data_root
            if probe_data_root is not None
            else Path(root_context.name)  # type: ignore[union-attr]
        )
        records = _collect_scaling_records(
            settings,
            fixture_root,
            probe_root,
            measured_runs,
            image_digest=image_digest,
            build_revision=build_revision,
            cache_condition=cache_condition,
            candidates=candidates,
            isolated=isolated,
            restart_before_stream=restart_before_stream,
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
            "diagnostic_candidates": [candidate.value for candidate in candidates],
            "formal_decision": False,
            "p2_r1_exit": "no-go",
            "round_exit": "diagnostic-no-go",
            "selected_provider": None,
            "next_round_ready": False,
            "p2_r2_ready": False,
            # _summarize() uses ``records`` for the normal-matrix count.  A
            # scaling-only diagnostic must expose its actual raw count too;
            # preserve ``scaling_records`` for compatibility and make the
            # diagnostic total unambiguous for future artifacts.
            "records": len(records),
            "scaling_records": len(records),
            "unique_measurement_keys": len(
                {
                    (
                        row.get("candidate"),
                        row.get("workload"),
                        row.get("record_batch_row_bound"),
                        row.get("sample_kind"),
                    )
                    for row in records
                }
            ),
        }
    )
    _write_artifacts(output, records, summary)
    return summary


def _discard_diagnostic_record(
    fixture: Fixture,
    measurement: dict[str, object],
    probe_root: Path,
    *,
    row_bound: int,
    metadata: dict[str, object],
) -> dict[str, object]:
    target_container = os.environ.get("GATEWAY_P2R1_TARGET_CONTAINER") == "1"
    record = dict(measurement)
    record.update(
        {
            "candidate": Candidate.A.value,
            "workload": fixture.workload.value,
            "dataset_id": fixture.dataset_id,
            "synthetic": fixture.synthetic,
            "package_bytes": fixture.package_bytes,
            "fixture_rows": fixture.rows,
            "python_version": platform.python_version(),
            "cpu_count": os.cpu_count(),
            "matrix_kind": "scaling",
            "diagnostic_variant": "devnull",
            "record_batch_row_bound": row_bound,
            "record_batch_byte_bound": BYTE_BOUND,
            "row_bound_applied": False,
            "cache_state": "warmup"
            if measurement.get("sample_kind") == "warmup"
            else "warm",
        }
    )
    record.update(_diagnostic_storage_metadata(probe_root, target_container=target_container))
    record.update(metadata)
    record["methodology_version"] = metadata.get(
        "measurement_methodology_version", "unknown"
    )
    record["metadata_complete"] = bool(metadata.get("metadata_complete"))
    record["bounded_stream_record_gate"] = False
    record["diagnostic_only"] = True
    return record


def run_a_paired_devnull_diagnostic(
    settings: RepositoryServiceSettings,
    output: Path,
    *,
    data_root: Path | None = None,
    measured_runs: int = 5,
    image_digest: str | None = None,
    build_revision: str | None = None,
    cache_condition: str | None = None,
) -> dict[str, object]:
    """Compare Candidate A streaming with direct-DEVNULL output.

    This diagnostic is intentionally not part of formal selection.  Direct
    DEVNULL uses time-fraction windows because its stdout carries no row
    framing; the raw records state that explicitly.
    """

    if measured_runs != 5:
        raise ValueError("P2-R1 requires exactly five measured runs")
    target_container = os.environ.get("GATEWAY_P2R1_TARGET_CONTAINER") == "1"
    probe_data_root = _resolve_probe_data_root(settings, data_root, target_container)
    if target_container:
        topology = load_cgroup_topology(settings.cgroup_layout)
        cgroup_input = topology.samples if topology is not None else settings.cgroup_root
        if cgroup_input is None:
            raise RuntimeError("target diagnostic requires delegated cgroup topology")
        sample_root = preflight_cgroup(cgroup_input, topology)
        settings = settings.model_copy(update={"cgroup_root": sample_root})
    _ensure_artifacts_absent(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    fixture_context = tempfile.TemporaryDirectory(prefix="gateway-p2r1-a-paired-fixtures-")
    root_context = (
        tempfile.TemporaryDirectory(prefix="gateway-p2r1-a-paired-target-")
        if probe_data_root is None
        else None
    )
    metadata = _measurement_metadata(
        settings,
        image_digest=image_digest,
        build_revision=build_revision,
        cache_condition=cache_condition,
    )
    records: list[dict[str, object]] = []
    try:
        fixture_root = Path(fixture_context.name)
        probe_root = (
            probe_data_root
            if probe_data_root is not None
            else Path(root_context.name)  # type: ignore[union-attr]
        )
        streaming_records = _collect_scaling_records(
            settings,
            fixture_root,
            probe_root,
            measured_runs,
            image_digest=image_digest,
            build_revision=build_revision,
            cache_condition=cache_condition,
            candidates=(Candidate.A,),
            isolated=True if target_container else False,
        )
        for record in streaming_records:
            record["diagnostic_variant"] = "streaming"
            record["diagnostic_only"] = True
        records.extend(streaming_records)
        for scale in SCALE_WORKLOADS:
            fixture = generate_scale_fixture(fixture_root, scale)
            for bound in ROW_BOUNDS:
                bound_settings = settings.model_copy(
                    update={"record_batch_rows": bound, "record_batch_bytes": BYTE_BOUND}
                )
                for sample_kind in EXPECTED_SAMPLE_KINDS:
                    if target_container:
                        measurement = run_offline_discard_workflow_isolated(
                            bound_settings,
                            fixture,
                            sample_kind=sample_kind,
                            root_parent=probe_root,
                        )
                    else:
                        measurement = run_offline_discard_diagnostic(
                            bound_settings,
                            fixture,
                            sample_kind=sample_kind,
                            root_parent=probe_root,
                        )
                    records.append(
                        _discard_diagnostic_record(
                            fixture,
                            measurement,
                            probe_root,
                            row_bound=bound,
                            metadata=metadata,
                        )
                    )
    finally:
        fixture_context.cleanup()
        if root_context is not None:
            root_context.cleanup()
    streaming_records = [
        row for row in records if row.get("diagnostic_variant") == "streaming"
    ]
    summary = _summarize([], settings, scaling_records=streaming_records)
    summary.update(
        {
            "decision_kind": "diagnostic",
            "diagnostic_kind": "candidate_a_paired_devnull",
            "diagnostic_variants": ["streaming", "devnull"],
            "formal_decision": False,
            "p2_r1_exit": "no-go",
            "round_exit": "diagnostic-no-go",
            "selected_provider": None,
            "proposed_provider": None,
            "next_round_ready": False,
            "p2_r2_ready": False,
            "records": len(records),
            "streaming_records": len(streaming_records),
            "devnull_records": len(records) - len(streaming_records),
            "unique_measurement_keys": len(
                {
                    (
                        row.get("candidate"),
                        row.get("diagnostic_variant"),
                        row.get("workload"),
                        row.get("record_batch_row_bound"),
                        row.get("sample_kind"),
                    )
                    for row in records
                }
            ),
            "window_basis": "time_fraction for direct DEVNULL; row_fraction for streaming",
        }
    )
    _write_artifacts(output, records, summary)
    return summary


def run_offline_discard_diagnostic_matrix(
    settings: RepositoryServiceSettings,
    output: Path,
    *,
    data_root: Path | None = None,
    image_digest: str | None = None,
    build_revision: str | None = None,
    cache_condition: str | None = None,
) -> dict[str, object]:
    """Run Candidate A same-SELECT discard evidence for S10/S40/S100.

    This is deliberately separate from the formal matrix: it does not emit
    bounded-stream records or make a provider decision.
    """

    _ensure_artifacts_absent(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    fixture_context = tempfile.TemporaryDirectory(
        prefix="gateway-p2r1-discard-fixtures-"
    )
    target_container = os.environ.get("GATEWAY_P2R1_TARGET_CONTAINER") == "1"
    probe_data_root = _resolve_probe_data_root(settings, data_root, target_container)
    metadata = _measurement_metadata(
        settings,
        image_digest=image_digest,
        build_revision=build_revision,
        cache_condition=cache_condition,
    )
    root_context = (
        tempfile.TemporaryDirectory(prefix="gateway-p2r1-discard-target-")
        if probe_data_root is None
        else None
    )
    records: list[dict[str, object]] = []
    try:
        fixture_root = Path(fixture_context.name)
        probe_root = (
            probe_data_root
            if probe_data_root is not None
            else Path(root_context.name)  # type: ignore[union-attr]
        )
        for scale in SCALE_WORKLOADS:
            fixture = generate_scale_fixture(fixture_root, scale)
            record = run_offline_discard_diagnostic(
                settings, fixture, root_parent=probe_root
            )
            record.update(metadata)
            record.update(
                {
                    "methodology_version": settings.measurement_methodology_version,
                    "matrix_kind": "scaling",
                    "storage_probe_root": "target-data-root"
                    if target_container
                    else "diagnostic-temporary-root",
                }
            )
            record.update(
                _diagnostic_storage_metadata(
                    probe_root, target_container=target_container
                )
            )
            records.append(record)
    finally:
        fixture_context.cleanup()
        if root_context is not None:
            root_context.cleanup()
    filesystem_types = sorted(
        {str(row["filesystem_type"]) for row in records if row.get("filesystem_type")}
    )
    volume_backends = sorted(
        {str(row["volume_backend"]) for row in records if row.get("volume_backend")}
    )
    storage_root_identities = sorted(
        {
            str(row["storage_root_identity"])
            for row in records
            if row.get("storage_root_identity")
        }
    )
    summary = _summarize([], settings, scaling_records=records)
    measurement_environment = summary.get("measurement_environment")
    if not isinstance(measurement_environment, dict):
        measurement_environment = {}
    measurement_environment.update(
        {
            "filesystem_types": filesystem_types,
            "volume_backends": volume_backends,
            "storage_root_identities": storage_root_identities,
            "storage_mount_verified": bool(records)
            and all(row.get("storage_mount_verified") is True for row in records),
            "storage_layout_versions": sorted(
                {
                    str(row["storage_layout_version"])
                    for row in records
                    if row.get("storage_layout_version")
                }
            ),
        }
    )
    summary["measurement_environment"] = measurement_environment
    summary.update(
        {
            "decision_kind": "diagnostic",
            "diagnostic_kind": "offline_cli_discard_to_devnull",
            "formal_decision": False,
            "p2_r1_exit": "no-go",
            "round_exit": "diagnostic-no-go",
            "selected_provider": None,
            "next_round_ready": False,
            "p2_r2_ready": False,
            "records": len(records),
            "methodology_version": settings.measurement_methodology_version,
            "metadata_complete": bool(records)
            and all(row.get("metadata_complete") is True for row in records),
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
            and row.get("allocated_delta_semantics") == "signed_net_allocated_blocks"
            and row.get("storage_snapshot_complete") is True
            and row.get("storage_lifecycle_complete") is True
            and _w3_lifecycle_evidence_valid(row)
            and row.get("storage_mount_verified") is True
            for row in w3_rows
        )
        bounded_status, bounded_reason, bounded_ratios = _bounded_stream_gate(
            candidate.value, scaling_rows
        )
        candidate_rows = [row for row in all_records if row.get("candidate") == candidate.value]
        failure_counts = _failure_counts(candidate_rows)
        storage_provenance_complete, storage_provenance_reason = _candidate_storage_provenance(
            all_records, candidate.value
        )
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
            and storage_provenance_complete
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
            "storage_provenance_complete": storage_provenance_complete,
            "storage_provenance_reason": storage_provenance_reason,
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
    filesystem_types = sorted(
        {str(row.get("filesystem_type")) for row in all_records if row.get("filesystem_type")}
    )
    volume_backends = sorted(
        {str(row.get("volume_backend")) for row in all_records if row.get("volume_backend")}
    )
    storage_root_identities = sorted(
        {
            str(row.get("storage_root_identity"))
            for row in all_records
            if row.get("storage_root_identity")
        }
    )
    storage_mount_values = [row.get("storage_mount_verified") for row in all_records]
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
            "filesystem_types": filesystem_types,
            "volume_backends": volume_backends,
            "storage_root_identities": storage_root_identities,
            "storage_mount_verified": bool(storage_mount_values)
            and all(value is True for value in storage_mount_values),
            "environment_class": "development-equivalent-smoke",
            "production_environment_assessed": False,
        },
        "decision_scope": "current_measurement_environment_only",
        "production_retest_required": True,
    }


def _v8_expected_keys(matrix_kind: str) -> set[tuple[str, ...]]:
    if matrix_kind == "normal":
        return {
            (Candidate.A.value, workload.value, "1024", sample)
            for workload in NORMAL_WORKLOADS
            for sample in EXPECTED_SAMPLE_KINDS
        }
    return {
        (Candidate.A.value, scale.value, str(bound), sample)
        for scale in SCALE_WORKLOADS
        for bound in ROW_BOUNDS
        for sample in EXPECTED_SAMPLE_KINDS
    }


def _v8_record_key(row: dict[str, object], matrix_kind: str) -> tuple[str, ...]:
    return (
        str(row.get("candidate")),
        str(row.get("workload")),
        str(row.get("record_batch_row_bound")) if matrix_kind == "scaling" else "1024",
        str(row.get("sample_kind")),
    )


def _v8_complete_memory_peaks(value: object) -> bool:
    if not isinstance(value, dict):
        return False

    def valid_peak(item: object) -> bool:
        return isinstance(item, (int, float)) and float(item) >= 0

    return all(
        isinstance(value.get(subject), dict)
        and all(
            valid_peak(cast(dict[str, object], value[subject]).get(window))
            for window in WINDOW_NAMES
        )
        for subject in MEMORY_SUBJECTS
    )


def _v8_coverage(
    records: list[dict[str, object]], matrix_kind: str
) -> tuple[bool, dict[str, int | bool | str]]:
    expected = _v8_expected_keys(matrix_kind)
    selected = [row for row in records if row.get("matrix_kind") == matrix_kind]
    actual = {_v8_record_key(row, matrix_kind) for row in selected}
    duplicates = len(selected) != len(actual)
    complete = not duplicates and actual == expected
    return complete, {
        "complete": complete,
        "expected": len(expected),
        "actual": len(selected),
        "unique": len(actual),
        "duplicates": int(duplicates),
        "missing": len(expected - actual),
        "extra": len(actual - expected),
    }


def _v8_memory_evidence_valid(row: dict[str, object]) -> bool:
    evidence = row.get("memory_evidence")
    if not isinstance(evidence, dict):
        return False
    return bool(
        evidence.get("coverage") == "available"
        and evidence.get("baseline_coverage") is True
        and evidence.get("cgroup_stat_coverage") is True
        and _v8_complete_memory_peaks(evidence.get("plateau_peaks"))
        and _v8_complete_memory_peaks(evidence.get("plateau_peaks_absolute"))
        and evidence.get("memory_limit_bytes") == V8_MEMORY_LIMIT_BYTES
        and isinstance(evidence.get("effective_memory_limit_bytes"), int)
        and cast(int, evidence["effective_memory_limit_bytes"]) >= V8_MEMORY_LIMIT_BYTES
        and isinstance(evidence.get("cgroup_memory_peak_bytes"), int)
        and cast(int, evidence["cgroup_memory_peak_bytes"]) >= 0
    )


def _v8_batch_contract_valid(row: dict[str, object]) -> bool:
    total_rows = row.get("total_rows")
    payload_bytes = row.get("total_stream_payload_bytes")
    batch_count = row.get("batch_count")
    max_batch_rows = row.get("max_batch_rows")
    max_batch_bytes = row.get("max_batch_bytes")
    row_bound = row.get("record_batch_row_bound")
    byte_bound = row.get("record_batch_byte_bound")
    basic = (
        row.get("batch_contract_valid") is True
        and row.get("batch_contract_violation_count") == 0
        and all(isinstance(value, int) and value >= 0 for value in (
            total_rows,
            payload_bytes,
            batch_count,
            max_batch_rows,
            max_batch_bytes,
        ))
        and isinstance(row_bound, int)
        and isinstance(byte_bound, int)
        and byte_bound == V8_BYTE_BOUND
    )
    if not basic:
        return False
    assert isinstance(total_rows, int)
    assert isinstance(batch_count, int)
    assert isinstance(max_batch_rows, int)
    assert isinstance(max_batch_bytes, int)
    assert isinstance(row_bound, int)
    assert isinstance(byte_bound, int)
    if total_rows == 0:
        if batch_count != 0 or max_batch_rows != 0 or max_batch_bytes != 0:
            return False
    elif batch_count == 0 or max_batch_rows < 1 or max_batch_rows > row_bound:
        return False
    oversized = row.get("oversized_single_row") is True
    if max_batch_bytes > byte_bound and not oversized:
        return False
    if row.get("encoded_line_applicable") is True and (
        row.get("encoded_line_bound_valid") is not True
        or not isinstance(row.get("max_encoded_line_bytes"), int)
        or not isinstance(row.get("encoded_line_bound"), int)
        or cast(int, row["max_encoded_line_bytes"])
        > cast(int, row["encoded_line_bound"])
    ):
        return False
    return True


def _v8_ratio_observation(
    records: list[dict[str, object]],
) -> tuple[str, dict[str, float], str | None]:
    if not records or any(not _v8_memory_evidence_valid(row) for row in records):
        return "unavailable", {}, "required absolute memory evidence is incomplete"
    measured = [
        row
        for row in records
        if row.get("matrix_kind") == "scaling"
        and str(row.get("sample_kind", "")).startswith("measured-")
    ]
    ratios: dict[str, float] = {}
    status = "pass"
    for bound in ROW_BOUNDS:
        for subject in MEMORY_SUBJECTS:
            for window in WINDOW_NAMES:
                scale_peaks: dict[str, float] = {}
                for scale in SCALE_WORKLOADS:
                    values = [
                        _plateau_value(row, subject, window)
                        for row in measured
                        if row.get("record_batch_row_bound") == bound
                        and row.get("workload") == scale.value
                    ]
                    if len(values) != 5:
                        return "unavailable", ratios, "missing measured scale evidence"
                    scale_peaks[scale.value] = max(values)
                peaks = list(scale_peaks.values())
                minimum = min(peaks)
                ratio = 1.0 if max(peaks) == 0 else float("inf") if minimum == 0 else max(peaks) / minimum
                ratios[f"bound_{bound}_{subject}_{window}_ratio"] = ratio
                for scale_name, value in scale_peaks.items():
                    ratios[f"bound_{bound}_{subject}_{window}_{scale_name}"] = value
                if ratio > 1.5:
                    status = "warning"
    return status, ratios, None


def _v8_capacity_advisory(
    records: list[dict[str, object]],
) -> tuple[str, float | None]:
    values = [
        float(cast(int | float, row["import_seconds"]))
        for row in records
        if row.get("workload") == Workload.W1.value
        and str(row.get("sample_kind", "")).startswith("measured-")
        and isinstance(row.get("import_seconds"), (int, float))
    ]
    if not values:
        return "unavailable", None
    projection = 4 * 86400 * 0.70 / max(values)
    return ("within_reference" if projection >= 1000 else "below_reference"), projection


def _v8_resource_advisory(
    records: list[dict[str, object]],
) -> dict[str, object]:
    exceedances: list[dict[str, object]] = []
    observed: list[int] = []
    for row in records:
        evidence = row.get("memory_evidence")
        peak = (
            evidence.get("cgroup_memory_peak_bytes")
            if isinstance(evidence, dict)
            else None
        )
        if not isinstance(peak, int):
            continue
        observed.append(peak)
        reference = (
            3 * 1024 * 1024 * 1024
            if row.get("workload") == Workload.W2.value
            else 2_500 * 1024 * 1024
        )
        if peak > reference:
            exceedances.append(
                {
                    "record_key": _v8_record_key(row, str(row.get("matrix_kind"))),
                    "observed_peak_bytes": peak,
                    "reference_bytes": reference,
                }
            )
    return {
        "ordinary_workflow_reference_bytes": 2684354560,
        "boundary_workflow_reference_bytes": 3221225472,
        "service_reference_bytes": 8589934592,
        "four_worker_burst_reference_bytes": 17179869184,
        "recommended_concurrency": 2,
        "observed_max_workflow_cgroup_peak_bytes": max(observed) if observed else None,
        "exceedances": exceedances,
        "status": "above_reference" if exceedances else "within_reference",
        "affects_formal_decision": False,
    }


def _summarize_v8(
    records: list[dict[str, object]], settings: RepositoryServiceSettings
) -> dict[str, object]:
    normal = [row for row in records if row.get("matrix_kind") == "normal"]
    scaling = [row for row in records if row.get("matrix_kind") == "scaling"]
    normal_complete, normal_counts = _v8_coverage(records, "normal")
    scaling_complete, scaling_counts = _v8_coverage(records, "scaling")
    candidate_rows = [row for row in records if row.get("candidate") == Candidate.A.value]
    record_set_valid = len(records) == 66 and all(
        row.get("candidate") == Candidate.A.value for row in records
    )
    failures = _failure_counts(candidate_rows)
    storage_complete, storage_reason = _candidate_storage_provenance(
        records, Candidate.A.value
    )
    support_envelope_complete = bool(candidate_rows) and all(
        row.get("support_envelope") == "validated" for row in candidate_rows
    )
    metadata_complete = bool(candidate_rows) and all(
        row.get("metadata_complete") is True for row in candidate_rows
    )
    batch_complete = bool(candidate_rows) and all(
        _v8_batch_contract_valid(row) for row in candidate_rows
    )
    memory_complete = bool(candidate_rows) and all(
        _v8_memory_evidence_valid(row) for row in candidate_rows
    )
    w3_rows = [
        row for row in normal
        if row.get("workload") in {Workload.W3_1.value, Workload.W3_10.value}
    ]
    w3_complete = bool(w3_rows) and all(
        row.get("storage_evidence_status") == "available"
        and row.get("storage_snapshot_complete") is True
        and _w3_lifecycle_evidence_valid(row)
        for row in w3_rows
    )
    workflow_gates = all(
        isinstance(row.get("hard_gates"), dict)
        and all(
            cast(dict[str, object], row["hard_gates"]).get(name) is True
            for name in ("workflow", "cancellation", "restart", "unknown_type")
        )
        for row in candidate_rows
    )
    hard_gate = bool(
        record_set_valid
        and normal_complete
        and scaling_complete
        and not _sample_failures(candidate_rows)
        and workflow_gates
        and batch_complete
        and memory_complete
        and w3_complete
        and storage_complete
        and support_envelope_complete
        and metadata_complete
    )
    ratio_status, ratios, ratio_reason = _v8_ratio_observation(scaling)
    capacity_status, capacity_projection = _v8_capacity_advisory(records)
    resource_advisory = _v8_resource_advisory(records)
    outcome = "go" if hard_gate else "no-go"
    actual_warmups = sum(row.get("sample_kind") == "warmup" for row in records)
    unique_keys = {
        (str(row.get("matrix_kind")), _v8_record_key(row, str(row.get("matrix_kind"))))
        for row in records
    }
    candidate_entry = {
        "status": "evaluated",
        "workloads": sorted({str(row.get("workload")) for row in candidate_rows}),
        "matrix_coverage_complete": normal_complete and scaling_complete,
        "batch_safety_gate": batch_complete,
        "bounded_stream_gate": batch_complete,
        "bounded_stream_gate_semantics": "batch_contract_v8",
        "scale_ratio_observation": ratio_status,
        "scale_ratio_reason": ratio_reason,
        "scale_ratios": ratios,
        "capacity_advisory_status": capacity_status,
        "capacity_projection_imports_per_day": capacity_projection,
        "storage_provenance_complete": storage_complete,
        "storage_provenance_reason": storage_reason,
        "support_envelope_complete": support_envelope_complete,
        "metadata_complete": metadata_complete,
        "memory_evidence_complete": memory_complete,
        **failures,
        "hard_gate": hard_gate,
        "result": "pass" if hard_gate else "fail",
    }
    candidate_b = {
        "status": "reserved_not_evaluated",
        "hard_gate": None,
        "result": "not_evaluated",
    }
    return {
        "round": "P2-R1",
        "methodology_version": settings.measurement_methodology_version,
        "formal_status": outcome,
        "measurement_outcome": outcome,
        "p2_r1_exit": outcome,
        "round_exit": outcome,
        "selected_provider": Candidate.A.value if hard_gate else None,
        "proposed_provider": Candidate.A.value if hard_gate else None,
        "next_round_ready": hard_gate,
        "p2_r2_ready": hard_gate,
        "candidate_b_status": "reserved_not_evaluated",
        "formal_decision": True,
        "production_retest_required": hard_gate,
        "candidate_matrix": {
            Candidate.A.value: candidate_entry,
            Candidate.B.value: candidate_b,
        },
        "records": len(records),
        "normal_records": len(normal),
        "scaling_records": len(scaling),
        "unique_measurement_keys": len(unique_keys),
        "performance_excluded_warmups": actual_warmups,
        "expected_records": 66,
        "expected_normal_records": 30,
        "expected_scaling_records": 36,
        "expected_warmups": 11,
        "execution_errors": failures["execution_errors"],
        "correctness_failures": failures["correctness_failures"],
        "sample_failures": _sample_failures(records),
        "coverage": {
            "normal": normal_counts,
            "scaling": scaling_counts,
            "complete": normal_complete and scaling_complete,
            "record_set_valid": record_set_valid,
        },
        "resource_advisory": resource_advisory,
        "resource_advisory_status": resource_advisory["status"],
        "capacity_advisory_status": capacity_status,
        "methodology": {
            "version": settings.measurement_methodology_version,
            "candidates": [Candidate.A.value],
            "reserved_candidates": [Candidate.B.value],
            "normal_row_bound": 1024,
            "row_bounds": list(ROW_BOUNDS),
            "byte_bound": V8_BYTE_BOUND,
            "bounded_stream_gate_semantics": "batch_contract_v8",
            "ratio_semantics": "observation_only",
            "memory_limit_bytes": V8_MEMORY_LIMIT_BYTES,
        },
        "measurement_environment": {
            "dolt_version": settings.dolt_version,
            "image_digests": sorted({str(row.get("image_digest")) for row in records}),
            "build_revisions": sorted({str(row.get("build_revision")) for row in records}),
            "filesystem_types": sorted({str(row.get("filesystem_type")) for row in records}),
            "volume_backends": sorted({str(row.get("volume_backend")) for row in records}),
            "storage_mount_verified": all(
                row.get("storage_mount_verified") is True for row in records
            ),
        },
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
    parser.add_argument("--v8-formal", action="store_true")
    parser.add_argument("--data-root", type=Path)
    parser.add_argument("--runs", type=int, default=5)
    parser.add_argument("--image-digest")
    parser.add_argument("--build-revision")
    parser.add_argument("--cache-condition")
    parser.add_argument("--restart-before-stream", action="store_true")
    parser.add_argument(
        "--candidates",
        nargs="+",
        choices=[candidate.value for candidate in Candidate],
    )
    parser.add_argument("--diagnostic", action="store_true")
    parser.add_argument("--scaling-diagnostic", action="store_true")
    parser.add_argument("--offline-discard-diagnostic", action="store_true")
    parser.add_argument("--a-paired-diagnostic", action="store_true")
    parser.add_argument("--reserved-b-w0-smoke", action="store_true")
    parser.add_argument("--workloads", nargs="+", choices=[workload.value for workload in Workload])
    args = parser.parse_args()
    if args.v8_formal and (
        args.diagnostic
        or args.scaling_diagnostic
        or args.offline_discard_diagnostic
        or args.a_paired_diagnostic
        or args.workloads
        or args.candidates
        or args.restart_before_stream
    ):
        parser.error("--v8-formal cannot be combined with diagnostic options")
    if args.reserved_b_w0_smoke and (
        args.v8_formal
        or args.scaling_diagnostic
        or args.offline_discard_diagnostic
        or args.a_paired_diagnostic
        or args.workloads
        or args.candidates
    ):
        parser.error("reserved B W0 smoke is a standalone diagnostic")
    if args.workloads and not args.diagnostic:
        parser.error("--workloads is diagnostic-only; add --diagnostic")
    diagnostic_modes = sum(
        bool(value)
        for value in (
            args.diagnostic,
            args.scaling_diagnostic,
            args.offline_discard_diagnostic,
            args.a_paired_diagnostic,
            args.reserved_b_w0_smoke,
        )
    )
    if diagnostic_modes > 1:
        parser.error("diagnostic modes are mutually exclusive")
    if args.workloads and (
        args.scaling_diagnostic
        or args.offline_discard_diagnostic
        or args.a_paired_diagnostic
    ):
        parser.error("--workloads is only valid with --diagnostic")
    if args.restart_before_stream and not (
        args.diagnostic or args.scaling_diagnostic
    ):
        parser.error("--restart-before-stream requires a workflow diagnostic")
    candidates = (
        tuple(Candidate(value) for value in args.candidates)
        if args.candidates
        else (Candidate.B,)
    )
    if args.candidates and not args.scaling_diagnostic:
        parser.error("--candidates is only valid with --scaling-diagnostic")
    workloads = (
        tuple(Workload(value) for value in args.workloads)
        if args.workloads
        else NORMAL_WORKLOADS
    )
    settings = RepositoryServiceSettings()
    if args.v8_formal:
        summary = run_v8_matrix(
            settings,
            args.output,
            data_root=args.data_root,
            measured_runs=args.runs,
            image_digest=args.image_digest,
            build_revision=args.build_revision,
            cache_condition=args.cache_condition,
        )
    elif args.reserved_b_w0_smoke:
        summary = run_reserved_b_w0_smoke(
            settings,
            args.output,
            image_digest=args.image_digest,
            build_revision=args.build_revision,
            cache_condition=args.cache_condition,
        )
    elif args.scaling_diagnostic:
        summary = run_scaling_diagnostic(
            settings,
            args.output,
            data_root=args.data_root,
            measured_runs=args.runs,
            image_digest=args.image_digest,
            build_revision=args.build_revision,
            cache_condition=args.cache_condition,
            candidates=candidates,
            restart_before_stream=args.restart_before_stream,
        )
    elif args.offline_discard_diagnostic:
        summary = run_offline_discard_diagnostic_matrix(
            settings,
            args.output,
            data_root=args.data_root,
            image_digest=args.image_digest,
            build_revision=args.build_revision,
            cache_condition=args.cache_condition,
        )
    elif args.a_paired_diagnostic:
        summary = run_a_paired_devnull_diagnostic(
            settings,
            args.output,
            data_root=args.data_root,
            measured_runs=args.runs,
            image_digest=args.image_digest,
            build_revision=args.build_revision,
            cache_condition=args.cache_condition,
        )
    else:
        summary = run_matrix(
            settings,
            args.output,
            data_root=args.data_root,
            workloads=workloads,
            measured_runs=args.runs,
            diagnostic=args.diagnostic,
            image_digest=args.image_digest,
            build_revision=args.build_revision,
            cache_condition=args.cache_condition,
            restart_before_stream=args.restart_before_stream,
        )
    print(json.dumps(summary, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
