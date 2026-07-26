#!/usr/bin/env bash
set -euo pipefail

VNEXT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
REPO_ROOT="$(git -C "${VNEXT_ROOT}" rev-parse --show-toplevel)"
BACKEND_ROOT="${VNEXT_ROOT}/backend"
RUST_ROOT="${VNEXT_ROOT}/rust"
COMPUTE_PYTHON_ROOT="${RUST_ROOT}/gateway-compute-python"
DEPLOY_ROOT="${VNEXT_ROOT}/deploy"
PINS_FILE="${DEPLOY_ROOT}/phase-1-image-pins.env"
DOCKERFILE="${BACKEND_ROOT}/Dockerfile"
COMPOSE_FILE="${DEPLOY_ROOT}/compose.yaml"
COMPOSE_PHASE_EXIT_FILE="${DEPLOY_ROOT}/compose.phase-exit.yaml"
PHASE_EXIT_WHEEL_STAGING_DIR="${BACKEND_ROOT}/.phase-exit-build"
PHASE_EXIT_UV_WHEEL_STAGING_PATH=""
PHASE_EXIT_UV_WHEEL_BASENAME=""
PHASE_EXIT_COMPUTE_WHEEL_STAGING_PATH=""
PHASE_EXIT_COMPUTE_WHEEL_BASENAME=""
PHASE_EXIT_DEPS_WHEEL_DIR="${PHASE_EXIT_WHEEL_STAGING_DIR}/container-deps-wheels"
IDENTITY_BUNDLE="${VNEXT_ROOT}/scripts/phase_exit_identity_bundle.py"
DEPS_WHEELS_SELECTOR="${VNEXT_ROOT}/scripts/phase_exit_container_deps_wheels.py"
R4_BASE="${R4_BASE:-b747590ac6ffdfe0e00b320363ce429e663e358e}"
PHASE_EXIT_NETWORK_DEADLINE_SEC="${PHASE_EXIT_NETWORK_DEADLINE_SEC:-120}"
PHASE_EXIT_IDENTITY_ARTIFACT_DIR="${REPO_ROOT}/docs/backend-vnext/refactoring/temporary/phase-1/artifacts"

LOCK_PATHS=(
  "${RUST_ROOT}/Cargo.lock"
  "${BACKEND_ROOT}/uv.lock"
  "${BACKEND_ROOT}/uv.container.lock"
  "${VNEXT_ROOT}/shared_kernel/uv.lock"
  "${VNEXT_ROOT}/conformance/uv.lock"
  "${VNEXT_ROOT}/repository_service/uv.lock"
)

usage() {
  echo "usage: $0 gate|check-static|trap-regression|success-path-regression|verify-registry-blocked|bootstrap-pip-regression|deps-classify-regression" >&2
  exit 2
}

phase_exit_blocked() {
  echo "BLOCKED: $*" >&2
  exit 3
}

phase_exit_is_transport_log() {
  local log_file="$1"
  [[ -f "${log_file}" ]] || return 1
  # Allowlist only confirmed transport phrases. Avoid bare "SSL:" (false positives
  # like local "ssl:extra" tokens). Prefer specific SSLError / certificate text.
  grep -Eqi \
    'Name or service not known|Temporary failure in name resolution|nodename nor servname|getaddrinfo failed|Connection refused|Connection timed out|Network is unreachable|Connection reset|Failed to establish a new connection|NewConnectionError|ConnectTimeoutError|Max retries exceeded|SSLError|CERTIFICATE_VERIFY_FAILED|SSL certificate problem|SSL connect error|ProxyError|ReadTimeoutError|Read timed out|The read operation timed out|handshake timed out' \
    "${log_file}"
}

phase_exit_curl_is_transport_ec() {
  local ec="$1"
  case "${ec}" in
    5|6|7|16|18|28|35|51|52|55|56|60|92|95|96|97) return 0 ;;
    *) return 1 ;;
  esac
}

phase_exit_http_status_is_registry_blocked() {
  local code="$1"
  [[ "${code}" =~ ^[0-9]+$ ]] || return 1
  case "${code}" in
    408|429) return 0 ;;
  esac
  if [[ "${code}" -ge 500 && "${code}" -lt 600 ]]; then
    return 0
  fi
  return 1
}

phase_exit_http_status_is_2xx() {
  local code="$1"
  [[ "${code}" =~ ^[0-9]+$ ]] || return 1
  [[ "${code}" -ge 200 && "${code}" -lt 300 ]]
}

phase_exit_report_http_status_failure() {
  local label="$1"
  local url="$2"
  local code="$3"
  if phase_exit_http_status_is_registry_blocked "${code}"; then
    phase_exit_blocked "${label} failed: ${url} HTTP ${code}"
  fi
  echo "${label} failed (local): ${url} HTTP ${code}" >&2
  exit 1
}

phase_exit_is_docker_pull_local_log() {
  local log_file="$1"
  [[ -f "${log_file}" ]] || return 1
  grep -Eqi \
    'invalid reference format|invalid reference|repository name must be lowercase|invalid tag' \
    "${log_file}"
}

phase_exit_curl_fetch_to_file() {
  local out_path="$1"
  local url="$2"
  local http_code="000"
  local curl_ec=0
  http_code="$(
    curl -sS -L --max-time "${PHASE_EXIT_NETWORK_DEADLINE_SEC}" \
      -o "${out_path}" -w '%{http_code}' "${url}" 2>/dev/null
  )" || curl_ec=$?
  printf '%s\t%s\n' "${curl_ec}" "${http_code:-000}"
}

phase_exit_read_curl_fetch_result() {
  local fetch_line="$1"
  CURL_FETCH_EC=""
  CURL_FETCH_HTTP_CODE=""
  IFS=$'\t' read -r CURL_FETCH_EC CURL_FETCH_HTTP_CODE <<<"${fetch_line}"
}

phase_exit_report_curl_fetch_failure() {
  local label="$1"
  local url="$2"
  local curl_ec="$3"
  local http_code="$4"
  if [[ "${curl_ec}" -eq 28 ]]; then
    phase_exit_blocked "${label} download timed out: ${url}"
  fi
  if phase_exit_curl_is_transport_ec "${curl_ec}"; then
    phase_exit_blocked "${label} download blocked: ${url} (curl exit ${curl_ec})"
  fi
  if phase_exit_http_status_is_registry_blocked "${http_code}"; then
    phase_exit_blocked "${label} download blocked: ${url} HTTP ${http_code}"
  fi
  if [[ "${curl_ec}" -ne 0 ]] || ! phase_exit_http_status_is_2xx "${http_code}"; then
    echo "${label} download failed (local): ${url} (curl exit ${curl_ec}, HTTP ${http_code})" >&2
    exit 1
  fi
}

phase_exit_assert_curl_fetch_ok() {
  phase_exit_report_curl_fetch_failure "$@"
}

phase_exit_report_docker_pull_failure() {
  local image="$1"
  local pull_ec="$2"
  local pull_log="$3"
  if [[ "${pull_ec}" -eq 124 ]]; then
    phase_exit_blocked "registry pull timed out: ${image}"
  fi
  if [[ "${pull_ec}" -ne 0 ]]; then
    if phase_exit_is_docker_pull_local_log "${pull_log}"; then
      echo "registry pull failed (local): ${image}" >&2
      exit 1
    fi
    phase_exit_blocked "registry pull failed: ${image}"
  fi
}

phase_exit_container_python_tag() {
  local version_file="$1"
  local py_ver
  py_ver="$(tr -d '[:space:]' <"${version_file}")"
  local major minor
  IFS=. read -r major minor _rest <<<"${py_ver}"
  printf 'cp%s%s\n' "${major}" "${minor}"
}

assert_deps_download_not_injected_on_formal_gate() {
  if [[ "${PHASE_EXIT_CONTAINER_INJECT_DEPS_TIMEOUT:-}" == "1" ]]; then
    phase_exit_blocked "container deps wheel download timed out (injected)"
  fi
}

sha256_file() {
  sha256sum "$1" | awk '{print $1}'
}

capture_lock_shas() {
  local out="$1"
  : >"${out}"
  local path
  for path in "${LOCK_PATHS[@]}"; do
    printf '%s %s\n' "$(sha256_file "${path}")" "${path}" >>"${out}"
  done
}

assert_lock_shas_unchanged() {
  local before="$1"
  local after="$2"
  if ! diff -u "${before}" "${after}" >/dev/null; then
    echo "lockfile identity changed during phase-exit-container gate" >&2
    diff -u "${before}" "${after}" >&2 || true
    exit 1
  fi
}

assert_linux_x86_64_glibc() {
  if [[ "${PHASE_EXIT_CONTAINER_SKIP_PLATFORM_CHECK:-}" == "1" ]]; then
    return 0
  fi
  if [[ "$(uname -s)" != "Linux" ]]; then
    echo "phase-exit-container requires Linux" >&2
    exit 1
  fi
  if [[ "$(uname -m)" != "x86_64" ]]; then
    echo "phase-exit-container requires linux/x86_64" >&2
    exit 1
  fi
  if [[ ! -e /lib/x86_64-linux-gnu/libc.so.6 ]] && [[ ! -e /usr/lib/libc.so.6 ]]; then
    echo "phase-exit-container requires glibc" >&2
    exit 1
  fi
}

assert_clean_worktree() {
  if [[ "${PHASE_EXIT_CONTAINER_ALLOW_DIRTY:-}" == "1" ]]; then
    return 0
  fi
  # Compare against HEAD so staged-only and unstaged tracked changes both fail closed.
  if ! git -C "${REPO_ROOT}" diff --quiet HEAD -- .; then
    echo "dirty worktree: tracked changes present (staged or unstaged vs HEAD)" >&2
    git -C "${REPO_ROOT}" status -sb >&2 || true
    exit 1
  fi
  local untracked
  untracked="$(git -C "${REPO_ROOT}" ls-files -o --exclude-standard | LC_ALL=C sort || true)"
  if [[ -n "${untracked}" ]]; then
    echo "dirty worktree: untracked files present" >&2
    printf '%s\n' "${untracked}" >&2
    exit 1
  fi
}

assert_head_identity() {
  local head
  head="$(git -C "${REPO_ROOT}" rev-parse HEAD)"
  if ! git -C "${REPO_ROOT}" merge-base --is-ancestor "${R4_BASE}" "${head}"; then
    echo "HEAD is not a descendant of WP5 R4 base ${R4_BASE}" >&2
    exit 1
  fi
  if [[ -z "${EXPECTED_HEAD:-}" ]]; then
    if [[ "${PHASE_EXIT_CONTAINER_REGRESSION_MODE:-}" == "1" ]]; then
      printf '%s\n' "${head}"
      return 0
    fi
    echo "EXPECTED_HEAD is required for formal phase-exit-container gate" >&2
    exit 1
  fi
  if [[ "${head}" != "${EXPECTED_HEAD}" ]]; then
    echo "HEAD mismatch: expected ${EXPECTED_HEAD}, got ${head}" >&2
    exit 1
  fi
  printf '%s\n' "${head}"
}

load_pins() {
  if [[ ! -f "${PINS_FILE}" ]]; then
    echo "missing pins file: ${PINS_FILE}" >&2
    exit 1
  fi
  # shellcheck disable=SC1090
  source "${PINS_FILE}"
  : "${PYTHON_RUNTIME_IMAGE:?}"
  : "${UV_VERSION:?}"
  : "${PYTHON_VERSION:?}"
  : "${RUST_TOOLCHAIN:?}"
  : "${UV_PIP_WHEEL_URL:?}"
  : "${UV_PIP_WHEEL_SHA256:?}"
  : "${PIP_VERSION:?}"
  : "${PIP_WHEEL_URL:?}"
  : "${PIP_WHEEL_SHA256:?}"
  phase_exit_configure_wheel_paths
}

phase_exit_configure_wheel_paths() {
  PHASE_EXIT_UV_WHEEL_BASENAME="${UV_PIP_WHEEL_URL##*/}"
  PHASE_EXIT_UV_WHEEL_STAGING_PATH="${PHASE_EXIT_WHEEL_STAGING_DIR}/${PHASE_EXIT_UV_WHEEL_BASENAME}"
  PHASE_EXIT_PIP_WHEEL_BASENAME="${PIP_WHEEL_URL##*/}"
  PHASE_EXIT_PIP_WHEEL_STAGING_PATH="${PHASE_EXIT_WHEEL_STAGING_DIR}/${PHASE_EXIT_PIP_WHEEL_BASENAME}"
}

assert_network_deadline_config() {
  if [[ ! "${PHASE_EXIT_NETWORK_DEADLINE_SEC}" =~ ^[0-9]+$ ]]; then
    echo "PHASE_EXIT_NETWORK_DEADLINE_SEC must be a positive integer" >&2
    exit 1
  fi
  if (( PHASE_EXIT_NETWORK_DEADLINE_SEC < 1 || PHASE_EXIT_NETWORK_DEADLINE_SEC > 3600 )); then
    echo "PHASE_EXIT_NETWORK_DEADLINE_SEC must be in [1, 3600], got ${PHASE_EXIT_NETWORK_DEADLINE_SEC}" >&2
    exit 1
  fi
}

assert_host_toolchain_matches_pins() {
  local uv_out rustc_out py_out pip_out uv_venv
  uv_venv="${PHASE_EXIT_WHEEL_STAGING_DIR}/uv-cli-venv"
  uv_out="$("${uv_venv}/bin/uv" --version 2>/dev/null || true)"
  if [[ "${uv_out}" != *" ${UV_VERSION}"* && "${uv_out}" != *"uv ${UV_VERSION}"* ]]; then
    echo "pinned uv-cli venv version mismatch: expected ${UV_VERSION}, got ${uv_out}" >&2
    exit 1
  fi
  pip_out="$("${uv_venv}/bin/python" -m pip --version 2>/dev/null || true)"
  if [[ "${pip_out}" != pip\ "${PIP_VERSION}"* ]]; then
    echo "pinned pip version mismatch: expected pip ${PIP_VERSION}, got ${pip_out}" >&2
    exit 1
  fi
  rustc_out="$(rustc --version 2>/dev/null || true)"
  if [[ "${rustc_out}" != *"rustc ${RUST_TOOLCHAIN}"* ]]; then
    echo "host rustc version mismatch: expected ${RUST_TOOLCHAIN}, got ${rustc_out}" >&2
    exit 1
  fi
  cd "${BACKEND_ROOT}"
  py_out="$(uv run --offline --no-sync python --version 2>/dev/null || true)"
  if [[ "${py_out}" != *"${PYTHON_VERSION}"* ]]; then
    echo "host python version mismatch: expected ${PYTHON_VERSION}, got ${py_out}" >&2
    exit 1
  fi
}

assert_uv_pip_wheel_pins() {
  case "${UV_PIP_WHEEL_URL}" in
    https://files.pythonhosted.org/*) ;;
    *)
      echo "UV_PIP_WHEEL_URL must be a files.pythonhosted.org URL" >&2
      exit 1
      ;;
  esac
  if [[ "${#UV_PIP_WHEEL_SHA256}" -ne 64 ]]; then
    echo "UV_PIP_WHEEL_SHA256 must be a 64-char sha256 hex digest" >&2
    exit 1
  fi
}

assert_pip_wheel_pins() {
  case "${PIP_WHEEL_URL}" in
    https://files.pythonhosted.org/*) ;;
    *)
      echo "PIP_WHEEL_URL must be a files.pythonhosted.org URL" >&2
      exit 1
      ;;
  esac
  if [[ "${#PIP_WHEEL_SHA256}" -ne 64 ]]; then
    echo "PIP_WHEEL_SHA256 must be a 64-char sha256 hex digest" >&2
    exit 1
  fi
}

assert_forbid_allow_dirty_on_formal_gate() {
  if [[ "${PHASE_EXIT_CONTAINER_ALLOW_DIRTY:-}" == "1" \
    && "${PHASE_EXIT_CONTAINER_REGRESSION_MODE:-}" != "1" ]]; then
    echo "PHASE_EXIT_CONTAINER_ALLOW_DIRTY is not permitted on formal phase-exit-container gate" >&2
    exit 1
  fi
}

assert_forbid_attestation_bypass_on_formal_gate() {
  # Formal `gate` mode must never honor regression/inject shortcuts.
  if [[ "${PHASE_EXIT_CONTAINER_REGRESSION_MODE:-}" == "1" ]]; then
    echo "PHASE_EXIT_CONTAINER_REGRESSION_MODE is not permitted on formal phase-exit-container gate" >&2
    exit 1
  fi
  if [[ "${PHASE_EXIT_CONTAINER_INJECT_BODY_SUCCESS:-}" == "1" ]]; then
    echo "PHASE_EXIT_CONTAINER_INJECT_BODY_SUCCESS is not permitted on formal phase-exit-container gate" >&2
    exit 1
  fi
  if [[ "${PHASE_EXIT_CONTAINER_SKIP_PLATFORM_CHECK:-}" == "1" ]]; then
    echo "PHASE_EXIT_CONTAINER_SKIP_PLATFORM_CHECK is not permitted on formal phase-exit-container gate" >&2
    exit 1
  fi
  if [[ "${PHASE_EXIT_CONTAINER_FORCE_CLEANUP_FAIL:-}" == "1" ]]; then
    echo "PHASE_EXIT_CONTAINER_FORCE_CLEANUP_FAIL is not permitted on formal phase-exit-container gate" >&2
    exit 1
  fi
  if [[ "${PHASE_EXIT_CONTAINER_INJECT_RMI_FAIL:-}" == "1" ]]; then
    echo "PHASE_EXIT_CONTAINER_INJECT_RMI_FAIL is not permitted on formal phase-exit-container gate" >&2
    exit 1
  fi
  if [[ "${PHASE_EXIT_CONTAINER_INJECT_TMP_RM_FAIL:-}" == "1" ]]; then
    echo "PHASE_EXIT_CONTAINER_INJECT_TMP_RM_FAIL is not permitted on formal phase-exit-container gate" >&2
    exit 1
  fi
  if [[ "${PHASE_EXIT_CONTAINER_INJECT_DEPS_TIMEOUT:-}" == "1" ]]; then
    echo "PHASE_EXIT_CONTAINER_INJECT_DEPS_TIMEOUT is not permitted on formal phase-exit-container gate" >&2
    exit 1
  fi
  if [[ "${PHASE_EXIT_CONTAINER_INJECT_BUILD_TIMEOUT:-}" == "1" ]]; then
    echo "PHASE_EXIT_CONTAINER_INJECT_BUILD_TIMEOUT is not permitted on formal phase-exit-container gate" >&2
    exit 1
  fi
  if [[ "${PHASE_EXIT_CONTAINER_INJECT_PULL_TIMEOUT:-}" == "1" ]]; then
    echo "PHASE_EXIT_CONTAINER_INJECT_PULL_TIMEOUT is not permitted on formal phase-exit-container gate" >&2
    exit 1
  fi
  if [[ "${PHASE_EXIT_CONTAINER_INJECT_REGISTRY_BLOCKED:-}" == "1" ]]; then
    echo "PHASE_EXIT_CONTAINER_INJECT_REGISTRY_BLOCKED is not permitted on formal phase-exit-container gate" >&2
    exit 1
  fi
}

assert_dockerfile_uses_digest_pins() {
  local line
  while IFS= read -r line; do
    case "${line}" in
      FROM\ *)
        if [[ "${line}" != *"@sha256:"* ]]; then
          if [[ "${line}" == *'${'* ]]; then
            continue
          fi
          echo "Dockerfile FROM must use digest-pinned base image: ${line}" >&2
          exit 1
        fi
        ;;
    esac
  done <"${DOCKERFILE}"
  if ! grep -q 'FROM ${PYTHON_RUNTIME_IMAGE}' "${DOCKERFILE}"; then
    echo "Dockerfile must parameterize python runtime image" >&2
    exit 1
  fi
  if grep -q 'rust-builder' "${DOCKERFILE}" || grep -q 'maturin build' "${DOCKERFILE}"; then
    echo "Dockerfile must not build wheels inside the image (host wheel is authoritative)" >&2
    exit 1
  fi
  if grep -qE 'gateway-compute-python\.whl|uv-0\.11\.28-linux_x86_64\.whl' "${DOCKERFILE}"; then
    echo "Dockerfile must not use invalid short wheel filenames" >&2
    exit 1
  fi
  if ! grep -q 'GATEWAY_COMPUTE_WHEEL_BASENAME' "${DOCKERFILE}"; then
    echo "Dockerfile must parameterize the host-staged release wheel basename" >&2
    exit 1
  fi
  if ! grep -q 'UV_WHEEL_BASENAME' "${DOCKERFILE}"; then
    echo "Dockerfile must parameterize the host-staged uv wheel basename" >&2
    exit 1
  fi
  if grep -qE 'curl.*install\.sh|astral\.sh/uv/.*/install\.sh' "${DOCKERFILE}"; then
    echo "Dockerfile must not use unverified curl-to-shell installers" >&2
    exit 1
  fi
  if grep -q 'COPY rust' "${DOCKERFILE}"; then
    echo "Dockerfile must not COPY rust source tree" >&2
    exit 1
  fi
  if grep -qE 'pip install.*"uv==' "${DOCKERFILE}"; then
    echo "Dockerfile must not pip install uv from floating PyPI" >&2
    exit 1
  fi
  if ! grep -q 'container-deps-wheels' "${DOCKERFILE}"; then
    echo "Dockerfile must COPY the host-staged container dependency wheelhouse" >&2
    exit 1
  fi
  if ! grep -q 'uv export --frozen --offline' "${DOCKERFILE}"; then
    echo "Dockerfile must export the frozen lockfile offline" >&2
    exit 1
  fi
  if ! grep -q 'uv pip install.*--offline.*--no-index' "${DOCKERFILE}"; then
    echo "Dockerfile must install container dependencies offline without an index" >&2
    exit 1
  fi
}

assert_pins_have_digests() {
  if [[ "${PYTHON_RUNTIME_IMAGE}" != *"@sha256:"* ]]; then
    echo "PYTHON_RUNTIME_IMAGE must include digest" >&2
    exit 1
  fi
  assert_uv_pip_wheel_pins
  assert_pip_wheel_pins
}

assert_docker_daemon() {
  if [[ "${PHASE_EXIT_CONTAINER_INJECT_DOCKER_DAEMON_FAIL:-}" == "1" ]]; then
    echo "docker daemon unavailable (injected)" >&2
    exit 1
  fi
  if ! docker info >/dev/null 2>&1; then
    echo "docker daemon unavailable" >&2
    exit 1
  fi
  if ! docker compose version >/dev/null 2>&1; then
    echo "docker compose unavailable" >&2
    exit 1
  fi
}

docker_pull_with_blocked() {
  local image="$1"
  if [[ "${PHASE_EXIT_CONTAINER_INJECT_REGISTRY_BLOCKED:-}" == "1" ]]; then
    phase_exit_blocked "registry pull blocked (injected): ${image}"
  fi
  if [[ "${PHASE_EXIT_CONTAINER_INJECT_PULL_TIMEOUT:-}" == "1" ]]; then
    phase_exit_blocked "registry pull timed out (injected): ${image}"
  fi
  local pull_ec=0
  local pull_log="${PHASE_EXIT_TMP:-/tmp}/docker-pull-${PHASE_EXIT_RUN_ID:-$$}.log"
  timeout "${PHASE_EXIT_NETWORK_DEADLINE_SEC}" docker pull "${image}" >"${pull_log}" 2>&1 || pull_ec=$?
  cat "${pull_log}" >&2
  phase_exit_report_docker_pull_failure "${image}" "${pull_ec}" "${pull_log}"
}

docker_build_offline() {
  # Offline build layer: all failures (including timeout) are implement/local exit 1.
  if [[ "${PHASE_EXIT_CONTAINER_INJECT_BUILD_TIMEOUT:-}" == "1" ]]; then
    echo "docker build timed out (injected)" >&2
    exit 1
  fi
  local build_ec=0
  timeout "${PHASE_EXIT_NETWORK_DEADLINE_SEC}" docker build "$@" || build_ec=$?
  if [[ "${build_ec}" -eq 124 ]]; then
    echo "docker build timed out with exit 124" >&2
    exit 1
  fi
  if [[ "${build_ec}" -ne 0 ]]; then
    echo "docker build failed with exit ${build_ec}" >&2
    exit 1
  fi
}

build_host_release_wheel() {
  local out_dir="$1"
  mkdir -p "${out_dir}"
  cd "${BACKEND_ROOT}"
  export UV_OFFLINE=true
  uv sync --locked --offline --all-groups
  local python_interpreter
  python_interpreter="$(uv run python -c 'import os, sys; print(os.path.realpath(sys.executable))')"
  export CARGO_TARGET_DIR="${out_dir}/cargo-target"
  export CARGO_NET_OFFLINE=true
  uv run maturin build \
    --release \
    --locked \
    --offline \
    --manifest-path "${COMPUTE_PYTHON_ROOT}/Cargo.toml" \
    --out "${out_dir}/dist" \
    --interpreter "${python_interpreter}"
  ls -1 "${out_dir}/dist"/*.whl | head -n 1
}

capture_wheel_identity() {
  local wheel_path="$1"
  uv run --offline --no-sync python - "${wheel_path}" "${VNEXT_ROOT}" <<'PY'
import hashlib
import importlib.metadata
import json
import sys
from pathlib import Path

import gateway_compute.gateway_compute as native

wheel_path = Path(sys.argv[1])
repo_root = Path(sys.argv[2])
source_tree = repo_root / "rust" / "gateway-compute-python"

module_file = Path(native.__file__).resolve()
if str(module_file).startswith(str(source_tree)):
    raise SystemExit(f"extension must not load from source tree: {module_file}")

wheel_sha256 = hashlib.sha256(wheel_path.read_bytes()).hexdigest()
extension_sha256 = hashlib.sha256(module_file.read_bytes()).hexdigest()
version = importlib.metadata.version("gateway-compute-python")
print(wheel_sha256)
print(extension_sha256)
print(version)
print(module_file)
PY
}

phase_exit_finalize_exit() {
  local body_ec="$1"
  local cleanup_ec="$2"
  if [[ "${body_ec}" -eq 0 && "${cleanup_ec}" -ne 0 ]]; then
    echo "phase-exit cleanup failed with exit ${cleanup_ec}" >&2
    return "${cleanup_ec}"
  fi
  if [[ "${body_ec}" -ne 0 && "${cleanup_ec}" -ne 0 ]]; then
    echo "phase-exit cleanup also failed: ${cleanup_ec}" >&2
  fi
  return "${body_ec}"
}

run_cleanup_runtime() {
  local project="$1"
  local image_tag="$2"
  local cleanup_ec=0
  export PHASE_EXIT_IMAGE_TAG="${image_tag}"
  export SOURCE_REVISION="${SOURCE_REVISION:-unknown}"
  export WHEEL_SHA256="${WHEEL_SHA256:-unknown}"
  export EXTENSION_SHA256="${EXTENSION_SHA256:-unknown}"
  docker compose -f "${COMPOSE_PHASE_EXIT_FILE}" -p "${project}" down -v --remove-orphans --rmi local \
    >/dev/null 2>&1 || cleanup_ec=$?

  local smoke_name="${project}-smoke"
  if docker container inspect "${smoke_name}" >/dev/null 2>&1; then
    docker rm -f "${smoke_name}" >/dev/null 2>&1 || cleanup_ec=$?
  fi
  if docker image inspect "${image_tag}" >/dev/null 2>&1; then
    if [[ "${PHASE_EXIT_CONTAINER_INJECT_RMI_FAIL:-}" == "1" ]]; then
      echo "injecting image removal failure" >&2
      cleanup_ec=96
    else
      docker rmi -f "${image_tag}" >/dev/null 2>&1 || cleanup_ec=$?
    fi
  fi
  return "${cleanup_ec}"
}

run_cleanup_files() {
  local cleanup_ec=0
  if [[ "${PHASE_EXIT_CONTAINER_FORCE_CLEANUP_FAIL:-}" == "1" ]]; then
    # Inject reports failure after best-effort sweep (no /tmp leak).
    rm -rf "${PHASE_EXIT_WHEEL_STAGING_DIR}" || true
    rm -rf "${PHASE_EXIT_TMP:-}" || true
    echo "injecting cleanup failure" >&2
    return 97
  fi
  if [[ "${PHASE_EXIT_CONTAINER_INJECT_TMP_RM_FAIL:-}" == "1" ]]; then
    # Same pattern: clear dirs, then report synthetic rm failure code.
    rm -rf "${PHASE_EXIT_WHEEL_STAGING_DIR}" || true
    rm -rf "${PHASE_EXIT_TMP:-}" || true
    echo "injecting phase-exit tmp removal failure" >&2
    return 95
  fi
  rm -rf "${PHASE_EXIT_WHEEL_STAGING_DIR}" || cleanup_ec=$?
  rm -rf "${PHASE_EXIT_TMP:-}" || cleanup_ec=$?
  return "${cleanup_ec}"
}

run_cleanup() {
  local project="$1"
  local image_tag="$2"
  local cleanup_ec=0
  run_cleanup_runtime "${project}" "${image_tag}" || cleanup_ec=$?
  run_cleanup_files || cleanup_ec=$?
  return "${cleanup_ec}"
}

stage_host_wheel_for_docker_build() {
  local wheel_path="$1"
  local expected_sha="$2"
  mkdir -p "${PHASE_EXIT_WHEEL_STAGING_DIR}"
  PHASE_EXIT_COMPUTE_WHEEL_BASENAME="$(basename "${wheel_path}")"
  PHASE_EXIT_COMPUTE_WHEEL_STAGING_PATH="${PHASE_EXIT_WHEEL_STAGING_DIR}/${PHASE_EXIT_COMPUTE_WHEEL_BASENAME}"
  cp -f "${wheel_path}" "${PHASE_EXIT_COMPUTE_WHEEL_STAGING_PATH}"
  local staged_sha
  staged_sha="$(sha256_file "${PHASE_EXIT_COMPUTE_WHEEL_STAGING_PATH}")"
  if [[ "${staged_sha}" != "${expected_sha}" ]]; then
    echo "staged wheel sha256 mismatch: expected ${expected_sha}, got ${staged_sha}" >&2
    exit 1
  fi
}

setup_pinned_host_uv() {
  local uv_venv="${PHASE_EXIT_WHEEL_STAGING_DIR}/uv-cli-venv"
  if [[ -x "${uv_venv}/bin/uv" ]]; then
    export PATH="${uv_venv}/bin:${PATH}"
    return 0
  fi
  python3 -m venv --without-pip "${uv_venv}"
  bootstrap_pinned_pip_into_venv "${uv_venv}/bin/python" "${PHASE_EXIT_PIP_WHEEL_STAGING_PATH}"
  "${uv_venv}/bin/python" -m pip install --no-cache-dir "${PHASE_EXIT_UV_WHEEL_STAGING_PATH}"
  export PATH="${uv_venv}/bin:${PATH}"
}

bootstrap_pinned_pip_into_venv() {
  local venv_python="$1"
  local pip_wheel="$2"
  "${venv_python}" - "${pip_wheel}" <<'PY'
import os
import subprocess
import sys
import tempfile
import zipfile

wheel = sys.argv[1]
with tempfile.TemporaryDirectory() as tmp:
    with zipfile.ZipFile(wheel) as zf:
        zf.extractall(tmp)
    env = {**os.environ, "PYTHONPATH": tmp}
    subprocess.check_call(
        [sys.executable, "-m", "pip", "install", "--no-index", "--no-cache-dir", "--force-reinstall", wheel],
        cwd=tmp,
        env=env,
    )
PY
}

stage_container_deps_wheels() {
  local export_dir="${PHASE_EXIT_TMP}/container-export"
  local selector_python wheel_list
  selector_python="$(run_identity_bundle_python)"
  local python_tag
  mkdir -p "${export_dir}" "${PHASE_EXIT_DEPS_WHEEL_DIR}"
  cp "${BACKEND_ROOT}/pyproject.container.toml" "${export_dir}/pyproject.toml"
  cp "${BACKEND_ROOT}/uv.container.lock" "${export_dir}/uv.lock"
  cp "${BACKEND_ROOT}/.python-version" "${export_dir}/"
  python_tag="$(phase_exit_container_python_tag "${export_dir}/.python-version")"
  wheel_list="${PHASE_EXIT_TMP}/deps-wheel-list.tsv"
  (
    cd "${export_dir}"
    uv export --frozen --no-dev --no-hashes --no-annotate -o requirements.txt
    if ! "${selector_python}" "${DEPS_WHEELS_SELECTOR}" filter-export \
      --input requirements.txt -o requirements-pypi.txt; then
      echo "container deps filter-export failed" >&2
      exit 1
    fi
    if [[ ! -s requirements-pypi.txt ]]; then
      echo "container deps requirements-pypi.txt empty after filter-export" >&2
      exit 1
    fi
    assert_deps_download_not_injected_on_formal_gate
    if ! "${selector_python}" "${DEPS_WHEELS_SELECTOR}" select \
      --requirements requirements-pypi.txt \
      --lock uv.lock \
      --python-tag "${python_tag}" >"${wheel_list}"; then
      echo "container deps wheel select failed" >&2
      exit 1
    fi
    if [[ ! -s "${wheel_list}" ]]; then
      echo "deps wheel select produced empty list" >&2
      exit 1
    fi
    local wheel_line url expected_sha basename dest fetch_line actual_sha
    while IFS= read -r wheel_line; do
      [[ -z "${wheel_line}" ]] && continue
      IFS=$'\t' read -r url expected_sha basename <<<"${wheel_line}"
      dest="${PHASE_EXIT_DEPS_WHEEL_DIR}/${basename}"
      fetch_line="$(phase_exit_curl_fetch_to_file "${dest}" "${url}")"
      phase_exit_read_curl_fetch_result "${fetch_line}"
      phase_exit_assert_curl_fetch_ok "deps-wheel" "${url}" "${CURL_FETCH_EC}" "${CURL_FETCH_HTTP_CODE}"
      actual_sha="$(sha256_file "${dest}")"
      if [[ "${actual_sha}" != "${expected_sha}" ]]; then
        echo "deps-wheel sha256 mismatch for ${basename}: expected ${expected_sha}, got ${actual_sha}" >&2
        exit 1
      fi
    done <"${wheel_list}"
  )
  touch "${PHASE_EXIT_DEPS_WHEEL_DIR}/.wheelhouse-marker"
}

run_identity_bundle_python() {
  if [[ -x "${BACKEND_ROOT}/.venv/bin/python" ]]; then
    printf '%s\n' "${BACKEND_ROOT}/.venv/bin/python"
  else
    printf '%s\n' "python3"
  fi
}

invoke_identity_bundle() {
  local subcommand="$1"
  local python_bin
  python_bin="$(run_identity_bundle_python)"
  "${python_bin}" "${IDENTITY_BUNDLE}" "${subcommand}"
}

rollback_identity_artifact() {
  local artifact_path="$1"
  local rb_ec=0
  if [[ -z "${artifact_path}" ]]; then
    return 0
  fi
  rm -f "${artifact_path}" || rb_ec=$?
  rm -f "${PHASE_EXIT_IDENTITY_ARTIFACT_DIR}/phase-exit-container-identity-latest.json" || rb_ec=$?
  return "${rb_ec}"
}

write_phase_exit_identity_draft() {
  export PHASE_EXIT_IDENTITY_DRAFT="${PHASE_EXIT_TMP}/identity-draft.json"
  export PHASE_EXIT_LOCK_AFTER
  export EXPECTED_HEAD="${EXPECTED_HEAD:-}"
  PHASE_EXIT_IDENTITY_CONTENT_DIGEST="$(
    invoke_identity_bundle draft
  )"
  export PHASE_EXIT_IDENTITY_CONTENT_DIGEST
}

persist_phase_exit_identity_atomic() {
  if [[ ! -f "${PHASE_EXIT_IDENTITY_DRAFT:-}" ]]; then
    echo "missing identity draft for persist" >&2
    return 1
  fi
  export PHASE_EXIT_IDENTITY_ARTIFACT_DIR
  invoke_identity_bundle persist
}

stage_pip_wheel_for_docker_build() {
  mkdir -p "${PHASE_EXIT_WHEEL_STAGING_DIR}"
  if [[ "${PHASE_EXIT_CONTAINER_INJECT_REGISTRY_BLOCKED:-}" == "1" ]]; then
    phase_exit_blocked "pip wheel download blocked (injected): ${PIP_WHEEL_URL}"
  fi
  if [[ "${PHASE_EXIT_CONTAINER_INJECT_PULL_TIMEOUT:-}" == "1" ]]; then
    phase_exit_blocked "pip wheel download timed out (injected): ${PIP_WHEEL_URL}"
  fi
  local fetch_line
  fetch_line="$(phase_exit_curl_fetch_to_file "${PHASE_EXIT_PIP_WHEEL_STAGING_PATH}" "${PIP_WHEEL_URL}")"
  phase_exit_read_curl_fetch_result "${fetch_line}"
  phase_exit_assert_curl_fetch_ok pip-wheel "${PIP_WHEEL_URL}" "${CURL_FETCH_EC}" "${CURL_FETCH_HTTP_CODE}"
  local staged_sha
  staged_sha="$(sha256_file "${PHASE_EXIT_PIP_WHEEL_STAGING_PATH}")"
  if [[ "${staged_sha}" != "${PIP_WHEEL_SHA256}" ]]; then
    echo "staged pip wheel sha256 mismatch: expected ${PIP_WHEEL_SHA256}, got ${staged_sha}" >&2
    exit 1
  fi
}

stage_uv_wheel_for_docker_build() {
  mkdir -p "${PHASE_EXIT_WHEEL_STAGING_DIR}"
  if [[ "${PHASE_EXIT_CONTAINER_INJECT_REGISTRY_BLOCKED:-}" == "1" ]]; then
    phase_exit_blocked "uv wheel download blocked (injected): ${UV_PIP_WHEEL_URL}"
  fi
  if [[ "${PHASE_EXIT_CONTAINER_INJECT_PULL_TIMEOUT:-}" == "1" ]]; then
    phase_exit_blocked "uv wheel download timed out (injected): ${UV_PIP_WHEEL_URL}"
  fi
  local fetch_line
  fetch_line="$(phase_exit_curl_fetch_to_file "${PHASE_EXIT_UV_WHEEL_STAGING_PATH}" "${UV_PIP_WHEEL_URL}")"
  phase_exit_read_curl_fetch_result "${fetch_line}"
  phase_exit_assert_curl_fetch_ok uv-wheel "${UV_PIP_WHEEL_URL}" "${CURL_FETCH_EC}" "${CURL_FETCH_HTTP_CODE}"
  local staged_sha
  staged_sha="$(sha256_file "${PHASE_EXIT_UV_WHEEL_STAGING_PATH}")"
  if [[ "${staged_sha}" != "${UV_PIP_WHEEL_SHA256}" ]]; then
    echo "staged uv wheel sha256 mismatch: expected ${UV_PIP_WHEEL_SHA256}, got ${staged_sha}" >&2
    exit 1
  fi
}

assert_image_contains_wheel_sha() {
  local image_tag="$1"
  local expected_wheel_sha="$2"
  docker run --rm \
    -e "GATEWAY_EXPECTED_WHEEL_SHA256=${expected_wheel_sha}" \
    -e "GATEWAY_EXPECTED_EXTENSION_SHA256=${EXTENSION_SHA256}" \
    -e "GATEWAY_SOURCE_REVISION=${SOURCE_REVISION}" \
    "${image_tag}" \
    python -c "import hashlib, os, pathlib; p=pathlib.Path(os.environ['GATEWAY_INSTALLED_WHEEL_PATH']); h=hashlib.sha256(p.read_bytes()).hexdigest(); exp=os.environ['GATEWAY_EXPECTED_WHEEL_SHA256']; assert h==exp, (h, exp); import gateway_compute.gateway_compute as native; m=pathlib.Path(native.__file__).resolve(); eh=hashlib.sha256(m.read_bytes()).hexdigest(); ee=os.environ['GATEWAY_EXPECTED_EXTENSION_SHA256']; assert eh==ee, (eh, ee)"
}

assert_healthz_ok() {
  local url="$1"
  python3 -c "import json, sys, urllib.request; data=json.load(urllib.request.urlopen(sys.argv[1], timeout=5)); assert data.get('status')=='ok', data" "${url}"
}

run_container_smokes() {
  local image_tag="$1"
  local source_revision="$2"
  local cid smoke_ec=0
  cid="$(docker run -d --name "${PHASE_EXIT_RUN_ID}-smoke" \
    -e "GATEWAY_SOURCE_REVISION=${source_revision}" \
    -e "GATEWAY_EXPECTED_WHEEL_SHA256=${WHEEL_SHA256}" \
    -e "GATEWAY_EXPECTED_EXTENSION_SHA256=${EXTENSION_SHA256}" \
    -p "${PHASE_EXIT_HOST_PORT}:8000" \
    "${image_tag}")"
  trap 'docker rm -f "${PHASE_EXIT_RUN_ID}-smoke" >/dev/null 2>&1 || true' RETURN
  local deadline=$((SECONDS + 60))
  while (( SECONDS < deadline )); do
    if curl -fsS "http://127.0.0.1:${PHASE_EXIT_HOST_PORT}/healthz" >/dev/null 2>&1; then
      break
    fi
    sleep 1
  done
  if [[ "${PHASE_EXIT_CONTAINER_INJECT_HEALTH_FAIL:-}" == "1" ]]; then
    echo "health smoke failed (injected)" >&2
    return 1
  fi
  curl -fsS "http://127.0.0.1:${PHASE_EXIT_HOST_PORT}/healthz" >/dev/null
  assert_healthz_ok "http://127.0.0.1:${PHASE_EXIT_HOST_PORT}/healthz"
  if [[ "${PHASE_EXIT_CONTAINER_INJECT_NATIVE_FAIL:-}" == "1" ]]; then
    echo "native smoke failed (injected)" >&2
    return 1
  fi
  docker exec "${cid}" python -m gateway_backend.container_native_smoke
  if docker container inspect "${cid}" >/dev/null 2>&1; then
    docker rm -f "${cid}" >/dev/null 2>&1 || smoke_ec=$?
  fi
  trap - RETURN
  return "${smoke_ec}"
}

run_compose_smoke() {
  local project="$1"
  local expected_image_id="$2"
  export PHASE_EXIT_IMAGE_TAG SOURCE_REVISION WHEEL_SHA256 EXTENSION_SHA256
  export GATEWAY_BACKEND_HOST_PORT="${PHASE_EXIT_COMPOSE_PORT}"
  if [[ "${PHASE_EXIT_CONTAINER_INJECT_COMPOSE_FAIL:-}" == "1" ]]; then
    echo "compose runtime failed (injected)" >&2
    return 1
  fi
  docker compose -f "${COMPOSE_PHASE_EXIT_FILE}" -p "${project}" config -q
  docker compose -f "${COMPOSE_PHASE_EXIT_FILE}" -p "${project}" up -d --no-build --wait backend
  local container_id running_image_id
  container_id="$(docker compose -f "${COMPOSE_PHASE_EXIT_FILE}" -p "${project}" ps -q backend)"
  running_image_id="$(docker inspect "${container_id}" --format '{{.Image}}')"
  if [[ "${running_image_id}" != "${expected_image_id}" ]]; then
    echo "compose backend image id mismatch: ${running_image_id} != ${expected_image_id}" >&2
    return 1
  fi
  curl -fsS "http://127.0.0.1:${PHASE_EXIT_COMPOSE_PORT}/healthz" >/dev/null
  assert_healthz_ok "http://127.0.0.1:${PHASE_EXIT_COMPOSE_PORT}/healthz"
  docker compose -f "${COMPOSE_PHASE_EXIT_FILE}" -p "${project}" exec -T backend \
    python -m gateway_backend.container_native_smoke
}

run_phase_exit_gate_body() {
  assert_linux_x86_64_glibc
  assert_forbid_allow_dirty_on_formal_gate
  assert_clean_worktree
  local source_revision
  source_revision="$(assert_head_identity)"
  load_pins
  assert_network_deadline_config
  assert_pins_have_digests
  assert_dockerfile_uses_digest_pins
  assert_docker_daemon

  PHASE_EXIT_RUN_ID="gateway-phase1-exit-${source_revision:0:12}-$$"
  PHASE_EXIT_IMAGE_TAG="gateway-vnext-phase1-exit:${source_revision:0:12}-$$"
  PHASE_EXIT_HOST_PORT="${PHASE_EXIT_HOST_PORT:-18080}"
  PHASE_EXIT_COMPOSE_PORT="${PHASE_EXIT_COMPOSE_PORT:-18081}"
  if [[ -z "${PHASE_EXIT_TMP:-}" ]]; then
    PHASE_EXIT_TMP="$(mktemp -d)"
  elif [[ ! -d "${PHASE_EXIT_TMP}" ]]; then
    echo "PHASE_EXIT_TMP is set but not a directory: ${PHASE_EXIT_TMP}" >&2
    exit 1
  fi
  PHASE_EXIT_LOCK_BEFORE="${PHASE_EXIT_TMP}/locks-before.txt"
  PHASE_EXIT_LOCK_AFTER="${PHASE_EXIT_TMP}/locks-after.txt"
  PHASE_EXIT_IDENTITY_FILE="${PHASE_EXIT_TMP}/identity.json"

  echo "phase-exit gate tmp=${PHASE_EXIT_TMP}"
  capture_lock_shas "${PHASE_EXIT_LOCK_BEFORE}"

  # Regression-only inject: success-path-regression sets REGRESSION_MODE=1.
  # Formal `gate` rejects INJECT_BODY_SUCCESS before reaching this body.
  if [[ "${PHASE_EXIT_CONTAINER_INJECT_BODY_SUCCESS:-}" == "1" ]]; then
    if [[ "${PHASE_EXIT_CONTAINER_REGRESSION_MODE:-}" != "1" ]]; then
      echo "PHASE_EXIT_CONTAINER_INJECT_BODY_SUCCESS requires REGRESSION_MODE=1" >&2
      exit 1
    fi
    echo "phase-exit-container gate passed (injected body success)"
    return 0
  fi

  if [[ "${PHASE_EXIT_CONTAINER_SKIP_BUILD:-}" == "1" ]]; then
    echo "PHASE_EXIT_CONTAINER_SKIP_BUILD=1 set; refusing full gate body" >&2
    exit 1
  fi

  docker_pull_with_blocked "${PYTHON_RUNTIME_IMAGE}"

  stage_pip_wheel_for_docker_build
  stage_uv_wheel_for_docker_build
  setup_pinned_host_uv
  assert_host_toolchain_matches_pins

  local wheel_path
  wheel_path="$(build_host_release_wheel "${PHASE_EXIT_TMP}")"
  cd "${BACKEND_ROOT}"
  uv pip install --offline --force-reinstall "${wheel_path}"
  mapfile -t identity_lines < <(capture_wheel_identity "${wheel_path}")
  WHEEL_SHA256="${identity_lines[0]}"
  EXTENSION_SHA256="${identity_lines[1]}"
  GATEWAY_COMPUTE_VERSION="${identity_lines[2]}"
  NATIVE_MODULE_PATH="${identity_lines[3]}"
  export WHEEL_SHA256 EXTENSION_SHA256 SOURCE_REVISION="${source_revision}"
  export PHASE_EXIT_HOST_UV_VERSION="$(uv --version 2>/dev/null || true)"
  export PHASE_EXIT_HOST_PIP_VERSION="$("${PHASE_EXIT_WHEEL_STAGING_DIR}/uv-cli-venv/bin/python" -m pip --version 2>/dev/null || true)"
  export PHASE_EXIT_HOST_RUSTC_VERSION="$(rustc --version 2>/dev/null || true)"
  export PHASE_EXIT_HOST_PYTHON_VERSION="$(uv run --offline --no-sync python --version 2>/dev/null || true)"
  export PHASE_EXIT_GATEWAY_COMPUTE_VERSION="${GATEWAY_COMPUTE_VERSION}"
  export PHASE_EXIT_PYTHON_RUNTIME_IMAGE="${PYTHON_RUNTIME_IMAGE}"
  export EXPECTED_HEAD="${EXPECTED_HEAD:-$(git -C "${REPO_ROOT}" rev-parse HEAD)}"
  stage_host_wheel_for_docker_build "${wheel_path}" "${WHEEL_SHA256}"
  stage_container_deps_wheels

  docker_build_offline \
    -f "${DOCKERFILE}" \
    -t "${PHASE_EXIT_IMAGE_TAG}" \
    --build-arg "PYTHON_RUNTIME_IMAGE=${PYTHON_RUNTIME_IMAGE}" \
    --build-arg "SOURCE_REVISION=${source_revision}" \
    --build-arg "WHEEL_SHA256=${WHEEL_SHA256}" \
    --build-arg "EXTENSION_SHA256=${EXTENSION_SHA256}" \
    --build-arg "UV_WHEEL_SHA256=${UV_PIP_WHEEL_SHA256}" \
    --build-arg "UV_VERSION=${UV_VERSION}" \
    --build-arg "PYTHON_VERSION=${PYTHON_VERSION}" \
    --build-arg "UV_WHEEL_BASENAME=${PHASE_EXIT_UV_WHEEL_BASENAME}" \
    --build-arg "GATEWAY_COMPUTE_WHEEL_BASENAME=${PHASE_EXIT_COMPUTE_WHEEL_BASENAME}" \
    --label "gateway.vnext.gate=phase-exit-container" \
    "${VNEXT_ROOT}"

  assert_image_contains_wheel_sha "${PHASE_EXIT_IMAGE_TAG}" "${WHEEL_SHA256}"

  local image_id repo_digest
  if ! image_id="$(docker image inspect "${PHASE_EXIT_IMAGE_TAG}" --format '{{.Id}}')"; then
    echo "docker image inspect failed for ${PHASE_EXIT_IMAGE_TAG}" >&2
    exit 1
  fi
  repo_digest="$(docker image inspect "${PHASE_EXIT_IMAGE_TAG}" --format '{{if .RepoDigests}}{{index .RepoDigests 0}}{{end}}')"
  local label_revision label_wheel label_extension
  label_revision="$(docker image inspect "${PHASE_EXIT_IMAGE_TAG}" --format '{{ index .Config.Labels "gateway.vnext.source.revision" }}')"
  label_wheel="$(docker image inspect "${PHASE_EXIT_IMAGE_TAG}" --format '{{ index .Config.Labels "gateway.vnext.wheel.sha256" }}')"
  label_extension="$(docker image inspect "${PHASE_EXIT_IMAGE_TAG}" --format '{{ index .Config.Labels "gateway.vnext.extension.sha256" }}')"
  if [[ "${label_revision}" != "${source_revision}" ]]; then
    echo "image revision label mismatch: ${label_revision} != ${source_revision}" >&2
    exit 1
  fi
  if [[ "${label_wheel}" != "${WHEEL_SHA256}" ]]; then
    echo "image wheel label mismatch" >&2
    exit 1
  fi
  if [[ "${label_extension}" != "${EXTENSION_SHA256}" ]]; then
    echo "image extension label mismatch" >&2
    exit 1
  fi
  if [[ "${PHASE_EXIT_CONTAINER_INJECT_LABEL_MISMATCH:-}" == "1" ]]; then
    echo "image revision label mismatch (injected)" >&2
    exit 1
  fi

  run_container_smokes "${PHASE_EXIT_IMAGE_TAG}" "${source_revision}"
  run_compose_smoke "${PHASE_EXIT_RUN_ID}" "${image_id}"

  capture_lock_shas "${PHASE_EXIT_LOCK_AFTER}"
  assert_lock_shas_unchanged "${PHASE_EXIT_LOCK_BEFORE}" "${PHASE_EXIT_LOCK_AFTER}"
  write_phase_exit_identity_draft
  echo "phase-exit-container gate passed"
}

# EXIT trap handler must be a real function so `local` is valid after the
# gated function returns (bash leaves EXIT traps outside that function scope).
phase_exit_exit_trap() {
  local ec=$?
  local cleanup_ec=0
  local identity_final_path=""
  local identity_persist_attempted=0
  run_cleanup_runtime "${PHASE_EXIT_RUN_ID}" "${PHASE_EXIT_IMAGE_TAG}" || cleanup_ec=$?
  if [[ "${ec}" -eq 0 && "${cleanup_ec}" -eq 0 && -n "${PHASE_EXIT_IDENTITY_DRAFT:-}" && -f "${PHASE_EXIT_IDENTITY_DRAFT}" && -n "${PHASE_EXIT_IDENTITY_CONTENT_DIGEST:-}" ]]; then
    identity_final_path="${PHASE_EXIT_IDENTITY_ARTIFACT_DIR}/phase-exit-container-identity-${PHASE_EXIT_IDENTITY_CONTENT_DIGEST}.json"
    identity_persist_attempted=1
    persist_phase_exit_identity_atomic || cleanup_ec=$?
  else
    rm -f "${PHASE_EXIT_IDENTITY_DRAFT:-}"
  fi
  run_cleanup_files || cleanup_ec=$?
  if [[ "${identity_persist_attempted}" -eq 1 && ( "${ec}" -ne 0 || "${cleanup_ec}" -ne 0 ) ]]; then
    rollback_identity_artifact "${identity_final_path}" || cleanup_ec=$?
  fi
  phase_exit_finalize_exit "${ec}" "${cleanup_ec}"
  exit $?
}

run_phase_exit_gate_shared() {
  PHASE_EXIT_RUN_ID="gateway-phase1-exit-pending-$$"
  PHASE_EXIT_IMAGE_TAG="gateway-vnext-phase1-exit-pending:$$"
  PHASE_EXIT_TMP=""
  trap 'phase_exit_exit_trap' EXIT
  run_phase_exit_gate_body
}

run_phase_exit_gate() {
  assert_forbid_attestation_bypass_on_formal_gate
  run_phase_exit_gate_shared
}

run_check_static() {
  load_pins
  assert_network_deadline_config
  assert_pins_have_digests
  assert_dockerfile_uses_digest_pins
  echo "phase-exit static checks ok"
}

run_trap_regression() {
  local trap_tmp1 trap_tmp2
  echo "==> phase-exit trap regression: body ok + cleanup fail"
  trap_tmp1="$(mktemp -d)"
  set +e
  (
    set -euo pipefail
    export PHASE_EXIT_CONTAINER_FORCE_CLEANUP_FAIL=1
    PHASE_EXIT_RUN_ID="gateway-phase1-exit-trap-$$"
    PHASE_EXIT_IMAGE_TAG="gateway-vnext-phase1-exit-trap:$$"
    PHASE_EXIT_TMP="${trap_tmp1}"
    trap 'phase_exit_exit_trap' EXIT
    exit 0
  )
  local ec=$?
  set -e
  rm -rf "${trap_tmp1}" || true
  if [[ "${ec}" -ne 97 ]]; then
    echo "expected exit 97 for cleanup failure after success, got ${ec}" >&2
    exit 1
  fi

  echo "==> phase-exit trap regression: body fail + cleanup fail"
  trap_tmp2="$(mktemp -d)"
  set +e
  (
    set -euo pipefail
    export PHASE_EXIT_CONTAINER_FORCE_CLEANUP_FAIL=1
    PHASE_EXIT_RUN_ID="gateway-phase1-exit-trap2-$$"
    PHASE_EXIT_IMAGE_TAG="gateway-vnext-phase1-exit-trap2:$$"
    PHASE_EXIT_TMP="${trap_tmp2}"
    trap 'phase_exit_exit_trap' EXIT
    exit 42
  )
  ec=$?
  set -e
  rm -rf "${trap_tmp2}" || true
  if [[ "${ec}" -ne 42 ]]; then
    echo "expected original body exit 42 when both fail, got ${ec}" >&2
    exit 1
  fi
  echo "phase-exit trap regression ok"
}

run_success_path_regression() {
  local expected_head success_tmp
  expected_head="$(git -C "${REPO_ROOT}" rev-parse HEAD)"
  echo "==> phase-exit success-path: regression run_phase_exit_gate_shared body ok + cleanup fail"
  success_tmp="$(mktemp -d)"
  set +e
  (
    set -euo pipefail
    export EXPECTED_HEAD="${expected_head}"
    export PHASE_EXIT_CONTAINER_REGRESSION_MODE=1
    export PHASE_EXIT_CONTAINER_ALLOW_DIRTY=1
    export PHASE_EXIT_CONTAINER_SKIP_PLATFORM_CHECK=1
    export PHASE_EXIT_CONTAINER_INJECT_BODY_SUCCESS=1
    export PHASE_EXIT_CONTAINER_FORCE_CLEANUP_FAIL=1
    export PHASE_EXIT_TMP="${success_tmp}"
    run_phase_exit_gate_shared
  )
  local ec=$?
  set -e
  rm -rf "${success_tmp}" || true
  if [[ "${ec}" -ne 97 ]]; then
    echo "expected exit 97 for real gate cleanup failure after success, got ${ec}" >&2
    exit 1
  fi

  echo "==> phase-exit success-path: regression run_phase_exit_gate_shared body ok + cleanup ok"
  success_tmp="$(mktemp -d)"
  set +e
  (
    set -euo pipefail
    export EXPECTED_HEAD="${expected_head}"
    export PHASE_EXIT_CONTAINER_REGRESSION_MODE=1
    export PHASE_EXIT_CONTAINER_ALLOW_DIRTY=1
    export PHASE_EXIT_CONTAINER_SKIP_PLATFORM_CHECK=1
    export PHASE_EXIT_CONTAINER_INJECT_BODY_SUCCESS=1
    unset PHASE_EXIT_CONTAINER_FORCE_CLEANUP_FAIL || true
    export PHASE_EXIT_TMP="${success_tmp}"
    run_phase_exit_gate_shared
  )
  ec=$?
  set -e
  rm -rf "${success_tmp}" || true
  if [[ "${ec}" -ne 0 ]]; then
    echo "expected exit 0 for real gate success path, got ${ec}" >&2
    exit 1
  fi
  echo "phase-exit success-path regression ok"
}

run_verify_registry_blocked() {
  load_pins
  assert_network_deadline_config
  assert_pins_have_digests
  docker_pull_with_blocked "${PYTHON_RUNTIME_IMAGE}"
}

run_bootstrap_pip_regression() {
  local regression_root pip_out
  regression_root="$(mktemp -d)"
  __phase_exit_bootstrap_regression_root="${regression_root}"
  trap '[[ -n "${__phase_exit_bootstrap_regression_root:-}" ]] && rm -rf "${__phase_exit_bootstrap_regression_root}"' EXIT
  PHASE_EXIT_WHEEL_STAGING_DIR="${regression_root}/staging"
  PHASE_EXIT_TMP="${regression_root}"
  mkdir -p "${PHASE_EXIT_WHEEL_STAGING_DIR}"
  load_pins
  assert_network_deadline_config
  assert_pins_have_digests
  stage_pip_wheel_for_docker_build
  local uv_venv="${regression_root}/venv"
  python3 -m venv --without-pip "${uv_venv}"
  bootstrap_pinned_pip_into_venv "${uv_venv}/bin/python" "${PHASE_EXIT_PIP_WHEEL_STAGING_PATH}"
  pip_out="$("${uv_venv}/bin/python" -m pip --version 2>/dev/null || true)"
  if [[ "${pip_out}" != pip\ "${PIP_VERSION}"* ]]; then
    echo "bootstrap pip regression failed: expected pip ${PIP_VERSION}, got ${pip_out}" >&2
    exit 1
  fi
  printf '%s\n' "${pip_out}"
}

run_export_select_regression() {
  local root export_dir selector_python python_tag wheel_list line_count pyarrow_ok line
  root="$(mktemp -d)"
  export_dir="${root}/container-export"
  selector_python="$(run_identity_bundle_python)"
  python_tag="$(phase_exit_container_python_tag "${BACKEND_ROOT}/.python-version")"
  wheel_list="${root}/deps-wheel-list.tsv"
  mkdir -p "${export_dir}"
  cp "${BACKEND_ROOT}/pyproject.container.toml" "${export_dir}/pyproject.toml"
  cp "${BACKEND_ROOT}/uv.container.lock" "${export_dir}/uv.lock"
  cp "${BACKEND_ROOT}/.python-version" "${export_dir}/"
  if ! (
    cd "${export_dir}"
    uv export --frozen --no-dev --no-hashes --no-annotate -o requirements.txt
    "${selector_python}" "${DEPS_WHEELS_SELECTOR}" filter-export \
      --input requirements.txt -o requirements-pypi.txt
    "${selector_python}" "${DEPS_WHEELS_SELECTOR}" select \
      --requirements requirements-pypi.txt \
      --lock uv.lock \
      --python-tag "${python_tag}" >"${wheel_list}"
  ); then
    rm -rf "${root}"
    return 1
  fi
  if [[ ! -s "${wheel_list}" ]]; then
    echo "export-select-regression: empty wheel list" >&2
    rm -rf "${root}"
    return 1
  fi
  line_count=0
  pyarrow_ok=0
  while IFS= read -r line; do
    [[ -z "${line}" ]] && continue
    line_count=$((line_count + 1))
    if [[ "${line}" == *pyarrow* ]] && [[ "${line}" == *manylinux* ]] && [[ "${line}" == *x86_64* ]]; then
      pyarrow_ok=1
    fi
  done <"${wheel_list}"
  if [[ "${line_count}" -le 0 ]]; then
    echo "export-select-regression: expected wheel lines > 0" >&2
    rm -rf "${root}"
    exit 1
  fi
  if [[ "${pyarrow_ok}" -ne 1 ]]; then
    echo "export-select-regression: expected pyarrow manylinux x86_64 wheel" >&2
    rm -rf "${root}"
    exit 1
  fi
  rm -rf "${root}"
}

run_deps_classify_regression() {
  local root log stderr_file ec selector_python python_tag
  root="$(mktemp -d)"
  __phase_exit_deps_classify_root="${root}"
  trap '[[ -n "${__phase_exit_deps_classify_root:-}" ]] && rm -rf "${__phase_exit_deps_classify_root}"' EXIT
  log="${root}/test.log"
  selector_python="$(run_identity_bundle_python)"
  python_tag="$(phase_exit_container_python_tag "${BACKEND_ROOT}/.python-version")"

  if ! "${selector_python}" "${DEPS_WHEELS_SELECTOR}" select-regression \
    --lock "${BACKEND_ROOT}/uv.container.lock" \
    --python-tag "${python_tag}"; then
    echo "deps-classify: select-regression failed" >&2
    exit 1
  fi

  if ! run_export_select_regression; then
    echo "deps-classify: export-select-regression failed" >&2
    exit 1
  fi

  export PHASE_EXIT_CONTAINER_INJECT_DEPS_TIMEOUT=1
  stderr_file="${root}/case-inject.err"
  set +e
  (
    assert_deps_download_not_injected_on_formal_gate 2>"${stderr_file}"
  )
  ec=$?
  unset PHASE_EXIT_CONTAINER_INJECT_DEPS_TIMEOUT || true
  set -e
  if [[ "${ec}" -ne 3 ]]; then
    echo "deps-classify: inject expected exit 3, got ${ec}" >&2
    exit 1
  fi

  stderr_file="${root}/case-curl-local.err"
  set +e
  (
    phase_exit_report_curl_fetch_failure pip-wheel "http://example.invalid/w.whl" 23 404 2>"${stderr_file}"
  )
  ec=$?
  set -e
  if [[ "${ec}" -ne 1 ]]; then
    echo "deps-classify: curl-local expected exit 1, got ${ec}" >&2
    exit 1
  fi

  stderr_file="${root}/case-deps-wheel-http503.err"
  set +e
  (
    phase_exit_report_curl_fetch_failure deps-wheel "http://example.invalid/w.whl" 22 503 2>"${stderr_file}"
  )
  ec=$?
  set -e
  if [[ "${ec}" -ne 3 ]]; then
    echo "deps-classify: deps-wheel-http503 expected exit 3, got ${ec}" >&2
    exit 1
  fi
  if ! grep -q 'BLOCKED:' "${stderr_file}"; then
    echo "deps-classify: deps-wheel-http503 expected BLOCKED" >&2
    exit 1
  fi

  stderr_file="${root}/case-curl-http503.err"
  set +e
  (
    phase_exit_report_curl_fetch_failure pip-wheel "http://example.invalid/w.whl" 22 503 2>"${stderr_file}"
  )
  ec=$?
  set -e
  if [[ "${ec}" -ne 3 ]]; then
    echo "deps-classify: curl-http503 expected exit 3, got ${ec}" >&2
    exit 1
  fi
  if ! grep -q 'BLOCKED:' "${stderr_file}"; then
    echo "deps-classify: curl-http503 expected BLOCKED" >&2
    exit 1
  fi

  stderr_file="${root}/case-curl-transport.err"
  set +e
  (
    phase_exit_report_curl_fetch_failure pip-wheel "http://example.invalid/w.whl" 6 000 2>"${stderr_file}"
  )
  ec=$?
  set -e
  if [[ "${ec}" -ne 3 ]]; then
    echo "deps-classify: curl-transport expected exit 3, got ${ec}" >&2
    exit 1
  fi

  for curl_ec in 16 18 92 95 96 97; do
    stderr_file="${root}/case-curl-ec-${curl_ec}.err"
    set +e
    (
      phase_exit_report_curl_fetch_failure pip-wheel "http://example.invalid/w.whl" "${curl_ec}" 200 2>"${stderr_file}"
    )
    ec=$?
    set -e
    if [[ "${ec}" -ne 3 ]]; then
      echo "deps-classify: curl-ec-${curl_ec} expected exit 3, got ${ec}" >&2
      exit 1
    fi
    if ! grep -q 'BLOCKED:' "${stderr_file}"; then
      echo "deps-classify: curl-ec-${curl_ec} expected BLOCKED" >&2
      exit 1
    fi
  done

  stderr_file="${root}/case-curl-timeout.err"
  set +e
  (
    phase_exit_report_curl_fetch_failure pip-wheel "http://example.invalid/w.whl" 28 000 2>"${stderr_file}"
  )
  ec=$?
  set -e
  if [[ "${ec}" -ne 3 ]]; then
    echo "deps-classify: curl-28 expected exit 3, got ${ec}" >&2
    exit 1
  fi
  if ! grep -q 'timed out' "${stderr_file}"; then
    echo "deps-classify: curl-28 expected timed out message" >&2
    exit 1
  fi

  for code in 503 429 408; do
    stderr_file="${root}/case-http-${code}.err"
    set +e
    (
      phase_exit_report_http_status_failure pypi-index "https://pypi.org/simple/" "${code}" 2>"${stderr_file}"
    )
    ec=$?
    set -e
    if [[ "${ec}" -ne 3 ]]; then
      echo "deps-classify: HTTP ${code} expected exit 3, got ${ec}" >&2
      exit 1
    fi
  done

  stderr_file="${root}/case-http-404.err"
  set +e
  (
    phase_exit_report_http_status_failure pypi-index "https://pypi.org/simple/" 404 2>"${stderr_file}"
  )
  ec=$?
  set -e
  if [[ "${ec}" -ne 1 ]]; then
    echo "deps-classify: HTTP 404 expected exit 1, got ${ec}" >&2
    exit 1
  fi
  if grep -q 'BLOCKED:' "${stderr_file}"; then
    echo "deps-classify: HTTP 404 must not emit BLOCKED" >&2
    exit 1
  fi

  stderr_file="${root}/case-deps-wheel-http404.err"
  set +e
  (
    phase_exit_report_curl_fetch_failure deps-wheel "http://example.invalid/w.whl" 0 404 2>"${stderr_file}"
  )
  ec=$?
  set -e
  if [[ "${ec}" -ne 1 ]]; then
    echo "deps-classify: deps-wheel-http404 expected exit 1, got ${ec}" >&2
    exit 1
  fi
  if grep -q 'BLOCKED:' "${stderr_file}"; then
    echo "deps-classify: deps-wheel-http404 must not emit BLOCKED" >&2
    exit 1
  fi

  printf '%s\n' 'invalid reference format' >"${root}/pull-local.log"
  stderr_file="${root}/case-pull-local.err"
  set +e
  (
    phase_exit_report_docker_pull_failure '!!!invalid!!!' 1 "${root}/pull-local.log" 2>"${stderr_file}"
  )
  ec=$?
  set -e
  if [[ "${ec}" -ne 1 ]]; then
    echo "deps-classify: docker pull local ref expected exit 1, got ${ec}" >&2
    exit 1
  fi

  printf '%s\n' 'Error response from daemon: manifest invalid' >"${root}/pull-manifest-invalid.log"
  stderr_file="${root}/case-pull-manifest-invalid.err"
  set +e
  (
    phase_exit_report_docker_pull_failure 'library/python:3.14' 1 "${root}/pull-manifest-invalid.log" 2>"${stderr_file}"
  )
  ec=$?
  set -e
  if [[ "${ec}" -ne 3 ]]; then
    echo "deps-classify: docker pull manifest invalid expected exit 3, got ${ec}" >&2
    exit 1
  fi
  if ! grep -q 'BLOCKED:' "${stderr_file}"; then
    echo "deps-classify: docker pull manifest invalid expected BLOCKED" >&2
    exit 1
  fi

  fetch_body="${root}/fetch-transport.body"
  fetch_line="$(phase_exit_curl_fetch_to_file "${fetch_body}" "http://127.0.0.1:1/")"
  phase_exit_read_curl_fetch_result "${fetch_line}"
  if [[ "${CURL_FETCH_EC}" -eq 0 ]]; then
    echo "deps-classify: T-fetch-transport expected non-zero curl_ec, got 0" >&2
    exit 1
  fi
  stderr_file="${root}/case-fetch-transport.err"
  set +e
  (
    phase_exit_assert_curl_fetch_ok fetch-probe "http://127.0.0.1:1/" "${CURL_FETCH_EC}" "${CURL_FETCH_HTTP_CODE}" 2>"${stderr_file}"
  )
  ec=$?
  set -e
  if [[ "${ec}" -ne 3 ]]; then
    echo "deps-classify: T-fetch-transport expected exit 3, got ${ec}" >&2
    exit 1
  fi
  if ! grep -q 'BLOCKED:' "${stderr_file}"; then
    echo "deps-classify: T-fetch-transport expected BLOCKED" >&2
    exit 1
  fi

  local trunc_port trunc_pid trunc_body trunc_line
  trunc_port="$(python3 -c 'import socket; s=socket.socket(); s.bind(("127.0.0.1", 0)); print(s.getsockname()[1]); s.close()')"
  TRUNC_PORT="${trunc_port}" python3 -u - <<'PY' &
import os
import socket

port = int(os.environ["TRUNC_PORT"])
sock = socket.socket()
sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
sock.bind(("127.0.0.1", port))
sock.listen(1)
conn, _ = sock.accept()
conn.sendall(
    b"HTTP/1.1 200 OK\r\n"
    b"Content-Length: 100\r\n"
    b"Connection: close\r\n"
    b"\r\n"
    b"12345"
)
conn.close()
sock.close()
PY
  trunc_pid=$!
  sleep 0.2
  trunc_body="${root}/fetch-truncated.body"
  trunc_line="$(phase_exit_curl_fetch_to_file "${trunc_body}" "http://127.0.0.1:${trunc_port}/")"
  wait "${trunc_pid}" 2>/dev/null || true
  phase_exit_read_curl_fetch_result "${trunc_line}"
  if [[ "${CURL_FETCH_EC}" -eq 0 ]]; then
    echo "deps-classify: T-fetch-truncated expected non-zero curl_ec, got 0" >&2
    exit 1
  fi
  if ! phase_exit_curl_is_transport_ec "${CURL_FETCH_EC}"; then
    echo "deps-classify: T-fetch-truncated expected transport curl_ec, got ${CURL_FETCH_EC}" >&2
    exit 1
  fi
  stderr_file="${root}/case-fetch-truncated.err"
  set +e
  (
    phase_exit_assert_curl_fetch_ok fetch-truncated "http://127.0.0.1:${trunc_port}/" "${CURL_FETCH_EC}" "${CURL_FETCH_HTTP_CODE}" 2>"${stderr_file}"
  )
  ec=$?
  set -e
  if [[ "${ec}" -ne 3 ]]; then
    echo "deps-classify: T-fetch-truncated expected exit 3, got ${ec}" >&2
    exit 1
  fi
  if ! grep -q 'BLOCKED:' "${stderr_file}"; then
    echo "deps-classify: T-fetch-truncated expected BLOCKED" >&2
    exit 1
  fi

  stderr_file="${root}/case-curl-http404.err"
  set +e
  (
    phase_exit_report_curl_fetch_failure pip-wheel "http://example.invalid/w.whl" 0 404 2>"${stderr_file}"
  )
  ec=$?
  set -e
  if [[ "${ec}" -ne 1 ]]; then
    echo "deps-classify: curl-http404 expected exit 1, got ${ec}" >&2
    exit 1
  fi
  if grep -q 'BLOCKED:' "${stderr_file}"; then
    echo "deps-classify: curl-http404 must not emit BLOCKED" >&2
    exit 1
  fi

  printf '%s\n' 'Error response from daemon: unauthorized' >"${root}/pull-net.log"
  stderr_file="${root}/case-pull-net.err"
  set +e
  (
    phase_exit_report_docker_pull_failure 'library/python:3.14' 1 "${root}/pull-net.log" 2>"${stderr_file}"
  )
  ec=$?
  set -e
  if [[ "${ec}" -ne 3 ]]; then
    echo "deps-classify: docker pull network expected exit 3, got ${ec}" >&2
    exit 1
  fi

  echo "deps-classify regression ok"
}

MODE="${1:-gate}"
case "${MODE}" in
  gate) run_phase_exit_gate ;;
  check-static) run_check_static ;;
  trap-regression) run_trap_regression ;;
  success-path-regression) run_success_path_regression ;;
  verify-registry-blocked) run_verify_registry_blocked ;;
  bootstrap-pip-regression) run_bootstrap_pip_regression ;;
  deps-classify-regression) run_deps_classify_regression ;;
  *) usage ;;
esac
