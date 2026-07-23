#!/usr/bin/env bash
set -euo pipefail

VNEXT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RUST_ROOT="${VNEXT_ROOT}/rust"
SHARED_KERNEL_ROOT="${VNEXT_ROOT}/shared_kernel"
REPOSITORY_ROOT="${VNEXT_ROOT}/repository_service"
BACKEND_ROOT="${VNEXT_ROOT}/backend"

usage() {
  echo "usage: $0 bootstrap|correctness|native" >&2
  exit 2
}

MODE="${1:-}"
case "${MODE}" in
  bootstrap)
    cd "${SHARED_KERNEL_ROOT}"
    echo "==> shared_kernel: uv sync --locked --all-groups"
    uv sync --locked --all-groups

    cd "${RUST_ROOT}"
    echo "==> cargo fetch --locked"
    cargo fetch --locked
    ;;
  correctness) ;;
  native)
    NATIVE_PR_GATE="${VNEXT_ROOT}/scripts/native_pr_gate.sh"
    chmod +x "${NATIVE_PR_GATE}"
    exec "${NATIVE_PR_GATE}"
    ;;
  *)
    usage
    ;;
esac

if [[ "${MODE}" != "correctness" ]]; then
  exit 0
fi

cd "${SHARED_KERNEL_ROOT}"

export UV_OFFLINE=true

echo "==> shared_kernel: uv sync --locked --offline --all-groups"
uv sync --locked --offline --all-groups

echo "==> shared_kernel: ruff"
uv run --offline --no-sync ruff check src tests

echo "==> shared_kernel: mypy"
uv run --offline --no-sync mypy

echo "==> shared_kernel: pytest+coverage"
uv run --offline --no-sync pytest -q --cov=gateway_shared_kernel --cov-report=term-missing

cd "${RUST_ROOT}"

export CARGO_TARGET_DIR="${RUST_ROOT}/target/gate"
export CARGO_NET_OFFLINE=true

NORMATIVE_VECTOR_ROOT="${VNEXT_ROOT}/fixtures/vectors/shared-kernel/canonical-encoding/v1"
if [[ ! -d "${NORMATIVE_VECTOR_ROOT}" ]]; then
  echo "missing normative vector root: ${NORMATIVE_VECTOR_ROOT}" >&2
  exit 1
fi

cd "${SHARED_KERNEL_ROOT}"
echo "==> shared_kernel: validate normative vector set"
uv run --offline --no-sync python -m gateway_shared_kernel.testing validate \
  "${NORMATIVE_VECTOR_ROOT}"

export GATEWAY_SHARED_KERNEL_VECTOR_ROOT="${NORMATIVE_VECTOR_ROOT}"

cd "${REPOSITORY_ROOT}"
echo "==> repository_service: uv sync --locked --offline --all-groups"
uv sync --locked --offline --all-groups

echo "==> repository_service: ruff"
uv run --offline --no-sync ruff check src tests

echo "==> repository_service: mypy"
uv run --offline --no-sync mypy

echo "==> repository_service: pytest"
uv run --offline --no-sync pytest -q

cd "${RUST_ROOT}"

echo "==> cargo fmt --check"
cargo fmt --check

echo "==> cargo clippy --locked --offline --workspace --all-targets --all-features -- -D warnings"
cargo clippy --locked --offline --workspace --all-targets --all-features -- -D warnings

echo "==> cargo test --locked --offline --workspace --all-targets"
cargo test --locked --offline --workspace --all-targets

echo "==> cargo build --locked --offline --workspace --release"
cargo build --locked --offline --workspace --release

echo "==> architecture/policy check"
cargo run --locked --offline --quiet --bin gateway-architecture-check -- \
  --rust-workspace-root "${RUST_ROOT}" \
  --vnext-root "${VNEXT_ROOT}"

NATIVE_KERNEL_COMPONENT="${VNEXT_ROOT}/scripts/native_kernel_component.sh"
chmod +x "${NATIVE_KERNEL_COMPONENT}"

echo "==> native-kernel component: wheel EXIT trap regression"
"${NATIVE_KERNEL_COMPONENT}" wheel-trap-regression

echo "==> native-kernel component: release wheel smoke"
"${NATIVE_KERNEL_COMPONENT}" wheel-smoke

cd "${BACKEND_ROOT}"
COMPUTE_PYTHON_ROOT="${RUST_ROOT}/gateway-compute-python"

cleanup_compute_python_source_so() {
  local so
  shopt -s globstar nullglob
  for so in "${COMPUTE_PYTHON_ROOT}"/python/**/*.so; do
    rm -f "${so}"
  done
  shopt -u globstar nullglob
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

echo "==> backend: uv sync --locked --offline --all-groups --reinstall-package gateway-compute-python"
uv sync --locked --offline --all-groups --reinstall-package gateway-compute-python
cleanup_compute_python_source_so

echo "==> native-kernel component: facade determinism / failure / GIL probes"
"${NATIVE_KERNEL_COMPONENT}" component-pytest

echo "==> backend: ruff"
uv run --offline --no-sync ruff check \
  src tests \
  "${COMPUTE_PYTHON_ROOT}/tests"

echo "==> backend: mypy"
uv run --offline --no-sync mypy

echo "==> backend: pytest production extension"
assert_installed_extension_has_no_test_hooks
assert_compute_python_source_tree_clean
uv run --offline --no-sync pytest -q \
  "${COMPUTE_PYTHON_ROOT}/tests/test_facade.py" \
  "${COMPUTE_PYTHON_ROOT}/tests/test_production_extension.py" \
  tests/

assert_installed_extension_has_no_test_hooks
assert_compute_python_source_tree_clean

echo "correctness gate passed"
