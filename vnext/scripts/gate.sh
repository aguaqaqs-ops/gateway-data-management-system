#!/usr/bin/env bash
set -euo pipefail

VNEXT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RUST_ROOT="${VNEXT_ROOT}/rust"

usage() {
  echo "usage: $0 bootstrap|correctness|native" >&2
  exit 2
}

MODE="${1:-}"
case "${MODE}" in
  bootstrap)
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

cd "${RUST_ROOT}"

export CARGO_NET_OFFLINE=true

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
