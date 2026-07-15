from __future__ import annotations

from argparse import ArgumentParser
from collections.abc import Sequence
from pathlib import Path

from ...capabilities.repository_import import RepositoryImportValidationPolicy
from .runner import (
    DEFAULT_DATASET_IDS,
    DEFAULT_DATASET_ROOT,
    JourneyHistoryCompareSuiteRunner,
)


def build_argument_parser() -> ArgumentParser:
    parser = ArgumentParser(
        prog="python -m backend_vnext.benchmarks.journey_history_compare",
        description=(
            "Run the Phase 4 journey + repo-backed history compare suite. "
            "The suite executes the journey baseline/init, modified submission, and compare chain in order."
        ),
    )
    parser.add_argument(
        "--dataset-root",
        type=Path,
        default=DEFAULT_DATASET_ROOT,
        help="Root directory that contains benchmark datasets.",
    )
    parser.add_argument(
        "--run-root",
        type=Path,
        required=True,
        help="Output root for suite summary, report, nested benchmark outputs and caches.",
    )
    parser.add_argument(
        "--result-out",
        type=Path,
        default=None,
        help="Optional Markdown report path. Defaults to <run-root>/report.md.",
    )
    parser.add_argument(
        "--dolt-bin",
        default="dolt",
        help="Path or name of the dolt binary.",
    )
    parser.add_argument(
        "--mysql-bin",
        default="mysql",
        help="Path or name of the mysql client binary.",
    )
    parser.add_argument(
        "--datasets",
        nargs="*",
        default=None,
        help="Dataset ids to benchmark. Defaults to the suite preset.",
    )
    parser.add_argument(
        "--journey-validation-policy",
        choices=[policy.value for policy in RepositoryImportValidationPolicy],
        default=RepositoryImportValidationPolicy.VERIFY_SCHEMA_ROW_COUNT_SUMMARY.value,
        help="Repository import validation policy for the journey phase.",
    )
    parser.add_argument(
        "--history-compare-validation-policy",
        choices=[policy.value for policy in RepositoryImportValidationPolicy],
        default=RepositoryImportValidationPolicy.DISABLED.value,
        help="Repository import validation policy for the history compare phase.",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_argument_parser()
    args = parser.parse_args(list(argv) if argv is not None else None)

    runner = JourneyHistoryCompareSuiteRunner(
        dataset_root=args.dataset_root,
        run_root=args.run_root,
        result_out=args.result_out,
        dolt_bin=args.dolt_bin,
        mysql_bin=args.mysql_bin,
    )
    summary = runner.run(
        datasets=tuple(args.datasets) if args.datasets else DEFAULT_DATASET_IDS,
        journey_validation_policy=args.journey_validation_policy,
        history_compare_validation_policy=args.history_compare_validation_policy,
    )
    print(f"run_id={summary.run_id}")
    print(f"summary={runner.summary_path}")
    print(f"report={runner.result_out}")
    return 0


if __name__ == "__main__":  # pragma: no cover - module execution path
    raise SystemExit(main())
