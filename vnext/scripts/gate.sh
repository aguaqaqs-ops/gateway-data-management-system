#!/usr/bin/env bash
set -euo pipefail

VNEXT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RUST_ROOT="${VNEXT_ROOT}/rust"
SHARED_KERNEL_ROOT="${VNEXT_ROOT}/shared_kernel"
REPOSITORY_ROOT="${VNEXT_ROOT}/repository_service"

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
    echo "native gate is not implemented until WP3" >&2
    exit 2
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

echo "correctness gate passed"
