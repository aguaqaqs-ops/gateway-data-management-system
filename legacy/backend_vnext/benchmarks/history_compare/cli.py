from __future__ import annotations

from argparse import ArgumentParser
from collections.abc import Sequence
from pathlib import Path
import json

from ...capabilities.repository_import import RepositoryImportValidationPolicy
from .models import HistoryCompareBenchmarkProfile, HistoryCompareRepositoryBackedDatasetInput
from .runner import (
    DEFAULT_DATASET_ROOT,
    DEFAULT_PROFILES,
    HistoryCompareBenchmarkRunner,
)


def build_argument_parser() -> ArgumentParser:
    parser = ArgumentParser(
        prog="python -m backend_vnext.benchmarks.history_compare",
        description=(
            "Run the repo-backed history compare benchmark with explicit repository-backed inputs."
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
        help="Output root for summary, report, repositories and caches.",
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
        "--profiles",
        nargs="*",
        choices=[profile.value for profile in HistoryCompareBenchmarkProfile],
        default=None,
        help="Benchmark profiles to run. Defaults to the runner preset.",
    )
    parser.add_argument(
        "--validation-policy",
        choices=[policy.value for policy in RepositoryImportValidationPolicy],
        default=RepositoryImportValidationPolicy.DISABLED.value,
        help="Repository import validation policy for compare-only open stages.",
    )
    parser.add_argument(
        "--repository-backed-inputs",
        type=Path,
        required=True,
        help="JSON file that maps dataset_id to repository-backed compare inputs.",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_argument_parser()
    args = parser.parse_args(list(argv) if argv is not None else None)

    repository_backed_inputs = _load_repository_backed_inputs(args.repository_backed_inputs)

    runner = HistoryCompareBenchmarkRunner(
        dataset_root=args.dataset_root,
        run_root=args.run_root,
        result_out=args.result_out,
        dolt_bin=args.dolt_bin,
        mysql_bin=args.mysql_bin,
    )
    summary = runner.run(
        profiles=tuple(args.profiles) if args.profiles else DEFAULT_PROFILES,
        datasets=tuple(args.datasets) if args.datasets else None,
        validation_policy=args.validation_policy,
        repository_backed_inputs=repository_backed_inputs,
    )
    print(f"run_id={summary.run_id}")
    print(f"summary={runner.summary_path}")
    print(f"report={runner.result_out}")
    return 0


def _load_repository_backed_inputs(path: Path) -> dict[str, HistoryCompareRepositoryBackedDatasetInput]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise TypeError("repository-backed inputs file must contain a JSON object")
    repository_backed_inputs: dict[str, HistoryCompareRepositoryBackedDatasetInput] = {}
    for dataset_id, repository_backed_payload in payload.items():
        if not isinstance(dataset_id, str) or not dataset_id:
            raise TypeError("repository-backed input keys must be non-empty strings")
        if not isinstance(repository_backed_payload, dict):
            raise TypeError("repository-backed input entries must be JSON objects")
        repository_backed_inputs[dataset_id] = HistoryCompareRepositoryBackedDatasetInput.from_payload(
            repository_backed_payload
        )
    return repository_backed_inputs


if __name__ == "__main__":  # pragma: no cover - module execution path
    raise SystemExit(main())
