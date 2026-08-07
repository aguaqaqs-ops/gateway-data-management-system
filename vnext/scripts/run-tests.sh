#!/usr/bin/env bash
set -euo pipefail

# Authoritative test entrypoint for the vNext Python packages.
#
# repository_service runs in two passes: the bulk of the suite in parallel,
# then the timing sensitive `serial` tests on their own so they never compete
# for CPU. Every other package is fast enough that xdist worker startup would
# dominate, so they run single process.

VNEXT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

FAST_PACKAGES=(
    shared_kernel
    repository_contracts
    repository_client
    backend
)

for package in "${FAST_PACKAGES[@]}"; do
    echo "==> ${package}"
    (cd "${VNEXT_ROOT}/${package}" && uv run pytest -q "$@")
done

echo "==> repository_service (parallel)"
(cd "${VNEXT_ROOT}/repository_service" && uv run pytest -q -m "not serial" "$@")

echo "==> repository_service (serial)"
(cd "${VNEXT_ROOT}/repository_service" && uv run pytest -q -m serial -n 0 "$@")
