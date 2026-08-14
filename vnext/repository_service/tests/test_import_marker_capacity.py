"""Marker inspection capacity and branch-independence evidence for P2-R6-S3-B.

Dolt 2.1.11 probe (disposable repo):
- Query 1: ``SELECT commit_hash, message FROM dolt_commits WHERE message = ?`` is global.
- Query 2: ``dolt_branches`` joined with ``dolt_log AS OF candidate`` for parent + direct refs.
- Global ``dolt_log WHERE commit_hash = ?`` without AS OF panics; AS OF is required.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import time
from unittest.mock import patch

import pytest

from gateway_repository_service.candidate_a.ref_validation import IMPORT_MAIN_REF
from gateway_repository_service.layout import DurableLayout
from gateway_repository_service.providers import OfflineCliProvider
from gateway_repository_service.process import DoltRunner, StreamCancellationCheck
from gateway_repository_service.versioned_import.models import derive_private_ref_name
from gateway_repository_service.versioned_import.ports import MarkerInspectionUnique
from gateway_repository_service.versioned_import.provider import CandidateAImportProvider
from support.lifecycle_harness import lifecycle_settings

from test_import_provider import (
    OPERATION_ID,
    _candidate_on_private_ref,
    _staging_replay_path,
)
BRANCH_COUNTS = (1, 8, 32, 128)
SAMPLE_RUNS = 5


@dataclass(frozen=True)
class MarkerSample:
    query_count: int
    process_count: int
    duration_seconds: float
    result_kind: str


@dataclass(frozen=True)
class MarkerBenchReport:
    branch_count: int
    samples: tuple[MarkerSample, ...]

    @property
    def p95_duration_seconds(self) -> float:
        durations = sorted(sample.duration_seconds for sample in self.samples)
        index = min(len(durations) - 1, int(round(0.95 * (len(durations) - 1))))
        return durations[index]


def _build_import_provider(tmp_path: Path) -> tuple[DurableLayout, CandidateAImportProvider]:
    settings = lifecycle_settings(tmp_path)
    layout = DurableLayout.create_for_probe(settings.data_root)
    repository = layout.staging_artifacts / "import-repo"
    repository.mkdir(parents=True, exist_ok=True)
    runner = DoltRunner(settings, layout.root)
    cli = OfflineCliProvider(settings, layout, repository, runner)
    cli.initialize_repository()
    provider = CandidateAImportProvider(settings, layout, repository, runner)
    return layout, provider


def _batch_create_branches(
    provider: CandidateAImportProvider,
    layout: DurableLayout,
    branch_count: int,
) -> None:
    provider._run_cli(
        "checkout_main_for_marker_bench",
        ["checkout", IMPORT_MAIN_REF],
        provider._settings.metadata_timeout_seconds,
    )
    statements = [
        *(f"CALL DOLT_BRANCH('bench-{index:04d}');" for index in range(branch_count)),
        "CALL DOLT_BRANCH('operator-marker-manual');",
    ]
    replay_path = _staging_replay_path(
        layout,
        f"marker-bench-branches-{branch_count}.sql",
        "".join(f"{statement}\n" for statement in statements),
    )
    provider._cli.run_cli(
        "batch_marker_branches",
        ["sql", "--result-format=csv"],
        provider._settings.metadata_timeout_seconds,
        stdin_path=replay_path,
    )


def _inspect_with_counts(
    provider: CandidateAImportProvider,
    marker: str,
) -> MarkerSample:
    query_count = 0
    process_count = 0
    original_query_json = provider._cli.query_json
    original_run_cli = provider._cli.run_cli

    def counting_query_json(
        kind: str,
        sql: str,
        *,
        revision: str | None = None,
    ) -> list[dict[str, object]]:
        nonlocal query_count
        query_count += 1
        return original_query_json(kind, sql, revision=revision)

    def counting_run_cli(
        kind: str,
        args: list[str],
        timeout: float,
        *,
        stdin_path: Path | None = None,
        cancellation: StreamCancellationCheck | None = None,
    ) -> object:
        nonlocal process_count
        process_count += 1
        return original_run_cli(
            kind,
            args,
            timeout,
            stdin_path=stdin_path,
            cancellation=cancellation,
        )

    started = time.perf_counter()
    with (
        patch.object(provider._cli, "query_json", side_effect=counting_query_json),
        patch.object(provider._cli, "run_cli", side_effect=counting_run_cli),
    ):
        inspection = provider.inspect_marker(marker)
    duration_seconds = time.perf_counter() - started
    return MarkerSample(
        query_count=query_count,
        process_count=process_count,
        duration_seconds=duration_seconds,
        result_kind=inspection.kind,
    )


def _run_branch_count_benchmark(branch_count: int, tmp_path: Path) -> MarkerBenchReport:
    layout, provider = _build_import_provider(tmp_path / f"branches-{branch_count}")
    _batch_create_branches(provider, layout, branch_count)
    private_ref, marker, expected, candidate = _candidate_on_private_ref(
        provider,
        layout,
        table_sql="CREATE TABLE marker_capacity (id BIGINT NOT NULL PRIMARY KEY);\n",
    )
    del private_ref

    warmup = _inspect_with_counts(provider, marker)
    assert warmup.result_kind == "unique"
    assert warmup.query_count == 2
    assert warmup.process_count == 2

    samples: list[MarkerSample] = []
    for _ in range(SAMPLE_RUNS):
        sample = _inspect_with_counts(provider, marker)
        assert sample.result_kind == "unique"
        assert sample.query_count == 2
        assert sample.process_count == 2
        samples.append(sample)

    inspection = provider.inspect_marker(marker)
    assert isinstance(inspection, MarkerInspectionUnique)
    assert inspection.candidate == candidate
    assert inspection.parent == expected
    assert derive_private_ref_name(OPERATION_ID) in inspection.refs

    return MarkerBenchReport(branch_count=branch_count, samples=tuple(samples))


@pytest.mark.integration
@pytest.mark.serial
def test_marker_query_count_is_branch_independent(tmp_path: Path) -> None:
    reports = [_run_branch_count_benchmark(branch_count, tmp_path) for branch_count in BRANCH_COUNTS]

    query_counts = {report.branch_count: report.samples[0].query_count for report in reports}
    process_counts = {report.branch_count: report.samples[0].process_count for report in reports}
    assert set(query_counts.values()) == {2}
    assert set(process_counts.values()) == {2}

    one_branch_p95 = reports[0].p95_duration_seconds
    one_branch_max = max(sample.duration_seconds for sample in reports[0].samples)
    threshold = max(0.5, 3.0 * one_branch_p95)
    assert reports[-1].p95_duration_seconds <= threshold, (
        "128-branch marker p95 exceeded threshold: "
        f"p95={reports[-1].p95_duration_seconds:.3f}s "
        f"threshold={threshold:.3f}s "
        f"one_branch_p95={one_branch_p95:.3f}s "
        f"one_branch_max={one_branch_max:.3f}s "
        f"query_counts={query_counts} "
        f"process_counts={process_counts} "
        f"128_branch_durations={[round(s.duration_seconds, 3) for s in reports[-1].samples]}"
    )

    for report in reports:
        assert all(sample.result_kind == "unique" for sample in report.samples)
        assert all(sample.query_count == 2 for sample in report.samples)
        assert all(sample.process_count == 2 for sample in report.samples)
