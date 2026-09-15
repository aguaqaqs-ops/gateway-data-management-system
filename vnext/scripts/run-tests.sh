#!/usr/bin/env bash
set -euo pipefail

# Authoritative test entrypoint for the vNext Python packages.
#
# repository_service runs in two passes: the bulk of the suite in parallel,
# then the timing sensitive `serial` tests on their own so they never compete
# for CPU. Every other package is fast enough that xdist worker startup would
# dominate, so they run single process.

VNEXT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# shellcheck source=lib/gateway-index-env.sh
source "${VNEXT_ROOT}/scripts/lib/gateway-index-env.sh"
UV_CONSUME="${GATEWAY_UV_CONSUME:-${VNEXT_ROOT}/scripts/uv-consume.sh}"
TEST_WORKERS="${GATEWAY_TEST_WORKERS:-auto}"
if [[ ! "${TEST_WORKERS}" =~ ^(auto|[0-9]+)$ ]]; then
    echo "error: GATEWAY_TEST_WORKERS must be auto or a non-negative integer" >&2
    exit 2
fi

PYTEST_TMP_ARGS=()
if [[ -n "${GATEWAY_TEST_BASETEMP:-}" ]]; then
    if [[ "${GATEWAY_TEST_BASETEMP}" != /* ]]; then
        echo "error: GATEWAY_TEST_BASETEMP must be an absolute path" >&2
        exit 2
    fi
    mkdir -p "${GATEWAY_TEST_BASETEMP}"
    PYTEST_TMP_ARGS+=(--basetemp "${GATEWAY_TEST_BASETEMP}")
fi

FAST_PACKAGES=(
    shared_kernel
    repository_contracts
    repository_client
    backend
)

COMPOSE_TEST_FILES=(
    tests/test_compose_lifecycle_negative_probes.py
    tests/test_import_compose_e2e.py
    tests/test_versioned_read_compose_e2e.py
)

LOCK_SNAPSHOT="$(mktemp)"
trap 'rm -f "${LOCK_SNAPSHOT}"' EXIT
gateway_snapshot_lockfile_sha256 "${VNEXT_ROOT}" >"${LOCK_SNAPSHOT}"

export GATEWAY_UV_CONSUME_SKIP_LOCK_ASSERT=1

run_locked_pytest() {
    "${UV_CONSUME}" -C . run pytest "${PYTEST_TMP_ARGS[@]}" "$@"
}

test_exit=0
for package in "${FAST_PACKAGES[@]}"; do
    echo "==> ${package}"
    if ! (cd "${VNEXT_ROOT}/${package}" && run_locked_pytest -q "$@"); then
        test_exit=1
    fi
done

echo "==> repository_service (parallel)"
if ! (
    cd "${VNEXT_ROOT}/repository_service"
    run_locked_pytest -q -m "(not serial) or parallel_safe" -n "${TEST_WORKERS}" "$@"
); then
    test_exit=1
fi

echo "==> repository_service (serial)"
if [[ -n "${GATEWAY_TEST_BASETEMP:-}" ]]; then
    # Docker secret bind mounts cannot be remounted from an LXC-provided
    # tmpfs in the authoritative Compose path. Keep those host paths on the
    # real filesystem while using tmpfs for all other test-owned workspaces.
    COMPOSE_IGNORES=()
    for compose_file in "${COMPOSE_TEST_FILES[@]}"; do
        COMPOSE_IGNORES+=("--ignore=${compose_file}")
    done
    if ! (
        cd "${VNEXT_ROOT}/repository_service"
        run_locked_pytest -q -m "serial and not parallel_safe" -n 0 "${COMPOSE_IGNORES[@]}" "$@"
    ); then
        test_exit=1
    fi
    PYTEST_TMP_ARGS=()
    if ! (
        cd "${VNEXT_ROOT}/repository_service"
        run_locked_pytest -q -m "serial and not parallel_safe" -n 0 "${COMPOSE_TEST_FILES[@]}" "$@"
    ); then
        test_exit=1
    fi
else
    if ! (
        cd "${VNEXT_ROOT}/repository_service"
        run_locked_pytest -q -m "serial and not parallel_safe" -n 0 "$@"
    ); then
        test_exit=1
    fi
fi

if ! gateway_assert_lockfiles_unchanged "${VNEXT_ROOT}" "${LOCK_SNAPSHOT}"; then
    exit 1
fi

exit "${test_exit}"
