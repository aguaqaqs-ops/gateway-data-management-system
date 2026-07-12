from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path
import json

from ...core import canonical_json_bytes
from ..repository_import import RepositoryImportBenchmarkDatasetManifest
from .models import (
    HistoryCompareBenchmarkResult,
    HistoryCompareBenchmarkSummary,
)


class SummaryJsonWriter:
    def write(self, path: Path, summary: HistoryCompareBenchmarkSummary) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(canonical_json_bytes(summary.to_payload()))

    def read(self, path: Path) -> HistoryCompareBenchmarkSummary:
        payload = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(payload, Mapping):
            raise TypeError("benchmark summary payload must be an object")
        return HistoryCompareBenchmarkSummary.from_payload(payload)


class MarkdownReportWriter:
    def write_from_summary_path(self, summary_path: Path, report_path: Path) -> None:
        summary = SummaryJsonWriter().read(summary_path)
        self.write(summary, report_path)

    def write(self, summary: HistoryCompareBenchmarkSummary, report_path: Path) -> None:
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(self.render(summary), encoding="utf-8")

    def render(self, summary: HistoryCompareBenchmarkSummary) -> str:
        lines: list[str] = []
        lines.append("# Repo-Backed History Compare Benchmark Report")
        lines.append("")
        lines.append(f"- Run ID: `{summary.run_id}`")
        lines.append(f"- Created At: `{summary.created_at.isoformat()}`")
        lines.append(f"- Machine Profile: `{summary.machine_profile.machine_profile_id}`")
        lines.append("")
        lines.append("## Scope")
        lines.append("")
        lines.append(
            "- Repo-backed history compare starts from repository-backed inputs and records no separate preparation stage."
        )
        lines.append(
            "- Baseline and current ref open times are reported independently so baseline readback can stay lighter than current ref materialization."
        )
        lines.append(
            "- The benchmark ladder can include warm-full, warm-partial, cold, and warm-verify runs on the same representative pair; warm-partial clears only comparison-core cache."
        )
        lines.append(
            "- Native Routes counts planner-selected native route decisions, not fallback attempts."
        )
        lines.append("")
        lines.append("## Machine Profile")
        lines.extend(
            [
                _table_header(("Field", "Value")),
                _table_row(("OS", summary.machine_profile.os_name)),
                _table_row(("CPU Count", summary.machine_profile.cpu_count)),
                _table_row(("CPU Model", summary.machine_profile.cpu_model)),
                _table_row(("Memory MB", summary.machine_profile.memory_total_mb)),
                _table_row(("Filesystem", summary.machine_profile.filesystem)),
                _table_row(("Dolt Version", summary.machine_profile.dolt_version)),
                _table_row(("Python Version", summary.machine_profile.python_version)),
                _table_row(("MySQL Client Version", summary.machine_profile.mysql_client_version)),
                _table_end(),
                "",
            ]
        )
        lines.append("## Datasets")
        lines.extend(_render_dataset_table(summary.datasets))
        lines.append("")
        lines.append("## Results")
        lines.extend(_render_results_table(summary.results))
        lines.append("")
        lines.append("## Stage Breakdown")
        for result in summary.results:
            lines.append("")
            lines.append(
                f"### {result.dataset_id} / {result.profile.value} / {result.provider.value}"
            )
            lines.append("")
            lines.append(f"- Repository ID: `{result.repository_id}`")
            lines.append(f"- Before Ref: `{result.before_repository_ref}`")
            lines.append(f"- Current Ref: `{result.current_repository_ref}`")
            lines.append("")
            lines.extend(_render_stage_table(result))
            lines.append("")
            lines.extend(_render_timing_table(result))
        return "\n".join(lines)


def _render_dataset_table(datasets: Sequence[RepositoryImportBenchmarkDatasetManifest]) -> list[str]:
    if not datasets:
        return ["No datasets selected."]
    lines = [_table_header(("Dataset", "Kind", "Tables", "Rows", "Largest Table", "SQL Bytes", "SQL Digest"))]
    for dataset in datasets:
        lines.append(
            _table_row(
                (
                    dataset.dataset_id,
                    dataset.dataset_kind,
                    dataset.table_count,
                    dataset.row_count_total,
                    dataset.largest_table_row_count,
                    dataset.source_sql_bytes,
                    dataset.source_sql_digest.to_payload(),
                )
            )
        )
    lines.append(_table_end())
    return lines


def _render_results_table(results: Sequence[HistoryCompareBenchmarkResult]) -> list[str]:
    if not results:
        return ["No benchmark results recorded."]
    lines = [
        _table_header(
            (
                "Dataset",
                "Profile",
                "Provider",
                "Comparison Mode",
                "Status",
                "Comparison Status",
                "Open Baseline Ref ms",
                "Open Current Ref ms",
                "Compare Stage ms",
                "Comparison ms",
                "Risk ms",
                "Surface ms",
                "Bundle ms",
                "Async Cache ms",
                "Total ms",
                "Native Routes",
                "Comparison Core Cache Hit/Miss",
                "Projection Cache Hit/Miss",
                "Pair Count",
                "Failure",
            )
        )
    ]
    for result in results:
        open_baseline_ms = _stage_duration(result, "OPEN_BASELINE_REPOSITORY_REF")
        open_current_ms = _stage_duration(result, "OPEN_CURRENT_REPOSITORY_REF")
        compare_stage_ms = _stage_duration(result, "HISTORY_COMPARE")
        lines.append(
            _table_row(
                (
                    result.dataset_id,
                    result.profile.value,
                    result.provider.value,
                    result.comparison_mode,
                    result.status.value,
                    result.comparison_status or "",
                    open_baseline_ms,
                    open_current_ms,
                    compare_stage_ms,
                    result.comparison_duration_ms,
                    result.risk_duration_ms,
                    result.surface_duration_ms,
                    result.bundle_duration_ms,
                    result.comparison_core_cache_completion_ms,
                    result.total_duration_ms,
                    result.native_route_count,
                    _format_comparison_core_cache_stats(result),
                    _format_cache_stats(result),
                    result.pair_count,
                    result.failure_stage or result.failure_reason or "",
                )
            )
        )
    lines.append(_table_end())
    return lines


def _render_stage_table(result: HistoryCompareBenchmarkResult) -> list[str]:
    if not result.stages:
        return ["No stage results recorded."]
    lines = [_table_header(("Stage", "Status", "ms", "Details"))]
    for stage in result.stages:
        lines.append(
            _table_row(
                (
                    stage.stage_name,
                    stage.status,
                    stage.duration_ms,
                    _format_stage_details(stage.stage_name, stage.details),
                )
            )
        )
    lines.append(_table_end())
    return lines


def _render_timing_table(result: HistoryCompareBenchmarkResult) -> list[str]:
    open_baseline_details = result.stage_details("OPEN_BASELINE_REPOSITORY_REF") or {}
    open_current_details = result.stage_details("OPEN_CURRENT_REPOSITORY_REF") or {}
    compare_details = result.stage_details("HISTORY_COMPARE") or {}
    rows: list[tuple[str, object | None]] = [
        ("Open Baseline Ref ms", open_baseline_details.get("open_ref_materialize_ms")),
        ("Open Baseline Materialized Tables", open_baseline_details.get("materialized_table_count")),
        ("Planned Baseline Row Tables", open_baseline_details.get("planned_row_table_count")),
        ("Planned Baseline Native Tables", open_baseline_details.get("planned_native_route_count")),
        (
            "Planned Baseline Summary Early Exit Tables",
            open_baseline_details.get("planned_summary_early_exit_count"),
        ),
        ("Open Current Ref ms", open_current_details.get("open_ref_materialize_ms")),
        ("Open Current Materialized Tables", open_current_details.get("materialized_table_count")),
        ("Compare Stage ms", result.stage_duration("HISTORY_COMPARE")),
        ("Comparison ms", result.comparison_duration_ms),
        ("Risk ms", result.risk_duration_ms),
        ("Surface ms", result.surface_duration_ms),
        ("Bundle ms", result.bundle_duration_ms),
        ("Comparison Core Cache Completion ms", compare_details.get("comparison_core_cache_completion_ms")),
        (
            "Comparison Core Cache Completion Writes",
            compare_details.get("comparison_core_cache_completion_write_count"),
        ),
        (
            "Comparison Core Cache Completion Hits",
            compare_details.get("comparison_core_cache_completion_hit_count"),
        ),
        (
            "Comparison Core Cache Completion Skips",
            compare_details.get("comparison_core_cache_completion_skip_count"),
        ),
        (
            "Comparison Core Cache Hit Count",
            result.comparison_core_cache_hit_count,
        ),
        (
            "Comparison Core Cache Miss Count",
            result.comparison_core_cache_miss_count,
        ),
        ("Native Route Count", result.native_route_count),
        ("Projection Cache Hit Count", result.cache_hit_count),
        ("Projection Cache Miss Count", result.cache_miss_count),
    ]
    if not any(value is not None for _, value in rows):
        return ["No timing details recorded."]
    lines = ["### Timing Breakdown", ""]
    lines.append(_table_header(("Metric", "Value")))
    for label, value in rows:
        if value is None:
            continue
        lines.append(_table_row((label, value)))
    lines.append(_table_end())
    return lines


def _stage_duration(result: HistoryCompareBenchmarkResult, stage_name: str) -> int | None:
    return result.stage_duration(stage_name)


def _format_cache_stats(result: HistoryCompareBenchmarkResult) -> str:
    hits = result.cache_hit_count
    misses = result.cache_miss_count
    if hits is None and misses is None:
        return ""
    return f"{hits or 0}/{misses or 0}"


def _format_comparison_core_cache_stats(result: HistoryCompareBenchmarkResult) -> str:
    hits = result.comparison_core_cache_hit_count
    misses = result.comparison_core_cache_miss_count
    if hits is None and misses is None:
        return ""
    return f"{hits or 0}/{misses or 0}"


def _format_stage_details(stage_name: str, details: Mapping[str, object]) -> str:
    if not details:
        return ""
    keys = _ordered_detail_keys(stage_name, details)
    rendered: list[str] = []
    for key in keys[:30]:
        rendered.append(f"{key}={_format_detail_value(details[key])}")
    if len(keys) > 30:
        rendered.append("...")
    return "; ".join(rendered)


def _ordered_detail_keys(stage_name: str, details: Mapping[str, object]) -> list[str]:
    preferred_keys = {
        "OPEN_BASELINE_REPOSITORY_REF": (
            "open_ref_materialize_ms",
            "materialized_table_count",
            "requested_tables",
            "planned_row_table_count",
            "planned_native_route_count",
            "planned_summary_early_exit_count",
            "repository_ref",
            "resolved_commit_hash",
            "table_count",
            "row_count_total",
        ),
        "OPEN_CURRENT_REPOSITORY_REF": (
            "open_ref_materialize_ms",
            "materialized_table_count",
            "requested_tables",
            "repository_ref",
            "resolved_commit_hash",
            "table_count",
            "row_count_total",
        ),
        "HISTORY_COMPARE": (
            "comparison_duration_ms",
            "risk_duration_ms",
            "surface_duration_ms",
            "bundle_duration_ms",
            "comparison_status",
            "native_route_count",
            "cache_hit_count",
            "cache_miss_count",
            "pair_count",
        ),
    }
    ordered: list[str] = []
    seen: set[str] = set()
    for key in preferred_keys.get(stage_name, ()):
        if key in details and key not in seen:
            ordered.append(key)
            seen.add(key)
    for key in sorted(details):
        if key in seen:
            continue
        ordered.append(key)
    return ordered


def _format_detail_value(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, float):
        return f"{value:.2f}"
    return str(value)


def _table_header(columns: Sequence[str]) -> str:
    header = "| " + " | ".join(columns) + " |"
    separator = "| " + " | ".join("---" for _ in columns) + " |"
    return "\n".join((header, separator))


def _table_row(values: Sequence[object]) -> str:
    return "| " + " | ".join(_escape_markdown_cell(value) for value in values) + " |"


def _table_end() -> str:
    return ""


def _escape_markdown_cell(value: object) -> str:
    if value is None:
        return ""
    text = str(value)
    return text.replace("|", r"\|").replace("\n", " ").replace("\r", " ")
