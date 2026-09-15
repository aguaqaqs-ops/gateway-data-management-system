#!/usr/bin/env bash
# Shared helpers for machine-wide PyPI index isolation during locked execution.
# Sourced by uv-consume.sh, run-tests.sh, and prepare-dev-dependencies.sh; do not execute directly.

if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
    echo "error: gateway-index-env.sh must be sourced, not executed" >&2
    exit 2
fi

GATEWAY_INDEX_ENV_NAMES=(
    UV_INDEX
    UV_DEFAULT_INDEX
    UV_INDEX_URL
    UV_EXTRA_INDEX_URL
    UV_FIND_LINKS
    UV_CONFIG_FILE
    UV_INSECURE_HOST
    PIP_INDEX_URL
    PIP_EXTRA_INDEX_URL
    PIP_FIND_LINKS
    PIP_TRUSTED_HOST
)

GATEWAY_UV_MODE_OVERRIDE_ENV_NAMES=(
    UV_FROZEN
    UV_NO_SYNC
    UV_LOCKED
)

gateway_index_env_names() {
    printf '%s\n' "${GATEWAY_INDEX_ENV_NAMES[@]}"
}

gateway_uv_mode_override_env_names() {
    printf '%s\n' "${GATEWAY_UV_MODE_OVERRIDE_ENV_NAMES[@]}"
}

gateway_with_isolated_index() {
    local -a unset_args=()
    local name
    for name in "${GATEWAY_INDEX_ENV_NAMES[@]}"; do
        unset_args+=(-u "${name}")
    done
    env "${unset_args[@]}" "$@"
}

gateway_with_isolated_uv_mode_overrides() {
    local -a unset_args=()
    local name
    for name in "${GATEWAY_UV_MODE_OVERRIDE_ENV_NAMES[@]}" UV_CONFIG_FILE; do
        unset_args+=(-u "${name}")
    done
    env "${unset_args[@]}" "$@"
}

gateway_with_isolated_uv_config() {
    local -a unset_args=()
    local name
    for name in "${GATEWAY_INDEX_ENV_NAMES[@]}" "${GATEWAY_UV_MODE_OVERRIDE_ENV_NAMES[@]}"; do
        unset_args+=(-u "${name}")
    done
    env "${unset_args[@]}" "$@"
}

gateway_invoke_uv() {
    local preserve_index="${1:?preserve_index flag required}"
    shift
    if [[ "${preserve_index}" == "1" ]]; then
        gateway_with_isolated_uv_mode_overrides uv --no-config "$@"
    else
        gateway_with_isolated_uv_config uv --no-config "$@"
    fi
}

gateway_uv_rejected_option_name() {
    local arg="${1:?argument required}"
    case "${arg}" in
        --*=*|"-?"=*)
            printf '%s\n' "${arg%%=*}"
            ;;
        *)
            if [[ "${arg}" =~ ^-[A-Za-z]= ]]; then
                printf '%s\n' "${arg%%=*}"
            else
                printf '%s\n' "${arg}"
            fi
            ;;
    esac
}

gateway_reject_dangerous_uv_args() {
    local allow_no_sync="${1:-0}"
    local arg option_name
    for arg in "${@:2}"; do
        option_name="$(gateway_uv_rejected_option_name "${arg}")"
        case "${arg}" in
            --index | --index=* | --default-index | --default-index=*)
                echo "error: caller may not override package index (${option_name})" >&2
                return 2
                ;;
            --index-url | --index-url=* | -i | -i=*)
                echo "error: caller may not override package index (${option_name})" >&2
                return 2
                ;;
            --extra-index-url | --extra-index-url=*)
                echo "error: caller may not override package index (${option_name})" >&2
                return 2
                ;;
            --find-links | --find-links=* | -f | -f=*)
                echo "error: caller may not override find-links (${option_name})" >&2
                return 2
                ;;
            --config-file | --config-file=*)
                echo "error: caller may not override uv config (${option_name})" >&2
                return 2
                ;;
            --project | --project=* | --package | --package=*)
                echo "error: caller may not switch project context (${option_name})" >&2
                return 2
                ;;
            --directory | --directory=*)
                echo "error: caller may not switch project context (${option_name})" >&2
                return 2
                ;;
            --no-project | --all-packages)
                echo "error: caller may not switch project context (${option_name})" >&2
                return 2
                ;;
            --no-locked)
                echo "error: caller may not disable locked consumption (${option_name})" >&2
                return 2
                ;;
            --frozen)
                echo "error: caller may not use frozen mode (${option_name})" >&2
                return 2
                ;;
            --no-sync)
                if [[ "${allow_no_sync}" != "1" ]]; then
                    echo "error: caller may not use no-sync outside controlled wrapper path (${option_name})" >&2
                    return 2
                fi
                ;;
        esac
    done
}

gateway_validate_run_script_path() {
    local work_dir="${1:?work dir required}"
    local script_path="${2:?script path required}"
    local resolved work_real
    work_real="$(cd "${work_dir}" && pwd)"
    resolved="$(cd "${work_dir}" && realpath -e "${script_path}" 2>/dev/null || true)"
    if [[ -n "${resolved}" && "${resolved}" != "${work_real}/"* ]]; then
        echo "error: run may not execute scripts outside project directory (${script_path})" >&2
        return 2
    fi
}

gateway_reject_cross_project_run_script_targets() {
    local work_dir="${1:?work dir required}"
    shift
    local -a args=("$@")
    local argc=${#args[@]}
    local index=0
    local arg command

    while [[ ${index} -lt ${argc} ]]; do
        arg="${args[index]}"
        case "${arg}" in
            --)
                index=$((index + 1))
                break
                ;;
            --no-sync | --offline | --locked | --frozen | --no-project | --all-packages)
                index=$((index + 1))
                ;;
            --*=*)
                index=$((index + 1))
                ;;
            --*)
                if [[ $((index + 1)) -lt ${argc} && "${args[$((index + 1))]}" != -* ]]; then
                    index=$((index + 2))
                else
                    index=$((index + 1))
                fi
                ;;
            -*)
                index=$((index + 1))
                ;;
            *)
                break
                ;;
        esac
    done

    [[ ${index} -lt ${argc} ]] || return 0
    command="${args[index]}"

    case "${command}" in
        *.py)
            gateway_validate_run_script_path "${work_dir}" "${command}"
            ;;
        python | python3)
            index=$((index + 1))
            while [[ ${index} -lt ${argc} ]]; do
                arg="${args[index]}"
                case "${arg}" in
                    -c | -m)
                        return 0
                        ;;
                    -*)
                        index=$((index + 1))
                        ;;
                    *.py)
                        gateway_validate_run_script_path "${work_dir}" "${arg}"
                        return $?
                        ;;
                    *)
                        return 0
                        ;;
                esac
            done
            ;;
    esac
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
        echo "error: one or more uv.lock files changed during controlled consumption" >&2
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
