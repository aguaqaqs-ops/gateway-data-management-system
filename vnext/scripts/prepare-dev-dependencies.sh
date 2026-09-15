#!/usr/bin/env bash
set -euo pipefail

# Prepare host-side Python virtual environments for all vNext packages.
# This script only syncs dependencies; it does not run tests.
#
# Environment:
#   GATEWAY_DEV_DEPENDENCY_MODE   internal | pypi (default: pypi)
#   GATEWAY_DEV_OFFLINE           1 to use uv sync --locked --offline
#   UV_INDEX_URL / UV_DEFAULT_INDEX   required when MODE=internal
#   UV_INSECURE_HOST              optional HTTP mirror trust
#   PIP_INDEX_URL / PIP_TRUSTED_HOST optional passthrough during sync

VNEXT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# shellcheck source=lib/gateway-index-env.sh
source "${VNEXT_ROOT}/scripts/lib/gateway-index-env.sh"
UV_CONSUME="${VNEXT_ROOT}/scripts/uv-consume.sh"

MODE="${GATEWAY_DEV_DEPENDENCY_MODE:-pypi}"
OFFLINE="${GATEWAY_DEV_OFFLINE:-0}"

if [[ "${MODE}" != "internal" && "${MODE}" != "pypi" ]]; then
    echo "error: GATEWAY_DEV_DEPENDENCY_MODE must be internal or pypi" >&2
    exit 2
fi

if [[ "${MODE}" == "internal" ]]; then
    if [[ -z "${UV_INDEX_URL:-}" && -z "${UV_DEFAULT_INDEX:-}" ]]; then
        echo "error: internal dependency mode requires UV_INDEX_URL or UV_DEFAULT_INDEX" >&2
        exit 2
    fi
fi

if [[ "${OFFLINE}" != "0" && "${OFFLINE}" != "1" ]]; then
    echo "error: GATEWAY_DEV_OFFLINE must be 0 or 1" >&2
    exit 2
fi

run_sync() {
    local -a consume_env=()
    local -a sync_args=()
    if [[ "${MODE}" == "internal" ]]; then
        consume_env+=(GATEWAY_UV_CONSUME_PRESERVE_INDEX=1)
    fi
    if [[ "${OFFLINE}" == "1" ]]; then
        sync_args+=(--offline)
    fi
    env "${consume_env[@]}" "${UV_CONSUME}" -C . sync "${sync_args[@]}"
}

while IFS= read -r package; do
    echo "==> prepare ${package} (mode=${MODE} offline=${OFFLINE})"
    (
        cd "${VNEXT_ROOT}/${package}"
        run_sync
    )
done < <(gateway_dev_packages)

echo "==> dependency prepare complete; lockfiles unchanged"
