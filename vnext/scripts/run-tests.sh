#!/usr/bin/env bash
set -euo pipefail

# Authoritative test entrypoint for the vNext Python packages.
#
# repository_service runs in two passes: the bulk of the suite in parallel,
# then the timing sensitive `serial` tests on their own so they never compete
# for CPU. Every other package is fast enough that xdist worker startup would
# dominate, so they run single process.

VNEXT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TEST_WORKERS="${GATEWAY_TEST_WORKERS:-auto}"
if [[ ! "${TEST_WORKERS}" =~ ^(auto|[0-9]+)$ ]]; then
    echo "error: GATEWAY_TEST_WORKERS must be auto or a non-negative integer" >&2
    exit 2
fi

FAST_PACKAGES=(
    shared_kernel
    repository_contracts
    repository_client
    backend
)

run_locked_pytest() {
    # The repository locks use the canonical PyPI registry. Do not let a
    # machine-wide mirror override the lock identity during test execution;
    # dependency provisioning may still use that mirror explicitly.
    env \
        -u UV_DEFAULT_INDEX \
        -u UV_INDEX_URL \
        -u UV_INSECURE_HOST \
        -u PIP_INDEX_URL \
        -u PIP_TRUSTED_HOST \
        uv run --locked pytest "$@"
}

for package in "${FAST_PACKAGES[@]}"; do
    echo "==> ${package}"
    (cd "${VNEXT_ROOT}/${package}" && run_locked_pytest -q "$@")
done

echo "==> repository_service (parallel)"
(cd "${VNEXT_ROOT}/repository_service" && run_locked_pytest -q -m "not serial" -n "${TEST_WORKERS}" "$@")

echo "==> repository_service (serial)"
(cd "${VNEXT_ROOT}/repository_service" && run_locked_pytest -q -m serial -n 0 "$@")
