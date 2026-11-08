"""Read-only Repository schema and selected table content evidence for S4.

An independent earlier source captures the expectation file. Verification
always reads the current candidate's public Repository API at exact commits.
The row digest is a sorted multiset of typed Arrow values, not IPC bytes.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections.abc import Mapping
from datetime import date, datetime, time
from decimal import Decimal
from pathlib import Path
from typing import Any

import httpx
import pyarrow as pa
import pyarrow.ipc as pa_ipc
from gateway_repository_contracts import GetVersionedCatalogResponse, encode_commit_id_path_segment

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tests.support.compose_gate_harness import BEARER_TOKEN  # noqa: E402


def _typed(value: Any) -> Any:
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
    raise ValueError(f"unhandled Arrow scalar type: {type(value).__name__}")


def _json_bytes(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode("utf-8")


def _table_digest(table: pa.Table) -> str:
    rows = sorted(_json_bytes(_typed(row)) for row in table.to_pylist())
    digest = hashlib.sha256()
    for row in rows:
        digest.update(len(row).to_bytes(8, "big"))
        digest.update(row)
    return "sha256:" + digest.hexdigest()


def read_identity(
    *, base_url: str, repository_id: str, commit_id: str, selected_tables: list[str],
) -> dict[str, Any]:
    encoded = encode_commit_id_path_segment(commit_id)
    with httpx.Client(base_url=base_url, headers={"Authorization": f"Bearer {BEARER_TOKEN}"},
                      timeout=300.0) as client:
        response = client.get(f"/v1/repositories/{repository_id}/versioned/commits/{encoded}/catalog")
        response.raise_for_status()
        catalog = GetVersionedCatalogResponse.model_validate_json(response.content).catalog
        if catalog.commit_id != commit_id:
            raise ValueError("Repository Catalog commit differs from the exact requested commit")
        tables = {table.name: table for table in catalog.tables}
        if len(tables) != len(catalog.tables):
            raise ValueError("Repository Catalog has duplicate table names")
        schema = [
            {"name": table.name, "row_count": table.row_count,
             "columns": [{"name": col.name, "sql_type": col.sql_type, "nullable": col.nullable}
                         for col in table.columns],
             "primary_key": list(table.primary_key)}
            for table in sorted(catalog.tables, key=lambda item: item.name)
        ]
        result: dict[str, Any] = {
            "schema_version": "s4-repository-identity/v1",
            "catalog_table_count": len(schema),
            "catalog_schema_sha256": "sha256:" + hashlib.sha256(_json_bytes(schema)).hexdigest(),
            "selected_tables": {},
        }
        if len(set(selected_tables)) != len(selected_tables) or not selected_tables:
            raise ValueError("selected table names must be nonempty and distinct")
        for table_name in selected_tables:
            table = tables.get(table_name)
            if table is None:
                raise ValueError("selected table is missing from Repository Catalog")
            rows = client.get(f"/v1/repositories/{repository_id}/versioned/commits/{encoded}/rows",
                              params={"table_name": table_name})
            rows.raise_for_status()
            arrow = pa_ipc.open_stream(rows.content).read_all()
            if arrow.num_rows != table.row_count or arrow.schema.names != [col.name for col in table.columns]:
                raise ValueError("selected Repository rows differ from Catalog count or schema")
            result["selected_tables"][table_name] = {
                "row_count": arrow.num_rows,
                "row_digest": _table_digest(arrow),
            }
        return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--repository-id", required=True)
    parser.add_argument("--commit-id", required=True)
    parser.add_argument("--dataset-id", required=True)
    parser.add_argument("--expected", type=Path, required=True)
    args = parser.parse_args()
    expected = json.loads(args.expected.read_text())
    item = expected["datasets"][args.dataset_id]
    selected = list(item["selected_tables"])
    actual = read_identity(base_url=args.base_url, repository_id=args.repository_id,
                           commit_id=args.commit_id, selected_tables=selected)
    if actual != item:
        raise SystemExit("Repository schema or selected table content differs from independent expectation")
    print(json.dumps({"dataset_id": args.dataset_id, "commit_id": args.commit_id,
                      "expected_sha256": hashlib.sha256(_json_bytes(item)).hexdigest(),
                      "actual": actual, "conclusion": "PASS"}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
