#!/usr/bin/env bash
set -euo pipefail

# Authoritative test entrypoint for the vNext Python packages.
#
# backend and repository_service run in two passes: the bulk of each suite in
# parallel, then timing sensitive serial tests on their own so they never
# compete for CPU. The three smaller packages run in one process.

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
)

BACKEND_COMPOSE_TEST_FILES=(
    tests/test_archive_compose_e2e.py
    tests/test_backend_http_container_gate.py
    tests/test_history_compose_e2e.py
    tests/test_ordered_compare_compose.py
    tests/test_ordered_submit_bisect_compose.py
    tests/test_review_compose_e2e.py
    tests/test_submit_compose_e2e.py
)

REPOSITORY_SERVICE_COMPOSE_TEST_FILES=(
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

echo "==> backend (parallel)"
backend_parallel_start=${SECONDS}
backend_parallel_status=0
if ! (
    cd "${VNEXT_ROOT}/backend"
    run_locked_pytest -q -m "(not serial) or parallel_safe" -n "${TEST_WORKERS}" "$@"
); then
    test_exit=1
    backend_parallel_status=1
fi
echo "==> backend (parallel) elapsed_seconds=$((SECONDS - backend_parallel_start)) status=${backend_parallel_status}"

echo "==> backend (serial)"
backend_serial_start=${SECONDS}
backend_serial_status=0
if [[ -n "${GATEWAY_TEST_BASETEMP:-}" ]]; then
    # Docker secret bind mounts cannot be remounted from an LXC-provided
    # tmpfs. Keep Compose inputs on the real filesystem.
    BACKEND_COMPOSE_IGNORES=()
    for compose_file in "${BACKEND_COMPOSE_TEST_FILES[@]}"; do
        BACKEND_COMPOSE_IGNORES+=("--ignore=${compose_file}")
    done
    if ! (
        cd "${VNEXT_ROOT}/backend"
        run_locked_pytest -q -m "serial and not parallel_safe" -n 0 "${BACKEND_COMPOSE_IGNORES[@]}" "$@"
    ); then
        test_exit=1
        backend_serial_status=1
    fi
    PYTEST_TMP_ARGS=()
    if ! (
        cd "${VNEXT_ROOT}/backend"
        run_locked_pytest -q -m "serial and not parallel_safe" -n 0 "${BACKEND_COMPOSE_TEST_FILES[@]}" "$@"
    ); then
        test_exit=1
        backend_serial_status=1
    fi
    PYTEST_TMP_ARGS+=(--basetemp "${GATEWAY_TEST_BASETEMP}")
else
    if ! (
        cd "${VNEXT_ROOT}/backend"
        run_locked_pytest -q -m "serial and not parallel_safe" -n 0 "$@"
    ); then
        test_exit=1
        backend_serial_status=1
    fi
fi
echo "==> backend (serial) elapsed_seconds=$((SECONDS - backend_serial_start)) status=${backend_serial_status}"

echo "==> repository_service (parallel)"
repository_service_parallel_start=${SECONDS}
repository_service_parallel_status=0
if ! (
    cd "${VNEXT_ROOT}/repository_service"
    run_locked_pytest -q -m "(not serial) or parallel_safe" -n "${TEST_WORKERS}" "$@"
); then
    test_exit=1
    repository_service_parallel_status=1
fi
echo "==> repository_service (parallel) elapsed_seconds=$((SECONDS - repository_service_parallel_start)) status=${repository_service_parallel_status}"

echo "==> repository_service (serial)"
repository_service_serial_start=${SECONDS}
repository_service_serial_status=0
if [[ -n "${GATEWAY_TEST_BASETEMP:-}" ]]; then
    # Docker secret bind mounts cannot be remounted from an LXC-provided
    # tmpfs in the authoritative Compose path. Keep those host paths on the
    # real filesystem while using tmpfs for all other test-owned workspaces.
    COMPOSE_IGNORES=()
    for compose_file in "${REPOSITORY_SERVICE_COMPOSE_TEST_FILES[@]}"; do
        COMPOSE_IGNORES+=("--ignore=${compose_file}")
    done
    if ! (
        cd "${VNEXT_ROOT}/repository_service"
        run_locked_pytest -q -m "serial and not parallel_safe" -n 0 "${COMPOSE_IGNORES[@]}" "$@"
    ); then
        test_exit=1
        repository_service_serial_status=1
    fi
    PYTEST_TMP_ARGS=()
    if ! (
        cd "${VNEXT_ROOT}/repository_service"
        run_locked_pytest -q -m "serial and not parallel_safe" -n 0 "${REPOSITORY_SERVICE_COMPOSE_TEST_FILES[@]}" "$@"
    ); then
        test_exit=1
        repository_service_serial_status=1
    fi
else
    if ! (
        cd "${VNEXT_ROOT}/repository_service"
        run_locked_pytest -q -m "serial and not parallel_safe" -n 0 "$@"
    ); then
        test_exit=1
        repository_service_serial_status=1
    fi
fi
echo "==> repository_service (serial) elapsed_seconds=$((SECONDS - repository_service_serial_start)) status=${repository_service_serial_status}"

if ! gateway_assert_lockfiles_unchanged "${VNEXT_ROOT}" "${LOCK_SNAPSHOT}"; then
    exit 1
fi

exit "${test_exit}"
