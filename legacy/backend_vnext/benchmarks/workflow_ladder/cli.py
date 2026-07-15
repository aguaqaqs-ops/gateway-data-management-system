from __future__ import annotations

from argparse import ArgumentParser
from collections.abc import Sequence
from pathlib import Path

from ...capabilities.repository_import import RepositoryImportValidationPolicy
from .runner import (
    DEFAULT_DATASET_IDS,
    DEFAULT_DATASET_ROOT,
    WorkflowLadderBenchmarkRunner,
)


def build_argument_parser() -> ArgumentParser:
    parser = ArgumentParser(
        prog="python -m backend_vnext.benchmarks.workflow_ladder",
        description=(
            "Run the Phase 4 real workflow ladder benchmark. "
            "The suite executes upload -> submit -> approve -> archive, "
            "then runs 2-node and 3-node history compare scenarios."
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
        help="Dataset ids to benchmark. Defaults to the runner preset.",
    )
    parser.add_argument(
        "--validation-policy",
        choices=[policy.value for policy in RepositoryImportValidationPolicy],
        default=RepositoryImportValidationPolicy.VERIFY_SCHEMA_ROW_COUNT_SUMMARY.value,
        help="Repository import validation policy for submit finalize.",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_argument_parser()
    args = parser.parse_args(list(argv) if argv is not None else None)

    runner = WorkflowLadderBenchmarkRunner(
        dataset_root=args.dataset_root,
        run_root=args.run_root,
        result_out=args.result_out,
        dolt_bin=args.dolt_bin,
        mysql_bin=args.mysql_bin,
    )
    summary = runner.run(
        datasets=tuple(args.datasets) if args.datasets else DEFAULT_DATASET_IDS,
        validation_policy=args.validation_policy,
    )
    print(f"run_id={summary.run_id}")
    print(f"summary={runner.summary_path}")
    print(f"report={runner.result_out}")
    return 0


if __name__ == "__main__":  # pragma: no cover - module execution path
    raise SystemExit(main())
