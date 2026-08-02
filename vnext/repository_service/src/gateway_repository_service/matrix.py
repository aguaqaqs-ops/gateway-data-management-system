"""Command-line P2-R1 two-candidate matrix runner."""

from __future__ import annotations

import argparse
import json
import os
import platform
import subprocess
import tempfile
from pathlib import Path
from typing import Iterable

from gateway_repository_service.fixtures import Fixture, Workload, generate_fixture
from gateway_repository_service.settings import RepositoryServiceSettings
from gateway_repository_service.workflow import Candidate, WorkflowMeasurement, run_workflow


def run_matrix(
    settings: RepositoryServiceSettings,
    output: Path,
    *,
    data_root: Path | None = None,
    workloads: Iterable[Workload] = (Workload.W0, Workload.W1, Workload.W2, Workload.W3_1, Workload.W3_10),
    measured_runs: int = 5,
) -> dict[str, object]:
    output.parent.mkdir(parents=True, exist_ok=True)
    if measured_runs < 5:
        raise ValueError("P2-R1 requires at least five measured runs")
    selected_workloads = tuple(workloads)
    output.write_text("", encoding="utf-8")
    records: list[dict[str, object]] = []
    fixture_context = tempfile.TemporaryDirectory(prefix="gateway-p2r1-fixtures-")
    root_context = (
        tempfile.TemporaryDirectory(prefix="gateway-p2r1-target-")
        if data_root is None
        else None
    )
    try:
        fixture_root = Path(fixture_context.name)
        probe_root = data_root if data_root is not None else Path(root_context.name)  # type: ignore[union-attr]
        for candidate in Candidate:
            for workload in selected_workloads:
                fixture = generate_fixture(fixture_root, workload)
                base_fixture = (
                    generate_fixture(fixture_root, Workload.W1)
                    if workload in {Workload.W3_1, Workload.W3_10}
                    else None
                )
                warmup = run_workflow(
                    settings,
                    candidate,
                    fixture,
                    sample_kind="warmup",
                    run_unknown_reject=workload == Workload.W0,
                    base_fixture=base_fixture,
                    root_parent=probe_root,
                )
                records.append(_record(fixture, warmup, probe_root))
                _append_jsonl(output, records[-1])
                for index in range(1, measured_runs + 1):
                    measurement = run_workflow(
                        settings,
                        candidate,
                        fixture,
                        sample_kind=f"measured-{index}",
                        run_unknown_reject=workload == Workload.W0,
                        base_fixture=base_fixture,
                        root_parent=probe_root,
                    )
                    records.append(_record(fixture, measurement, probe_root))
                    _append_jsonl(output, records[-1])
    finally:
        fixture_context.cleanup()
        if root_context is not None:
            root_context.cleanup()

    summary = _summarize(records, settings)
    output.with_suffix(".summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    output.with_suffix(".md").write_text(_markdown(summary), encoding="utf-8")
    return summary


def _record(fixture: Fixture, measurement: WorkflowMeasurement, filesystem_path: Path) -> dict[str, object]:
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
        }
    )
    return data


def _append_jsonl(path: Path, record: dict[str, object]) -> None:
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, sort_keys=True) + "\n")
        handle.flush()


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


def _summarize(records: list[dict[str, object]], settings: RepositoryServiceSettings) -> dict[str, object]:
    measured = [record for record in records if str(record["sample_kind"]).startswith("measured-")]
    by_candidate: dict[str, dict[str, object]] = {}
    for candidate in Candidate:
        candidate_rows = [row for row in measured if row["candidate"] == candidate.value]
        workload_names = {str(row["workload"]) for row in candidate_rows}
        workflow = all(bool(row["correctness"]) for row in candidate_rows)
        safety_rows = [row for row in candidate_rows if row["workload"] in {"W0", "W1", "W2"}]
        safety = all(
            isinstance(row["import_seconds"], (int, float))
            and float(row["import_seconds"]) <= settings.import_timeout_seconds
            for row in safety_rows
        )
        w1 = [
            float(row["import_seconds"])
            for row in candidate_rows
            if row["workload"] == Workload.W1.value and isinstance(row["import_seconds"], (int, float))
        ]
        max_import = max(w1) if w1 else None
        capacity = (4 * 86400 * 0.70 / max_import) if max_import else 0.0
        w1_storage = [
            int(row["logical_bytes_after"]) - int(row["logical_bytes_before"])
            for row in candidate_rows
            if row["workload"] == Workload.W1.value
            and isinstance(row["logical_bytes_after"], (int, float))
            and isinstance(row["logical_bytes_before"], (int, float))
        ]
        incremental_storage = [
            int(row["logical_bytes_after"]) - int(row["logical_bytes_before"])
            for row in candidate_rows
            if row["workload"] in {Workload.W3_1.value, Workload.W3_10.value}
            and isinstance(row["logical_bytes_after"], (int, float))
            and isinstance(row["logical_bytes_before"], (int, float))
        ]
        full_storage = max(w1_storage) if w1_storage else 0
        incremental_gate = bool(incremental_storage) and all(
            0 < value <= max(full_storage * 2, 1) for value in incremental_storage
        )
        w1_stream_delta = [
            int(row["stream_rss_delta_kib"])
            for row in candidate_rows
            if row["workload"] == Workload.W1.value
            and isinstance(row["stream_rss_delta_kib"], (int, float))
        ]
        w2_stream_delta = [
            int(row["stream_rss_delta_kib"])
            for row in candidate_rows
            if row["workload"] == Workload.W2.value
            and isinstance(row["stream_rss_delta_kib"], (int, float))
        ]
        bounded_stream = bool(w1_stream_delta and w2_stream_delta) and max(w2_stream_delta) <= max(
            max(w1_stream_delta) * 2, 64 * 1024
        )
        hard_gate = workflow and safety and capacity >= 1000 and incremental_gate and bounded_stream
        by_candidate[candidate.value] = {
            "workloads": sorted(workload_names),
            "workflow": workflow,
            "safety_limit": safety,
            "max_w1_import_seconds": max_import,
            "capacity_projection_imports_per_day": capacity,
            "capacity_gate": capacity >= 1000,
            "incremental_storage_gate": incremental_gate,
            "bounded_stream_gate": bounded_stream,
            "hard_gate": hard_gate,
            "result": "pass" if hard_gate else "fail",
        }
    a_pass = bool(by_candidate[Candidate.A.value]["hard_gate"])
    b_pass = bool(by_candidate[Candidate.B.value]["hard_gate"])
    selected = Candidate.A.value if a_pass else Candidate.B.value if b_pass else None
    return {
        "round": "P2-R1",
        "candidate_matrix": by_candidate,
        "selected_provider": selected,
        "selection_reason": "simplicity-first; Candidate A wins whenever it passes all hard gates"
        if selected
        else "both candidates failed at least one hard gate",
        "round_exit": "go" if selected else "no-go",
        "next_round_ready": bool(selected),
        "records": len(records),
        "measurement_environment": {
            "dolt_version": settings.dolt_version,
            "python_version": platform.python_version(),
            "cpu_count": os.cpu_count(),
            "filesystem": _filesystem_type(),
        },
    }


def _markdown(summary: dict[str, object]) -> str:
    matrix = summary["candidate_matrix"]
    assert isinstance(matrix, dict)
    lines = [
        "# P2-R1 Provider Feasibility Decision",
        "",
        f"- round: `{summary['round']}`",
        f"- selected_provider: `{summary['selected_provider']}`",
        f"- round_exit: `{summary['round_exit']}`",
        f"- next_round_ready: `{summary['next_round_ready']}`",
        "",
        "| Candidate | Workflow | 60m safety | W1 max import (s) | Capacity projection | Hard gate |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for name, result in matrix.items():
        assert isinstance(result, dict)
        lines.append(
            f"| {name} | {result['workflow']} | {result['safety_limit']} | "
            f"{result['max_w1_import_seconds']} | {result['capacity_projection_imports_per_day']:.2f} | "
            f"{result['hard_gate']} |"
        )
    lines.extend(
        [
            "",
            "All workloads are deterministic synthetic fixtures. Results are feasibility measurements, not production SLOs.",
            "",
        ]
    )
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the P2-R1 Dolt provider matrix")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--data-root", type=Path)
    parser.add_argument("--runs", type=int, default=5)
    parser.add_argument("--workloads", nargs="+", choices=[workload.value for workload in Workload])
    args = parser.parse_args()
    workloads = tuple(Workload(value) for value in args.workloads) if args.workloads else tuple(Workload)
    summary = run_matrix(
        RepositoryServiceSettings(),
        args.output,
        data_root=args.data_root,
        workloads=workloads,
        measured_runs=args.runs,
    )
    print(json.dumps(summary, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
