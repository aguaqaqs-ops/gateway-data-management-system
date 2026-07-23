#!/usr/bin/env bash
set -euo pipefail

VNEXT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BACKEND_ROOT="${VNEXT_ROOT}/backend"
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
  echo "native-pr gate tmp=${NATIVE_PR_TMP}"
  trap native_pr_on_exit EXIT

  cd "${BACKEND_ROOT}"
  export UV_OFFLINE=true
  uv sync --locked --offline --all-groups

  echo "==> native-pr: build release wheel"
  local python_interpreter wheel
  python_interpreter="$(uv run python -c 'import os, sys; print(os.path.realpath(sys.executable))')"
  export CARGO_TARGET_DIR="${NATIVE_PR_TMP}/cargo-target"
  uv run maturin build \
    --release \
    --manifest-path "${COMPUTE_PYTHON_ROOT}/Cargo.toml" \
    --out "${NATIVE_PR_TMP}/dist" \
    --interpreter "${python_interpreter}"

  wheel="$(ls -1 "${NATIVE_PR_TMP}/dist"/*.whl | head -n 1)"
  echo "release wheel: ${wheel}"

  uv pip install --offline --force-reinstall "${wheel}"
  assert_installed_extension_has_no_test_hooks
  cleanup_compute_python_source_so

  echo "==> native-pr: verify installed module origin"
  uv run --offline --no-sync python - <<'PY'
import importlib.metadata
from pathlib import Path

import gateway_compute
import gateway_compute.gateway_compute as native

module_file = Path(native.__file__).resolve()
parts = set(module_file.parts)
if "site-packages" not in parts and ".venv" not in parts:
    raise SystemExit(f"production extension not installed in venv site-packages: {module_file}")
print("module origin:", module_file)
print("distribution:", importlib.metadata.version("gateway-compute-python"))
print("native version:", gateway_compute.__version__)
PY

  chmod +x "${NATIVE_KERNEL_COMPONENT}"

  echo "==> native-pr: native-kernel component wheel smoke"
  "${NATIVE_KERNEL_COMPONENT}" wheel-smoke

  echo "==> native-pr: native-kernel component probes"
  "${NATIVE_KERNEL_COMPONENT}" component-pytest

  echo "==> native-pr: PR-NATIVE artifact full-chain targeted suite"
  export GATE_PR_NATIVE=1
  uv run --offline --no-sync pytest -q --collect-only -m pr_native
  uv run --offline --no-sync pytest -q -m pr_native

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
