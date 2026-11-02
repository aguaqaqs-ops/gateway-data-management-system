#!/usr/bin/env bash
set -euo pipefail

FRONTEND_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
REPO_DIR="$(git -C "$FRONTEND_DIR" rev-parse --show-toplevel)"
LOG_DIR="${GATEWAY_FE_LOG_DIR:-/home/dev/gdds-fe-logs/frontend}"
NPM_CACHE_DIR="${GATEWAY_FRONTEND_NPM_CACHE:-/home/dev/gdds-fe-cache/frontend/npm-cache}"
NPM_CACHE_ARCHIVE="${GATEWAY_FRONTEND_NPM_CACHE_ARCHIVE:-/home/dev/gdds-fe-cache/frontend/npm-cacache.tar.gz}"
NPM_CACHE_SOURCE_COMMIT="${GATEWAY_FRONTEND_NPM_CACHE_SOURCE_COMMIT:-unknown}"
TOOLCHAIN_IMAGE="mcr.microsoft.com/playwright:v1.64.1-noble"
DOCKER_NETWORK="${GATEWAY_FRONTEND_DOCKER_NETWORK:-none}"
BACKEND_ORIGIN="${GATEWAY_FRONTEND_BACKEND_ORIGIN:-http://127.0.0.1:8000}"
LOCK_FILE="$FRONTEND_DIR/package-lock.json"
EXPECTED_TOOLCHAIN_DIFF_IDS='["sha256:bec87777bc2fb2edcdf9af11df1531469e7df911309c1413082b18fcb8610278","sha256:1590c449306a9032a32c49afeac5e4c7cae86197c4a7dd95c095c3ae220a7f07","sha256:c8a795d9cdbc02d20daf1ecac5377667d61d63392fbe5bdbba94cc79a4cf3fe9","sha256:89e210c351d8ddaa3c7a6132e19a5aaf27ec837371dd94f0698dfa4c1e5aef3d","sha256:ea03ac3d8e487159afdc9d45b9a8d3f4035418655881b896cc34fa2e464c27fc","sha256:16f77d0178dafdf603cd05f8464e39df636665b2b028e18e0b95bfbee5ecacd5","sha256:d8597d6a5431eca9c1082ade19c2b7cdef69fbaaae43f0b67fbbd25f3a35c2bb"]'
RUN_E2E=0

if [[ $# -gt 1 || ( $# -eq 1 && "$1" != "--e2e" ) ]]; then
  echo "usage: $0 [--e2e]" >&2
  exit 2
fi
if [[ $# -eq 1 ]]; then
  RUN_E2E=1
fi

if [[ ! -f "$LOCK_FILE" ]]; then
  echo "package lockfile is missing: $LOCK_FILE" >&2
  exit 2
fi
mapfile -t RESOLVED_ENTRIES < <(grep -Eo '"resolved"[[:space:]]*:[[:space:]]*"[^"]+"' "$LOCK_FILE" || true)
if [[ ${#RESOLVED_ENTRIES[@]} -eq 0 ]]; then
  echo "package lockfile has no resolved package URLs: $LOCK_FILE" >&2
  exit 2
fi
for resolved_entry in "${RESOLVED_ENTRIES[@]}"; do
  if [[ "$resolved_entry" != '"resolved": "https://registry.npmjs.org/'* ]]; then
    echo "package lockfile contains a noncanonical resolved URL; use https://registry.npmjs.org/: $LOCK_FILE" >&2
    exit 2
  fi
done

if ! command -v docker >/dev/null 2>&1; then
  echo "Docker is required; Node.js is provided by the fixed Playwright image." >&2
  exit 2
fi
if [[ ! -d "$NPM_CACHE_DIR" ]] || [[ -z "$(find "$NPM_CACHE_DIR" -mindepth 1 -maxdepth 1 -print -quit)" ]]; then
  echo "npm cache is missing or empty: $NPM_CACHE_DIR" >&2
  exit 2
fi
if [[ ! -f "$NPM_CACHE_ARCHIVE" ]]; then
  echo "npm cache source archive is missing: $NPM_CACHE_ARCHIVE" >&2
  exit 2
fi
if ! docker image inspect "$TOOLCHAIN_IMAGE" >/dev/null 2>&1; then
  echo "toolchain image is not loaded locally: $TOOLCHAIN_IMAGE" >&2
  exit 2
fi
TOOLCHAIN_DIFF_IDS="$(docker image inspect --format '{{json .RootFS.Layers}}' "$TOOLCHAIN_IMAGE")"
if [[ "$TOOLCHAIN_DIFF_IDS" != "$EXPECTED_TOOLCHAIN_DIFF_IDS" ]]; then
  echo "toolchain image RootFS DiffIDs do not match the pinned image identity: $TOOLCHAIN_IMAGE" >&2
  exit 2
fi
if [[ -n "$(git -C "$REPO_DIR" status --porcelain --untracked-files=all)" ]]; then
  echo "tests require a clean, committed worktree: $REPO_DIR" >&2
  exit 2
fi

SOURCE_ARCHIVE="$(mktemp "${TMPDIR:-/tmp}/gateway-frontend-source.XXXXXX.tar")"
trap 'rm -f "$SOURCE_ARCHIVE"' EXIT
if ! git -C "$REPO_DIR" archive --format=tar HEAD frontend > "$SOURCE_ARCHIVE"; then
  echo "could not archive tracked frontend files from HEAD" >&2
  exit 2
fi

mkdir -p "$LOG_DIR"
LOG_FILE="$LOG_DIR/frontend-tests-$(date -u +%Y%m%dT%H%M%SZ).log"
STARTED_AT="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
HEAD_START="$(git -C "$REPO_DIR" rev-parse HEAD)"
FRONTEND_TREE_START="$(git -C "$REPO_DIR" rev-parse HEAD:frontend)"
HOSTNAME_START="$(hostname -f)"
NPM_CACHE_ARCHIVE_SHA256="$(sha256sum "$NPM_CACHE_ARCHIVE" | awk '{print $1}')"
SOURCE_ARCHIVE_SHA256="$(sha256sum "$SOURCE_ARCHIVE" | awk '{print $1}')"
RESOLVED_COUNT="${#RESOLVED_ENTRIES[@]}"

{
  printf 'hostname=%s\n' "$HOSTNAME_START"
  printf 'started_at=%s\n' "$STARTED_AT"
  printf 'head_start=%s\n' "$HEAD_START"
  printf 'frontend_tree_start=%s\n' "$FRONTEND_TREE_START"
  printf 'toolchain_image=%s\n' "$TOOLCHAIN_IMAGE"
  printf 'toolchain_rootfs_diff_ids=%s\n' "$TOOLCHAIN_DIFF_IDS"
  printf 'docker_network=%s\n' "$DOCKER_NETWORK"
  printf 'npm_cache=%s\n' "$NPM_CACHE_DIR"
  printf 'npm_cache_source_archive=%s\n' "$NPM_CACHE_ARCHIVE"
  printf 'npm_cache_source_archive_sha256=%s\n' "$NPM_CACHE_ARCHIVE_SHA256"
  printf 'npm_cache_source_commit=%s\n' "$NPM_CACHE_SOURCE_COMMIT"
  printf 'package_lock_resolved_count=%s\n' "$RESOLVED_COUNT"
  printf 'tracked_frontend_archive_sha256=%s\n' "$SOURCE_ARCHIVE_SHA256"
  printf 'run_e2e=%s\n' "$RUN_E2E"
} | tee "$LOG_FILE"

set +e
docker run --rm --init --ipc=host --network "$DOCKER_NETWORK" \
  --volume "$SOURCE_ARCHIVE:/frontend-source.tar:ro" \
  --volume "$NPM_CACHE_DIR:/npm-cache:ro" \
  --env "GATEWAY_FRONTEND_BACKEND_ORIGIN=$BACKEND_ORIGIN" \
  --env "GATEWAY_FE_RUN_E2E=$RUN_E2E" \
  "$TOOLCHAIN_IMAGE" bash -euo pipefail -c '
    mkdir -p /tmp/frontend /tmp/npm-cache
    tar -xf /frontend-source.tar --strip-components=1 -C /tmp/frontend
    cp -a /npm-cache/. /tmp/npm-cache/
    cd /tmp/frontend
    npm ci --offline --cache /tmp/npm-cache --no-audit --no-fund
    npm run typecheck
    npm run lint
    npm run test:unit
    npm run build
    if [[ "$GATEWAY_FE_RUN_E2E" == "1" ]]; then
      npm run test:e2e
    fi
  ' 2>&1 | tee -a "$LOG_FILE"
RUN_EXIT_CODE=${PIPESTATUS[0]}
set -e

ENDED_AT="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
HEAD_END="$(git -C "$REPO_DIR" rev-parse HEAD)"
FRONTEND_TREE_END="$(git -C "$REPO_DIR" rev-parse HEAD:frontend)"
HOSTNAME_END="$(hostname -f)"
{
  printf 'hostname_end=%s\n' "$HOSTNAME_END"
  printf 'ended_at=%s\n' "$ENDED_AT"
  printf 'head_end=%s\n' "$HEAD_END"
  printf 'frontend_tree_end=%s\n' "$FRONTEND_TREE_END"
  printf 'exit_code=%s\n' "$RUN_EXIT_CODE"
} | tee -a "$LOG_FILE"
sha256sum "$LOG_FILE" | tee "$LOG_FILE.sha256"
exit "$RUN_EXIT_CODE"
