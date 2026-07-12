from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path
import json

from ...core import canonical_json_bytes
from ..flow_journey import MarkdownReportWriter as FlowJourneyMarkdownReportWriter
from ..history_compare import MarkdownReportWriter as HistoryCompareMarkdownReportWriter
from ..repository_import import RepositoryImportBenchmarkDatasetManifest
from .models import JourneyHistoryCompareSuiteSummary


class SummaryJsonWriter:
    def write(self, path: Path, summary: JourneyHistoryCompareSuiteSummary) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(canonical_json_bytes(summary.to_payload()))

    def read(self, path: Path) -> JourneyHistoryCompareSuiteSummary:
        payload = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(payload, Mapping):
            raise TypeError("benchmark summary payload must be an object")
        return JourneyHistoryCompareSuiteSummary.from_payload(payload)


class MarkdownReportWriter:
    def write_from_summary_path(self, summary_path: Path, report_path: Path) -> None:
        summary = SummaryJsonWriter().read(summary_path)
        self.write(summary, report_path)

    def write(self, summary: JourneyHistoryCompareSuiteSummary, report_path: Path) -> None:
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(self.render(summary), encoding="utf-8")

    def render(self, summary: JourneyHistoryCompareSuiteSummary) -> str:
        lines: list[str] = []
        lines.append("# Journey + History Compare Suite Report")
        lines.append("")
        lines.append(f"- Run ID: `{summary.run_id}`")
        lines.append(f"- Created At: `{summary.created_at.isoformat()}`")
        lines.append(f"- Machine Profile: `{summary.machine_profile.machine_profile_id}`")
        lines.append(f"- Status: `{summary.status.value}`")
        lines.append("")
        lines.append("## Scope")
        lines.append("")
        lines.append(
            "- This suite runs the journey baseline/init path first, then the repo-backed history compare ladder on one representative pair."
        )
        lines.append(
            "- The compare ladder records warm-full, warm-partial, cold, and warm-verify on the same baseline/current pair so cache inheritance boundaries stay visible."
        )
        lines.append(
            "- The journey and history compare benchmarks still write their own nested summaries and reports under the suite run root."
        )
        lines.append("")
        lines.append("## Overview")
        lines.extend(
            [
                _table_header(("Field", "Value")),
                _table_row(("Datasets", ", ".join(summary.dataset_ids))),
                _table_row(
                    (
                        "Journey Run ID",
                        None if summary.flow_journey_summary is None else summary.flow_journey_summary.run_id,
                    )
                ),
                _table_row(("Journey Duration ms", summary.journey_duration_ms)),
                _table_row(
                    (
                        "History Compare Run ID",
                        None
                        if summary.history_compare_summary is None
                        else summary.history_compare_summary.run_id,
                    )
                ),
                _table_row(("History Compare Duration ms", summary.history_compare_duration_ms)),
                _table_row(("Total Duration ms", summary.total_duration_ms)),
                _table_end(),
                "",
            ]
        )
        lines.append("## Execution Order")
        lines.append("")
        for step in summary.execution_order:
            lines.append(f"- {step}")
        lines.append("")
        lines.append("## Datasets")
        lines.append("")
        if summary.flow_journey_summary is not None:
            lines.extend(_render_dataset_table(summary.flow_journey_summary.datasets))
        elif summary.history_compare_summary is not None:
            lines.extend(_render_dataset_table(summary.history_compare_summary.datasets))
        else:
            lines.append("No datasets selected.")
        lines.append("")
        lines.append("## Journey")
        lines.append("")
        if summary.flow_journey_summary is None:
            lines.append("Journey summary not recorded.")
        else:
            journey_report = FlowJourneyMarkdownReportWriter().render(summary.flow_journey_summary)
            lines.append(_demote_headings(journey_report))
        lines.append("")
        lines.append("## History Compare")
        lines.append("")
        if summary.history_compare_summary is None:
            lines.append("History compare summary not recorded.")
        else:
            compare_report = HistoryCompareMarkdownReportWriter().render(summary.history_compare_summary)
            lines.append(_demote_headings(compare_report))
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


def _table_header(columns: Sequence[object]) -> str:
    return "| " + " | ".join(str(column) for column in columns) + " |"


def _table_row(values: Sequence[object]) -> str:
    rendered = ["" if value is None else str(value) for value in values]
    return "| " + " | ".join(rendered) + " |"


def _table_end() -> str:
    return ""


def _demote_headings(markdown: str) -> str:
    lines: list[str] = []
    for line in markdown.splitlines():
        if line.startswith("#"):
            hash_count = len(line) - len(line.lstrip("#"))
            lines.append("#" * min(hash_count + 1, 6) + line[hash_count:])
        else:
            lines.append(line)
    return "\n".join(lines)
