"""Capture independent S4 Repository expectations from fixed B source.

Run under B V788's backend environment on a dedicated test node. The
external B table_diff_driver.py and this script are SHA-pinned by the
controller. This invokes B's source staging and canonical projection only;
it never calls C/D's SQL renderer or native storage-diff result as expected.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

from gateway_backend.bootstrap.compute_kernel import initialize_compute_kernel
from gateway_backend.capabilities.table_access import (
    KernelExecutionContext, NeverCancel, OperationMemoryBudget, kernel_execution_scope,
)
from gateway_backend.infrastructure.repository_write.import_publication import _schema_columns_from_descriptor


def _load_fixed_driver(path: Path) -> Any:
    spec = importlib.util.spec_from_file_location("fixed_b_table_diff_driver", path)
    if spec is None or spec.loader is None:
        raise RuntimeError("fixed B source driver could not be loaded")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _sha(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def _typed(value: Any) -> Any:
    from datetime import date, datetime, time
    from decimal import Decimal
    from collections.abc import Mapping

    if value is None:
        return ["null"]
    if type(value) is bool:
        return ["bool", value]
    if type(value) is int:
        return ["int", str(value)]
    if type(value) is float:
        return ["float", value.hex()]
    if type(value) is str:
        return ["str", value]
    if type(value) is bytes:
        return ["bytes", value.hex()]
    if isinstance(value, Decimal):
        return ["decimal", str(value)]
    if isinstance(value, (datetime, date, time)):
        return [type(value).__name__, value.isoformat()]
    if isinstance(value, list):
        return ["list", [_typed(item) for item in value]]
    if isinstance(value, Mapping):
        return ["map", [[str(key), _typed(item)] for key, item in sorted(value.items())]]
    raise ValueError(f"unhandled frozen source scalar: {type(value).__name__}")


def _canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode("utf-8")


def _table_digest(rows: list[dict[str, Any]]) -> str:
    values = sorted(_canonical(_typed(row)) for row in rows)
    digest = hashlib.sha256()
    for row in values:
        digest.update(len(row).to_bytes(8, "big"))
        digest.update(row)
    return "sha256:" + digest.hexdigest()


def capture(
    *, source_root: Path, datasets_sha256: str, package_id: str,
    selected_names: list[str], old_driver: Path,
) -> dict[str, Any]:
    driver = _load_fixed_driver(old_driver)
    driver.ROOT = source_root
    metadata = source_root / "datasets.json"
    if _sha(metadata) != datasets_sha256:
        raise RuntimeError("frozen source dataset metadata differs from the pinned SHA")
    cases = {row["dataset_id"]: row for row in json.loads(metadata.read_text())["datasets"]}
    item = cases[package_id]
    file_info, = item["files"]
    package = source_root / "packages" / f"{package_id}.tar.gz"
    if package.stat().st_size != file_info["bytes"] or _sha(package) != file_info["sha256"]:
        raise RuntimeError("frozen source package differs from its manifest")
    context = KernelExecutionContext(OperationMemoryBudget(24 * 1024**3), NeverCancel(), 1)
    initialize_compute_kernel(1)
    with kernel_execution_scope(context, new_operation=True):
        prepared = driver.project(item, context)
        try:
            manifests = {table.name: table for table in prepared.manifest.tables}
            tables = {table.descriptor.table_name: table for table in prepared.projection.tables}
            if set(manifests) != set(tables) or len(tables) != len(prepared.projection.tables):
                raise RuntimeError("old canonical projection table membership is invalid")
            schema = []
            for name in sorted(tables):
                table = tables[name]
                manifest = manifests[name]
                cols = _schema_columns_from_descriptor(table.descriptor, manifest)
                schema.append({"name": name, "row_count": manifest.canonical_row_count,
                               "columns": [{"name": col["name"], "sql_type": col["sql_type"],
                                            "nullable": col["nullable"]} for col in cols],
                               "primary_key": list(manifest.canonical_key_columns)})
            selected: dict[str, Any] = {}
            if not selected_names or len(set(selected_names)) != len(selected_names):
                raise RuntimeError("selected tables must be nonempty and distinct")
            for name in selected_names:
                table = tables.get(name)
                if table is None or table.reader is None:
                    raise RuntimeError("selected old canonical table is missing")
                reader = table.reader.reopen()
                try:
                    with reader.arrow_stream() as stream:
                        arrow = stream.read_all()
                finally:
                    reader.close()
                if arrow.num_rows != manifests[name].canonical_row_count:
                    raise RuntimeError("selected old canonical row count differs from its manifest")
                selected[name] = {"row_count": arrow.num_rows,
                                  "row_digest": _table_digest(arrow.to_pylist())}
            return {"schema_version": "s4-repository-identity/v1",
                    "catalog_table_count": len(schema),
                    "catalog_schema_sha256": "sha256:" + hashlib.sha256(_canonical(schema)).hexdigest(),
                    "selected_tables": selected}
        finally:
            prepared.close()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--datasets-sha256", required=True)
    parser.add_argument("--package-id", required=True)
    parser.add_argument("--select", action="append", required=True)
    parser.add_argument("--old-driver", type=Path, required=True)
    parser.add_argument("--old-driver-sha256", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    old_worktree = Path(os.environ["GATEWAY_S4_B_WORKTREE"]).resolve()
    old_head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=old_worktree,
                              check=True, capture_output=True, text=True).stdout.strip()
    old_status = subprocess.run(["git", "status", "--porcelain"], cwd=old_worktree,
                                check=True, capture_output=True, text=True).stdout.strip()
    if old_head != "788ed36e7742a067bf01c16ad2e6aaed2fed91fb" or old_status:
        raise RuntimeError("independent B source worktree identity is invalid")
    if _sha(args.old_driver) != args.old_driver_sha256:
        raise RuntimeError("old B source driver identity changed")
    if args.output.exists():
        raise RuntimeError("independent expected output already exists")
    result = capture(source_root=args.source_root, datasets_sha256=args.datasets_sha256,
                     package_id=args.package_id, selected_names=args.select, old_driver=args.old_driver)
    package = args.source_root / "packages" / f"{args.package_id}.tar.gz"
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps({"dataset_id": args.package_id,
                                       "source_commit": old_head,
                                       "datasets_sha256": args.datasets_sha256,
                                       "package_sha256": _sha(package),
                                       "old_driver_sha256": args.old_driver_sha256,
                                       "expected": result}, sort_keys=True, indent=2) + "\n")
    print(json.dumps({"dataset_id": args.package_id, "expected_sha256": _sha(args.output),
                      "selected_table_count": len(result["selected_tables"]),
                      "catalog_table_count": result["catalog_table_count"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
