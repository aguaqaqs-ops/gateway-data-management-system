#!/usr/bin/env bash
set -euo pipefail

FRONTEND_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
REPO_DIR="$(git -C "$FRONTEND_DIR" rev-parse --show-toplevel)"
LOG_DIR="${GATEWAY_FE_LOG_DIR:-/home/dev/gdds-fe-logs/fe0}"
NPM_CACHE_DIR="${GATEWAY_FRONTEND_NPM_CACHE:-/home/dev/gdds-fe-cache/fe0/npm-cache}"
TOOLCHAIN_IMAGE="mcr.microsoft.com/playwright:v1.64.1-noble"
DOCKER_NETWORK="${GATEWAY_FRONTEND_DOCKER_NETWORK:-none}"
BACKEND_ORIGIN="${GATEWAY_FRONTEND_BACKEND_ORIGIN:-http://127.0.0.1:8000}"
RUN_E2E=0

if [[ $# -gt 1 || ( $# -eq 1 && "$1" != "--e2e" ) ]]; then
  echo "usage: $0 [--e2e]" >&2
  exit 2
fi
if [[ $# -eq 1 ]]; then
  RUN_E2E=1
fi

if ! command -v docker >/dev/null 2>&1; then
  echo "Docker is required; Node.js is provided by the fixed Playwright image." >&2
  exit 2
fi
if [[ ! -d "$NPM_CACHE_DIR" ]] || [[ -z "$(find "$NPM_CACHE_DIR" -mindepth 1 -maxdepth 1 -print -quit)" ]]; then
  echo "npm cache is missing or empty: $NPM_CACHE_DIR" >&2
  exit 2
fi
if ! docker image inspect "$TOOLCHAIN_IMAGE" >/dev/null 2>&1; then
  echo "toolchain image is not loaded locally: $TOOLCHAIN_IMAGE" >&2
  exit 2
fi
if [[ -n "$(git -C "$REPO_DIR" status --porcelain --untracked-files=all)" ]]; then
  echo "tests require a clean, committed worktree: $REPO_DIR" >&2
  exit 2
fi

mkdir -p "$LOG_DIR"
LOG_FILE="$LOG_DIR/frontend-tests-$(date -u +%Y%m%dT%H%M%SZ).log"
STARTED_AT="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
HEAD_START="$(git -C "$REPO_DIR" rev-parse HEAD)"
HOSTNAME_START="$(hostname -f)"

{
  printf 'hostname=%s\n' "$HOSTNAME_START"
  printf 'started_at=%s\n' "$STARTED_AT"
  printf 'head_start=%s\n' "$HEAD_START"
  printf 'toolchain_image=%s\n' "$TOOLCHAIN_IMAGE"
  printf 'docker_network=%s\n' "$DOCKER_NETWORK"
  printf 'npm_cache=%s\n' "$NPM_CACHE_DIR"
  printf 'run_e2e=%s\n' "$RUN_E2E"
} | tee "$LOG_FILE"

set +e
docker run --rm --init --ipc=host --network "$DOCKER_NETWORK" \
  --volume "$FRONTEND_DIR:/source:ro" \
  --volume "$NPM_CACHE_DIR:/npm-cache:ro" \
  --env "GATEWAY_FRONTEND_BACKEND_ORIGIN=$BACKEND_ORIGIN" \
  --env "GATEWAY_FE_RUN_E2E=$RUN_E2E" \
  "$TOOLCHAIN_IMAGE" bash -euo pipefail -c '
    mkdir -p /tmp/frontend /tmp/npm-cache
    cp -a /source/. /tmp/frontend/
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
HOSTNAME_END="$(hostname -f)"
{
  printf 'hostname_end=%s\n' "$HOSTNAME_END"
  printf 'ended_at=%s\n' "$ENDED_AT"
  printf 'head_end=%s\n' "$HEAD_END"
  printf 'exit_code=%s\n' "$RUN_EXIT_CODE"
} | tee -a "$LOG_FILE"
sha256sum "$LOG_FILE" | tee "$LOG_FILE.sha256"
exit "$RUN_EXIT_CODE"
