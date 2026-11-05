#!/usr/bin/env bash
# FE3a real-backend e2e runner (frontend kickoff §4).
#
# Standalone script, NOT part of run-tests.sh (kickoff §4.1, owner Q4).
# Spins up the Compose backend stack on this node, seeds one repository per
# scope, verifies the running /openapi.json against the committed snapshot
# through the preview server, then runs the Playwright real-backend suite
# inside the toolchain container (production build, per-identity contexts).
#
# Usage:
#   frontend/scripts/run-real-backend-e2e.sh --suite smoke --session <name> \
#     --log-dir <absolute-dir> [--evidence-dir <absolute-dir>] \
#     [--subphase <name>]
#
# Only --suite smoke is implemented in FE3a; journeys/t1 belong to FE3b.
#
# Environment (same npm cache variables as run-tests.sh, kickoff §2.2):
#   GATEWAY_FRONTEND_NPM_CACHE / _ARCHIVE / _SOURCE_COMMIT
set -Eeuo pipefail

FRONTEND_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd -P)"
REPO_DIR="$(git -C "$FRONTEND_DIR" rev-parse --show-toplevel)"
NPM_CACHE_DIR="${GATEWAY_FRONTEND_NPM_CACHE:-/home/dev/gdds-fe-cache/frontend/npm-cache}"
NPM_CACHE_ARCHIVE="${GATEWAY_FRONTEND_NPM_CACHE_ARCHIVE:-/home/dev/gdds-fe-cache/frontend/npm-cacache.tar.gz}"
NPM_CACHE_SOURCE_COMMIT="${GATEWAY_FRONTEND_NPM_CACHE_SOURCE_COMMIT:-unknown}"
TOOLCHAIN_IMAGE="mcr.microsoft.com/playwright:v1.64.1-noble"

SUITE=""
SESSION=""
SUBPHASE="fe3a"
LOG_DIR=""
EVIDENCE_DIR=""
INPUT_ROOT=""
LOG_FILE=""
RUN_STAGE="argument-validation"

usage() {
  cat <<'USAGE'
usage: frontend/scripts/run-real-backend-e2e.sh --suite smoke --session <name> [--subphase <name>] [--input-root <dir>] --log-dir <absolute-dir> [--evidence-dir <absolute-dir>]
USAGE
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --suite) [[ -z "$SUITE" && $# -ge 2 ]] || { usage >&2; exit 2; }; SUITE="$2"; shift 2 ;;
    --session) [[ -z "$SESSION" && $# -ge 2 ]] || { usage >&2; exit 2; }; SESSION="$2"; shift 2 ;;
    --subphase) [[ "$SUBPHASE" == "fe3a" && $# -ge 2 ]] || { usage >&2; exit 2; }; SUBPHASE="$2"; shift 2 ;;
    --input-root) [[ -z "$INPUT_ROOT" && $# -ge 2 ]] || { usage >&2; exit 2; }; INPUT_ROOT="$2"; shift 2 ;;
    --log-dir) [[ -z "$LOG_DIR" && $# -ge 2 ]] || { usage >&2; exit 2; }; LOG_DIR="$2"; shift 2 ;;
    --evidence-dir) [[ -z "$EVIDENCE_DIR" && $# -ge 2 ]] || { usage >&2; exit 2; }; EVIDENCE_DIR="$2"; shift 2 ;;
    --help) usage; exit 0 ;;
    *) usage >&2; exit 2 ;;
  esac
done

[[ -n "$SUITE" && -n "$SESSION" && -n "$LOG_DIR" ]] || { usage >&2; exit 2; }
[[ "$SESSION" =~ ^[a-z0-9][a-z0-9-]{1,62}$ ]] || {
  printf 'error=session name must match ^[a-z0-9][a-z0-9-]{1,62}$\n' >&2
  exit 2
}
[[ "$SUBPHASE" =~ ^[a-z0-9][a-z0-9-]{1,62}$ ]] || {
  printf 'error=subphase name must match ^[a-z0-9][a-z0-9-]{1,62}$\n' >&2
  exit 2
}
[[ "$LOG_DIR" == /* ]] || { echo "log dir must be absolute" >&2; exit 2; }
[[ -z "$EVIDENCE_DIR" || "$EVIDENCE_DIR" == /* ]] || { echo "evidence dir must be absolute" >&2; exit 2; }
LOG_DIR="$(realpath -m -- "$LOG_DIR")"
if [[ -n "$EVIDENCE_DIR" ]]; then EVIDENCE_DIR="$(realpath -m -- "$EVIDENCE_DIR")"; fi

path_in_repo() { [[ "$1" == "$REPO_DIR" || "$1" == "$REPO_DIR/"* ]]; }
if path_in_repo "$LOG_DIR" || { [[ -n "$EVIDENCE_DIR" ]] && path_in_repo "$EVIDENCE_DIR"; }; then
  echo "logs and evidence must be outside the worktree" >&2
  exit 2
fi

# --- occupancy: whole-node mkdir + compose gate flock (kickoff §4.2) ---
BUSY_DIR="/home/dev/gdds-node-busy.d"
GATE_LOCK="/tmp/gateway-compose-gate.lock"
HAVE_BUSY=0
HAVE_FLOCK=0
TOOLCHAIN_CONTAINER=""
PROJECT_NAME=""
RUN_ROOT=""
RS_TAG=""
RS_TAG_SET=0
SMOKE_INPUT=""
STACK_STARTED=0
INTERRUPT_SIGNAL=""

log() { printf '%s\n' "$*" | tee -a "$LOG_FILE"; }

mkdir -p -- "$LOG_DIR"
if [[ -n "$EVIDENCE_DIR" ]]; then mkdir -p -- "$EVIDENCE_DIR"; fi
STARTED_AT="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
HEAD_START="$(git -C "$REPO_DIR" rev-parse HEAD)"
LOG_FILE="$LOG_DIR/real-backend-e2e-${SUITE}-${SESSION}-$(git -C "$REPO_DIR" rev-parse --short HEAD)-$(date -u +%Y%m%dT%H%M%SZ)-$$.log"
[[ ! -e "$LOG_FILE" ]] || { echo "refusing to overwrite log: $LOG_FILE" >&2; exit 2; }
: > "$LOG_FILE"

dolt_running() {
  local comm
  for comm in /proc/[0-9]*/comm; do
    [[ -r "$comm" ]] || continue
    IFS= read -r name < "$comm" || continue
    [[ "$name" == "dolt" ]] && return 0
  done
  return 1
}

# B3: rewrite only purpose + add failure time; keep every other marker field.
rewrite_marker_cleanup_failed() {
  local marker="$BUSY_DIR/$SESSION"
  [[ -f "$marker" ]] || return 0
  python3 -I - "$marker" "$SESSION" "$(date -u +%Y-%m-%dT%H:%M:%SZ)" <<'PY'
import sys

path, session, failed_at = sys.argv[1:4]
lines = open(path, encoding="utf-8").read().splitlines()
out = []
replaced = False
for line in lines:
    if line.startswith("purpose="):
        out.append(f"purpose=cleanup-failed ({session})")
        replaced = True
    else:
        out.append(line)
if not replaced:
    out.append(f"purpose=cleanup-failed ({session})")
out.append(f"cleanup_failed_at={failed_at}")
open(path, "w", encoding="utf-8").write("\n".join(out) + "\n")
PY
}

cleanup() {
  local exit_code=$?
  local cleanup_failed=0
  trap '' INT TERM HUP
  trap - EXIT
  set +e
  local now

  # 1. stop and remove the toolchain container first: this ends any running
  #    `docker exec` (B2) and frees the project network (kickoff §4.8).
  if [[ -n "$TOOLCHAIN_CONTAINER" ]]; then
    docker stop --time 10 "$TOOLCHAIN_CONTAINER" >/dev/null 2>&1 || true
    docker rm --force "$TOOLCHAIN_CONTAINER" >/dev/null 2>&1 || true
  fi
  # 2. compose logs, then down (volumes, orphans, project-local images).
  if [[ -n "$PROJECT_NAME" ]]; then
    docker compose -f "$REPO_DIR/vnext/deploy/compose.yaml" -p "$PROJECT_NAME" logs --no-color --timestamps \
      >"$LOG_DIR/compose-$PROJECT_NAME.log" 2>&1 || true
    if ! docker compose -f "$REPO_DIR/vnext/deploy/compose.yaml" -p "$PROJECT_NAME" down -v --remove-orphans --rmi local \
      >/dev/null 2>&1; then
      cleanup_failed=1
      log "cleanup_compose_down=failed"
    fi
  fi
  # 3. remove the per-run RS image tag (kickoff §4.8).
  if [[ "$RS_TAG_SET" == "1" ]]; then
    docker image rm "$RS_TAG" >/dev/null 2>&1 || true
  fi
  # 4. residual checks. Port 8000 and dolt belong to the cleanup only when
  #    this run actually started the Compose stack (B3).
  if [[ -n "$PROJECT_NAME" ]]; then
    local leftovers
    leftovers="$(docker ps -a --filter "label=com.docker.compose.project=$PROJECT_NAME" --format '{{.Names}}' 2>/dev/null)"
    [[ -z "$leftovers" ]] || { cleanup_failed=1; log "cleanup_leftover_containers=$leftovers"; }
    leftovers="$(docker network ls --filter "label=com.docker.compose.project=$PROJECT_NAME" --format '{{.Name}}' 2>/dev/null)"
    [[ -z "$leftovers" ]] || { cleanup_failed=1; log "cleanup_leftover_networks=$leftovers"; }
    leftovers="$(docker volume ls --filter "label=com.docker.compose.project=$PROJECT_NAME" --format '{{.Name}}' 2>/dev/null)"
    [[ -z "$leftovers" ]] || { cleanup_failed=1; log "cleanup_leftover_volumes=$leftovers"; }
  fi
  if [[ "$STACK_STARTED" == "1" ]]; then
    local port_users
    port_users="$(docker ps --filter publish=8000 --format '{{.Names}}' 2>/dev/null)"
    if [[ -n "$port_users" ]]; then
      cleanup_failed=1
      log "cleanup_port_8000_busy=$(printf '%s' "$port_users" | tr '\n' ' ')"
    fi
    if dolt_running; then
      cleanup_failed=1
      log "cleanup_dolt_processes=running"
    fi
  fi
  # 5. release flock, then delete the busy marker (kickoff §4.2 order).
  if [[ "$HAVE_FLOCK" == "1" ]]; then
    exec 9>&- || true
    HAVE_FLOCK=0
    log "flock_released_at=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  fi
  if [[ "$HAVE_BUSY" == "1" ]]; then
    now="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
    if [[ "$cleanup_failed" == "0" ]]; then
      rm -f -- "$BUSY_DIR/$SESSION" 2>/dev/null || true
      if rmdir -- "$BUSY_DIR" 2>/dev/null; then
        log "occupancy_released_at=$now"
      else
        cleanup_failed=1
        rewrite_marker_cleanup_failed
        log "cleanup_busy_dir=remove_failed"
      fi
      HAVE_BUSY=0
    else
      rewrite_marker_cleanup_failed
    fi
  fi

  if [[ "$INTERRUPT_SIGNAL" != "" ]]; then
    log "interrupted_by=$INTERRUPT_SIGNAL"
  fi
  log "cleanup_status=$([[ "$cleanup_failed" == "0" ]] && echo ok || echo failed)"

  # 6. remove per-run secrets and inputs.
  [[ -n "$RUN_ROOT" ]] && rm -rf -- "$RUN_ROOT" || true

  {
    printf 'ended_at=%s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
    printf 'hostname_end=%s\n' "$(hostname -f 2>/dev/null || hostname)"
    printf 'head_end=%s\n' "$(git -C "$REPO_DIR" rev-parse HEAD 2>/dev/null || true)"
    printf 'frontend_tree_end=%s\n' "$(git -C "$REPO_DIR" rev-parse HEAD:frontend 2>/dev/null || true)"
    printf 'vnext_tree_end=%s\n' "$(git -C "$REPO_DIR" rev-parse HEAD:vnext 2>/dev/null || true)"
    printf 'worktree_clean_end=%s\n' "$([[ -z "$(git -C "$REPO_DIR" status --porcelain=v1 --untracked-files=all 2>/dev/null)" ]] && echo true || echo false)"
    printf 'exit_code=%s\n' "$exit_code"
  } >> "$LOG_FILE" 2>/dev/null || true
  sha256sum "$LOG_FILE" > "$LOG_FILE.sha256" 2>/dev/null || true
  printf 'log_file=%s\n' "$LOG_FILE"
  cat "$LOG_FILE.sha256" 2>/dev/null || true
  exit "$exit_code"
}

on_signal() {
  local signal="$1" code="$2"
  trap - INT TERM HUP
  INTERRUPT_SIGNAL="$signal"
  log "signal_received=$signal"
  log "signal_exit_code=$code"
  exit "$code"
}

trap cleanup EXIT
trap 'on_signal INT 130' INT
trap 'on_signal TERM 143' TERM
trap 'on_signal HUP 129' HUP

if [[ "$SUITE" != "smoke" ]]; then
  printf 'error=only --suite smoke is implemented in FE3a; --suite %s belongs to FE3b\n' "$SUITE" >&2
  exit 2
fi
if [[ -n "$INPUT_ROOT" ]]; then
  printf 'error=--input-root is for the FE3b t1 suite; smoke uses the shared upload inputs\n' >&2
  exit 2
fi

RUN_STAGE="occupancy"
HOSTNAME_START="$(hostname -f 2>/dev/null || hostname)"
{
  printf 'hostname=%s\n' "$HOSTNAME_START"
  printf 'started_at=%s\n' "$STARTED_AT"
  printf 'head_start=%s\n' "$HEAD_START"
  printf 'frontend_tree_start=%s\n' "$(git -C "$REPO_DIR" rev-parse HEAD:frontend)"
  printf 'vnext_tree_start=%s\n' "$(git -C "$REPO_DIR" rev-parse HEAD:vnext)"
  printf 'suite=%s\n' "$SUITE"
  printf 'session=%s\n' "$SESSION"
  printf 'subphase=%s\n' "$SUBPHASE"
  printf 'npm_cache_dir=%s\n' "$NPM_CACHE_DIR"
  printf 'npm_cache_source_commit=%s\n' "$NPM_CACHE_SOURCE_COMMIT"
} | tee "$LOG_FILE"

if ! mkdir "$BUSY_DIR" 2>/dev/null; then
  if [[ -f "$BUSY_DIR/$SESSION" ]]; then
    log "error=node is busy (own marker present)"
  else
    log "error=node is busy: $BUSY_DIR exists"
    ls -la "$BUSY_DIR" 2>/dev/null | tee -a "$LOG_FILE" || true
  fi
  exit 3
fi
printf 'session=%s\npurpose=fe3a-real-backend-e2e-%s\nstarted_at=%s\nhostname=%s\nworktree=%s\nhead=%s\n' \
  "$SESSION" "$SUITE" "$STARTED_AT" "$HOSTNAME_START" "$REPO_DIR" "$HEAD_START" > "$BUSY_DIR/$SESSION"
HAVE_BUSY=1
log "occupancy_marker=$(printf '%s' "$(tr '\n' ';' < "$BUSY_DIR/$SESSION")")"
log "occupancy_acquired_at=$(date -u +%Y-%m-%dT%H:%M:%SZ)"

exec 9>"$GATE_LOCK"
if ! flock -n 9; then
  log "error=compose gate lock is held"
  exit 3
fi
HAVE_FLOCK=1
log "flock_acquired_at=$(date -u +%Y-%m-%dT%H:%M:%SZ)"

# Residual checks (kickoff §4.2): port 8000, dolt, own containers/volumes/networks.
RUN_STAGE="residual-check"
if [[ -n "$(docker ps --filter publish=8000 --format '{{.Names}}' 2>/dev/null)" ]]; then
  log "error=port 8000 is already published"
  docker ps --filter publish=8000 --format '{{.Names}}' | tee -a "$LOG_FILE"
  exit 3
fi
if dolt_running; then
  log "error=dolt processes are running"
  exit 3
fi
if [[ -n "$(docker ps -a --filter "name=gdds-fe-${SUBPHASE}-" --format '{{.Names}}' 2>/dev/null)" ]]; then
  log "error=previous ${SUBPHASE} compose/toolchain leftovers exist"
  docker ps -a --filter "name=gdds-fe-${SUBPHASE}-" --format '{{.Names}}' | tee -a "$LOG_FILE"
  exit 3
fi
if [[ -n "$(docker volume ls --filter "name=gdds-fe-${SUBPHASE}-" --format '{{.Name}}' 2>/dev/null)" ]]; then
  log "error=previous ${SUBPHASE} compose volume leftovers exist"
  docker volume ls --filter "name=gdds-fe-${SUBPHASE}-" --format '{{.Name}}' | tee -a "$LOG_FILE"
  exit 3
fi
if [[ -n "$(docker network ls --filter "name=gdds-fe-${SUBPHASE}-" --format '{{.Name}}' 2>/dev/null)" ]]; then
  log "error=previous ${SUBPHASE} compose network leftovers exist"
  docker network ls --filter "name=gdds-fe-${SUBPHASE}-" --format '{{.Name}}' | tee -a "$LOG_FILE"
  exit 3
fi

# Toolchain + npm cache preconditions (same as run-tests.sh).
RUN_STAGE="preconditions"
if [[ ! -d "$NPM_CACHE_DIR" ]] || [[ -z "$(find "$NPM_CACHE_DIR" -mindepth 1 -maxdepth 1 -print -quit)" ]]; then
  log "error=npm cache is missing or empty: $NPM_CACHE_DIR"
  exit 2
fi
if [[ ! -f "$NPM_CACHE_ARCHIVE" ]]; then
  log "error=npm cache source archive is missing: $NPM_CACHE_ARCHIVE"
  exit 2
fi
if ! docker image inspect "$TOOLCHAIN_IMAGE" >/dev/null 2>&1; then
  log "error=toolchain image is not loaded locally: $TOOLCHAIN_IMAGE"
  exit 2
fi
if [[ -n "$(git -C "$REPO_DIR" status --porcelain=v1 --untracked-files=all)" ]]; then
  log "error=source worktree is not clean"
  git -C "$REPO_DIR" status --porcelain=v1 --untracked-files=all | tee -a "$LOG_FILE"
  exit 2
fi
NPM_CACHE_ARCHIVE_SHA="$(sha256sum "$NPM_CACHE_ARCHIVE" | awk '{print $1}')"
log "npm_cache_archive=$NPM_CACHE_ARCHIVE"
log "npm_cache_archive_sha256=$NPM_CACHE_ARCHIVE_SHA"
TOOLCHAIN_IDENTITY_ARCHIVE="$(mktemp "${TMPDIR:-/tmp}/gateway-fe3a-toolchain.XXXXXX.tar")"
docker image save --output "$TOOLCHAIN_IDENTITY_ARCHIVE" "$TOOLCHAIN_IMAGE"
TOOLCHAIN_IDENTITY="$(python3 "$FRONTEND_DIR/scripts/docker-save-image-identity.py" "$TOOLCHAIN_IDENTITY_ARCHIVE")"
rm -f -- "$TOOLCHAIN_IDENTITY_ARCHIVE"
log "toolchain_image=$TOOLCHAIN_IMAGE"
log "toolchain_identity=$TOOLCHAIN_IDENTITY"
log "docker_version=$(docker version --format '{{.Server.Version}}' 2>/dev/null || echo unknown)"
log "compose_version=$(docker compose version --short 2>/dev/null || echo unknown)"

# Dependency input tag (kickoff §4.3): never build the dep image here.
RUN_STAGE="dependency-input"
DEP_INPUT_JSON="$("$REPO_DIR/vnext/scripts/build-backend-dependency-base.sh" --print-input 2>/dev/null)"
DEPENDENCY_TAG="$(python3 -c 'import json,sys; print(json.loads(sys.argv[1])["image"])' "$DEP_INPUT_JSON")"
DEPENDENCY_INPUT_SHA="$(python3 -c 'import json,sys; print(json.loads(sys.argv[1])["input_sha256"])' "$DEP_INPUT_JSON")"
log "dependency_base_image=$DEPENDENCY_TAG"
log "dependency_input_sha256=$DEPENDENCY_INPUT_SHA"
if ! docker image inspect "$DEPENDENCY_TAG" >/dev/null 2>&1; then
  log "error=dependency-base image missing locally: $DEPENDENCY_TAG (cache miss, stop)"
  exit 2
fi
DEP_LABEL="$(docker image inspect "$DEPENDENCY_TAG" --format '{{index .Config.Labels "gateway.backend.dependency-input-sha256"}}')"
log "dependency_input_label=$DEP_LABEL"
if [[ "$DEP_LABEL" != "$DEPENDENCY_INPUT_SHA" ]]; then
  log "error=dependency-base label mismatch: $DEP_LABEL != $DEPENDENCY_INPUT_SHA"
  exit 2
fi
DEP_IMAGE_ID="$(docker image inspect "$DEPENDENCY_TAG" --format '{{.Id}}')"
DEP_ROOTFS_LAYERS="$(docker image inspect "$DEPENDENCY_TAG" --format '{{json .RootFS.Layers}}')"
log "dependency_image_id=$DEP_IMAGE_ID"
log "dependency_rootfs_layers=$DEP_ROOTFS_LAYERS"

# RS dependency tag + label check (kickoff §4.3).
RUN_STAGE="rs-dependency"
RS_UV_SHA="$(sha256sum "$REPO_DIR/vnext/repository_service/uv.lock" | awk '{print $1}')"
RS_DEP_TAG="gateway-p2r1-repository:lock-${RS_UV_SHA:0:12}"
log "rs_dependency_base_image=$RS_DEP_TAG"
if ! docker image inspect "$RS_DEP_TAG" >/dev/null 2>&1; then
  log "error=RS dependency image missing: $RS_DEP_TAG (cache miss, stop)"
  exit 2
fi
RS_LABEL="$(docker image inspect "$RS_DEP_TAG" --format '{{index .Config.Labels "gateway.p2r1.uv-lock-sha256"}}')"
if [[ "$RS_LABEL" != "$RS_UV_SHA" ]]; then
  log "error=RS dependency label mismatch: $RS_LABEL != $RS_UV_SHA"
  exit 2
fi
log "rs_dependency_label=$RS_LABEL"

RUN_STAGE="rs-build"
RS_TAG="gateway-repository-service:fe-${HEAD_START:0:12}"
log "rs_image_tag=$RS_TAG"
RS_TAG_SET=1
if ! GATEWAY_REPOSITORY_SERVICE_IMAGE="$RS_TAG" GATEWAY_P2R1_DEPENDENCY_BASE_IMAGE="$RS_DEP_TAG" GATEWAY_DOCKER_BUILD_NETWORK=none \
  "$REPO_DIR/vnext/scripts/build-repository-service-image.sh" 2>&1 | tee -a "$LOG_FILE"; then
  log "error=RS image build failed (cache miss or network needed, stop)"
  exit 2
fi
export GATEWAY_REPOSITORY_SERVICE_IMAGE="$RS_TAG"
RS_IMAGE_ID="$(docker image inspect "$RS_TAG" --format '{{.Id}}')"
RS_LABELS="$(docker image inspect "$RS_TAG" --format '{{json .Config.Labels}}')"
log "rs_image_built=$RS_TAG"
log "rs_image_id=$RS_IMAGE_ID"
log "rs_image_labels=$RS_LABELS"

# Project + secrets (outside the worktree, container-readable).
RUN_STAGE="compose-up"
STAMP="$(date -u +%Y%m%dt%H%M%Sz | tr 'A-Z' 'a-z')"
PROJECT_NAME="gdds-fe-${SUBPHASE}-${HEAD_START:0:12}-${STAMP}"
export COMPOSE_PROJECT_NAME="$PROJECT_NAME"
RUN_ROOT="$(mktemp -d "${TMPDIR:-/tmp}/gateway-fe3a-e2e.XXXXXX")"
chmod 0755 "$RUN_ROOT"
log "compose_project=$PROJECT_NAME"
log "run_root=$RUN_ROOT"

# Random per-run tokens (never logged, never in build products).
SUBMITTER_TOKEN="fe3a-submitter-$(openssl rand -hex 16)"
NOPREVIEW_TOKEN="fe3a-nopreview-$(openssl rand -hex 16)"
REVIEWER_TOKEN="fe3a-reviewer-$(openssl rand -hex 16)"
ARCHIVER_TOKEN="fe3a-archiver-$(openssl rand -hex 16)"
NOPERM_TOKEN="fe3a-noperm-$(openssl rand -hex 16)"
RS_BEARER="fe3a-rs-$(openssl rand -hex 16)"
INTERNAL_BEARER="fe3a-internal-$(openssl rand -hex 16)"
UPLOAD_DEVICE="fe3a-device-upload-preview"
UPLOAD_PROJECT="fe3a-project-upload-preview"
PERMISSION_DEVICE="fe3a-device-permission-denied"
PERMISSION_PROJECT="fe3a-project-permission-denied"
INPUT_SCOPE_SLUGS=(input-a input-b-mod input-c input-d input-b-full)
INPUT_SCOPE_NAMES=("A" "B-mod" "C" "D" "B-full")
INPUT_TOKENS=()
for input_slug in "${INPUT_SCOPE_SLUGS[@]}"; do
  INPUT_TOKENS+=("fe3a-${input_slug}-$(openssl rand -hex 16)")
done

cat > "$RUN_ROOT/session.json" <<EOF
{"sessions": [
  {"token": "$SUBMITTER_TOKEN", "actor_id": "fe3a-upload-preview-submitter", "gateway_device_external_key": "$UPLOAD_DEVICE", "business_project_id": "$UPLOAD_PROJECT", "permissions": ["workspace_read", "read_project_history", "upload_submit_workspace", "preview_workspace"]},
  {"token": "$REVIEWER_TOKEN", "actor_id": "fe3a-upload-preview-reviewer", "gateway_device_external_key": "$UPLOAD_DEVICE", "business_project_id": "$UPLOAD_PROJECT", "permissions": ["workspace_read", "read_project_history", "review_submission"]},
  {"token": "$ARCHIVER_TOKEN", "actor_id": "fe3a-upload-preview-archiver", "gateway_device_external_key": "$UPLOAD_DEVICE", "business_project_id": "$UPLOAD_PROJECT", "permissions": ["workspace_read", "read_project_history", "archive_submission"]},
  {"token": "$NOPREVIEW_TOKEN", "actor_id": "fe3a-permission-denied-no-preview", "gateway_device_external_key": "$PERMISSION_DEVICE", "business_project_id": "$PERMISSION_PROJECT", "permissions": ["workspace_read", "read_project_history", "upload_submit_workspace"]},
  {"token": "$NOPERM_TOKEN", "actor_id": "fe3a-permission-denied-noperm", "gateway_device_external_key": "$PERMISSION_DEVICE", "business_project_id": "$PERMISSION_PROJECT", "permissions": ["workspace_read", "read_project_history"]}
]}
EOF
# Input-scope identities: one upload/preview submitter per independent scope.
python3 -I - "$RUN_ROOT/session.json" "${INPUT_SCOPE_SLUGS[@]}" "${INPUT_TOKENS[@]}" <<'PY'
import json
import sys

path, *rest = sys.argv[1:]
slugs = rest[: len(rest) // 2]
tokens = rest[len(rest) // 2 :]
with open(path, encoding="utf-8") as handle:
    data = json.load(handle)
for slug, token in zip(slugs, tokens, strict=True):
    data["sessions"].append({
        "token": token,
        "actor_id": f"fe3a-{slug}-submitter",
        "gateway_device_external_key": f"fe3a-device-{slug}",
        "business_project_id": f"fe3a-project-{slug}",
        "permissions": ["workspace_read", "read_project_history", "upload_submit_workspace", "preview_workspace"],
    })
with open(path, "w", encoding="utf-8") as handle:
    json.dump(data, handle, indent=2)
    handle.write("\n")
PY
printf '%s\n' "$RS_BEARER" > "$RUN_ROOT/repository-bearer-token"
printf '%s\n' "$INTERNAL_BEARER" > "$RUN_ROOT/internal-bearer-token"
chmod 0644 "$RUN_ROOT/session.json" "$RUN_ROOT/repository-bearer-token" "$RUN_ROOT/internal-bearer-token"
export GATEWAY_P2R2_BEARER_TOKEN_FILE="$RUN_ROOT/repository-bearer-token"
export GATEWAY_BACKEND_SESSION_FILE="$RUN_ROOT/session.json"
export GATEWAY_BACKEND_PROVISIONED_MAPPING_FILE="$RUN_ROOT/provisioned-mapping.json"
export GATEWAY_BACKEND_INTERNAL_BEARER_TOKEN_FILE="$RUN_ROOT/internal-bearer-token"
export GATEWAY_REPOSITORY_SERVICE_BEARER_TOKEN_FILE="$RUN_ROOT/repository-bearer-token"
export GATEWAY_BACKEND_USE_PRELOADED_DEPENDENCIES=1
export GATEWAY_BACKEND_DEPENDENCY_BASE_IMAGE="$DEPENDENCY_TAG"
export GATEWAY_DOCKER_BUILD_NETWORK=none
log "identity=submitter scope=upload-preview permissions=workspace_read,read_project_history,upload_submit_workspace,preview_workspace"
log "identity=reviewer scope=upload-preview permissions=workspace_read,read_project_history,review_submission"
log "identity=archiver scope=upload-preview permissions=workspace_read,read_project_history,archive_submission"
log "identity=no-preview scope=permission-denied permissions=workspace_read,read_project_history,upload_submit_workspace"
log "identity=noperm scope=permission-denied permissions=workspace_read,read_project_history"
for input_slug in "${INPUT_SCOPE_SLUGS[@]}"; do
  log "identity=${input_slug} scope=${input_slug} permissions=workspace_read,read_project_history,upload_submit_workspace,preview_workspace"
done

# 1. build backend+worker images (offline, preloaded deps).
if ! docker compose -f "$REPO_DIR/vnext/deploy/compose.yaml" -p "$PROJECT_NAME" build backend worker 2>&1 | tee -a "$LOG_FILE"; then
  log "error=backend/worker build failed"
  exit 2
fi
docker compose -f "$REPO_DIR/vnext/deploy/compose.yaml" -p "$PROJECT_NAME" images 2>&1 | tee -a "$LOG_FILE" || true

# 2. up repository-service, wait ready, seed one repository per scope.
STACK_STARTED=1
if ! docker compose -f "$REPO_DIR/vnext/deploy/compose.yaml" -p "$PROJECT_NAME" up -d --no-build repository-service 2>&1 | tee -a "$LOG_FILE"; then
  log "error=repository-service up failed"
  exit 2
fi
RS_READY_OK=0
for _ in $(seq 1 90); do
  if docker compose -f "$REPO_DIR/vnext/deploy/compose.yaml" -p "$PROJECT_NAME" exec -T repository-service python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/readyz', timeout=5.0)" >/dev/null 2>&1; then
    RS_READY_OK=1
    break
  fi
  sleep 2
done
if [[ "$RS_READY_OK" != "1" ]]; then
  log "error=repository-service never became ready"
  exit 2
fi
log "repository_service_ready=ok"

SCOPE_SLUGS=(upload-preview permission-denied "${INPUT_SCOPE_SLUGS[@]}")
SCOPE_NAMES=("上传与预览" "权限拒绝" "${INPUT_SCOPE_NAMES[@]}")
SCOPE_ROWS=()
for index in "${!SCOPE_SLUGS[@]}"; do
  scope="${SCOPE_SLUGS[$index]}"
  scope_name="${SCOPE_NAMES[$index]}"
  case "$scope" in
    upload-preview)
      device_key="$UPLOAD_DEVICE"; business_project="$UPLOAD_PROJECT" ;;
    permission-denied)
      device_key="$PERMISSION_DEVICE"; business_project="$PERMISSION_PROJECT" ;;
    input-*)
      device_key="fe3a-device-${scope}"; business_project="fe3a-project-${scope}" ;;
    *)
      log "error=unknown scope $scope"; exit 2 ;;
  esac
  baseline_node="fe3a-baseline-${scope}"
  seed_key="fe3a-seed-${SUBPHASE}-${scope}-${STAMP}-${SESSION}"
  if ! docker compose -f "$REPO_DIR/vnext/deploy/compose.yaml" -p "$PROJECT_NAME" exec -T repository-service python -c "
import urllib.request
req = urllib.request.Request('http://127.0.0.1:8000/v1/repositories', method='POST', headers={'Authorization': 'Bearer $RS_BEARER', 'Idempotency-Key': '$seed_key'})
print(urllib.request.urlopen(req, timeout=120.0).read().decode())" > "$RUN_ROOT/seed-${scope}.json" 2>>"$LOG_FILE"; then
    log "error=repository-service seed failed for scope=$scope"
    exit 2
  fi
  seed_json="$(cat "$RUN_ROOT/seed-${scope}.json")"
  repo_id="$(python3 -c 'import json,sys; print(json.loads(sys.argv[1])["repository_id"])' "$seed_json")"
  init_commit="$(python3 -c 'import json,sys; print(json.loads(sys.argv[1])["initial_commit_id"])' "$seed_json")"
  SCOPE_ROWS+=("${scope}|${device_key}|${business_project}|${baseline_node}|${repo_id}|${init_commit}")
  log "scope=$scope_name scope_slug=$scope repository_id=$repo_id initial_commit_id=$init_commit business_baseline_node_id=$baseline_node"
done

python3 -I - "$RUN_ROOT/provisioned-mapping.json" "${SCOPE_ROWS[@]}" <<'PY'
import json
import sys

out_path, *rows = sys.argv[1:]
mappings = []
for row in rows:
    _slug, device, project, node, repo, commit = row.split("|")
    mappings.append({
        "gateway_device_external_key": device,
        "business_project_id": project,
        "repository_id": repo,
        "business_baseline_node_id": node,
        "business_baseline_commit_id": commit,
        "baseline_head_version": 0,
        "enabled": True,
    })
with open(out_path, "w", encoding="utf-8") as handle:
    json.dump({"mappings": mappings}, handle, indent=2)
    handle.write("\n")
PY
chmod 0644 "$RUN_ROOT/provisioned-mapping.json"
log "provisioned_mappings=$(python3 -c 'import json,sys; print(len(json.load(open(sys.argv[1]))["mappings"]))' "$RUN_ROOT/provisioned-mapping.json")"

# 3. up backend+worker, wait /readyz and the worker readiness log line.
if ! docker compose -f "$REPO_DIR/vnext/deploy/compose.yaml" -p "$PROJECT_NAME" up -d --no-build backend worker 2>&1 | tee -a "$LOG_FILE"; then
  log "error=backend/worker up failed"
  exit 2
fi
READYZ_OK=0
for _ in $(seq 1 90); do
  if curl -fsS http://127.0.0.1:8000/readyz >/dev/null 2>&1; then
    READYZ_OK=1
    break
  fi
  sleep 2
done
if [[ "$READYZ_OK" != "1" ]]; then
  log "error=backend /readyz never became ready"
  exit 2
fi
log "backend_readyz=ok"
WORKER_READY_OK=0
for _ in $(seq 1 60); do
  if docker compose -f "$REPO_DIR/vnext/deploy/compose.yaml" -p "$PROJECT_NAME" logs worker --no-color 2>/dev/null | grep -q 'code=worker_ready'; then
    WORKER_READY_OK=1
    break
  fi
  sleep 2
done
if [[ "$WORKER_READY_OK" != "1" ]]; then
  log "error=worker never logged code=worker_ready"
  exit 2
fi
log "worker_ready=ok"
for svc in backend worker; do
  cid=$(docker compose -f "$REPO_DIR/vnext/deploy/compose.yaml" -p "$PROJECT_NAME" ps -q "$svc")
  log "${svc}_image_id=$(docker inspect --format '{{.Image}}' "$cid")"
done
log "compose_network_id=$(docker network inspect "${PROJECT_NAME}_default" --format '{{.Id}}' 2>/dev/null || echo unknown)"

# 4. Smoke input directory. These committed fixtures are the FE3a smoke
# upload; the four FE3b upload sequences and their real inputs are still
# pending the design-session record (review B10).
# Q10 upload inputs: five independent directories, one per input scope.
# SQL files are the committed derived inputs; logics come from the shared
# source fixtures without copying them into the worktree.
SMOKE_INPUT="$RUN_ROOT/inputs"
INPUT_FIXTURES="$FRONTEND_DIR/e2e-real/fixtures/upload-inputs"
SHARED_INPUTS="$FRONTEND_DIR/src/test/fixtures/source/upload-inputs"
mkdir -p -- "$SMOKE_INPUT"/{a,b,c,d}/{sql,comps/logic}
for input_name in a b c d; do
  printf 'fe3a-input-%s\n' "$input_name" > "$SMOKE_INPUT/$input_name/input.pmc"
done
cp -- "$INPUT_FIXTURES/sql-baseline.sql" "$SMOKE_INPUT/a/sql/dbcfg.sql"
cp -- "$INPUT_FIXTURES/sql-initial.sql" "$SMOKE_INPUT/b/sql/dbcfg.sql"
cp -- "$INPUT_FIXTURES/sql-modified.sql" "$SMOKE_INPUT/c/sql/dbcfg.sql"
cp -- "$SHARED_INPUTS/sql-replacement-current.sql" "$SMOKE_INPUT/d/sql/dbcfg.sql"
cp -- "$SHARED_INPUTS/logics-1.xml" "$SMOKE_INPUT/a/comps/logic/logics.xml"
cp -- "$SHARED_INPUTS/logics-2.xml" "$SMOKE_INPUT/b/comps/logic/logics.xml"
cp -- "$SHARED_INPUTS/logics-3.xml" "$SMOKE_INPUT/c/comps/logic/logics.xml"
cp -- "$SHARED_INPUTS/logics-3.xml" "$SMOKE_INPUT/d/comps/logic/logics.xml"
chmod -R a+rX -- "$SMOKE_INPUT"
log "smoke_input=$SMOKE_INPUT"
for input_name in a b c d; do
  log "smoke_input_scope=${input_name} sql_sha256=$(sha256sum "$SMOKE_INPUT/$input_name/sql/dbcfg.sql" | cut -d' ' -f1) logics_sha256=$(sha256sum "$SMOKE_INPUT/$input_name/comps/logic/logics.xml" | cut -d' ' -f1)"
done

# 5. Toolchain container on the compose network, production build from a
# git archive (never the live worktree), input mounted read-only.
RUN_STAGE="toolchain"
git -C "$REPO_DIR" archive --format=tar HEAD frontend > "$RUN_ROOT/frontend.tar"
TOOLCHAIN_CONTAINER="${PROJECT_NAME}-toolchain"
if ! docker run -d --init --ipc=host --name "$TOOLCHAIN_CONTAINER" --label "com.docker.compose.project=$PROJECT_NAME" \
  --network "${PROJECT_NAME}_default" \
  --volume "$RUN_ROOT/frontend.tar:/frontend.tar:ro" \
  --volume "$NPM_CACHE_DIR:/npm-cache:ro" \
  --volume "$LOG_DIR:/results" \
  --volume "$SMOKE_INPUT:/input:ro" \
  --env "GATEWAY_FRONTEND_BACKEND_ORIGIN=http://backend:8000" \
  --env "GATEWAY_FE_SUITE=$SUITE" \
  "$TOOLCHAIN_IMAGE" sleep infinity >/dev/null; then
  log "error=toolchain container failed to start"
  exit 2
fi
log "toolchain_container=$TOOLCHAIN_CONTAINER"
log "toolchain_network=${PROJECT_NAME}_default"

if ! docker exec "$TOOLCHAIN_CONTAINER" bash -euo pipefail -c '
  mkdir -p /tmp/frontend /tmp/npm-cache
  tar -xf /frontend.tar --strip-components=1 -C /tmp/frontend
  cp -a /npm-cache/. /tmp/npm-cache/
  cd /tmp/frontend
  npm ci --offline --cache /tmp/npm-cache --no-audit --no-fund
  npm run build
' 2>&1 | tee -a "$LOG_FILE"; then
  log "error=toolchain build failed"
  exit 2
fi

# 6. Preview server inside the toolchain container, then the OpenAPI check
# through that preview proxy (kickoff §5.2; B4).
RUN_STAGE="preview"
docker exec -d "$TOOLCHAIN_CONTAINER" bash -c 'cd /tmp/frontend && exec npm run preview -- --host 127.0.0.1 --port 4173 > /tmp/preview.log 2>&1'
PREVIEW_OK=0
for _ in $(seq 1 60); do
  if docker exec "$TOOLCHAIN_CONTAINER" node -e 'fetch("http://127.0.0.1:4173/").then((r) => process.exit(r.ok ? 0 : 1)).catch(() => process.exit(1))' >/dev/null 2>&1; then
    PREVIEW_OK=1
    break
  fi
  sleep 2
done
if [[ "$PREVIEW_OK" != "1" ]]; then
  log "error=preview server never became ready"
  docker exec "$TOOLCHAIN_CONTAINER" tail -50 /tmp/preview.log 2>/dev/null | tee -a "$LOG_FILE" || true
  exit 2
fi
log "preview_ready=http://127.0.0.1:4173"

RUN_STAGE="openapi-compare"
if ! docker exec "$TOOLCHAIN_CONTAINER" node -e 'fetch("http://127.0.0.1:4173/openapi.json").then(async (r) => { if (!r.ok) process.exit(1); process.stdout.write(await r.text()); }).catch(() => process.exit(1))' > "$LOG_DIR/openapi-runtime.json"; then
  log "error=fetching /openapi.json through the preview proxy failed"
  exit 2
fi
set +e
python3 -I - "$FRONTEND_DIR/openapi.json" "$LOG_DIR/openapi-runtime.json" "$LOG_DIR" <<'PY'
import hashlib
import json
import pathlib
import sys

snapshot_path, runtime_path, out_dir = (pathlib.Path(arg) for arg in sys.argv[1:4])


def normalize(value):
    return json.dumps(value, indent=2, sort_keys=True, ensure_ascii=True) + "\n"


snapshot = normalize(json.loads(snapshot_path.read_text(encoding="utf-8")))
runtime = normalize(json.loads(runtime_path.read_text(encoding="utf-8")))
(out_dir / "openapi-snapshot.normalized.json").write_text(snapshot, encoding="utf-8")
(out_dir / "openapi-runtime.normalized.json").write_text(runtime, encoding="utf-8")
print("openapi_snapshot_sha256=" + hashlib.sha256(snapshot_path.read_bytes()).hexdigest())
print("openapi_snapshot_normalized_sha256=" + hashlib.sha256(snapshot.encode()).hexdigest())
print("openapi_runtime_sha256=" + hashlib.sha256(runtime_path.read_bytes()).hexdigest())
print("openapi_runtime_normalized_sha256=" + hashlib.sha256(runtime.encode()).hexdigest())
sys.exit(0 if snapshot == runtime else 3)
PY
OPENAPI_RC=$?
set -e
if [[ "$OPENAPI_RC" == "3" ]]; then
  diff -u "$LOG_DIR/openapi-snapshot.normalized.json" "$LOG_DIR/openapi-runtime.normalized.json" \
    > "$LOG_DIR/openapi.diff" || true
  log "openapi_compare=mismatch"
  log "error=runtime /openapi.json differs from committed snapshot (stop, no browser tests)"
  exit 2
fi
if [[ "$OPENAPI_RC" != "0" ]]; then
  log "error=OpenAPI normalization failed (rc=$OPENAPI_RC)"
  exit 2
fi
log "openapi_compare=match"
sha256sum "$LOG_DIR/openapi-snapshot.normalized.json" "$LOG_DIR/openapi-runtime.normalized.json" | tee -a "$LOG_FILE"

# 7. Identities JSON for per-context injection (owner Q5). Tokens are random
# per run; the file stays outside the worktree and is copied into the
# toolchain container with 0600 permissions.
cat > "$RUN_ROOT/identities.json" <<EOF
[{"name": "submitter", "token": "$SUBMITTER_TOKEN", "actorId": "fe3a-upload-preview-submitter", "businessProjectId": "$UPLOAD_PROJECT", "gatewayDeviceExternalKey": "$UPLOAD_DEVICE", "scope": "upload-preview"},
 {"name": "reviewer", "token": "$REVIEWER_TOKEN", "actorId": "fe3a-upload-preview-reviewer", "businessProjectId": "$UPLOAD_PROJECT", "gatewayDeviceExternalKey": "$UPLOAD_DEVICE", "scope": "upload-preview"},
 {"name": "archiver", "token": "$ARCHIVER_TOKEN", "actorId": "fe3a-upload-preview-archiver", "businessProjectId": "$UPLOAD_PROJECT", "gatewayDeviceExternalKey": "$UPLOAD_DEVICE", "scope": "upload-preview"},
 {"name": "noperm", "token": "$NOPERM_TOKEN", "actorId": "fe3a-permission-denied-noperm", "businessProjectId": "$PERMISSION_PROJECT", "gatewayDeviceExternalKey": "$PERMISSION_DEVICE", "scope": "permission-denied"},
 {"name": "no-preview", "token": "$NOPREVIEW_TOKEN", "actorId": "fe3a-permission-denied-no-preview", "businessProjectId": "$PERMISSION_PROJECT", "gatewayDeviceExternalKey": "$PERMISSION_DEVICE", "scope": "permission-denied"}]
EOF
python3 -I - "$RUN_ROOT/identities.json" "${INPUT_SCOPE_SLUGS[@]}" "${INPUT_TOKENS[@]}" <<'PY'
import json
import sys

path, *rest = sys.argv[1:]
slugs = rest[: len(rest) // 2]
tokens = rest[len(rest) // 2 :]
with open(path, encoding="utf-8") as handle:
    data = json.load(handle)
for slug, token in zip(slugs, tokens, strict=True):
    data.append({
        "name": slug,
        "token": token,
        "actorId": f"fe3a-{slug}-submitter",
        "businessProjectId": f"fe3a-project-{slug}",
        "gatewayDeviceExternalKey": f"fe3a-device-{slug}",
        "scope": slug,
    })
with open(path, "w", encoding="utf-8") as handle:
    json.dump(data, handle, indent=2)
    handle.write("\n")
PY
chmod 0600 "$RUN_ROOT/identities.json"
docker cp "$RUN_ROOT/identities.json" "$TOOLCHAIN_CONTAINER:/tmp/identities.json"

# 8. Run the suite; results come from the Playwright JSON reporter in the log
# directory (B2), not from the tee of the process output.
RUN_STAGE="suite"
log "suite_start=$SUITE"
RESULTS_FILE="$LOG_DIR/results.json"
rm -f -- "$RESULTS_FILE"
set +e
docker exec \
  --env "GATEWAY_FE_SUITE=$SUITE" \
  --env "GATEWAY_FE_SMOKE_INPUT_ROOT=/input" \
  --env "GATEWAY_FE_RESULTS_FILE=/results/results.json" \
  --env "GATEWAY_FE_RESULTS_DIR=/results" \
  --env "GATEWAY_FRONTEND_BACKEND_ORIGIN=http://backend:8000" \
  "$TOOLCHAIN_CONTAINER" bash -euo pipefail -c '
  cd /tmp/frontend
  export GATEWAY_FE_IDENTITIES="$(cat /tmp/identities.json)"
  npx playwright test --config playwright.real.config.ts
' > >(tee -a "$LOG_FILE") 2>&1 &
SUITE_PID=$!
wait "$SUITE_PID"
PLAYWRIGHT_EXIT=$?
set -e
log "playwright_process_exit=$PLAYWRIGHT_EXIT"

if [[ -n "$EVIDENCE_DIR" ]]; then
  mkdir -p -- "$EVIDENCE_DIR/test-results"
  docker cp "$TOOLCHAIN_CONTAINER:/tmp/frontend/test-results/." "$EVIDENCE_DIR/test-results/" 2>/dev/null || true
fi

SUITE_EXIT="$(python3 -I - "$RESULTS_FILE" "$LOG_DIR/suite-summary.txt" <<'PY'
import datetime
import json
import sys

results_path, summary_path = sys.argv[1], sys.argv[2]
lines = []
if not results_path or not __import__("os").path.exists(results_path):
    lines.append("suite_results=missing")
    code = 2
else:
    try:
        data = json.load(open(results_path, encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001 - the result file is external input
        lines.append(f"suite_results_error={exc}")
        code = 2
    else:
        def walk(suites):
            for suite in suites or []:
                for spec in suite.get("specs") or []:
                    for test in spec.get("tests") or []:
                        for result in test.get("results") or []:
                            start = result.get("startTime") or ""
                            duration = result.get("duration") or 0
                            try:
                                start_dt = datetime.datetime.fromisoformat(start.replace("Z", "+00:00"))
                                end = (start_dt + datetime.timedelta(milliseconds=duration)).isoformat().replace("+00:00", "Z")
                            except Exception:  # noqa: BLE001
                                end = ""
                            lines.append(
                                f"test_start={start} test_end={end} "
                                f"test_status={result.get('status')} test_title={test.get('title')}"
                            )
                walk(suite.get("suites"))
        walk(data.get("suites"))
        stats = data.get("stats") or {}
        expected = stats.get("expected") or 0
        unexpected = stats.get("unexpected")
        lines.append(
            f"suite_stats_expected={expected} suite_stats_unexpected={unexpected} "
            f"suite_stats_skipped={stats.get('skipped')} suite_stats_flaky={stats.get('flaky')}"
        )
        code = 0 if expected > 0 and unexpected == 0 else 1
open(summary_path, "w", encoding="utf-8").write("\n".join(lines) + "\n")
print(code)
PY
)"
cat "$LOG_DIR/suite-summary.txt" | tee -a "$LOG_FILE"
log "results_file=$RESULTS_FILE"
# Q10: per-scope bundle-manifest facts recorded by the smoke suite.
if [[ -f "$LOG_DIR/input-scope-results.json" ]]; then
  python3 -I - "$LOG_DIR/input-scope-results.json" <<'PY' | tee -a "$LOG_FILE"
import json
import sys

for record in json.load(open(sys.argv[1], encoding="utf-8")):
    pairs = ";".join(
        f"{pair['before_input_index']}->{pair['current_input_index']}:"
        f"changed={pair['changed_table_count']},degraded={pair['degraded_table_count']},"
        f"failed={pair['failed_table_count']},rows={pair['table_count']}"
        for pair in record["pairs"]
    )
    identities = ",".join(f"{item['pair_id']}={item['status']}" for item in record["identity_pairs"])
    print(
        f"input_scope={record['scope']} identity={record['identity']} "
        f"upload_status={record['upload_status']} operation_id={record['operation_id']} "
        f"preview_result_id={record['preview_result_id']} bundle_id={record['bundle_id']} "
        f"failed_pairs={record['failed_pairs']} pairs={pairs} identity_pairs={identities}"
    )
PY
else
  log "input_scope_results=missing"
fi
log "suite_exit=$SUITE_EXIT"
exit "$SUITE_EXIT"
