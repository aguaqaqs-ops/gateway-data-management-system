from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime, timezone
from pathlib import Path
from time import perf_counter
from uuid import uuid4

from ...core import DiagnosticRecord
from ...cache import (
    ComparisonCoreCache,
    FilesystemComparisonCoreCache,
    FilesystemProjectionTableCache,
    ProjectionTableCache,
)
from ...capabilities.repository_import import RepositoryImportValidationPolicy
from ..flow_journey import (
    FlowJourneyBenchmarkProfile,
    FlowJourneyBenchmarkRunner,
)
from ..history_compare import (
    HistoryCompareBenchmarkProfile,
    HistoryCompareBenchmarkRunner,
    HistoryCompareRepositoryBackedDatasetInput,
)
from ...repository_server import RepositoryServerTableCache
from .._paths import resolve_benchmark_path
from ..repository_import import (
    RepositoryImportBenchmarkMachineProfile,
    detect_local_machine_profile,
)
from ..flow_journey.runner import _default_machine_profile_id as _journey_default_machine_profile_id
from .models import JourneyHistoryCompareSuiteStatus, JourneyHistoryCompareSuiteSummary
from .report import MarkdownReportWriter, SummaryJsonWriter


DEFAULT_DATASET_IDS: tuple[str, ...] = ("business_large",)
DEFAULT_DATASET_ROOT = Path("/home/issac/test-dir/business-benchmark-data")
DEFAULT_JOURNEY_PROFILES: tuple[FlowJourneyBenchmarkProfile, ...] = (
    FlowJourneyBenchmarkProfile.FULL_JOURNEY_WARM,
)
DEFAULT_HISTORY_COMPARE_PROFILES: tuple[HistoryCompareBenchmarkProfile, ...] = (
    HistoryCompareBenchmarkProfile.REPO_BACKED_WARM,
    HistoryCompareBenchmarkProfile.REPO_BACKED_WARM_PARTIAL,
    HistoryCompareBenchmarkProfile.REPO_BACKED_COLD,
    HistoryCompareBenchmarkProfile.REPO_BACKED_WARM_VERIFICATION,
)
DEFAULT_EXECUTION_ORDER: tuple[str, ...] = (
    "BASELINE_INIT_SUBMISSION",
    "INITIAL_MODIFIED_SUBMISSION",
    "HISTORY_COMPARE_WARM_FULL",
    "HISTORY_COMPARE_WARM_PARTIAL",
    "HISTORY_COMPARE_COLD",
    "HISTORY_COMPARE_WARM_VERIFICATION",
)


class JourneyHistoryCompareSuiteRunner:
    def __init__(
        self,
        *,
        dataset_root: Path = DEFAULT_DATASET_ROOT,
        run_root: Path,
        result_out: Path | None = None,
        dolt_bin: str = "dolt",
        mysql_bin: str = "mysql",
        machine_profile: RepositoryImportBenchmarkMachineProfile | None = None,
        repository_ref_cache: RepositoryServerTableCache | None = None,
        comparison_core_cache: ComparisonCoreCache | None = None,
        projection_table_cache: ProjectionTableCache | None = None,
    ) -> None:
        self.dataset_root = resolve_benchmark_path(dataset_root)
        self.run_root = resolve_benchmark_path(run_root)
        self.result_out = result_out if result_out is not None else self.run_root / "report.md"
        self.dolt_bin = dolt_bin
        self.mysql_bin = mysql_bin
        self.machine_profile = machine_profile or detect_local_machine_profile(
            machine_profile_id=_journey_default_machine_profile_id(),
            dolt_bin=self.dolt_bin,
            mysql_bin=self.mysql_bin,
        )
        self.repository_ref_cache = repository_ref_cache or RepositoryServerTableCache(
            self.run_root / "repository-ref-cache"
        )
        self.comparison_core_cache = comparison_core_cache or FilesystemComparisonCoreCache(
            self.run_root / "comparison-core-cache"
        )
        self.projection_table_cache = projection_table_cache or FilesystemProjectionTableCache(
            self.run_root / "projection-table-cache"
        )
        self.flow_journey_runner = FlowJourneyBenchmarkRunner(
            dataset_root=self.dataset_root,
            run_root=self.run_root / "flow_journey",
            dolt_bin=self.dolt_bin,
            mysql_bin=self.mysql_bin,
            machine_profile=self.machine_profile,
            comparison_core_cache=self.comparison_core_cache,
            projection_table_cache=self.projection_table_cache,
        )
        self.history_compare_runner = HistoryCompareBenchmarkRunner(
            dataset_root=self.dataset_root,
            run_root=self.run_root / "history_compare",
            dolt_bin=self.dolt_bin,
            mysql_bin=self.mysql_bin,
            machine_profile=self.machine_profile,
            repository_ref_cache=self.repository_ref_cache,
            comparison_core_cache=self.comparison_core_cache,
            projection_table_cache=self.projection_table_cache,
        )
        self.summary_path = self.run_root / "summary.json"
        self.run_root.mkdir(parents=True, exist_ok=True)
        self.result_out.parent.mkdir(parents=True, exist_ok=True)

    def run(
        self,
        *,
        datasets: Sequence[str] | None = DEFAULT_DATASET_IDS,
        journey_validation_policy: RepositoryImportValidationPolicy | str = (
            RepositoryImportValidationPolicy.VERIFY_SCHEMA_ROW_COUNT_SUMMARY
        ),
        history_compare_validation_policy: RepositoryImportValidationPolicy | str = (
            RepositoryImportValidationPolicy.DISABLED
        ),
    ) -> JourneyHistoryCompareSuiteSummary:
        self.run_root.mkdir(parents=True, exist_ok=True)
        selected_dataset_ids = DEFAULT_DATASET_IDS if datasets is None else tuple(datasets)

        diagnostics: list[DiagnosticRecord] = []

        journey_start = perf_counter()
        try:
            journey_summary = self.flow_journey_runner.run(
                profiles=DEFAULT_JOURNEY_PROFILES,
                datasets=selected_dataset_ids,
                validation_policy=journey_validation_policy,
            )
        except Exception as exc:  # pragma: no cover - defensive orchestration path
            diagnostics.append(
                DiagnosticRecord(
                    code="benchmark.suite.journey.failed",
                    message="suite journey phase failed",
                    phase="summary",
                    severity="ERROR",
                    details={"error": str(exc)},
                )
            )
            summary = self._build_summary(
                status=JourneyHistoryCompareSuiteStatus.FAILED,
                dataset_ids=selected_dataset_ids,
                journey_summary=None,
                history_compare_summary=None,
                journey_duration_ms=_elapsed_ms(journey_start),
                history_compare_duration_ms=None,
                failure_stage="FLOW_JOURNEY",
                failure_reason=str(exc),
                diagnostics=tuple(diagnostics),
            )
            self._write_outputs(summary)
            return summary
        journey_duration_ms = _elapsed_ms(journey_start)
        diagnostics.extend(journey_summary.diagnostics)

        if _summary_has_failed_results(journey_summary.results):
            diagnostics.append(
                DiagnosticRecord(
                    code="benchmark.suite.journey.failed",
                    message="suite journey phase recorded a failed result",
                    phase="summary",
                    severity="ERROR",
                    details={"run_id": journey_summary.run_id},
                )
            )
            summary = self._build_summary(
                status=JourneyHistoryCompareSuiteStatus.FAILED,
                dataset_ids=selected_dataset_ids,
                journey_summary=journey_summary,
                history_compare_summary=None,
                journey_duration_ms=journey_duration_ms,
                history_compare_duration_ms=None,
                failure_stage="FLOW_JOURNEY",
                failure_reason="flow journey benchmark recorded a failed result",
                diagnostics=tuple(diagnostics),
            )
            self._write_outputs(summary)
            return summary

        repository_backed_inputs = _build_repository_backed_inputs_from_journey(
            journey_summary=journey_summary,
            dataset_ids=selected_dataset_ids,
        )
        history_compare_start = perf_counter()
        try:
            history_compare_summary = self.history_compare_runner.run(
                profiles=DEFAULT_HISTORY_COMPARE_PROFILES,
                datasets=selected_dataset_ids,
                validation_policy=history_compare_validation_policy,
                repository_backed_inputs=repository_backed_inputs,
            )
        except Exception as exc:  # pragma: no cover - defensive orchestration path
            diagnostics.append(
                DiagnosticRecord(
                    code="benchmark.suite.history_compare.failed",
                    message="suite history compare phase failed",
                    phase="summary",
                    severity="ERROR",
                    details={"error": str(exc)},
                )
            )
            summary = self._build_summary(
                status=JourneyHistoryCompareSuiteStatus.FAILED,
                dataset_ids=selected_dataset_ids,
                journey_summary=journey_summary,
                history_compare_summary=None,
                journey_duration_ms=journey_duration_ms,
                history_compare_duration_ms=_elapsed_ms(history_compare_start),
                failure_stage="HISTORY_COMPARE",
                failure_reason=str(exc),
                diagnostics=tuple(diagnostics),
            )
            self._write_outputs(summary)
            return summary
        history_compare_duration_ms = _elapsed_ms(history_compare_start)
        diagnostics.extend(history_compare_summary.diagnostics)

        status = (
            JourneyHistoryCompareSuiteStatus.FAILED
            if _summary_has_failed_results(history_compare_summary.results)
            else JourneyHistoryCompareSuiteStatus.PASSED
        )
        failure_stage = None
        failure_reason = None
        if status is JourneyHistoryCompareSuiteStatus.FAILED:
            diagnostics.append(
                DiagnosticRecord(
                    code="benchmark.suite.history_compare.failed",
                    message="suite history compare phase recorded a failed result",
                    phase="summary",
                    severity="ERROR",
                    details={"run_id": history_compare_summary.run_id},
                )
            )
            failure_stage = "HISTORY_COMPARE"
            failure_reason = "history compare benchmark recorded a failed result"
        else:
            diagnostics.append(
                DiagnosticRecord(
                    code="benchmark.suite.completed",
                    message="journey and history compare suite completed",
                    phase="summary",
                    severity="INFO",
                    details={
                        "journey_run_id": journey_summary.run_id,
                        "history_compare_run_id": history_compare_summary.run_id,
                    },
                )
            )
        summary = self._build_summary(
            status=status,
            dataset_ids=selected_dataset_ids,
            journey_summary=journey_summary,
            history_compare_summary=history_compare_summary,
            journey_duration_ms=journey_duration_ms,
            history_compare_duration_ms=history_compare_duration_ms,
            failure_stage=failure_stage,
            failure_reason=failure_reason,
            diagnostics=tuple(diagnostics),
        )
        self._write_outputs(summary)
        return summary

    def _build_summary(
        self,
        *,
        status: JourneyHistoryCompareSuiteStatus,
        dataset_ids: Sequence[str],
        journey_summary,
        history_compare_summary,
        journey_duration_ms: int | None,
        history_compare_duration_ms: int | None,
        failure_stage: str | None,
        failure_reason: str | None,
        diagnostics: tuple[DiagnosticRecord, ...],
    ) -> JourneyHistoryCompareSuiteSummary:
        return JourneyHistoryCompareSuiteSummary(
            run_id=_build_run_id(),
            created_at=_utc_now(),
            machine_profile=self.machine_profile,
            dataset_ids=tuple(dataset_ids),
            execution_order=DEFAULT_EXECUTION_ORDER,
            status=status,
            flow_journey_summary=journey_summary,
            history_compare_summary=history_compare_summary,
            journey_duration_ms=journey_duration_ms,
            history_compare_duration_ms=history_compare_duration_ms,
            failure_stage=failure_stage,
            failure_reason=failure_reason,
            diagnostics=diagnostics,
        )

    def _write_outputs(self, summary: JourneyHistoryCompareSuiteSummary) -> None:
        SummaryJsonWriter().write(self.summary_path, summary)
        MarkdownReportWriter().write(summary, self.result_out)


def _summary_has_failed_results(results) -> bool:
    for result in results:
        status = getattr(result, "status", None)
        if status is None:
            return True
        if getattr(status, "value", status) != "PASSED":
            return True
    return False


def _build_repository_backed_inputs_from_journey(
    *,
    journey_summary,
    dataset_ids: Sequence[str],
) -> dict[str, HistoryCompareRepositoryBackedDatasetInput]:
    selected_dataset_ids = {str(dataset_id) for dataset_id in dataset_ids}
    dataset_results: dict[str, dict[str, object]] = {}
    for result in journey_summary.results:
        if result.dataset_id not in selected_dataset_ids:
            continue
        if result.repository_path is None or result.repository_commit_hash is None:
            continue
        bucket = dataset_results.setdefault(result.dataset_id, {})
        submission_kind = getattr(result.submission_kind, "value", result.submission_kind)
        if submission_kind == "BASELINE_INIT_SUBMISSION" and "baseline" not in bucket:
            bucket["baseline"] = result
        elif submission_kind == "INITIAL_MODIFIED_SUBMISSION" and "current" not in bucket:
            bucket["current"] = result

    repository_backed_inputs: dict[str, HistoryCompareRepositoryBackedDatasetInput] = {}
    for dataset_id in dataset_ids:
        bucket = dataset_results.get(dataset_id)
        if bucket is None or "baseline" not in bucket or "current" not in bucket:
            raise ValueError(
                f"journey summary did not include repository-backed inputs for dataset_id={dataset_id}"
            )
        baseline_result = bucket["baseline"]
        current_result = bucket["current"]
        assert baseline_result.repository_path is not None
        assert baseline_result.repository_commit_hash is not None
        assert current_result.repository_path is not None
        assert current_result.repository_commit_hash is not None
        baseline_repository_id = baseline_result.repository_id or dataset_id
        current_repository_id = current_result.repository_id or dataset_id
        if baseline_repository_id != current_repository_id:
            raise ValueError(
                f"journey baseline/current repository ids do not match for dataset_id={dataset_id}"
            )
        repository_backed_inputs[dataset_id] = HistoryCompareRepositoryBackedDatasetInput(
            dataset_id=dataset_id,
            before_repository_path=baseline_result.repository_path,
            current_repository_path=current_result.repository_path,
            before_repository_ref=baseline_result.repository_commit_hash,
            current_repository_ref=current_result.repository_commit_hash,
            requested_tables=tuple(baseline_result.requested_tables),
            repository_id=baseline_repository_id,
        )
    return repository_backed_inputs


def _build_run_id() -> str:
    return f"journey-history-compare-suite-{_utc_now().strftime('%Y%m%d')}-{uuid4().hex[:8]}"


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _elapsed_ms(start: float) -> int:
    return max(0, int((perf_counter() - start) * 1000))
