from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path
import json

from ...core import canonical_json_bytes
from ..repository_import import RepositoryImportBenchmarkDatasetManifest
from .models import (
    FlowJourneyBenchmarkResult,
    FlowJourneyBenchmarkSummary,
)


class SummaryJsonWriter:
    def write(self, path: Path, summary: FlowJourneyBenchmarkSummary) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(canonical_json_bytes(summary.to_payload()))

    def read(self, path: Path) -> FlowJourneyBenchmarkSummary:
        payload = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(payload, Mapping):
            raise TypeError("benchmark summary payload must be an object")
        return FlowJourneyBenchmarkSummary.from_payload(payload)


class MarkdownReportWriter:
    def write_from_summary_path(self, summary_path: Path, report_path: Path) -> None:
        summary = SummaryJsonWriter().read(summary_path)
        self.write(summary, report_path)

    def write(self, summary: FlowJourneyBenchmarkSummary, report_path: Path) -> None:
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(self.render(summary), encoding="utf-8")

    def render(self, summary: FlowJourneyBenchmarkSummary) -> str:
        lines: list[str] = []
        lines.append("# Flow Journey Benchmark Report")
        lines.append("")
        lines.append(f"- Run ID: `{summary.run_id}`")
        lines.append(f"- Created At: `{summary.created_at}`")
        lines.append(f"- Machine Profile: `{summary.machine_profile.machine_profile_id}`")
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
            if result.repository_path is not None:
                lines.append(f"- Repository Path: `{result.repository_path}`")
            if result.repository_commit_hash is not None:
                lines.append(f"- Repository Commit: `{result.repository_commit_hash}`")
            if result.workspace_id is not None:
                lines.append(f"- Workspace: `{result.workspace_id}`")
            if result.submission_id is not None:
                lines.append(f"- Submission: `{result.submission_id}`")
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


def _render_results_table(results: Sequence[FlowJourneyBenchmarkResult]) -> list[str]:
    if not results:
        return ["No benchmark results recorded."]
    lines = [
        _table_header(
            (
                "Dataset",
                "Profile",
                "Submission",
                "Provider",
                "Status",
                "Prepare ms",
                "Preview ms",
                "Accept ms",
                "Finalize ms",
                "Open Ref ms",
                "Preview Native",
                "Preview Cache",
                "Failure",
            )
        )
    ]
    for result in results:
        preview_details = result.stage_details("UPLOAD_PREVIEW") or {}
        open_ref_stage = "OPEN_NEW_BASELINE_REF" if result.stage("OPEN_NEW_BASELINE_REF") is not None else "OPEN_BASELINE_REF"
        prepare_stage = "PREPARE_COMPARE_INPUTS" if result.stage("PREPARE_COMPARE_INPUTS") is not None else "PREPARE_BASELINE_INPUTS"
        lines.append(
            _table_row(
                (
                    result.dataset_id,
                    result.profile.value,
                    result.submission_kind.value,
                    result.provider.value,
                    result.status.value,
                    _stage_duration(result, prepare_stage),
                    _stage_duration(result, "UPLOAD_PREVIEW"),
                    _stage_duration(result, "SUBMIT_ACCEPTANCE"),
                    _stage_duration(result, "SUBMIT_FINALIZE"),
                    _stage_duration(result, open_ref_stage),
                    preview_details.get("native_route_count"),
                    _format_cache_stats(preview_details),
                    result.failure_stage or result.failure_reason or "",
                )
            )
        )
    lines.append(_table_end())
    return lines


def _render_stage_table(result: FlowJourneyBenchmarkResult) -> list[str]:
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


def _render_timing_table(result: FlowJourneyBenchmarkResult) -> list[str]:
    prepare_details = result.stage_details("PREPARE_COMPARE_INPUTS") or result.stage_details("PREPARE_BASELINE_INPUTS") or {}
    preview_details = result.stage_details("UPLOAD_PREVIEW") or {}
    submit_finalize_details = result.stage_details("SUBMIT_FINALIZE") or {}

    rows: list[tuple[str, object | None]] = [
        ("Source SQL Materialization ms", _prepare_sql_parse_ms(prepare_details)),
        ("Prepare Rows Extract ms", prepare_details.get("rows_extract_ms")),
        ("Prepare Rows Mutate ms", prepare_details.get("rows_mutate_ms")),
        ("Prepare Baseline Materialize ms", prepare_details.get("baseline_materialize_ms")),
        ("Prepare Current Materialize ms", prepare_details.get("current_materialize_ms")),
        ("Prepare Context Build ms", prepare_details.get("context_build_ms")),
        ("Submit Finalize Parse ms", submit_finalize_details.get("parse_duration_ms")),
        ("Submit Finalize Staging ms", submit_finalize_details.get("staging_duration_ms")),
        ("Submit Finalize Server Start ms", submit_finalize_details.get("server_start_ms")),
        ("Submit Finalize Import ms", submit_finalize_details.get("import_duration_ms")),
        ("Submit Finalize Commit ms", submit_finalize_details.get("commit_duration_ms")),
        ("Submit Finalize Validation ms", submit_finalize_details.get("validation_duration_ms")),
        ("Submit Finalize Cleanup ms", submit_finalize_details.get("cleanup_duration_ms")),
        ("Submit Finalize Total ms", submit_finalize_details.get("total_duration_ms")),
        (
            "Submit Finalize Compare-Core Promotion ms",
            submit_finalize_details.get("comparison_core_cache_promotion_ms"),
        ),
        (
            "Submit Finalize Compare-Core Promotion Writes",
            submit_finalize_details.get("comparison_core_cache_promotion_write_count"),
        ),
        (
            "Submit Finalize Compare-Core Promotion Hits",
            submit_finalize_details.get("comparison_core_cache_promotion_hit_count"),
        ),
        (
            "Submit Finalize Compare-Core Promotion Skips",
            submit_finalize_details.get("comparison_core_cache_promotion_skip_count"),
        ),
        ("Preview Compare ms", preview_details.get("comparison_duration_ms")),
        ("Preview Risk ms", preview_details.get("risk_duration_ms")),
        ("Preview Surface ms", preview_details.get("surface_duration_ms")),
        ("Preview Comparison Core Cache Completion ms", preview_details.get("comparison_core_cache_completion_ms")),
        (
            "Preview Comparison Core Cache Completion Writes",
            preview_details.get("comparison_core_cache_completion_write_count"),
        ),
        (
            "Preview Comparison Core Cache Completion Hits",
            preview_details.get("comparison_core_cache_completion_hit_count"),
        ),
        (
            "Preview Comparison Core Cache Completion Skips",
            preview_details.get("comparison_core_cache_completion_skip_count"),
        ),
        ("Preview Comparison Core Cache Hit Count", preview_details.get("comparison_core_cache_hit_count")),
        ("Preview Comparison Core Cache Miss Count", preview_details.get("comparison_core_cache_miss_count")),
    ]
    if not any(value is not None for _, value in rows):
        return ["No timing details recorded."]
    lines = ["### Timing Breakdown", ""]
    lines.append(_table_header(("Metric", "ms")))
    for label, value in rows:
        if value is None:
            continue
        lines.append(_table_row((label, value)))
    lines.append(_table_end())
    return lines


def _stage_duration(result: FlowJourneyBenchmarkResult, stage_name: str) -> int | None:
    duration = result.stage_duration(stage_name)
    return duration


def _prepare_sql_parse_ms(details: Mapping[str, object]) -> object | None:
    value = details.get("source_sql_materialization_ms")
    return value


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
        "PREPARE_BASELINE_INPUTS": (
            "source_sql_materialization_ms",
            "rows_extract_ms",
            "rows_mutate_ms",
            "baseline_materialize_ms",
            "current_materialize_ms",
            "context_build_ms",
            "table_count",
        ),
        "PREPARE_COMPARE_INPUTS": (
            "source_sql_materialization_ms",
            "rows_extract_ms",
            "rows_mutate_ms",
            "baseline_materialize_ms",
            "current_materialize_ms",
            "context_build_ms",
            "table_count",
        ),
        "UPLOAD_PREVIEW": (
            "comparison_duration_ms",
            "risk_duration_ms",
            "surface_duration_ms",
            "comparison_core_cache_completion_ms",
            "comparison_core_cache_completion_write_count",
            "comparison_core_cache_completion_hit_count",
            "comparison_core_cache_completion_skip_count",
            "comparison_core_cache_hit_count",
            "comparison_core_cache_miss_count",
            "comparison_status",
            "native_route_count",
            "cache_hit_count",
            "cache_miss_count",
            "table_count",
        ),
        "SUBMIT_FINALIZE": (
            "parse_duration_ms",
            "staging_duration_ms",
            "server_start_ms",
            "import_duration_ms",
            "commit_duration_ms",
            "validation_duration_ms",
            "cleanup_duration_ms",
            "total_duration_ms",
            "workspace_status",
            "operation_id",
            "repository_path",
            "repository_commit_hash",
            "provider",
            "server_mode",
            "imported_table_count",
            "validation_result",
        ),
        "OPEN_NEW_BASELINE_REF": (
            "open_ref_materialize_ms",
            "table_count",
            "row_count_total",
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


def _format_cache_stats(details: Mapping[str, object]) -> str:
    hits = details.get("cache_hit_count")
    misses = details.get("cache_miss_count")
    if hits is None and misses is None:
        return ""
    return f"{hits or 0}/{misses or 0}"


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
