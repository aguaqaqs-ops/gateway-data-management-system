from __future__ import annotations

from argparse import ArgumentParser
from collections.abc import Sequence
from pathlib import Path

from .runner import (
    DEFAULT_DATASET_ROOT,
    DEFAULT_INITIAL_ABNORMAL_DATASET,
    DEFAULT_INITIAL_BASELINE_DATASET,
    DEFAULT_MODIFIED_DATASET,
    FormalArchiveJourneyBenchmarkRunner,
)


def build_argument_parser() -> ArgumentParser:
    parser = ArgumentParser(
        prog="python -m backend_vnext.benchmarks.formal_archive_journey",
        description=(
            "Run the large formal archive journey benchmark through formal API/TestClient. "
            "The flow covers first upload/submit/archive and second FULL upload with abnormal initial."
        ),
    )
    parser.add_argument(
        "--dataset-root",
        type=Path,
        default=DEFAULT_DATASET_ROOT,
        help="Root containing the large, large-1 and large-2 dataset directories.",
    )
    parser.add_argument(
        "--run-root",
        type=Path,
        required=True,
        help="Output root for state, package tarballs, events and summary.",
    )
    parser.add_argument(
        "--baseline-dataset",
        default=DEFAULT_INITIAL_BASELINE_DATASET,
        help="Dataset for first initialize-baseline upload.",
    )
    parser.add_argument(
        "--abnormal-initial-dataset",
        default=DEFAULT_INITIAL_ABNORMAL_DATASET,
        help="Dataset for second FULL upload initial package.",
    )
    parser.add_argument(
        "--modified-dataset",
        default=DEFAULT_MODIFIED_DATASET,
        help="Dataset for second FULL upload modified package.",
    )
    parser.add_argument(
        "--skip-baseline-initial-diagnostics",
        action="store_true",
        help="Do not attempt the optional baseline -> initial diagnostics route.",
    )
    parser.add_argument(
        "--operation-timeout-seconds",
        type=float,
        default=3600.0,
        help="Maximum wait time for submit/archive operations.",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_argument_parser()
    args = parser.parse_args(list(argv) if argv is not None else None)
    runner = FormalArchiveJourneyBenchmarkRunner(
        dataset_root=args.dataset_root,
        run_root=args.run_root,
        operation_timeout_seconds=args.operation_timeout_seconds,
    )
    summary = runner.run(
        baseline_dataset=args.baseline_dataset,
        abnormal_initial_dataset=args.abnormal_initial_dataset,
        modified_dataset=args.modified_dataset,
        include_baseline_initial_diagnostics=not args.skip_baseline_initial_diagnostics,
    )
    print(f"run_id={summary['run_id']}")
    print(f"summary={runner.summary_path}")
    print(f"events={runner.events_path}")
    return 0
