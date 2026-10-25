#!/usr/bin/env bash
set -euo pipefail

# Check that backend's installed Rust extension was built from the vnext/rust
# tree of the current commit. The authoritative runner builds the extension with
# GATEWAY_RUST_BUILD_INPUT set to that tree id; the extension exposes it as
# gateway_compute.gateway_compute.__build_input__.
#
# Exit codes: 0 match, 1 mismatch or unreadable extension, 2 usage/Git error.

VNEXT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
UV_CONSUME="${GATEWAY_UV_CONSUME:-${VNEXT_ROOT}/scripts/uv-consume.sh}"

if ! expected="$(git -C "${VNEXT_ROOT}" rev-parse --verify --quiet 'HEAD:vnext/rust')"; then
    echo "error: could not resolve the vnext/rust tree of HEAD" >&2
    exit 2
fi

if ! installed="$(
    cd "${VNEXT_ROOT}/backend"
    "${UV_CONSUME}" -C . run --no-sync python -I -c \
        'import gateway_compute.gateway_compute as native; print(getattr(native, "__build_input__", "<missing>"))'
)"; then
    echo "==> rust extension build input expected=${expected} installed=<unreadable> status=mismatch"
    echo "error: could not import the installed gateway_compute extension" >&2
    exit 1
fi
installed="${installed##*$'\n'}"

if [[ "${installed}" != "${expected}" ]]; then
    echo "==> rust extension build input expected=${expected} installed=${installed:-<empty>} status=mismatch"
    echo "error: installed gateway_compute extension was not built from the current vnext/rust tree" >&2
    exit 1
fi
echo "==> rust extension build input expected=${expected} installed=${installed} status=ok"
