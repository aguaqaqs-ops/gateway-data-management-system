"""CLI: python -m gateway_shared_kernel.testing generate|validate <path>."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from gateway_shared_kernel.testing.closure import ClosureValidationError, validate_vector_set
from gateway_shared_kernel.testing.generate import generate_candidate
from gateway_shared_kernel.testing.paths import resolve_vector_root


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m gateway_shared_kernel.testing",
        description=(
            "WP1 candidate vector tooling (out-of-tree; pending WP2 confirmation)."
        ),
    )
    sub = parser.add_subparsers(dest="command", required=True)

    gen = sub.add_parser("generate", help="Write a candidate vector set to an empty directory")
    gen.add_argument("output_dir", type=Path)

    val = sub.add_parser("validate", help="Validate a vector-set directory read-only")
    val.add_argument("vector_dir", type=Path)
    val.add_argument(
        "--manifest-only",
        action="store_true",
        help="Skip per-case execution against the Python reference",
    )

    args = parser.parse_args(argv)
    try:
        if args.command == "generate":
            path = generate_candidate(args.output_dir)
            print(f"candidate written: {path}")
            return 0
        if args.command == "validate":
            # Read-only resolver: may validate candidate or future normative root.
            root = resolve_vector_root(args.vector_dir)
            validate_vector_set(root, execute_cases=not args.manifest_only)
            print(f"vector set ok: {root}")
            return 0
    except (ValueError, ClosureValidationError, OSError, FileNotFoundError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
