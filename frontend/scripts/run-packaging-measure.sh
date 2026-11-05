#!/usr/bin/env bash
# FE3a M1: packaging peak-memory measurement (frontend kickoff §8.4).
#
# Runs the M1 probe (scripts/measure-packaging-memory.mjs) inside the fixed
# toolchain container against the production build, with the source
# directory read-only mounted. No backend needed; no occupancy marker.
#
# Usage:
#   frontend/scripts/run-packaging-measure.sh \
#     --input-root <absolute-dir> --mode modified|full \
#     --runs <n> --report <absolute-json> --log-dir <absolute-dir>
#
# Environment (same variables as run-tests.sh):
#   GATEWAY_FRONTEND_NPM_CACHE / _ARCHIVE / _SOURCE_COMMIT
set -Eeuo pipefail

FRONTEND_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd -P)"
REPO_DIR="$(git -C "$FRONTEND_DIR" rev-parse --show-toplevel)"
NPM_CACHE_DIR="${GATEWAY_FRONTEND_NPM_CACHE:-/home/dev/gdds-fe-cache/frontend/npm-cache}"
NPM_CACHE_ARCHIVE="${GATEWAY_FRONTEND_NPM_CACHE_ARCHIVE:-/home/dev/gdds-fe-cache/frontend/npm-cacache.tar.gz}"
NPM_CACHE_SOURCE_COMMIT="${GATEWAY_FRONTEND_NPM_CACHE_SOURCE_COMMIT:-unknown}"
TOOLCHAIN_IMAGE="mcr.microsoft.com/playwright:v1.64.1-noble"

INPUT_ROOT=""
MODE=""
RUNS="3"
REPORT=""
LOG_DIR=""
LOG_FILE=""

usage() {
  cat <<'USAGE'
usage: frontend/scripts/run-packaging-measure.sh --input-root <absolute-dir> --mode modified|full --runs <n> --report <absolute-json> --log-dir <absolute-dir>
USAGE
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --input-root) [[ -z "$INPUT_ROOT" && $# -ge 2 ]] || { usage >&2; exit 2; }; INPUT_ROOT="$2"; shift 2 ;;
    --mode) [[ -z "$MODE" && $# -ge 2 ]] || { usage >&2; exit 2; }; MODE="$2"; shift 2 ;;
    --runs) [[ $# -ge 2 ]] || { usage >&2; exit 2; }; RUNS="$2"; shift 2 ;;
    --log-dir) [[ -z "$LOG_DIR" && $# -ge 2 ]] || { usage >&2; exit 2; }; LOG_DIR="$2"; shift 2 ;;
    --help) usage; exit 0 ;;
    *) usage >&2; exit 2 ;;
  esac
done

[[ -n "$INPUT_ROOT" && -n "$MODE" && -n "$REPORT" && -n "$LOG_DIR" ]] || { usage >&2; exit 2; }
[[ "$INPUT_ROOT" == /* && "$REPORT" == /* && "$LOG_DIR" == /* ]] || { echo "paths must be absolute" >&2; exit 2; }
[[ "$MODE" == "modified" || "$MODE" == "full" ]] || { echo "mode must be modified|full" >&2; exit 2; }
INPUT_ROOT="$(realpath -m -- "$INPUT_ROOT")"
REPORT="$(realpath -m -- "$REPORT")"
LOG_DIR="$(realpath -m -- "$LOG_DIR")"
[[ -d "$INPUT_ROOT" ]] || { echo "input root is not a directory: $INPUT_ROOT" >&2; exit 2; }

path_in_repo() { [[ "$1" == "$REPO_DIR" || "$1" == "$REPO_DIR/"* ]]; }
if path_in_repo "$REPORT" || path_in_repo "$LOG_DIR"; then
  echo "report and logs must be outside the worktree" >&2
  exit 2
fi

# The toolchain container runs as root: mount the source read-only.
mkdir -p -- "$LOG_DIR" "$(dirname -- "$REPORT")"
STARTED_AT="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
HEAD_START="$(git -C "$REPO_DIR" rev-parse HEAD)"
LOG_FILE="$LOG_DIR/packaging-measure-$(git -C "$REPO_DIR" rev-parse --short HEAD)-$(date -u +%Y%m%dT%H%M%SZ)-$$.log"
[[ ! -e "$LOG_FILE" ]] || { echo "refusing to overwrite log: $LOG_FILE" >&2; exit 2; }
: > "$LOG_FILE"

SOURCE_ARCHIVE="$(mktemp "${TMPDIR:-/tmp}/gateway-frontend-source.XXXXXX.tar")"
cleanup() { rm -f -- "$SOURCE_ARCHIVE"; }
trap cleanup EXIT

finish() {
  local exit_code=$?
  trap - EXIT
  {
    printf 'ended_at=%s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
    printf 'hostname_end=%s\n' "$(hostname -f 2>/dev/null || hostname)"
    printf 'head_end=%s\n' "$(git -C "$REPO_DIR" rev-parse HEAD 2>/dev/null || true)"
    printf 'exit_code=%s\n' "$exit_code"
  } >> "$LOG_FILE" 2>/dev/null || true
  rm -f -- "$SOURCE_ARCHIVE"
  sha256sum "$LOG_FILE" > "$LOG_FILE.sha256" 2>/dev/null || true
  printf 'log_file=%s\n' "$LOG_FILE"
  cat "$LOG_FILE.sha256" 2>/dev/null || true
  exit "$exit_code"
}
trap finish EXIT

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
if [[ -n "$(git -C "$REPO_DIR" status --porcelain=v1 --untracked-files=all)" ]]; then
  echo "tests require a clean, committed worktree: $REPO_DIR" >&2
  exit 2
fi
if ! git -C "$REPO_DIR" archive --format=tar HEAD frontend > "$SOURCE_ARCHIVE"; then
  echo "could not archive tracked frontend files from HEAD" >&2
  exit 2
fi

REPORT_DIR="$(dirname -- "$REPORT")"
{
  printf 'hostname=%s\n' "$(hostname -f 2>/dev/null || hostname)"
  printf 'started_at=%s\n' "$STARTED_AT"
  printf 'head_start=%s\n' "$HEAD_START"
  printf 'frontend_tree_start=%s\n' "$(git -C "$REPO_DIR" rev-parse HEAD:frontend)"
  printf 'toolchain_image=%s\n' "$TOOLCHAIN_IMAGE"
  printf 'npm_cache=%s\n' "$NPM_CACHE_DIR"
  printf 'npm_cache_source_archive=%s\n' "$NPM_CACHE_ARCHIVE"
  printf 'npm_cache_source_archive_sha256=%s\n' "$(sha256sum "$NPM_CACHE_ARCHIVE" | awk '{print $1}')"
  printf 'npm_cache_source_commit=%s\n' "$NPM_CACHE_SOURCE_COMMIT"
  printf 'input_root=%s\n' "$INPUT_ROOT"
  printf 'mode=%s\n' "$MODE"
  printf 'runs=%s\n' "$RUNS"
  printf 'report=%s\n' "$REPORT"
} | tee "$LOG_FILE"

set +e
docker run --rm --init --ipc=host --network none \
  --volume "$SOURCE_ARCHIVE:/frontend-source.tar:ro" \
  --volume "$NPM_CACHE_DIR:/npm-cache:ro" \
  --volume "$INPUT_ROOT:/input:ro" \
  --volume "$REPORT_DIR:/report" \
  "$TOOLCHAIN_IMAGE" bash -euo pipefail -c '
    mkdir -p /tmp/frontend /tmp/npm-cache
    tar -xf /frontend-source.tar --strip-components=1 -C /tmp/frontend
    cp -a /npm-cache/. /tmp/npm-cache/
    cd /tmp/frontend
    npm ci --offline --cache /tmp/npm-cache --no-audit --no-fund
    npm run build
    node scripts/measure-packaging-memory.mjs --input-root /input --mode "'"$MODE"'" --runs "'"$RUNS"'" --output /report/'"$(basename -- "$REPORT")"'
  ' 2>&1 | tee -a "$LOG_FILE"
RUN_EXIT_CODE=${PIPESTATUS[0]}
set -e
exit "$RUN_EXIT_CODE"
