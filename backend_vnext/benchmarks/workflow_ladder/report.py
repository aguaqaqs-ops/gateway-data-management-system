from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path
import json

from ...core import canonical_json_bytes
from .models import (
    WorkflowLadderBenchmarkSummary,
    WorkflowLadderCompareResult,
    WorkflowLadderNodeResult,
)


class SummaryJsonWriter:
    def write(self, path: Path, summary: WorkflowLadderBenchmarkSummary) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(canonical_json_bytes(summary.to_payload()))

    def read(self, path: Path) -> WorkflowLadderBenchmarkSummary:
        payload = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(payload, Mapping):
            raise TypeError("benchmark summary payload must be an object")
        return WorkflowLadderBenchmarkSummary.from_payload(payload)


class MarkdownReportWriter:
    def write_from_summary_path(self, summary_path: Path, report_path: Path) -> None:
        summary = SummaryJsonWriter().read(summary_path)
        self.write(summary, report_path)

    def write(self, summary: WorkflowLadderBenchmarkSummary, report_path: Path) -> None:
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(self.render(summary), encoding="utf-8")

    def render(self, summary: WorkflowLadderBenchmarkSummary) -> str:
        lines: list[str] = []
        lines.append("# Real Workflow Ladder Benchmark Report")
        lines.append("")
        lines.append(f"- Run ID: `{summary.run_id}`")
        lines.append(f"- Created At: `{summary.created_at.isoformat()}`")
        lines.append(f"- Machine Profile: `{summary.machine_profile.machine_profile_id}`")
        lines.append(f"- Status: `{summary.status.value}`")
        lines.append("")
        lines.append("## Scope")
        lines.append("")
        lines.append(
            "- This suite runs a real three-node workflow ladder: upload -> submit -> approve -> archive."
        )
        lines.append(
            "- The compare phase is kept separate and can run both a 2-node compare and a 3-node dual-pair compare."
        )
        lines.append(
            "- No setup/prepared/synthetic summary stage is recorded; the suite only uses repo-backed facts and shared caches."
        )
        lines.append("")
        lines.append("## Overview")
        lines.extend(
            [
                _table_header(("Field", "Value")),
                _table_row(("Datasets", ", ".join(summary.dataset_ids))),
                _table_row(("Node Count", len(summary.node_results))),
                _table_row(("Compare Count", len(summary.compare_results))),
                _table_row(("Total Duration ms", summary.total_duration_ms)),
                _table_row(("Failure Stage", summary.failure_stage)),
                _table_row(("Failure Reason", summary.failure_reason)),
                _table_end(),
                "",
            ]
        )
        lines.append("## Execution Order")
        lines.append("")
        for step in summary.execution_order:
            lines.append(f"- {step}")
        lines.append("")
        lines.append("## Nodes")
        lines.append("")
        for node_result in summary.node_results:
            lines.extend(self._render_node_section(node_result))
            lines.append("")
        lines.append("## Compare Scenarios")
        lines.append("")
        for compare_result in summary.compare_results:
            lines.extend(self._render_compare_section(compare_result))
            lines.append("")
        lines.append("## Diagnostics")
        if summary.diagnostics:
            for diagnostic in summary.diagnostics:
                lines.append(
                    f"- `{diagnostic.code}`: {diagnostic.message} ({diagnostic.severity})"
                )
        else:
            lines.append("No diagnostics recorded.")
        return "\n".join(lines)

    def _render_node_section(self, result: WorkflowLadderNodeResult) -> list[str]:
        lines: list[str] = []
        lines.append(f"### Node `{result.node_id}`")
        lines.append("")
        lines.extend(
            [
                _table_header(("Field", "Value")),
                _table_row(("Dataset", result.dataset_id)),
                _table_row(("Dataset Kind", result.dataset_kind)),
                _table_row(("Submission Kind", result.submission_kind)),
                _table_row(("Status", result.status.value)),
                _table_row(("Workspace", result.workspace_id)),
                _table_row(("Submission", result.submission_id)),
                _table_row(("Repository ID", result.repository_id)),
                _table_row(("Repository Path", result.repository_path)),
                _table_row(("Repository Commit", result.repository_commit_hash)),
                _table_row(("Baseline Repo Ref", result.baseline_repository_ref)),
                _table_row(("Current Repo Ref", result.current_repository_ref)),
                _table_row(("Total ms", result.total_duration_ms)),
                _table_row(("Failure", result.failure_stage or result.failure_reason)),
                _table_end(),
            ]
        )
        lines.append("")
        lines.extend(_render_stage_breakdown(result.stages))
        lines.append("")
        lines.extend(_render_node_timing(result))
        return lines

    def _render_compare_section(self, result: WorkflowLadderCompareResult) -> list[str]:
        lines: list[str] = []
        lines.append(f"### Scenario `{result.scenario_name}`")
        lines.append("")
        lines.extend(
            [
                _table_header(("Field", "Value")),
                _table_row(("Pair Count", result.pair_count)),
                _table_row(("Pair IDs", ", ".join(result.pair_ids))),
                _table_row(
                    (
                        "Pair Refs",
                        "; ".join(f"{before} -> {current}" for before, current in result.pair_refs),
                    )
                ),
                _table_row(("Status", result.status.value)),
                _table_row(("Comparison Status", result.comparison_status)),
                _table_row(("Comparison Mode", result.comparison_mode)),
                _table_row(("Bundle ms", result.bundle_duration_ms)),
                _table_row(("Compare ms", result.comparison_duration_ms)),
                _table_row(("Risk ms", result.risk_duration_ms)),
                _table_row(("Surface ms", result.surface_duration_ms)),
                _table_row(("Native Routes", result.native_route_count)),
                _table_row(("Comparison Core Cache Hit/Miss", _format_hit_miss(result.comparison_core_cache_hit_count, result.comparison_core_cache_miss_count))),
                _table_row(("Comparison Core Cache Completion ms", result.comparison_core_cache_completion_ms)),
                _table_row(("Failure", result.failure_stage or result.failure_reason)),
                _table_end(),
            ]
        )
        lines.append("")
        lines.extend(_render_stage_breakdown(result.stages))
        lines.append("")
        lines.extend(_render_compare_timing(result))
        return lines


def _render_stage_breakdown(stages: Sequence[object]) -> list[str]:
    if not stages:
        return ["No stage results recorded."]
    lines = [_table_header(("Stage", "Status", "ms", "Details"))]
    for stage in stages:
        stage_name = getattr(stage, "stage_name", "")
        status = getattr(stage, "status", "")
        duration_ms = getattr(stage, "duration_ms", "")
        details = getattr(stage, "details", {})
        lines.append(_table_row((stage_name, status, duration_ms, _format_stage_details(details))))
    lines.append(_table_end())
    return lines


def _render_node_timing(result: WorkflowLadderNodeResult) -> list[str]:
    rows: list[tuple[str, object | None]] = [
        ("Open New Baseline ms", result.stage_duration("OPEN_NEW_BASELINE")),
        ("Upload ms", result.stage_duration("UPLOAD")),
        ("Submit ms", result.stage_duration("SUBMIT")),
        ("Approve ms", result.stage_duration("APPROVE")),
        ("Archive ms", result.stage_duration("ARCHIVE")),
        ("Upload Preview ms", _stage_detail(result, "UPLOAD", "comparison_duration_ms")),
        ("Upload Risk ms", _stage_detail(result, "UPLOAD", "risk_duration_ms")),
        ("Upload Surface ms", _stage_detail(result, "UPLOAD", "surface_duration_ms")),
        ("Submit Acceptance ms", _stage_detail(result, "SUBMIT", "acceptance_duration_ms")),
        ("Submit Finalize ms", _stage_detail(result, "SUBMIT", "finalize_duration_ms")),
        ("Submit Compare-Core Promotion ms", _stage_detail(result, "SUBMIT", "comparison_core_cache_promotion_ms")),
        ("Approve Start Review ms", _stage_detail(result, "APPROVE", "start_review_duration_ms")),
        ("Approve Result Status", _stage_detail(result, "APPROVE", "submission_status")),
        ("Archive Open Ref ms", _stage_detail(result, "ARCHIVE", "open_ref_duration_ms")),
        ("Archive Execute ms", _stage_detail(result, "ARCHIVE", "execute_duration_ms")),
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


def _render_compare_timing(result: WorkflowLadderCompareResult) -> list[str]:
    rows: list[tuple[str, object | None]] = [
        ("Compare Stage ms", result.stage_duration("HISTORY_COMPARE")),
        ("Comparison ms", result.comparison_duration_ms),
        ("Risk ms", result.risk_duration_ms),
        ("Surface ms", result.surface_duration_ms),
        ("Bundle ms", result.bundle_duration_ms),
        ("Comparison Core Cache Completion ms", result.comparison_core_cache_completion_ms),
        (
            "Comparison Core Cache Completion Pair Count",
            result.comparison_core_cache_completion_pair_count,
        ),
        (
            "Comparison Core Cache Completion Writes",
            result.comparison_core_cache_completion_write_count,
        ),
        (
            "Comparison Core Cache Completion Hits",
            result.comparison_core_cache_completion_hit_count,
        ),
        (
            "Comparison Core Cache Completion Skips",
            result.comparison_core_cache_completion_skip_count,
        ),
        ("Comparison Core Cache Hit Count", result.comparison_core_cache_hit_count),
        ("Comparison Core Cache Miss Count", result.comparison_core_cache_miss_count),
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


def _stage_detail(result: WorkflowLadderNodeResult, stage_name: str, detail_key: str) -> object | None:
    details = result.stage_details(stage_name) or {}
    return details.get(detail_key)


def _format_stage_details(details: Mapping[str, object]) -> str:
    if not details:
        return ""
    rendered: list[str] = []
    for key in sorted(details)[:20]:
        rendered.append(f"{key}={details[key]!r}")
    return "; ".join(rendered)


def _format_hit_miss(hit_count: int | None, miss_count: int | None) -> str:
    if hit_count is None and miss_count is None:
        return ""
    return f"{hit_count or 0}/{miss_count or 0}"


def _table_header(columns: Sequence[object]) -> str:
    return "| " + " | ".join(str(column) for column in columns) + " |"


def _table_row(values: Sequence[object]) -> str:
    rendered = ["" if value is None else str(value) for value in values]
    return "| " + " | ".join(rendered) + " |"


def _table_end() -> str:
    return ""
