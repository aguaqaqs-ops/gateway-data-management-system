#!/usr/bin/env bash
set -euo pipefail

VNEXT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BACKEND_ROOT="${VNEXT_ROOT}/backend"
COMPUTE_PYTHON_ROOT="${VNEXT_ROOT}/rust/gateway-compute-python"

usage() {
  echo "usage: $0 wheel-smoke|component-pytest|wheel-trap-regression" >&2
  exit 2
}

MODE="${1:-}"
case "${MODE}" in
  wheel-smoke | component-pytest | wheel-trap-regression) ;;
  *) usage ;;
esac

cleanup_compute_python_source_so() {
  local so
  shopt -s globstar nullglob
  for so in "${COMPUTE_PYTHON_ROOT}"/python/**/*.so; do
    rm -f "${so}"
  done
  shopt -u globstar nullglob
}

restore_production_install() {
  if [[ "${NATIVE_KERNEL_FORCE_RESTORE_FAIL:-}" == "1" ]]; then
    echo "injecting restore_production_install failure" >&2
    return 99
  fi
  cd "${BACKEND_ROOT}"
  export UV_OFFLINE=true
  uv sync --locked --offline --all-groups --reinstall-package gateway-compute-python
  cleanup_compute_python_source_so
}

assert_installed_extension_has_no_test_hooks() {
  uv run --offline --no-sync python - <<'PY'
import gateway_compute.gateway_compute as native

bad = [
    name
    for name in dir(native)
    if name.startswith("_test_") or name.startswith("_TEST_")
]
if bad:
    raise SystemExit(f"production extension must not export test hooks: {bad}")
PY
}

# Decide final exit code after wheel-smoke body + restore attempt.
wheel_smoke_finalize_exit() {
  local body_ec="$1"
  local restore_ec="$2"
  if [[ "${body_ec}" -eq 0 && "${restore_ec}" -ne 0 ]]; then
    echo "restore_production_install failed with exit ${restore_ec}" >&2
    return "${restore_ec}"
  fi
  if [[ "${body_ec}" -ne 0 && "${restore_ec}" -ne 0 ]]; then
    echo "restore_production_install also failed: ${restore_ec}" >&2
  fi
  return "${body_ec}"
}

# Shared EXIT handler for production wheel_smoke and wheel-trap-regression.
# Requires WHEEL_SMOKE_TMP and WHEEL_SMOKE_SAVED_CARGO_TARGET_DIR in the same shell.
wheel_smoke_on_exit() {
  local ec=$?
  local restore_ec=0
  restore_production_install || restore_ec=$?
  CARGO_TARGET_DIR="${WHEEL_SMOKE_SAVED_CARGO_TARGET_DIR-}"
  if [[ -n "${WHEEL_SMOKE_TMP:-}" ]]; then
    rm -rf "${WHEEL_SMOKE_TMP}"
    WHEEL_SMOKE_TMP=""
  fi
  wheel_smoke_finalize_exit "${ec}" "${restore_ec}"
  exit $?
}

wheel_smoke_exit_trap_regression() {
  local tmp final_ec saved_cargo_target_dir marker
  saved_cargo_target_dir="${CARGO_TARGET_DIR-}"

  echo "==> wheel-smoke EXIT trap regression: body ok + restore fail"
  marker="$(mktemp)"
  set +e
  (
    set -euo pipefail
    export NATIVE_KERNEL_FORCE_RESTORE_FAIL=1
    WHEEL_SMOKE_TMP="$(mktemp -d)"
    WHEEL_SMOKE_SAVED_CARGO_TARGET_DIR="${saved_cargo_target_dir}"
    export CARGO_TARGET_DIR="${WHEEL_SMOKE_TMP}/cargo-target"
    mkdir -p "${CARGO_TARGET_DIR}"
    printf '%s\n' "${WHEEL_SMOKE_TMP}" >"${marker}"
    echo "regression tmp=${WHEEL_SMOKE_TMP}"
    # Install the same production EXIT handler used by wheel_smoke.
    trap wheel_smoke_on_exit EXIT
    exit 0
  )
  final_ec=$?
  set -e
  tmp="$(cat "${marker}")"
  rm -f "${marker}"
  if [[ "${final_ec}" -ne 99 ]]; then
    echo "expected exit 99 for restore failure after success, got ${final_ec}" >&2
    exit 1
  fi
  if [[ -e "${tmp}" ]]; then
    echo "tmp not cleaned after shared-trap restore-failure: ${tmp}" >&2
    exit 1
  fi
  if [[ "${CARGO_TARGET_DIR-}" != "${saved_cargo_target_dir}" ]]; then
    echo "parent CARGO_TARGET_DIR mutated after case 1: ${CARGO_TARGET_DIR-}" >&2
    exit 1
  fi

  echo "==> wheel-smoke EXIT trap regression: body fail + restore fail"
  marker="$(mktemp)"
  set +e
  (
    set -euo pipefail
    export NATIVE_KERNEL_FORCE_RESTORE_FAIL=1
    WHEEL_SMOKE_TMP="$(mktemp -d)"
    WHEEL_SMOKE_SAVED_CARGO_TARGET_DIR="${saved_cargo_target_dir}"
    export CARGO_TARGET_DIR="${WHEEL_SMOKE_TMP}/cargo-target"
    mkdir -p "${CARGO_TARGET_DIR}"
    printf '%s\n' "${WHEEL_SMOKE_TMP}" >"${marker}"
    echo "regression tmp=${WHEEL_SMOKE_TMP}"
    trap wheel_smoke_on_exit EXIT
    exit 42
  )
  final_ec=$?
  set -e
  tmp="$(cat "${marker}")"
  rm -f "${marker}"
  if [[ "${final_ec}" -ne 42 ]]; then
    echo "expected original body exit 42 when both fail, got ${final_ec}" >&2
    exit 1
  fi
  if [[ -e "${tmp}" ]]; then
    echo "tmp not cleaned after shared-trap dual-failure: ${tmp}" >&2
    exit 1
  fi

  unset NATIVE_KERNEL_FORCE_RESTORE_FAIL || true
  if [[ "${CARGO_TARGET_DIR-}" != "${saved_cargo_target_dir}" ]]; then
    echo "parent CARGO_TARGET_DIR mutated: ${CARGO_TARGET_DIR-}" >&2
    exit 1
  fi
  echo "wheel-smoke EXIT trap regression ok"
}

wheel_smoke() {
  (
    set -euo pipefail
    local wheel
    WHEEL_SMOKE_TMP="$(mktemp -d)"
    WHEEL_SMOKE_SAVED_CARGO_TARGET_DIR="${CARGO_TARGET_DIR-}"
    echo "wheel-smoke tmp=${WHEEL_SMOKE_TMP}"
    trap wheel_smoke_on_exit EXIT

    cd "${BACKEND_ROOT}"
    export UV_OFFLINE=true
    uv sync --locked --offline --all-groups

    echo "building release wheel into ${WHEEL_SMOKE_TMP}/dist"
    local python_interpreter
    python_interpreter="$(uv run python -c 'import os, sys; print(os.path.realpath(sys.executable))')"
    export CARGO_TARGET_DIR="${WHEEL_SMOKE_TMP}/cargo-target"
    uv run maturin build \
      --release \
      --manifest-path "${COMPUTE_PYTHON_ROOT}/Cargo.toml" \
      --out "${WHEEL_SMOKE_TMP}/dist" \
      --interpreter "${python_interpreter}"

    wheel="$(ls -1 "${WHEEL_SMOKE_TMP}/dist"/*.whl | head -n 1)"
  echo "release wheel: ${wheel}"

  uv pip install --offline --force-reinstall "${wheel}"
  assert_installed_extension_has_no_test_hooks

  uv run --offline --no-sync python - <<PY
import importlib.metadata
import json
import sys

import pyarrow as pa

import gateway_compute
from gateway_compute import canonical_row_hashes_v1

OUTPUT_ROW_HASH_SCHEMA = pa.schema([pa.field("row_hash", pa.binary(32), nullable=False)])


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


def read_row_hashes(reader):
    table = reader.read_all()
    assert table.schema == OUTPUT_ROW_HASH_SCHEMA
    column = table.column(0)
    return [column[i].as_py() for i in range(table.num_rows)]


def assert_sorted_unsigned_lexicographic(hashes):
    assert hashes == sorted(hashes)


# empty table
reader = pa.RecordBatchReader.from_batches(pa.schema([]), [])
output, result_jcs = canonical_row_hashes_v1(request_jcs([]), reader)
assert isinstance(output, pa.RecordBatchReader)
assert b'"row_count":"0"' in result_jcs
assert read_row_hashes(output) == []
parsed = json.loads(result_jcs.decode())
assert parsed["raw_content_digest"].startswith("sha256:")
assert parsed["table_schema_digest"].startswith("sha256:")
print("wheel-smoke: empty table ok")

# multi-batch (3 rows)
fields = [{"name": "v", "nullable": False, "semantic_type": {"kind": "string"}}]
schema = pa.schema([pa.field("v", pa.string(), nullable=False)])
multi_reader = pa.RecordBatchReader.from_batches(
    schema,
    [
        pa.record_batch([pa.array(["alpha"], type=pa.string())], schema=schema),
        pa.record_batch([pa.array(["beta", "gamma"], type=pa.string())], schema=schema),
    ],
)
output, result_jcs = canonical_row_hashes_v1(request_jcs(fields), multi_reader)
hashes = read_row_hashes(output)
assert b'"row_count":"3"' in result_jcs
assert len(hashes) == 3
assert len(set(hashes)) == 3
assert_sorted_unsigned_lexicographic(hashes)
parsed = json.loads(result_jcs.decode())
assert parsed["raw_content_digest"].startswith("sha256:")
assert parsed["table_schema_digest"].startswith("sha256:")
print("wheel-smoke: multi-batch ok")

# duplicate rows (same hash retained twice)
dup_batch = pa.record_batch([pa.array(["x", "x"], type=pa.string())], schema=schema)
dup_reader = pa.RecordBatchReader.from_batches(schema, [dup_batch])
output, result_jcs = canonical_row_hashes_v1(request_jcs(fields), dup_reader)
hashes = read_row_hashes(output)
assert b'"row_count":"2"' in result_jcs
assert len(hashes) == 2
assert hashes[0] == hashes[1]
print("wheel-smoke: duplicate rows ok")

print("wheel-smoke: installed wheel ok")
print("wheel:", "${wheel}")
print("python:", sys.version.split()[0])
print("gateway_compute:", importlib.metadata.version("gateway-compute-python"))
print("gateway_compute_native:", gateway_compute.__version__)
PY
  )
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
  wheel-trap-regression) wheel_smoke_exit_trap_regression ;;
esac
