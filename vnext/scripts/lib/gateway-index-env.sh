#!/usr/bin/env bash
# Shared helpers for machine-wide PyPI index isolation during locked execution.
# Sourced by run-tests.sh and prepare-dev-dependencies.sh; do not execute directly.

if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
    echo "error: gateway-index-env.sh must be sourced, not executed" >&2
    exit 2
fi

GATEWAY_INDEX_ENV_NAMES=(
    UV_DEFAULT_INDEX
    UV_INDEX_URL
    UV_INSECURE_HOST
    PIP_INDEX_URL
    PIP_TRUSTED_HOST
)

gateway_index_env_names() {
    printf '%s\n' "${GATEWAY_INDEX_ENV_NAMES[@]}"
}

gateway_with_isolated_index() {
    local -a unset_args=()
    local name
    for name in "${GATEWAY_INDEX_ENV_NAMES[@]}"; do
        unset_args+=(-u "${name}")
    done
    env "${unset_args[@]}" "$@"
}

gateway_lockfile_paths() {
    local vnext_root="${1:?vnext root required}"
    printf '%s\n' \
        "${vnext_root}/shared_kernel/uv.lock" \
        "${vnext_root}/repository_contracts/uv.lock" \
        "${vnext_root}/repository_client/uv.lock" \
        "${vnext_root}/backend/uv.lock" \
        "${vnext_root}/repository_service/uv.lock"
}

gateway_snapshot_lockfile_sha256() {
    local vnext_root="${1:?vnext root required}"
    local path
    while IFS= read -r path; do
        if [[ ! -f "${path}" ]]; then
            echo "error: missing lockfile ${path}" >&2
            return 1
        fi
        sha256sum "${path}"
    done < <(gateway_lockfile_paths "${vnext_root}")
}

gateway_assert_lockfiles_unchanged() {
    local vnext_root="${1:?vnext root required}"
    local before_file="${2:?before snapshot file required}"
    local after_file
    after_file="$(mktemp)"
    if ! gateway_snapshot_lockfile_sha256 "${vnext_root}" >"${after_file}"; then
        rm -f "${after_file}"
        return 1
    fi
    if ! cmp -s "${before_file}" "${after_file}"; then
        echo "error: one or more uv.lock files changed during dependency provisioning" >&2
        rm -f "${after_file}"
        return 1
    fi
    rm -f "${after_file}"
}

gateway_dev_packages() {
    printf '%s\n' \
        shared_kernel \
        repository_contracts \
        repository_client \
        backend \
        repository_service
}
