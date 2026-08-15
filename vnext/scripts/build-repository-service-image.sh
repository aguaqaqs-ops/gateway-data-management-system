#!/usr/bin/env bash
set -euo pipefail

# Build repository-service image using the retained P2-R1 dependency cache when available.
# Local uncached builds that download Dolt/uv from the public internet are intentionally
# not supported here; use a remote builder with retained cache instead.
#
# Environment:
#   GATEWAY_REPOSITORY_SERVICE_IMAGE     output tag (default: gateway-repository-service:local)
#   GATEWAY_P2R1_DEPENDENCY_BASE_IMAGE   dependency-base tag to reuse
#   GATEWAY_P2R1_CACHE_URL               cache HTTP root (default: http://172.17.0.1:18080)
#   GATEWAY_P2R1_CANDIDATE_SHA           optional; must match helper candidate_sha
#   GATEWAY_P2R1_BUILD_INPUT_REVISION    optional; must match helper build_input_revision
#   GATEWAY_P2R1_SOURCE_TREE_SHA256      optional; must match helper source_tree_sha256
#   GATEWAY_P2R1_UV_LOCK_SHA256          optional; must match repository_service/uv.lock
#   DOCKER_HOST                          optional remote Docker daemon
#
# GATEWAY_P2R1_BUILD_REVISION is ignored and is not an identity override.

VNEXT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
REPO_ROOT="$(cd "${VNEXT_ROOT}/.." && pwd)"
IMAGE_TAG="${GATEWAY_REPOSITORY_SERVICE_IMAGE:-gateway-repository-service:local}"
UV_LOCK_SHA256="$(sha256sum "${VNEXT_ROOT}/repository_service/uv.lock" | awk '{print $1}')"
if [[ -n "${GATEWAY_P2R1_UV_LOCK_SHA256:-}" && "${GATEWAY_P2R1_UV_LOCK_SHA256}" != "${UV_LOCK_SHA256}" ]]; then
  echo "error: GATEWAY_P2R1_UV_LOCK_SHA256 does not match repository_service/uv.lock" >&2
  exit 1
fi
DEPENDENCY_BASE="${GATEWAY_P2R1_DEPENDENCY_BASE_IMAGE:-gateway-p2r1-repository:lock-${UV_LOCK_SHA256:0:12}}"
CACHE_URL="${GATEWAY_P2R1_CACHE_URL:-http://172.17.0.1:18080}"
DIGEST_HELPER="${VNEXT_ROOT}/repository_service/tests/support/build_context_digest.py"

if ! IDENTITY_JSON="$(python3 "${DIGEST_HELPER}" identity)"; then
  echo "error: unable to compute repository image identity" >&2
  exit 1
fi

readarray -t IDENTITY_FIELDS < <(
  printf '%s' "${IDENTITY_JSON}" | python3 -c '
import json, sys
payload = json.load(sys.stdin)
for key in ("candidate_sha", "build_input_revision", "source_tree_sha256"):
    value = payload.get(key)
    if not isinstance(value, str) or not value:
        raise SystemExit(f"error: identity missing {key}")
    print(value)
'
)
CANDIDATE_SHA="${IDENTITY_FIELDS[0]:-}"
BUILD_INPUT_REVISION="${IDENTITY_FIELDS[1]:-}"
SOURCE_TREE_SHA256="${IDENTITY_FIELDS[2]:-}"

if [[ -n "${GATEWAY_P2R1_CANDIDATE_SHA:-}" && "${GATEWAY_P2R1_CANDIDATE_SHA}" != "${CANDIDATE_SHA}" ]]; then
  echo "error: GATEWAY_P2R1_CANDIDATE_SHA does not match helper candidate_sha" >&2
  exit 1
fi
if [[ -n "${GATEWAY_P2R1_BUILD_INPUT_REVISION:-}" && "${GATEWAY_P2R1_BUILD_INPUT_REVISION}" != "${BUILD_INPUT_REVISION}" ]]; then
  echo "error: GATEWAY_P2R1_BUILD_INPUT_REVISION does not match helper build_input_revision" >&2
  exit 1
fi
if [[ -n "${GATEWAY_P2R1_SOURCE_TREE_SHA256:-}" && "${GATEWAY_P2R1_SOURCE_TREE_SHA256}" != "${SOURCE_TREE_SHA256}" ]]; then
  echo "error: GATEWAY_P2R1_SOURCE_TREE_SHA256 does not match helper source_tree_sha256" >&2
  exit 1
fi

if [[ ! "${CANDIDATE_SHA}" =~ ^[0-9a-f]{40}$ ]]; then
  echo "error: candidate_sha must be a 40-character lowercase hex digest" >&2
  exit 1
fi
if [[ ! "${BUILD_INPUT_REVISION}" =~ ^[0-9a-f]{40}$ ]]; then
  echo "error: build_input_revision must be a 40-character lowercase hex digest" >&2
  exit 1
fi
if [[ ! "${SOURCE_TREE_SHA256}" =~ ^sha256:[0-9a-f]{64}$ ]]; then
  echo "error: source_tree_sha256 must be a sha256 digest" >&2
  exit 1
fi

cache_reachable() {
  curl -fsS --connect-timeout 2 "${CACHE_URL}/" >/dev/null 2>&1 \
    || curl -fsS --connect-timeout 2 -o /dev/null "${CACHE_URL}/dolt/2.1.11/dolt-linux-amd64.tar.gz"
}

dependency_base_available() {
  if ! docker image inspect "${DEPENDENCY_BASE}" >/dev/null 2>&1; then
    return 1
  fi
  local label_digest
  label_digest="$(docker image inspect "${DEPENDENCY_BASE}" --format '{{index .Config.Labels "gateway.p2r1.uv-lock-sha256"}}')"
  [[ -n "${label_digest}" && "${label_digest}" == "${UV_LOCK_SHA256}" ]]
}

build_args=(
  --network=host
  --file "${VNEXT_ROOT}/repository_service/Dockerfile"
  --tag "${IMAGE_TAG}"
  --build-arg "CANDIDATE_SHA=${CANDIDATE_SHA}"
  --build-arg "BUILD_INPUT_REVISION=${BUILD_INPUT_REVISION}"
  --build-arg "SOURCE_TREE_SHA256=${SOURCE_TREE_SHA256}"
  --build-arg "UV_LOCK_SHA256=${UV_LOCK_SHA256}"
  --build-arg MYSQL_CONNECTOR_VERSION=9.7.0
  --build-arg PYARROW_VERSION=25.0.0
)

if dependency_base_available; then
  echo "==> building ${IMAGE_TAG} from retained dependency-base ${DEPENDENCY_BASE}"
  build_args+=(
    --build-arg "BASE_IMAGE=${DEPENDENCY_BASE}"
    --build-arg USE_PRELOADED_DEPENDENCIES=1
  )
elif cache_reachable; then
  echo "==> building ${IMAGE_TAG} from retained artifact cache at ${CACHE_URL}"
  build_args+=(
    --build-arg "DOLT_DOWNLOAD_URL=${CACHE_URL}/dolt/2.1.11/dolt-linux-amd64.tar.gz"
    --build-arg "UV_BOOTSTRAP_INDEX_URL=${CACHE_URL}/uv/simple"
    --build-arg "UV_BOOTSTRAP_TRUSTED_HOST=172.17.0.1"
  )
  if [[ -n "${HTTP_PROXY:-}" ]]; then
    build_args+=(--build-arg "HTTP_PROXY=${HTTP_PROXY}")
  fi
  if [[ -n "${HTTPS_PROXY:-}" ]]; then
    build_args+=(--build-arg "HTTPS_PROXY=${HTTPS_PROXY}")
  fi
  build_args+=(--build-arg "NO_PROXY=${NO_PROXY:-172.17.0.1,localhost,127.0.0.1}")
else
  echo "error: no retained dependency-base image and artifact cache is unreachable at ${CACHE_URL}" >&2
  echo "hint: run on the remote development host documented in vnext/deploy/p2r1-cache/README.md" >&2
  echo "hint: export DOCKER_HOST=ssh://<remote> when building against a remote daemon" >&2
  exit 1
fi

if timeout 1800 docker build "${build_args[@]}" "${VNEXT_ROOT}"; then
  :
else
  exit_code=$?
  if [[ "${exit_code}" -eq 124 ]]; then
    echo "error: docker build timed out after 1800s" >&2
  fi
  exit "${exit_code}"
fi
echo "==> built ${IMAGE_TAG}"
