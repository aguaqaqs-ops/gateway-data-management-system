from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping, Sequence
from pathlib import Path
import json

from ...core import BenchmarkRunResult, canonical_json_bytes
from .runner import RepositoryImportBenchmarkSummary


class SummaryJsonWriter:
    def write(self, path: Path, summary: RepositoryImportBenchmarkSummary) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(canonical_json_bytes(summary.to_payload()))

    def read(self, path: Path) -> RepositoryImportBenchmarkSummary:
        payload = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(payload, Mapping):
            raise TypeError("benchmark summary payload must be an object")
        return RepositoryImportBenchmarkSummary.from_payload(payload)


class MarkdownReportWriter:
    def write_from_summary_path(self, summary_path: Path, report_path: Path) -> None:
        summary = SummaryJsonWriter().read(summary_path)
        self.write(summary, report_path)

    def write(self, summary: RepositoryImportBenchmarkSummary, report_path: Path) -> None:
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(self.render(summary), encoding="utf-8")

    def render(self, summary: RepositoryImportBenchmarkSummary) -> str:
        lines: list[str] = []
        lines.append("# Repository Import Benchmark Report")
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
        lines.extend(_render_dataset_table(summary))
        lines.append("")
        lines.append("## Results")
        lines.extend(_render_results_table(summary.results))
        lines.append("")
        lines.append("## Best Passed Providers")
        lines.extend(_render_best_passed_table(summary.results))
        lines.append("")
        return "\n".join(lines)


def _render_dataset_table(summary: RepositoryImportBenchmarkSummary) -> list[str]:
    rows: list[tuple[object, ...]] = []
    for dataset in summary.datasets:
        rows.append(
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
    if not rows:
        return ["No datasets selected."]
    lines = [_table_header(("Dataset", "Kind", "Tables", "Rows", "Largest Table", "SQL Bytes", "SQL Digest"))]
    for row in rows:
        lines.append(_table_row(row))
    lines.append(_table_end())
    return lines


def _render_results_table(results: tuple[BenchmarkRunResult, ...]) -> list[str]:
    if not results:
        return ["No benchmark results recorded."]
    lines = [
        _table_header(
            (
                "Dataset",
                "Profile",
                "Provider",
                "Status",
                "Validation",
                "Rows/s",
                "Total ms",
                "Failure",
            )
        )
    ]
    for result in results:
        lines.append(
            _table_row(
                (
                    result.dataset_id,
                    result.profile,
                    result.provider,
                    result.status,
                    result.validation_result,
                    _format_number(result.rows_per_second),
                    result.total_duration_ms,
                    result.failure_phase or "",
                )
            )
        )
    lines.append(_table_end())
    return lines


def _render_best_passed_table(results: tuple[BenchmarkRunResult, ...]) -> list[str]:
    grouped: dict[tuple[str, str], list[BenchmarkRunResult]] = defaultdict(list)
    for result in results:
        if result.status != "PASSED" or result.validation_result != "PASSED":
            continue
        grouped[(result.dataset_id, result.profile)].append(result)
    if not grouped:
        return ["No passed results available."]
    lines = [_table_header(("Dataset", "Profile", "Best Provider", "Rows/s", "Total ms"))]
    for (dataset_id, profile), candidates in sorted(grouped.items()):
        best = min(candidates, key=_best_result_sort_key)
        lines.append(
            _table_row(
                (
                    dataset_id,
                    profile,
                    best.provider,
                    _format_number(best.rows_per_second),
                    best.total_duration_ms,
                )
            )
        )
    lines.append(_table_end())
    return lines


def _best_result_sort_key(result: BenchmarkRunResult) -> tuple[float, int, str]:
    rows_per_second = result.rows_per_second if result.rows_per_second is not None else -1.0
    total_duration_ms = result.total_duration_ms if result.total_duration_ms is not None else 10**12
    return (-rows_per_second, total_duration_ms, result.provider)


def _format_number(value: object) -> str:
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
