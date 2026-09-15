#!/usr/bin/env bash
set -euo pipefail

VNEXT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BACKEND_ROOT="${VNEXT_ROOT}/backend"
COMPUTE_PYTHON_ROOT="${VNEXT_ROOT}/rust/gateway-compute-python"
RUST_ROOT="${VNEXT_ROOT}/rust"
# shellcheck source=lib/gateway-index-env.sh
source "${VNEXT_ROOT}/scripts/lib/gateway-index-env.sh"
UV_CONSUME="${VNEXT_ROOT}/scripts/uv-consume.sh"

usage() {
  echo "usage: $0 wheel-smoke|wheel-smoke-installed|component-pytest|wheel-trap-regression" >&2
  exit 2
}

MODE="${1:-}"
case "${MODE}" in
  wheel-smoke | wheel-smoke-installed | component-pytest | wheel-trap-regression) ;;
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
  export UV_OFFLINE=true
  "${UV_CONSUME}" -C "${BACKEND_ROOT}" sync --offline --all-groups --reinstall-package gateway-compute-python
  cleanup_compute_python_source_so
}

assert_installed_extension_has_no_test_hooks() {
  "${UV_CONSUME}" -C "${BACKEND_ROOT}" run --offline --no-sync python - <<'PY'
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

assert_installed_wheel_provenance() {
  "${UV_CONSUME}" -C "${BACKEND_ROOT}" run --offline --no-sync python - <<'PY'
import hashlib
import importlib.metadata
import json
import os
import sys
from pathlib import Path
from urllib.parse import unquote, urlparse

import gateway_compute
import gateway_compute.gateway_compute as native

source_root = Path(os.environ["NATIVE_KERNEL_SOURCE_ROOT"]).resolve()
wheel_path = Path(os.environ["NATIVE_KERNEL_WHEEL_PATH"]).resolve()
expected_sha256 = os.environ["NATIVE_KERNEL_WHEEL_SHA256"]
module_file = Path(native.__file__).resolve()
if module_file.is_relative_to(source_root):
    raise SystemExit(f"native module came from editable/source tree: {module_file}")
if not module_file.is_relative_to(Path(sys.prefix).resolve()):
    raise SystemExit(f"native module is outside active environment: {module_file}")

actual_sha256 = hashlib.sha256(wheel_path.read_bytes()).hexdigest()
if actual_sha256 != expected_sha256:
    raise SystemExit(f"wheel hash mismatch: {actual_sha256} != {expected_sha256}")

dist = importlib.metadata.distribution("gateway-compute-python")
direct_url = None
for path in dist.files or []:
    if path.name == "direct_url.json":
        direct_url = json.loads(dist.locate_file(path).read_text(encoding="utf-8"))
        break
if not isinstance(direct_url, dict):
    raise SystemExit("installed wheel is missing direct_url.json")
origin_url = direct_url.get("url")
if not isinstance(origin_url, str) or not origin_url.endswith(".whl"):
    raise SystemExit(f"installed distribution origin is not a wheel: {origin_url!r}")
origin_path = Path(unquote(urlparse(origin_url).path)).resolve()
if origin_path != wheel_path:
    raise SystemExit(f"installed wheel origin mismatch: {origin_path} != {wheel_path}")
if not hasattr(gateway_compute, "canonical_row_hashes_v1"):
    raise SystemExit("canonical_row_hashes_v1 is not importable from installed wheel")
if hasattr(gateway_compute, "canonical_row_hashes_v2"):
    raise SystemExit("legacy canonical_row_hashes_v2 leaked from installed wheel")
print("wheel-smoke: provenance ok")
PY
}

build_release_wheel() {
  local out_dir="$1"
  local python_interpreter
  python_interpreter="$("${UV_CONSUME}" -C "${BACKEND_ROOT}" run python -c 'import os, sys; print(os.path.realpath(sys.executable))')"
  export CARGO_NET_OFFLINE=true
  "${UV_CONSUME}" -C "${BACKEND_ROOT}" run maturin build \
    --release \
    --locked \
    --offline \
    --manifest-path "${COMPUTE_PYTHON_ROOT}/Cargo.toml" \
    --out "${out_dir}" \
    --interpreter "${python_interpreter}"
}

# Decide final exit code after wheel-smoke body + restore attempt.
wheel_smoke_finalize_exit() {
  local body_ec="$1"
  local restore_ec="$2"
  local lock_ec="${3:-0}"
  if [[ "${lock_ec}" -ne 0 ]]; then
    if [[ "${body_ec}" -eq 0 ]]; then
      return "${lock_ec}"
    fi
    return "${body_ec}"
  fi
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
  local lock_ec=0
  restore_production_install || restore_ec=$?
  CARGO_TARGET_DIR="${WHEEL_SMOKE_SAVED_CARGO_TARGET_DIR-}"
  if [[ -n "${WHEEL_SMOKE_TMP:-}" ]]; then
    rm -rf "${WHEEL_SMOKE_TMP}"
    WHEEL_SMOKE_TMP=""
  fi
  if [[ -n "${WHEEL_SMOKE_LOCK_SNAPSHOT:-}" ]]; then
    gateway_assert_lockfiles_unchanged "${VNEXT_ROOT}" "${WHEEL_SMOKE_LOCK_SNAPSHOT}" || lock_ec=$?
    rm -f "${WHEEL_SMOKE_LOCK_SNAPSHOT}"
    WHEEL_SMOKE_LOCK_SNAPSHOT=""
  fi
  wheel_smoke_finalize_exit "${ec}" "${restore_ec}" "${lock_ec}"
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
    WHEEL_SMOKE_LOCK_SNAPSHOT="$(mktemp)"
    gateway_snapshot_lockfile_sha256 "${VNEXT_ROOT}" >"${WHEEL_SMOKE_LOCK_SNAPSHOT}"
    export CARGO_TARGET_DIR="${WHEEL_SMOKE_TMP}/cargo-target"
    mkdir -p "${CARGO_TARGET_DIR}"
    printf '%s\n' "${WHEEL_SMOKE_TMP}" >"${marker}"
    echo "regression tmp=${WHEEL_SMOKE_TMP}"
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
    WHEEL_SMOKE_LOCK_SNAPSHOT="$(mktemp)"
    gateway_snapshot_lockfile_sha256 "${VNEXT_ROOT}" >"${WHEEL_SMOKE_LOCK_SNAPSHOT}"
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

run_installed_wheel_smoke_python() {
  local wheel_label="${1:-installed-wheel}"
  "${UV_CONSUME}" -C "${BACKEND_ROOT}" run --offline --no-sync python - <<PY
import importlib.metadata
import json
import sys

import pyarrow as pa

import gateway_compute
from gateway_compute import canonical_row_hashes_v1

OUTPUT_ROW_HASH_SCHEMA = pa.schema([pa.field("row_hash", pa.binary(32), nullable=False)])


def request_jcs(fields):
    payload = {
        "boundary_version": 1,
        "canonical_encoding_version": 1,
        "arrow_mapping_version": 1,
        "declared_fields": fields,
    }
    return json.dumps(payload, separators=(",", ":"), sort_keys=True).encode()


def read_row_hashes(reader):
    table = reader.read_all()
    assert table.schema == OUTPUT_ROW_HASH_SCHEMA
    column = table.column(0)
    return [column[i].as_py() for i in range(table.num_rows)]


def assert_sorted_unsigned_lexicographic(hashes):
    assert hashes == sorted(hashes)


reader = pa.RecordBatchReader.from_batches(pa.schema([]), [])
output, result_jcs = canonical_row_hashes_v1(request_jcs([]), reader)
assert isinstance(output, pa.RecordBatchReader)
assert b'"row_count":"0"' in result_jcs
assert read_row_hashes(output) == []
parsed = json.loads(result_jcs.decode())
assert parsed["boundary_version"] == 1
assert parsed["raw_content_digest"].startswith("sha256:")
assert parsed["table_schema_digest"].startswith("sha256:")
print("wheel-smoke: empty table ok")

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
assert parsed["boundary_version"] == 1
assert parsed["raw_content_digest"].startswith("sha256:")
assert parsed["table_schema_digest"].startswith("sha256:")
print("wheel-smoke: multi-batch ok")

dup_batch = pa.record_batch([pa.array(["x", "x"], type=pa.string())], schema=schema)
dup_reader = pa.RecordBatchReader.from_batches(schema, [dup_batch])
output, result_jcs = canonical_row_hashes_v1(request_jcs(fields), dup_reader)
hashes = read_row_hashes(output)
assert b'"row_count":"2"' in result_jcs
assert len(hashes) == 2
assert hashes[0] == hashes[1]
print("wheel-smoke: duplicate rows ok")

print("wheel-smoke: installed wheel ok")
print("wheel:", "${wheel_label}")
print("python:", sys.version.split()[0])
print("gateway_compute:", importlib.metadata.version("gateway-compute-python"))
print("gateway_compute_native:", gateway_compute.__version__)
PY
}

wheel_smoke_installed() {
  export UV_OFFLINE=true
  run_installed_wheel_smoke_python "preinstalled"
}

wheel_smoke() {
  (
    set -euo pipefail
    local wheel
    WHEEL_SMOKE_TMP="$(mktemp -d)"
    WHEEL_SMOKE_SAVED_CARGO_TARGET_DIR="${CARGO_TARGET_DIR-}"
    WHEEL_SMOKE_LOCK_SNAPSHOT="$(mktemp)"
    gateway_snapshot_lockfile_sha256 "${VNEXT_ROOT}" >"${WHEEL_SMOKE_LOCK_SNAPSHOT}"
    echo "wheel-smoke tmp=${WHEEL_SMOKE_TMP}"
    trap wheel_smoke_on_exit EXIT

    export UV_OFFLINE=true
    "${UV_CONSUME}" -C "${BACKEND_ROOT}" sync --offline --all-groups

    echo "building release wheel into ${WHEEL_SMOKE_TMP}/dist"
    export CARGO_TARGET_DIR="${WHEEL_SMOKE_TMP}/cargo-target"
    build_release_wheel "${WHEEL_SMOKE_TMP}/dist"

    wheel="$(ls -1 "${WHEEL_SMOKE_TMP}/dist"/*.whl | head -n 1)"
    echo "release wheel: ${wheel}"

    export NATIVE_KERNEL_SOURCE_ROOT="${COMPUTE_PYTHON_ROOT}/python"
    export NATIVE_KERNEL_WHEEL_PATH="${wheel}"
    export NATIVE_KERNEL_WHEEL_SHA256="$(sha256sum "${wheel}" | awk '{print $1}')"
    "${UV_CONSUME}" -C "${BACKEND_ROOT}" pip-install --offline --force-reinstall "${wheel}"
    assert_installed_extension_has_no_test_hooks
    assert_installed_wheel_provenance
    run_installed_wheel_smoke_python "${wheel}"
  )
}

component_pytest() {
  export UV_OFFLINE=true
  "${UV_CONSUME}" -C "${BACKEND_ROOT}" run --offline --no-sync pytest -q \
    "${COMPUTE_PYTHON_ROOT}/tests/test_v1.py"
}

case "${MODE}" in
  wheel-smoke) wheel_smoke ;;
  wheel-smoke-installed) wheel_smoke_installed ;;
  component-pytest) component_pytest ;;
  wheel-trap-regression) wheel_smoke_exit_trap_regression ;;
esac
