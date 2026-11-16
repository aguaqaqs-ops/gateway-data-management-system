#!/usr/bin/env bash
set -euo pipefail

printf '==> umask=%s\n' "$(umask)"

# Authoritative test entrypoint for the vNext packages.
#
# Cheap and parallel batches run first: rust, the three smaller Python
# packages, backend parallel, and repository_service parallel. If any of those
# steps fails, both serial batches are skipped and skipped packages report
# not_run. Otherwise backend serial and repository_service serial run in order.

VNEXT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# shellcheck source=lib/gateway-index-env.sh
source "${VNEXT_ROOT}/scripts/lib/gateway-index-env.sh"
UV_CONSUME="${GATEWAY_UV_CONSUME:-${VNEXT_ROOT}/scripts/uv-consume.sh}"
TEST_WORKERS="${GATEWAY_TEST_WORKERS:-auto}"
TEST_SCOPE="${GATEWAY_TEST_SCOPE:-stage}"

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
    PACKAGE_STATUS["${package}"]=not_run
done

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
if [[ "${TEST_SCOPE}" != "stage" && "${TEST_SCOPE}" != "package" ]]; then
    echo "error: GATEWAY_TEST_SCOPE must be stage or package" >&2
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

RUNNER_PYTEST_ARGS=("$@")

run_locked_pytest() {
    local package="${PWD##*/}"
    local storage_path
    storage_path="$(runner_hypothesis_storage_path "${package}")"
    HYPOTHESIS_STORAGE_DIRECTORY="${storage_path}" \
        "${UV_CONSUME}" -C . run pytest -p no:cacheprovider --durations=0 --durations-min=1.0 "${PYTEST_TMP_ARGS[@]}" "$@"
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

run_parallel_batch() {
    local package="$1"
    local marker_expr="(not serial) or parallel_safe"
    if [[ "${TEST_SCOPE}" == "package" ]]; then
        marker_expr="((not serial) or parallel_safe) and not container"
    fi
    echo "==> ${package} (parallel)"
    local parallel_start=${SECONDS}
    local parallel_status=0
    if ! (
        cd "${VNEXT_ROOT}/${package}"
        run_locked_pytest -q -m "${marker_expr}" -n "${TEST_WORKERS}" "${RUNNER_PYTEST_ARGS[@]}"
    ); then
        test_exit=1
        parallel_status=1
        PACKAGE_STATUS["${package}"]=failed
    fi
    echo "==> ${package} (parallel) elapsed_seconds=$((SECONDS - parallel_start)) status=${parallel_status}"
}

run_serial_batches() {
    local package="$1"
    echo "==> ${package} (serial)"
    local serial_start=${SECONDS}
    local serial_status=0
    if [[ "${TEST_SCOPE}" == "package" ]]; then
        if ! (
            cd "${VNEXT_ROOT}/${package}"
            run_locked_pytest -q -m "(serial and not parallel_safe) and not container" -n 0 "${RUNNER_PYTEST_ARGS[@]}"
        ); then
            test_exit=1
            serial_status=1
        fi
    elif [[ -n "${GATEWAY_TEST_BASETEMP:-}" ]]; then
        # Docker secret bind mounts cannot be remounted from an LXC-provided
        # tmpfs in the authoritative Compose path. Keep container tests on the
        # real filesystem while using tmpfs for all other test-owned workspaces.
        if ! (
            cd "${VNEXT_ROOT}/${package}"
            run_locked_pytest -q -m "(serial and not parallel_safe) and not container" -n 0 "${RUNNER_PYTEST_ARGS[@]}"
        ); then
            test_exit=1
            serial_status=1
        fi
        PYTEST_TMP_ARGS=()
        if ! (
            cd "${VNEXT_ROOT}/${package}"
            run_locked_pytest -q -m "(serial and not parallel_safe) and container" -n 0 "${RUNNER_PYTEST_ARGS[@]}"
        ); then
            test_exit=1
            serial_status=1
        fi
        PYTEST_TMP_ARGS+=(--basetemp "${GATEWAY_TEST_BASETEMP}")
    else
        if ! (
            cd "${VNEXT_ROOT}/${package}"
            run_locked_pytest -q -m "serial and not parallel_safe" -n 0 "${RUNNER_PYTEST_ARGS[@]}"
        ); then
            test_exit=1
            serial_status=1
        fi
    fi
    if [[ "${serial_status}" -eq 0 ]]; then
        PACKAGE_STATUS["${package}"]=passed
    else
        PACKAGE_STATUS["${package}"]=failed
    fi
    echo "==> ${package} (serial) elapsed_seconds=$((SECONDS - serial_start)) status=${serial_status}"
}

test_exit=0
if [[ -n "${SELECTED_PACKAGE_SET[rust]:-}" ]]; then
    echo "==> rust"
    rust_start=${SECONDS}
    rust_status=0
    run_rust_step fmt fmt --all --check || rust_status=1
    run_rust_step clippy clippy --workspace --locked --offline --all-targets -- -D warnings || rust_status=1
    run_rust_step test test --workspace --locked --offline || rust_status=1
    if [[ "${rust_status}" -eq 0 ]]; then
        PACKAGE_STATUS[rust]=passed
    else
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
    if (cd "${VNEXT_ROOT}/${package}" && run_locked_pytest -q "${RUNNER_PYTEST_ARGS[@]}"); then
        PACKAGE_STATUS["${package}"]=passed
    else
        test_exit=1
        PACKAGE_STATUS["${package}"]=failed
    fi
done

if [[ -n "${SELECTED_PACKAGE_SET[backend]:-}" ]]; then
    run_parallel_batch backend
fi

if [[ -n "${SELECTED_PACKAGE_SET[repository_service]:-}" ]]; then
    run_parallel_batch repository_service
fi

skip_serial=0
if [[ "${test_exit}" -ne 0 ]] && [[ -n "${SELECTED_PACKAGE_SET[backend]:-}" || -n "${SELECTED_PACKAGE_SET[repository_service]:-}" ]]; then
    skip_serial=1
    echo "==> skipping serial batches because an earlier step failed"
fi

if [[ "${skip_serial}" -eq 0 && -n "${SELECTED_PACKAGE_SET[backend]:-}" ]]; then
    run_serial_batches backend
fi

if [[ "${skip_serial}" -eq 0 && -n "${SELECTED_PACKAGE_SET[repository_service]:-}" ]]; then
    run_serial_batches repository_service
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
