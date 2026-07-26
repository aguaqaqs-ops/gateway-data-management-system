"""Container PHASE-EXIT-CONTAINER native compute smoke entrypoint."""

from __future__ import annotations

import hashlib
import importlib.metadata
import json
import os
import sys
from pathlib import Path
from typing import Any

import pyarrow as pa

from gateway_backend.compute import canonical_row_hashes_v1

_FORBIDDEN_NATIVE_PREFIXES = (
    "/app/rust",
    "/build/rust",
)

SMOKE_TABLE_FIELDS: list[dict[str, Any]] = [
    {
        "name": "flag",
        "nullable": True,
        "semantic_type": {"kind": "boolean"},
    }
]

SMOKE_REQUEST_JCS: bytes = json.dumps(
    {
        "request_schema_version": 1,
        "contract_binding": {
            "contract_id": "gateway-vnext.canonical-row-hash-compute-boundary",
            "semantic_version": "1.0.0",
        },
        "canonical_encoding_version": 1,
        "arrow_mapping_schema_version": 1,
        "declared_table_schema": {"fields": SMOKE_TABLE_FIELDS},
    },
    separators=(",", ":"),
    sort_keys=True,
).encode()

EXPECTED_ROW_HASHES_HEX: tuple[str, ...] = (
    "250d63ec676e9cf17d4b4e91337e781284be60b1aa59d9fc5c37584d85ce71f5",
    "3180b10d6d203c7fbe989745616bc3d2ff5e17e338453acc4983bb0ecf181c0e",
)

EXPECTED_ROW_HASH_SCHEMA = pa.schema(
    [pa.field("row_hash", pa.binary(32), nullable=False)],
)

EXPECTED_RESULT_JCS_BYTES: bytes = (
    b'{"arrow_mapping_schema_version":1,"canonical_encoding_version":1,'
    b'"contract_binding":{"contract_id":"gateway-vnext.canonical-row-hash-compute-boundary",'
    b'"semantic_version":"1.0.0"},"diagnostics":[],"raw_content_digest":'
    b'"sha256:ad30a8d266a2ab6910e6c725682d015cc60486d054819f7bab1ff5e8dc7e7ea3",'
    b'"result_schema_version":1,"row_count":"2","table_schema_digest":'
    b'"sha256:d942ff735528a8ec4297b476074e1c2e3fd2289518242b4f96c99a421b02f7d8"}'
)


def _fail(message: str) -> None:
    print(f"container_native_smoke: {message}", file=sys.stderr)
    raise SystemExit(1)


def assert_row_hash_column(table: pa.Table, expected_hex: tuple[str, ...]) -> None:
    if table.schema != EXPECTED_ROW_HASH_SCHEMA:
        _fail(f"output schema mismatch: {table.schema}")
    if table.num_columns != 1:
        _fail(f"unexpected column count: {table.num_columns}")
    if table.num_rows != len(expected_hex):
        _fail(f"unexpected row count: {table.num_rows}")
    col = table.column("row_hash")
    for index, expected in enumerate(expected_hex):
        row_bytes = col[index].as_py()
        if not isinstance(row_bytes, bytes) or len(row_bytes) != 32:
            _fail(f"row_hash[{index}] must be 32 bytes")
        actual = row_bytes.hex()
        if actual != expected:
            _fail(f"row_hash[{index}] mismatch: expected {expected}, got {actual}")


def assert_result_jcs_contract(result_jcs: bytes) -> None:
    if result_jcs != EXPECTED_RESULT_JCS_BYTES:
        _fail("result_jcs bytes mismatch")


def _verify_source_revision() -> None:
    expected = os.environ.get("GATEWAY_SOURCE_REVISION", "").strip()
    if not expected or expected == "unknown":
        _fail("GATEWAY_SOURCE_REVISION missing or unknown")
    wheel_label = os.environ.get("GATEWAY_EXPECTED_WHEEL_SHA256", "").strip()
    if not wheel_label or wheel_label == "unknown":
        _fail("GATEWAY_EXPECTED_WHEEL_SHA256 missing or unknown")
    extension_label = os.environ.get("GATEWAY_EXPECTED_EXTENSION_SHA256", "").strip()
    if not extension_label or extension_label == "unknown":
        _fail("GATEWAY_EXPECTED_EXTENSION_SHA256 missing or unknown")


def _verify_wheel_identity() -> None:
    import gateway_compute.gateway_compute as native  # type: ignore[import-untyped]

    wheel_path = Path(
        os.environ.get(
            "GATEWAY_INSTALLED_WHEEL_PATH",
            "/opt/gateway/wheels/gateway-compute-python.whl",
        )
    ).resolve()
    wheel_label = os.environ.get("GATEWAY_EXPECTED_WHEEL_SHA256", "").strip()
    if not wheel_path.is_file():
        _fail(f"installed wheel file missing: {wheel_path}")
    wheel_sha = hashlib.sha256(wheel_path.read_bytes()).hexdigest()
    if wheel_sha != wheel_label:
        _fail(f"wheel sha256 mismatch: expected {wheel_label}, got {wheel_sha}")

    module_file = Path(native.__file__).resolve()
    for prefix in _FORBIDDEN_NATIVE_PREFIXES:
        if str(module_file).startswith(prefix):
            _fail(f"native extension must not load from rust source tree: {module_file}")
    if not any(part in module_file.parts for part in (".venv", "site-packages")):
        _fail(f"native extension must be installed in venv/site-packages: {module_file}")

    bad = [name for name in dir(native) if name.startswith("_test_") or name.startswith("_TEST_")]
    if bad:
        _fail(f"production extension must not export test hooks: {bad}")

    extension_sha = hashlib.sha256(module_file.read_bytes()).hexdigest()
    extension_label = os.environ.get("GATEWAY_EXPECTED_EXTENSION_SHA256", "").strip()
    if extension_sha != extension_label:
        _fail(f"extension sha256 mismatch: expected {extension_label}, got {extension_sha}")

    version = importlib.metadata.version("gateway-compute-python")
    if not version:
        _fail("gateway-compute-python version missing")
    direct_url = None
    for path in importlib.metadata.distribution("gateway-compute-python").files or []:
        if path.name == "direct_url.json":
            dist = importlib.metadata.distribution("gateway-compute-python")
            direct_url = json.loads(dist.locate_file(path).read_text(encoding="utf-8"))
            break
    if direct_url is not None:
        url = direct_url.get("url", "")
        if str(module_file).startswith("/app/rust") or "/rust/gateway-compute-python" in url:
            _fail(f"direct_url must not reference source tree: {url}")


def _run_native_compute_smoke() -> None:
    table = pa.table({"flag": [True, False]})
    output, result_jcs = canonical_row_hashes_v1(SMOKE_REQUEST_JCS, table)
    batches = output.read_all()
    assert_row_hash_column(batches, EXPECTED_ROW_HASHES_HEX)
    assert_result_jcs_contract(result_jcs)


def main() -> None:
    _verify_source_revision()
    _verify_wheel_identity()
    _run_native_compute_smoke()
    print("container_native_smoke: ok")


if __name__ == "__main__":
    main()
