#!/usr/bin/env bash
set -euo pipefail

VNEXT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BACKEND_ROOT="${VNEXT_ROOT}/backend"
RUST_ROOT="${VNEXT_ROOT}/rust"
COMPUTE_PYTHON_ROOT="${VNEXT_ROOT}/rust/gateway-compute-python"
NATIVE_KERNEL_COMPONENT="${VNEXT_ROOT}/scripts/native_kernel_component.sh"

cleanup_compute_python_source_so() {
  local so
  shopt -s globstar nullglob
  for so in "${COMPUTE_PYTHON_ROOT}"/python/**/*.so; do
    rm -f "${so}"
  done
  shopt -u globstar nullglob
}

restore_production_install() {
  if [[ "${NATIVE_PR_FORCE_RESTORE_FAIL:-}" == "1" ]]; then
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

assert_compute_python_source_tree_clean() {
  local files=()
  shopt -s globstar nullglob
  files=( "${COMPUTE_PYTHON_ROOT}"/python/**/*.so )
  shopt -u globstar nullglob
  if ((${#files[@]} > 0)); then
    echo "source package tree must not contain .so artifacts:" >&2
    printf '  %s\n' "${files[@]}" >&2
    exit 1
  fi
}

assert_cargo_lock_unchanged() {
  if ! git -C "${VNEXT_ROOT}" diff --exit-code -- "${RUST_ROOT}/Cargo.lock" >/dev/null 2>&1; then
    echo "Cargo.lock changed during native-pr gate" >&2
    git -C "${VNEXT_ROOT}" diff -- "${RUST_ROOT}/Cargo.lock" >&2 || true
    exit 1
  fi
}

capture_wheel_identity() {
  local wheel_path="$1"
  local out_file="$2"
  uv run --offline --no-sync python - "${wheel_path}" "${out_file}" "${VNEXT_ROOT}" <<'PY'
import hashlib
import importlib.metadata
import json
import sys
from pathlib import Path

import gateway_compute.gateway_compute as native

wheel_path = Path(sys.argv[1])
out_file = Path(sys.argv[2])
repo_root = Path(sys.argv[3])
source_tree = repo_root / "rust" / "gateway-compute-python"

module_file = Path(native.__file__).resolve()
if str(module_file).startswith(str(source_tree)):
    raise SystemExit(f"extension must not load from source tree: {module_file}")

wheel_sha256 = hashlib.sha256(wheel_path.read_bytes()).hexdigest()
extension_sha256 = hashlib.sha256(module_file.read_bytes()).hexdigest()

dist = importlib.metadata.distribution("gateway-compute-python")
direct_url = None
for path in dist.files or []:
    if path.name == "direct_url.json":
        direct_url = json.loads(dist.locate_file(path).read_text(encoding="utf-8"))
        break

if direct_url is None:
    raise SystemExit("direct_url.json missing for gateway-compute-python")

url = direct_url.get("url", "")
if not url.endswith(".whl"):
    raise SystemExit(f"expected wheel direct_url, got: {url}")
if str(source_tree) in url:
    raise SystemExit(f"direct_url must not reference source tree: {url}")

identity = {
    "wheel_path": str(wheel_path.resolve()),
    "wheel_sha256": wheel_sha256,
    "extension_sha256": extension_sha256,
    "module_file": str(module_file),
    "version": importlib.metadata.version("gateway-compute-python"),
    "direct_url": direct_url,
}
out_file.write_text(json.dumps(identity, indent=2, sort_keys=True) + "\n", encoding="utf-8")
print("wheel identity captured:", wheel_sha256[:16], extension_sha256[:16])
PY
}

assert_wheel_identity_unchanged() {
  local baseline_file="$1"
  local label="$2"
  uv run --offline --no-sync python - "${baseline_file}" "${label}" <<'PY'
import hashlib
import importlib.metadata
import json
import sys
from pathlib import Path

import gateway_compute.gateway_compute as native

baseline_file = Path(sys.argv[1])
label = sys.argv[2]
baseline = json.loads(baseline_file.read_text(encoding="utf-8"))

module_file = Path(native.__file__).resolve()
extension_sha256 = hashlib.sha256(module_file.read_bytes()).hexdigest()
version = importlib.metadata.version("gateway-compute-python")

if extension_sha256 != baseline["extension_sha256"]:
    raise SystemExit(
        f"wheel extension identity changed at {label}: "
        f"{baseline['extension_sha256']} -> {extension_sha256}"
    )
if version != baseline["version"]:
    raise SystemExit(
        f"gateway-compute-python version changed at {label}: "
        f"{baseline['version']} -> {version}"
    )
if str(module_file) != baseline["module_file"]:
    raise SystemExit(
        f"extension module path changed at {label}: "
        f"{baseline['module_file']} -> {module_file}"
    )
print(f"wheel identity unchanged at {label}")
PY
}

native_pr_finalize_exit() {
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

native_pr_on_exit() {
  local ec=$?
  local restore_ec=0
  restore_production_install || restore_ec=$?
  CARGO_TARGET_DIR="${NATIVE_PR_SAVED_CARGO_TARGET_DIR-}"
  if [[ -n "${NATIVE_PR_TMP:-}" ]]; then
    rm -rf "${NATIVE_PR_TMP}"
    NATIVE_PR_TMP=""
  fi
  native_pr_finalize_exit "${ec}" "${restore_ec}"
  exit $?
}

native_pr_exit_trap_regression() {
  local tmp final_ec saved_cargo_target_dir marker
  saved_cargo_target_dir="${CARGO_TARGET_DIR-}"

  echo "==> native-pr EXIT trap regression: body ok + restore fail"
  marker="$(mktemp)"
  set +e
  (
    set -euo pipefail
    export NATIVE_PR_FORCE_RESTORE_FAIL=1
    NATIVE_PR_TMP="$(mktemp -d)"
    NATIVE_PR_SAVED_CARGO_TARGET_DIR="${saved_cargo_target_dir}"
    export CARGO_TARGET_DIR="${NATIVE_PR_TMP}/cargo-target"
    mkdir -p "${CARGO_TARGET_DIR}"
    printf '%s\n' "${NATIVE_PR_TMP}" >"${marker}"
    echo "regression tmp=${NATIVE_PR_TMP}"
    trap native_pr_on_exit EXIT
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

  echo "==> native-pr EXIT trap regression: body fail + restore fail"
  marker="$(mktemp)"
  set +e
  (
    set -euo pipefail
    export NATIVE_PR_FORCE_RESTORE_FAIL=1
    NATIVE_PR_TMP="$(mktemp -d)"
    NATIVE_PR_SAVED_CARGO_TARGET_DIR="${saved_cargo_target_dir}"
    export CARGO_TARGET_DIR="${NATIVE_PR_TMP}/cargo-target"
    mkdir -p "${CARGO_TARGET_DIR}"
    printf '%s\n' "${NATIVE_PR_TMP}" >"${marker}"
    echo "regression tmp=${NATIVE_PR_TMP}"
    trap native_pr_on_exit EXIT
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

  unset NATIVE_PR_FORCE_RESTORE_FAIL || true
  if [[ "${CARGO_TARGET_DIR-}" != "${saved_cargo_target_dir}" ]]; then
    echo "parent CARGO_TARGET_DIR mutated: ${CARGO_TARGET_DIR-}" >&2
    exit 1
  fi
  echo "native-pr EXIT trap regression ok"
}

run_native_pr_gate_body() {
  native_pr_exit_trap_regression

  NATIVE_PR_TMP="$(mktemp -d)"
  NATIVE_PR_SAVED_CARGO_TARGET_DIR="${CARGO_TARGET_DIR-}"
  NATIVE_PR_WHEEL_IDENTITY_FILE="${NATIVE_PR_TMP}/wheel-identity.json"
  echo "native-pr gate tmp=${NATIVE_PR_TMP}"
  trap native_pr_on_exit EXIT

  cd "${BACKEND_ROOT}"
  export UV_OFFLINE=true
  uv sync --locked --offline --all-groups

  assert_cargo_lock_unchanged

  echo "==> native-pr: build release wheel"
  local python_interpreter wheel
  python_interpreter="$(uv run python -c 'import os, sys; print(os.path.realpath(sys.executable))')"
  export CARGO_TARGET_DIR="${NATIVE_PR_TMP}/cargo-target"
  export CARGO_NET_OFFLINE=true
  uv run maturin build \
    --release \
    --locked \
    --offline \
    --manifest-path "${COMPUTE_PYTHON_ROOT}/Cargo.toml" \
    --out "${NATIVE_PR_TMP}/dist" \
    --interpreter "${python_interpreter}"

  assert_cargo_lock_unchanged

  wheel="$(ls -1 "${NATIVE_PR_TMP}/dist"/*.whl | head -n 1)"
  echo "release wheel: ${wheel}"

  uv pip install --offline --force-reinstall "${wheel}"
  assert_installed_extension_has_no_test_hooks
  cleanup_compute_python_source_so
  capture_wheel_identity "${wheel}" "${NATIVE_PR_WHEEL_IDENTITY_FILE}"

  chmod +x "${NATIVE_KERNEL_COMPONENT}"

  echo "==> native-pr: installed-wheel smoke (no rebuild/sync)"
  "${NATIVE_KERNEL_COMPONENT}" wheel-smoke-installed

  echo "==> native-pr: authoritative Rust kernel_component probes"
  cd "${RUST_ROOT}"
  export CARGO_NET_OFFLINE=true
  cargo test --locked --offline --package gateway-compute-python-impl kernel_component

  cd "${BACKEND_ROOT}"
  assert_wheel_identity_unchanged "${NATIVE_PR_WHEEL_IDENTITY_FILE}" "after kernel_component tests"

  echo "==> native-pr: native-kernel component facade probes"
  "${NATIVE_KERNEL_COMPONENT}" component-pytest

  assert_wheel_identity_unchanged "${NATIVE_PR_WHEEL_IDENTITY_FILE}" "after component-pytest"

  echo "==> native-pr: PR-NATIVE artifact full-chain targeted suite"
  export GATE_PR_NATIVE=1
  NATIVE_PR_WHEEL_SHA256="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["wheel_sha256"])' "${NATIVE_PR_WHEEL_IDENTITY_FILE}")"
  export NATIVE_PR_WHEEL_SHA256
  uv run --offline --no-sync pytest -q --collect-only -m pr_native
  uv run --offline --no-sync pytest -q -m pr_native

  assert_wheel_identity_unchanged "${NATIVE_PR_WHEEL_IDENTITY_FILE}" "after pr_native suite"
  assert_installed_extension_has_no_test_hooks
  assert_compute_python_source_tree_clean
  echo "native gate passed"
}

usage() {
  echo "usage: $0 [gate|trap-regression]" >&2
  exit 2
}

MODE="${1:-gate}"
case "${MODE}" in
  gate) run_native_pr_gate_body ;;
  trap-regression) native_pr_exit_trap_regression ;;
  *) usage ;;
esac
