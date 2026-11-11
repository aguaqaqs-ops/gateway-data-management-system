#!/usr/bin/env bash
# Backend validation of the frontend Source Package output (kickoff §7.1, Q17/Q18).
# The entry constraints follow the "生成入口" rules (kickoff §7.1): committed script,
# dependency image, network none, read-only source, preflight against the image record,
# empty output directory, log outside the worktree, image identity from docker save.
set -Eeuo pipefail

FRONTEND_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd -P)"
ROOT="$(cd -- "$(git -C "$FRONTEND_DIR" rev-parse --show-toplevel)" && pwd -P)"
FE_IMAGE="${GATEWAY_FE_PACKAGE_IMAGE:-mcr.microsoft.com/playwright:v1.64.1-noble}"
BACKEND_IMAGE="${GATEWAY_BACKEND_DEPS_IMAGE:-}"
if [[ -z "$BACKEND_IMAGE" ]]; then
  BACKEND_IMAGE="$(python3 -I - "$ROOT" <<'PY'
import json, subprocess, sys
root = sys.argv[1]
out = subprocess.run([f"{root}/vnext/scripts/build-backend-dependency-base.sh", "--print-input"], check=True, capture_output=True, text=True).stdout
print(json.loads(out)["image"])
PY
)"
fi
VALIDATE_TAG=""
VALIDATE_BUILT=0
OUT=""
LOG_DIR=""
LOG_FILE=""
IDENTITY_ARCHIVES=()
RUN_STAGE="argument-validation"

usage() {
  cat <<'USAGE'
usage: frontend/scripts/validate-upload-package.sh --output <empty-absolute-directory> --log-dir <absolute-directory>
USAGE
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --output)
      [[ -z "$OUT" && $# -ge 2 ]] || { usage >&2; exit 2; }
      OUT="$2"; shift 2 ;;
    --log-dir)
      [[ -z "$LOG_DIR" && $# -ge 2 ]] || { usage >&2; exit 2; }
      LOG_DIR="$2"; shift 2 ;;
    --help) usage; exit 0 ;;
    *) usage >&2; exit 2 ;;
  esac
done

[[ -n "$OUT" && -n "$LOG_DIR" ]] || { usage >&2; exit 2; }
[[ "$OUT" == /* && "$LOG_DIR" == /* ]] || { echo "output and log directories must be absolute paths" >&2; exit 2; }
OUT="$(realpath -m -- "$OUT")"
LOG_DIR="$(realpath -m -- "$LOG_DIR")"

path_in_repo() { [[ "$1" == "$ROOT" || "$1" == "$ROOT/"* ]]; }
if path_in_repo "$OUT" || path_in_repo "$LOG_DIR"; then
  echo "validation output and logs must be outside the worktree" >&2
  exit 2
fi
if [[ "$LOG_DIR" == "$OUT" || "$LOG_DIR" == "$OUT/"* ]]; then
  echo "log directory must not be inside the output directory" >&2
  exit 2
fi

mkdir -p -- "$LOG_DIR"
STARTED_AT="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
HEAD_START="$(git -C "$ROOT" rev-parse HEAD)"
SHORT_HEAD="${HEAD_START:0:10}"
LOG_FILE="$LOG_DIR/upload-validator-${SHORT_HEAD}-$(date -u +%Y%m%dT%H%M%SZ)-$$.log"
[[ ! -e "$LOG_FILE" ]] || { echo "refusing to overwrite log: $LOG_FILE" >&2; exit 2; }
: > "$LOG_FILE"

finish() {
  local exit_code=$?
  trap - EXIT
  local ended_at head_end frontend_tree_end vnext_tree_end host_end archive
  ended_at="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  head_end="$(git -C "$ROOT" rev-parse HEAD 2>/dev/null || true)"
  frontend_tree_end="$(git -C "$ROOT" rev-parse HEAD:frontend 2>/dev/null || true)"
  vnext_tree_end="$(git -C "$ROOT" rev-parse HEAD:vnext 2>/dev/null || true)"
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
  for archive in "${IDENTITY_ARCHIVES[@]:-}"; do [[ -n "$archive" ]] && rm -f -- "$archive"; done
  if [[ "$VALIDATE_BUILT" == "1" && -n "$VALIDATE_TAG" ]]; then
    docker rmi "$VALIDATE_TAG" >> "$LOG_FILE" 2>&1 || true
  fi
  sha256sum "$LOG_FILE" > "$LOG_FILE.sha256" 2>/dev/null || true
  printf 'log_file=%s\n' "$LOG_FILE"
  cat "$LOG_FILE.sha256" 2>/dev/null || true
  exit "$exit_code"
}
trap finish EXIT

log() { printf '%s\n' "$*" | tee -a "$LOG_FILE"; }
trap 'status=$?; log "exit_code=$status"; exit "$status"' EXIT
path_is_empty() { [[ -d "$1" ]] && [[ -z "$(find "$1" -mindepth 1 -maxdepth 1 -print -quit)" ]]; }

RUN_STAGE="preconditions"
HOSTNAME_START="$(hostname -f 2>/dev/null || hostname)"
{
  printf 'hostname=%s\n' "$HOSTNAME_START"
  printf 'started_at=%s\n' "$STARTED_AT"
  printf 'head_start=%s\n' "$HEAD_START"
  printf 'frontend_tree_start=%s\n' "$(git -C "$ROOT" rev-parse HEAD:frontend)"
  printf 'vnext_tree_start=%s\n' "$(git -C "$ROOT" rev-parse HEAD:vnext)"
  printf 'toolchain_image=%s\n' "$FE_IMAGE"
  printf 'dependency_image=%s\n' "$BACKEND_IMAGE"
  printf 'docker_network=none\n'
  printf 'output=%s\n' "$OUT"
} | tee -a "$LOG_FILE"

if [[ -n "$(git -C "$ROOT" status --porcelain=v1 --untracked-files=all)" ]]; then
  log "error=source worktree is not clean"
  exit 2
fi
command -v docker >/dev/null 2>&1 || { log "error=docker is unavailable"; exit 2; }
command -v python3 >/dev/null 2>&1 || { log "error=python3 is unavailable for image identity parsing"; exit 2; }
for image in "$FE_IMAGE" "$BACKEND_IMAGE"; do
  docker image inspect "$image" >/dev/null 2>&1 || { log "error=image is not loaded locally: $image"; exit 2; }
done

if [[ -e "$OUT" && ! -d "$OUT" ]]; then
  log "error=output path exists and is not a directory: $OUT"
  exit 2
fi
mkdir -p -- "$OUT"
if ! path_is_empty "$OUT"; then
  log "error=output directory must be empty before validation: $OUT"
  exit 2
fi
chmod 0777 "$OUT"

RUN_STAGE="input-sha256"
for input in \
  vnext/backend/pyproject.toml \
  vnext/backend/uv.lock \
  vnext/backend/.python-version \
  vnext/backend/Dockerfile \
  vnext/rust/Cargo.lock \
  vnext/rust/rust-toolchain.toml \
  frontend/scripts/build-upload-validation-fixtures.mjs \
  frontend/scripts/validate_upload_package.py \
  frontend/scripts/validate-upload-package.sh \
  frontend/scripts/docker-save-image-identity.py \
  frontend/src/features/workbench/upload-package.ts; do
  [[ -f "$ROOT/$input" ]] || { log "error=required input is missing: $input"; exit 2; }
  log "input_sha256 $input $(sha256sum "$ROOT/$input" | awk '{print $1}')"
done

RUN_STAGE="dependency-input-preflight"
if docker run --rm --network none \
  --volume "$ROOT:/source:ro" \
  --workdir /source \
  "$BACKEND_IMAGE" /build/backend/.venv/bin/python -c '
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
record_only = {"backend/pyproject.toml", "rust/Cargo.lock"}
required_mismatches = []
record_mismatches = []
for name, path in paths.items():
    actual = hashlib.sha256(path.read_bytes()).hexdigest()
    print(f"image_input {name} expected={expected[name]} candidate={actual}")
    if actual != expected[name]:
        if name in required:
            required_mismatches.append(name)
        elif name in record_only:
            record_mismatches.append(name)
if required_mismatches:
    print("required_input_mismatch=" + ",".join(required_mismatches))
    sys.exit(2)
print("required_inputs_match=true")
print("record_only_mismatches=" + (",".join(record_mismatches) if record_mismatches else "none"))
' 2>&1 | tee -a "$LOG_FILE"; then
  log "dependency_input_preflight_exit_code=0"
else
  preflight_exit=$?
  log "dependency_input_preflight_exit_code=$preflight_exit"
  exit "$preflight_exit"
fi

RUN_STAGE="validator-image-build"
VALIDATE_TAG="gateway-backend-validate:fe-${HEAD_START:0:10}"
PRINT_INPUT_JSON="$("$ROOT/vnext/scripts/build-backend-dependency-base.sh" --print-input 2>/dev/null)"
PRINT_INPUT_TAG="$(python3 -I -c 'import json,sys; print(json.loads(sys.argv[1])["image"])' "$PRINT_INPUT_JSON")"
if [[ "$PRINT_INPUT_TAG" != "$BACKEND_IMAGE" ]]; then
  log "error=dependency image tag does not match --print-input for this HEAD"
  exit 2
fi
log "validator_image_tag=$VALIDATE_TAG"
if docker image inspect "$VALIDATE_TAG" >/dev/null 2>&1; then
  log "error=validator tag already exists, refusing to reuse: $VALIDATE_TAG"
  exit 2
fi
if ! docker build --network=none \
  -f "$ROOT/vnext/backend/Dockerfile" \
  --build-arg "DEPENDENCY_BASE_IMAGE=$BACKEND_IMAGE" \
  --build-arg "USE_PRELOADED_DEPENDENCIES=1" \
  -t "$VALIDATE_TAG" "$ROOT/vnext" 2>&1 | tee -a "$LOG_FILE"; then
  log "error=validator backend image build failed (cache miss or network needed, stop)"
  exit 2
fi
VALIDATE_BUILT=1
log "validator_image_built=$VALIDATE_TAG"

RUN_STAGE="image-identity"
for pair in "toolchain:$FE_IMAGE" "dependency:$BACKEND_IMAGE" "validator:$VALIDATE_TAG"; do
  label="${pair%%:*}"
  image="${pair#*:}"
  archive="$(mktemp "$LOG_DIR/.identity-${label}.XXXXXX.tar")"
  IDENTITY_ARCHIVES+=("$archive")
  docker image save --output "$archive" "$image" 2>&1 | tee -a "$LOG_FILE"
  identity_json="$(python3 "$FRONTEND_DIR/scripts/docker-save-image-identity.py" "$archive")"
  config_digest="$(python3 -c 'import json,sys; print(json.loads(sys.argv[1])["config_digest"])' "$identity_json")"
  diff_ids="$(python3 -c 'import json,sys; print(json.dumps(json.loads(sys.argv[1])["diff_ids"],separators=(",",":")))' "$identity_json")"
  log "${label}_image_config_digest=$config_digest"
  log "${label}_image_rootfs_diff_ids=$diff_ids"
done

RUN_STAGE="package-frontend"
docker run --rm --network none \
  -v "$ROOT/frontend:/src:ro" -v "$OUT:/out" -w /src \
  "$FE_IMAGE" node scripts/build-upload-validation-fixtures.mjs /out 2>&1 | tee -a "$LOG_FILE"

RUN_STAGE="validate-backend"
docker run --rm --network none \
  -v "$ROOT:/src:ro" -v "$OUT:/out:ro" -w /src \
  -e PYTHONPATH=/src/vnext/backend/src:/src/vnext/shared_kernel/src:/src/vnext/repository_contracts/src:/src/vnext/repository_client/src \
  "$VALIDATE_TAG" /app/backend/.venv/bin/python frontend/scripts/validate_upload_package.py /out 2>&1 | tee -a "$LOG_FILE"

RUN_STAGE="package-sha256"
sha256sum "$OUT"/*.tar.gz | tee -a "$LOG_FILE"
RUN_STAGE="done"
