#!/usr/bin/env bash
set -Eeuo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
FRONTEND_DIR="$(cd -- "$SCRIPT_DIR/.." && pwd -P)"
REPO_DIR="$(cd -- "$(git -C "$FRONTEND_DIR" rev-parse --show-toplevel)" && pwd -P)"
IMAGE="gateway-backend-deps:lock-d054366c02fa"
OUTPUT_ONE=""
OUTPUT_TWO=""
LOG_DIR=""
LOG_FILE=""
IDENTITY_ARCHIVE=""
RUN_STAGE="argument-validation"

usage() {
  cat <<'USAGE'
usage: frontend/scripts/generate-backend-bundle-fixtures.sh \
  --output-one <empty-absolute-directory> \
  --output-two <empty-absolute-directory> \
  --log-dir <absolute-directory>
USAGE
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --output-one)
      [[ -z "$OUTPUT_ONE" && $# -ge 2 ]] || { usage >&2; exit 2; }
      OUTPUT_ONE="$2"
      shift 2
      ;;
    --output-two)
      [[ -z "$OUTPUT_TWO" && $# -ge 2 ]] || { usage >&2; exit 2; }
      OUTPUT_TWO="$2"
      shift 2
      ;;
    --log-dir)
      [[ -z "$LOG_DIR" && $# -ge 2 ]] || { usage >&2; exit 2; }
      LOG_DIR="$2"
      shift 2
      ;;
    --help)
      usage
      exit 0
      ;;
    *)
      usage >&2
      exit 2
      ;;
  esac
done

[[ -n "$OUTPUT_ONE" && -n "$OUTPUT_TWO" && -n "$LOG_DIR" ]] || { usage >&2; exit 2; }
[[ "$OUTPUT_ONE" == /* && "$OUTPUT_TWO" == /* && "$LOG_DIR" == /* ]] || {
  echo "output directories and log directory must be absolute paths" >&2
  exit 2
}

OUTPUT_ONE="$(realpath -m -- "$OUTPUT_ONE")"
OUTPUT_TWO="$(realpath -m -- "$OUTPUT_TWO")"
LOG_DIR="$(realpath -m -- "$LOG_DIR")"

path_in_repo() {
  [[ "$1" == "$REPO_DIR" || "$1" == "$REPO_DIR/"* ]]
}

if path_in_repo "$OUTPUT_ONE" || path_in_repo "$OUTPUT_TWO" || path_in_repo "$LOG_DIR"; then
  echo "fixture outputs and logs must be outside the worktree" >&2
  exit 2
fi
if [[ "$OUTPUT_ONE" == "$OUTPUT_TWO" || "$OUTPUT_ONE" == "$OUTPUT_TWO/"* || "$OUTPUT_TWO" == "$OUTPUT_ONE/"* ]]; then
  echo "fixture output directories must be distinct and must not contain one another" >&2
  exit 2
fi
if [[ "$LOG_DIR" == "$OUTPUT_ONE" || "$LOG_DIR" == "$OUTPUT_ONE/"* || "$LOG_DIR" == "$OUTPUT_TWO" || "$LOG_DIR" == "$OUTPUT_TWO/"* ]]; then
  echo "log directory must not be inside either fixture output directory" >&2
  exit 2
fi

mkdir -p -- "$LOG_DIR" "$OUTPUT_ONE" "$OUTPUT_TWO"
STARTED_AT="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
HEAD_START="$(git -C "$REPO_DIR" rev-parse HEAD)"
SHORT_HEAD="${HEAD_START:0:10}"
LOG_FILE="$LOG_DIR/backend-fixtures-${SHORT_HEAD}-$(date -u +%Y%m%dT%H%M%SZ)-$$.log"
if [[ -e "$LOG_FILE" ]]; then
  echo "refusing to overwrite log: $LOG_FILE" >&2
  exit 2
fi
: > "$LOG_FILE"

finish() {
  local exit_code=$?
  trap - EXIT
  local ended_at head_end frontend_tree_end vnext_tree_end host_end
  ended_at="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  head_end="$(git -C "$REPO_DIR" rev-parse HEAD 2>/dev/null || true)"
  frontend_tree_end="$(git -C "$REPO_DIR" rev-parse HEAD:frontend 2>/dev/null || true)"
  vnext_tree_end="$(git -C "$REPO_DIR" rev-parse HEAD:vnext 2>/dev/null || true)"
  host_end="$(hostname -f 2>/dev/null || hostname)"
  {
    printf 'ended_at=%s\n' "$ended_at"
    printf 'hostname_end=%s\n' "$host_end"
    printf 'head_end=%s\n' "$head_end"
    printf 'frontend_tree_end=%s\n' "$frontend_tree_end"
    printf 'vnext_tree_end=%s\n' "$vnext_tree_end"
    printf 'final_stage=%s\n' "$RUN_STAGE"
    printf 'exit_code=%s\n' "$exit_code"
  } >> "$LOG_FILE" 2>/dev/null || true
  if [[ -n "$IDENTITY_ARCHIVE" ]]; then rm -f -- "$IDENTITY_ARCHIVE"; fi
  sha256sum "$LOG_FILE" > "$LOG_FILE.sha256" 2>/dev/null || true
  printf 'log_file=%s\n' "$LOG_FILE"
  if [[ -f "$LOG_FILE.sha256" ]]; then cat "$LOG_FILE.sha256"; fi
  exit "$exit_code"
}
trap finish EXIT

log() {
  printf '%s\n' "$*" | tee -a "$LOG_FILE"
}

path_is_empty() {
  [[ -d "$1" ]] && [[ -z "$(find "$1" -mindepth 1 -maxdepth 1 -print -quit)" ]]
}

RUN_STAGE="preconditions"
HOSTNAME_START="$(hostname -f 2>/dev/null || hostname)"
FRONTEND_TREE_START="$(git -C "$REPO_DIR" rev-parse HEAD:frontend)"
VNEXT_TREE_START="$(git -C "$REPO_DIR" rev-parse HEAD:vnext)"
{
  printf 'hostname=%s\n' "$HOSTNAME_START"
  printf 'started_at=%s\n' "$STARTED_AT"
  printf 'head_start=%s\n' "$HEAD_START"
  printf 'frontend_tree_start=%s\n' "$FRONTEND_TREE_START"
  printf 'vnext_tree_start=%s\n' "$VNEXT_TREE_START"
  printf 'dependency_image=%s\n' "$IMAGE"
  printf 'docker_network=none\n'
  printf 'output_one=%s\n' "$OUTPUT_ONE"
  printf 'output_two=%s\n' "$OUTPUT_TWO"
} | tee -a "$LOG_FILE"

if [[ -n "$(git -C "$REPO_DIR" status --porcelain=v1 --untracked-files=all)" ]]; then
  log "error=source worktree is not clean"
  exit 2
fi
if ! path_is_empty "$OUTPUT_ONE" || ! path_is_empty "$OUTPUT_TWO"; then
  log "error=both fixture output directories must be empty before generation"
  exit 2
fi
command -v docker >/dev/null 2>&1 || { log "error=docker is unavailable"; exit 2; }
command -v python3 >/dev/null 2>&1 || { log "error=python3 is unavailable for image identity parsing"; exit 2; }
[[ -f "$FRONTEND_DIR/scripts/generate-backend-bundle-fixture.py" ]] || {
  log "error=backend fixture generator is missing"
  exit 2
}

RUN_STAGE="input-sha256"
for input in \
  vnext/backend/pyproject.toml \
  vnext/backend/uv.lock \
  vnext/backend/.python-version \
  vnext/rust/Cargo.lock \
  vnext/rust/rust-toolchain.toml \
  frontend/scripts/generate-backend-bundle-fixture.py \
  frontend/scripts/docker-save-image-identity.py \
  frontend/src/test/fixtures/source/business-navigation.json \
  frontend/src/test/fixtures/source/navigation-diagnostics.json \
  frontend/src/test/fixtures/source/business-navigation-workbench.json; do
  [[ -f "$REPO_DIR/$input" ]] || { log "error=required input is missing: $input"; exit 2; }
  log "input_sha256 $input $(sha256sum "$REPO_DIR/$input" | awk '{print $1}')"
done

RUN_STAGE="clean-worktree-check"
if ! docker image inspect "$IMAGE" >/dev/null 2>&1; then
  log "error=dependency image is not loaded locally: $IMAGE"
  exit 2
fi
IDENTITY_ARCHIVE="$(mktemp "${TMPDIR:-/tmp}/gateway-fe-backend-deps.XXXXXX.tar")"
RUN_STAGE="image-identity"
docker image save --output "$IDENTITY_ARCHIVE" "$IMAGE" 2>&1 | tee -a "$LOG_FILE"
IDENTITY_JSON="$(python3 "$FRONTEND_DIR/scripts/docker-save-image-identity.py" "$IDENTITY_ARCHIVE")"
IMAGE_CONFIG_DIGEST="$(python3 -c 'import json,sys; print(json.loads(sys.argv[1])["config_digest"])' "$IDENTITY_JSON")"
IMAGE_ROOTFS_DIFF_IDS="$(python3 -c 'import json,sys; print(json.dumps(json.loads(sys.argv[1])["diff_ids"],separators=(",",":")))' "$IDENTITY_JSON")"
log "dependency_image_config_digest=$IMAGE_CONFIG_DIGEST"
log "dependency_image_rootfs_diff_ids=$IMAGE_ROOTFS_DIFF_IDS"

SOURCE_PYTHONPATH="/source/vnext/backend/src:/source/vnext/repository_contracts/src:/source/vnext/shared_kernel/src:/source/vnext/repository_service/src:/source/vnext/rust/gateway-compute-python-impl/src:/source/vnext/rust/gateway-compute-python/src:/source/vnext/rust/gateway-architecture-check/src:/source/vnext/rust/gateway-shared-kernel/src:/source/vnext/rust/gateway-compute-core/src:/source/vnext/repository_client/src"
log "backend_source_pythonpath=$SOURCE_PYTHONPATH"

RUN_STAGE="dependency-input-preflight"
if docker run --rm --network none \
  --volume "$REPO_DIR:/source:ro" \
  --workdir /source \
  "$IMAGE" /build/backend/.venv/bin/python -c '
import hashlib
import json
import sys
from pathlib import Path

inputs = json.loads(Path("/usr/local/share/gateway-backend-dependency-base/inputs.json").read_bytes())
expected = inputs["tag_inputs"]["files"]
paths = {
    "backend/pyproject.toml": Path("/source/vnext/backend/pyproject.toml"),
    "backend/uv.lock": Path("/source/vnext/backend/uv.lock"),
    "backend/.python-version": Path("/source/vnext/backend/.python-version"),
    "rust/Cargo.lock": Path("/source/vnext/rust/Cargo.lock"),
    "rust/rust-toolchain.toml": Path("/source/vnext/rust/rust-toolchain.toml"),
}
required = {"backend/uv.lock", "backend/.python-version"}
mismatches = []
for name, path in paths.items():
    actual = hashlib.sha256(path.read_bytes()).hexdigest()
    print(f"image_input {name} expected={expected[name]} candidate={actual}")
    if name in required and actual != expected[name]:
        mismatches.append(name)
if mismatches:
    print("required_input_mismatch=" + ",".join(mismatches))
    sys.exit(2)
print("required_inputs_match=true")
print("record_only_mismatches=backend/pyproject.toml,rust/Cargo.lock")
' 2>&1 | tee -a "$LOG_FILE"; then
  log "dependency_input_preflight_exit_code=0"
else
  exit_code=$?
  log "dependency_input_preflight_exit_code=$exit_code"
  exit "$exit_code"
fi

run_generator() {
  local run_number="$1"
  local output_dir="$2"
  RUN_STAGE="generate_run_${run_number}"
  log "generation_run=${run_number} started_at=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  if docker run --rm --network none \
    --volume "$REPO_DIR:/source:ro" \
    --volume "$output_dir:/output" \
    --workdir /source \
    --env "PYTHONPATH=$SOURCE_PYTHONPATH" \
    "$IMAGE" /build/backend/.venv/bin/python \
    /source/frontend/scripts/generate-backend-bundle-fixture.py \
    --output-root /output \
    --navigation /source/frontend/src/test/fixtures/source/business-navigation.json \
    --navigation-diagnostics /source/frontend/src/test/fixtures/source/navigation-diagnostics.json \
    --workbench-navigation /source/frontend/src/test/fixtures/source/business-navigation-workbench.json \
    2>&1 | tee -a "$LOG_FILE"; then
    log "generation_run_${run_number}_exit_code=0"
  else
    local exit_code=$?
    log "generation_run_${run_number}_exit_code=$exit_code"
    exit "$exit_code"
  fi
  local file_count tree_digest
  file_count="$(find "$output_dir" -type f | wc -l | tr -d ' ')"
  tree_digest="$(cd "$output_dir" && find . -type f -print0 | sort -z | xargs -0 sha256sum | sha256sum | awk '{print $1}')"
  log "generation_run_${run_number}_file_count=$file_count"
  log "generation_run_${run_number}_tree_sha256=$tree_digest"
}

run_generator 1 "$OUTPUT_ONE"
run_generator 2 "$OUTPUT_TWO"

RUN_STAGE="byte-for-byte-comparison"
log "comparison_started_at=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
if diff -qr -- "$OUTPUT_ONE" "$OUTPUT_TWO" 2>&1 | tee -a "$LOG_FILE"; then
  log "byte_identical=true"
else
  exit_code=$?
  log "byte_identical=false"
  log "comparison_exit_code=$exit_code"
  exit "$exit_code"
fi
