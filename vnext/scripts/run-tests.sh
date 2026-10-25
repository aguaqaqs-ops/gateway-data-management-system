#!/usr/bin/env bash
set -euo pipefail

printf '==> umask=%s\n' "$(umask)"

# Authoritative test entrypoint for the vNext packages.
#
# The rust package (cargo fmt, clippy and test in vnext/rust) runs first.
# backend and repository_service run in two passes: the bulk of each suite in
# parallel, then timing sensitive serial tests on their own so they never
# compete for CPU. The three smaller Python packages run in one process.

VNEXT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# shellcheck source=lib/gateway-index-env.sh
source "${VNEXT_ROOT}/scripts/lib/gateway-index-env.sh"
UV_CONSUME="${GATEWAY_UV_CONSUME:-${VNEXT_ROOT}/scripts/uv-consume.sh}"
TEST_WORKERS="${GATEWAY_TEST_WORKERS:-auto}"

RUNNER_TMPDIR="${TMPDIR:-/tmp}"
if [[ "${RUNNER_TMPDIR}" != /* ]]; then
    echo "error: TMPDIR must be an absolute path for the authoritative runner" >&2
    exit 2
fi
if [[ ! -d "${RUNNER_TMPDIR}" ]]; then
    echo "error: TMPDIR must name an existing directory: ${RUNNER_TMPDIR}" >&2
    exit 2
fi
RUNNER_TMPDIR="$(cd "${RUNNER_TMPDIR}" && pwd -P)"
REPO_ROOT="$(cd "${VNEXT_ROOT}/.." && pwd -P)"
if [[ "${RUNNER_TMPDIR}" == "${REPO_ROOT}" || "${RUNNER_TMPDIR}" == "${REPO_ROOT}/"* ]]; then
    echo "error: TMPDIR must be outside the worktree: ${RUNNER_TMPDIR}" >&2
    exit 2
fi
RUNNER_HYPOTHESIS_ROOT="${RUNNER_TMPDIR%/}/gateway-runner-hypothesis"
echo "==> Hypothesis storage root=${RUNNER_HYPOTHESIS_ROOT} (effective TMPDIR=${RUNNER_TMPDIR})"
# Cargo build cache for the rust package and the backend extension build. It is
# not a test input; the runner removes it before use and on exit.
RUNNER_CARGO_TARGET_DIR="${RUNNER_TMPDIR%/}/gateway-runner-cargo-target"

PYTEST_TMP_ARGS=()

FAST_PACKAGES=(
    shared_kernel
    repository_contracts
    repository_client
)

PYTHON_PACKAGES=(
    "${FAST_PACKAGES[@]}"
    backend
    repository_service
)

ALL_PACKAGES=(
    rust
    "${PYTHON_PACKAGES[@]}"
)

# Until S2a deletes the old extension (DC52), its crates' tests embed a Python
# interpreter and read the backend environment, so cargo test skips them.
# clippy and fmt still cover the whole workspace.
RUST_TEST_EXCLUDES=(
    --exclude gateway-compute-python
    --exclude gateway-compute-python-impl
)

declare -A SELECTED_PACKAGE_SET=()
SELECTED_PACKAGES=()
if [[ "${GATEWAY_TEST_PACKAGES+x}" == "x" ]]; then
    requested_packages="${GATEWAY_TEST_PACKAGES}"
    if [[ ! "${requested_packages}" =~ ^[a-z_]+(,[a-z_]+)*$ ]]; then
        echo "error: GATEWAY_TEST_PACKAGES must be a comma-separated list of package names" >&2
        exit 2
    fi
    IFS=',' read -r -a requested_package_list <<<"${requested_packages}"
    for package in "${requested_package_list[@]}"; do
        case " ${ALL_PACKAGES[*]} " in
            *" ${package} "*) ;;
            *)
                echo "error: unknown package in GATEWAY_TEST_PACKAGES: ${package}" >&2
                exit 2
                ;;
        esac
        if [[ -n "${SELECTED_PACKAGE_SET[${package}]:-}" ]]; then
            echo "error: duplicate package in GATEWAY_TEST_PACKAGES: ${package}" >&2
            exit 2
        fi
        SELECTED_PACKAGE_SET["${package}"]=1
    done
    for package in "${ALL_PACKAGES[@]}"; do
        if [[ -n "${SELECTED_PACKAGE_SET[${package}]:-}" ]]; then
            SELECTED_PACKAGES+=("${package}")
        fi
    done
else
    SELECTED_PACKAGES=("${ALL_PACKAGES[@]}")
    for package in "${SELECTED_PACKAGES[@]}"; do
        SELECTED_PACKAGE_SET["${package}"]=1
    done
fi

SELECTED_PYTHON_PACKAGES=()
for package in "${SELECTED_PACKAGES[@]}"; do
    if [[ "${package}" != "rust" ]]; then
        SELECTED_PYTHON_PACKAGES+=("${package}")
    fi
done
USES_CARGO_TARGET=0
if [[ -n "${SELECTED_PACKAGE_SET[rust]:-}" || -n "${SELECTED_PACKAGE_SET[backend]:-}" ]]; then
    USES_CARGO_TARGET=1
fi

declare -A PACKAGE_STATUS=()
for package in "${SELECTED_PACKAGES[@]}"; do
    PACKAGE_STATUS["${package}"]=passed
done

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

runner_hypothesis_storage_path() {
    printf '%s/%s\n' "${RUNNER_HYPOTHESIS_ROOT}" "$1"
}

LOCK_SNAPSHOT=""
cleanup_runner_state() {
    local exit_status=$?
    local cleanup_failed=0
    trap - EXIT
    trap '' HUP INT TERM
    for package in "${SELECTED_PYTHON_PACKAGES[@]}"; do
        local storage_path
        storage_path="$(runner_hypothesis_storage_path "${package}")"
        if [[ -e "${storage_path}" || -L "${storage_path}" ]]; then
            echo "==> cleanup Hypothesis storage package=${package} path=${storage_path}"
            if ! rm -rf -- "${storage_path}"; then
                echo "error: could not remove Hypothesis storage: ${storage_path}" >&2
                cleanup_failed=1
            fi
        else
            printf '==> cleanup Hypothesis storage package=%s path=%s status=already_absent\n' \
                "${package}" "${storage_path}"
        fi
    done
    if [[ "${USES_CARGO_TARGET}" == "1" ]]; then
        if [[ -e "${RUNNER_CARGO_TARGET_DIR}" || -L "${RUNNER_CARGO_TARGET_DIR}" ]]; then
            echo "==> cleanup cargo target path=${RUNNER_CARGO_TARGET_DIR}"
            if ! rm -rf -- "${RUNNER_CARGO_TARGET_DIR}"; then
                echo "error: could not remove cargo target: ${RUNNER_CARGO_TARGET_DIR}" >&2
                cleanup_failed=1
            fi
        else
            echo "==> cleanup cargo target path=${RUNNER_CARGO_TARGET_DIR} status=already_absent"
        fi
    fi
    if [[ -n "${LOCK_SNAPSHOT}" ]] && ! rm -f "${LOCK_SNAPSHOT}"; then
        echo "error: could not remove lock snapshot: ${LOCK_SNAPSHOT}" >&2
        cleanup_failed=1
    fi
    if [[ "${exit_status}" -eq 0 && "${cleanup_failed}" -ne 0 ]]; then
        exit_status=1
    fi
    exit "${exit_status}"
}
trap cleanup_runner_state EXIT
trap 'exit 129' HUP
trap 'exit 130' INT
trap 'exit 143' TERM

for package in "${SELECTED_PYTHON_PACKAGES[@]}"; do
    storage_path="$(runner_hypothesis_storage_path "${package}")"
    if [[ -e "${storage_path}" || -L "${storage_path}" ]]; then
        echo "==> remove stale Hypothesis storage package=${package} path=${storage_path}"
        rm -rf -- "${storage_path}"
    else
        echo "==> Hypothesis storage package=${package} path=${storage_path} status=already_absent"
    fi
done
if [[ "${USES_CARGO_TARGET}" == "1" ]]; then
    if [[ -e "${RUNNER_CARGO_TARGET_DIR}" || -L "${RUNNER_CARGO_TARGET_DIR}" ]]; then
        echo "==> remove stale cargo target path=${RUNNER_CARGO_TARGET_DIR}"
        rm -rf -- "${RUNNER_CARGO_TARGET_DIR}"
    else
        echo "==> cargo target path=${RUNNER_CARGO_TARGET_DIR} status=already_absent"
    fi
fi

if [[ ! "${TEST_WORKERS}" =~ ^(auto|[0-9]+)$ ]]; then
    echo "error: GATEWAY_TEST_WORKERS must be auto or a non-negative integer" >&2
    exit 2
fi
if [[ -n "${GATEWAY_TEST_BASETEMP:-}" ]]; then
    if [[ "${GATEWAY_TEST_BASETEMP}" != /* ]]; then
        echo "error: GATEWAY_TEST_BASETEMP must be an absolute path" >&2
        exit 2
    fi
    mkdir -p "${GATEWAY_TEST_BASETEMP}"
    PYTEST_TMP_ARGS+=(--basetemp "${GATEWAY_TEST_BASETEMP}")
fi

LOCK_SNAPSHOT="$(mktemp)"
gateway_snapshot_lockfile_sha256 "${VNEXT_ROOT}" >"${LOCK_SNAPSHOT}"

export GATEWAY_UV_CONSUME_SKIP_LOCK_ASSERT=1

fail_all_selected_packages() {
    local failed_package
    for failed_package in "${SELECTED_PACKAGES[@]}"; do
        PACKAGE_STATUS["${failed_package}"]=failed
        echo "==> ${failed_package} status=${PACKAGE_STATUS[${failed_package}]}"
    done
}

# Materialize each selected locked environment before hashing it. uv run would
# perform this sync at the first pytest invocation; doing it here makes the
# manifest describe the environment the subsequent tests actually use.
#
# uv does not rebuild the backend's Rust extension (a path dependency) when only
# Rust sources change, so the backend sync always reinstalls it, embedding the
# vnext/rust tree id of HEAD, and the runner then checks the installed value.
if [[ -n "${SELECTED_PACKAGE_SET[backend]:-}" ]]; then
    if ! RUST_BUILD_INPUT="$(git -C "${REPO_ROOT}" rev-parse --verify --quiet 'HEAD:vnext/rust')"; then
        echo "error: could not resolve the vnext/rust tree of HEAD" >&2
        fail_all_selected_packages
        exit 1
    fi
fi
for package in "${SELECTED_PYTHON_PACKAGES[@]}"; do
    echo "==> sync test environment package=${package}"
    sync_args=()
    if [[ "${package}" == "backend" ]]; then
        sync_args=(--reinstall-package gateway-compute-python)
        echo "==> rust extension build input=${RUST_BUILD_INPUT} cargo_target=${RUNNER_CARGO_TARGET_DIR}"
    fi
    sync_status=0
    (
        cd "${VNEXT_ROOT}/${package}"
        if [[ "${package}" == "backend" ]]; then
            # Only the extension build sees these; manifests and pytest do not.
            export GATEWAY_RUST_BUILD_INPUT="${RUST_BUILD_INPUT}"
            export CARGO_TARGET_DIR="${RUNNER_CARGO_TARGET_DIR}"
        fi
        "${UV_CONSUME}" -C . sync "${sync_args[@]}"
    ) || sync_status=1
    if [[ "${sync_status}" -eq 0 && "${package}" == "backend" ]]; then
        "${VNEXT_ROOT}/scripts/check-rust-extension-build-input.sh" || sync_status=1
    fi
    if [[ "${sync_status}" -ne 0 ]]; then
        fail_all_selected_packages
        exit 1
    fi
done

INPUT_CLOSURE_SCRIPT="${VNEXT_ROOT}/scripts/test_input_closure.py"
for package in "${SELECTED_PACKAGES[@]}"; do
    if [[ "${package}" == "rust" ]]; then
        echo "==> test input manifest package=${package}"
        if ! python3 -I "${INPUT_CLOSURE_SCRIPT}" manifest --package "${package}"; then
            fail_all_selected_packages
            exit 1
        fi
        continue
    fi
    storage_path="$(runner_hypothesis_storage_path "${package}")"
    if [[ -e "${storage_path}" || -L "${storage_path}" ]]; then
        echo "error: Hypothesis storage must be absent before manifest: ${storage_path}" >&2
        exit 1
    fi
    echo "==> test input manifest package=${package} hypothesis_storage=${storage_path}"
    if ! HYPOTHESIS_STORAGE_DIRECTORY="${storage_path}" \
        python3 -I "${INPUT_CLOSURE_SCRIPT}" manifest --package "${package}"; then
        fail_all_selected_packages
        exit 1
    fi
done

run_locked_pytest() {
    local package="${PWD##*/}"
    local storage_path
    storage_path="$(runner_hypothesis_storage_path "${package}")"
    HYPOTHESIS_STORAGE_DIRECTORY="${storage_path}" \
        "${UV_CONSUME}" -C . run pytest -p no:cacheprovider "${PYTEST_TMP_ARGS[@]}" "$@"
}

run_rust_step() {
    local step="$1"
    shift
    local step_start=${SECONDS}
    local step_status=0
    echo "==> rust (${step})"
    if ! (
        cd "${VNEXT_ROOT}/rust"
        CARGO_TARGET_DIR="${RUNNER_CARGO_TARGET_DIR}" cargo "$@"
    ); then
        step_status=1
    fi
    echo "==> rust (${step}) elapsed_seconds=$((SECONDS - step_start)) status=${step_status}"
    return "${step_status}"
}

test_exit=0
if [[ -n "${SELECTED_PACKAGE_SET[rust]:-}" ]]; then
    echo "==> rust"
    rust_start=${SECONDS}
    rust_status=0
    run_rust_step fmt fmt --all --check || rust_status=1
    run_rust_step clippy clippy --workspace --locked --offline --all-targets -- -D warnings || rust_status=1
    run_rust_step test test --workspace --locked --offline "${RUST_TEST_EXCLUDES[@]}" || rust_status=1
    if [[ "${rust_status}" -ne 0 ]]; then
        test_exit=1
        PACKAGE_STATUS[rust]=failed
    fi
    echo "==> rust elapsed_seconds=$((SECONDS - rust_start)) status=${rust_status}"
fi

for package in "${FAST_PACKAGES[@]}"; do
    if [[ -z "${SELECTED_PACKAGE_SET[${package}]:-}" ]]; then
        continue
    fi
    echo "==> ${package}"
    if ! (cd "${VNEXT_ROOT}/${package}" && run_locked_pytest -q "$@"); then
        test_exit=1
        PACKAGE_STATUS["${package}"]=failed
    fi
done

if [[ -n "${SELECTED_PACKAGE_SET[backend]:-}" ]]; then
echo "==> backend (parallel)"
backend_parallel_start=${SECONDS}
backend_parallel_status=0
if ! (
    cd "${VNEXT_ROOT}/backend"
    run_locked_pytest -q -m "(not serial) or parallel_safe" -n "${TEST_WORKERS}" "$@"
); then
    test_exit=1
    backend_parallel_status=1
    PACKAGE_STATUS[backend]=failed
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
        PACKAGE_STATUS[backend]=failed
    fi
    PYTEST_TMP_ARGS=()
    if ! (
        cd "${VNEXT_ROOT}/backend"
        run_locked_pytest -q -m "serial and not parallel_safe" -n 0 "${BACKEND_COMPOSE_TEST_FILES[@]}" "$@"
    ); then
        test_exit=1
        backend_serial_status=1
        PACKAGE_STATUS[backend]=failed
    fi
    PYTEST_TMP_ARGS+=(--basetemp "${GATEWAY_TEST_BASETEMP}")
else
    if ! (
        cd "${VNEXT_ROOT}/backend"
        run_locked_pytest -q -m "serial and not parallel_safe" -n 0 "$@"
    ); then
        test_exit=1
        backend_serial_status=1
        PACKAGE_STATUS[backend]=failed
    fi
fi
echo "==> backend (serial) elapsed_seconds=$((SECONDS - backend_serial_start)) status=${backend_serial_status}"
fi

if [[ -n "${SELECTED_PACKAGE_SET[repository_service]:-}" ]]; then
echo "==> repository_service (parallel)"
repository_service_parallel_start=${SECONDS}
repository_service_parallel_status=0
if ! (
    cd "${VNEXT_ROOT}/repository_service"
    run_locked_pytest -q -m "(not serial) or parallel_safe" -n "${TEST_WORKERS}" "$@"
); then
    test_exit=1
    repository_service_parallel_status=1
    PACKAGE_STATUS[repository_service]=failed
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
        PACKAGE_STATUS[repository_service]=failed
    fi
    PYTEST_TMP_ARGS=()
    if ! (
        cd "${VNEXT_ROOT}/repository_service"
        run_locked_pytest -q -m "serial and not parallel_safe" -n 0 "${REPOSITORY_SERVICE_COMPOSE_TEST_FILES[@]}" "$@"
    ); then
        test_exit=1
        repository_service_serial_status=1
        PACKAGE_STATUS[repository_service]=failed
    fi
else
    if ! (
        cd "${VNEXT_ROOT}/repository_service"
        run_locked_pytest -q -m "serial and not parallel_safe" -n 0 "$@"
    ); then
        test_exit=1
        repository_service_serial_status=1
        PACKAGE_STATUS[repository_service]=failed
    fi
fi
echo "==> repository_service (serial) elapsed_seconds=$((SECONDS - repository_service_serial_start)) status=${repository_service_serial_status}"
fi

if ! gateway_assert_lockfiles_unchanged "${VNEXT_ROOT}" "${LOCK_SNAPSHOT}"; then
    test_exit=1
    for package in "${SELECTED_PACKAGES[@]}"; do
        PACKAGE_STATUS["${package}"]=failed
    done
fi

for package in "${SELECTED_PACKAGES[@]}"; do
    echo "==> ${package} status=${PACKAGE_STATUS[${package}]}"
done

exit "${test_exit}"
