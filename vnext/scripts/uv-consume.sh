#!/usr/bin/env bash
set -euo pipefail

# Controlled uv consumption wrapper. Only sync/run/lock-check/pip-install are allowed.
# Does not update lockfiles; snapshots five lockfiles before and after execution.

VNEXT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# shellcheck source=lib/gateway-index-env.sh
source "${VNEXT_ROOT}/scripts/lib/gateway-index-env.sh"

UV_CONSUME_SCRIPT="${VNEXT_ROOT}/scripts/uv-consume.sh"
WORK_DIR="${PWD}"
PRESERVE_INDEX="${GATEWAY_UV_CONSUME_PRESERVE_INDEX:-0}"
SKIP_LOCK_ASSERT="${GATEWAY_UV_CONSUME_SKIP_LOCK_ASSERT:-0}"
LOCK_SNAPSHOT=""

usage() {
    cat >&2 <<'EOF'
usage: uv-consume.sh [-C <package-dir>] <sync|run|lock-check|pip-install> [uv args...]

Controlled uv consumption for vNext packages. Lockfiles must remain unchanged.

Environment:
  GATEWAY_UV_CONSUME_PRESERVE_INDEX   1 to keep caller index env (internal prepare only)
  GATEWAY_UV_CONSUME_SKIP_LOCK_ASSERT 1 to skip five-lock exit assert (testing only)
EOF
    exit 2
}

cleanup_lock_snapshot() {
    if [[ -n "${LOCK_SNAPSHOT}" ]]; then
        rm -f "${LOCK_SNAPSHOT}"
        LOCK_SNAPSHOT=""
    fi
}

snapshot_lockfiles() {
    LOCK_SNAPSHOT="$(mktemp)"
    gateway_snapshot_lockfile_sha256 "${VNEXT_ROOT}" >"${LOCK_SNAPSHOT}"
}

assert_lockfiles_unchanged_or_fail() {
    local command_ec="${1:?command exit code required}"
    if [[ "${SKIP_LOCK_ASSERT}" == "1" ]]; then
        return "${command_ec}"
    fi
    if ! gateway_assert_lockfiles_unchanged "${VNEXT_ROOT}" "${LOCK_SNAPSHOT}"; then
        cleanup_lock_snapshot
        if [[ "${command_ec}" -eq 0 ]]; then
            return 1
        fi
        return "${command_ec}"
    fi
    cleanup_lock_snapshot
    return "${command_ec}"
}

run_in_work_dir() {
    (
        cd "${WORK_DIR}"
        "$@"
    )
}

args_contain_no_sync() {
    local arg
    for arg in "$@"; do
        if [[ "${arg}" == "--no-sync" ]]; then
            return 0
        fi
    done
    return 1
}

run_lock_check() {
    run_in_work_dir gateway_invoke_uv "${PRESERVE_INDEX}" lock --check --offline --project "${WORK_DIR}"
}

run_sync() {
    local -a uv_args=("$@")
    if ! gateway_reject_dangerous_uv_args 0 "${uv_args[@]}"; then
        return 2
    fi
    snapshot_lockfiles
    local command_ec=0
    set +e
    run_in_work_dir gateway_invoke_uv "${PRESERVE_INDEX}" sync --locked "${uv_args[@]}"
    command_ec=$?
    set -e
    assert_lockfiles_unchanged_or_fail "${command_ec}"
}

run_run() {
    local -a uv_args=("$@")
    local allow_no_sync=0
    if args_contain_no_sync "${uv_args[@]}"; then
        allow_no_sync=1
    fi
    if ! gateway_reject_dangerous_uv_args "${allow_no_sync}" "${uv_args[@]}"; then
        return 2
    fi
    if ! gateway_reject_cross_project_run_script_targets "${WORK_DIR}" "${uv_args[@]}"; then
        return 2
    fi
    snapshot_lockfiles
    local command_ec=0
    if [[ "${allow_no_sync}" == "1" ]]; then
        set +e
        run_lock_check
        command_ec=$?
        set -e
        if [[ "${command_ec}" -ne 0 ]]; then
            assert_lockfiles_unchanged_or_fail "${command_ec}"
            return "${command_ec}"
        fi
        set +e
        run_in_work_dir gateway_invoke_uv "${PRESERVE_INDEX}" run --locked --project "${WORK_DIR}" "${uv_args[@]}"
        command_ec=$?
        set -e
    else
        set +e
        run_in_work_dir gateway_invoke_uv "${PRESERVE_INDEX}" run --locked --project "${WORK_DIR}" "${uv_args[@]}"
        command_ec=$?
        set -e
    fi
    assert_lockfiles_unchanged_or_fail "${command_ec}"
}

run_pip_install() {
    local -a uv_args=("$@")
    local arg option_name
    for arg in "${uv_args[@]}"; do
        option_name="$(gateway_uv_rejected_option_name "${arg}")"
        case "${arg}" in
            --index | --index=* | --index-url | --index-url=* | --extra-index-url | --extra-index-url=*)
                echo "error: pip-install may not override package index (${option_name})" >&2
                return 2
                ;;
            --config-file | --config-file=*)
                echo "error: pip-install may not override uv config (${option_name})" >&2
                return 2
                ;;
        esac
    done
    local has_offline=0
    for arg in "${uv_args[@]}"; do
        if [[ "${arg}" == "--offline" ]]; then
            has_offline=1
            break
        fi
    done
    if [[ "${has_offline}" != "1" ]]; then
        echo "error: pip-install requires --offline" >&2
        return 2
    fi
    snapshot_lockfiles
    local command_ec=0
    set +e
    run_in_work_dir gateway_invoke_uv "${PRESERVE_INDEX}" pip install "${uv_args[@]}"
    command_ec=$?
    set -e
    assert_lockfiles_unchanged_or_fail "${command_ec}"
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        -C)
            shift
            [[ $# -gt 0 ]] || usage
            WORK_DIR="$(cd "$1" && pwd)"
            shift
            ;;
        sync | run | lock-check | pip-install)
            break
            ;;
        -h | --help)
            usage
            ;;
        *)
            usage
            ;;
    esac
done

[[ $# -gt 0 ]] || usage
SUBCOMMAND="$1"
shift

case "${SUBCOMMAND}" in
    sync)
        run_sync "$@"
        ;;
    run)
        run_run "$@"
        ;;
    lock-check)
        snapshot_lockfiles
        set +e
        run_lock_check
        command_ec=$?
        set -e
        assert_lockfiles_unchanged_or_fail "${command_ec}"
        ;;
    pip-install)
        run_pip_install "$@"
        ;;
    *)
        usage
        ;;
esac
