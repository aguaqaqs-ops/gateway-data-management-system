#!/usr/bin/env bash
set -euo pipefail

VNEXT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RUST_ROOT="${VNEXT_ROOT}/rust"

cd "${RUST_ROOT}"

echo "==> cargo fetch --locked"
cargo fetch --locked

echo "Rust workspace dependencies are cached for offline correctness gate."
