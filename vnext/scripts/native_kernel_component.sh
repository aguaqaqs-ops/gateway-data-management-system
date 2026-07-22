#!/usr/bin/env bash
set -euo pipefail

VNEXT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BACKEND_ROOT="${VNEXT_ROOT}/backend"
COMPUTE_PYTHON_ROOT="${VNEXT_ROOT}/rust/gateway-compute-python"

usage() {
  echo "usage: $0 wheel-smoke|component-pytest" >&2
  exit 2
}

MODE="${1:-}"
case "${MODE}" in
  wheel-smoke | component-pytest) ;;
  *) usage ;;
esac

wheel_smoke() {
  local tmp wheel
  tmp="$(mktemp -d)"
  trap 'rm -rf "${tmp:-}"' EXIT

  cd "${BACKEND_ROOT}"
  export UV_OFFLINE=true
  uv sync --locked --offline --all-groups

  echo "building release wheel into ${tmp}/dist"
  local python_interpreter
  python_interpreter="$(uv run python -c 'import os, sys; print(os.path.realpath(sys.executable))')"
  uv run maturin build \
    --release \
    --manifest-path "${COMPUTE_PYTHON_ROOT}/Cargo.toml" \
    --out "${tmp}/dist" \
    --interpreter "${python_interpreter}"

  wheel="$(ls -1 "${tmp}/dist"/*.whl | head -n 1)"
  echo "release wheel: ${wheel}"

  uv pip install --offline --force-reinstall "${wheel}"

  uv run --offline --no-sync python - <<PY
import importlib.metadata
import json
import sys

import pyarrow as pa

import gateway_compute
from gateway_compute import canonical_row_hashes_v1

def request_jcs(fields):
    payload = {
        "request_schema_version": 1,
        "contract_binding": {
            "contract_id": "gateway-vnext.canonical-row-hash-compute-boundary",
            "semantic_version": "1.0.0",
        },
        "canonical_encoding_version": 1,
        "arrow_mapping_schema_version": 1,
        "declared_table_schema": {"fields": fields},
    }
    return json.dumps(payload, separators=(",", ":"), sort_keys=True).encode()

# empty table
reader = pa.RecordBatchReader.from_batches(pa.schema([]), [])
output, result_jcs = canonical_row_hashes_v1(request_jcs([]), reader)
assert isinstance(output, pa.RecordBatchReader)
assert b'"row_count":"0"' in result_jcs

# multi-batch
schema = pa.schema([pa.field("v", pa.string(), nullable=False)])
multi = pa.RecordBatchReader.from_batches(
    schema,
    [
        pa.record_batch([pa.array(["alpha"], type=pa.string())], schema=schema),
        pa.record_batch(
            [pa.array(["beta", "gamma"], type=pa.string())],
            schema=schema,
        ),
    ],
)
output, result_jcs = canonical_row_hashes_v1(
    request_jcs([{"name": "v", "nullable": False, "semantic_type": {"kind": "string"}}]),
    multi,
)
assert output.read_all().num_rows == 3
assert b'"row_count":"3"' in result_jcs

# duplicate row hashes retained
dup_schema = pa.schema([pa.field("v", pa.string(), nullable=False)])
dup_batch = pa.record_batch([pa.array(["x", "x"], type=pa.string())], schema=dup_schema)
output, result_jcs = canonical_row_hashes_v1(
    request_jcs([{"name": "v", "nullable": False, "semantic_type": {"kind": "string"}}]),
    dup_batch,
)
table = output.read_all()
assert table.num_rows == 2
assert table.column(0)[0].as_py() == table.column(0)[1].as_py()
assert b'"row_count":"2"' in result_jcs

print("wheel-smoke: empty + multi-batch + duplicate ok")
print("wheel:", "${wheel}")
print("python:", sys.version.split()[0])
print("gateway_compute:", importlib.metadata.version("gateway-compute-python"))
print("gateway_compute_native:", gateway_compute.__version__)
PY

  echo "restoring editable production install"
  uv sync --locked --offline --all-groups --reinstall-package gateway-compute-python
}

component_pytest() {
  cd "${BACKEND_ROOT}"
  export UV_OFFLINE=true
  uv run --offline --no-sync pytest -q \
    "${COMPUTE_PYTHON_ROOT}/tests/test_component_gil.py" \
    "${COMPUTE_PYTHON_ROOT}/tests/test_component_determinism.py" \
    "${COMPUTE_PYTHON_ROOT}/tests/test_component_failure.py"
}

case "${MODE}" in
  wheel-smoke) wheel_smoke ;;
  component-pytest) component_pytest ;;
esac
